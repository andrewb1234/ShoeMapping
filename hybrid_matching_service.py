"""Service layer for hybrid ITML + K-Means shoe matching.

This module wraps HybridKMeansPipeline to provide the same interface as
SupervisedMatchingService, so precompute_recommendations.py can use either
backend interchangeably.

Distance-to-similarity conversion:
    similarity = 100 * exp(-distance / median_distance)
This gives 100 for distance=0, ~60 for median distance, and decays smoothly.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from hybrid_kmeans_pipeline import HybridKMeansPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/runrepeat_lab_tests.sqlite")
DEFAULT_SYNTHETIC_PATH = Path("data/synthetic_similarity_dataset.csv")


class HybridMatchingService:
    """Service layer that adapts HybridKMeansPipeline to the precompute interface."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        synthetic_path: Path | str = DEFAULT_SYNTHETIC_PATH,
        n_clusters: int = 8,
        include_pace: bool = True,
    ) -> None:
        self.db_path = Path(db_path)
        self.synthetic_path = Path(synthetic_path)
        self.n_clusters = n_clusters
        self.include_pace = include_pace

        self._pipeline: Optional[HybridKMeansPipeline] = None
        self._shoe_names: Optional[List[str]] = None

    def _ensure_fitted(self) -> HybridKMeansPipeline:
        if self._pipeline is None:
            logger.info("Fitting hybrid ITML + K-Means pipeline...")
            self._pipeline = HybridKMeansPipeline(
                db_path=self.db_path,
                synthetic_path=self.synthetic_path,
                n_clusters=self.n_clusters,
                include_pace=self.include_pace,
            )
            self._pipeline.fit()

            # Build name lookup list
            sf = self._pipeline.clusterer.shoe_frame
            self._shoe_names = [
                f"{row['brand']} {row['shoe_name']}" for _, row in sf.iterrows()
            ]
            logger.info("Hybrid pipeline ready (%d shoes)", len(self._shoe_names))
        return self._pipeline

    def find_shoe_by_name(self, shoe_name: str) -> Optional[str]:
        """Fuzzy-match a human-readable name to a shoe_id."""
        pipe = self._ensure_fitted()
        sf = pipe.clusterer.shoe_frame

        matches = get_close_matches(shoe_name, self._shoe_names, n=1, cutoff=0.6)
        if matches:
            matched_name = matches[0]
            idx = self._shoe_names.index(matched_name)
            return str(sf.iloc[idx]["shoe_id"])
        return None

    def get_recommendations(
        self,
        shoe_name: str,
        top_k: int = 5,
        terrain: Optional[str] = None,
        exclude_same_brand: bool = False,
    ) -> Dict[str, Any]:
        """Get recommendations using ITML-transformed distances.

        Computes the query shoe's distance to EVERY other shoe in the
        ITML-warped feature space, converts to a 0-100 similarity score,
        and returns the top-k.
        """
        pipe = self._ensure_fitted()
        sf = pipe.clusterer.shoe_frame
        transformed = pipe.transformed_matrix

        # Resolve query shoe
        shoe_id = self.find_shoe_by_name(shoe_name)
        if not shoe_id:
            return {
                "error": f'Shoe "{shoe_name}" not found',
                "suggestions": self._get_name_suggestions(shoe_name),
            }

        # Find index in the clusterer's shoe_frame
        id_matches = sf.index[sf["shoe_id"].astype(str) == shoe_id].tolist()
        if not id_matches:
            return {"error": f"shoe_id {shoe_id} not in feature matrix"}
        target_idx = id_matches[0]
        # Convert to positional index
        target_pos = sf.index.get_loc(target_idx)

        query_vector = transformed[target_pos]
        target_row = sf.iloc[target_pos]
        query_brand = str(target_row["brand"])

        # Compute distances to all shoes (vectorised)
        diffs = transformed - query_vector
        distances = np.linalg.norm(diffs, axis=1)

        # Convert distances → similarity scores using Gaussian kernel
        # Use median of non-zero distances as the scale parameter
        nonzero = distances[distances > 0]
        if len(nonzero) == 0:
            median_dist = 1.0
        else:
            median_dist = float(np.median(nonzero))

        similarities = 100.0 * np.exp(-distances / median_dist)

        # Build candidate list
        candidates: List[Dict[str, Any]] = []
        for pos in range(len(sf)):
            if pos == target_pos:
                continue
            row = sf.iloc[pos]
            if exclude_same_brand and str(row["brand"]) == query_brand:
                continue
            candidates.append({
                "shoe_id": str(row["shoe_id"]),
                "shoe_name": f"{row['brand']} {row['shoe_name']}",
                "brand": str(row["brand"]),
                "similarity_score": float(similarities[pos]),
                "distance": float(distances[pos]),
                "cluster_label": int(pipe.labels_[pos]),
            })

        # Sort by similarity descending, take top_k
        candidates.sort(key=lambda c: c["similarity_score"], reverse=True)
        top = candidates[:top_k]

        matched_shoe = {
            "shoe_id": shoe_id,
            "name": f"{target_row['brand']} {target_row['shoe_name']}",
            "brand": str(target_row["brand"]),
        }

        return {
            "query": shoe_name,
            "matched_shoe": matched_shoe,
            "recommendations": top,
            "algorithm": "hybrid_itml_kmeans",
            "cluster_label": int(pipe.labels_[target_pos]),
            "n_clusters": int(pipe.kmeans.n_clusters),
        }

    def _get_name_suggestions(self, shoe_name: str, max_suggestions: int = 5) -> List[str]:
        self._ensure_fitted()
        return get_close_matches(shoe_name, self._shoe_names, n=max_suggestions, cutoff=0.3)


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_service_instance: Optional[HybridMatchingService] = None


def get_hybrid_matching_service() -> HybridMatchingService:
    """Get or create the global hybrid matching service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = HybridMatchingService()
    return _service_instance

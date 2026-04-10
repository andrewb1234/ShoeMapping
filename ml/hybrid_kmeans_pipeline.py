"""Hybrid K-Means pipeline with Gemini-informed metric learning.

Follows the architecture originally described in the project design docs:
  Phase 1 – Feature Engineering  (delegated to ShoeKMeansClusterer)
  Phase 2 – Pairwise Targets     (Gemini similarity → Must-Link / Cannot-Link)
  Phase 3 – Distance Metric Learning (ITML from metric-learn)
  Phase 4 – K-Means Clustering   (in the ITML-transformed space)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

# Patch metric-learn compatibility with scikit-learn >= 1.6
# (force_all_finite was renamed to ensure_all_finite in sklearn validation funcs)
import metric_learn._util as _ml_util

def _wrap_sklearn_fn(fn):
    """Wrap a sklearn validation function to translate the renamed kwarg."""
    def wrapper(*args, **kwargs):
        if "force_all_finite" in kwargs:
            kwargs["ensure_all_finite"] = kwargs.pop("force_all_finite")
        return fn(*args, **kwargs)
    return wrapper

for _name in ("check_X_y", "check_array"):
    _orig = getattr(_ml_util, _name, None)
    if _orig is not None:
        setattr(_ml_util, _name, _wrap_sklearn_fn(_orig))

from metric_learn import ITML

from shoe_clustering import ShoeKMeansClusterer, PACE_LABELS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/runrepeat_lab_tests.sqlite")
DEFAULT_SYNTHETIC_PATH = Path("data/synthetic_similarity_dataset.csv")
DEFAULT_MUST_LINK_THRESHOLD = 60
DEFAULT_CANNOT_LINK_THRESHOLD = 15


class HybridKMeansPipeline:
    """K-Means clustering in an ITML-warped feature space informed by Gemini scores."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        synthetic_path: Path | str = DEFAULT_SYNTHETIC_PATH,
        n_clusters: int = 8,
        n_neighbors: int = 5,
        terrain_filter: Optional[str] = None,
        must_link_threshold: float = DEFAULT_MUST_LINK_THRESHOLD,
        cannot_link_threshold: float = DEFAULT_CANNOT_LINK_THRESHOLD,
        random_state: int = 42,
        include_pace: bool = True,
    ) -> None:
        self.db_path = Path(db_path)
        self.synthetic_path = Path(synthetic_path)
        self.n_clusters = n_clusters
        self.n_neighbors = n_neighbors
        self.terrain_filter = terrain_filter
        self.must_link_threshold = must_link_threshold
        self.cannot_link_threshold = cannot_link_threshold
        self.random_state = random_state
        self.include_pace = include_pace

        # Runtime state set after fit()
        self.clusterer: Optional[ShoeKMeansClusterer] = None
        self.itml: Optional[ITML] = None
        self.transformed_matrix: Optional[np.ndarray] = None
        self.kmeans: Optional[KMeans] = None
        self.labels_: Optional[np.ndarray] = None
        self.all_feature_names: List[str] = []

    # ------------------------------------------------------------------
    # Phase 2: Convert Gemini scores to pairwise constraints
    # ------------------------------------------------------------------

    def _load_pairwise_constraints(
        self, shoe_ids: pd.Series, scaled_matrix: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Load synthetic dataset and produce (pairs, labels) arrays for ITML.

        Returns:
            pairs  – (N, 2, D) float array of feature-vector pairs
            labels – (N,)      int array: +1 = Must-Link, -1 = Cannot-Link
        """
        syn = pd.read_csv(self.synthetic_path)
        logger.info(
            f"Loaded {len(syn)} synthetic pairs from {self.synthetic_path} "
            f"(score range {syn['similarity_score'].min()}-{syn['similarity_score'].max()})"
        )

        shoe_id_to_idx = {sid: idx for idx, sid in enumerate(shoe_ids)}

        pair_vectors: List[np.ndarray] = []
        labels: List[int] = []

        must_link_count = 0
        cannot_link_count = 0
        dropped_count = 0
        unmapped_count = 0

        for _, row in syn.iterrows():
            a_id = row["shoe_a_id"]
            b_id = row["shoe_b_id"]

            idx_a = shoe_id_to_idx.get(a_id)
            idx_b = shoe_id_to_idx.get(b_id)
            if idx_a is None or idx_b is None:
                unmapped_count += 1
                continue

            score = row["similarity_score"]
            if score >= self.must_link_threshold:
                pair_vectors.append(np.stack([scaled_matrix[idx_a], scaled_matrix[idx_b]]))
                labels.append(1)
                must_link_count += 1
            elif score <= self.cannot_link_threshold:
                pair_vectors.append(np.stack([scaled_matrix[idx_a], scaled_matrix[idx_b]]))
                labels.append(-1)
                cannot_link_count += 1
            else:
                dropped_count += 1

        logger.info(
            f"Pairwise constraints: {must_link_count} Must-Link (>={self.must_link_threshold}), "
            f"{cannot_link_count} Cannot-Link (<={self.cannot_link_threshold}), "
            f"{dropped_count} dropped (ambiguous), {unmapped_count} unmapped"
        )

        if not pair_vectors:
            raise ValueError(
                "No valid pairwise constraints found. Check thresholds or synthetic dataset."
            )

        return np.array(pair_vectors), np.array(labels, dtype=int)

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def fit(self) -> "HybridKMeansPipeline":
        """Run the full 4-phase pipeline."""

        # Phase 1: Feature Engineering
        logger.info("Phase 1: Feature engineering via ShoeKMeansClusterer")
        self.clusterer = ShoeKMeansClusterer(
            db_path=self.db_path,
            terrain_filter=self.terrain_filter,
            include_pace=self.include_pace,
        )
        scaled_matrix, feature_names = self.clusterer.get_preprocessed_data()
        self.all_feature_names = feature_names
        shoe_ids = self.clusterer.shoe_frame["shoe_id"]
        logger.info(f"Feature matrix shape: {scaled_matrix.shape}, features: {feature_names}")

        # Phase 2: Pairwise Targets
        logger.info("Phase 2: Building pairwise constraints from Gemini scores")
        pairs, labels = self._load_pairwise_constraints(shoe_ids, scaled_matrix)

        # Phase 3: Distance Metric Learning (ITML)
        logger.info("Phase 3: Training ITML metric learner")
        self.itml = ITML(random_state=self.random_state, max_iter=1000)
        self.itml.fit(pairs, labels)
        self.transformed_matrix = self.itml.transform(scaled_matrix)
        logger.info(f"Transformed matrix shape: {self.transformed_matrix.shape}")

        # Phase 4: K-Means in transformed space
        logger.info("Phase 4: K-Means clustering in ITML-warped space")
        effective_clusters = max(1, min(self.n_clusters, len(scaled_matrix)))
        self.kmeans = KMeans(
            n_clusters=effective_clusters,
            random_state=self.random_state,
            n_init=10,
        )
        self.kmeans.fit(self.transformed_matrix)
        self.labels_ = self.kmeans.labels_

        cluster_sizes = np.bincount(self.labels_)
        logger.info(
            f"Clustering complete: {effective_clusters} clusters, "
            f"sizes: {dict(enumerate(cluster_sizes.tolist()))}"
        )
        return self

    # ------------------------------------------------------------------
    # Recommendation
    # ------------------------------------------------------------------

    def recommend(
        self,
        shoe_name: str,
        n_neighbors: Optional[int] = None,
        shoe_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Recommend similar shoes using the hybrid ITML + K-Means pipeline."""
        if self.kmeans is None or self.transformed_matrix is None or self.labels_ is None:
            self.fit()

        assert self.clusterer is not None
        assert self.clusterer.shoe_frame is not None
        assert self.kmeans is not None
        assert self.transformed_matrix is not None
        assert self.labels_ is not None

        neighbor_count = max(1, n_neighbors or self.n_neighbors)
        target_index = self.clusterer._resolve_shoe_index(shoe_name, shoe_id=shoe_id)
        target_row = self.clusterer.shoe_frame.iloc[target_index]

        query_vector = self.transformed_matrix[target_index].reshape(1, -1)
        cluster_label = int(self.kmeans.predict(query_vector)[0])

        # Find all shoes in the same cluster, rank by distance
        cluster_indices = np.where(self.labels_ == cluster_label)[0]
        cluster_vectors = self.transformed_matrix[cluster_indices]
        distances = np.linalg.norm(cluster_vectors - query_vector, axis=1)

        ranked = sorted(
            zip(cluster_indices.tolist(), distances.tolist()),
            key=lambda x: x[1],
        )

        nearest: List[Dict[str, Any]] = []
        for idx, dist in ranked:
            if idx == target_index:
                continue
            row = self.clusterer.shoe_frame.iloc[idx]
            nearest.append(
                {
                    "shoe_id": str(row["shoe_id"]),
                    "brand": str(row["brand"]),
                    "shoe_name": str(row["shoe_name"]),
                    "source_url": str(row["source_url"]),
                    "cluster_label": int(self.labels_[idx]),
                    "distance_to_query": float(dist),
                }
            )
            if len(nearest) >= neighbor_count:
                break

        return {
            "query": shoe_name,
            "matched_shoe": {
                "shoe_id": str(target_row["shoe_id"]),
                "brand": str(target_row["brand"]),
                "shoe_name": str(target_row["shoe_name"]),
                "source_url": str(target_row["source_url"]),
                "cluster_label": cluster_label,
            },
            "cluster_label": cluster_label,
            "cluster_size": int(len(cluster_indices)),
            "nearest_shoes": nearest,
            "feature_names": self.all_feature_names,
            "n_clusters": int(self.kmeans.n_clusters),
            "pipeline": "hybrid_itml_kmeans",
        }


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Hybrid K-Means pipeline with Gemini-informed ITML metric learning"
    )
    parser.add_argument("shoe_name", help="Human-readable shoe name to look up")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--synthetic-path", type=Path, default=DEFAULT_SYNTHETIC_PATH)
    parser.add_argument("--clusters", type=int, default=8)
    parser.add_argument("--neighbors", type=int, default=5)
    parser.add_argument("--terrain", type=str, default=None)
    parser.add_argument("--must-link", type=float, default=DEFAULT_MUST_LINK_THRESHOLD)
    parser.add_argument("--cannot-link", type=float, default=DEFAULT_CANNOT_LINK_THRESHOLD)
    parser.add_argument("--no-pace", action="store_true", help="Disable Pace one-hot features")

    args = parser.parse_args()

    pipeline = HybridKMeansPipeline(
        db_path=args.db_path,
        synthetic_path=args.synthetic_path,
        n_clusters=args.clusters,
        n_neighbors=args.neighbors,
        terrain_filter=args.terrain,
        must_link_threshold=args.must_link,
        cannot_link_threshold=args.cannot_link,
        include_pace=not args.no_pace,
    )

    result = pipeline.recommend(args.shoe_name, n_neighbors=args.neighbors)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

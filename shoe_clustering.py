"""RunRepeat shoe clustering utilities.

This module builds a K-means model over RunRepeat lab-test metrics and lets
callers look up a shoe by human-readable name to get its cluster label and
nearest neighbors.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from sklearn.cluster import KMeans
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
except ImportError:  # pragma: no cover - handled at runtime with a clear error
    KMeans = None
    SimpleImputer = None
    StandardScaler = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/runrepeat_lab_tests.sqlite")
DEFAULT_FEATURES = [
    "Drop",
    "Heel stack",
    "Forefoot stack",
    "Energy return heel",
    "Weight",
    "Midsole softness (old method)",
    "Torsional rigidity",
]

FEATURE_ALIASES: Dict[str, Sequence[str]] = {
    "Drop": ("Drop",),
    "Heel stack": ("Heel stack",),
    "Forefoot stack": ("Forefoot stack",),
    "Energy return heel": ("Energy return heel", "Energy return (heel)", "Energy return"),
    "Weight": ("Weight",),
    "Midsole softness (old method)": (
        "Midsole softness (old method)",
        "Midsole softness",
    ),
    "Torsional rigidity": ("Torsional rigidity", "Torsional rigidity (old method)"),
}


@dataclass(frozen=True)
class ShoeSummary:
    """Compact shoe metadata used in clustering responses."""

    shoe_id: str
    brand: str
    shoe_name: str
    source_url: str
    crawled_at: str
    audience_verdict: Optional[int]
    feature_values: Dict[str, Optional[float]]
    raw_lab_test_values: Dict[str, Optional[str]]
    cluster_label: int
    distance_to_query: Optional[float] = None
    distance_to_centroid: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "shoe_id": self.shoe_id,
            "brand": self.brand,
            "shoe_name": self.shoe_name,
            "source_url": self.source_url,
            "crawled_at": self.crawled_at,
            "audience_verdict": self.audience_verdict,
            "feature_values": self.feature_values,
            "raw_lab_test_values": self.raw_lab_test_values,
            "cluster_label": self.cluster_label,
        }
        if self.distance_to_query is not None:
            payload["distance_to_query"] = self.distance_to_query
        if self.distance_to_centroid is not None:
            payload["distance_to_centroid"] = self.distance_to_centroid
        return payload


class ShoeKMeansClusterer:
    """Train a K-means model over RunRepeat shoes and generate recommendations."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        n_clusters: int = 8,
        n_neighbors: int = 5,
        random_state: int = 42,
        feature_names: Optional[Sequence[str]] = None,
        terrain_filter: Optional[str] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.n_clusters = max(1, n_clusters)
        self.n_neighbors = max(1, n_neighbors)
        self.random_state = random_state
        self.feature_names = list(feature_names or DEFAULT_FEATURES)
        self.terrain_filter = terrain_filter

        self.imputer = None
        self.scaler = None
        self.model: Optional[KMeans] = None

        self.shoe_frame: Optional[pd.DataFrame] = None
        self.feature_frame: Optional[pd.DataFrame] = None
        self.scaled_matrix: Optional[np.ndarray] = None
        self.labels_: Optional[np.ndarray] = None
        self._search_keys: Optional[pd.Series] = None

    @staticmethod
    def _require_ml_dependencies() -> None:
        if KMeans is None or SimpleImputer is None or StandardScaler is None:
            raise ImportError(
                "scikit-learn is required for clustering. Install dependencies with `pip install -r requirements.txt`."
            )

    @staticmethod
    def _safe_json_loads(value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            return {}
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            logger.warning("Failed to parse lab_test_results JSON payload")
            return {}

    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = "" if value is None else str(value)
        text = text.lower().replace("review", " ")
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _parse_numeric(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float, np.integer, np.floating)):
            if pd.isna(value):
                return None
            return float(value)

        text = str(value).strip()
        if not text or text.lower() in {"none", "n/a", "na", "nan", "-"}:
            return None

        grams_match = re.search(r"\((\d+(?:\.\d+)?)\s*g\)", text, flags=re.IGNORECASE)
        if grams_match:
            return float(grams_match.group(1))

        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if match:
            return float(match.group(0))

        return None

    def _load_shoe_rows(self) -> pd.DataFrame:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(
                """
                SELECT shoe_id, brand, shoe_name, source_url, audience_verdict, lab_test_results, crawled_at
                FROM shoes
                """,
                conn,
            )

        if df.empty:
            raise ValueError(f"No shoe rows found in database: {self.db_path}")

        df["lab_test_results"] = df["lab_test_results"].apply(self._safe_json_loads)
        
        # Apply terrain filter if specified
        if self.terrain_filter:
            def matches_terrain(lab_results: Dict[str, Any]) -> bool:
                terrain = lab_results.get("Terrain")
                if terrain is None:
                    return False
                terrain_norm = self._normalize_text(terrain)
                filter_norm = self._normalize_text(self.terrain_filter)
                return terrain_norm == filter_norm
            
            mask = df["lab_test_results"].apply(matches_terrain)
            df = df[mask]
            if df.empty:
                raise ValueError(f"No shoes found matching terrain filter: {self.terrain_filter}")
        
        return df

    def _resolve_lab_test_key(self, lab_results: Dict[str, Any], feature_name: str) -> Tuple[Optional[str], Optional[Any]]:
        aliases = FEATURE_ALIASES.get(feature_name, (feature_name,))
        normalized_results = {self._normalize_text(key): key for key in lab_results.keys()}

        for alias in aliases:
            alias_key = normalized_results.get(self._normalize_text(alias))
            if alias_key is not None:
                return alias_key, lab_results.get(alias_key)
        return None, None

    def _build_feature_frame(self, shoe_rows: pd.DataFrame) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []
        search_keys: List[str] = []

        for _, row in shoe_rows.iterrows():
            lab_results = row["lab_test_results"] if isinstance(row["lab_test_results"], dict) else {}
            feature_values: Dict[str, Optional[float]] = {}
            raw_feature_values: Dict[str, Optional[str]] = {}

            for feature_name in self.feature_names:
                raw_key, raw_value = self._resolve_lab_test_key(lab_results, feature_name)
                feature_values[feature_name] = self._parse_numeric(raw_value)
                raw_feature_values[feature_name] = None if raw_key is None else str(raw_value)

            rows.append(
                {
                    "shoe_id": row["shoe_id"],
                    "brand": row["brand"],
                    "shoe_name": row["shoe_name"],
                    "source_url": row["source_url"],
                    "audience_verdict": row["audience_verdict"],
                    "crawled_at": row["crawled_at"],
                    "lab_test_results": lab_results,
                    "feature_values": feature_values,
                    "raw_feature_values": raw_feature_values,
                    **feature_values,
                }
            )
            search_keys.append(self._normalize_text(row["shoe_name"]))

        feature_frame = pd.DataFrame(rows)
        feature_frame = feature_frame.dropna(axis=0, how="all", subset=self.feature_names)
        # Build search_keys after filtering to align indices
        self._search_keys = pd.Series([self._normalize_text(r["shoe_name"]) for _, r in feature_frame.iterrows()], index=feature_frame.index)
        feature_frame = feature_frame.reset_index(drop=True)
        self._search_keys = self._search_keys.reset_index(drop=True)
        return feature_frame

    def get_preprocessed_data(self) -> tuple[np.ndarray, List[str]]:
        """Get preprocessed feature matrix and feature names without fitting final model.
        
        Returns:
            Tuple of (scaled_feature_matrix, feature_names)
        """
        self._require_ml_dependencies()
        self.imputer = SimpleImputer(strategy="median")
        self.scaler = StandardScaler()
        shoe_rows = self._load_shoe_rows()
        feature_frame = self._build_feature_frame(shoe_rows)
        if feature_frame.empty:
            raise ValueError("No shoes contain enough feature data for clustering.")

        # Check for features with >30% missing values
        feature_matrix = feature_frame[self.feature_names]
        missing_counts = feature_matrix.isna().sum()
        total_shoes = len(feature_matrix)
        
        features_to_keep = []
        for feature in self.feature_names:
            missing_pct = (missing_counts[feature] / total_shoes) * 100
            if missing_pct > 30:
                logger.warning(f"Feature '{feature}' has {missing_pct:.1f}% missing values (>30%), excluding from clustering")
            else:
                features_to_keep.append(feature)
        
        if not features_to_keep:
            raise ValueError("No features have sufficient data (<30% missing) for clustering")
        
        # Update feature names to only include features with sufficient data
        self.feature_names = features_to_keep
        feature_matrix = feature_matrix[self.feature_names]
        
        imputed = self.imputer.fit_transform(feature_matrix)
        scaled = self.scaler.fit_transform(imputed)
        
        return scaled, self.feature_names

    def fit(self) -> "ShoeKMeansClusterer":
        """Load shoes from SQLite and fit the clustering pipeline."""
        self._require_ml_dependencies()
        self.imputer = SimpleImputer(strategy="median")
        self.scaler = StandardScaler()
        shoe_rows = self._load_shoe_rows()
        feature_frame = self._build_feature_frame(shoe_rows)
        if feature_frame.empty:
            raise ValueError("No shoes contain enough feature data for clustering.")

        # Check for features with >30% missing values
        feature_matrix = feature_frame[self.feature_names]
        missing_counts = feature_matrix.isna().sum()
        total_shoes = len(feature_matrix)
        
        features_to_keep = []
        for feature in self.feature_names:
            missing_pct = (missing_counts[feature] / total_shoes) * 100
            if missing_pct > 30:
                logger.warning(f"Feature '{feature}' has {missing_pct:.1f}% missing values (>30%), excluding from clustering")
            else:
                features_to_keep.append(feature)
        
        if not features_to_keep:
            raise ValueError("No features have sufficient data (<30% missing) for clustering")
        
        # Update feature names to only include features with sufficient data
        self.feature_names = features_to_keep
        feature_matrix = feature_matrix[self.feature_names]
        
        imputed = self.imputer.fit_transform(feature_matrix)
        scaled = self.scaler.fit_transform(imputed)

        effective_clusters = max(1, min(self.n_clusters, len(feature_frame)))
        self.model = KMeans(n_clusters=effective_clusters, random_state=self.random_state, n_init=10)
        self.model.fit(scaled)

        self.shoe_frame = feature_frame
        self.feature_frame = feature_matrix.copy()
        self.scaled_matrix = scaled
        self.labels_ = self.model.labels_
        return self

    def _ensure_fitted(self) -> None:
        if self.model is None or self.shoe_frame is None or self.scaled_matrix is None or self.labels_ is None:
            self.fit()

    def _resolve_shoe_index(self, shoe_name: str, shoe_id: Optional[str] = None) -> int:
        self._ensure_fitted()
        assert self.shoe_frame is not None
        assert self._search_keys is not None

        if shoe_id:
            exact_id_matches = [idx for idx, candidate in enumerate(self.shoe_frame["shoe_id"].astype(str)) if candidate == shoe_id]
            if exact_id_matches:
                return exact_id_matches[0]

        query = self._normalize_text(shoe_name)
        if not query:
            raise ValueError("shoe_name cannot be empty")

        exact_matches = [idx for idx, candidate in enumerate(self._search_keys) if candidate == query]
        if exact_matches:
            return exact_matches[0]

        containing_matches = [idx for idx, candidate in enumerate(self._search_keys) if query in candidate or candidate in query]
        if len(containing_matches) == 1:
            return containing_matches[0]

        if containing_matches:
            return max(
                containing_matches,
                key=lambda idx: SequenceMatcher(None, query, self._search_keys.iloc[idx]).ratio(),
            )

        close_matches = get_close_matches(query, list(self._search_keys), n=1, cutoff=0.45)
        if close_matches:
            return list(self._search_keys).index(close_matches[0])

        raise ValueError(f"Could not find a shoe matching: {shoe_name}")

    def _row_to_summary(
        self,
        row: pd.Series,
        cluster_label: int,
        distance_to_query: Optional[float] = None,
        distance_to_centroid: Optional[float] = None,
    ) -> ShoeSummary:
        feature_values = row["feature_values"] if isinstance(row["feature_values"], dict) else {}
        raw_feature_values = row["raw_feature_values"] if isinstance(row["raw_feature_values"], dict) else {}
        return ShoeSummary(
            shoe_id=str(row["shoe_id"]),
            brand=str(row["brand"]),
            shoe_name=str(row["shoe_name"]),
            source_url=str(row["source_url"]),
            crawled_at=str(row["crawled_at"]),
            audience_verdict=None if pd.isna(row["audience_verdict"]) else int(row["audience_verdict"]),
            feature_values={name: (None if value is None or pd.isna(value) else float(value)) for name, value in feature_values.items()},
            raw_lab_test_values={name: (None if value is None else str(value)) for name, value in raw_feature_values.items()},
            cluster_label=int(cluster_label),
            distance_to_query=distance_to_query,
            distance_to_centroid=distance_to_centroid,
        )

    def recommend(self, shoe_name: str, n_neighbors: Optional[int] = None, shoe_id: Optional[str] = None) -> Dict[str, Any]:
        """Return cluster info and nearest shoes for a human-readable shoe name."""
        self._ensure_fitted()
        assert self.model is not None
        assert self.shoe_frame is not None
        assert self.scaled_matrix is not None
        assert self.labels_ is not None

        neighbor_count = max(1, n_neighbors or self.n_neighbors)
        target_index = self._resolve_shoe_index(shoe_name, shoe_id=shoe_id)
        target_row = self.shoe_frame.iloc[target_index]
        query_vector = self.scaled_matrix[target_index].reshape(1, -1)
        cluster_label = int(self.model.predict(query_vector)[0])
        centroid_vector = self.model.cluster_centers_[cluster_label].reshape(1, -1)
        centroid_raw = self.scaler.inverse_transform(centroid_vector)[0]

        target_cluster_indices = np.where(self.labels_ == cluster_label)[0]
        target_cluster_vectors = self.scaled_matrix[target_cluster_indices]
        distances = np.linalg.norm(target_cluster_vectors - query_vector, axis=1)

        ranked_cluster_members = sorted(
            zip(target_cluster_indices.tolist(), distances.tolist()),
            key=lambda item: item[1],
        )

        nearest_members: List[Dict[str, Any]] = []
        for idx, distance in ranked_cluster_members:
            if idx == target_index:
                continue
            row = self.shoe_frame.iloc[idx]
            member_summary = self._row_to_summary(
                row,
                cluster_label=int(self.labels_[idx]),
                distance_to_query=float(distance),
                distance_to_centroid=float(np.linalg.norm(self.scaled_matrix[idx] - centroid_vector[0])),
            )
            nearest_members.append(member_summary.to_dict())
            if len(nearest_members) >= neighbor_count:
                break

        matched_summary = self._row_to_summary(
            target_row,
            cluster_label=cluster_label,
            distance_to_query=0.0,
            distance_to_centroid=float(np.linalg.norm(query_vector[0] - centroid_vector[0])),
        )

        cluster_center = {
            name: (None if pd.isna(value) else float(value))
            for name, value in zip(self.feature_names, centroid_raw)
        }

        return {
            "query": shoe_name,
            "matched_shoe": matched_summary.to_dict(),
            "cluster_label": cluster_label,
            "cluster_size": int(len(target_cluster_indices)),
            "cluster_center": cluster_center,
            "nearest_shoes": nearest_members,
            "feature_names": self.feature_names,
            "n_clusters": int(self.model.n_clusters),
        }


def recommend_similar_shoes(
    shoe_name: str,
    db_path: Path | str = DEFAULT_DB_PATH,
    n_clusters: int = 8,
    n_neighbors: int = 5,
    terrain_filter: Optional[str] = None,
    shoe_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience wrapper for one-off clustering lookups."""
    clusterer = ShoeKMeansClusterer(db_path=db_path, n_clusters=n_clusters, n_neighbors=n_neighbors, terrain_filter=terrain_filter)
    return clusterer.recommend(shoe_name, n_neighbors=n_neighbors, shoe_id=shoe_id)


def main() -> None:
    """CLI entry point for manual clustering lookups."""
    import argparse

    parser = argparse.ArgumentParser(description="Run K-means clustering for a RunRepeat shoe")
    parser.add_argument("shoe_name", help="Human-readable shoe name to look up")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Path to the RunRepeat SQLite database")
    parser.add_argument("--clusters", type=int, default=8, help="Number of K-means clusters")
    parser.add_argument("--neighbors", type=int, default=5, help="Number of nearest shoes to return")
    parser.add_argument("--terrain", type=str, help="Filter by terrain (e.g., 'Road' or 'Trail'). If not specified, includes all shoes.")

    args = parser.parse_args()
    result = recommend_similar_shoes(
        args.shoe_name,
        db_path=args.db_path,
        n_clusters=args.clusters,
        n_neighbors=args.neighbors,
        terrain_filter=args.terrain,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Elbow Method helper to estimate the optimal number of K-means clusters.

Run this script to plot Within-Cluster Sum of Squares (WCSS) for K=1..12.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import numpy as np

from shoe_clustering import DEFAULT_DB_PATH, ShoeKMeansClusterer

try:
    from sklearn.cluster import KMeans
except ImportError:  # pragma: no cover - handled at runtime with a clear error
    KMeans = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def prepare_data(db_path: Path | str, terrain_filter: str | None = None) -> tuple[np.ndarray, List[str]]:
    """Load and preprocess data once for repeated K-means runs."""
    clusterer = ShoeKMeansClusterer(db_path=db_path, terrain_filter=terrain_filter)
    scaled_matrix, feature_names = clusterer.get_preprocessed_data()
    return scaled_matrix, feature_names


def compute_wcss_for_k_range(
    scaled_matrix: np.ndarray, k_range: range = range(1, 13), random_state: int = 42, n_init: int = 10
) -> List[float]:
    """Return WCSS for each K in the given range."""
    if KMeans is None:
        raise ImportError("scikit-learn is required for clustering")

    wcss_values = []
    for k in k_range:
        logger.info(f"Fitting K-means with K={k}...")
        kmeans = KMeans(n_clusters=k, random_state=random_state, n_init=n_init)
        kmeans.fit(scaled_matrix)
        wcss = kmeans.inertia_
        wcss_values.append(wcss)
        logger.info(f"K={k}: WCSS={wcss:.2f}")
    return wcss_values


def plot_elbow_curve(k_values: List[int], wcss_values: List[float], title: str = "Elbow Method") -> None:
    """Plot the WCSS vs number of clusters curve."""
    plt.figure(figsize=(8, 5))
    plt.plot(k_values, wcss_values, marker="o", linestyle="-")
    plt.title(title)
    plt.xlabel("Number of clusters (K)")
    plt.ylabel("Within-Cluster Sum of Squares (WCSS)")
    plt.xticks(k_values)
    plt.grid(True, which="both", linestyle="--", linewidth=0.5)
    plt.tight_layout()
    plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Elbow Method to estimate optimal K for K-means.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Path to the RunRepeat SQLite database")
    parser.add_argument("--terrain", type=str, help="Filter by terrain (e.g., 'Road' or 'Trail'). If omitted, includes all shoes.")
    parser.add_argument("--max-k", type=int, default=12, help="Maximum number of clusters to test (default: 12)")
    parser.add_argument("--random-state", type=int, default=42, help="Random state for reproducibility")
    parser.add_argument("--n-init", type=int, default=10, help="Number of K-means initializations per K")
    args = parser.parse_args()

    if args.max_k < 1:
        raise ValueError("max-k must be at least 1")

    k_range = range(1, args.max_k + 1)

    logger.info(f"Preparing data (terrain={args.terrain or 'Both'})...")
    scaled_matrix, feature_names = prepare_data(args.db_path, terrain_filter=args.terrain)
    logger.info(f"Using {len(feature_names)} features on {scaled_matrix.shape[0]} shoes")

    wcss_values = compute_wcss_for_k_range(
        scaled_matrix, k_range=k_range, random_state=args.random_state, n_init=args.n_init
    )

    title = f"Elbow Method ({'Terrain: ' + args.terrain if args.terrain else 'All terrains'})"
    plot_elbow_curve(list(k_range), wcss_values, title=title)


if __name__ == "__main__":
    main()

"""Evaluation script for the supervised shoe matching model.

This script calculates various metrics including MAE, RMSE, and NDCG
to assess the quality of the supervised similarity predictions.
"""

import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from ml.supervised_shoe_matcher import SupervisedShoeMatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def dcg_at_k(relevances: List[float], k: int) -> float:
    """Calculate Discounted Cumulative Gain at position k."""
    relevances = relevances[:k]
    gains = [rel / math.log2(i + 2) for i, rel in enumerate(relevances)]
    return sum(gains)


def ndcg_at_k(true_relevances: List[float], predicted_scores: List[float], k: int) -> float:
    """Calculate Normalized Discounted Cumulative Gain at position k."""
    # Sort by predicted scores
    sorted_indices = sorted(range(len(predicted_scores)), key=lambda i: predicted_scores[i], reverse=True)
    ranked_relevances = [true_relevances[i] for i in sorted_indices]
    
    # Calculate DCG
    dcg = dcg_at_k(ranked_relevances, k)
    
    # Calculate IDCG (perfect ranking)
    ideal_relevances = sorted(true_relevances, reverse=True)
    idcg = dcg_at_k(ideal_relevances, k)
    
    # Avoid division by zero
    if idcg == 0:
        return 0.0
    
    return dcg / idcg


def evaluate_model(
    model_path: Path = Path("data/supervised_shoe_matcher.pkl"),
    test_dataset_path: Path = Path("data/synthetic_similarity_dataset.csv"),
    holdout_ratio: float = 0.2
) -> Dict[str, float]:
    """Evaluate the supervised model on various metrics."""
    
    logger.info("Loading model and test dataset...")
    
    # Load the trained matcher
    matcher = SupervisedShoeMatcher()
    matcher.load_model(model_path)
    matcher.load_shoes_from_db()
    
    # Load the synthetic dataset
    df = pd.read_csv(test_dataset_path)
    
    # Split into train/test (use different split from training)
    np.random.seed(42)  # Different seed for evaluation
    mask = np.random.random(len(df)) > holdout_ratio
    test_df = df[mask].copy()
    
    logger.info(f"Evaluating on {len(test_df)} holdout pairs")
    
    # Calculate regression metrics
    true_scores = test_df['similarity_score'].values
    predicted_scores = []
    
    for _, row in test_df.iterrows():
        try:
            pred_score = matcher.predict_similarity(row['shoe_a_id'], row['shoe_b_id'])
            predicted_scores.append(pred_score)
        except Exception as e:
            logger.warning(f"Failed to predict similarity for {row['shoe_a_name']} vs {row['shoe_b_name']}: {e}")
            predicted_scores.append(50.0)  # Default prediction
    
    predicted_scores = np.array(predicted_scores)
    
    # Regression metrics
    mae = mean_absolute_error(true_scores, predicted_scores)
    mse = mean_squared_error(true_scores, predicted_scores)
    rmse = math.sqrt(mse)
    
    # Ranking metrics (NDCG)
    # Group by shoe_a to evaluate ranking for each query shoe
    query_groups = test_df.groupby('shoe_a_id')
    ndcg_scores = []
    
    for query_shoe_id, group in query_groups:
        if len(group) < 2:  # Need at least 2 items to rank
            continue
        
        true_relevances = group['similarity_score'].tolist()
        pred_scores = []
        
        for _, row in group.iterrows():
            try:
                pred_score = matcher.predict_similarity(row['shoe_a_id'], row['shoe_b_id'])
                pred_scores.append(pred_score)
            except:
                pred_scores.append(50.0)
        
        # Calculate NDCG at different k values
        for k in [3, 5, 10]:
            if len(true_relevances) >= k:
                ndcg = ndcg_at_k(true_relevances, pred_scores, k)
                ndcg_scores.append(('ndcg@' + str(k), ndcg))
    
    # Average NDCG scores
    ndcg_metrics = {}
    for k in [3, 5, 10]:
        k_scores = [score for metric, score in ndcg_scores if metric == 'ndcg@' + str(k)]
        if k_scores:
            ndcg_metrics[f'ndcg@{k}'] = np.mean(k_scores)
    
    # Correlation metrics
    correlation = np.corrcoef(true_scores, predicted_scores)[0, 1]
    if np.isnan(correlation):
        correlation = 0.0
    
    # Accuracy within thresholds
    within_5 = np.mean(np.abs(true_scores - predicted_scores) <= 5)
    within_10 = np.mean(np.abs(true_scores - predicted_scores) <= 10)
    within_15 = np.mean(np.abs(true_scores - predicted_scores) <= 15)
    
    metrics = {
        'mae': mae,
        'mse': mse,
        'rmse': rmse,
        'correlation': correlation,
        'within_5_points': within_5,
        'within_10_points': within_10,
        'within_15_points': within_15,
        **ndcg_metrics
    }
    
    return metrics


def compare_with_kmeans(
    supervised_metrics: Dict[str, float],
    num_samples: int = 100
) -> Dict[str, float]:
    """Compare supervised model with baseline K-means approach."""
    
    logger.info("Comparing with K-means baseline...")
    
    # Load test samples
    df = pd.read_csv("data/synthetic_similarity_dataset.csv")
    sample_df = df.head(num_samples).copy()
    
    # For K-means, we'll use a simple heuristic based on cluster distance
    # This is a simplified comparison - in practice, K-means doesn't output similarity scores
    from ml.shoe_clustering import ShoeKMeansClusterer
    
    clusterer = ShoeKMeansClusterer(n_clusters=8, terrain_filter=None)
    
    kmeans_predictions = []
    for _, row in sample_df.iterrows():
        try:
            # Get cluster assignments
            result_a = clusterer.lookup_shoe(row['shoe_a_name'])
            result_b = clusterer.lookup_shoe(row['shoe_b_name'])
            
            if result_a and result_b:
                # Simple similarity: same cluster = 80, different clusters = 20
                if result_a['cluster_label'] == result_b['cluster_label']:
                    similarity = 80.0
                else:
                    similarity = 20.0
                kmeans_predictions.append(similarity)
            else:
                kmeans_predictions.append(50.0)
        except:
            kmeans_predictions.append(50.0)
    
    true_scores = sample_df['similarity_score'].values
    kmeans_predictions = np.array(kmeans_predictions)
    
    kmeans_mae = mean_absolute_error(true_scores, kmeans_predictions)
    kmeans_rmse = math.sqrt(mean_squared_error(true_scores, kmeans_predictions))
    
    logger.info(f"K-means baseline MAE: {kmeans_mae:.2f}, RMSE: {kmeans_rmse:.2f}")
    logger.info(f"Supervised model MAE: {supervised_metrics['mae']:.2f}, RMSE: {supervised_metrics['rmse']:.2f}")
    
    improvement_mae = ((kmeans_mae - supervised_metrics['mae']) / kmeans_mae) * 100
    improvement_rmse = ((kmeans_rmse - supervised_metrics['rmse']) / kmeans_rmse) * 100
    
    logger.info(f"Improvement: {improvement_mae:.1f}% MAE, {improvement_rmse:.1f}% RMSE")
    
    return {
        'kmeans_mae': kmeans_mae,
        'kmeans_rmse': kmeans_rmse,
        'mae_improvement_percent': improvement_mae,
        'rmse_improvement_percent': improvement_rmse
    }


def main():
    """Run full evaluation pipeline."""
    print("=" * 60)
    print("SUPERVISED SHOE MATCHING MODEL EVALUATION")
    print("=" * 60)
    
    # Check if model exists
    model_path = Path("data/supervised_shoe_matcher.pkl")
    if not model_path.exists():
        print(f"Error: Model not found at {model_path}")
        print("Please run supervised_shoe_matcher.py to train the model first.")
        return
    
    # Check if dataset exists
    dataset_path = Path("data/synthetic_similarity_dataset.csv")
    if not dataset_path.exists():
        print(f"Error: Dataset not found at {dataset_path}")
        print("Please run synthetic_dataset_generator.py to generate the dataset first.")
        return
    
    # Evaluate supervised model
    print("\n1. Evaluating supervised model...")
    metrics = evaluate_model()
    
    print("\n2. Supervised Model Metrics:")
    print("-" * 40)
    print(f"MAE: {metrics['mae']:.2f}")
    print(f"RMSE: {metrics['rmse']:.2f}")
    print(f"Correlation: {metrics['correlation']:.3f}")
    print(f"Within 5 points: {metrics['within_5_points']:.1%}")
    print(f"Within 10 points: {metrics['within_10_points']:.1%}")
    print(f"Within 15 points: {metrics['within_15_points']:.1%}")
    
    if 'ndcg@3' in metrics:
        print(f"NDCG@3: {metrics['ndcg@3']:.3f}")
    if 'ndcg@5' in metrics:
        print(f"NDCG@5: {metrics['ndcg@5']:.3f}")
    if 'ndcg@10' in metrics:
        print(f"NDCG@10: {metrics['ndcg@10']:.3f}")
    
    # Compare with K-means
    print("\n3. Comparing with K-means baseline...")
    comparison = compare_with_kmeans(metrics)
    
    print("\n4. Comparison Results:")
    print("-" * 40)
    print(f"K-means MAE: {comparison['kmeans_mae']:.2f}")
    print(f"Supervised MAE: {metrics['mae']:.2f}")
    print(f"Improvement: {comparison['mae_improvement_percent']:.1f}%")
    
    # Save evaluation results
    results = {
        'supervised_metrics': metrics,
        'kmeans_comparison': comparison
    }
    
    results_path = Path("data/model_evaluation_results.json")
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n5. Results saved to {results_path}")
    print("\n" + "=" * 60)
    print("EVALUATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()

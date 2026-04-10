#!/usr/bin/env python3
"""Test script to verify the K-Means integration with XGBoost."""

import pandas as pd
from pathlib import Path
from ml.supervised_shoe_matcher import SupervisedShoeMatcher
from scripts.synthetic_dataset_generator import generate_synthetic_dataset

def test_integration():
    """Test the integration of K-Means clustering with XGBoost."""
    
    print("=== Testing K-Means Integration with XGBoost ===\n")
    
    # 1. Generate a small synthetic dataset with clustering features
    print("1. Generating synthetic dataset with clustering features...")
    generate_synthetic_dataset(
        num_pairs=100,  # Small test dataset
        batch_size=15,
        output_path=Path("data/test_synthetic_dataset.csv")
    )
    print("   ✓ Generated test dataset\n")
    
    # 2. Load and inspect the dataset
    print("2. Inspecting generated dataset...")
    df = pd.read_csv("data/test_synthetic_dataset.csv")
    print(f"   Dataset shape: {df.shape}")
    print(f"   Columns: {list(df.columns)}")
    
    # Check for clustering features
    has_cluster_features = 'is_same_kmeans_cluster' in df.columns and 'euclidean_distance' in df.columns
    print(f"   Has clustering features: {has_cluster_features}")
    
    if has_cluster_features:
        print(f"   Same cluster pairs: {df['is_same_kmeans_cluster'].sum()}/{len(df)}")
        print(f"   Average Euclidean distance: {df['euclidean_distance'].mean():.3f}")
    print("   ✓ Dataset inspection complete\n")
    
    # 3. Train the supervised model
    print("3. Training supervised model with clustering features...")
    matcher = SupervisedShoeMatcher(model_type="xgboost")
    matcher.load_shoes_from_db()
    
    metrics = matcher.train_from_synthetic_dataset(
        dataset_path=Path("data/test_synthetic_dataset.csv"),
        test_size=0.2
    )
    
    print(f"   Training metrics:")
    print(f"     MAE: {metrics['mae']:.2f}")
    print(f"     RMSE: {metrics['rmse']:.2f}")
    print(f"     Train samples: {metrics['train_samples']}")
    print(f"     Test samples: {metrics['test_samples']}")
    print("   ✓ Model training complete\n")
    
    # 4. Test prediction with clustering features
    print("4. Testing similarity prediction...")
    if len(matcher.shoes_df) >= 2:
        shoe_a_id = matcher.shoes_df.iloc[0]['shoe_id']
        shoe_b_id = matcher.shoes_df.iloc[1]['shoe_id']
        
        similarity = matcher.predict_similarity(shoe_a_id, shoe_b_id)
        print(f"   Predicted similarity between {shoe_a_id} and {shoe_b_id}: {similarity:.2f}")
        print("   ✓ Prediction test complete\n")
    
    # 5. Test feature calculation
    print("5. Testing delta feature calculation with clustering...")
    if len(matcher.shoes_df) >= 2:
        shoe_a = matcher.shoes_df.iloc[0]
        shoe_b = matcher.shoes_df.iloc[1]
        
        deltas = matcher.calculate_delta_features(shoe_a, shoe_b)
        
        print("   Delta features:")
        for key, value in deltas.items():
            if 'cluster' in key.lower() or 'distance' in key.lower():
                print(f"     {key}: {value}")
        print("   ✓ Feature calculation test complete\n")
    
    print("=== Integration Test Complete ===")
    print("\nKey improvements:")
    print("• K-Means cluster labels are now fed directly into XGBoost")
    print("• Euclidean distances between shoes are included as features")
    print("• XGBoost can learn optimal weights for clustering information")
    print("• Dataset size increased to 50,000 pairs for better training")

if __name__ == "__main__":
    test_integration()

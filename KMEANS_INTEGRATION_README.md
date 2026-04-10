# K-Means Integration with XGBoost for Shoe Similarity Matching

## Overview

We've enhanced the supervised shoe matching algorithm by integrating K-Means clustering data directly into the XGBoost model. This allows the model to learn optimal weights for clustering information organically, rather than blending scores at the end.

## Key Improvements

### 1. Direct Feature Integration
Instead of post-processing similarity scores, we now feed K-Means clustering data directly into XGBoost as features:

- **`is_same_kmeans_cluster`**: Binary feature indicating whether two shoes belong to the same cluster
- **`euclidean_distance`**: Continuous feature representing the distance between shoes in the scaled feature space

### 2. Increased Dataset Size
- Expanded from 10,000 to **50,000 shoe pairs** for better model training
- Larger dataset helps XGBoost learn more accurate patterns and weights

### 3. Algorithm Learning
XGBoost now automatically learns rules like:
- "If Euclidean distance > X, heavily penalize similarity"
- "If shoes are in the same cluster, increase similarity weight"
- Optimal balance between clustering and feature-based similarity

## Implementation Details

### Feature Engineering
```python
# Inside calculate_delta_features()
deltas['is_same_kmeans_cluster'] = 1 if shoe_a['cluster_label'] == shoe_b['cluster_label'] else 0
deltas['euclidean_distance'] = calculate_distance(shoe_a_vector, shoe_b_vector)
```

### Model Training
The model now trains on these additional features:
- All original delta features (Drop, Heel stack, etc.)
- Categorical features (Terrain, Arch Support)
- **NEW**: K-Means cluster membership
- **NEW**: Euclidean distance in feature space

## Usage

### Generate Full Dataset
```bash
python scripts/synthetic_dataset_generator.py
```
This creates a 50,000 pair dataset with clustering features.

### Train Model with Clustering
```python
from ml.supervised_shoe_matcher import SupervisedShoeMatcher

matcher = SupervisedShoeMatcher(model_type="xgboost")
matcher.load_shoes_from_db()  # Automatically initializes K-Means
metrics = matcher.train_from_synthetic_dataset()
matcher.save_model()
```

### Test Integration
```bash
python scripts/test_kmeans_integration.py
```

## Benefits

1. **Better Accuracy**: XGBoost learns optimal weights for clustering information
2. **More Robust**: Model considers both feature-level differences and cluster-level similarities
3. **Scalable**: Approach works with any number of clusters or features
4. **Interpretable**: Feature importance scores show how much weight XGBoost gives to clustering

## Technical Notes

- K-Means uses 8 clusters by default (configurable)
- Shoes with insufficient feature data are filtered out during clustering
- Euclidean distances are calculated in the scaled feature space
- Model saves/loads cluster information for consistency

## Future Enhancements

- Experiment with different numbers of clusters
- Try other clustering algorithms (DBSCAN, Hierarchical)
- Add cluster distance to centroid as additional feature
- Implement cluster-specific models

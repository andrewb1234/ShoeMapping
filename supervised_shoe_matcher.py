"""Supervised shoe matching algorithm using XGBoost.

This module implements the new matching algorithm that trains on synthetic
similarity scores and predicts similarity between any shoe pair.
"""

import json
import logging
import pickle
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# Import clustering functionality
from shoe_clustering import ShoeKMeansClusterer

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

FEATURE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "Drop": ("Drop",),
    "Heel stack": ("Heel stack",),
    "Forefoot stack": ("Forefoot stack",),
    "Energy return heel": ("Energy return heel", "Energy return (heel)", "Energy return"),
    "Weight": ("Weight",),
    "Midsole softness (old method)": ("Midsole softness (old method)", "Midsole softness"),
    "Torsional rigidity": ("Torsional rigidity",),
}


class SupervisedShoeMatcher:
    """Supervised learning-based shoe similarity matcher."""
    
    def __init__(self, model_type: str = "xgboost"):
        """
        Initialize the matcher.
        
        Args:
            model_type: Either "xgboost" or "randomforest"
        """
        self.model_type = model_type
        self.model = None
        self.imputer = SimpleImputer(strategy="median")
        self.scaler = StandardScaler()
        self.feature_columns = None
        self.shoes_df = None
        self.clusterer = None
        self.shoe_features = None
        
    def load_shoes_from_db(self, db_path: Path = DEFAULT_DB_PATH) -> pd.DataFrame:
        """Load all shoes from the database and flatten lab test results."""
        conn = sqlite3.connect(db_path)
        
        # Load basic shoe data
        df = pd.read_sql_query("SELECT shoe_id, brand, shoe_name, lab_test_results FROM shoes", conn)
        conn.close()
        
        # Filter out shoes with no lab test results
        df = df[df['lab_test_results'].notna()].copy()
        
        # Parse JSON lab test results
        lab_results = df['lab_test_results'].apply(json.loads)
        
        # Create feature columns
        for feature in DEFAULT_FEATURES:
            df[feature] = None
        
        # Add categorical columns
        df['Terrain'] = None
        df['Arch Support'] = None
            
        # Extract features using aliases
        for idx, results in enumerate(lab_results):
            # Extract numeric features
            for feature, aliases in FEATURE_ALIASES.items():
                for alias in aliases:
                    if alias in results and results[alias] is not None:
                        # Try to convert to numeric
                        try:
                            value = float(str(results[alias]).replace('mm', '').replace('g', '').strip())
                            df.at[df.index[idx], feature] = value
                            break
                        except (ValueError, TypeError):
                            continue
            
            # Extract categorical features
            if 'Terrain' in results and results['Terrain'] is not None:
                df.at[df.index[idx], 'Terrain'] = results['Terrain']
            if 'Arch Support' in results and results['Arch Support'] is not None:
                df.at[df.index[idx], 'Arch Support'] = results['Arch Support']
        
        # Filter to shoes with at least some features
        feature_cols = [col for col in df.columns if col in DEFAULT_FEATURES]
        df = df.dropna(subset=feature_cols, thresh=3).copy()  # Require at least 3 features
        
        self.shoes_df = df
        
        # Initialize and fit clusterer
        self._initialize_clusterer()
        
        logger.info(f"Loaded {len(df)} shoes with lab test data")
        return df
    
    def _initialize_clusterer(self) -> None:
        """Initialize and fit the K-Means clusterer."""
        self.clusterer = ShoeKMeansClusterer(random_state=42)
        self.clusterer.fit()
        
        # Merge cluster labels back to original shoes dataframe using shoe_id
        cluster_df = pd.DataFrame({
            'shoe_id': self.clusterer.shoe_frame['shoe_id'],
            'cluster_label': self.clusterer.labels_
        })
        
        # Merge to keep only shoes that have cluster labels
        self.shoes_df = self.shoes_df.merge(cluster_df, on='shoe_id', how='inner')
        
        # Get the feature matrix for distance calculations
        imputer = SimpleImputer(strategy="median")
        scaler = StandardScaler()
        
        # Extract features for clustering
        feature_matrix = self.shoes_df[DEFAULT_FEATURES].copy()
        imputed = imputer.fit_transform(feature_matrix)
        self.shoe_features = scaler.fit_transform(imputed)
        
        logger.info(f"Initialized K-Means with {self.clusterer.model.n_clusters} clusters")
    
    def _calculate_euclidean_distance(self, shoe_a_idx: int, shoe_b_idx: int) -> float:
        """Calculate Euclidean distance between two shoes in feature space."""
        if self.shoe_features is None:
            return 0.0
        return np.linalg.norm(self.shoe_features[shoe_a_idx] - self.shoe_features[shoe_b_idx])
    
    def calculate_delta_features(self, shoe_a: pd.Series, shoe_b: pd.Series) -> Dict[str, float]:
        """Calculate directional differences between shoe features (shoe_b - shoe_a)."""
        deltas = {}
        
        # Numeric features
        for feature in DEFAULT_FEATURES:
            val_a = shoe_a[feature] if pd.notna(shoe_a[feature]) else None
            val_b = shoe_b[feature] if pd.notna(shoe_b[feature]) else None
            
            if val_a is not None and val_b is not None:
                # Use directional difference (shoe_b - shoe_a) instead of absolute
                deltas[f'diff_{feature.lower().replace(" ", "_")}'] = val_b - val_a
            else:
                deltas[f'diff_{feature.lower().replace(" ", "_")}'] = np.nan
        
        # Categorical features
        deltas['is_same_terrain'] = 1 if shoe_a.get('Terrain') == shoe_b.get('Terrain') else 0
        deltas['is_same_support'] = 1 if shoe_a.get('Arch Support') == shoe_b.get('Arch Support') else 0
        
        # K-Means clustering features
        deltas['is_same_kmeans_cluster'] = 1 if shoe_a.get('cluster_label') == shoe_b.get('cluster_label') else 0
        
        # Calculate Euclidean distance between shoes in feature space
        shoe_a_idx = self.shoes_df[self.shoes_df['shoe_id'] == shoe_a['shoe_id']].index[0]
        shoe_b_idx = self.shoes_df[self.shoes_df['shoe_id'] == shoe_b['shoe_id']].index[0]
        deltas['euclidean_distance'] = self._calculate_euclidean_distance(shoe_a_idx, shoe_b_idx)
        
        return deltas
    
    def train_from_synthetic_dataset(
        self,
        dataset_path: Path = Path("data/synthetic_similarity_dataset.csv"),
        test_size: float = 0.2,
        random_state: int = 42
    ) -> Dict[str, float]:
        """Train the model on synthetic similarity dataset."""
        
        logger.info(f"Training {self.model_type} model on synthetic dataset")
        
        # Load synthetic dataset
        if not dataset_path.exists():
            raise FileNotFoundError(f"Synthetic dataset not found at {dataset_path}")
        
        df = pd.read_csv(dataset_path)
        
        # Extract feature columns (diff features instead of delta features)
        diff_columns = [col for col in df.columns if col.startswith('diff_')]
        # Also include categorical features if present
        categorical_columns = [col for col in df.columns if col.startswith('is_same_')]
        feature_columns = diff_columns + categorical_columns
        
        X = df[feature_columns].copy()
        y = df['similarity_score'].copy()
        
        # Remove any rows with all NaN features
        valid_mask = X.notna().any(axis=1)
        X = X[valid_mask]
        y = y[valid_mask]
        
        logger.info(f"Training on {len(X)} valid samples")
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state
        )
        
        # Impute missing values
        X_train_imputed = self.imputer.fit_transform(X_train)
        X_test_imputed = self.imputer.transform(X_test)
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train_imputed)
        X_test_scaled = self.scaler.transform(X_test_imputed)
        
        # Train model
        if self.model_type == "xgboost":
            self.model = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=random_state,
                n_jobs=-1
            )
        else:  # randomforest
            self.model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=random_state,
                n_jobs=-1
            )
        
        self.model.fit(X_train_scaled, y_train)
        self.feature_columns = feature_columns
        
        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        mae = mean_absolute_error(y_test, y_pred)
        mse = mean_squared_error(y_test, y_pred)
        rmse = np.sqrt(mse)
        
        metrics = {
            'mae': mae,
            'mse': mse,
            'rmse': rmse,
            'train_samples': len(X_train),
            'test_samples': len(X_test)
        }
        
        logger.info(f"Training complete. MAE: {mae:.2f}, RMSE: {rmse:.2f}")
        
        return metrics
    
    def predict_similarity(self, shoe_a_id: str, shoe_b_id: str) -> float:
        """Predict similarity score between two shoes."""
        if self.model is None:
            raise ValueError("Model not trained. Call train_from_synthetic_dataset() first.")
        
        if self.shoes_df is None:
            raise ValueError("Shoes not loaded. Call load_shoes_from_db() first.")
        
        # Find shoes
        shoe_a = self.shoes_df[self.shoes_df['shoe_id'] == shoe_a_id]
        shoe_b = self.shoes_df[self.shoes_df['shoe_id'] == shoe_b_id]
        
        if shoe_a.empty or shoe_b.empty:
            raise ValueError("One or both shoe IDs not found")
        
        shoe_a = shoe_a.iloc[0]
        shoe_b = shoe_b.iloc[0]
        
        # Calculate delta features
        deltas = self.calculate_delta_features(shoe_a, shoe_b)
        delta_df = pd.DataFrame([deltas])
        
        # Ensure we have the same columns as training
        for col in self.feature_columns:
            if col not in delta_df.columns:
                delta_df[col] = np.nan
        
        delta_df = delta_df[self.feature_columns]
        
        # Impute and scale
        delta_imputed = self.imputer.transform(delta_df)
        delta_scaled = self.scaler.transform(delta_imputed)
        
        # Predict
        similarity = self.model.predict(delta_scaled)[0]
        return max(0, min(100, float(similarity)))  # Convert to Python float and clamp to 0-100 range
    
    def find_similar_shoes(
        self,
        query_shoe_id: str,
        top_k: int = 5,
        exclude_same_brand: bool = False
    ) -> List[Dict[str, Any]]:
        """Find most similar shoes to a query shoe."""
        if self.model is None:
            raise ValueError("Model not trained. Call train_from_synthetic_dataset() first.")
        
        if self.shoes_df is None:
            raise ValueError("Shoes not loaded. Call load_shoes_from_db() first.")
        
        # Find query shoe
        query_shoe = self.shoes_df[self.shoes_df['shoe_id'] == query_shoe_id]
        if query_shoe.empty:
            raise ValueError(f"Query shoe ID {query_shoe_id} not found")
        
        query_shoe = query_shoe.iloc[0]
        query_brand = query_shoe['brand']
        
        # Calculate similarity with all other shoes
        similarities = []
        
        for _, other_shoe in self.shoes_df.iterrows():
            if other_shoe['shoe_id'] == query_shoe_id:
                continue
            
            if exclude_same_brand and other_shoe['brand'] == query_brand:
                continue
            
            # Calculate delta features
            deltas = self.calculate_delta_features(query_shoe, other_shoe)
            delta_df = pd.DataFrame([deltas])
            
            # Ensure we have the same columns as training
            for col in self.feature_columns:
                if col not in delta_df.columns:
                    delta_df[col] = np.nan
            
            delta_df = delta_df[self.feature_columns]
            
            # Impute and scale
            delta_imputed = self.imputer.transform(delta_df)
            delta_scaled = self.scaler.transform(delta_imputed)
            
            # Predict similarity
            similarity = self.model.predict(delta_scaled)[0]
            similarity = max(0, min(100, float(similarity)))  # Convert to Python float and clamp
            
            similarities.append({
                'shoe_id': other_shoe['shoe_id'],
                'shoe_name': f"{other_shoe['brand']} {other_shoe['shoe_name']}",
                'brand': other_shoe['brand'],
                'similarity_score': similarity
            })
        
        # Sort by similarity and return top k
        similarities.sort(key=lambda x: x['similarity_score'], reverse=True)
        return similarities[:top_k]
    
    def save_model(self, model_path: Path = Path("data/supervised_shoe_matcher.pkl")) -> None:
        """Save the trained model and preprocessing objects."""
        if self.model is None:
            raise ValueError("No model to save")
        
        model_data = {
            'model': self.model,
            'imputer': self.imputer,
            'scaler': self.scaler,
            'feature_columns': self.feature_columns,
            'model_type': self.model_type,
            'clusterer': self.clusterer,  # Save clusterer as well
            'shoe_features': self.shoe_features  # Save feature matrix
        }
        
        with open(model_path, 'wb') as f:
            pickle.dump(model_data, f)
        
        logger.info(f"Model saved to {model_path}")
    
    def load_model(self, model_path: Path = Path("data/supervised_shoe_matcher.pkl")) -> None:
        """Load a trained model and preprocessing objects."""
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found at {model_path}")
        
        with open(model_path, 'rb') as f:
            model_data = pickle.load(f)
        
        self.model = model_data['model']
        self.imputer = model_data['imputer']
        self.scaler = model_data['scaler']
        self.feature_columns = model_data['feature_columns']
        self.model_type = model_data['model_type']
        
        # Load clusterer and features if available (for newer models)
        if 'clusterer' in model_data:
            self.clusterer = model_data['clusterer']
            self.shoe_features = model_data.get('shoe_features')
        
        logger.info(f"Model loaded from {model_path}")


def train_and_save_model(
    synthetic_dataset_path: Path = Path("data/synthetic_similarity_dataset.csv"),
    model_output_path: Path = Path("data/supervised_shoe_matcher.pkl"),
    model_type: str = "xgboost"
) -> Dict[str, float]:
    """Convenience function to train and save the model."""
    
    matcher = SupervisedShoeMatcher(model_type=model_type)
    
    # Load shoes
    matcher.load_shoes_from_db()
    
    # Train model
    metrics = matcher.train_from_synthetic_dataset(synthetic_dataset_path)
    
    # Save model
    matcher.save_model(model_output_path)
    
    return metrics


if __name__ == "__main__":
    # Train and save the model
    metrics = train_and_save_model()
    print("Training metrics:", metrics)

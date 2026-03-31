"""Service layer for supervised shoe matching.

This module provides high-level functions that integrate with the webapp
and replace the existing K-means based matching.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from difflib import get_close_matches

from supervised_shoe_matcher import SupervisedShoeMatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/runrepeat_lab_tests.sqlite")
MODEL_PATH = Path("data/supervised_shoe_matcher.pkl")


class SupervisedMatchingService:
    """Service layer for supervised shoe matching."""
    
    def __init__(self, model_path: Path = MODEL_PATH):
        """Initialize the service with a trained model."""
        self.matcher = SupervisedShoeMatcher()
        self.model_path = model_path
        self._shoes_cache = None
        
        # Load the trained model
        if model_path.exists():
            self.matcher.load_model(model_path)
            self.matcher.load_shoes_from_db()
            logger.info("Supervised matching service initialized with trained model")
        else:
            logger.warning(f"No trained model found at {model_path}")
    
    def get_available_shoes(self, terrain: Optional[str] = None) -> List[Dict[str, str]]:
        """Get list of available shoes for the dropdown."""
        if self.matcher.shoes_df is None:
            self.matcher.load_shoes_from_db()
        
        df = self.matcher.shoes_df.copy()
        
        # Filter by terrain if specified
        if terrain and terrain.lower() in ['road', 'trail']:
            # Extract terrain from lab test results
            def get_terrain(lab_results):
                if not lab_results:
                    return None
                try:
                    results = json.loads(lab_results) if isinstance(lab_results, str) else lab_results
                    # Check various terrain fields
                    for field in ['Terrain', 'Road/Trail']:
                        if field in results:
                            terrain_val = str(results[field]).lower()
                            if terrain.lower() in terrain_val:
                                return terrain.title()
                    return None
                except:
                    return None
            
            df['terrain'] = df['lab_test_results'].apply(get_terrain)
            df = df[df['terrain'] == terrain.title()].copy()
        
        # Return formatted list
        shoes = []
        for _, row in df.iterrows():
            shoes.append({
                'shoe_id': row['shoe_id'],
                'name': f"{row['brand']} {row['shoe_name']}"
            })
        
        return sorted(shoes, key=lambda x: x['name'])
    
    def find_shoe_by_name(self, shoe_name: str) -> Optional[str]:
        """Find shoe ID by human-readable name using fuzzy matching."""
        if self.matcher.shoes_df is None:
            self.matcher.load_shoes_from_db()
        
        # Create list of shoe names
        shoe_names = []
        for _, row in self.matcher.shoes_df.iterrows():
            shoe_names.append(f"{row['brand']} {row['shoe_name']}")
        
        # Find close matches
        matches = get_close_matches(shoe_name, shoe_names, n=1, cutoff=0.6)
        
        if matches:
            matched_name = matches[0]
            # Find the corresponding shoe_id
            for _, row in self.matcher.shoes_df.iterrows():
                if f"{row['brand']} {row['shoe_name']}" == matched_name:
                    return row['shoe_id']
        
        return None
    
    def get_recommendations(
        self,
        shoe_name: str,
        top_k: int = 5,
        terrain: Optional[str] = None,
        exclude_same_brand: bool = False
    ) -> Dict[str, any]:
        """Get shoe recommendations using the supervised model."""
        
        # Find the shoe ID
        shoe_id = self.find_shoe_by_name(shoe_name)
        if not shoe_id:
            return {
                'error': f'Shoe "{shoe_name}" not found',
                'suggestions': self._get_name_suggestions(shoe_name)
            }
        
        # Get matched shoe details
        matched_shoe = self.matcher.shoes_df[self.matcher.shoes_df['shoe_id'] == shoe_id].iloc[0]
        
        # Get clustering information from the matcher's clusterer
        cluster_info = {}
        if self.matcher.clusterer is not None:
            # Get cluster label for the matched shoe
            cluster_label = int(matched_shoe.get('cluster_label', 0))
            
            # Convert cluster center to Python native types
            cluster_center = {}
            if hasattr(self.matcher.clusterer.model, 'cluster_centers_'):
                center_values = self.matcher.clusterer.model.cluster_centers_[cluster_label]
                feature_names = self.matcher.clusterer.feature_names
                cluster_center = {
                    name: float(value) for name, value in zip(feature_names, center_values)
                }
            
            cluster_info = {
                'cluster_label': cluster_label,
                'cluster_size': int(sum(self.matcher.clusterer.labels_ == cluster_label)),
                'cluster_center': cluster_center,
                'feature_names': list(self.matcher.clusterer.feature_names),
                'n_clusters': int(self.matcher.clusterer.model.n_clusters)
            }
        else:
            # Fallback values if clusterer is not available
            cluster_info = {
                'cluster_label': 0,
                'cluster_size': 0,
                'cluster_center': {},
                'feature_names': [],
                'n_clusters': 0
            }
        
        # Find similar shoes
        similar_shoes = self.matcher.find_similar_shoes(
            shoe_id,
            top_k=top_k,
            exclude_same_brand=exclude_same_brand
        )
        
        # Filter by terrain if specified
        if terrain and terrain.lower() in ['road', 'trail']:
            similar_shoes = self._filter_by_terrain(similar_shoes, terrain.title())
        
        return {
            'query': shoe_name,
            'matched_shoe': {
                'shoe_id': shoe_id,
                'name': f"{matched_shoe['brand']} {matched_shoe['shoe_name']}",
                'brand': matched_shoe['brand']
            },
            'recommendations': similar_shoes,
            'algorithm': 'supervised_xgboost',
            **cluster_info  # Add all clustering information
        }
    
    def _get_name_suggestions(self, shoe_name: str, max_suggestions: int = 5) -> List[str]:
        """Get name suggestions for a failed lookup."""
        if self.matcher.shoes_df is None:
            self.matcher.load_shoes_from_db()
        
        shoe_names = []
        for _, row in self.matcher.shoes_df.iterrows():
            shoe_names.append(f"{row['brand']} {row['shoe_name']}")
        
        return get_close_matches(shoe_name, shoe_names, n=max_suggestions, cutoff=0.3)
    
    def _filter_by_terrain(self, shoes: List[Dict], terrain: str) -> List[Dict]:
        """Filter shoes by terrain type."""
        def get_shoe_terrain(shoe_id: str) -> Optional[str]:
            shoe = self.matcher.shoes_df[self.matcher.shoes_df['shoe_id'] == shoe_id]
            if shoe.empty:
                return None
            
            lab_results = shoe.iloc[0]['lab_test_results']
            try:
                results = json.loads(lab_results) if isinstance(lab_results, str) else lab_results
                for field in ['Terrain', 'Road/Trail']:
                    if field in results:
                        terrain_val = str(results[field]).lower()
                        if terrain.lower() in terrain_val:
                            return terrain.title()
                return None
            except:
                return None
        
        filtered = []
        for shoe in shoes:
            shoe_terrain = get_shoe_terrain(shoe['shoe_id'])
            if shoe_terrain == terrain:
                filtered.append(shoe)
        
        return filtered


# Global service instance
_service_instance = None


def get_matching_service() -> SupervisedMatchingService:
    """Get or create the global matching service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SupervisedMatchingService()
    return _service_instance


def recommend_similar_shoes(
    shoe_name: str,
    top_k: int = 5,
    terrain: Optional[str] = None,
    exclude_same_brand: bool = False
) -> Dict[str, any]:
    """Convenience function for backward compatibility."""
    service = get_matching_service()
    return service.get_recommendations(
        shoe_name=shoe_name,
        top_k=top_k,
        terrain=terrain,
        exclude_same_brand=exclude_same_brand
    )


if __name__ == "__main__":
    # Test the service
    service = get_matching_service()
    
    # Get available shoes
    shoes = service.get_available_shoes()
    print(f"Found {len(shoes)} shoes")
    
    if shoes:
        # Test recommendations
        test_shoe = shoes[0]['name']
        print(f"\nGetting recommendations for: {test_shoe}")
        result = service.get_recommendations(test_shoe)
        print(f"Matched: {result.get('matched_shoe', {}).get('name')}")
        print("Recommendations:")
        for rec in result.get('recommendations', []):
            print(f"  - {rec['name']} (similarity: {rec['similarity_score']:.1f})")

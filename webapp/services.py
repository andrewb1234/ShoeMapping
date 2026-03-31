from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Try to import the supervised matching service first
try:
    from supervised_matching_service import get_matching_service
    SUPERVISED_MATCHING_AVAILABLE = True
except ImportError:
    SUPERVISED_MATCHING_AVAILABLE = False
    from shoe_clustering import DEFAULT_DB_PATH, recommend_similar_shoes

logger = logging.getLogger(__name__)

ALLOWED_TERRAINS = {"Road", "Trail"}


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return " ".join(text.lower().replace("review", " ").split())


def normalize_terrain_selection(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    selection = str(value).strip()
    if not selection or selection.lower() == "both":
        return None

    for candidate in sorted(ALLOWED_TERRAINS):
        if normalize_text(selection) == normalize_text(candidate):
            return candidate

    raise ValueError(f"Invalid terrain selection: {value!r}")


def terrain_response_value(terrain: Optional[str]) -> str:
    return terrain or "Both"


def safe_json_loads(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        logger.warning("Failed to parse lab_test_results JSON payload")
        return {}

    return parsed if isinstance(parsed, dict) else {}


def display_name(brand: str, shoe_name: str) -> str:
    clean_name = str(shoe_name).strip()
    if clean_name.lower().endswith(" review"):
        clean_name = clean_name[:-7].strip()
    return f"{brand.strip()} · {clean_name}"


class ShoeCatalogService:
    """Read shoe metadata from the RunRepeat SQLite database."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def _fetch_rows(self) -> List[Tuple[Any, ...]]:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT shoe_id, brand, shoe_name, source_url, audience_verdict,
                       lab_test_results, crawled_at
                FROM shoes
                ORDER BY brand, shoe_name
                """
            )
            return cursor.fetchall()

    def list_shoes(self, terrain: Optional[str] = None) -> List[Dict[str, Any]]:
        terrain_filter = normalize_terrain_selection(terrain)
        items: List[Dict[str, Any]] = []

        for row in self._fetch_rows():
            shoe_id, brand, shoe_name, source_url, audience_verdict, lab_json, crawled_at = row
            lab_results = safe_json_loads(lab_json)
            shoe_terrain = lab_results.get("Terrain")

            if terrain_filter and normalize_text(shoe_terrain) != normalize_text(terrain_filter):
                continue

            items.append(
                {
                    "shoe_id": str(shoe_id),
                    "brand": str(brand),
                    "shoe_name": str(shoe_name),
                    "display_name": display_name(str(brand), str(shoe_name)),
                    "terrain": shoe_terrain,
                    "source_url": str(source_url),
                    "crawled_at": str(crawled_at),
                    "audience_verdict": None if audience_verdict is None else int(audience_verdict),
                }
            )

        items.sort(key=lambda item: (item["brand"].lower(), item["shoe_name"].lower()))
        return items

    def get_shoe_by_id(self, shoe_id: str) -> Dict[str, Any]:
        if not shoe_id:
            return {}

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT shoe_id, brand, shoe_name, source_url, audience_verdict,
                       lab_test_results, crawled_at
                FROM shoes
                WHERE shoe_id = ?
                """,
                (shoe_id,),
            )
            row = cursor.fetchone()

        if not row:
            return {}

        _, brand, shoe_name, source_url, audience_verdict, lab_json, crawled_at = row
        lab_results = safe_json_loads(lab_json)
        return {
            "shoe_id": str(row[0]),
            "brand": str(brand),
            "shoe_name": str(shoe_name),
            "display_name": display_name(str(brand), str(shoe_name)),
            "terrain": lab_results.get("Terrain"),
            "source_url": str(source_url),
            "crawled_at": str(crawled_at),
            "audience_verdict": None if audience_verdict is None else int(audience_verdict),
        }


class ShoeRecommendationService:
    """Wrap the clustering engine behind a reusable service API.
    
    Now supports both the original K-means clustering and the new supervised
    learning approach using XGBoost similarity predictions.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH, catalog_service: Optional[ShoeCatalogService] = None) -> None:
        self.db_path = Path(db_path)
        self.catalog_service = catalog_service or ShoeCatalogService(db_path)
        self._clusterers: Dict[Tuple[str, int], Any] = {}
        
        # Initialize supervised matching service if available
        if SUPERVISED_MATCHING_AVAILABLE:
            try:
                self.supervised_service = get_matching_service()
                logger.info("Using supervised matching algorithm")
            except Exception as e:
                logger.warning(f"Failed to initialize supervised matching: {e}. Falling back to K-means.")
                self.supervised_service = None
        else:
            self.supervised_service = None

    def _get_clusterer(self, terrain_filter: Optional[str], n_clusters: int, n_neighbors: int) -> Any:
        cache_key = (terrain_response_value(terrain_filter), max(1, n_clusters))
        clusterer = self._clusterers.get(cache_key)
        if clusterer is None:
            from shoe_clustering import ShoeKMeansClusterer

            clusterer = ShoeKMeansClusterer(
                db_path=self.db_path,
                n_clusters=max(1, n_clusters),
                n_neighbors=max(1, n_neighbors),
                terrain_filter=terrain_filter,
            )
            self._clusterers[cache_key] = clusterer
        else:
            clusterer.n_neighbors = max(1, n_neighbors)
        return clusterer

    def recommend(
        self,
        shoe_name: str,
        terrain: Optional[str] = None,
        n_neighbors: int = 5,
        n_clusters: int = 8,
        shoe_id: Optional[str] = None,
        use_supervised: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Get shoe recommendations using either supervised or K-means approach.
        
        Args:
            shoe_name: Name of the shoe to find alternatives for
            terrain: Filter by terrain (Road/Trail/Both)
            n_neighbors: Number of recommendations to return
            n_clusters: Number of clusters for K-means (ignored if supervised)
            shoe_id: Optional shoe ID (used internally)
            use_supervised: Force using supervised (True) or K-means (False). 
                          If None, uses supervised if available.
        """
        
        # Decide which algorithm to use
        should_use_supervised = use_supervised if use_supervised is not None else (self.supervised_service is not None)
        
        if should_use_supervised and self.supervised_service:
            # Use supervised matching
            try:
                result = self.supervised_service.get_recommendations(
                    shoe_name=shoe_name,
                    top_k=n_neighbors,
                    terrain=terrain,
                    exclude_same_brand=False
                )
                
                # Format result to match expected structure
                if 'error' in result:
                    return {
                        'error': result['error'],
                        'suggestions': result.get('suggestions', []),
                        'terrain': terrain_response_value(terrain),
                    }
                
                # Convert recommendations to expected format
                recommendations = []
                for rec in result.get('recommendations', []):
                    # Get full shoe details from catalog
                    shoe_details = self.catalog_service.get_shoe_by_id(rec['shoe_id'])
                    if shoe_details:
                        recommendations.append({
                            'shoe_id': rec['shoe_id'],
                            'shoe_name': shoe_details['shoe_name'],
                            'brand': shoe_details['brand'],
                            'display_name': shoe_details['display_name'],
                            'similarity_score': rec['similarity_score'],
                            'terrain': shoe_details['terrain'],
                            'audience_verdict': shoe_details['audience_verdict'],
                        })
                
                return {
                    'matched_shoe': result.get('matched_shoe', {}),
                    'recommendations': recommendations,
                    'terrain': terrain_response_value(terrain),
                    'algorithm': 'supervised_xgboost',
                }
                
            except Exception as e:
                logger.error(f"Supervised matching failed: {e}. Falling back to K-means.")
                should_use_supervised = False
        
        # Use K-means clustering (original approach)
        terrain_filter = normalize_terrain_selection(terrain)
        clusterer = self._get_clusterer(terrain_filter, n_clusters=n_clusters, n_neighbors=n_neighbors)
        result = clusterer.recommend(shoe_name, n_neighbors=n_neighbors, shoe_id=shoe_id)
        return {
            **result,
            "terrain": terrain_response_value(terrain_filter),
            "recommendations": result["nearest_shoes"],
            "algorithm": "kmeans",
        }

    def recommend_by_shoe_id(
        self,
        shoe_id: str,
        terrain: Optional[str] = None,
        n_neighbors: int = 5,
        n_clusters: int = 8,
    ) -> Dict[str, Any]:
        shoe = self.catalog_service.get_shoe_by_id(shoe_id)
        if not shoe:
            raise LookupError(f"Unknown shoe_id: {shoe_id}")
        return self.recommend(
            shoe["shoe_name"],
            terrain=terrain,
            n_neighbors=n_neighbors,
            n_clusters=n_clusters,
            shoe_id=shoe_id,
        )

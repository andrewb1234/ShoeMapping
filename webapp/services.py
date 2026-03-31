from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_RECOMMENDATIONS_PATH = Path("data/precomputed_recommendations.json")

logger = logging.getLogger(__name__)

ALLOWED_TERRAINS = {"Road", "Trail"}
DEFAULT_CATALOG_PATH = Path("data/shoes.catalog.json")


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
    """Read shoe metadata from the compact JSON catalog."""

    def __init__(self, catalog_path: Path | str = DEFAULT_CATALOG_PATH) -> None:
        self.catalog_path = Path(catalog_path)
        self._catalog: Optional[List[Dict[str, Any]]] = None

    def _load_catalog(self) -> List[Dict[str, Any]]:
        if self._catalog is None:
            if not self.catalog_path.exists():
                raise FileNotFoundError(f"Catalog not found: {self.catalog_path}")
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                self._catalog = json.load(f)
        return self._catalog or []

    def list_shoes(self, terrain: Optional[str] = None) -> List[Dict[str, Any]]:
        terrain_filter = normalize_terrain_selection(terrain)
        items: List[Dict[str, Any]] = []

        for shoe in self._load_catalog():
            shoe_terrain = shoe.get("terrain")

            if terrain_filter and normalize_text(shoe_terrain) != normalize_text(terrain_filter):
                continue

            items.append({
                "shoe_id": shoe["shoe_id"],
                "brand": shoe["brand"],
                "shoe_name": shoe["shoe_name"],
                "display_name": shoe["display_name"],
                "terrain": shoe_terrain,
                "source_url": shoe["source_url"],
                "crawled_at": shoe["crawled_at"],
                "audience_verdict": shoe["audience_verdict"],
            })

        items.sort(key=lambda item: (item["brand"].lower(), item["shoe_name"].lower()))
        return items

    def get_shoe_by_id(self, shoe_id: str) -> Dict[str, Any]:
        if not shoe_id:
            return {}

        for shoe in self._load_catalog():
            if shoe["shoe_id"] == shoe_id:
                return {
                    "shoe_id": shoe["shoe_id"],
                    "brand": shoe["brand"],
                    "shoe_name": shoe["shoe_name"],
                    "display_name": shoe["display_name"],
                    "terrain": shoe.get("terrain"),
                    "source_url": shoe["source_url"],
                    "crawled_at": shoe["crawled_at"],
                    "audience_verdict": shoe["audience_verdict"],
                }

        return {}


class ShoeRecommendationService:
    """Serve pre-computed shoe recommendations from a static JSON file.

    At deploy-time this avoids importing heavy ML libraries (scikit-learn,
    xgboost) and keeps the Vercel Lambda well under the 500 MB size limit.
    """

    def __init__(
        self,
        catalog_service: Optional[ShoeCatalogService] = None,
        recommendations_path: Path | str = DEFAULT_RECOMMENDATIONS_PATH,
    ) -> None:
        self.catalog_service = catalog_service or ShoeCatalogService()
        self.recommendations_path = Path(recommendations_path)
        self._recs: Optional[Dict[str, List[Dict[str, Any]]]] = None

    def _load_recommendations(self) -> Dict[str, List[Dict[str, Any]]]:
        if self._recs is None:
            if not self.recommendations_path.exists():
                raise FileNotFoundError(
                    f"Precomputed recommendations not found: {self.recommendations_path}. "
                    "Run `python precompute_recommendations.py` first."
                )
            with open(self.recommendations_path, "r", encoding="utf-8") as f:
                self._recs = json.load(f)
            logger.info(
                "Loaded precomputed recommendations for %d shoes",
                len(self._recs),
            )
        return self._recs

    def recommend(
        self,
        shoe_name: str,
        terrain: Optional[str] = None,
        n_neighbors: int = 5,
        n_clusters: int = 8,
        shoe_id: Optional[str] = None,
        use_supervised: Optional[bool] = None,
        rejected: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return pre-computed recommendations for a shoe.

        Parameters kept for API compatibility with the previous ML-backed
        implementation.  ``n_clusters`` and ``use_supervised`` are accepted
        but ignored.
        """
        rejected = rejected or []
        terrain_filter = normalize_terrain_selection(terrain)

        # Resolve shoe_id when only a name is provided
        if not shoe_id:
            shoe_id = self._resolve_shoe_id(shoe_name)
            if not shoe_id:
                return {
                    "error": f"Shoe not found: {shoe_name}",
                    "suggestions": [],
                    "terrain": terrain_response_value(terrain_filter),
                }

        recs_map = self._load_recommendations()
        stored = recs_map.get(shoe_id, [])

        # Filter by terrain and rejected list
        filtered: List[Dict[str, Any]] = []
        for rec in stored:
            if rec["shoe_id"] in rejected:
                continue
            if terrain_filter and normalize_text(rec.get("terrain")) != normalize_text(terrain_filter):
                continue
            filtered.append(rec)
            if len(filtered) >= n_neighbors:
                break

        query_shoe = self.catalog_service.get_shoe_by_id(shoe_id)

        return {
            "query": query_shoe.get("display_name", shoe_name) if query_shoe else shoe_name,
            "query_shoe": query_shoe.get("display_name", shoe_name) if query_shoe else shoe_name,
            "query_shoe_id": shoe_id,
            "matched_shoe": query_shoe or {},
            "terrain": terrain_response_value(terrain_filter),
            "recommendations": filtered,
            "algorithm": "supervised_precomputed",
        }

    def recommend_by_shoe_id(
        self,
        shoe_id: str,
        terrain: Optional[str] = None,
        n_neighbors: int = 5,
        n_clusters: int = 8,
        rejected: Optional[List[str]] = None,
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
            rejected=rejected,
        )

    # ------------------------------------------------------------------
    def _resolve_shoe_id(self, shoe_name: str) -> Optional[str]:
        """Best-effort name → shoe_id lookup via the catalog."""
        target = normalize_text(shoe_name)
        for shoe in self.catalog_service._load_catalog():
            candidate = normalize_text(
                f"{shoe.get('brand', '')} {shoe.get('shoe_name', '')}"
            )
            if target == candidate or target in candidate or candidate in target:
                return shoe["shoe_id"]
        return None

from __future__ import annotations

from functools import lru_cache

from webapp.services import ShoeCatalogService, ShoeRecommendationService


@lru_cache(maxsize=1)
def get_catalog_service() -> ShoeCatalogService:
    return ShoeCatalogService()


@lru_cache(maxsize=1)
def get_recommendation_service() -> ShoeRecommendationService:
    return ShoeRecommendationService(catalog_service=get_catalog_service())

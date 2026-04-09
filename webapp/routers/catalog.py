from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from webapp.config import get_settings
from webapp.deps import get_catalog_service, get_recommendation_service
from webapp.models import (
    RecommendationRequest,
    RecommendationResponse,
    ShoeDetailResponse,
    ShoeListResponse,
)
from webapp.services import (
    ShoeCatalogService,
    ShoeRecommendationService,
    normalize_terrain_selection,
    terrain_response_value,
)


public_router = APIRouter()
catalog_api_router = APIRouter()


def _personalization_context() -> dict:
    settings = get_settings()
    return {
        "public_web_base_url": settings.public_web_base_url,
        "personalization_base_url": settings.personalization_base_url,
        "personalization_enabled": settings.personalization_is_configured,
    }


@public_router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "home.html", _personalization_context())


@public_router.get("/explore", response_class=HTMLResponse)
def explore(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "explore.html", _personalization_context())


@catalog_api_router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@catalog_api_router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@catalog_api_router.get("/readyz")
def readyz(
    request: Request,
    catalog_service: ShoeCatalogService = Depends(get_catalog_service),
) -> dict:
    shoes = catalog_service.list_shoes()
    settings = request.app.state.settings
    runtime_mode = getattr(request.app.state, "runtime_mode", settings.app_mode)
    response = {"status": "ready", "catalog_size": len(shoes), "mode": runtime_mode}
    if runtime_mode == "personalization":
        from personalization.db import check_database_ready

        response["database"] = check_database_ready()
        response["strava_configured"] = settings.strava_is_configured
    return response


@catalog_api_router.get("/api/catalog/shoes", response_model=ShoeListResponse)
@catalog_api_router.get("/api/shoes", response_model=ShoeListResponse, include_in_schema=False)
def list_shoes(
    terrain: Optional[str] = Query(default=None, description="Road, Trail, or Both"),
    catalog_service: ShoeCatalogService = Depends(get_catalog_service),
) -> ShoeListResponse:
    try:
        normalized_terrain = normalize_terrain_selection(terrain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    shoes = catalog_service.list_shoes(normalized_terrain)
    return ShoeListResponse(
        terrain=terrain_response_value(normalized_terrain),
        count=len(shoes),
        shoes=shoes,
    )


@catalog_api_router.get("/api/catalog/shoes/{shoe_id}", response_model=ShoeDetailResponse)
@catalog_api_router.get("/api/catalog/shoe/{shoe_id}/statistics", response_model=ShoeDetailResponse)
@catalog_api_router.get("/api/shoe/{shoe_id}/statistics", response_model=ShoeDetailResponse, include_in_schema=False)
def get_shoe_detail(
    shoe_id: str,
    catalog_service: ShoeCatalogService = Depends(get_catalog_service),
) -> ShoeDetailResponse:
    shoe = catalog_service.get_shoe_by_id(shoe_id)
    if not shoe:
        raise HTTPException(status_code=404, detail="Shoe not found")
    return ShoeDetailResponse(**shoe)


@catalog_api_router.post("/api/catalog/recommendations", response_model=RecommendationResponse)
@catalog_api_router.post("/api/recommendations", response_model=RecommendationResponse, include_in_schema=False)
def recommend_shoes(
    payload: RecommendationRequest,
    recommendation_service: ShoeRecommendationService = Depends(get_recommendation_service),
) -> RecommendationResponse:
    try:
        if payload.shoe_id:
            result = recommendation_service.recommend_by_shoe_id(
                payload.shoe_id,
                terrain=payload.terrain,
                n_neighbors=payload.n_neighbors,
                n_clusters=payload.n_clusters,
                rejected=payload.rejected,
            )
        else:
            result = recommendation_service.recommend(
                payload.shoe_name or "",
                terrain=payload.terrain,
                n_neighbors=payload.n_neighbors,
                n_clusters=payload.n_clusters,
                rejected=payload.rejected,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RecommendationResponse(**result)

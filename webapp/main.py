from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from webapp.models import RecommendationRequest, RecommendationResponse, ShoeListResponse
from webapp.services import (
    ShoeCatalogService,
    ShoeRecommendationService,
    normalize_terrain_selection,
    terrain_response_value,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Shoe Matcher", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@lru_cache(maxsize=1)
def get_catalog_service() -> ShoeCatalogService:
    return ShoeCatalogService()


@lru_cache(maxsize=1)
def get_recommendation_service() -> ShoeRecommendationService:
    return ShoeRecommendationService(catalog_service=get_catalog_service())


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/shoes", response_model=ShoeListResponse)
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


@app.post("/api/recommendations", response_model=RecommendationResponse)
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


@app.get("/api/shoe/{shoe_id}/statistics")
def get_shoe_statistics(
    shoe_id: str,
    catalog_service: ShoeCatalogService = Depends(get_catalog_service),
) -> dict:
    """Get detailed statistics for a specific shoe."""
    shoe = catalog_service.get_shoe_by_id(shoe_id)
    if not shoe:
        raise HTTPException(status_code=404, detail="Shoe not found")
    
    # Fetch the lab test results from the catalog
    from pathlib import Path
    import json
    
    catalog_path = Path(__file__).resolve().parent.parent / "data" / "shoes.catalog.json"
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    
    # Find the shoe in the catalog
    lab_results = None
    for shoe_data in catalog:
        if shoe_data["shoe_id"] == shoe_id:
            lab_results = shoe_data["lab_test_results"]
            break
    
    if not lab_results:
        raise HTTPException(status_code=404, detail="Shoe data not found")
    
    return {
        "shoe_id": shoe["shoe_id"],
        "shoe_name": shoe["shoe_name"],
        "brand": shoe["brand"],
        "audience_verdict": shoe["audience_verdict"],
        "lab_test_results": lab_results,
    }

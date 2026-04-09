from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from personalization.db import check_database_ready, get_db_session
from personalization.jobs import create_job
from personalization.models import JobType, User
from personalization.profile import compute_runner_profile, latest_profile, update_profile_overrides
from personalization.schemas import (
    PersonalizedRecommendationResponse,
    ProfileUpdateRequest,
    RunnerProfileResponse,
    SessionBootstrapResponse,
)
from personalization.scoring import SUPPORTED_CONTEXTS, ensure_recommendations
from personalization.security import decode_session_cookie
from personalization.session import bootstrap_user_session, get_current_user
from webapp.config import get_settings
from webapp.deps import get_catalog_service, get_recommendation_service
from webapp.services import ShoeCatalogService, ShoeRecommendationService


page_router = APIRouter()
api_router = APIRouter()


@page_router.get("/", response_class=HTMLResponse)
def personalize_home(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "personalize.html",
        {
            "public_web_base_url": settings.public_web_base_url,
            "strava_enabled": settings.enable_strava_ui and settings.strava_is_configured,
        },
    )


@api_router.post("/api/personalization/session/bootstrap", response_model=SessionBootstrapResponse)
def bootstrap_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
) -> SessionBootstrapResponse:
    settings = get_settings()
    existing_cookie = request.cookies.get(settings.session_cookie_name)
    payload = decode_session_cookie(existing_cookie) if existing_cookie else None
    if payload and payload.get("sid"):
        user = db.query(User).filter(User.guest_session_id == payload["sid"]).one_or_none()
        if user:
            return SessionBootstrapResponse(
                user_id=user.id,
                session_status="existing",
                strava_available=settings.enable_strava_ui and settings.strava_is_configured,
            )
    user = bootstrap_user_session(response, db)
    return SessionBootstrapResponse(
        user_id=user.id,
        session_status="created",
        strava_available=settings.enable_strava_ui and settings.strava_is_configured,
    )


@api_router.get("/api/profile", response_model=RunnerProfileResponse)
def get_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    catalog_service: ShoeCatalogService = Depends(get_catalog_service),
) -> RunnerProfileResponse:
    profile = latest_profile(db, user.id) or compute_runner_profile(db, user, catalog_service)
    return RunnerProfileResponse(
        user_id=user.id,
        profile_version=profile.profile_version,
        computed_at=profile.computed_at,
        summary=profile.profile_json,
        coverage=profile.coverage_json,
        manual_overrides=profile.profile_json.get("manual_overrides", {}),
    )


@api_router.patch("/api/profile", response_model=RunnerProfileResponse)
def patch_profile(
    payload: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    catalog_service: ShoeCatalogService = Depends(get_catalog_service),
) -> RunnerProfileResponse:
    profile = update_profile_overrides(
        db,
        user,
        payload.model_dump(exclude_unset=True),
        catalog_service,
    )
    create_job(db, user.id, JobType.recompute_recommendations.value)
    return RunnerProfileResponse(
        user_id=user.id,
        profile_version=profile.profile_version,
        computed_at=profile.computed_at,
        summary=profile.profile_json,
        coverage=profile.coverage_json,
        manual_overrides=profile.profile_json.get("manual_overrides", {}),
    )


@api_router.get("/api/recommendations/personalized", response_model=PersonalizedRecommendationResponse)
def personalized_recommendations(
    context: str = Query(default="easy"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    catalog_service: ShoeCatalogService = Depends(get_catalog_service),
    recommendation_service: ShoeRecommendationService = Depends(get_recommendation_service),
) -> PersonalizedRecommendationResponse:
    if context not in SUPPORTED_CONTEXTS:
        raise HTTPException(status_code=400, detail=f"Unsupported context: {context}")
    if latest_profile(db, user.id) is None:
        compute_runner_profile(db, user, catalog_service)
    payload = ensure_recommendations(db, user, context, catalog_service, recommendation_service)
    return PersonalizedRecommendationResponse(**payload)


@api_router.get("/api/personalization/readyz")
def personalization_readyz() -> dict:
    settings = get_settings()
    data = check_database_ready()
    return {
        **data,
        "strava_configured": settings.strava_is_configured,
        "inline_jobs": settings.inline_job_execution,
    }

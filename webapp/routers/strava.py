from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from personalization.db import get_db_session
from personalization.jobs import create_job
from personalization.models import JobType, User
from personalization.session import get_current_user
from personalization.strava import (
    authorization_url,
    connect_user_from_code,
    decode_oauth_state,
    queue_payload_for_webhook,
)
from webapp.config import get_settings


router = APIRouter()


@router.get("/auth/strava/start")
def start_strava_auth(
    include_private: bool = Query(default=False),
    user: User = Depends(get_current_user),
) -> RedirectResponse:
    settings = get_settings()
    if not (settings.enable_strava_ui and settings.strava_is_configured):
        raise HTTPException(status_code=503, detail="Strava integration is not enabled.")
    return RedirectResponse(authorization_url(user.id, include_private=include_private))


@router.get("/auth/strava/callback")
def strava_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    settings = get_settings()
    if error:
        return RedirectResponse(f"/?strava_error={error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing Strava OAuth response details.")
    state_payload = decode_oauth_state(state)
    if not state_payload or "uid" not in state_payload:
        raise HTTPException(status_code=400, detail="Invalid Strava state payload.")
    user = db.scalar(select(User).where(User.id == state_payload["uid"]))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found for Strava callback.")
    connect_user_from_code(db, user, code)
    create_job(db, user.id, JobType.strava_backfill.value)
    return RedirectResponse(f"{settings.app_base_url}/?strava=connected")


@router.get("/webhooks/strava")
def verify_strava_webhook(request: Request) -> JSONResponse:
    settings = get_settings()
    verify_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if verify_token != settings.strava_verify_token:
        raise HTTPException(status_code=403, detail="Invalid Strava verify token.")
    return JSONResponse({"hub.challenge": challenge})


@router.post("/webhooks/strava")
async def receive_strava_webhook(
    request: Request,
    db: Session = Depends(get_db_session),
) -> dict:
    payload = await request.json()
    job_payload = queue_payload_for_webhook(payload)
    athlete_id = job_payload.get("athlete_id")
    user = db.scalar(select(User).where(User.strava_athlete_id == athlete_id))
    if user is not None:
        create_job(db, user.id, JobType.strava_refresh.value, payload_json=job_payload, run_inline=False)
    return {"status": "ok"}

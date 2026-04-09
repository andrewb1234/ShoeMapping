from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

import httpx
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from personalization.imports import store_normalized_activities
from personalization.models import ActivitySource, JobType, SourceType, StravaConnection, StravaConnectionStatus, User
from personalization.security import decrypt_value, encrypt_value
from personalization.utils import normalize_text, parse_datetime, utcnow
from webapp.config import get_settings


AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"


def _state_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().session_secret, salt="shoe-mapping-strava-state")


def encode_oauth_state(user_id: str, include_private: bool) -> str:
    return _state_serializer().dumps({"uid": user_id, "private": include_private})


def decode_oauth_state(value: str) -> dict | None:
    try:
        return _state_serializer().loads(value)
    except BadSignature:
        return None


def _scopes(include_private: bool) -> str:
    scopes = ["read", "activity:read"]
    if include_private:
        scopes.append("activity:read_all")
    return ",".join(scopes)


def authorization_url(user_id: str, include_private: bool = False) -> str:
    settings = get_settings()
    state = encode_oauth_state(user_id, include_private)
    params = {
        "client_id": settings.strava_client_id,
        "redirect_uri": settings.strava_redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": _scopes(include_private),
        "state": state,
    }
    query = "&".join(f"{key}={httpx.QueryParams({key: value})[key]}" for key, value in params.items())
    return f"{AUTHORIZE_URL}?{query}"


def _token_client() -> httpx.Client:
    return httpx.Client(timeout=20.0)


def exchange_code(code: str) -> dict:
    settings = get_settings()
    with _token_client() as client:
        response = client.post(
            TOKEN_URL,
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


def _upsert_connection(session: Session, user: User, token_payload: dict) -> StravaConnection:
    athlete = token_payload.get("athlete") or {}
    athlete_id = str(athlete.get("id"))
    scopes = [scope.strip() for scope in str(token_payload.get("scope", "")).split(",") if scope.strip()]
    connection = session.scalar(select(StravaConnection).where(StravaConnection.user_id == user.id))
    expires_at = parse_datetime(token_payload.get("expires_at")) or utcnow() + timedelta(hours=6)
    if connection is None:
        connection = StravaConnection(
            user_id=user.id,
            athlete_id=athlete_id,
            accepted_scopes=scopes,
            access_token_encrypted=encrypt_value(token_payload["access_token"]),
            refresh_token_encrypted=encrypt_value(token_payload["refresh_token"]),
            expires_at=expires_at,
            status=StravaConnectionStatus.active.value,
        )
        session.add(connection)
    else:
        connection.athlete_id = athlete_id
        connection.accepted_scopes = scopes
        connection.access_token_encrypted = encrypt_value(token_payload["access_token"])
        connection.refresh_token_encrypted = encrypt_value(token_payload["refresh_token"])
        connection.expires_at = expires_at
        connection.status = StravaConnectionStatus.active.value
    user.strava_athlete_id = athlete_id
    session.add(user)
    session.commit()
    session.refresh(connection)
    return connection


def connect_user_from_code(session: Session, user: User, code: str) -> StravaConnection:
    token_payload = exchange_code(code)
    return _upsert_connection(session, user, token_payload)


def refresh_access_token(session: Session, connection: StravaConnection) -> StravaConnection:
    settings = get_settings()
    refresh_token = decrypt_value(connection.refresh_token_encrypted)
    with _token_client() as client:
        response = client.post(
            TOKEN_URL,
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        response.raise_for_status()
        payload = response.json()
    connection.access_token_encrypted = encrypt_value(payload["access_token"])
    connection.refresh_token_encrypted = encrypt_value(payload["refresh_token"])
    connection.expires_at = parse_datetime(payload.get("expires_at")) or (utcnow() + timedelta(hours=6))
    connection.accepted_scopes = [scope.strip() for scope in str(payload.get("scope", "")).split(",") if scope.strip()]
    session.add(connection)
    session.commit()
    session.refresh(connection)
    return connection


def _valid_access_token(session: Session, connection: StravaConnection) -> str:
    if connection.expires_at <= utcnow() + timedelta(minutes=5):
        connection = refresh_access_token(session, connection)
    return decrypt_value(connection.access_token_encrypted)


def _normalized_strava_activity(activity: dict) -> dict | None:
    sport_type = activity.get("sport_type") or activity.get("type") or "Run"
    if "run" not in normalize_text(sport_type):
        return None
    started_at = parse_datetime(activity.get("start_date")) or parse_datetime(activity.get("start_date_local"))
    if started_at is None:
        return None
    return {
        "external_id": str(activity.get("id")),
        "started_at": started_at,
        "timezone_name": activity.get("timezone"),
        "sport_type": sport_type,
        "distance_m": float(activity.get("distance") or 0.0),
        "moving_time_s": float(activity.get("moving_time") or 0.0),
        "elapsed_time_s": float(activity.get("elapsed_time") or activity.get("moving_time") or 0.0),
        "elevation_gain_m": float(activity.get("total_elevation_gain") or 0.0),
        "avg_hr": activity.get("average_heartrate"),
        "avg_cadence": activity.get("average_cadence"),
        "gear_ref": activity.get("gear_id"),
        "terrain_guess": "trail" if "trail" in normalize_text(sport_type) else "road",
        "surface_guess": "trail" if "trail" in normalize_text(sport_type) else "road",
        "payload_json": activity,
    }


def backfill_user_activities(
    session: Session,
    user: User,
    connection: StravaConnection,
    max_activities: int = 300,
) -> dict:
    access_token = _valid_access_token(session, connection)
    after = int((utcnow() - timedelta(days=180)).timestamp())
    collected: List[dict[str, Any]] = []
    page = 1
    with _token_client() as client:
        while len(collected) < max_activities:
            response = client.get(
                ACTIVITIES_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"per_page": 100, "page": page, "after": after},
            )
            response.raise_for_status()
            items = response.json()
            if not items:
                break
            for activity in items:
                normalized = _normalized_strava_activity(activity)
                if normalized:
                    collected.append(normalized)
                if len(collected) >= max_activities:
                    break
            page += 1
    result = store_normalized_activities(
        session,
        user,
        SourceType.strava,
        collected,
        scope_json={"athlete_id": connection.athlete_id, "mode": "strava_backfill"},
    )
    connection.status = StravaConnectionStatus.active.value
    session.add(connection)
    session.commit()
    return {"imported": result["imported_activities"], "duplicates": result["duplicates"]}


def get_connection_for_user(session: Session, user_id: str) -> StravaConnection | None:
    return session.scalar(select(StravaConnection).where(StravaConnection.user_id == user_id))


def queue_payload_for_webhook(event: dict) -> dict:
    return {
        "athlete_id": str(event.get("owner_id")),
        "object_id": str(event.get("object_id")),
        "aspect_type": event.get("aspect_type"),
        "object_type": event.get("object_type"),
        "updates": event.get("updates") or {},
    }

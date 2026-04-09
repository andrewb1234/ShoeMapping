from __future__ import annotations

from datetime import timedelta
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from personalization.models import ActivityFeature, ActivityRaw, OwnedShoe, User
from personalization.utils import normalize_text, utcnow
from webapp.services import ShoeCatalogService


DEFAULT_RETIREMENT_TARGETS = {
    "road_daily": 600.0,
    "race_uptempo": 400.0,
    "trail": 500.0,
}


def default_retirement_target(terrain: str | None, ride_role: str | None) -> float:
    if terrain == "Trail":
        return DEFAULT_RETIREMENT_TARGETS["trail"]
    if ride_role in {"race", "uptempo"}:
        return DEFAULT_RETIREMENT_TARGETS["race_uptempo"]
    return DEFAULT_RETIREMENT_TARGETS["road_daily"]


def shoe_display_name(owned_shoe: OwnedShoe, catalog_service: ShoeCatalogService) -> str:
    if owned_shoe.catalog_shoe_id:
        shoe = catalog_service.get_shoe_by_id(owned_shoe.catalog_shoe_id)
        if shoe:
            return shoe["display_name"]
    brand = owned_shoe.custom_brand or "Custom"
    name = owned_shoe.custom_name or "Unmapped shoe"
    return f"{brand} · {name}"


def _potential_identifiers(
    owned_shoe: OwnedShoe,
    catalog_service: ShoeCatalogService,
) -> set[str]:
    identifiers: set[str] = set()
    if owned_shoe.strava_gear_id:
        identifiers.add(normalize_text(owned_shoe.strava_gear_id))
    if owned_shoe.catalog_shoe_id:
        identifiers.add(normalize_text(owned_shoe.catalog_shoe_id))
        shoe = catalog_service.get_shoe_by_id(owned_shoe.catalog_shoe_id)
        if shoe:
            identifiers.add(normalize_text(shoe["display_name"]))
            identifiers.add(normalize_text(f"{shoe['brand']} {shoe['shoe_name']}"))
            identifiers.add(normalize_text(shoe["shoe_name"]))
    if owned_shoe.custom_name:
        identifiers.add(normalize_text(owned_shoe.custom_name))
    if owned_shoe.custom_brand and owned_shoe.custom_name:
        identifiers.add(normalize_text(f"{owned_shoe.custom_brand} {owned_shoe.custom_name}"))
    return {value for value in identifiers if value}


def _activity_usage(session: Session, user_id: str) -> tuple[Dict[str, float], Dict[str, int]]:
    now = utcnow()
    recent_cutoff = now - timedelta(days=30)
    distance_by_identifier: Dict[str, float] = {}
    recent_by_identifier: Dict[str, int] = {}
    rows = session.execute(
        select(ActivityFeature.gear_ref, ActivityFeature.distance_m, ActivityRaw.started_at)
        .join(ActivityRaw, ActivityRaw.id == ActivityFeature.activity_id)
        .where(ActivityRaw.user_id == user_id)
    ).all()
    for gear_ref, distance_m, started_at in rows:
        identifier = normalize_text(gear_ref)
        if not identifier:
            continue
        distance_by_identifier[identifier] = distance_by_identifier.get(identifier, 0.0) + ((distance_m or 0.0) / 1000.0)
        if started_at and started_at >= recent_cutoff:
            recent_by_identifier[identifier] = recent_by_identifier.get(identifier, 0) + 1
    return distance_by_identifier, recent_by_identifier


def build_rotation_summary(
    session: Session,
    user: User,
    catalog_service: ShoeCatalogService,
) -> List[dict]:
    owned_shoes = session.scalars(
        select(OwnedShoe).where(OwnedShoe.user_id == user.id).order_by(OwnedShoe.created_at.asc())
    ).all()
    distance_by_identifier, recent_by_identifier = _activity_usage(session, user.id)
    summaries: List[dict] = []
    for owned in owned_shoes:
        identifiers = _potential_identifiers(owned, catalog_service)
        matched_distance = sum(distance_by_identifier.get(identifier, 0.0) for identifier in identifiers)
        recent_uses = sum(recent_by_identifier.get(identifier, 0) for identifier in identifiers)
        display_name = shoe_display_name(owned, catalog_service)
        catalog_entry = catalog_service.get_shoe_by_id(owned.catalog_shoe_id or "")
        terrain = catalog_entry.get("terrain")
        facets = catalog_entry.get("facets") or {}
        ride_role = facets.get("ride_role")
        retirement_target = owned.retirement_target_km or default_retirement_target(terrain, ride_role)
        current_mileage = round((owned.start_mileage_km or 0.0) + matched_distance, 1)
        remaining = None if retirement_target is None else round(retirement_target - current_mileage, 1)
        if remaining is None:
            status = "tracking"
        elif remaining <= 0:
            status = "replace_now"
        elif remaining <= 50:
            status = "watch"
        else:
            status = "healthy"
        summaries.append(
            {
                "id": owned.id,
                "catalog_shoe_id": owned.catalog_shoe_id,
                "display_name": display_name,
                "terrain": terrain,
                "ride_role": ride_role,
                "current_mileage_km": current_mileage,
                "retirement_target_km": retirement_target,
                "remaining_km": remaining,
                "status": status,
                "notes": owned.notes,
                "is_active": owned.is_active,
                "facets": facets,
                "recent_uses_30d": recent_uses,
            }
        )
    return summaries

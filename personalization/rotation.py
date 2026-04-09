from __future__ import annotations

from datetime import timedelta, timezone
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


def build_catalog_identifier_map(catalog_service: ShoeCatalogService) -> Dict[str, str | None]:
    identifier_map: Dict[str, str | None] = {}
    for shoe in catalog_service.list_shoes():
        identifiers = {
            normalize_text(shoe["display_name"]),
            normalize_text(f"{shoe['brand']} {shoe['shoe_name']}"),
            normalize_text(shoe["shoe_name"]),
        }
        for identifier in identifiers:
            if not identifier:
                continue
            existing = identifier_map.get(identifier)
            if existing is None and identifier in identifier_map:
                continue
            if existing and existing != shoe["shoe_id"]:
                identifier_map[identifier] = None
                continue
            identifier_map[identifier] = shoe["shoe_id"]
    return identifier_map


def resolve_catalog_shoe_id(raw_name: str | None, catalog_service: ShoeCatalogService) -> str | None:
    if not raw_name:
        return None
    identifier_map = build_catalog_identifier_map(catalog_service)
    return identifier_map.get(normalize_text(raw_name))


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


def _activity_usage(session: Session, user_id: str) -> Dict[str, dict]:
    now = utcnow()
    recent_cutoff = now - timedelta(days=30)
    usage_by_identifier: Dict[str, dict] = {}
    rows = session.execute(
        select(ActivityFeature.gear_ref, ActivityFeature.distance_m, ActivityRaw.started_at)
        .join(ActivityRaw, ActivityRaw.id == ActivityFeature.activity_id)
        .where(ActivityRaw.user_id == user_id)
    ).all()
    for gear_ref, distance_m, started_at in rows:
        identifier = normalize_text(gear_ref)
        if not identifier:
            continue
        entry = usage_by_identifier.setdefault(
            identifier,
            {
                "raw_import_name": str(gear_ref).strip(),
                "distance_km": 0.0,
                "activity_count": 0,
                "recent_uses_30d": 0,
            },
        )
        entry["distance_km"] += (distance_m or 0.0) / 1000.0
        entry["activity_count"] += 1
        if started_at and started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if started_at and started_at >= recent_cutoff:
            entry["recent_uses_30d"] += 1
    return usage_by_identifier


def _status_for_mileage(current_mileage: float, retirement_target: float | None) -> tuple[float | None, str]:
    remaining = None if retirement_target is None else round(retirement_target - current_mileage, 1)
    if remaining is None:
        return None, "tracking"
    if remaining <= 0:
        return remaining, "replace_now"
    if remaining <= 50:
        return remaining, "watch"
    return remaining, "healthy"


def build_rotation_summary(
    session: Session,
    user: User,
    catalog_service: ShoeCatalogService,
) -> List[dict]:
    owned_shoes = session.scalars(
        select(OwnedShoe).where(OwnedShoe.user_id == user.id).order_by(OwnedShoe.created_at.asc())
    ).all()
    usage_by_identifier = _activity_usage(session, user.id)
    summaries: List[dict] = []
    consumed_identifiers: set[str] = set()

    for owned in owned_shoes:
        identifiers = _potential_identifiers(owned, catalog_service)
        matched_entries = [usage_by_identifier[identifier] for identifier in identifiers if identifier in usage_by_identifier]
        matched_distance = sum(entry["distance_km"] for entry in matched_entries)
        activity_count = sum(entry["activity_count"] for entry in matched_entries)
        recent_uses = sum(entry["recent_uses_30d"] for entry in matched_entries)
        for identifier in identifiers:
            if identifier in usage_by_identifier:
                consumed_identifiers.add(identifier)
        display_name = shoe_display_name(owned, catalog_service)
        catalog_entry = catalog_service.get_shoe_by_id(owned.catalog_shoe_id or "")
        terrain = catalog_entry.get("terrain")
        facets = catalog_entry.get("facets") or {}
        ride_role = facets.get("ride_role")
        retirement_target = owned.retirement_target_km or default_retirement_target(terrain, ride_role)
        current_mileage = round((owned.start_mileage_km or 0.0) + matched_distance, 1)
        remaining, status = _status_for_mileage(current_mileage, retirement_target)
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
                "source_kind": "manual_with_import" if activity_count else "manual",
                "mapping_status": "catalog_matched" if owned.catalog_shoe_id else "unmapped",
                "raw_import_name": matched_entries[0]["raw_import_name"] if matched_entries else None,
                "activity_count": activity_count,
                "recent_uses_30d": recent_uses,
            }
        )

    catalog_identifier_map = build_catalog_identifier_map(catalog_service)
    for identifier, entry in sorted(usage_by_identifier.items(), key=lambda item: item[1]["raw_import_name"].lower()):
        if identifier in consumed_identifiers:
            continue
        catalog_shoe_id = catalog_identifier_map.get(identifier)
        catalog_entry = catalog_service.get_shoe_by_id(catalog_shoe_id or "")
        terrain = catalog_entry.get("terrain")
        facets = catalog_entry.get("facets") or {}
        ride_role = facets.get("ride_role")
        retirement_target = default_retirement_target(terrain, ride_role) if catalog_shoe_id else None
        current_mileage = round(entry["distance_km"], 1)
        remaining, status = _status_for_mileage(current_mileage, retirement_target)
        summaries.append(
            {
                "id": f"imported:{identifier}",
                "catalog_shoe_id": catalog_shoe_id,
                "display_name": entry["raw_import_name"],
                "terrain": terrain,
                "ride_role": ride_role,
                "current_mileage_km": current_mileage,
                "retirement_target_km": retirement_target,
                "remaining_km": remaining,
                "status": status,
                "notes": None,
                "is_active": True,
                "facets": facets,
                "source_kind": "imported",
                "mapping_status": "catalog_matched" if catalog_shoe_id else "unmapped",
                "raw_import_name": entry["raw_import_name"],
                "activity_count": entry["activity_count"],
                "recent_uses_30d": entry["recent_uses_30d"],
            }
        )
    return summaries


def summarize_rotation_inventory(shoes: List[dict]) -> dict:
    manual_count = sum(1 for shoe in shoes if shoe.get("source_kind") in {"manual", "manual_with_import"})
    imported_count = sum(1 for shoe in shoes if shoe.get("source_kind") == "imported")
    mapped_count = sum(1 for shoe in shoes if shoe.get("mapping_status") == "catalog_matched")
    unmapped_count = sum(1 for shoe in shoes if shoe.get("mapping_status") == "unmapped")
    return {
        "manual_count": manual_count,
        "imported_count": imported_count,
        "mapped_count": mapped_count,
        "unmapped_count": unmapped_count,
    }

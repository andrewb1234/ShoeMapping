from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from personalization.models import (
    ActivityFeature,
    ActivityLabel,
    ActivityRaw,
    LabelSource,
    RunContext,
    RunnerProfile,
    User,
)
from personalization.rotation import build_rotation_summary
from personalization.utils import normalize_text, percentile, to_min_per_km, utcnow
from webapp.services import ShoeCatalogService


LOOKBACK_DAYS = 180


def latest_profile(session: Session, user_id: str) -> RunnerProfile | None:
    return session.scalar(
        select(RunnerProfile)
        .where(RunnerProfile.user_id == user_id)
        .order_by(RunnerProfile.profile_version.desc(), RunnerProfile.computed_at.desc())
    )


def _empty_profile(user_id: str, overrides: dict | None = None) -> tuple[dict, dict]:
    manual_overrides = overrides or {}
    summary = {
        "lookback_days": LOOKBACK_DAYS,
        "total_runs": 0,
        "weekly_mileage_km": 0.0,
        "median_run_distance_km": 0.0,
        "long_run_share": 0.0,
        "elevation_gain_per_km_m": 0.0,
        "terrain_mix": {"road": 0.0, "trail": 0.0, "unknown": 1.0},
        "terrain_preference": manual_overrides.get("preferred_terrain") or "unknown",
        "pace_bands_min_per_km": {},
        "cadence_band": None,
        "heart_rate_band": None,
        "shoe_rotation_breadth": 0,
        "current_mileage_by_shoe": {},
        "context_counts": {},
        "manual_overrides": manual_overrides,
    }
    coverage = {
        "total_runs": 0,
        "hr_coverage": 0.0,
        "cadence_coverage": 0.0,
        "gear_coverage": 0.0,
        "known_terrain_share": 0.0,
        "missing_signals": profile_missing_signals(
            {
                "hr_coverage": 0.0,
                "cadence_coverage": 0.0,
                "gear_coverage": 0.0,
            },
            0,
        ),
    }
    return summary, coverage


def _manual_overrides(latest: RunnerProfile | None) -> dict:
    if not latest:
        return {}
    profile_json = latest.profile_json or {}
    return dict(profile_json.get("manual_overrides") or {})


def relabel_user_activities(session: Session, user_id: str) -> None:
    rows = session.execute(
        select(
            ActivityRaw.id,
            ActivityFeature.distance_m,
            ActivityFeature.moving_time_s,
            ActivityFeature.avg_pace_mps,
            ActivityFeature.avg_hr,
            ActivityFeature.avg_cadence,
            ActivityFeature.elevation_gain_m,
            ActivityFeature.terrain_guess,
        )
        .join(ActivityFeature, ActivityFeature.activity_id == ActivityRaw.id)
        .where(ActivityRaw.user_id == user_id)
    ).all()
    if not rows:
        return

    distances = [row.distance_m or 0.0 for row in rows if row.distance_m]
    paces = [row.avg_pace_mps or 0.0 for row in rows if row.avg_pace_mps]
    heart_rates = [row.avg_hr or 0.0 for row in rows if row.avg_hr]
    cadences = [row.avg_cadence or 0.0 for row in rows if row.avg_cadence]

    long_distance = percentile(distances, 0.8) or 0.0
    fast_pace = percentile(paces, 0.75) or 0.0
    easy_pace = percentile(paces, 0.35) or 0.0
    high_hr = percentile(heart_rates, 0.75) or 0.0
    high_cadence = percentile(cadences, 0.75) or 0.0

    existing = {
        label.activity_id: label
        for label in session.scalars(
            select(ActivityLabel).join(ActivityRaw, ActivityRaw.id == ActivityLabel.activity_id).where(
                ActivityRaw.user_id == user_id
            )
        ).all()
    }

    for row in rows:
        elev_per_km = 0.0
        if row.distance_m and row.distance_m > 0 and row.elevation_gain_m:
            elev_per_km = row.elevation_gain_m / (row.distance_m / 1000.0)

        context = RunContext.easy.value
        confidence = 0.62
        if normalize_text(row.terrain_guess) == "trail" or elev_per_km >= 45:
            context = RunContext.trail.value
            confidence = 0.88
        elif (row.moving_time_s or 0.0) >= 75 * 60 or (row.distance_m or 0.0) >= long_distance:
            context = RunContext.long.value
            confidence = 0.84
        elif (row.avg_pace_mps or 0.0) >= fast_pace * 0.98 or (
            high_hr and (row.avg_hr or 0.0) >= high_hr and (row.moving_time_s or 0.0) >= 20 * 60
        ) or (
            high_cadence and (row.avg_cadence or 0.0) >= high_cadence and (row.moving_time_s or 0.0) >= 20 * 60
        ):
            context = RunContext.workout.value
            confidence = 0.76
        elif (row.moving_time_s or 0.0) <= 45 * 60 and easy_pace and (row.avg_pace_mps or 0.0) <= easy_pace * 0.95:
            context = RunContext.recovery.value
            confidence = 0.68

        label = existing.get(row.id)
        if label:
            label.run_context = context
            label.context_confidence = confidence
            label.label_source = LabelSource.auto.value
        else:
            label = ActivityLabel(
                activity_id=row.id,
                run_context=context,
                context_confidence=confidence,
                label_source=LabelSource.auto.value,
            )
            session.add(label)
    session.commit()


def profile_missing_signals(coverage: dict, total_runs: int) -> List[str]:
    missing: List[str] = []
    if total_runs < 3:
        missing.append("You only have a small activity sample so far.")
    if coverage.get("hr_coverage", 0.0) < 0.3:
        missing.append("Heart rate coverage is limited, so effort-based matching is weaker.")
    if coverage.get("cadence_coverage", 0.0) < 0.3:
        missing.append("Cadence coverage is limited, so workout classification uses pace first.")
    if coverage.get("gear_coverage", 0.0) < 0.3:
        missing.append("Most activities are not linked to a shoe yet, so rotation advice is approximate.")
    return missing


def compute_runner_profile(
    session: Session,
    user: User,
    catalog_service: ShoeCatalogService,
) -> RunnerProfile:
    relabel_user_activities(session, user.id)
    previous = latest_profile(session, user.id)
    manual_overrides = _manual_overrides(previous)
    lookback_start = utcnow() - timedelta(days=LOOKBACK_DAYS)
    rows = session.execute(
        select(
            ActivityRaw.id,
            ActivityRaw.started_at,
            ActivityFeature.distance_m,
            ActivityFeature.moving_time_s,
            ActivityFeature.elevation_gain_m,
            ActivityFeature.avg_pace_mps,
            ActivityFeature.avg_hr,
            ActivityFeature.avg_cadence,
            ActivityFeature.terrain_guess,
            ActivityFeature.surface_guess,
            ActivityFeature.has_hr,
            ActivityFeature.has_cadence,
            ActivityFeature.gear_ref,
            ActivityLabel.run_context,
        )
        .join(ActivityFeature, ActivityFeature.activity_id == ActivityRaw.id)
        .join(ActivityLabel, ActivityLabel.activity_id == ActivityRaw.id)
        .where(ActivityRaw.user_id == user.id)
        .where(ActivityRaw.started_at >= lookback_start)
        .order_by(ActivityRaw.started_at.asc())
    ).all()
    if not rows:
        summary, coverage = _empty_profile(user.id, manual_overrides)
    else:
        total_runs = len(rows)
        distances_km = [(row.distance_m or 0.0) / 1000.0 for row in rows]
        total_distance_km = round(sum(distances_km), 1)
        total_elevation = sum(row.elevation_gain_m or 0.0 for row in rows)
        paces = [row.avg_pace_mps for row in rows if row.avg_pace_mps]
        heart_rates = [row.avg_hr for row in rows if row.avg_hr]
        cadences = [row.avg_cadence for row in rows if row.avg_cadence]
        terrain_counts = Counter(normalize_text(row.terrain_guess) or "unknown" for row in rows)
        context_counts = Counter(row.run_context for row in rows if row.run_context)
        known_terrain = terrain_counts.get("road", 0) + terrain_counts.get("trail", 0)
        total_window_weeks = LOOKBACK_DAYS / 7.0
        rotation_summary = build_rotation_summary(session, user, catalog_service)
        current_mileage = {
            shoe["display_name"]: shoe["current_mileage_km"] for shoe in rotation_summary if shoe["is_active"]
        }
        summary = {
            "lookback_days": LOOKBACK_DAYS,
            "total_runs": total_runs,
            "weekly_mileage_km": round(total_distance_km / total_window_weeks, 1),
            "median_run_distance_km": round(percentile(distances_km, 0.5) or 0.0, 1),
            "long_run_share": round((context_counts.get("long", 0) / total_runs), 2),
            "elevation_gain_per_km_m": round(total_elevation / total_distance_km, 1) if total_distance_km else 0.0,
            "terrain_mix": {
                "road": round(terrain_counts.get("road", 0) / total_runs, 2),
                "trail": round(terrain_counts.get("trail", 0) / total_runs, 2),
                "unknown": round(terrain_counts.get("unknown", 0) / total_runs, 2),
            },
            "terrain_preference": manual_overrides.get("preferred_terrain")
            or ("trail" if terrain_counts.get("trail", 0) > terrain_counts.get("road", 0) else "road"),
            "pace_bands_min_per_km": {
                "easy": round(to_min_per_km(percentile(paces, 0.35)) or 0.0, 2),
                "steady": round(to_min_per_km(percentile(paces, 0.5)) or 0.0, 2),
                "fast": round(to_min_per_km(percentile(paces, 0.75)) or 0.0, 2),
            }
            if paces
            else {},
            "cadence_band": (
                {
                    "easy": round(percentile(cadences, 0.35) or 0.0, 1),
                    "steady": round(percentile(cadences, 0.5) or 0.0, 1),
                    "fast": round(percentile(cadences, 0.75) or 0.0, 1),
                }
                if len(cadences) / total_runs >= 0.3
                else None
            ),
            "heart_rate_band": (
                {
                    "easy": round(percentile(heart_rates, 0.35) or 0.0, 1),
                    "steady": round(percentile(heart_rates, 0.5) or 0.0, 1),
                    "fast": round(percentile(heart_rates, 0.75) or 0.0, 1),
                }
                if len(heart_rates) / total_runs >= 0.3
                else None
            ),
            "shoe_rotation_breadth": len({normalize_text(row.gear_ref) for row in rows if row.gear_ref}) or len(rotation_summary),
            "current_mileage_by_shoe": current_mileage,
            "context_counts": dict(context_counts),
            "manual_overrides": manual_overrides,
        }
        if manual_overrides.get("weekly_mileage_override_km") is not None:
            summary["weekly_mileage_km"] = round(float(manual_overrides["weekly_mileage_override_km"]), 1)
        if manual_overrides.get("target_contexts"):
            summary["target_contexts"] = manual_overrides["target_contexts"]
        if manual_overrides.get("notes"):
            summary["notes"] = manual_overrides["notes"]

        coverage = {
            "total_runs": total_runs,
            "hr_coverage": round(sum(1 for row in rows if row.has_hr) / total_runs, 2),
            "cadence_coverage": round(sum(1 for row in rows if row.has_cadence) / total_runs, 2),
            "gear_coverage": round(sum(1 for row in rows if row.gear_ref) / total_runs, 2),
            "known_terrain_share": round(known_terrain / total_runs, 2),
            "missing_signals": profile_missing_signals(
                {
                    "hr_coverage": round(sum(1 for row in rows if row.has_hr) / total_runs, 2),
                    "cadence_coverage": round(sum(1 for row in rows if row.has_cadence) / total_runs, 2),
                    "gear_coverage": round(sum(1 for row in rows if row.gear_ref) / total_runs, 2),
                },
                total_runs,
            ),
        }

    next_version = 1 if previous is None else previous.profile_version + 1
    profile = RunnerProfile(
        user_id=user.id,
        profile_version=next_version,
        profile_json=summary,
        coverage_json=coverage,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def update_profile_overrides(
    session: Session,
    user: User,
    overrides: Dict[str, Any],
    catalog_service: ShoeCatalogService,
) -> RunnerProfile:
    previous = latest_profile(session, user.id)
    manual_overrides = _manual_overrides(previous)
    for key, value in overrides.items():
        if value is None:
            manual_overrides.pop(key, None)
        else:
            manual_overrides[key] = value
    if previous:
        summary = dict(previous.profile_json or {})
        coverage = dict(previous.coverage_json or {})
    else:
        summary, coverage = _empty_profile(user.id, manual_overrides)
    summary["manual_overrides"] = manual_overrides
    if manual_overrides.get("preferred_terrain"):
        summary["terrain_preference"] = manual_overrides["preferred_terrain"]
    if manual_overrides.get("weekly_mileage_override_km") is not None:
        summary["weekly_mileage_km"] = round(float(manual_overrides["weekly_mileage_override_km"]), 1)
    if manual_overrides.get("target_contexts"):
        summary["target_contexts"] = manual_overrides["target_contexts"]
    if manual_overrides.get("notes"):
        summary["notes"] = manual_overrides["notes"]
    next_version = 1 if previous is None else previous.profile_version + 1
    profile = RunnerProfile(
        user_id=user.id,
        profile_version=next_version,
        profile_json=summary,
        coverage_json=coverage,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from personalization.models import ActivityFeature, ActivityLabel, ActivityRaw, User
from personalization.rotation import build_rotation_summary
from personalization.utils import utcnow
from webapp.services import ShoeCatalogService


def compute_shoe_efficiency_heatmap(
    session: Session,
    user: User,
    catalog_service: ShoeCatalogService,
) -> List[dict]:
    """
    Compute efficiency metrics per shoe using HR-adjusted pace.
    Higher efficiency = faster pace at lower HR (lower is better normalized pace).
    """
    rows = session.execute(
        select(
            ActivityFeature.gear_ref,
            ActivityFeature.avg_pace_mps,
            ActivityFeature.avg_hr,
            ActivityFeature.distance_m,
            ActivityFeature.elevation_gain_m,
            ActivityRaw.started_at,
        )
        .join(ActivityRaw, ActivityRaw.id == ActivityFeature.activity_id)
        .where(
            ActivityRaw.user_id == user.id,
            ActivityFeature.avg_pace_mps.is_not(None),
            ActivityFeature.avg_hr.is_not(None),
            ActivityFeature.avg_hr > 0,
        )
        .order_by(ActivityRaw.started_at.asc())
    ).all()

    # Group by gear_ref
    shoe_data: Dict[str, List[dict]] = {}
    for gear_ref, pace_mps, hr, distance_m, elevation_m, started_at in rows:
        if not gear_ref:
            continue
        entry = shoe_data.setdefault(gear_ref, [])
        entry.append({
            "pace_mps": pace_mps,
            "avg_hr": hr,
            "distance_km": (distance_m or 0) / 1000,
            "elevation_gain_m": elevation_m or 0,
            "started_at": started_at,
        })

    # Get shoe display names from rotation
    rotation = build_rotation_summary(session, user, catalog_service)
    display_names = {shoe["raw_import_name"]: shoe["display_name"] for shoe in rotation if shoe.get("raw_import_name")}
    
    results = []
    for gear_ref, runs in shoe_data.items():
        if len(runs) < 2:
            continue
        
        # Calculate efficiency: pace normalized by HR (lower is better)
        # Formula: pace_min_per_km / (avg_hr / 100) to get HR-adjusted effort
        efficiencies = []
        for run in runs:
            pace_min_per_km = 16.6667 / run["pace_mps"]  # Convert m/s to min/km
            hr_factor = run["avg_hr"] / 100
            efficiency = pace_min_per_km / hr_factor if hr_factor > 0 else pace_min_per_km
            efficiencies.append(efficiency)
        
        total_distance = sum(r["distance_km"] for r in runs)
        
        results.append({
            "gear_ref": gear_ref,
            "display_name": display_names.get(gear_ref, gear_ref),
            "avg_efficiency": round(sum(efficiencies) / len(efficiencies), 2),
            "min_efficiency": round(min(efficiencies), 2),
            "max_efficiency": round(max(efficiencies), 2),
            "run_count": len(runs),
            "total_distance_km": round(total_distance, 1),
            "efficiency_tier": _efficiency_tier(sum(efficiencies) / len(efficiencies)),
        })
    
    # Sort by efficiency (lower is better)
    results.sort(key=lambda x: x["avg_efficiency"])
    return results


def _efficiency_tier(avg_efficiency: float) -> str:
    """Classify efficiency into tiers."""
    if avg_efficiency < 4.0:
        return "excellent"
    if avg_efficiency < 4.5:
        return "good"
    if avg_efficiency < 5.0:
        return "fair"
    return "needs_attention"


def compute_monthly_mileage_trend(
    session: Session,
    user: User,
    months: int = 12,
) -> List[dict]:
    """
    Compute monthly aggregated mileage and pace data by shoe.
    """
    cutoff = utcnow() - timedelta(days=30 * months)
    
    rows = session.execute(
        select(
            ActivityFeature.gear_ref,
            ActivityFeature.distance_m,
            ActivityFeature.avg_pace_mps,
            ActivityFeature.avg_hr,
            ActivityRaw.started_at,
        )
        .join(ActivityRaw, ActivityRaw.id == ActivityFeature.activity_id)
        .where(
            ActivityRaw.user_id == user.id,
            ActivityRaw.started_at >= cutoff,
            ActivityFeature.distance_m.is_not(None),
        )
        .order_by(ActivityRaw.started_at.asc())
    ).all()

    # Group by month and shoe
    monthly_data: Dict[str, Dict[str, dict]] = {}
    for gear_ref, distance_m, pace_mps, hr, started_at in rows:
        if not gear_ref or not started_at:
            continue
        
        month_key = started_at.strftime("%Y-%m")
        shoe_key = gear_ref
        
        month_entry = monthly_data.setdefault(month_key, {})
        shoe_entry = month_entry.setdefault(shoe_key, {
            "total_distance_km": 0.0,
            "pace_readings": [],
            "hr_readings": [],
            "run_count": 0,
        })
        
        shoe_entry["total_distance_km"] += (distance_m or 0) / 1000
        if pace_mps:
            shoe_entry["pace_readings"].append(pace_mps)
        if hr:
            shoe_entry["hr_readings"].append(hr)
        shoe_entry["run_count"] += 1
    
    # Convert to sorted list
    results = []
    for month_key in sorted(monthly_data.keys()):
        shoes = monthly_data[month_key]
        shoe_summaries = []
        for gear_ref, data in shoes.items():
            avg_pace = sum(data["pace_readings"]) / len(data["pace_readings"]) if data["pace_readings"] else None
            avg_hr = sum(data["hr_readings"]) / len(data["hr_readings"]) if data["hr_readings"] else None
            
            pace_min_km = 16.6667 / avg_pace if avg_pace else None
            
            shoe_summaries.append({
                "gear_ref": gear_ref,
                "distance_km": round(data["total_distance_km"], 1),
                "avg_pace_min_km": round(pace_min_km, 2) if pace_min_km else None,
                "avg_hr": round(avg_hr, 1) if avg_hr else None,
                "run_count": data["run_count"],
            })
        
        results.append({
            "month": month_key,
            "month_label": datetime.strptime(month_key, "%Y-%m").strftime("%b %Y"),
            "shoes": shoe_summaries,
            "total_distance_km": round(sum(s["distance_km"] for s in shoe_summaries), 1),
        })
    
    return results


def compute_shoe_mileage_tracker(
    session: Session,
    user: User,
    catalog_service: ShoeCatalogService,
) -> List[dict]:
    """
    Compute cumulative mileage per shoe with retirement zone indicators.
    """
    # Get rotation data which already has retirement targets
    rotation = build_rotation_summary(session, user, catalog_service)
    
    # Get usage data with date tracking for odometer effect
    rows = session.execute(
        select(
            ActivityFeature.gear_ref,
            ActivityFeature.distance_m,
            ActivityRaw.started_at,
        )
        .join(ActivityRaw, ActivityRaw.id == ActivityFeature.activity_id)
        .where(ActivityRaw.user_id == user.id)
        .order_by(ActivityRaw.started_at.asc())
    ).all()

    # Build cumulative mileage history
    shoe_history: Dict[str, List[dict]] = {}
    for gear_ref, distance_m, started_at in rows:
        if not gear_ref:
            continue
        history = shoe_history.setdefault(gear_ref, [])
        history.append({
            "distance_km": (distance_m or 0) / 1000,
            "date": started_at.isoformat() if started_at else None,
        })

    results = []
    for shoe in rotation:
        gear_ref = shoe.get("raw_import_name", shoe["display_name"])
        current_mileage = shoe["current_mileage_km"]
        target = shoe.get("retirement_target_km")
        
        # Calculate retirement zone
        retirement_pct = None
        zone = "unknown"
        if target and target > 0:
            retirement_pct = round((current_mileage / target) * 100, 1)
            if retirement_pct >= 100:
                zone = "replace_now"
            elif retirement_pct >= 85:
                zone = "critical"
            elif retirement_pct >= 70:
                zone = "warning"
            else:
                zone = "healthy"
        
        results.append({
            "shoe_id": shoe["id"],
            "catalog_shoe_id": shoe.get("catalog_shoe_id"),
            "display_name": shoe["display_name"],
            "current_mileage_km": current_mileage,
            "retirement_target_km": target,
            "retirement_pct": retirement_pct,
            "zone": zone,
            "source_kind": shoe.get("source_kind"),
            "mapping_status": shoe.get("mapping_status"),
            "recent_uses_30d": shoe.get("recent_uses_30d", 0),
            "activity_count": shoe.get("activity_count", 0),
            "history": shoe_history.get(gear_ref, []),
        })
    
    # Sort by retirement percentage (highest first = most urgent)
    results.sort(key=lambda x: x["retirement_pct"] or 0, reverse=True)
    return results


def compute_pace_distribution(
    session: Session,
    user: User,
) -> List[dict]:
    """
    Compute pace distribution statistics by shoe and run context.
    """
    rows = session.execute(
        select(
            ActivityFeature.gear_ref,
            ActivityFeature.avg_pace_mps,
            ActivityLabel.run_context,
            ActivityRaw.started_at,
        )
        .join(ActivityRaw, ActivityRaw.id == ActivityFeature.activity_id)
        .join(ActivityLabel, ActivityLabel.activity_id == ActivityFeature.activity_id)
        .where(
            ActivityRaw.user_id == user.id,
            ActivityFeature.avg_pace_mps.is_not(None),
        )
    ).all()

    # Group by shoe and run context
    distribution: Dict[str, Dict[str, List[float]]] = {}
    for gear_ref, pace_mps, run_context, started_at in rows:
        if not gear_ref or not pace_mps:
            continue
        
        pace_min_km = 16.6667 / pace_mps
        shoe_data = distribution.setdefault(gear_ref, {})
        context = run_context or "unknown"
        context_readings = shoe_data.setdefault(context, [])
        context_readings.append(pace_min_km)
    
    results = []
    for gear_ref, contexts in distribution.items():
        context_stats = []
        for context, paces in contexts.items():
            if len(paces) < 1:
                continue
            paces_sorted = sorted(paces)
            n = len(paces_sorted)
            
            context_stats.append({
                "run_context": context,
                "count": n,
                "min": round(min(paces_sorted), 2),
                "max": round(max(paces_sorted), 2),
                "median": round(paces_sorted[n // 2], 2),
                "q1": round(paces_sorted[n // 4], 2),
                "q3": round(paces_sorted[3 * n // 4], 2),
                "mean": round(sum(paces_sorted) / n, 2),
            })
        
        results.append({
            "gear_ref": gear_ref,
            "contexts": context_stats,
        })
    
    return results


def compute_rotation_calendar(
    session: Session,
    user: User,
    weeks: int = 12,
) -> List[dict]:
    """
    Compute shoe usage calendar heatmap by week.
    """
    cutoff = utcnow() - timedelta(weeks=weeks)
    
    rows = session.execute(
        select(
            ActivityFeature.gear_ref,
            ActivityFeature.distance_m,
            ActivityRaw.started_at,
        )
        .join(ActivityRaw, ActivityRaw.id == ActivityFeature.activity_id)
        .where(
            ActivityRaw.user_id == user.id,
            ActivityRaw.started_at >= cutoff,
            ActivityFeature.gear_ref.is_not(None),
        )
        .order_by(ActivityRaw.started_at.asc())
    ).all()

    # Group by week and shoe
    calendar: Dict[str, Dict[str, dict]] = {}
    for gear_ref, distance_m, started_at in rows:
        if not started_at:
            continue
        
        # Get ISO week
        iso_cal = started_at.isocalendar()
        week_key = f"{iso_cal.year}-W{iso_cal.week:02d}"
        
        week_entry = calendar.setdefault(week_key, {})
        shoe_entry = week_entry.setdefault(gear_ref, {
            "days_used": set(),
            "total_distance_km": 0.0,
        })
        
        shoe_entry["days_used"].add(started_at.date())
        shoe_entry["total_distance_km"] += (distance_m or 0) / 1000
    
    # Convert to sorted list
    results = []
    for week_key in sorted(calendar.keys()):
        shoes = calendar[week_key]
        shoe_data = []
        for gear_ref, data in shoes.items():
            shoe_data.append({
                "gear_ref": gear_ref,
                "days_used": len(data["days_used"]),
                "total_distance_km": round(data["total_distance_km"], 1),
            })
        
        results.append({
            "week": week_key,
            "shoes": shoe_data,
            "total_shoes_used": len(shoe_data),
        })
    
    return results


def get_all_visualizations(
    session: Session,
    user: User,
    catalog_service: ShoeCatalogService,
) -> dict:
    """
    Compute and return all visualization data in one payload.
    """
    return {
        "efficiency_heatmap": compute_shoe_efficiency_heatmap(session, user, catalog_service),
        "monthly_mileage": compute_monthly_mileage_trend(session, user),
        "shoe_mileage": compute_shoe_mileage_tracker(session, user, catalog_service),
        "pace_distribution": compute_pace_distribution(session, user),
        "rotation_calendar": compute_rotation_calendar(session, user),
        "generated_at": utcnow().isoformat(),
    }

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from personalization.models import PersonalizedRecommendation, User, UserFeedback
from personalization.profile import latest_profile
from personalization.rotation import build_rotation_summary
from personalization.utils import normalize_text, utcnow
from webapp.services import ShoeCatalogService, ShoeRecommendationService


SUPPORTED_CONTEXTS = ["easy", "long", "workout", "trail", "replace"]


CONTEXT_ROLE_SCORES = {
    "easy": {"easy": 35, "daily": 28, "uptempo": 12, "race": 8, "trail": 6, "hike": 4},
    "long": {"easy": 32, "daily": 28, "uptempo": 16, "race": 12, "trail": 18, "hike": 10},
    "workout": {"race": 35, "uptempo": 32, "daily": 18, "easy": 10, "trail": 6, "hike": 2},
    "trail": {"trail": 35, "hike": 30, "easy": 6, "daily": 4, "uptempo": 8, "race": 4},
    "replace": {"daily": 30, "easy": 28, "trail": 28, "uptempo": 20, "race": 18, "hike": 18},
}


def _confidence_bucket(summary: dict, coverage: dict) -> str:
    total_runs = summary.get("total_runs", 0)
    if total_runs >= 12 and coverage.get("known_terrain_share", 0.0) >= 0.6:
        return "high"
    if total_runs >= 4 or summary.get("shoe_rotation_breadth", 0) >= 1:
        return "medium"
    return "low"


def _liked_anchor_ids(session: Session, user_id: str, rotation: list[dict]) -> List[str]:
    anchors = [
        shoe["catalog_shoe_id"]
        for shoe in rotation
        if shoe.get("catalog_shoe_id") and shoe.get("is_active")
    ]
    feedback_rows = session.scalars(
        select(UserFeedback).where(
            UserFeedback.user_id == user_id,
            UserFeedback.signal.in_(["like", "comfortable", "owned"]),
        )
    ).all()
    anchors.extend(feedback.catalog_shoe_id for feedback in feedback_rows if feedback.catalog_shoe_id)
    return list(dict.fromkeys(anchors))


def _preferred_terrain(context: str, summary: dict) -> str:
    if context == "trail":
        return "trail"
    preference = normalize_text(summary.get("terrain_preference"))
    return "trail" if preference == "trail" else "road"


def _rotation_gap_points(candidate: dict, active_rotation: list[dict], context: str, replace_anchor: dict | None) -> float:
    candidate_role = candidate.get("facets", {}).get("ride_role")
    active_roles = [shoe.get("ride_role") for shoe in active_rotation if shoe.get("is_active")]
    if context == "replace" and replace_anchor:
        if candidate_role == replace_anchor.get("ride_role"):
            return 10.0
        return 4.0
    if candidate_role not in active_roles:
        return 10.0
    if active_roles.count(candidate_role) >= 2:
        return 1.0
    return 4.0


def _load_fit_points(candidate: dict, summary: dict, context: str) -> float:
    weekly = summary.get("weekly_mileage_km", 0.0) or 0.0
    cushion = candidate.get("facets", {}).get("cushion_level")
    durability = candidate.get("facets", {}).get("durability_proxy")
    if context == "trail":
        return 15.0 if durability == "high" else 10.0 if durability == "medium" else 5.0
    if weekly >= 60:
        return 15.0 if cushion in {"high", "max"} else 9.0 if cushion == "balanced" else 4.0
    if weekly >= 30:
        return 12.0 if cushion in {"balanced", "high"} else 6.0
    if context == "workout":
        return 10.0 if candidate.get("facets", {}).get("weight_class") == "light" else 6.0
    return 8.0 if cushion in {"balanced", "high"} else 5.0


def _terrain_fit_points(candidate: dict, preferred_terrain: str) -> float:
    terrain = normalize_text(candidate.get("terrain"))
    if preferred_terrain == "trail":
        return 20.0 if terrain == "trail" else 4.0
    return 20.0 if terrain != "trail" else 3.0


def _similarity_points(
    recommendation_service: ShoeRecommendationService,
    anchor_ids: list[str],
    candidate_id: str,
) -> float:
    if not anchor_ids:
        return 0.0
    similarity = max(
        recommendation_service.similarity_between(anchor_id, candidate_id)
        for anchor_id in anchor_ids
    )
    return round((similarity / 100.0) * 10.0, 1)


def _comfort_points(candidate: dict, feedback_rows: list[UserFeedback]) -> float:
    positive_brands = {
        normalize_text(feedback.note)
        for feedback in feedback_rows
        if feedback.signal == "comfortable" and feedback.note
    }
    candidate_brand = normalize_text(candidate.get("brand"))
    if candidate_brand and candidate_brand in positive_brands:
        return 8.0
    if any(
        feedback.signal in {"comfortable", "like"} and feedback.catalog_shoe_id == candidate.get("shoe_id")
        for feedback in feedback_rows
    ):
        return 10.0
    return 0.0


def _redundancy_penalty(
    candidate: dict,
    active_rotation: list[dict],
    recommendation_service: ShoeRecommendationService,
) -> float:
    candidate_id = candidate.get("shoe_id")
    candidate_role = candidate.get("facets", {}).get("ride_role")
    for owned in active_rotation:
        if owned.get("catalog_shoe_id") == candidate_id:
            return -10.0
        owned_id = owned.get("catalog_shoe_id")
        if not owned_id:
            continue
        similarity = recommendation_service.similarity_between(owned_id, candidate_id)
        if similarity >= 85 and owned.get("ride_role") == candidate_role:
            return -8.0
        if similarity >= 70 and owned.get("ride_role") == candidate_role:
            return -4.0
    return 0.0


def _retirement_penalty(candidate: dict, active_rotation: list[dict]) -> float:
    for owned in active_rotation:
        if owned.get("catalog_shoe_id") != candidate.get("shoe_id"):
            continue
        target = owned.get("retirement_target_km")
        current = owned.get("current_mileage_km")
        if not target or not current:
            return 0.0
        ratio = current / target
        if ratio >= 1.0:
            return -20.0
        if ratio >= 0.9:
            return -10.0
    return 0.0


def _replace_anchor(active_rotation: list[dict]) -> dict | None:
    ordered = sorted(
        active_rotation,
        key=lambda shoe: (
            0 if shoe.get("status") == "replace_now" else 1 if shoe.get("status") == "watch" else 2,
            -(shoe.get("current_mileage_km") or 0.0),
        ),
    )
    return ordered[0] if ordered else None


def _explanation(
    candidate: dict,
    context: str,
    component_scores: dict[str, float],
    penalties: list[str],
) -> tuple[list[str], str]:
    positives = []
    role = candidate.get("facets", {}).get("ride_role", "daily")
    terrain = normalize_text(candidate.get("terrain")) or "road"
    if component_scores.get("context_fit", 0) > 20:
        positives.append(f"Its {role} profile is a strong fit for your {context} running.")
    if component_scores.get("terrain_fit", 0) > 12:
        positives.append(f"It is built for {terrain} use, which matches your current terrain bias.")
    if component_scores.get("rotation_gap", 0) >= 8:
        positives.append("It fills a gap in your current shoe rotation instead of duplicating it.")
    if component_scores.get("similarity_to_liked_shoes", 0) >= 6:
        positives.append("It stays close to shoes you already use or rate positively.")
    if component_scores.get("load_fit", 0) >= 10 and len(positives) < 3:
        positives.append("Its cushioning and durability align with your current training load.")
    explanation = positives[:3]
    if penalties:
        explanation.append("Penalty applied: " + penalties[0])
    return explanation[:3], " ".join(explanation[:3])


def compute_recommendations_for_context(
    session: Session,
    user: User,
    context: str,
    catalog_service: ShoeCatalogService,
    recommendation_service: ShoeRecommendationService,
) -> PersonalizedRecommendation:
    profile = latest_profile(session, user.id)
    if not profile:
        raise LookupError("Runner profile not available")
    summary = profile.profile_json or {}
    coverage = profile.coverage_json or {}
    rotation = build_rotation_summary(session, user, catalog_service)
    active_rotation = [shoe for shoe in rotation if shoe.get("is_active")]
    feedback_rows = session.scalars(select(UserFeedback).where(UserFeedback.user_id == user.id)).all()
    preferred_terrain = _preferred_terrain(context, summary)
    anchor_ids = _liked_anchor_ids(session, user.id, active_rotation)
    replace_anchor = _replace_anchor(active_rotation) if context == "replace" else None
    if replace_anchor and replace_anchor.get("catalog_shoe_id"):
        anchor_ids = [replace_anchor["catalog_shoe_id"], *anchor_ids]

    scored_results: List[dict] = []
    for candidate in catalog_service.list_shoes():
        candidate_id = candidate["shoe_id"]
        role_scores = CONTEXT_ROLE_SCORES.get(context, CONTEXT_ROLE_SCORES["easy"])
        context_fit = float(role_scores.get(candidate.get("facets", {}).get("ride_role"), 6))
        terrain_fit = _terrain_fit_points(candidate, preferred_terrain)
        load_fit = _load_fit_points(candidate, summary, context)
        rotation_gap = _rotation_gap_points(candidate, active_rotation, context, replace_anchor)
        similarity_points = _similarity_points(recommendation_service, anchor_ids, candidate_id)
        comfort_points = _comfort_points(candidate, feedback_rows)
        redundancy_penalty = _redundancy_penalty(candidate, active_rotation, recommendation_service)
        retirement_penalty = _retirement_penalty(candidate, active_rotation)
        component_scores = {
            "context_fit": context_fit,
            "terrain_fit": terrain_fit,
            "load_fit": load_fit,
            "rotation_gap": rotation_gap,
            "similarity_to_liked_shoes": similarity_points,
            "comfort_history": comfort_points,
            "redundancy_penalty": redundancy_penalty,
            "retirement_penalty": retirement_penalty,
        }
        final_score = round(sum(component_scores.values()), 1)
        penalties = []
        if redundancy_penalty < 0:
            penalties.append("It overlaps heavily with shoes already in your rotation.")
        if retirement_penalty < 0:
            penalties.append("You already own this shoe and it is near retirement mileage.")
        positive_drivers, explanation = _explanation(candidate, context, component_scores, penalties)
        scored_results.append(
            {
                **candidate,
                "final_score": final_score,
                "explanation": explanation,
                "positive_drivers": positive_drivers,
                "penalties": penalties,
                "missing_signals": coverage.get("missing_signals", []),
                "confidence": _confidence_bucket(summary, coverage),
                "component_scores": component_scores,
            }
        )

    scored_results.sort(key=lambda item: (-item["final_score"], item["brand"], item["shoe_name"]))
    payload = {
        "context": context,
        "profile_version": profile.profile_version,
        "generated_at": utcnow().isoformat(),
        "confidence": _confidence_bucket(summary, coverage),
        "missing_signals": coverage.get("missing_signals", []),
        "results": scored_results[:10],
    }
    record = PersonalizedRecommendation(
        user_id=user.id,
        context=context,
        profile_version=profile.profile_version,
        results_json=payload,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def latest_cached_recommendation(session: Session, user_id: str, context: str) -> PersonalizedRecommendation | None:
    return session.scalar(
        select(PersonalizedRecommendation)
        .where(PersonalizedRecommendation.user_id == user_id, PersonalizedRecommendation.context == context)
        .order_by(PersonalizedRecommendation.profile_version.desc(), PersonalizedRecommendation.computed_at.desc())
    )


def ensure_recommendations(
    session: Session,
    user: User,
    context: str,
    catalog_service: ShoeCatalogService,
    recommendation_service: ShoeRecommendationService,
) -> dict:
    profile = latest_profile(session, user.id)
    if not profile:
        raise LookupError("Runner profile not available")
    cached = latest_cached_recommendation(session, user.id, context)
    if cached and cached.profile_version == profile.profile_version:
        return cached.results_json
    record = compute_recommendations_for_context(session, user, context, catalog_service, recommendation_service)
    return record.results_json


def recompute_all_contexts(
    session: Session,
    user: User,
    catalog_service: ShoeCatalogService,
    recommendation_service: ShoeRecommendationService,
) -> dict:
    payload = {}
    for context in SUPPORTED_CONTEXTS:
        payload[context] = ensure_recommendations(session, user, context, catalog_service, recommendation_service)
    return payload

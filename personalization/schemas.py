from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SessionBootstrapResponse(BaseModel):
    user_id: str
    session_status: str
    strava_available: bool


class ProfileOverrides(BaseModel):
    preferred_terrain: Optional[str] = None
    weekly_mileage_override_km: Optional[float] = Field(default=None, ge=0)
    target_contexts: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class RunnerProfileResponse(BaseModel):
    user_id: str
    profile_version: int
    computed_at: Optional[datetime] = None
    summary: Dict[str, Any]
    coverage: Dict[str, Any]
    manual_overrides: ProfileOverrides = Field(default_factory=ProfileOverrides)


class ProfileUpdateRequest(ProfileOverrides):
    pass


class OwnedShoeCreateRequest(BaseModel):
    catalog_shoe_id: Optional[str] = None
    custom_brand: Optional[str] = None
    custom_name: Optional[str] = None
    strava_gear_id: Optional[str] = None
    start_mileage_km: float = Field(default=0, ge=0)
    retirement_target_km: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None


class OwnedShoeUpdateRequest(BaseModel):
    start_mileage_km: Optional[float] = Field(default=None, ge=0)
    retirement_target_km: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    strava_gear_id: Optional[str] = None


class OwnedShoeResponse(BaseModel):
    id: str
    catalog_shoe_id: Optional[str] = None
    display_name: str
    terrain: Optional[str] = None
    ride_role: Optional[str] = None
    current_mileage_km: float
    retirement_target_km: Optional[float] = None
    remaining_km: Optional[float] = None
    status: str
    notes: Optional[str] = None
    is_active: bool
    facets: Optional[Dict[str, Any]] = None
    source_kind: str
    mapping_status: str
    raw_import_name: Optional[str] = None
    activity_count: int = 0
    recent_uses_30d: int = 0


class RotationSummary(BaseModel):
    manual_count: int = 0
    imported_count: int = 0
    mapped_count: int = 0
    unmapped_count: int = 0


class RotationResponse(BaseModel):
    shoes: List[OwnedShoeResponse]
    summary: RotationSummary = Field(default_factory=RotationSummary)


class FeedbackRequest(BaseModel):
    catalog_shoe_id: str
    signal: str
    context: Optional[str] = None
    note: Optional[str] = None


class ImportJobResponse(BaseModel):
    id: str
    job_type: str
    status: str
    summary: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    error_text: Optional[str] = None


class PersonalizedRecommendationItem(BaseModel):
    shoe_id: str
    brand: str
    shoe_name: str
    display_name: str
    terrain: Optional[str] = None
    audience_verdict: Optional[int] = None
    source_url: Optional[str] = None
    facets: Dict[str, Any] = Field(default_factory=dict)
    metric_snapshot: Dict[str, Any] = Field(default_factory=dict)
    final_score: float
    explanation: str
    positive_drivers: List[str] = Field(default_factory=list)
    penalties: List[str] = Field(default_factory=list)
    missing_signals: List[str] = Field(default_factory=list)
    confidence: str
    component_scores: Dict[str, float] = Field(default_factory=dict)


class PersonalizedRecommendationResponse(BaseModel):
    context: str
    profile_version: int
    generated_at: datetime
    confidence: str
    missing_signals: List[str] = Field(default_factory=list)
    results: List[PersonalizedRecommendationItem] = Field(default_factory=list)

from __future__ import annotations

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from personalization.db import Base
from personalization.utils import utcnow


def new_id() -> str:
    return str(uuid4())


class SourceType(str, enum.Enum):
    manual = "manual"
    csv = "csv"
    gpx = "gpx"
    strava = "strava"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class JobType(str, enum.Enum):
    parse_import = "parse_import"
    rebuild_profile = "rebuild_profile"
    recompute_recommendations = "recompute_recommendations"
    strava_backfill = "strava_backfill"
    strava_refresh = "strava_refresh"


class RunContext(str, enum.Enum):
    easy = "easy"
    long = "long"
    workout = "workout"
    recovery = "recovery"
    trail = "trail"
    unknown = "unknown"


class LabelSource(str, enum.Enum):
    auto = "auto"
    user = "user"


class FeedbackSignal(str, enum.Enum):
    like = "like"
    dislike = "dislike"
    owned = "owned"
    retired = "retired"
    comfortable = "comfortable"
    uncomfortable = "uncomfortable"


class StravaConnectionStatus(str, enum.Enum):
    active = "active"
    revoked = "revoked"
    error = "error"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    guest_session_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    strava_athlete_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    preferences_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OwnedShoe(Base):
    __tablename__ = "owned_shoes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    catalog_shoe_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    custom_brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    custom_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    strava_gear_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    start_mileage_km: Mapped[float] = mapped_column(Float, default=0.0)
    retirement_target_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ActivitySource(Base):
    __tablename__ = "activity_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    scope_json: Mapped[dict] = mapped_column(JSON, default=dict)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_cursor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActivityRaw(Base):
    __tablename__ = "activities_raw"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_activity_source_external"),
        UniqueConstraint("source_id", "checksum", name="uq_activity_source_checksum"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("activity_sources.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    timezone_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sport_type: Mapped[str] = mapped_column(String(64), default="Run")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActivityFeature(Base):
    __tablename__ = "activity_features"

    activity_id: Mapped[str] = mapped_column(
        ForeignKey("activities_raw.id", ondelete="CASCADE"),
        primary_key=True,
    )
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    moving_time_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    elapsed_time_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_pace_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_cadence: Mapped[float | None] = mapped_column(Float, nullable=True)
    surface_guess: Mapped[str | None] = mapped_column(String(64), nullable=True)
    terrain_guess: Mapped[str | None] = mapped_column(String(64), nullable=True)
    has_hr: Mapped[bool] = mapped_column(Boolean, default=False)
    has_cadence: Mapped[bool] = mapped_column(Boolean, default=False)
    gear_ref: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)


class ActivityLabel(Base):
    __tablename__ = "activity_labels"

    activity_id: Mapped[str] = mapped_column(
        ForeignKey("activities_raw.id", ondelete="CASCADE"),
        primary_key=True,
    )
    run_context: Mapped[str] = mapped_column(String(32), default=RunContext.unknown.value)
    context_confidence: Mapped[float] = mapped_column(Float, default=0.1)
    label_source: Mapped[str] = mapped_column(String(16), default=LabelSource.auto.value)


class RunnerProfile(Base):
    __tablename__ = "runner_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    profile_version: Mapped[int] = mapped_column(Integer, index=True)
    profile_json: Mapped[dict] = mapped_column(JSON, default=dict)
    coverage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PersonalizedRecommendation(Base):
    __tablename__ = "personalized_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    context: Mapped[str] = mapped_column(String(32), index=True)
    profile_version: Mapped[int] = mapped_column(Integer, index=True)
    results_json: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StravaConnection(Base):
    __tablename__ = "strava_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    athlete_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    accepted_scopes: Mapped[list] = mapped_column(JSON, default=list)
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default=StravaConnectionStatus.active.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    catalog_shoe_id: Mapped[str] = mapped_column(String(255), index=True)
    context: Mapped[str | None] = mapped_column(String(32), nullable=True)
    signal: Mapped[str] = mapped_column(String(32), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.pending.value, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings_json: Mapped[list] = mapped_column(JSON, default=list)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

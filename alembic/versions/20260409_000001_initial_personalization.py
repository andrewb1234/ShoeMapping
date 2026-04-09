"""Initial personalization schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260409_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("guest_session_id", sa.String(length=128), nullable=False),
        sa.Column("strava_athlete_id", sa.String(length=64), nullable=True),
        sa.Column("preferences_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_guest_session_id", "users", ["guest_session_id"], unique=True)
    op.create_index("ix_users_strava_athlete_id", "users", ["strava_athlete_id"], unique=False)

    op.create_table(
        "owned_shoes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalog_shoe_id", sa.String(length=255), nullable=True),
        sa.Column("custom_brand", sa.String(length=255), nullable=True),
        sa.Column("custom_name", sa.String(length=255), nullable=True),
        sa.Column("strava_gear_id", sa.String(length=64), nullable=True),
        sa.Column("start_mileage_km", sa.Float(), nullable=False),
        sa.Column("retirement_target_km", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_owned_shoes_user_id", "owned_shoes", ["user_id"], unique=False)
    op.create_index("ix_owned_shoes_catalog_shoe_id", "owned_shoes", ["catalog_shoe_id"], unique=False)
    op.create_index("ix_owned_shoes_strava_gear_id", "owned_shoes", ["strava_gear_id"], unique=False)

    op.create_table(
        "activity_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cursor", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_activity_sources_user_id", "activity_sources", ["user_id"], unique=False)
    op.create_index("ix_activity_sources_source_type", "activity_sources", ["source_type"], unique=False)

    op.create_table(
        "activities_raw",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("activity_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone_name", sa.String(length=128), nullable=True),
        sa.Column("sport_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "external_id", name="uq_activity_source_external"),
        sa.UniqueConstraint("source_id", "checksum", name="uq_activity_source_checksum"),
    )
    op.create_index("ix_activities_raw_user_id", "activities_raw", ["user_id"], unique=False)
    op.create_index("ix_activities_raw_source_id", "activities_raw", ["source_id"], unique=False)
    op.create_index("ix_activities_raw_checksum", "activities_raw", ["checksum"], unique=False)
    op.create_index("ix_activities_raw_started_at", "activities_raw", ["started_at"], unique=False)

    op.create_table(
        "activity_features",
        sa.Column("activity_id", sa.String(length=36), sa.ForeignKey("activities_raw.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("moving_time_s", sa.Float(), nullable=True),
        sa.Column("elapsed_time_s", sa.Float(), nullable=True),
        sa.Column("elevation_gain_m", sa.Float(), nullable=True),
        sa.Column("avg_pace_mps", sa.Float(), nullable=True),
        sa.Column("avg_hr", sa.Float(), nullable=True),
        sa.Column("avg_cadence", sa.Float(), nullable=True),
        sa.Column("surface_guess", sa.String(length=64), nullable=True),
        sa.Column("terrain_guess", sa.String(length=64), nullable=True),
        sa.Column("has_hr", sa.Boolean(), nullable=False),
        sa.Column("has_cadence", sa.Boolean(), nullable=False),
        sa.Column("gear_ref", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_activity_features_gear_ref", "activity_features", ["gear_ref"], unique=False)

    op.create_table(
        "activity_labels",
        sa.Column("activity_id", sa.String(length=36), sa.ForeignKey("activities_raw.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("run_context", sa.String(length=32), nullable=False),
        sa.Column("context_confidence", sa.Float(), nullable=False),
        sa.Column("label_source", sa.String(length=16), nullable=False),
    )

    op.create_table(
        "runner_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("coverage_json", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_runner_profiles_user_id", "runner_profiles", ["user_id"], unique=False)
    op.create_index("ix_runner_profiles_profile_version", "runner_profiles", ["profile_version"], unique=False)

    op.create_table(
        "personalized_recommendations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("context", sa.String(length=32), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("results_json", sa.JSON(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_personalized_recommendations_user_id", "personalized_recommendations", ["user_id"], unique=False)
    op.create_index("ix_personalized_recommendations_context", "personalized_recommendations", ["context"], unique=False)
    op.create_index("ix_personalized_recommendations_profile_version", "personalized_recommendations", ["profile_version"], unique=False)

    op.create_table(
        "strava_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("athlete_id", sa.String(length=64), nullable=False),
        sa.Column("accepted_scopes", sa.JSON(), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("athlete_id"),
    )
    op.create_index("ix_strava_connections_athlete_id", "strava_connections", ["athlete_id"], unique=False)

    op.create_table(
        "user_feedback",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalog_shoe_id", sa.String(length=255), nullable=False),
        sa.Column("context", sa.String(length=32), nullable=True),
        sa.Column("signal", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_feedback_user_id", "user_feedback", ["user_id"], unique=False)
    op.create_index("ix_user_feedback_catalog_shoe_id", "user_feedback", ["catalog_shoe_id"], unique=False)
    op.create_index("ix_user_feedback_signal", "user_feedback", ["signal"], unique=False)

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_import_jobs_user_id", "import_jobs", ["user_id"], unique=False)
    op.create_index("ix_import_jobs_job_type", "import_jobs", ["job_type"], unique=False)
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_import_jobs_status", table_name="import_jobs")
    op.drop_index("ix_import_jobs_job_type", table_name="import_jobs")
    op.drop_index("ix_import_jobs_user_id", table_name="import_jobs")
    op.drop_table("import_jobs")

    op.drop_index("ix_user_feedback_signal", table_name="user_feedback")
    op.drop_index("ix_user_feedback_catalog_shoe_id", table_name="user_feedback")
    op.drop_index("ix_user_feedback_user_id", table_name="user_feedback")
    op.drop_table("user_feedback")

    op.drop_index("ix_strava_connections_athlete_id", table_name="strava_connections")
    op.drop_table("strava_connections")

    op.drop_index("ix_personalized_recommendations_profile_version", table_name="personalized_recommendations")
    op.drop_index("ix_personalized_recommendations_context", table_name="personalized_recommendations")
    op.drop_index("ix_personalized_recommendations_user_id", table_name="personalized_recommendations")
    op.drop_table("personalized_recommendations")

    op.drop_index("ix_runner_profiles_profile_version", table_name="runner_profiles")
    op.drop_index("ix_runner_profiles_user_id", table_name="runner_profiles")
    op.drop_table("runner_profiles")

    op.drop_table("activity_labels")
    op.drop_index("ix_activity_features_gear_ref", table_name="activity_features")
    op.drop_table("activity_features")

    op.drop_index("ix_activities_raw_started_at", table_name="activities_raw")
    op.drop_index("ix_activities_raw_checksum", table_name="activities_raw")
    op.drop_index("ix_activities_raw_source_id", table_name="activities_raw")
    op.drop_index("ix_activities_raw_user_id", table_name="activities_raw")
    op.drop_table("activities_raw")

    op.drop_index("ix_activity_sources_source_type", table_name="activity_sources")
    op.drop_index("ix_activity_sources_user_id", table_name="activity_sources")
    op.drop_table("activity_sources")

    op.drop_index("ix_owned_shoes_strava_gear_id", table_name="owned_shoes")
    op.drop_index("ix_owned_shoes_catalog_shoe_id", table_name="owned_shoes")
    op.drop_index("ix_owned_shoes_user_id", table_name="owned_shoes")
    op.drop_table("owned_shoes")

    op.drop_index("ix_users_strava_athlete_id", table_name="users")
    op.drop_index("ix_users_guest_session_id", table_name="users")
    op.drop_table("users")

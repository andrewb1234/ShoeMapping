from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_mode: str
    environment: str
    app_base_url: str
    public_web_base_url: str
    personalization_base_url: str
    database_url: str | None
    session_secret: str
    strava_client_id: str | None
    strava_client_secret: str | None
    strava_verify_token: str | None
    strava_redirect_uri: str | None
    enable_strava_ui: bool
    inline_job_execution: bool
    auto_create_db: bool
    session_cookie_name: str = "shoe_mapping_session"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def strava_is_configured(self) -> bool:
        return all(
            [
                self.strava_client_id,
                self.strava_client_secret,
                self.strava_verify_token,
                self.strava_redirect_uri,
            ]
        )

    @property
    def personalization_is_configured(self) -> bool:
        return bool(self.personalization_base_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    vercel_env = os.getenv("VERCEL_ENV")
    vercel_url = os.getenv("VERCEL_URL")
    environment = os.getenv("APP_ENV", vercel_env or "development")
    default_public_url = f"https://{vercel_url}" if vercel_url else "http://127.0.0.1:8000"
    default_personalization_url = "http://127.0.0.1:9000" if environment.lower() == "development" else ""

    app_base_url = os.getenv("APP_BASE_URL", default_public_url)
    public_web_base_url = os.getenv("PUBLIC_WEB_BASE_URL", default_public_url)
    personalization_base_url = os.getenv("PERSONALIZATION_BASE_URL", default_personalization_url)
    return Settings(
        app_mode=os.getenv("APP_MODE", "public"),
        environment=environment,
        app_base_url=app_base_url.rstrip("/"),
        public_web_base_url=public_web_base_url.rstrip("/"),
        personalization_base_url=personalization_base_url.rstrip("/"),
        database_url=os.getenv("DATABASE_URL"),
        session_secret=os.getenv("SESSION_SECRET", "development-only-session-secret"),
        strava_client_id=os.getenv("STRAVA_CLIENT_ID"),
        strava_client_secret=os.getenv("STRAVA_CLIENT_SECRET"),
        strava_verify_token=os.getenv("STRAVA_VERIFY_TOKEN"),
        strava_redirect_uri=os.getenv("STRAVA_REDIRECT_URI"),
        enable_strava_ui=_as_bool(os.getenv("ENABLE_STRAVA_UI"), default=False),
        inline_job_execution=_as_bool(
            os.getenv("INLINE_JOB_EXECUTION"),
            default=environment.lower() != "production",
        ),
        auto_create_db=_as_bool(
            os.getenv("AUTO_CREATE_DB"),
            default=environment.lower() != "production",
        ),
    )

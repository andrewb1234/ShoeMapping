from __future__ import annotations

from time import sleep

from sqlalchemy import select
from sqlalchemy.orm import Session

from personalization.db import SessionLocal
from personalization.models import ImportJob, JobStatus, JobType, User
from personalization.profile import compute_runner_profile
from personalization.scoring import recompute_all_contexts
from personalization.strava import backfill_user_activities, get_connection_for_user
from personalization.utils import utcnow
from webapp.config import get_settings
from webapp.services import ShoeCatalogService, ShoeRecommendationService


def create_job(
    session: Session,
    user_id: str,
    job_type: str,
    payload_json: dict | None = None,
    summary_json: dict | None = None,
    warnings_json: list[str] | None = None,
    run_inline: bool | None = None,
) -> ImportJob:
    job = ImportJob(
        user_id=user_id,
        job_type=job_type,
        status=JobStatus.pending.value,
        payload_json=payload_json or {},
        summary_json=summary_json or {},
        warnings_json=warnings_json or [],
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    if run_inline is None:
        run_inline = get_settings().inline_job_execution
    if run_inline:
        process_job_by_id(job.id)
        session.refresh(job)
    return job


def enqueue_profile_refresh(session: Session, user_id: str) -> None:
    create_job(session, user_id, JobType.rebuild_profile.value)
    create_job(session, user_id, JobType.recompute_recommendations.value)


def fetch_job_for_user(session: Session, user_id: str, job_id: str) -> ImportJob | None:
    return session.scalar(
        select(ImportJob).where(ImportJob.user_id == user_id, ImportJob.id == job_id)
    )


def _process_job(session: Session, job: ImportJob) -> None:
    catalog_service = ShoeCatalogService()
    recommendation_service = ShoeRecommendationService(catalog_service=catalog_service)
    user = session.get(User, job.user_id)
    if user is None:
        raise LookupError("Job user not found")

    if job.job_type == JobType.parse_import.value:
        job.summary_json = {**job.summary_json, "status": "parsed"}
    elif job.job_type == JobType.rebuild_profile.value:
        profile = compute_runner_profile(session, user, catalog_service)
        job.summary_json = {"profile_version": profile.profile_version}
    elif job.job_type == JobType.recompute_recommendations.value:
        results = recompute_all_contexts(session, user, catalog_service, recommendation_service)
        job.summary_json = {"contexts": list(results.keys())}
    elif job.job_type in {JobType.strava_backfill.value, JobType.strava_refresh.value}:
        connection = get_connection_for_user(session, user.id)
        if connection is None:
            raise LookupError("Strava connection not found")
        result = backfill_user_activities(session, user, connection)
        job.summary_json = result
    else:
        raise ValueError(f"Unsupported job type: {job.job_type}")


def process_job_by_id(job_id: str) -> None:
    with SessionLocal() as session:
        job = session.get(ImportJob, job_id)
        if job is None or job.status == JobStatus.completed.value:
            return
        job.status = JobStatus.running.value
        job.started_at = utcnow()
        session.add(job)
        session.commit()
        try:
            _process_job(session, job)
            job.status = JobStatus.completed.value
            job.completed_at = utcnow()
            job.error_text = None
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.failed.value
            job.completed_at = utcnow()
            job.error_text = str(exc)
        session.add(job)
        session.commit()


def process_next_pending_job() -> bool:
    with SessionLocal() as session:
        job = session.scalar(
            select(ImportJob)
            .where(ImportJob.status == JobStatus.pending.value)
            .order_by(ImportJob.created_at.asc())
        )
        if job is None:
            return False
        job_id = job.id
    process_job_by_id(job_id)
    return True


def worker_loop(sleep_seconds: float = 2.0) -> None:
    while True:
        processed = process_next_pending_job()
        if not processed:
            sleep(sleep_seconds)

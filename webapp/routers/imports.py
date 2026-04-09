from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from personalization.db import get_db_session
from personalization.imports import parse_csv_bytes, parse_gpx_bytes, store_normalized_activities
from personalization.jobs import create_job, enqueue_profile_refresh, fetch_job_for_user
from personalization.models import ImportJob, JobStatus, JobType, SourceType, User
from personalization.schemas import ImportJobResponse
from personalization.session import get_current_user


router = APIRouter()


@router.post("/api/imports", response_model=ImportJobResponse)
async def create_import(
    file: UploadFile = File(...),
    source_type: str | None = Form(default=None),
    column_mapping_json: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> ImportJobResponse:
    filename = file.filename or "upload"
    inferred_source = source_type or Path(filename).suffix.lstrip(".").lower()
    if inferred_source not in {SourceType.csv.value, SourceType.gpx.value}:
        raise HTTPException(status_code=400, detail="Only CSV and GPX imports are supported.")

    job = create_job(
        db,
        user.id,
        JobType.parse_import.value,
        summary_json={"filename": filename, "source_type": inferred_source},
        run_inline=False,
    )
    job.status = JobStatus.running.value
    db.add(job)
    db.commit()
    payload = await file.read()
    try:
        column_mapping = json.loads(column_mapping_json) if column_mapping_json else None
        if inferred_source == SourceType.csv.value:
            activities, summary, warnings = parse_csv_bytes(filename, payload, column_mapping=column_mapping)
            ingest_summary = store_normalized_activities(
                db,
                user,
                SourceType.csv,
                activities,
                scope_json={"filename": filename, "column_mapping": summary.get("column_mapping", {})},
            )
        else:
            activities, summary, warnings = parse_gpx_bytes(filename, payload)
            ingest_summary = store_normalized_activities(
                db,
                user,
                SourceType.gpx,
                activities,
                scope_json={"filename": filename},
            )
        job.status = JobStatus.completed.value
        job.summary_json = {**summary, **ingest_summary}
        job.warnings_json = warnings
        job.error_text = None
        db.add(job)
        db.commit()
        enqueue_profile_refresh(db, user.id)
    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.failed.value
        job.error_text = str(exc)
        db.add(job)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ImportJobResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        summary=job.summary_json,
        warnings=job.warnings_json,
        error_text=job.error_text,
    )


@router.get("/api/imports/{job_id}", response_model=ImportJobResponse)
def get_import_status(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> ImportJobResponse:
    job = fetch_job_for_user(db, user.id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return ImportJobResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        summary=job.summary_json,
        warnings=job.warnings_json,
        error_text=job.error_text,
    )

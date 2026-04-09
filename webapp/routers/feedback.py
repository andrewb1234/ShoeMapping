from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from personalization.db import get_db_session
from personalization.jobs import create_job
from personalization.models import JobType, User, UserFeedback
from personalization.schemas import FeedbackRequest
from personalization.session import get_current_user


router = APIRouter()


@router.post("/api/feedback")
def create_feedback(
    payload: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict:
    feedback = UserFeedback(
        user_id=user.id,
        catalog_shoe_id=payload.catalog_shoe_id,
        context=payload.context,
        signal=payload.signal,
        note=payload.note,
    )
    db.add(feedback)
    db.commit()
    create_job(db, user.id, JobType.recompute_recommendations.value)
    return {"status": "ok"}

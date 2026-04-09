from __future__ import annotations

from uuid import uuid4

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from personalization.db import get_db_session
from personalization.models import User
from personalization.security import decode_session_cookie, session_serializer
from personalization.utils import utcnow
from webapp.config import get_settings


def _cookie_name() -> str:
    return get_settings().session_cookie_name


def bootstrap_user_session(response: Response, db: Session) -> User:
    settings = get_settings()
    guest_session_id = str(uuid4())
    user = User(guest_session_id=guest_session_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    cookie_value = session_serializer().dumps({"sid": guest_session_id})
    response.set_cookie(
        key=settings.session_cookie_name,
        value=cookie_value,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=60 * 60 * 24 * 365,
    )
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db_session),
) -> User:
    raw_cookie = request.cookies.get(_cookie_name())
    payload = decode_session_cookie(raw_cookie) if raw_cookie else None
    if not payload or "sid" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not initialized",
        )
    user = db.scalar(select(User).where(User.guest_session_id == payload["sid"]))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found",
        )
    user.last_seen_at = utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from personalization.db import get_db_session
from personalization.jobs import enqueue_profile_refresh
from personalization.models import OwnedShoe, User
from personalization.rotation import build_rotation_summary, default_retirement_target, summarize_rotation_inventory
from personalization.schemas import (
    OwnedShoeCreateRequest,
    OwnedShoeResponse,
    OwnedShoeUpdateRequest,
    RotationResponse,
)
from personalization.session import get_current_user
from webapp.deps import get_catalog_service
from webapp.services import ShoeCatalogService


router = APIRouter()


@router.get("/api/rotation", response_model=RotationResponse)
def get_rotation(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    catalog_service: ShoeCatalogService = Depends(get_catalog_service),
) -> RotationResponse:
    shoes = build_rotation_summary(db, user, catalog_service)
    return RotationResponse(
        shoes=[OwnedShoeResponse(**shoe) for shoe in shoes],
        summary=summarize_rotation_inventory(shoes),
    )


@router.post("/api/rotation/shoes", response_model=OwnedShoeResponse)
def add_owned_shoe(
    payload: OwnedShoeCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    catalog_service: ShoeCatalogService = Depends(get_catalog_service),
) -> OwnedShoeResponse:
    if not payload.catalog_shoe_id and not (payload.custom_brand and payload.custom_name):
        raise HTTPException(status_code=400, detail="Provide a catalog shoe or a custom brand and name.")
    catalog_entry = catalog_service.get_shoe_by_id(payload.catalog_shoe_id or "")
    ride_role = (catalog_entry.get("facets") or {}).get("ride_role")
    terrain = catalog_entry.get("terrain")
    owned_shoe = OwnedShoe(
        user_id=user.id,
        catalog_shoe_id=payload.catalog_shoe_id,
        custom_brand=payload.custom_brand or catalog_entry.get("brand"),
        custom_name=payload.custom_name or catalog_entry.get("shoe_name"),
        strava_gear_id=payload.strava_gear_id,
        start_mileage_km=payload.start_mileage_km,
        retirement_target_km=payload.retirement_target_km or default_retirement_target(terrain, ride_role),
        notes=payload.notes,
        is_active=True,
    )
    db.add(owned_shoe)
    db.commit()
    enqueue_profile_refresh(db, user.id)
    shoes = build_rotation_summary(db, user, catalog_service)
    created = next(shoe for shoe in shoes if shoe["id"] == owned_shoe.id)
    return OwnedShoeResponse(**created)


@router.patch("/api/rotation/shoes/{shoe_id}", response_model=OwnedShoeResponse)
def update_owned_shoe(
    shoe_id: str,
    payload: OwnedShoeUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    catalog_service: ShoeCatalogService = Depends(get_catalog_service),
) -> OwnedShoeResponse:
    owned_shoe = db.scalar(
        select(OwnedShoe).where(OwnedShoe.id == shoe_id, OwnedShoe.user_id == user.id)
    )
    if owned_shoe is None:
        raise HTTPException(status_code=404, detail="Owned shoe not found")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(owned_shoe, field, value)
    db.add(owned_shoe)
    db.commit()
    enqueue_profile_refresh(db, user.id)
    shoes = build_rotation_summary(db, user, catalog_service)
    updated = next(shoe for shoe in shoes if shoe["id"] == owned_shoe.id)
    return OwnedShoeResponse(**updated)

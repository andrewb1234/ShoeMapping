from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from personalization.db import get_db_session
from personalization.session import get_current_user
from personalization.models import User
from personalization.visualizations import get_all_visualizations
from webapp.deps import get_catalog_service
from webapp.services import ShoeCatalogService


router = APIRouter()


@router.get("/api/visualizations")
def get_visualizations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    catalog_service: ShoeCatalogService = Depends(get_catalog_service),
) -> dict:
    """
    Get all running data visualizations for the current user.
    
    Returns:
    - efficiency_heatmap: HR-adjusted pace efficiency by shoe
    - monthly_mileage: Monthly aggregated stats by shoe
    - shoe_mileage: Cumulative mileage tracker with retirement zones
    - pace_distribution: Pace quartiles by shoe and run context
    - rotation_calendar: Weekly shoe usage heatmap
    """
    return get_all_visualizations(db, user, catalog_service)

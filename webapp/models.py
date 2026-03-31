from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

TerrainSelection = Literal["Road", "Trail", "Both"]


class ShoeListItem(BaseModel):
    shoe_id: str
    brand: str
    shoe_name: str
    display_name: str
    terrain: Optional[str] = None
    source_url: str
    crawled_at: str
    audience_verdict: Optional[int] = None


class ShoeListResponse(BaseModel):
    terrain: str
    count: int
    shoes: List[ShoeListItem]


class RecommendationRequest(BaseModel):
    shoe_id: Optional[str] = None
    shoe_name: Optional[str] = None
    terrain: Optional[str] = None
    n_neighbors: int = Field(default=5, ge=1, le=20)
    n_clusters: int = Field(default=8, ge=1, le=20)
    rejected: Optional[List[str]] = Field(default_factory=list, description="List of rejected shoe IDs to exclude")

    @model_validator(mode="after")
    def validate_query(self) -> "RecommendationRequest":
        if not self.shoe_id and not self.shoe_name:
            raise ValueError("Provide either shoe_id or shoe_name.")
        return self


class RecommendationResponse(BaseModel):
    query: Optional[str] = None
    query_shoe: Optional[str] = None
    query_shoe_id: Optional[str] = None
    terrain: str
    matched_shoe: Optional[Dict[str, Any]] = None
    recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    algorithm: Optional[str] = None
    cluster_label: Optional[int] = None
    cluster_size: Optional[int] = None
    cluster_center: Optional[Dict[str, Optional[float]]] = None
    feature_names: Optional[List[str]] = None
    n_clusters: Optional[int] = None
    error: Optional[str] = None
    suggestions: Optional[List[str]] = None

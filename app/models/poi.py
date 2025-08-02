# campulse-backend/app/models/poi.py
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from app.core.geopoint import GeoPointModel

class POICreate(BaseModel):
    name: str
    description: Optional[str] = None
    lat: float
    lng: float
    location: GeoPointModel
    radius_m: int
    type: str
    tags: List[str] = []
    cover_image_url: Optional[str] = None

class POIUpdate(POICreate):
    name: Optional[str] = None
    description: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    location: Optional[GeoPointModel] = None
    radius_m: Optional[int] = None
    type: Optional[str] = None
    tags: Optional[List[str]] = None
    cover_image_url: Optional[str] = None

from app.models.base import DocumentInDB

class POIInDB(DocumentInDB, POICreate):
    pass

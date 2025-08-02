# campulse-backend/app/models/institution.py
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from app.core.geopoint import GeoPointModel

class InstitutionCreate(BaseModel):
    owner_id: str
    name: str
    category: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    lat: float
    lng: float
    location: GeoPointModel
    poi_id: Optional[str] = None
    region: str
    website: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    cover_image_url: Optional[str] = None
    verified: bool = False

class InstitutionUpdate(InstitutionCreate):
    owner_id: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    location: Optional[GeoPointModel] = None
    poi_id: Optional[str] = None
    region: Optional[str] = None
    website: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    cover_image_url: Optional[str] = None
    verified: Optional[bool] = None

from app.models.base import DocumentInDB

class InstitutionInDB(DocumentInDB, InstitutionCreate):
    pass

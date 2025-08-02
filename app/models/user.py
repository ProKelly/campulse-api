# campulse-backend/app/models/user.py
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from app.core.geopoint import GeoPointModel

class NotificationSettings(BaseModel):
    new_posts: bool = True
    proximity_alerts: bool = False
    ai_recommendations: bool = True

class PrivacySettings(BaseModel):
    share_location_history: bool = False

class LocationHistoryEntry(BaseModel):
    location: GeoPointModel
    timestamp: datetime = Field(default_factory=datetime.now)

class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    role: str = "user"
    preferred_categories: List[str] = []
    language: str = "en"
    location: GeoPointModel
    location_history: List[LocationHistoryEntry] = []
    notification_settings: NotificationSettings = NotificationSettings()
    privacy: PrivacySettings = PrivacySettings()
    profile_image_url: Optional[str] = None
    bio: Optional[str] = None
    followers: List[str] = []
    following: List[str] = []

class UserUpdate(UserCreate):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    preferred_categories: Optional[List[str]] = None
    language: Optional[str] = None
    location: Optional[GeoPointModel] = None
    location_history: Optional[List[LocationHistoryEntry]] = None
    notification_settings: Optional[NotificationSettings] = None
    privacy: Optional[PrivacySettings] = None
    profile_image_url: Optional[str] = None
    bio: Optional[str] = None
    followers: Optional[List[str]] = None
    following: Optional[List[str]] = None

from app.models.base import DocumentInDB

class UserInDB(DocumentInDB, UserCreate):
    pass

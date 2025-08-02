from typing import List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field

class MapLocation(BaseModel):
    label: str
    lat: float
    lng: float

class SmartSuggestions(BaseModel):
    suggested_tags: List[str] = []
    related_posts: List[str] = []

# Specific models for different post types
class JobDetails(BaseModel):
    salary: Optional[str] = None
    application_deadline: Optional[datetime] = None
    application_requirements: List[str] = []
    job_type: Optional[str] = None  # e.g., full-time, part-time, contract
    location: Optional[str] = None

class InternshipDetails(BaseModel):
    stipend: Optional[str] = None
    duration: Optional[str] = None
    application_deadline: Optional[datetime] = None
    application_requirements: List[str] = []
    location: Optional[str] = None

class EventDetails(BaseModel):
    event_date: Optional[datetime] = None
    venue: Optional[str] = None
    organizer: Optional[str] = None
    registration_link: Optional[str] = None

class NewsDetails(BaseModel):
    source: Optional[str] = None
    published_date: Optional[datetime] = None

# Union of all possible post details
PostDetails = Union[JobDetails, InternshipDetails, EventDetails, NewsDetails]

class InstitutionPostCreate(BaseModel):
    institution_id: str
    title: str
    content: str
    type_of_post: str  # e.g., "job", "internship", "news", "event"
    tags: List[str] = []
    sentiment: Optional[str] = None
    poi_id: Optional[str] = None
    categories: List[str] = []
    image_url: Optional[str] = None
    visibility: str = "public"
    map_location: Optional[MapLocation] = None
    smart_suggestions: SmartSuggestions = SmartSuggestions()
    summary: Optional[str] = None
    details: Optional[PostDetails] = None  # Dynamic field for specific post details

class InstitutionPostUpdate(InstitutionPostCreate):
    institution_id: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    type_of_post: Optional[str] = None
    tags: Optional[List[str]] = None
    sentiment: Optional[str] = None
    poi_id: Optional[str] = None
    categories: Optional[List[str]] = None
    image_url: Optional[str] = None
    visibility: Optional[str] = None
    map_location: Optional[MapLocation] = None
    smart_suggestions: Optional[SmartSuggestions] = None
    summary: Optional[str] = None
    details: Optional[PostDetails] = None

from app.models.base import DocumentInDB

class InstitutionPostInDB(DocumentInDB, InstitutionPostCreate):
    published_at: Optional[datetime] = None
    distance: Optional[float] = None
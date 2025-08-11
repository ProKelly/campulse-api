from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

class NewsLocation(BaseModel):
    lat: float
    lng: float

class NewsCreate(BaseModel):
    headline: str
    summary: str
    source: str
    tags: List[str] = []
    topic: str
    location: Optional[NewsLocation] = None
    show_full_article: bool = False
    article_url: Optional[str] = None

class NewsUpdate(NewsCreate):
    headline: Optional[str] = None
    summary: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[List[str]] = None
    topic: Optional[str] = None
    location: Optional[NewsLocation] = None
    show_full_article: Optional[bool] = None
    article_url: Optional[str] = None

from app.models.base import DocumentInDB

class NewsInDB(DocumentInDB, NewsCreate):
    timestamp: Optional[datetime] = None

# News from api sources
class NewsItem(BaseModel):
    id: Optional[str]
    title: str
    description: Optional[str]
    url: Optional[str]
    source: Optional[str]
    image: Optional[str]
    time: Optional[str]
    type_of_post: Optional[str]
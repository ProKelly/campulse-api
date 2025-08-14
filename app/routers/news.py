from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
import asyncio
from dateutil.parser import parse
from app.models.news import NewsCreate, NewsUpdate, NewsInDB, NewsItem
from app.auth.firebase_auth import get_current_user_id
from app.config import db
from app.db.utils import convert_doc_to_model
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from app.core.websearch import fetch_newsapi_news, fetch_serpapi_news, fetch_serper_news

router = APIRouter(prefix="/news", tags=["News"])


# Firestore CRUD endpoints
@router.post("/", response_model=NewsInDB, status_code=status.HTTP_201_CREATED)
async def create_news(news: NewsCreate, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    news_data = news.model_dump()
    news_data['timestamp'] = SERVER_TIMESTAMP
    try:
        doc_ref = db.collection("news").document()
        doc_ref.set(news_data)  # synchronous
        created_doc = doc_ref.get()  # synchronous
        return convert_doc_to_model(created_doc.id, created_doc.to_dict(), NewsInDB)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create news: {e}")


@router.get("/", response_model=List[NewsInDB])
async def get_all_news():
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        news_entries = []
        docs = db.collection("news").stream()  # synchronous
        for doc in docs:
            news_entries.append(convert_doc_to_model(doc.id, doc.to_dict(), NewsInDB))
        return news_entries
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve news: {e}")


@router.get("/{news_id}", response_model=NewsInDB)
async def get_news(news_id: str):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        news_ref = db.collection("news").document(news_id)
        doc = news_ref.get()  # synchronous
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News entry not found")
        return convert_doc_to_model(doc.id, doc.to_dict(), NewsInDB)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve news: {e}")


@router.put("/{news_id}", response_model=NewsInDB)
async def update_news(news_id: str, news: NewsUpdate, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        news_ref = db.collection("news").document(news_id)
        doc = news_ref.get()  # synchronous
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News entry not found")
        update_data = news.model_dump(exclude_unset=True)
        news_ref.update(update_data)  # synchronous
        updated_doc = news_ref.get()  # synchronous
        return convert_doc_to_model(updated_doc.id, updated_doc.to_dict(), NewsInDB)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update news: {e}")


@router.delete("/{news_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_news(news_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        news_ref = db.collection("news").document(news_id)
        doc = news_ref.get()  # synchronous
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News entry not found")
        news_ref.delete()  # synchronous
        return {"message": "News entry deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete news: {e}")


# External news search endpoint
@router.get("/search", response_model=List[NewsItem])
async def search_news(
    q: Optional[str] = Query("", description="Search query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    source: Optional[str] = Query(None, description="Source filter: 'newsapi', 'serpapi', 'serper' or None for all"),
):
    tasks = []
    results = []

    query = q or "Cameroon"

    if source in [None, "newsapi"]:
        tasks.append(fetch_newsapi_news(query=query, page=page, page_size=page_size))
    if source in [None, "serpapi"]:
        tasks.append(fetch_serpapi_news(query=query, num=page_size))
    if source in [None, "serper"]:
        tasks.append(fetch_serper_news(query=query, num=page_size))

    if not tasks:
        raise HTTPException(status_code=400, detail="Invalid source parameter")

    fetched_results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in fetched_results:
        if isinstance(result, Exception):
            continue
        results.extend(result)

    seen = set()
    unique_results = []
    for item in results:
        identifier = item.url or item.title
        if identifier and identifier not in seen:
            seen.add(identifier)
            unique_results.append(item)

    def parse_time(t):
        try:
            return parse(t)
        except Exception:
            return None

    unique_results.sort(key=lambda x: parse_time(x.time) or 0, reverse=True)

    start = (page - 1) * page_size
    end = start + page_size
    return unique_results[start:end]

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.models.news import NewsCreate, NewsUpdate, NewsInDB
from app.auth.firebase_auth import get_current_user_id
from app.config import db
from app.db.utils import convert_doc_to_model
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

router = APIRouter(prefix="/news", tags=["News"])

@router.post("/", response_model=NewsInDB, status_code=status.HTTP_201_CREATED)
async def create_news(news: NewsCreate, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        news_data = news.model_dump()
        news_data['timestamp'] = SERVER_TIMESTAMP
        doc_ref = db.collection("news").document()
        await doc_ref.set(news_data)
        created_doc = await doc_ref.get()
        return convert_doc_to_model(created_doc.id, created_doc.to_dict(), NewsInDB)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create news: {e}")

@router.get("/", response_model=List[NewsInDB])
async def get_all_news():
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        news_entries = []
        docs = db.collection("news").stream()
        async for doc in docs:
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
        doc = await news_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News entry not found")
        return convert_doc_to_model(doc.id, doc.to_dict(), NewsInDB)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve news: {e}")

@router.put("/{news_id}", response_model=NewsInDB)
async def update_news(news_id: str, news: NewsUpdate, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        news_ref = db.collection("news").document(news_id)
        if not (await news_ref.get()).exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News entry not found")
        update_data = news.model_dump(exclude_unset=True)
        await news_ref.update(update_data)
        updated_doc = await news_ref.get()
        return convert_doc_to_model(updated_doc.id, updated_doc.to_dict(), NewsInDB)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update news: {e}")

@router.delete("/{news_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_news(news_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        news_ref = db.collection("news").document(news_id)
        if not (await news_ref.get()).exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News entry not found")
        await news_ref.delete()
        return {"message": "News entry deleted successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete news: {e}")

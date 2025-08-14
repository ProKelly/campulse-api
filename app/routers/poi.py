from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.models.poi import POICreate, POIUpdate, POIInDB
from app.auth.firebase_auth import get_current_user_id
from app.config import db
from app.db.utils import convert_doc_to_model
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

router = APIRouter(prefix="/pois", tags=["POIs"])


@router.post("/", response_model=POIInDB, status_code=status.HTTP_201_CREATED)
async def create_poi(poi: POICreate, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        poi_data = poi.model_dump(by_alias=True)
        poi_data['location'] = poi.location.to_firestore_geopoint()
        poi_data['created_at'] = SERVER_TIMESTAMP

        doc_ref = db.collection("pois").document()
        doc_ref.set(poi_data)  # synchronous
        created_doc = doc_ref.get()  # synchronous

        return convert_doc_to_model(created_doc.id, created_doc.to_dict(), POIInDB)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create POI: {e}")


@router.get("/", response_model=List[POIInDB])
async def get_all_pois():
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        pois = []
        docs = db.collection("pois").stream()  # synchronous
        for doc in docs:
            pois.append(convert_doc_to_model(doc.id, doc.to_dict(), POIInDB))
        return pois
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve POIs: {e}")


@router.get("/{poi_id}", response_model=POIInDB)
async def get_poi(poi_id: str):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        poi_ref = db.collection("pois").document(poi_id)
        doc = poi_ref.get()  # synchronous
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POI not found")
        return convert_doc_to_model(doc.id, doc.to_dict(), POIInDB)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve POI: {e}")


@router.put("/{poi_id}", response_model=POIInDB)
async def update_poi(poi_id: str, poi: POIUpdate, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        poi_ref = db.collection("pois").document(poi_id)
        existing_doc = poi_ref.get()  # synchronous
        if not existing_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POI not found")

        update_data = poi.model_dump(exclude_unset=True, by_alias=True)
        if 'location' in update_data and update_data['location'] is not None:
            update_data['location'] = poi.location.to_firestore_geopoint()

        poi_ref.update(update_data)  # synchronous
        updated_doc = poi_ref.get()  # synchronous

        return convert_doc_to_model(updated_doc.id, updated_doc.to_dict(), POIInDB)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update POI: {e}")


@router.delete("/{poi_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_poi(poi_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        poi_ref = db.collection("pois").document(poi_id)
        existing_doc = poi_ref.get()  # synchronous
        if not existing_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POI not found")

        poi_ref.delete()  # synchronous
        return {"message": "POI deleted successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete POI: {e}")

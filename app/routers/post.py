from datetime import datetime, timedelta  # Fixed import
import math
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from app.models.post import InstitutionPostCreate, InstitutionPostUpdate, InstitutionPostInDB
from app.auth.firebase_auth import get_current_user_id
from app.config import db
from app.db.utils import convert_doc_to_model, bounding_box
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
import logging
import geohash2 

router = APIRouter(prefix="/institution_posts", tags=["Institution Posts"])
logger = logging.getLogger(__name__)


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points using Haversine formula"""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

@router.post("/", response_model=InstitutionPostInDB, status_code=status.HTTP_201_CREATED)
async def create_institution_post(post: InstitutionPostCreate, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore not initialized.")
    
    institution_ref = db.collection("institutions").document(post.institution_id)
    institution_doc = institution_ref.get()

    if not institution_doc.exists:
        raise HTTPException(status_code=400, detail="Institution not found.")
    if institution_doc.to_dict().get('owner_id') != current_user_id:
        raise HTTPException(status_code=403, detail="Not authorized to post for this institution.")

    try:
        post_data = post.model_dump(by_alias=True)
        post_data['published_at'] = SERVER_TIMESTAMP

        # Ensure we have map_location
        if post.map_location:
            lat = post.map_location.lat
            lng = post.map_location.lng
            post_data['geohash'] = geohash2.encode(lat, lng, precision=9)

        doc_ref = db.collection("institution_posts").document()
        doc_ref.set(post_data)

        created_doc = doc_ref.get()
        return convert_doc_to_model(created_doc.id, created_doc.to_dict(), InstitutionPostInDB)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create institution post: {e}")

@router.get("/", response_model=List[InstitutionPostInDB])
async def get_all_institution_posts(
    category: Optional[str] = None,
    time_filter: Optional[str] = None,
    sort: Optional[str] = None,
    limit: int = 50
):
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore not initialized.")
    
    try:
        query = db.collection("institution_posts")
        
        # Apply category filter if specified
        if category and category.lower() != 'all':
            query = query.where('categories', 'array_contains', category)
        
        # Apply time filter if specified
        if time_filter:
            now = datetime.now()
            time_filter = time_filter.lower()
            
            if time_filter == 'today':
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                query = query.where('created_at', '>=', start_time)
            elif time_filter == 'this week':
                start_time = now - timedelta(days=now.weekday())
                start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
                query = query.where('created_at', '>=', start_time)
            elif time_filter == 'this month':
                start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                query = query.where('created_at', '>=', start_time)
        
        # Default sorting by created_at
        query = query.order_by('created_at', direction='DESCENDING')
        
        # Limit results
        query = query.limit(limit)
        
        # Execute query
        posts = []
        docs = query.stream()
        
        for doc in docs:
            posts.append(convert_doc_to_model(doc.id, doc.to_dict(), InstitutionPostInDB))
        
        # Apply "Popular" sorting in memory if needed
        if sort and sort.lower() == 'popular':
            posts.sort(key=lambda x: len(x.smart_suggestions.related_posts) if hasattr(x, 'smart_suggestions') else 0, reverse=True)
        
        return posts
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve posts: {e}")
    

@router.get("/nearby", response_model=List[InstitutionPostInDB])
async def get_nearby_institution_posts(lat: float, lon: float, radius: int = 500):
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore not initialized.")
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="Invalid coordinates")

    try:
        min_lat, min_lon, max_lat, max_lon = bounding_box(lat, lon, radius)

        # Compute geohashes for corners of the box
        geohash_sw = geohash2.encode(min_lat, min_lon, precision=5)
        geohash_ne = geohash2.encode(max_lat, max_lon, precision=5)

        # Query Firestore by geohash range
        query = db.collection("institution_posts") \
                  .where("geohash", ">=", geohash_sw) \
                  .where("geohash", "<=", geohash_ne)

        posts = []
        for doc in query.stream():
            post_data = doc.to_dict()
            if 'map_location' in post_data:
                post_lat = post_data['map_location']['lat']
                post_lon = post_data['map_location']['lng']
                distance = haversine_distance(lat, lon, post_lat, post_lon)
                if distance <= radius:
                    post_model = convert_doc_to_model(doc.id, post_data, InstitutionPostInDB)
                    setattr(post_model, 'distance', distance)
                    posts.append(post_model)

        posts.sort(key=lambda x: x.distance)
        return posts[:50]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve nearby institution posts: {e}")

@router.get("/{post_id}", response_model=InstitutionPostInDB)
async def get_institution_post(post_id: str):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        post_ref = db.collection("institution_posts").document(post_id)
        doc = await post_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution post not found")
        return convert_doc_to_model(doc.id, doc.to_dict(), InstitutionPostInDB)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve institution post: {e}")

@router.put("/{post_id}", response_model=InstitutionPostInDB)
async def update_institution_post(post_id: str, post: InstitutionPostUpdate, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        post_ref = db.collection("institution_posts").document(post_id)
        existing_doc = await post_ref.get()
        
        if not existing_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution post not found")
            
        institution_id = existing_doc.to_dict().get('institution_id')
        institution_ref = db.collection("institutions").document(institution_id)
        institution_doc = institution_ref.get()
        
        if not institution_doc.exists or institution_doc.to_dict().get('owner_id') != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this post.")
            
        update_data = post.model_dump(exclude_unset=True, by_alias=True)
        await post_ref.update(update_data)
        updated_doc = await post_ref.get()
        return convert_doc_to_model(updated_doc.id, updated_doc.to_dict(), InstitutionPostInDB)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update institution post: {e}")

@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_institution_post(post_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        post_ref = db.collection("institution_posts").document(post_id)
        existing_doc = await post_ref.get()
        
        if not existing_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution post not found")
            
        institution_id = existing_doc.to_dict().get('institution_id')
        institution_ref = db.collection("institutions").document(institution_id)
        institution_doc = institution_ref.get()
        
        if not institution_doc.exists or institution_doc.to_dict().get('owner_id') != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this post.")
            
        await post_ref.delete()
        return {"message": "Institution post deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete institution post: {e}")
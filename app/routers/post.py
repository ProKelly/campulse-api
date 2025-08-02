from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.models.post import InstitutionPostCreate, InstitutionPostUpdate, InstitutionPostInDB
from app.auth.firebase_auth import get_current_user_id
from app.config import db
from app.db.utils import convert_doc_to_model
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
import math

router = APIRouter(prefix="/institution_posts", tags=["Institution Posts"])

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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    
    institution_ref = db.collection("institutions").document(post.institution_id)
    institution_doc = institution_ref.get()
    
    if not institution_doc.exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Institution not found.")
    if institution_doc.to_dict().get('owner_id') != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to post for this institution.")

    try:
        post_data = post.model_dump(by_alias=True)
        post_data['published_at'] = SERVER_TIMESTAMP
        
        doc_ref = db.collection("institution_posts").document()
        doc_ref.set(post_data)
        
        created_doc = doc_ref.get()
        if not created_doc.exists:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created post.")

        return convert_doc_to_model(created_doc.id, created_doc.to_dict(), InstitutionPostInDB)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create institution post: {e}")

@router.get("/", response_model=List[InstitutionPostInDB])
async def get_all_institution_posts(limit: int = 100):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        posts = []
        query = db.collection("institution_posts").order_by("published_at", direction="DESCENDING").limit(limit)
        docs = query.stream()
        
        for doc in docs:
            posts.append(convert_doc_to_model(doc.id, doc.to_dict(), InstitutionPostInDB))
        
        return posts
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve institution posts: {e}")

@router.get("/nearby", response_model=List[InstitutionPostInDB])
async def get_nearby_institution_posts(lat: float, lon: float, radius: int = 500):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid coordinates")

    try:
        posts = []
        docs = db.collection("institution_posts").stream()

        for doc in docs:
            post_data = doc.to_dict()
            if 'map_location' not in post_data:
                # Log skipped post due to missing map_location
                print(f"Skipping post {doc.id} due to missing map_location")
                continue

            try:
                post_lat = post_data['map_location']['lat']
                post_lon = post_data['map_location']['lng']
                distance = haversine_distance(lat, lon, post_lat, post_lon)

                # Log map_location and distance for debugging
                print(f"Post {doc.id}: map_location=({post_lat}, {post_lon}), distance={distance} meters")

                if distance <= radius:
                    post_model = convert_doc_to_model(doc.id, post_data, InstitutionPostInDB)
                    setattr(post_model, 'distance', distance)  # Add distance attribute dynamically
                    posts.append(post_model)
            except KeyError as e:
                print(f"KeyError for post {doc.id}: {e}")
            except Exception as e:
                print(f"Unexpected error for post {doc.id}: {e}")

        # Sort posts by distance and limit to 50
        posts.sort(key=lambda x: x.distance)
        return posts[:50]
    except Exception as e:
        print(f"Error in get_nearby_institution_posts: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail=f"Failed to retrieve nearby institution posts: {e}")

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
from datetime import datetime, timedelta
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
import ollama  # New import for Ollama
import json, requests

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

@router.get("/ai-search", response_model=List[InstitutionPostInDB])
async def ai_search_posts(
    search_query: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius: int = 5000
):
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore not initialized.")

    try:
        # --- Step 1. Use remote Ollama daemon to extract search params ---
        prompt = f"""Analyze the user's natural language search query and extract parameters for filtering posts.

Query: {search_query}

Output ONLY the JSON object, nothing else:
{{
  "post_types": ["job", "internship", "event", "news"],
  "keywords": [],
  "categories": [],
  "time_filter": null,
  "location_type": null
}}
"""

        # Call the exposed Ollama daemon
        OLLAMA_URL = "https://api.dsmartcity.site/ollama"
        payload = {
            "model": "qwen2:0.5b",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        }

        headers = {"Content-Type": "application/json"}
        resp = requests.post(OLLAMA_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Safely extract JSON from Ollama response
        if "message" not in data or "content" not in data["message"]:
            raise HTTPException(status_code=500, detail="Invalid response from Ollama API")

        extracted = data["message"]["content"]

        # Strip any extra text and parse JSON
        start = extracted.find("{")
        end = extracted.rfind("}") + 1
        if start == -1 or end == -1:
            raise HTTPException(status_code=500, detail="Failed to parse JSON from Ollama")
        params = json.loads(extracted[start:end])

        # --- Step 2. Build Firestore Query ---
        query = db.collection("institution_posts")

        if params.get("categories"):
            query = query.where("categories", "array_contains_any", params["categories"])
        if params.get("post_types"):
            query = query.where("type_of_post", "in", params["post_types"])

        if params.get("time_filter"):
            now = datetime.now()
            tf = params["time_filter"].lower()
            if tf == "today":
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif tf == "this week":
                start_time = now - timedelta(days=now.weekday())
                start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            elif tf == "this month":
                start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                start_time = None
            if start_time:
                query = query.where("created_at", ">=", start_time)

        # --- Step 3. Fetch initial results ---
        posts = [convert_doc_to_model(doc.id, doc.to_dict(), InstitutionPostInDB) for doc in query.stream()]

        # --- Step 4. Keyword filtering ---
        keywords = params.get("keywords", [])
        if keywords:
            posts = [
                post for post in posts
                if any(
                    kw.lower() in (post.title or "").lower()
                    or kw.lower() in (post.content or "").lower()
                    or kw.lower() in " ".join(post.tags or []).lower()
                    for kw in keywords
                )
            ]

        # --- Step 5. Nearby filtering ---
        if params.get("location_type") == "nearby" and lat and lon:
            posts = [post for post in posts if hasattr(post, "map_location")]
            for post in posts:
                if post.map_location:
                    post.distance = haversine_distance(
                        lat, lon,
                        post.map_location.lat,
                        post.map_location.lng
                    )
            posts.sort(key=lambda x: getattr(x, "distance", float("inf")))
            posts = [p for p in posts if getattr(p, "distance", float("inf")) <= radius]

        return posts[:50]

    except Exception as e:
        logger.error(f"AI search failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI search failed: {e}")


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

        if category and category.lower() != 'all':
            query = query.where('categories', 'array_contains', category)

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

        query = query.order_by('created_at', direction='DESCENDING')
        query = query.limit(limit)

        posts = []
        for doc in query.stream():
            posts.append(convert_doc_to_model(doc.id, doc.to_dict(), InstitutionPostInDB))

        if sort and sort.lower() == 'popular':
            posts.sort(key=lambda x: len(x.smart_suggestions.related_posts) if hasattr(x, 'smart_suggestions') else 0, reverse=True)

        return posts

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve posts: {e}")


@router.get("/nearby", response_model=List[InstitutionPostInDB])
async def get_nearby_institution_posts(lat: float, lon: float, radius: int = 500):
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore not initialized.")

    try:
        # Calculate bounding box for geohash
        min_lat, min_lon, max_lat, max_lon = bounding_box(lat, lon, radius)
        geohash_sw = geohash2.encode(min_lat, min_lon, precision=7)  # Adjusted precision for better performance
        geohash_ne = geohash2.encode(max_lat, max_lon, precision=7)

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
        doc = post_ref.get()
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
        existing_doc = post_ref.get()

        if not existing_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution post not found")

        institution_id = existing_doc.to_dict().get('institution_id')
        institution_ref = db.collection("institutions").document(institution_id)
        institution_doc = institution_ref.get()

        if not institution_doc.exists or institution_doc.to_dict().get('owner_id') != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this post.")

        update_data = post.model_dump(exclude_unset=True, by_alias=True)
        post_ref.update(update_data)
        updated_doc = post_ref.get()
        return convert_doc_to_model(updated_doc.id, updated_doc.to_dict(), InstitutionPostInDB)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update institution post: {e}")


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_institution_post(post_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        post_ref = db.collection("institution_posts").document(post_id)
        existing_doc = post_ref.get()

        if not existing_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution post not found")

        institution_id = existing_doc.to_dict().get('institution_id')
        institution_ref = db.collection("institutions").document(institution_id)
        institution_doc = institution_ref.get()

        if not institution_doc.exists or institution_doc.to_dict().get('owner_id') != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this post.")

        post_ref.delete()
        return {"message": "Institution post deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete institution post: {e}")

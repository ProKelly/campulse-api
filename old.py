import os
import json
from datetime import datetime
from typing import List, Optional, Dict, Any, Union

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr

import firebase_admin
from firebase_admin import credentials, firestore, auth
from google.cloud.firestore import GeoPoint, FieldValue, Timestamp # Import specific types

# --- Load Environment Variables ---
load_dotenv()

# --- Initialize Firebase Admin SDK ---
try:
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
        print("Firebase initialized using GOOGLE_APPLICATION_CREDENTIALS.")
    elif os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"):
        cred_json_str = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        cred_json = json.loads(cred_json_str)
        cred = credentials.Certificate(cred_json)
        firebase_admin.initialize_app(cred)
        print("Firebase initialized using FIREBASE_SERVICE_ACCOUNT_JSON.")
    elif os.path.exists("./serviceAccountKey.json"):
        cred = credentials.Certificate("./serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        print("Firebase initialized using local serviceAccountKey.json.")
    else:
        raise Exception("Firebase credentials not found. Please set GOOGLE_APPLICATION_CREDENTIALS, FIREBASE_SERVICE_ACCOUNT_JSON, or place serviceAccountKey.json in the root.")

    db = firestore.client()
    print("Firestore client obtained.")

except Exception as e:
    print(f"Error initializing Firebase: {e}")
    db = None # Set db to None if initialization fails

# --- FastAPI App Instance ---
app = FastAPI(
    title="AfriConnect Backend",
    description="API for users, POIs, institutions, posts, and news using FastAPI and Firestore.",
    version="1.0.0",
)

# --- Authentication Dependency ---
oauth2_scheme = HTTPBearer(auto_error=False)

async def get_current_user_id(
    token: HTTPAuthorizationCredentials = Depends(oauth2_scheme)
) -> str:
    if db is None: # Ensure Firebase is initialized
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Firebase is not initialized. Cannot authenticate.",
        )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        decoded_token = auth.verify_id_token(token.credentials)
        uid = decoded_token['uid']
        return uid
    except Exception as e:
        print(f"Firebase authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

# --- Custom Pydantic Types for Firestore Specifics ---

class GeoPointModel(BaseModel):
    latitude: float = Field(..., alias='_latitude')
    longitude: float = Field(..., alias='_longitude')

    @classmethod
    def __get_validators__(cls):
        yield cls.validate_geopoint

    @classmethod
    def validate_geopoint(cls, v):
        if isinstance(v, GeoPoint):
            # When reading from Firestore
            return cls(latitude=v.latitude, longitude=v.longitude)
        elif isinstance(v, dict) and 'latitude' in v and 'longitude' in v:
            # When receiving from request body (or directly from dict for testing)
            return cls(latitude=v['latitude'], longitude=v['longitude'])
        raise ValueError('Invalid GeoPoint format')

    def to_firestore_geopoint(self) -> GeoPoint:
        # Convert to Firestore GeoPoint for writing to DB
        return GeoPoint(self.latitude, self.longitude)
    
    # Custom serializer for Pydantic v2 to handle the alias correctly
    def model_dump(self, *args, **kwargs):
        data = super().model_dump(*args, **kwargs)
        # Remove original keys and add aliased keys for Firestore compatibility
        data['_latitude'] = data.pop('latitude')
        data['_longitude'] = data.pop('longitude')
        return data

# --- Base Model for common fields in DB responses ---
class DocumentInDB(BaseModel):
    id: str = Field(..., description="Firestore document ID")
    created_at: Optional[datetime] = None # Will be Timestamp from Firestore

    @classmethod
    def convert_timestamp_to_datetime(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Converts Firestore Timestamp objects to Python datetime objects."""
        if 'created_at' in data and isinstance(data['created_at'], Timestamp):
            data['created_at'] = data['created_at'].astimezone(datetime.now().astimezone().tzinfo) # Convert to local timezone
        if 'published_at' in data and isinstance(data['published_at'], Timestamp): # For Posts/News
            data['published_at'] = data['published_at'].astimezone(datetime.now().astimezone().tzinfo)
        # Handle nested timestamps in location_history for User
        if 'location_history' in data and isinstance(data['location_history'], list):
            for entry in data['location_history']:
                if 'timestamp' in entry and isinstance(entry['timestamp'], Timestamp):
                    entry['timestamp'] = entry['timestamp'].astimezone(datetime.now().astimezone().tzinfo)
        return data

# --- Pydantic Models for each Collection ---

# User Collection
class NotificationSettings(BaseModel):
    new_posts: bool = True
    proximity_alerts: bool = False
    ai_recommendations: bool = True

class PrivacySettings(BaseModel):
    share_location_history: bool = False

class LocationHistoryEntry(BaseModel):
    location: GeoPointModel
    timestamp: datetime = Field(default_factory=datetime.now) # For new entries, use current time

class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    role: str = "user"
    preferred_categories: List[str] = []
    language: str = "en"
    location: GeoPointModel # Initial location
    location_history: List[LocationHistoryEntry] = []
    notification_settings: NotificationSettings = NotificationSettings()
    privacy: PrivacySettings = PrivacySettings()
    profile_image_url: Optional[str] = None
    bio: Optional[str] = None
    followers: List[str] = [] # List of user_ids
    following: List[str] = [] # List of user_ids

class UserUpdate(UserCreate):
    # All fields are optional for update
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

class UserInDB(DocumentInDB, UserCreate):
    # No extra fields, just inherits from UserCreate and DocumentInDB
    pass

# POI Collection
class POICreate(BaseModel):
    name: str
    description: Optional[str] = None
    lat: float # For client use, though GeoPoint is stored in Firestore
    lng: float # For client use
    location: GeoPointModel # Actual GeoPoint
    radius_m: int
    type: str
    tags: List[str] = []
    cover_image_url: Optional[str] = None

class POIUpdate(POICreate):
    name: Optional[str] = None
    description: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    location: Optional[GeoPointModel] = None
    radius_m: Optional[int] = None
    type: Optional[str] = None
    tags: Optional[List[str]] = None
    cover_image_url: Optional[str] = None

class POIInDB(DocumentInDB, POICreate):
    pass

# Institution Collection
class InstitutionCreate(BaseModel):
    owner_id: str # User ID of the owner
    name: str
    category: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    lat: float
    lng: float
    location: GeoPointModel
    poi_id: Optional[str] = None # Associated POI
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

class InstitutionInDB(DocumentInDB, InstitutionCreate):
    pass

# InstitutionPost Collection
class MapLocation(BaseModel):
    label: str
    lat: float
    lng: float

class SmartSuggestions(BaseModel):
    suggested_tags: List[str] = []
    related_posts: List[str] = [] # List of post IDs

class InstitutionPostCreate(BaseModel):
    institution_id: str
    title: str
    content: str
    type_of_post: str # e.g., "job", "news", "event"
    tags: List[str] = []
    sentiment: Optional[str] = None # e.g., "positive", "negative", "neutral"
    poi_id: Optional[str] = None
    categories: List[str] = []
    image_url: Optional[str] = None
    visibility: str = "public" # e.g., "public", "nearby_only", "followers"
    map_location: Optional[MapLocation] = None
    smart_suggestions: SmartSuggestions = SmartSuggestions()
    summary: Optional[str] = None

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

class InstitutionPostInDB(DocumentInDB, InstitutionPostCreate):
    published_at: Optional[datetime] = None # Firestore will set this

# News Collection
class NewsLocation(BaseModel): # Separate for News as schema is slightly different
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

class NewsInDB(DocumentInDB, NewsCreate):
    timestamp: Optional[datetime] = None # Firestore will set this


# --- Utility Function to Handle Firestore Data for Responses ---
def convert_doc_to_model(doc_id: str, doc_data: Dict[str, Any], Model: BaseModel) -> BaseModel:
    """Converts a Firestore document snapshot to a Pydantic model."""
    data = {"id": doc_id, **doc_data}
    
    # Manually convert GeoPoint instances to GeoPointModel for response
    for key, value in data.items():
        if isinstance(value, GeoPoint):
            data[key] = {'_latitude': value.latitude, '_longitude': value.longitude}
        elif isinstance(value, dict):
            # Recursively handle nested dictionaries (e.g., location_history)
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, GeoPoint):
                    value[sub_key] = {'_latitude': sub_value.latitude, '_longitude': sub_value.longitude}
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    for sub_key, sub_value in item.items():
                        if isinstance(sub_value, GeoPoint):
                            item[sub_key] = {'_latitude': sub_value.latitude, '_longitude': sub_value.longitude}

    # Convert Firestore Timestamps to Python datetime objects for Pydantic validation
    data = DocumentInDB.convert_timestamp_to_datetime(data)
    
    # Pydantic v2's model_validate can handle dicts directly
    return Model.model_validate(data)


# --- API Routes ---

@app.get("/", summary="Root endpoint", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the AfriConnect API!"}

# --- Users Endpoints ---
@app.post("/users/", response_model=UserInDB, status_code=status.HTTP_201_CREATED, summary="Create a new user", tags=["Users"])
async def create_user(user: UserCreate, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        user_data = user.model_dump(by_alias=True) # Use by_alias=True to dump GeoPointModel correctly
        
        # Convert GeoPointModel to firestore.GeoPoint
        if 'location' in user_data:
            user_data['location'] = user.location.to_firestore_geopoint()
        if 'location_history' in user_data:
            user_data['location_history'] = [
                {"location": entry.location.to_firestore_geopoint(), "timestamp": entry.timestamp}
                for entry in user.location_history
            ]

        # Use the provided user_id from auth as the document ID for consistency
        user_ref = db.collection("users").document(current_user_id)
        if (await user_ref.get()).exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with this ID already exists.")

        user_data['created_at'] = FieldValue.server_timestamp()
        await user_ref.set(user_data)
        
        # Return the created user data with the correct ID and converted timestamp
        # Fetch the document back to ensure we get the server-generated timestamp and correct GeoPoint format
        created_doc = await user_ref.get()
        return convert_doc_to_model(created_doc.id, created_doc.to_dict(), UserInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create user: {e}")

@app.get("/users/{user_id}", response_model=UserInDB, summary="Get a user by ID", tags=["Users"])
async def get_user(user_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        user_ref = db.collection("users").document(user_id)
        doc = await user_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return convert_doc_to_model(doc.id, doc.to_dict(), UserInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve user: {e}")

@app.put("/users/{user_id}", response_model=UserInDB, summary="Update a user by ID", tags=["Users"])
async def update_user(user_id: str, user: UserUpdate, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    # Authorization: Ensure current_user_id matches user_id for self-update or has admin role
    if user_id != current_user_id:
        # In a real app, you'd check user role for admin access here
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this user.")
    try:
        user_ref = db.collection("users").document(user_id)
        if not (await user_ref.get()).exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        update_data = user.model_dump(exclude_unset=True, by_alias=True) # Only update fields that are set

        if 'location' in update_data and update_data['location'] is not None:
            update_data['location'] = user.location.to_firestore_geopoint()
        if 'location_history' in update_data and update_data['location_history'] is not None:
             update_data['location_history'] = [
                {"location": entry.location.to_firestore_geopoint(), "timestamp": entry.timestamp}
                for entry in user.location_history
            ]

        await user_ref.update(update_data)
        updated_doc = await user_ref.get() # Get updated document to return full data
        return convert_doc_to_model(updated_doc.id, updated_doc.to_dict(), UserInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update user: {e}")

@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a user by ID", tags=["Users"])
async def delete_user(user_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    # Authorization: Ensure current_user_id matches user_id or has admin role
    if user_id != current_user_id:
        # In a real app, you'd check user role for admin access here
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this user.")
    try:
        user_ref = db.collection("users").document(user_id)
        if not (await user_ref.get()).exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        await user_ref.delete()
        return {"message": "User deleted successfully"}
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete user: {e}")

# --- POI Endpoints ---
@app.post("/pois/", response_model=POIInDB, status_code=status.HTTP_201_CREATED, summary="Create a new POI", tags=["POIs"])
async def create_poi(poi: POICreate, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        poi_data = poi.model_dump(by_alias=True)
        poi_data['location'] = poi.location.to_firestore_geopoint()
        
        # Auto-generate ID for POIs
        doc_ref = db.collection("pois").document()
        await doc_ref.set(poi_data)
        
        created_doc = await doc_ref.get()
        return convert_doc_to_model(created_doc.id, created_doc.to_dict(), POIInDB)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create POI: {e}")

@app.get("/pois/", response_model=List[POIInDB], summary="Get all POIs", tags=["POIs"])
async def get_all_pois():
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        pois = []
        docs = db.collection("pois").stream()
        async for doc in docs: # Use async for
            pois.append(convert_doc_to_model(doc.id, doc.to_dict(), POIInDB))
        return pois
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve POIs: {e}")

@app.get("/pois/{poi_id}", response_model=POIInDB, summary="Get a POI by ID", tags=["POIs"])
async def get_poi(poi_id: str):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        poi_ref = db.collection("pois").document(poi_id)
        doc = await poi_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POI not found")
        return convert_doc_to_model(doc.id, doc.to_dict(), POIInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve POI: {e}")

@app.put("/pois/{poi_id}", response_model=POIInDB, summary="Update a POI by ID", tags=["POIs"])
async def update_poi(poi_id: str, poi: POIUpdate, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    # Example: Only allow admins or specific users to update POIs
    # You'd typically check current_user_id against an admin role or other permission
    try:
        poi_ref = db.collection("pois").document(poi_id)
        if not (await poi_ref.get()).exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POI not found")
        
        update_data = poi.model_dump(exclude_unset=True, by_alias=True)
        if 'location' in update_data and update_data['location'] is not None:
            update_data['location'] = poi.location.to_firestore_geopoint()

        await poi_ref.update(update_data)
        updated_doc = await poi_ref.get()
        return convert_doc_to_model(updated_doc.id, updated_doc.to_dict(), POIInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update POI: {e}")

@app.delete("/pois/{poi_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a POI by ID", tags=["POIs"])
async def delete_poi(poi_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    # Example: Only allow admins to delete POIs
    try:
        poi_ref = db.collection("pois").document(poi_id)
        if not (await poi_ref.get()).exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POI not found")
        await poi_ref.delete()
        return {"message": "POI deleted successfully"}
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete POI: {e}")

# --- Institution Endpoints ---
@app.post("/institutions/", response_model=InstitutionInDB, status_code=status.HTTP_201_CREATED, summary="Create a new institution", tags=["Institutions"])
async def create_institution(institution: InstitutionCreate, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    # Ensure the owner_id matches the authenticated user's ID
    if institution.owner_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only create institutions owned by yourself.")
    try:
        institution_data = institution.model_dump(by_alias=True)
        institution_data['location'] = institution.location.to_firestore_geopoint()
        institution_data['created_at'] = FieldValue.server_timestamp()
        
        doc_ref = db.collection("institutions").document()
        await doc_ref.set(institution_data)
        
        created_doc = await doc_ref.get()
        return convert_doc_to_model(created_doc.id, created_doc.to_dict(), InstitutionInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create institution: {e}")

@app.get("/institutions/", response_model=List[InstitutionInDB], summary="Get all institutions", tags=["Institutions"])
async def get_all_institutions():
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        institutions = []
        docs = db.collection("institutions").stream()
        async for doc in docs:
            institutions.append(convert_doc_to_model(doc.id, doc.to_dict(), InstitutionInDB))
        return institutions
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve institutions: {e}")

@app.get("/institutions/{institution_id}", response_model=InstitutionInDB, summary="Get an institution by ID", tags=["Institutions"])
async def get_institution(institution_id: str):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        institution_ref = db.collection("institutions").document(institution_id)
        doc = await institution_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
        return convert_doc_to_model(doc.id, doc.to_dict(), InstitutionInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve institution: {e}")

@app.put("/institutions/{institution_id}", response_model=InstitutionInDB, summary="Update an institution by ID", tags=["Institutions"])
async def update_institution(institution_id: str, institution: InstitutionUpdate, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        institution_ref = db.collection("institutions").document(institution_id)
        existing_doc = await institution_ref.get()
        if not existing_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
        
        # Authorization: Only the owner can update
        if existing_doc.to_dict().get('owner_id') != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this institution.")

        update_data = institution.model_dump(exclude_unset=True, by_alias=True)
        if 'location' in update_data and update_data['location'] is not None:
            update_data['location'] = institution.location.to_firestore_geopoint()

        await institution_ref.update(update_data)
        updated_doc = await institution_ref.get()
        return convert_doc_to_model(updated_doc.id, updated_doc.to_dict(), InstitutionInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update institution: {e}")

@app.delete("/institutions/{institution_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an institution by ID", tags=["Institutions"])
async def delete_institution(institution_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        institution_ref = db.collection("institutions").document(institution_id)
        existing_doc = await institution_ref.get()
        if not existing_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")

        # Authorization: Only the owner can delete
        if existing_doc.to_dict().get('owner_id') != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this institution.")

        await institution_ref.delete()
        return {"message": "Institution deleted successfully"}
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete institution: {e}")

# --- Institution Posts Endpoints ---
@app.post("/institution_posts/", response_model=InstitutionPostInDB, status_code=status.HTTP_201_CREATED, summary="Create a new institution post", tags=["Institution Posts"])
async def create_institution_post(post: InstitutionPostCreate, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    # Verify institution owner
    institution_ref = db.collection("institutions").document(post.institution_id)
    institution_doc = await institution_ref.get()
    if not institution_doc.exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Institution not found.")
    if institution_doc.to_dict().get('owner_id') != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to post for this institution.")

    try:
        post_data = post.model_dump(by_alias=True)
        post_data['published_at'] = FieldValue.server_timestamp()
        
        doc_ref = db.collection("institution_posts").document() # Firestore auto-generates ID
        await doc_ref.set(post_data)
        
        created_doc = await doc_ref.get()
        return convert_doc_to_model(created_doc.id, created_doc.to_dict(), InstitutionPostInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create institution post: {e}")

@app.get("/institution_posts/", response_model=List[InstitutionPostInDB], summary="Get all institution posts", tags=["Institution Posts"])
async def get_all_institution_posts():
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        posts = []
        docs = db.collection("institution_posts").stream()
        async for doc in docs:
            posts.append(convert_doc_to_model(doc.id, doc.to_dict(), InstitutionPostInDB))
        return posts
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve institution posts: {e}")

@app.get("/institution_posts/{post_id}", response_model=InstitutionPostInDB, summary="Get an institution post by ID", tags=["Institution Posts"])
async def get_institution_post(post_id: str):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        post_ref = db.collection("institution_posts").document(post_id)
        doc = await post_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution post not found")
        return convert_doc_to_model(doc.id, doc.to_dict(), InstitutionPostInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve institution post: {e}")

@app.put("/institution_posts/{post_id}", response_model=InstitutionPostInDB, summary="Update an institution post by ID", tags=["Institution Posts"])
async def update_institution_post(post_id: str, post: InstitutionPostUpdate, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        post_ref = db.collection("institution_posts").document(post_id)
        existing_doc = await post_ref.get()
        if not existing_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution post not found")

        # Authorization: Only the owner of the institution can update its posts
        institution_id_of_post = existing_doc.to_dict().get('institution_id')
        institution_ref = db.collection("institutions").document(institution_id_of_post)
        institution_doc = await institution_ref.get()
        if not institution_doc.exists or institution_doc.to_dict().get('owner_id') != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this post.")

        update_data = post.model_dump(exclude_unset=True, by_alias=True)
        await post_ref.update(update_data)
        updated_doc = await post_ref.get()
        return convert_doc_to_model(updated_doc.id, updated_doc.to_dict(), InstitutionPostInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update institution post: {e}")

@app.delete("/institution_posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an institution post by ID", tags=["Institution Posts"])
async def delete_institution_post(post_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        post_ref = db.collection("institution_posts").document(post_id)
        existing_doc = await post_ref.get()
        if not existing_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution post not found")

        # Authorization: Only the owner of the institution can delete its posts
        institution_id_of_post = existing_doc.to_dict().get('institution_id')
        institution_ref = db.collection("institutions").document(institution_id_of_post)
        institution_doc = await institution_ref.get()
        if not institution_doc.exists or institution_doc.to_dict().get('owner_id') != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this post.")

        await post_ref.delete()
        return {"message": "Institution post deleted successfully"}
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete institution post: {e}")

# --- News Endpoints ---
@app.post("/news/", response_model=NewsInDB, status_code=status.HTTP_201_CREATED, summary="Create a new news entry", tags=["News"])
async def create_news(news: NewsCreate, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    # News creation might be restricted to specific roles (e.g., admin)
    # For now, just requires any authenticated user.
    try:
        news_data = news.model_dump()
        news_data['timestamp'] = FieldValue.server_timestamp()
        
        doc_ref = db.collection("news").document() # Firestore auto-generates ID
        await doc_ref.set(news_data)
        
        created_doc = await doc_ref.get()
        return convert_doc_to_model(created_doc.id, created_doc.to_dict(), NewsInDB)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create news: {e}")

@app.get("/news/", response_model=List[NewsInDB], summary="Get all news entries", tags=["News"])
async def get_all_news():
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        news_entries = []
        docs = db.collection("news").stream()
        async for doc in docs:
            news_entries.append(convert_doc_to_model(doc.id, doc.to_dict(), NewsInDB))
        return news_entries
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve news: {e}")

@app.get("/news/{news_id}", response_model=NewsInDB, summary="Get a news entry by ID", tags=["News"])
async def get_news(news_id: str):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        news_ref = db.collection("news").document(news_id)
        doc = await news_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News entry not found")
        return convert_doc_to_model(doc.id, doc.to_dict(), NewsInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve news: {e}")

@app.put("/news/{news_id}", response_model=NewsInDB, summary="Update a news entry by ID", tags=["News"])
async def update_news(news_id: str, news: NewsUpdate, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    # News update might be restricted to specific roles (e.g., admin)
    try:
        news_ref = db.collection("news").document(news_id)
        if not (await news_ref.get()).exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News entry not found")

        update_data = news.model_dump(exclude_unset=True)
        await news_ref.update(update_data)
        updated_doc = await news_ref.get()
        return convert_doc_to_model(updated_doc.id, updated_doc.to_dict(), NewsInDB)
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update news: {e}")

@app.delete("/news/{news_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a news entry by ID", tags=["News"])
async def delete_news(news_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    # News deletion might be restricted to specific roles (e.g., admin)
    try:
        news_ref = db.collection("news").document(news_id)
        if not (await news_ref.get()).exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News entry not found")
        await news_ref.delete()
        return {"message": "News entry deleted successfully"}
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete news: {e}")
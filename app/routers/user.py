from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.models.user import UserCreate, UserUpdate, UserInDB
from app.auth.firebase_auth import get_current_user_id
from app.config import db
from app.db.utils import convert_doc_to_model
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta

router = APIRouter(prefix="/users", tags=["Users"])

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Secret key for JWT (replace with a secure key in production)
SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def generate_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": user_id, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@router.post("/", response_model=UserInDB, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        # print("[DEBUG] Received user:", user)
        user_data = user.model_dump(by_alias=True)
        # print("[DEBUG] user_data after model_dump:", user_data)
        if 'location' in user_data:
            # print("[DEBUG] Location before conversion:", user.location)
            user_data['location'] = user.location.to_firestore_geopoint()
            # print("[DEBUG] Location after conversion:", user_data['location'])
        if 'location_history' in user_data:
            user_data['location_history'] = [
                {"location": entry.location.to_firestore_geopoint(), "timestamp": entry.timestamp}
                for entry in user.location_history
            ]
        user_ref = db.collection("users").document(current_user_id)
        doc = user_ref.get()
        if doc.exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with this ID already exists.")
        user_data['created_at'] = SERVER_TIMESTAMP
        user_ref.set(user_data)
        created_doc = user_ref.get()
        return convert_doc_to_model(created_doc.id, created_doc.to_dict(), UserInDB)
    except HTTPException as he:
        raise he
    except Exception as e:
        # print("[ERROR] Exception in create_user:", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create user: {e}")

@router.get("/{user_id}", response_model=UserInDB)
async def get_user(user_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        # print(f"[DEBUG] Fetching user profile for user_id: {user_id}")
        user_ref = db.collection("users").document(user_id)
        doc = user_ref.get()
        # print(f"[DEBUG] Document exists: {doc.exists}")
        if not doc.exists:
            # print("[DEBUG] User not found in Firestore.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        doc_data = doc.to_dict()
        # print(f"[DEBUG] Document data: {doc_data}")
        result = convert_doc_to_model(doc.id, doc_data, UserInDB)
        # print(f"[DEBUG] Converted user model: {result}")
        return result
    except HTTPException as he:
        # print(f"[ERROR] HTTPException in get_user: {he.detail}")
        raise he
    except Exception as e:
        # print(f"[ERROR] Exception in get_user: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve user: {e}")

@router.put("/{user_id}", response_model=UserInDB)
async def update_user(user_id: str, user: UserUpdate, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    if user_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this user.")
    try:
        user_ref = db.collection("users").document(user_id)
        if not (await user_ref.get()).exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        update_data = user.model_dump(exclude_unset=True, by_alias=True)
        if 'location' in update_data and update_data['location'] is not None:
            update_data['location'] = user.location.to_firestore_geopoint()
        if 'location_history' in update_data and update_data['location_history'] is not None:
            update_data['location_history'] = [
                {"location": entry.location.to_firestore_geopoint(), "timestamp": entry.timestamp}
                for entry in user.location_history
            ]
        await user_ref.update(update_data)
        updated_doc = await user_ref.get()
        return convert_doc_to_model(updated_doc.id, updated_doc.to_dict(), UserInDB)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update user: {e}")

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    if user_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this user.")
    try:
        user_ref = db.collection("users").document(user_id)
        if not (await user_ref.get()).exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        await user_ref.delete()
        return {"message": "User deleted successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete user: {e}")

@router.post("/login", response_model=dict, status_code=status.HTTP_200_OK)
async def login_user(email: str, password: str):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        # Query Firestore for the user with the given email
        users_ref = db.collection("users").where("email", "==", email)
        docs = await users_ref.get()
        if not docs:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user_doc = docs[0]
        user_data = user_doc.to_dict()

        # Verify the password (assuming passwords are hashed and stored securely)
        if not verify_password(password, user_data.get("password")):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # Generate a token (e.g., Firebase ID token or JWT)
        token = generate_token(user_data["id"])

        return {"token": token, "user_id": user_data["id"]}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to login user: {e}")

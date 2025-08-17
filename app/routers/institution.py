from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.models.institution import InstitutionCreate, InstitutionUpdate, InstitutionInDB
from app.auth.firebase_auth import get_current_user_id
from app.config import db
from app.db.utils import convert_doc_to_model
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
import logging

# Configure logging
logger = logging.getLogger("institution_router")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

router = APIRouter(prefix="/institutions", tags=["Institutions"])


@router.post("/", response_model=InstitutionInDB, status_code=status.HTTP_201_CREATED)
async def create_institution(institution: InstitutionCreate, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    if institution.owner_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only create institutions owned by yourself.")
    try:
        institution_data = institution.model_dump(by_alias=True)
        institution_data['location'] = institution.location.to_firestore_geopoint()
        institution_data['created_at'] = SERVER_TIMESTAMP

        doc_ref = db.collection("institutions").document()
        doc_ref.set(institution_data)  # synchronous
        created_doc = doc_ref.get()  # synchronous

        return convert_doc_to_model(created_doc.id, created_doc.to_dict(), InstitutionInDB)
    except HTTPException as he:
        print("HTTPException occurred: %s", he.detail)
        raise he
    except Exception as e:
        print("Unexpected error occurred: %s", str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create institution: {e}")


@router.get("/", response_model=List[InstitutionInDB])
async def get_all_institutions():
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        institutions = []
        docs = db.collection("institutions").stream()  # synchronous
        for doc in docs:
            institutions.append(convert_doc_to_model(doc.id, doc.to_dict(), InstitutionInDB))
        return institutions
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve institutions: {e}")


@router.get("/{institution_id}", response_model=InstitutionInDB)
async def get_institution(institution_id: str):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        institution_ref = db.collection("institutions").document(institution_id)
        doc = institution_ref.get()  # synchronous
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
        return convert_doc_to_model(doc.id, doc.to_dict(), InstitutionInDB)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve institution: {e}")


@router.put("/{institution_id}", response_model=InstitutionInDB)
async def update_institution(institution_id: str, institution: InstitutionUpdate, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        institution_ref = db.collection("institutions").document(institution_id)
        existing_doc = institution_ref.get()  # synchronous
        if not existing_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
        if existing_doc.to_dict().get('owner_id') != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this institution.")

        update_data = institution.model_dump(exclude_unset=True, by_alias=True)
        if 'location' in update_data and update_data['location'] is not None:
            update_data['location'] = institution.location.to_firestore_geopoint()

        institution_ref.update(update_data)  # synchronous
        updated_doc = institution_ref.get()  # synchronous

        return convert_doc_to_model(updated_doc.id, updated_doc.to_dict(), InstitutionInDB)
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update institution: {e}")


@router.delete("/{institution_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_institution(institution_id: str, current_user_id: str = Depends(get_current_user_id)):
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized.")
    try:
        institution_ref = db.collection("institutions").document(institution_id)
        existing_doc = institution_ref.get()  # synchronous
        if not existing_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")
        if existing_doc.to_dict().get('owner_id') != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this institution.")

        institution_ref.delete()  # synchronous
        return {"message": "Institution deleted successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete institution: {e}")



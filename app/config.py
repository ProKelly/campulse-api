# app/config.py
import os, json
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

load_dotenv()

def init_firebase():
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        cred = credentials.ApplicationDefault()
    elif os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"):
        cred = credentials.Certificate(json.loads(os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")))
    elif os.path.exists("./serviceAccountKey.json"):
        cred = credentials.Certificate("./serviceAccountKey.json")
    else:
        raise RuntimeError("Firebase credentials not found.")
    
    firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_firebase()

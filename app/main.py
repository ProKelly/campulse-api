# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import user, poi, institution, post, news
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(
    title="Campulse Backend",
    description="API backend for Campulse #dsmartcity",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dsmartcity.site",
        "https://www.dsmartcity.site",
        "http://localhost:5173",
        "https://api.dsmartcity.site",
        ],
    
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(user.router)
app.include_router(poi.router)
app.include_router(institution.router)
app.include_router(post.router)
app.include_router(news.router)

@app.get("/")
async def root():
    return {"message": "Welcome to Campulse API, Explore your city's opportunities"}

# app/main.py
from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from .routers import user, poi, institution, post, news
from dotenv import load_dotenv
import os, httpx

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

# OLLAMA_URL = "http://127.0.0.1:11434"

# @app.api_route("/ollama/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
# async def proxy_ollama(path: str, request: Request):
#     async with httpx.AsyncClient() as client:
#         url = f"{OLLAMA_URL}/{path}"
#         headers = dict(request.headers)
#         body = await request.body()
#         resp = await client.request(request.method, url, headers=headers, content=body)
#         return Response(
#             content=resp.content,
#             status_code=resp.status_code,
#             headers=resp.headers
#         )

@app.get("/")
async def root():
    return {"message": "Welcome to Campulse API, Explore your city's opportunities"}

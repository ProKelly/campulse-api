import os
import httpx
from typing import List
from app.models.news import NewsItem

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
NEWSAPI_URL = "https://newsapi.org/v2/top-headlines"

async def fetch_newsapi_news(query: str = "", page: int = 1, page_size: int = 20) -> List[NewsItem]:
    headers = {"Authorization": NEWSAPI_KEY} if NEWSAPI_KEY else {}
    params = {
        "q": query or "Cameroon",
        "page": page,
        "pageSize": page_size,
        "language": "en",
        "country": "cm",  # Cameroon country code
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(NEWSAPI_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

    news_items = []
    for article in data.get("articles", []):
        news_items.append(
            NewsItem(
                id=article.get("url"),
                title=article.get("title"),
                description=article.get("description"),
                url=article.get("url"),
                source=article.get("source", {}).get("name"),
                image=article.get("urlToImage"),
                time=article.get("publishedAt"),
                type_of_post="news",
            )
        )
    return news_items


SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
SERPAPI_URL = "https://serpapi.com/search.json"

async def fetch_serpapi_news(query: str = "Cameroon", num: int = 20) -> List[NewsItem]:
    if not SERPAPI_API_KEY:
        return []
    params = {
        "engine": "google_news",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "hl": "en",
        "gl": "cm",  # Geo-location Cameroon
        "num": num,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(SERPAPI_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    news_items = []
    news_results = data.get("news_results", [])
    for item in news_results:
        news_items.append(
            NewsItem(
                id=item.get("link"),
                title=item.get("title"),
                description=item.get("snippet"),
                url=item.get("link"),
                source=item.get("source"),
                image=item.get("thumbnail"),
                time=item.get("date"),
                type_of_post="news",
            )
        )
    return news_items


SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SERPER_URL = "https://google.serper.dev/news"

HEADERS = {
    "X-API-KEY": SERPER_API_KEY
} if SERPER_API_KEY else {}

async def fetch_serper_news(query: str = "Cameroon", num: int = 20) -> List[NewsItem]:
    if not SERPER_API_KEY:
        return []
    params = {
        "q": query,
        "hl": "en",
        "gl": "cm",
        "num": num
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(SERPER_URL, json=params, headers=HEADERS)
        response.raise_for_status()
        data = response.json()

    news_items = []
    for item in data.get("news", []):
        news_items.append(
            NewsItem(
                id=item.get("link"),
                title=item.get("title"),
                description=item.get("description"),
                url=item.get("link"),
                source=item.get("source"),
                image=item.get("thumbnail"),
                time=item.get("date"),
                type_of_post="news",
            )
        )
    return news_items

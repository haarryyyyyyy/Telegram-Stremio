import secrets
import aiohttp
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from app.core.config import settings
from app.dashboard.html import DASHBOARD_HTML

dashboard_router = APIRouter(tags=["Admin Dashboard"])


@dashboard_router.get("", response_class=HTMLResponse)
@dashboard_router.get("/", response_class=HTMLResponse)
async def dashboard_page():
    return HTMLResponse(content=DASHBOARD_HTML)


class MatchRequest(BaseModel):
    unmatched_id: str
    tmdb_id: int
    media_type: str = "movie"
    canonical_title: Optional[str] = None
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None


class ReindexRequest(BaseModel):
    channels: Optional[List[int | str]] = None
    limit: Optional[int] = None


class TokenCreateRequest(BaseModel):
    name: Optional[str] = "User"


@dashboard_router.get("/api/unmatched")
async def list_unmatched_items(request: Request):
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        return {"items": []}
    items = await storage.list_unmatched(limit=100)
    return {"items": items}


@dashboard_router.get("/api/search-tmdb")
async def search_tmdb(query: str, type: str = "movie"):
    api_key = settings.tmdb_api_key
    if not api_key:
        return {"results": []}

    endpoint = f"https://api.themoviedb.org/3/search/{type}"
    params = {"api_key": api_key, "query": query, "include_adult": "false"}

    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = []
                for item in data.get("results", [])[:10]:
                    title = item.get("title") or item.get("name")
                    release = item.get("release_date") or item.get("first_air_date") or ""
                    year = int(release.split("-")[0]) if release and release.split("-")[0].isdigit() else None
                    poster = f"https://image.tmdb.org/t/p/w200{item['poster_path']}" if item.get("poster_path") else None
                    results.append({
                        "id": item["id"],
                        "title": title,
                        "year": year,
                        "poster": poster,
                        "overview": item.get("overview", "")[:150],
                        "media_type": type,
                    })
                return {"results": results}
    return {"results": []}


@dashboard_router.post("/api/match")
async def manual_match(payload: MatchRequest, request: Request):
    pipeline = getattr(request.app.state, "pipeline", None)
    storage = getattr(request.app.state, "storage", None)

    title = payload.canonical_title
    year = payload.year

    # If title wasn't passed directly, resolve details from TMDB
    if not title and settings.tmdb_api_key:
        endpoint = f"https://api.themoviedb.org/3/{payload.media_type}/{payload.tmdb_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, params={"api_key": settings.tmdb_api_key}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    title = data.get("title") or data.get("name")
                    release = data.get("release_date") or data.get("first_air_date") or ""
                    if release and release.split("-")[0].isdigit():
                        year = int(release.split("-")[0])

    if not title:
        title = f"TMDB-{payload.tmdb_id}"

    success = False
    if pipeline:
        success = await pipeline.resolve_unmatched(
            unmatched_id=payload.unmatched_id,
            tmdb_id=payload.tmdb_id,
            canonical_title=title,
            year=year,
            media_type=payload.media_type,
            season=payload.season,
            episode=payload.episode,
        )
    elif storage and hasattr(storage, "manual_match_item"):
        res = await storage.manual_match_item(
            unmatched_id=payload.unmatched_id,
            tmdb_id=payload.tmdb_id,
            media_type=payload.media_type,
            season=payload.season,
            episode=payload.episode,
        )
        return {"status": "matched", "record": res}

    if not success:
        raise HTTPException(status_code=400, detail="Failed to resolve unmatched item")

    return {
        "status": "matched",
        "record": {
            "tmdb_id": payload.tmdb_id,
            "title": title,
            "year": year,
            "media_type": payload.media_type,
        },
    }


@dashboard_router.post("/api/reindex")
async def trigger_reindex(payload: ReindexRequest, request: Request):
    reindexer = getattr(request.app.state, "reindexer", None)
    if not reindexer:
        raise HTTPException(status_code=500, detail="Reindexer not configured")

    channels = payload.channels or settings.telegram_channels
    if not channels:
        raise HTTPException(status_code=400, detail="No channels specified to reindex")

    started = reindexer.start_reindex(channels=channels, limit=payload.limit)
    return {"started": started, "channels": channels}


@dashboard_router.get("/api/reindex/status")
async def reindex_status(request: Request):
    reindexer = getattr(request.app.state, "reindexer", None)
    if not reindexer:
        return {"status": "disabled"}
    return reindexer.get_progress()


@dashboard_router.get("/api/stats")
async def get_stats(request: Request):
    db = getattr(request.app.state, "db", None)
    if not db:
        return {"total_media": 0, "unmatched": 0}

    total_media = await db.media.count_documents({})
    movies = await db.media.count_documents({"media_type": "movie"})
    series = await db.media.count_documents({"media_type": "tv"})
    unmatched = await db.unmatched_queue.count_documents({})
    tokens_count = await db.tokens.count_documents({})

    return {
        "total_media": total_media,
        "movies": movies,
        "series": series,
        "unmatched": unmatched,
        "tokens_count": tokens_count,
    }


@dashboard_router.get("/api/tokens")
async def list_tokens(request: Request):
    db = getattr(request.app.state, "db", None)
    if not db:
        return {"tokens": []}
    cursor = db.tokens.find().sort("created_at", -1)
    tokens = []
    base_url = settings.base_url
    async for doc in cursor:
        tok = doc["token"]
        tokens.append({
            "token": tok,
            "name": doc.get("name", "User"),
            "created_at": doc.get("created_at"),
            "manifest_url": f"{base_url}/{tok}/manifest.json",
            "stremio_install_url": f"stremio://{base_url.replace('https://', '').replace('http://', '')}/{tok}/manifest.json",
        })
    return {"tokens": tokens}


@dashboard_router.post("/api/tokens")
async def create_token(payload: TokenCreateRequest, request: Request):
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="DB not initialized")

    new_token = f"tok_{secrets.token_hex(6)}"
    doc = {
        "token": new_token,
        "name": payload.name or "User",
        "created_at": __import__("time").time(),
    }
    await db.tokens.insert_one(doc)

    base_url = settings.base_url
    return {
        "token": new_token,
        "name": doc["name"],
        "manifest_url": f"{base_url}/{new_token}/manifest.json",
        "stremio_install_url": f"stremio://{base_url.replace('https://', '').replace('http://', '')}/{new_token}/manifest.json",
    }

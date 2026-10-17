from typing import Optional
from urllib.parse import quote
from fastapi import APIRouter, Request, HTTPException, Header, Response
from fastapi.responses import JSONResponse, StreamingResponse
from app.core.config import settings
from app.stremio.catalog import CatalogManager, StremioMetaItem

stremio_router = APIRouter(tags=["Stremio"])


@stremio_router.get("/{token}/manifest.json")
async def get_manifest(token: str):
    return {
        "id": "community.telegram.stremio.v2",
        "version": "2.0.0",
        "name": "Telegram Stremio V2",
        "description": "Blazing-fast multi-bot Telegram streaming engine with dynamic 15m spotlight and smart catalogs.",
        "resources": ["catalog", "stream"],
        "types": ["movie", "series"],
        "catalogs": [
            {
                "id": "spotlight",
                "type": "movie",
                "name": "🌟 15m Spotlight",
                "extra": [
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "id": "recent",
                "type": "movie",
                "name": "🆕 Recently Added",
                "extra": [
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "id": "recommended",
                "type": "movie",
                "name": "🎬 Recommended For You",
                "extra": [
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "id": "spotlight",
                "type": "series",
                "name": "🌟 15m TV & Anime",
                "extra": [
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
            {
                "id": "recent",
                "type": "series",
                "name": "🆕 Recent TV & Anime",
                "extra": [
                    {"name": "search", "isRequired": False},
                    {"name": "skip", "isRequired": False},
                ],
            },
        ],
    }


@stremio_router.get("/{token}/catalog/{type}/{id}/search={query}.json")
async def get_catalog_search_path_handler(
    token: str,
    type: str,
    id: str,
    query: str,
    request: Request,
):
    catalog_mgr: CatalogManager = request.app.state.catalog_manager
    metas = await catalog_mgr.search_catalog(catalog_type=type, query=query)
    return {
        "metas": [
            {
                "id": m.id,
                "type": m.type,
                "name": m.name,
                "poster": m.poster,
                "year": m.year,
            }
            for m in metas
        ]
    }


@stremio_router.get("/{token}/catalog/{type}/{id}.json")
async def get_catalog_handler(
    token: str,
    type: str,
    id: str,
    request: Request,
    skip: int = 0,
    search: Optional[str] = None,
):
    catalog_mgr: CatalogManager = request.app.state.catalog_manager
    if search:
        metas = await catalog_mgr.search_catalog(catalog_type=type, query=search)
    else:
        metas = await catalog_mgr.get_catalog(
            token=token,
            catalog_type=type,
            catalog_id=id,
            skip=skip,
        )
    return {
        "metas": [
            {
                "id": m.id,
                "type": m.type,
                "name": m.name,
                "poster": m.poster,
                "year": m.year,
            }
            for m in metas
        ]
    }


@stremio_router.get("/{token}/stream/{type}/{id}.json")
async def get_stream_handler(
    token: str,
    type: str,
    id: str,
    request: Request,
):
    db = request.app.state.db
    # id format: tmdb:19169 or tmdb:19169:1:10 (for series)
    parts = id.split(":")
    if len(parts) < 2 or parts[0] != "tmdb":
        return {"streams": []}

    try:
        tmdb_id = int(parts[1])
    except ValueError:
        return {"streams": []}

    query = {"tmdb_id": tmdb_id}
    if len(parts) >= 4:
        # season:episode
        query["season"] = int(parts[2])
        query["episode"] = int(parts[3])

    cursor = db.media.find(query)
    streams = []
    base_url = settings.base_url

    async for doc in cursor:
        quality_label = doc.get("quality") or "HD"
        size_gb = round(doc.get("file_size", 0) / (1024 ** 3), 1)
        size_str = f" • {size_gb} GB" if size_gb > 0 else ""
        alias_str = f" [{doc['matched_alias']}]" if doc.get("matched_alias") and doc["matched_alias"] != doc["title"] else ""

        title = f"⚡ [{quality_label}]{alias_str}{size_str}"
        file_id = doc.get("file_id", "")
        safe_filename = quote(f"{doc['title']}_{quality_label}.mkv")
        stream_url = f"{base_url}/{token}/dl/{file_id}/{safe_filename}"

        streams.append({
            "name": f"Telegram V2 ({quality_label})",
            "title": title,
            "url": stream_url,
        })

    return {"streams": streams}


@stremio_router.get("/{token}/dl/{file_id}/{filename}")
@stremio_router.head("/{token}/dl/{file_id}/{filename}")
async def stream_video_file(
    token: str,
    file_id: str,
    filename: str,
    request: Request,
    range: Optional[str] = Header(None),
):
    mux = getattr(request.app.state, "multiplexer", None)
    db = request.app.state.db

    # Look up file record for total size
    record = await db.media.find_one({"file_id": file_id})
    file_size = record.get("file_size", 0) if record else 0

    if file_size <= 0:
        raise HTTPException(status_code=404, detail="File metadata not found")

    # Parse HTTP Range header
    start = 0
    end = file_size - 1
    if range and range.startswith("bytes="):
        range_val = range.replace("bytes=", "").strip()
        parts = range_val.split("-")
        if parts[0]:
            start = int(parts[0])
        if len(parts) > 1 and parts[1]:
            end = int(parts[1])

    if start > end or end >= file_size:
        raise HTTPException(
            status_code=416,
            detail="Range Not Satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    content_length = end - start + 1
    headers = {
        "Content-Type": "video/x-matroska",
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(content_length),
        "Accept-Ranges": "bytes",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=3600",
    }

    if request.method == "HEAD":
        return Response(status_code=206, headers=headers)

    # Use multi-bot chunk multiplexer
    chunk_stream = mux.stream_range(file_id=file_id, start=start, end=end)
    return StreamingResponse(chunk_stream, status_code=206, headers=headers)

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from app.dashboard.routes import dashboard_router


@pytest.fixture
def mock_app():
    app = FastAPI()
    app.include_router(dashboard_router, prefix="/admin")

    app.state.storage = AsyncMock()
    app.state.resolver = AsyncMock()
    app.state.reindexer = MagicMock()
    app.state.db = MagicMock()

    return app


@pytest.mark.asyncio
async def test_get_unmatched_queue(mock_app):
    mock_app.state.storage.list_unmatched.return_value = [
        {
            "id": "unmatched_1",
            "filename": "Viduthalai.Part.1.mkv",
            "parsed_title": "Viduthalai Part 1",
            "file_size": 2048000000,
        }
    ]

    transport = ASGITransport(app=mock_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin/api/unmatched")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["filename"] == "Viduthalai.Part.1.mkv"


@pytest.mark.asyncio
async def test_manual_match_unmatched_item(mock_app):
    mock_app.state.storage.manual_match_item.return_value = {
        "tmdb_id": 19169,
        "title": "Alaipayuthey",
        "status": "matched",
    }

    transport = ASGITransport(app=mock_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "unmatched_id": "unmatched_1",
            "tmdb_id": 19169,
            "media_type": "movie",
        }
        resp = await client.post("/admin/api/match", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "matched"
        assert data["record"]["tmdb_id"] == 19169
        mock_app.state.storage.manual_match_item.assert_awaited_once_with(
            unmatched_id="unmatched_1",
            tmdb_id=19169,
            media_type="movie",
            season=None,
            episode=None,
        )


@pytest.mark.asyncio
async def test_reindex_endpoints(mock_app):
    mock_app.state.reindexer.start_reindex.return_value = True
    mock_app.state.reindexer.get_progress.return_value = {
        "status": "running",
        "scanned": 42,
        "matched": 40,
        "unmatched": 2,
    }

    transport = ASGITransport(app=mock_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Trigger reindex
        start_resp = await client.post("/admin/api/reindex", json={"channels": [-10012345]})
        assert start_resp.status_code == 200
        assert start_resp.json()["started"] is True

        # Check status
        status_resp = await client.get("/admin/api/reindex/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "running"
        assert status_resp.json()["scanned"] == 42

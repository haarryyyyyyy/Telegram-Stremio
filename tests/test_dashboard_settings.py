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
    app.state.db = MagicMock()
    app.state.bot_pool = AsyncMock()
    app.state.multiplexer = MagicMock()
    app.state.resolver = MagicMock()

    return app


@pytest.mark.asyncio
async def test_get_and_update_settings(mock_app):
    mock_app.state.storage.get_settings.return_value = {
        "tmdb_api_key": "my_tmdb",
        "tvdb_api_key": "my_tvdb",
        "channels": ["@my_channel"],
    }
    mock_app.state.bot_pool.get_tokens = MagicMock(return_value=["123456:ABC"])

    transport = ASGITransport(app=mock_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Get settings
        resp = await client.get("/admin/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tmdb_api_key"] == "my_tmdb"
        assert "123456:ABC" in data["bot_tokens"]

        # 2. Save settings
        update_resp = await client.post(
            "/admin/api/settings",
            json={
                "tmdb_api_key": "new_tmdb",
                "tvdb_api_key": "new_tvdb",
                "channels": ["-100123"],
            },
        )
        assert update_resp.status_code == 200
        mock_app.state.storage.save_settings.assert_awaited_once()


@pytest.mark.asyncio
async def test_dynamic_add_and_remove_bot_endpoints(mock_app):
    mock_worker = MagicMock()
    mock_app.state.bot_pool.add_bot = AsyncMock(return_value=mock_worker)
    mock_app.state.bot_pool.remove_bot = AsyncMock(return_value=True)
    mock_app.state.bot_pool.get_workers.return_value = [mock_worker]
    mock_app.state.storage.get_settings.return_value = {"bot_tokens": []}

    transport = ASGITransport(app=mock_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Add bot
        add_resp = await client.post("/admin/api/bots", json={"token": "987654:XYZ"})
        assert add_resp.status_code == 200
        mock_app.state.bot_pool.add_bot.assert_awaited_once_with("987654:XYZ")
        mock_app.state.multiplexer.update_bots.assert_called_once()

        # Remove bot
        del_resp = await client.post("/admin/api/bots/remove", json={"token": "987654:XYZ"})
        assert del_resp.status_code == 200
        mock_app.state.bot_pool.remove_bot.assert_awaited_once_with("987654:XYZ")

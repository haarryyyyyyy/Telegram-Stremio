import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from app.stremio.routes import stremio_router
from app.stremio.catalog import CatalogManager, LibraryMediaItem


@pytest.fixture
def mock_app():
    app = FastAPI()
    app.include_router(stremio_router)

    app.state.db = MagicMock()
    mock_catalog = MagicMock(spec=CatalogManager)
    app.state.catalog_manager = mock_catalog
    return app


@pytest.mark.asyncio
async def test_manifest_supports_search(mock_app):
    transport = ASGITransport(app=mock_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/test_token/manifest.json")
        assert resp.status_code == 200
        manifest = resp.json()
        
        # Verify that movie and series catalogs declare search in extra
        movie_cats = [c for c in manifest["catalogs"] if c["type"] == "movie"]
        assert len(movie_cats) > 0
        search_extras = [
            e for c in movie_cats for e in c.get("extra", []) if e.get("name") == "search"
        ]
        assert len(search_extras) > 0, "Movie catalog must declare 'search' in extra for Nuvio search"


@pytest.mark.asyncio
async def test_search_via_path_extra_for_nuvio(mock_app):
    transport = ASGITransport(app=mock_app)
    
    mock_item = MagicMock()
    mock_item.id = "tmdb:19169"
    mock_item.type = "movie"
    mock_item.name = "Alaipayuthey"
    mock_item.poster = "http://poster.jpg"
    mock_item.year = 2000
    mock_app.state.catalog_manager.search_catalog = AsyncMock(return_value=[mock_item])

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Nuvio / Stremio path format: /{token}/catalog/{type}/{id}/search={query}.json
        resp = await client.get("/test_token/catalog/movie/spotlight/search=Alaipayuthey.json")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["metas"]) == 1
        assert data["metas"][0]["name"] == "Alaipayuthey"
        mock_app.state.catalog_manager.search_catalog.assert_awaited_once_with(
            catalog_type="movie",
            query="Alaipayuthey",
        )

import pytest
from unittest.mock import AsyncMock, patch
from app.indexer.parser import ParsedMedia
from app.indexer.resolver import MetadataResolver


@pytest.mark.asyncio
async def test_tvdb_series_classification_and_mapping():
    resolver = MetadataResolver(tmdb_api_key="mock_tmdb_key", tvdb_api_key="mock_tvdb_key")

    parsed = ParsedMedia(
        title="Breaking Bad",
        year=2008,
        media_type="series",
        season=1,
        episode=1,
        quality="1080p",
    )

    # Mock TVDB v4 login & search
    mock_tvdb_token = "mock_jwt_token"
    mock_tvdb_search_results = {
        "status": "success",
        "data": [
            {
                "tvdb_id": "81189",
                "name": "Breaking Bad",
                "year": "2008",
                "primary_type": "series",
                "image_url": "https://artworks.thetvdb.com/banners/posters/81189.jpg",
                "overview": "A high school chemistry teacher diagnosed with lung cancer...",
            }
        ],
    }

    # Mock TMDB /find/81189?external_source=tvdb_id
    mock_tmdb_find_result = {
        "tv_results": [
            {
                "id": 1396,
                "name": "Breaking Bad",
                "first_air_date": "2008-01-20",
                "poster_path": "/breaking_bad.jpg",
                "genre_ids": [18],
                "origin_country": ["US"],
                "overview": "A high school chemistry teacher...",
            }
        ]
    }

    with patch.object(resolver, "_fetch_tvdb_token", AsyncMock(return_value=mock_tvdb_token)), \
         patch.object(resolver, "_fetch_tvdb_json", AsyncMock(return_value=mock_tvdb_search_results)), \
         patch.object(resolver, "_fetch_json", AsyncMock(return_value=mock_tmdb_find_result)):

        resolved = await resolver.resolve_tvdb(parsed)

        assert resolved is not None
        assert resolved.tmdb_id == 1396
        assert resolved.canonical_title == "Breaking Bad"
        assert resolved.media_type == "series"
        assert resolved.year == 2008

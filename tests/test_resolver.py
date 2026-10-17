import pytest
from unittest.mock import AsyncMock, patch
from app.indexer.parser import ParsedMedia
from app.indexer.resolver import MetadataResolver, ResolvedMedia


@pytest.mark.asyncio
async def test_resolve_regional_alias_movie():
    resolver = MetadataResolver(api_key="mock_tmdb_key")

    mock_search_response = {
        "results": [
            {
                "id": 19169,
                "title": "Alaipayuthey",
                "original_title": "Alaipayuthey",
                "release_date": "2000-04-14",
                "genre_ids": [10749, 18],
                "poster_path": "/mock_poster.jpg",
                "overview": "A young couple marries in secret...",
            }
        ]
    }

    mock_alt_titles_response = {
        "id": 19169,
        "titles": [
            {"iso_3166_1": "IN", "title": "Sakhi", "type": "Telugu title"},
            {"iso_3166_1": "IN", "title": "Waves", "type": "English title"},
        ],
    }

    parsed = ParsedMedia(title="Sakhi", year=2000, media_type="movie")

    with patch.object(resolver, "_fetch_json", new_callable=AsyncMock) as mock_fetch:
        # First call is /search/movie, second call is /movie/{id}/alternative_titles
        mock_fetch.side_effect = [mock_search_response, mock_alt_titles_response]

        resolved = await resolver.resolve(parsed)

        assert resolved is not None
        assert isinstance(resolved, ResolvedMedia)
        assert resolved.tmdb_id == 19169
        assert resolved.canonical_title == "Alaipayuthey"
        assert resolved.year == 2000
        assert resolved.media_type == "movie"
        assert resolved.matched_alias == "Sakhi"


@pytest.mark.asyncio
async def test_resolve_anime_auto_detection():
    resolver = MetadataResolver(api_key="mock_tmdb_key")

    mock_search_response = {
        "results": [
            {
                "id": 37854,
                "name": "One Piece",
                "original_name": "ONE PIECE",
                "first_air_date": "1999-10-20",
                "genre_ids": [16, 10759, 35],
                "origin_country": ["JP"],
                "poster_path": "/one_piece.jpg",
                "overview": "Monkey D. Luffy embarks on an adventure...",
            }
        ]
    }

    mock_alt_titles_response = {"id": 37854, "results": []}

    parsed = ParsedMedia(title="One Piece", episode=1080, media_type="series")

    with patch.object(resolver, "_fetch_json", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = [mock_search_response, mock_alt_titles_response]

        resolved = await resolver.resolve(parsed)

        assert resolved is not None
        assert resolved.tmdb_id == 37854
        assert resolved.canonical_title == "One Piece"
        assert resolved.media_type == "anime"


@pytest.mark.asyncio
async def test_resolve_unmatched_returns_none():
    resolver = MetadataResolver(api_key="mock_tmdb_key")

    mock_empty_search = {"results": []}

    parsed = ParsedMedia(title="SomeRandomUnmatchedFileXYZ", year=2024, media_type="movie")

    with patch.object(resolver, "_fetch_json", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_empty_search

        resolved = await resolver.resolve(parsed)

        assert resolved is None

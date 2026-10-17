import pytest
from app.stremio.catalog import CatalogManager, StremioMetaItem, LibraryMediaItem


@pytest.fixture
def mock_library():
    # 6 mock movies in the user's library
    items = []
    for i in range(1, 7):
        items.append(
            LibraryMediaItem(
                tmdb_id=100 + i,
                title=f"Movie {i}",
                year=2020 + i,
                media_type="movie",
                poster_url=f"https://image.tmdb.org/t/p/w500/poster_{i}.jpg",
                file_id=f"tg_file_{i}",
                quality="1080p",
            )
        )
    # Add a 4K duplicate of Movie 1 to test deduplication
    items.append(
        LibraryMediaItem(
            tmdb_id=101,
            title="Movie 1",
            year=2021,
            media_type="movie",
            poster_url="https://image.tmdb.org/t/p/w500/poster_1.jpg",
            file_id="tg_file_1_4k",
            quality="4K",
        )
    )
    return items


@pytest.mark.asyncio
async def test_spotlight_catalog_rotates_every_15_minutes_and_deduplicates(mock_library):
    catalog_mgr = CatalogManager(library_provider=lambda: mock_library)

    # Window 1: Time T = 100,000s
    t1 = 100000.0
    items_window1 = await catalog_mgr.get_catalog(
        token="user_1",
        catalog_type="movie",
        catalog_id="spotlight",
        current_timestamp=t1,
    )

    # Verify deduplication: 6 unique movies despite 7 files
    assert len(items_window1) == 6
    tmdb_ids_w1 = [item.id for item in items_window1]
    assert len(set(tmdb_ids_w1)) == 6

    # Within same 15-min window (e.g. +5 minutes), ordering is stable
    items_same_window = await catalog_mgr.get_catalog(
        token="user_1",
        catalog_type="movie",
        catalog_id="spotlight",
        current_timestamp=t1 + 300.0,
    )
    assert [item.id for item in items_same_window] == tmdb_ids_w1

    # Next 15-min window (+15 minutes = +900s), spotlight rotates
    t2 = t1 + 901.0
    items_window2 = await catalog_mgr.get_catalog(
        token="user_1",
        catalog_type="movie",
        catalog_id="spotlight",
        current_timestamp=t2,
    )
    tmdb_ids_w2 = [item.id for item in items_window2]

    # Verify order has rotated to feature fresh items
    assert tmdb_ids_w1 != tmdb_ids_w2


@pytest.mark.asyncio
async def test_personalized_recommendations_catalog(mock_library):
    # Mock recommendation provider: user watched movie 1, recommends movies 4, 6, 999 (where 999 is not in library)
    def mock_recommendation_provider(token: str) -> list[int]:
        assert token == "user_special"
        return [104, 106, 999]  # TMDB IDs 104 (Movie 4), 106 (Movie 6), 999 (not in library)

    catalog_mgr = CatalogManager(
        library_provider=lambda: mock_library,
        recommendation_provider=mock_recommendation_provider,
    )

    items = await catalog_mgr.get_catalog(
        token="user_special",
        catalog_type="movie",
        catalog_id="recommended",
    )

    # Only Movie 4 and Movie 6 should be returned, in recommended order
    assert len(items) == 2
    assert items[0].id == "tmdb:104"
    assert items[0].name == "Movie 4"
    assert items[1].id == "tmdb:106"
    assert items[1].name == "Movie 6"

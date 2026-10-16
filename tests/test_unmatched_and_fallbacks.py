import asyncio
import os
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE", "mongodb://localhost:27017/db1,mongodb://localhost:27017/db2")
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from Backend.helper.pyro import extract_caption_candidates
from Backend.helper.metadata.providers.tmdb import pick_best


class TestUnmatchedAndFallbacks(unittest.TestCase):
    def test_extract_caption_candidates_single_line(self):
        caption = "🎬 Viduthalai: Part 1 (2023) [Tamil + Telugu] 1080p HQ"
        candidates = extract_caption_candidates(caption)
        self.assertTrue(len(candidates) > 0)
        self.assertTrue(any("viduthalai" in c.lower() for c in candidates))

    def test_extract_caption_candidates_multiline(self):
        caption = (
            "🔥 Leo (2023) Tamil HDRip\n"
            "Quality: 1080p FHD\n"
            "Audio: Tamil + Telugu + Hindi\n"
            "Size: 2.1 GB\n"
            "Join our channel: @telegram_movies\n"
            "https://t.me/example\n"
        )
        candidates = extract_caption_candidates(caption)
        self.assertTrue(len(candidates) > 0)
        # First candidate should be Leo 2023
        self.assertIn("Leo", candidates[0])
        # Metadata lines should have been ignored
        for c in candidates:
            self.assertFalse(c.lower().startswith("audio:"))
            self.assertFalse(c.lower().startswith("quality:"))
            self.assertFalse(c.lower().startswith("size:"))
            self.assertNotIn("telegram_movies", c)

    def test_rule1_pick_best_year_match_fallback(self):
        """When TMDB #1 search result has matching release year and plausible prefix, accept it."""
        mock_item = MagicMock()
        mock_item.title = "Viduthalai Part - 1"
        mock_item.release_date = MagicMock()
        mock_item.release_date.year = 2023
        mock_item.original_title = "Viduthalai Part 1"

        # Query is regional spelling 'Vidudhala Part 1', year 2023
        res = asyncio.run(pick_best([mock_item], "Vidudhala Part 1", 2023, "movie"))
        self.assertIsNotNone(res)
        self.assertEqual(res.title, "Viduthalai Part - 1")

    def test_rule1_pick_best_mismatch_year_rejected(self):
        """When release year does not match (diff > 1), do not accept fallback."""
        mock_item = MagicMock()
        mock_item.title = "Viduthalai Part - 1"
        mock_item.release_date = MagicMock()
        mock_item.release_date.year = 1990
        mock_item.original_title = "Viduthalai Part 1"

        res = asyncio.run(pick_best([mock_item], "Vidudhala Part 1", 2023, "movie"))
        self.assertIsNone(res)

    def test_auto_catalog_timezone_import(self):
        """Auto catalog classification must have access to timezone without NameError."""
        from Backend.helper.auto_catalog import timezone
        from datetime import datetime
        now = datetime.now(timezone.utc)
        self.assertIsNotNone(now)

    def test_one_piece_absolute_episode_and_anime_classification(self):
        """One Piece 1015 must be recognized as having episode 1015, not classified as movie."""
        from Backend.helper.metadata.parse import parse_media_name, extract_absolute_episode
        from Backend.helper.metadata.entry import _is_anime_result

        fn = "One Piece Episode 1015.mkv"
        parsed = parse_media_name(fn)
        abs_ep = extract_absolute_episode(fn, parsed)
        self.assertEqual(abs_ep, 1015)

        # Anime check with Kitsu hit
        kitsu_result = {"title": "One Piece", "kitsu_id": 12, "source": "kitsu"}
        self.assertTrue(_is_anime_result(kitsu_result, anime_channel=False))

        # Live action TV (like The Traitors) on anime channel must NOT be marked as anime
        traitors_result = {
            "title": "The Traitors",
            "genres": ["Reality"],
            "original_language": "te",
            "origin_country": ["IN"],
        }
        self.assertFalse(_is_anime_result(traitors_result, anime_channel=True))

    def test_the_traitors_telugu_title_and_variants(self):
        """The Traitors Telugu must preserve 'Telugu' in title and generate regional variants."""
        from Backend.helper.metadata.parse import parse_media_name
        from Backend.helper.metadata.common import build_query_variants

        fn = "The.Traitors.Telugu.S01E01.1080p.mkv"
        parsed = parse_media_name(fn)
        self.assertEqual(parsed["title"], "The Traitors Telugu")
        self.assertEqual(parsed["season"], 1)
        self.assertEqual(parsed["episode"], 1)

        variants = build_query_variants(parsed["title"])
        self.assertIn("The Traitors Telugu", variants)
        self.assertIn("The Traitors India", variants)
        self.assertIn("The Traitors", variants)


if __name__ == "__main__":
    unittest.main()

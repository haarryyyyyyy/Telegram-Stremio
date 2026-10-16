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


if __name__ == "__main__":
    unittest.main()

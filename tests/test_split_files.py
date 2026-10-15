import asyncio
import os
import unittest

# Ensure minimum environment and event loop for headless imports
os.environ.setdefault("DATABASE", "mongodb://localhost:27017/db1,mongodb://localhost:27017/db2")
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from Backend.helper.split_files import (
    parse_combined_episodes,
    parse_split_info,
    split_archive_ext,
    strip_part_suffix,
)
from Backend.helper.metadata.parse import (
    apply_combined_override,
    extract_absolute_episode,
    parse_media_name,
)
from Backend.helper.metadata.common import (
    build_query_variants,
    title_similarity,
)


class TestSplitFilesAndParsing(unittest.TestCase):
    def test_split_archive_detection(self):
        """Zip archive parts must be identified, while video parts must not."""
        self.assertEqual(split_archive_ext("MyMovie.zip.001"), "zip")
        self.assertEqual(split_archive_ext("Archive.part.zip.02"), "zip")
        self.assertIsNone(split_archive_ext("Movie.mkv.001"))
        self.assertIsNone(split_archive_ext("Video.mp4"))

    def test_parse_split_info(self):
        """Detect trailing numeric split suffixes and extract part numbers."""
        res = parse_split_info("Epic.Movie.2024.1080p.mkv.01")
        self.assertIsNotNone(res)
        norm_key, part_num = res
        self.assertEqual(norm_key, "epic.movie.2024.1080p.mkv")
        self.assertEqual(part_num, 1)

    def test_strip_part_suffix(self):
        """Strip trailing split part suffix to recover base filename."""
        self.assertEqual(
            strip_part_suffix("Epic.Movie.2024.1080p.mkv.01"),
            "Epic.Movie.2024.1080p.mkv",
        )
        self.assertEqual(
            strip_part_suffix("NormalMovie.1080p.mkv"),
            "NormalMovie.1080p.mkv",
        )

    def test_parse_combined_episodes_range(self):
        """Detect episode range in season combined files."""
        info = parse_combined_episodes("Breaking.Bad.S02.E01-E04.1080p.mkv")
        self.assertIsNotNone(info)
        self.assertEqual(info["season"], 2)
        self.assertEqual(info["start"], 1)
        self.assertEqual(info["end"], 4)

    def test_parse_combined_full_season(self):
        """Detect full season batch / combined files."""
        info = parse_combined_episodes("Breaking.Bad.Season.2.Complete.720p.mkv")
        self.assertIsNotNone(info)
        self.assertEqual(info["season"], 2)
        self.assertIsNone(info["start"])

        info2 = parse_combined_episodes("Game.of.Thrones.S01.Combined.mkv")
        self.assertIsNotNone(info2)
        self.assertEqual(info2["season"], 1)
        self.assertIsNone(info2["start"])

    def test_apply_combined_override(self):
        """Ensure apply_combined_override sets correct metadata payload."""
        payload = {"title": "Show", "quality": "1080p"}
        apply_combined_override(payload, {"season": 3, "start": None, "end": None})
        self.assertEqual(payload["season_number"], 3)
        self.assertEqual(payload["episode_number"], 1)
        self.assertTrue(payload["is_combined"])
        self.assertEqual(payload["episode_title"], "Season 3 Complete")
        self.assertIn("Full", payload["quality"])

    def test_season_zero_normalized(self):
        """Season 0 must be normalized to None so specials do not hijack season 0."""
        parsed = parse_media_name("Show Name Season 0.mkv")
        self.assertIsNone(parsed.get("season"))

    def test_language_and_audio_tag_stripping(self):
        """Foreign language, multi-audio, and dub tags must be stripped from parsed title."""
        parsed = parse_media_name("Vidudhalai 2024 Tamil Multi Audio 1080p.mkv")
        self.assertEqual(parsed.get("title"), "Vidudhalai")
        self.assertEqual(parsed.get("year"), 2024)

        parsed2 = parse_media_name("Jawan 2023 Hindi Dual Audio 720p WEB-DL.mkv")
        self.assertEqual(parsed2.get("title"), "Jawan")

    def test_absolute_episode_extraction(self):
        """Orphan / absolute episodes should be extracted accurately."""
        ep = extract_absolute_episode("One Piece 1172 1080p.mkv")
        self.assertEqual(ep, 1172)

        ep2 = extract_absolute_episode("Naruto Shippuden - 016 480p.mkv")
        self.assertEqual(ep2, 16)

    def test_query_variants_and_similarity(self):
        """Search query variants must support bilingual titles and fuzzy matches."""
        variants = build_query_variants("Parasite 기생충", 2019)
        self.assertTrue(any("Parasite" in v for v in variants))
        self.assertTrue(any("기생충" in v for v in variants))

        sim = title_similarity("Vidudhalai", "Vidudhala")
        self.assertGreater(sim, 0.85)


if __name__ == "__main__":
    unittest.main()

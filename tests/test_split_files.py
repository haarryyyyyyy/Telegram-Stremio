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

    def test_safe_dt_and_bytes(self):
        """Token date parser and byte extractor must handle strings, naive/aware datetimes, and ints."""
        from Backend.helper.database import _to_utc_dt, _safe_bytes
        from datetime import datetime, timezone

        self.assertIsNone(_to_utc_dt(None))
        self.assertIsNone(_to_utc_dt(""))
        self.assertIsNone(_to_utc_dt("invalid-date"))

        # String ISO parsing
        parsed = _to_utc_dt("2026-10-15T12:00:00Z")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)

        # Naive datetime
        naive = datetime(2026, 10, 15, 12, 0)
        aware = _to_utc_dt(naive)
        self.assertEqual(aware.tzinfo, timezone.utc)

        # Byte extraction
        self.assertEqual(_safe_bytes({"bytes": 2048}), 2048)
        self.assertEqual(_safe_bytes(4096), 4096)
        self.assertEqual(_safe_bytes(None), 0)
        self.assertEqual(_safe_bytes("invalid"), 0)

    def test_proxy_url_building(self):
        """build_proxy_url must normalize missing schemes and join paths without duplicating original base."""
        try:
            from Backend.fastapi.routes.stremio_routes import build_proxy_url
            from Backend.helper.settings_manager import SettingsManager
        except ImportError:
            raise unittest.SkipTest("fastapi not installed in local environment")

        SettingsManager._instance = None
        orig = "http://mybackend.com:8080/dl/tok123/streamhash/video.mkv"

        # Reverse proxy mode
        SettingsManager.update({"http_proxy_url": "cdn.example.com", "mediaflow_proxy": False})
        res = build_proxy_url(orig)
        self.assertEqual(res, "https://cdn.example.com/dl/tok123/streamhash/video.mkv")

        # Mediaflow mode
        SettingsManager.update({"http_proxy_url": "http://mediaflow.lan:8888", "mediaflow_proxy": True, "mediaflow_password": ""})
        res = build_proxy_url(orig)
        self.assertTrue(res.startswith("http://mediaflow.lan:8888/proxy/stream?d="))

    def test_subtitles_formatting(self):
        """stremio_subtitle_entries must output ISO 639-2 code in lang and human label in label."""
        from Backend.helper.subtitles import stremio_subtitle_entries

        subs = [
            {"msg_id": 101, "encoded": "enc1", "name": "sub.srt", "lang_code": "eng", "lang_label": "English"},
            {"msg_id": 102, "encoded": "enc2", "name": "sub.srt", "lang_code": "eng", "lang_label": "English"},
        ]
        entries = stremio_subtitle_entries(subs, "tok", "http://base.com")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["lang"], "eng")
        self.assertEqual(entries[0]["label"], "English (1)")
        self.assertEqual(entries[1]["lang"], "eng")
        self.assertEqual(entries[1]["label"], "English (2)")

    def test_video_mime_resolution(self):
        """_resolve_filename_mime must reliably resolve video/x-matroska for .mkv files."""
        try:
            from Backend.fastapi.routes.stream_routes import _resolve_filename_mime
        except ImportError:
            raise unittest.SkipTest("fastapi not installed in local environment")

        from collections import namedtuple
        MockFileId = namedtuple("MockFileId", ["file_name", "mime_type"])
        f_mkv = MockFileId(file_name="Movie.2024.1080p.mkv", mime_type=None)
        name, mime = _resolve_filename_mime(f_mkv)
        self.assertEqual(name, "Movie.2024.1080p.mkv")
        self.assertEqual(mime, "video/x-matroska")


if __name__ == "__main__":
    unittest.main()

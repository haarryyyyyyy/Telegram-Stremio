import unittest
from unittest.mock import AsyncMock, PropertyMock, patch

from Backend.helper.settings_manager import Settings, SettingsManager
from Backend.helper.stream_formatter import PRESETS, format_stream


class TestV520Features(unittest.IsolatedAsyncioTestCase):
    def test_settings_manager_defaults(self):
        settings = SettingsManager.current()
        self.assertIn(settings.default_streaming, ("bots", "userbot"))
        self.assertIn(settings.stream_formatter, ("default", "custom", *PRESETS))
        self.assertIsInstance(settings.spatial_poster_enabled, bool)

    def test_stream_formatter_presets(self):
        self.assertIn("torrentio", PRESETS)
        self.assertIn("torbox", PRESETS)
        self.assertIn("gdrive", PRESETS)

        settings = SettingsManager.current()
        # Default returns None so callers fall back to standard naming
        formatted = format_stream(
            settings,
            "Inception.2010.1080p.BluRay.x264.mkv",
            2_000_000_000,
            addon_name="Telegram",
        )
        self.assertIsNone(formatted)

        # Test preset formatting when enabled
        with patch.object(Settings, "stream_formatter", new_callable=PropertyMock) as mock_fmt:
            mock_fmt.return_value = "torrentio"
            custom = format_stream(
                settings,
                "Inception.2010.1080p.BluRay.x264.mkv",
                2_000_000_000,
                addon_name="Telegram",
            )
            self.assertIsNotNone(custom)
            name, title = custom
            self.assertIn("Telegram", name)
            self.assertIn("1080p", name)

    @patch("Backend.helper.metadata.providers.cinemeta.cached_call", new_callable=AsyncMock)
    async def test_cinemeta_cache_key_type_prefix(self, mock_cached_call):
        from Backend.helper.metadata.providers import cinemeta
        mock_cached_call.return_value = {"title": "Test"}
        res = await cinemeta.cached_detail("tt1234567", "tvSeries")
        self.assertEqual(res, {"title": "Test"})
        args, kwargs = mock_cached_call.call_args
        # First arg is cache, second is cache_key
        self.assertEqual(args[1], "series:tt1234567")


if __name__ == "__main__":
    unittest.main()

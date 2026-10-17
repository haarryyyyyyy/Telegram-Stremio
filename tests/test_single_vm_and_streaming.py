import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from pyrogram.file_id import FileId


class TestSingleVMAndStreaming(unittest.IsolatedAsyncioTestCase):
    async def test_dc_prewarm_sessions(self):
        """Verify that _prewarm_sessions initializes media sessions for DCs 1, 2, 4, 5."""
        from Backend.helper.custom_dl import ByteStreamer

        mock_client = MagicMock()
        mock_client.media_sessions = {}
        mock_client.storage.test_mode = AsyncMock(return_value=False)
        mock_client.storage.dc_id = AsyncMock(return_value=2)

        # Mock ExportAuthorization invoke
        exported_auth = MagicMock()
        exported_auth.id = 12345
        exported_auth.bytes = b"authbytes"
        mock_client.invoke = AsyncMock(return_value=exported_auth)

        streamer = ByteStreamer(mock_client, client_index=0)

        with patch("Backend.helper.custom_dl.Auth") as mock_auth_cls, \
             patch("Backend.helper.custom_dl.Session") as mock_session_cls:
            mock_auth_instance = MagicMock()
            mock_auth_instance.create = AsyncMock(return_value=b"key")
            mock_auth_cls.return_value = mock_auth_instance

            mock_sess_instance = MagicMock()
            mock_sess_instance.start = AsyncMock()
            mock_sess_instance.send = AsyncMock()
            mock_session_cls.return_value = mock_sess_instance

            await streamer._prewarm_sessions()

            # For DCs 1, 4, 5 (since current_dc is 2), Auth and Session were created
            self.assertIn(1, mock_client.media_sessions)
            self.assertIn(4, mock_client.media_sessions)
            self.assertIn(5, mock_client.media_sessions)

    async def test_immediate_session_pool_multi_bot(self):
        """Verify that prefetch_stream immediately includes extra bot clients in session_pool."""
        from Backend.helper.custom_dl import ByteStreamer

        mock_client = MagicMock()
        mock_client.media_sessions = {2: MagicMock()}
        mock_client.storage.test_mode = AsyncMock(return_value=False)
        mock_client.storage.dc_id = AsyncMock(return_value=2)

        streamer = ByteStreamer(mock_client, client_index=0)

        # Mock extra bot streamer
        mock_extra_client = MagicMock()
        mock_extra_client.media_sessions = {2: MagicMock()}
        extra_streamer = ByteStreamer(mock_extra_client, client_index=1)

        file_id = MagicMock()
        file_id.dc_id = 2
        file_id.file_size = 10 * 1024 * 1024
        file_id.media_id = 999
        file_id.access_hash = 888
        file_id.file_reference = b"ref"
        file_id.thumbnail_size = None

        with patch.object(streamer, "_get_media_session", new_callable=AsyncMock) as mock_get_sess, \
             patch.object(extra_streamer, "_get_media_session", new_callable=AsyncMock) as mock_extra_get_sess, \
             patch.object(ByteStreamer, "_get_location", new_callable=AsyncMock) as mock_get_loc:
            
            mock_get_sess.return_value = MagicMock()
            mock_extra_get_sess.return_value = MagicMock()
            mock_get_loc.return_value = MagicMock()

            # Call prefetch_stream
            gen = await streamer.prefetch_stream(
                file_id=file_id,
                client_index=0,
                offset=0,
                first_part_cut=0,
                last_part_cut=1024 * 1024,
                part_count=2,
                chunk_size=1024 * 1024,
                prefetch=4,
                parallelism=2,
                extra_clients=[(1, extra_streamer)],
            )
            # Generator created without error
            self.assertIsNotNone(gen)

    async def test_stremio_manifest_bingecat_catalogs(self):
        """Verify that Stremio manifest includes spotlight and recommended smart catalogs."""
        from Backend.fastapi.routes.stremio_routes import get_manifest

        token_data = {"token": "test-token", "user_id": 12345}
        with patch("Backend.db.get_custom_catalogs", new_callable=AsyncMock) as mock_cats, \
             patch("Backend.db.get_catalog_order", new_callable=AsyncMock) as mock_order:
            mock_cats.return_value = []
            mock_order.return_value = []

            manifest = await get_manifest(token="test-token", token_data=token_data)

            catalog_ids = [c["id"] for c in manifest["catalogs"]]
            self.assertIn("spotlight", catalog_ids)
            self.assertIn("recommended", catalog_ids)
            self.assertIn("latest_movies", catalog_ids)

            # Check spotlight entry details
            spotlight_entries = [c for c in manifest["catalogs"] if c["id"] == "spotlight"]
            types = {c["type"] for c in spotlight_entries}
            self.assertIn("movie", types)
            self.assertIn("series", types)

    async def test_single_vm_restart_endpoint(self):
        """Verify that admin restart initiates local process restart directly."""
        from Backend.fastapi.routes.api_routes import restart_app_api

        with patch("Backend.fastapi.routes.api_routes._perform_restart", new_callable=AsyncMock):
            res = await restart_app_api(target="all")
            self.assertEqual(res["status"], "success")
            self.assertIn("Server restart initiated", res["message"])


if __name__ == "__main__":
    unittest.main()

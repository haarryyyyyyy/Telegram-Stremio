import asyncio

import httpx

from Backend.helper.settings_manager import SettingsManager
from Backend.logger import LOGGER


#----- Periodically self-ping the public status page to keep the instance awake
async def ping():
    sleep_time = 1200

    while True:
        await asyncio.sleep(sleep_time)
        try:
            base = (SettingsManager.current().base_url or "").rstrip("/")
            if not base:
                LOGGER.warning("Ping skipped: base_url is not configured")
                continue

            ping_url = f"{base}/status"

            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(ping_url)
                if 200 <= resp.status_code < 400:
                    LOGGER.info("Pinged keep-alive URL %s — Status: %s", ping_url, resp.status_code)
                else:
                    LOGGER.warning(
                        "Keep-alive ping to %s returned %s (check BASE_URL / reverse proxy)",
                        ping_url,
                        resp.status_code,
                    )
        except httpx.TimeoutException:
            LOGGER.warning("Timeout: Could not connect to keep-alive URL.")
        except Exception as e:
            LOGGER.warning(f"Keep-alive ping error: {e}")

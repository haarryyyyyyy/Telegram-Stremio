import asyncio
from datetime import datetime
from typing import Optional

from pyrogram.enums import ParseMode

from Backend import StartTime, __version__, db
from Backend.config import Telegram
from Backend.helper.pyro import get_readable_time
from Backend.logger import LOGGER

_monitor_task: Optional[asyncio.Task] = None
_LOCAL_START_TIME = datetime.utcnow()


def _format_seconds(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    mins = minutes % 60
    if hours < 24:
        return f"{hours}h {mins}m"
    days = hours // 24
    hrs = hours % 24
    return f"{days}d {hrs}h"


async def _send_telegram_alert(bot_client, text: str) -> None:
    if not Telegram.OWNER_ID or not bot_client:
        return
    try:
        await bot_client.send_message(
            chat_id=Telegram.OWNER_ID,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        LOGGER.error(f"[Cluster Monitor] Failed to send Telegram alert: {e}")


async def _cluster_monitor_loop(bot_client) -> None:
    LOGGER.info(f"[Cluster Monitor] Started heartbeat monitor for node: {Telegram.NODE_NAME}")
    # Initial pause to allow initial connections to settle
    await asyncio.sleep(5)
    
    while True:
        try:
            # 1. Update our own node's heartbeat
            await db.record_node_heartbeat(
                node_name=Telegram.NODE_NAME,
                ingest_enabled=Telegram.INGEST_ENABLED,
                version=__version__,
                started_at=_LOCAL_START_TIME,
                port=Telegram.PORT,
            )

            # 2. Inspect peer nodes in cluster
            nodes = await db.get_cluster_nodes()
            now = datetime.utcnow()

            for node in nodes:
                node_name = node.get("node_name")
                if not node_name or node_name == Telegram.NODE_NAME:
                    continue

                is_online = node.get("is_online", False)
                alerted_down = node.get("alerted_down", False)
                seconds_ago = node.get("seconds_ago", 0)
                ingest_role = "Primary Ingest & Streamer" if node.get("ingest_enabled") else "Load-Balanced Streamer"

                # If peer node has been silent for > 60 seconds and not yet alerted
                if not is_online and seconds_ago >= 60 and not alerted_down:
                    LOGGER.warning(f"[Cluster Monitor] Peer node '{node_name}' appears OFFLINE ({seconds_ago}s since last heartbeat). Sending alert...")
                    msg = (
                        f"⚠️ <b>[Cluster Alert] Node Offline!</b>\n\n"
                        f"• <b>Node:</b> <code>{node_name}</code>\n"
                        f"• <b>Status:</b> 🔴 <b>OFFLINE</b>\n"
                        f"• <b>Last Seen:</b> {_format_seconds(seconds_ago)} ago\n"
                        f"• <b>Role:</b> {ingest_role}\n\n"
                        f"<i>Please check your server status or systemctl restart telegram-stremio.</i>"
                    )
                    await _send_telegram_alert(bot_client, msg)
                    await db.set_node_alerted_down(node_name, True)

                # If peer node has recovered and was previously alerted down
                elif is_online and alerted_down:
                    uptime_str = _format_seconds(node.get("uptime_seconds", 0))
                    LOGGER.info(f"[Cluster Monitor] Peer node '{node_name}' has RECOVERED and is back online.")
                    msg = (
                        f"✅ <b>[Cluster Alert] Node Recovered!</b>\n\n"
                        f"• <b>Node:</b> <code>{node_name}</code>\n"
                        f"• <b>Status:</b> 🟢 <b>ONLINE</b>\n"
                        f"• <b>Uptime:</b> {uptime_str}\n"
                        f"• <b>Role:</b> {ingest_role}\n\n"
                        f"<i>The node is back online and accepting streams.</i>"
                    )
                    await _send_telegram_alert(bot_client, msg)
                    await db.set_node_alerted_down(node_name, False)

        except asyncio.CancelledError:
            break
        except Exception as e:
            LOGGER.error(f"[Cluster Monitor] Error in monitor loop: {e}")

        await asyncio.sleep(15)


def start_cluster_monitor(bot_client) -> None:
    global _monitor_task
    if _monitor_task is None or _monitor_task.done():
        _monitor_task = asyncio.create_task(_cluster_monitor_loop(bot_client))

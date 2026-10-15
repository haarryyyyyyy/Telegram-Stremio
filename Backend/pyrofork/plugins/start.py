from pyrogram import Client, enums, filters
from pyrogram.types import Message

from Backend import db
from Backend.config import Telegram
from Backend.helper.settings_manager import SettingsManager
from Backend.logger import LOGGER


#----- /start: hand out the personal Stremio addon link
@Client.on_message(filters.command('start') & filters.private, group=10)
async def send_start_message(client: Client, message: Message):
    try:
        user_id = (message.from_user.id if message.from_user else None) or (message.sender_chat.id if message.sender_chat else None) or message.chat.id
        base_url = SettingsManager.current().base_url
        user_name = (message.from_user.first_name or message.from_user.username or f"User {user_id}") if message.from_user else f"Chat {user_id}"

        token_doc = await db.ensure_api_token_for_user(user_id, user_name)
        token_str = token_doc.get("token") if token_doc else None
        addon_url = f"{base_url}/stremio/{token_str}/manifest.json" if token_str else f"{base_url}/stremio/manifest.json"

        await message.reply_text(
            '🎉 <b>Welcome to the Telegram Stremio Media Server!</b>\n\n'
            'Here is your personal Stremio Addon link:\n\n'
            '🎬 <b>Stremio Addon — Install Link:</b>\n'
            f'<code>{addon_url}</code>\n\n'
            'Tap the link above → <b>Install</b> in Stremio to start watching!',
            quote=True,
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        await message.reply_text(f"⚠️ Error: {e}")
        LOGGER.error(f"Error in /start handler: {e}")

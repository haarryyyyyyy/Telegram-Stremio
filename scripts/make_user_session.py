"""Log in a Telegram user account once and print its session string for USER_SESSION_STRING.

The account must be an admin with "Delete messages" of the skip, storage and announcement channels.
It is only used to delete messages older than 48 hours, which Telegram never lets bots delete.

Run from the repo root on the server (it asks for the phone number, the login code and 2FA password):
    uv run python scripts/make_user_session.py
Then add the printed line to config.env and restart.

The session string is full access to that Telegram account. Keep config.env private.
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pyrogram import Client

load_dotenv(Path(__file__).resolve().parent.parent / "config.env")


async def main():
    api_id, api_hash = os.getenv("API_ID", "").strip(), os.getenv("API_HASH", "").strip()
    if not api_id.isdigit() or not api_hash:
        sys.exit("Set API_ID and API_HASH in config.env first.")
    async with Client("make_user_session", api_id=int(api_id), api_hash=api_hash, in_memory=True) as app:
        session = await app.export_session_string()
        who = app.me.username or app.me.first_name or app.me.id
    print(f"\nLogged in as {who}. Add this line to config.env, then restart:\n")
    print(f'USER_SESSION_STRING="{session}"')
    print("\nKeep it secret: it gives full access to this Telegram account.")


asyncio.run(main())

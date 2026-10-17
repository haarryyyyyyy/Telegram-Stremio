import os
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    mongo_uri: str = Field(default_factory=lambda: os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    db_name: str = Field(default_factory=lambda: os.getenv("DB_NAME", "telegram_stremio_v2"))
    tmdb_api_key: str = Field(default_factory=lambda: os.getenv("TMDB_API_KEY", ""))
    tvdb_api_key: str = Field(default_factory=lambda: os.getenv("TVDB_API_KEY", ""))
    telegram_api_id: int = Field(default_factory=lambda: int(os.getenv("TELEGRAM_API_ID", "0")))
    telegram_api_hash: str = Field(default_factory=lambda: os.getenv("TELEGRAM_API_HASH", ""))
    bot_tokens_raw: str = Field(default_factory=lambda: os.getenv("BOT_TOKENS", ""))
    telegram_channels_raw: str = Field(default_factory=lambda: os.getenv("TELEGRAM_CHANNELS", ""))
    admin_password: str = Field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", "admin123"))
    base_url: str = Field(default_factory=lambda: os.getenv("BASE_URL", "http://localhost:8000").rstrip("/"))

    @property
    def bot_tokens(self) -> List[str]:
        if not self.bot_tokens_raw:
            return []
        return [t.strip() for t in self.bot_tokens_raw.replace("\n", ",").split(",") if t.strip()]

    @property
    def telegram_bot_tokens(self) -> List[str]:
        return self.bot_tokens

    @property
    def telegram_channels(self) -> List[int | str]:
        if not self.telegram_channels_raw:
            return []
        channels = []
        for ch in self.telegram_channels_raw.split(","):
            ch = ch.strip()
            if not ch:
                continue
            if ch.lstrip("-").isdigit():
                channels.append(int(ch))
            else:
                channels.append(ch)
        return channels


settings = Settings()

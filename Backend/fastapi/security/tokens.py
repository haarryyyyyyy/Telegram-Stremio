from datetime import datetime, timezone

from fastapi import HTTPException

from Backend import db
from Backend.config import Telegram
from Backend.helper.settings_manager import SettingsManager

#----- Validate an API token and annotate it with subscription/limit status
async def verify_token(token: str):
    token_data = await db.get_api_token(token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid or expired API token")

    limits = token_data.get("limits", {})
    usage = token_data.get("usage", {})

    token_data["limit_exceeded"] = None
    token_data["subscription_expired"] = False

    #----- Owner-linked tokens are admins (honour persisted flag, else derive)
    _uid = token_data.get("user_id")
    try:
        token_data["is_admin"] = bool(token_data.get("is_admin")) or (
            _uid is not None and int(_uid) == int(Telegram.OWNER_ID)
        )
    except (TypeError, ValueError):
        token_data["is_admin"] = bool(token_data.get("is_admin"))

    #----- Access expiry checks. Admin and never-expires tokens always bypass.
    if not token_data["is_admin"] and not token_data.get("subscription_exempt"):
        def _expired(when):
            ref = datetime.now(timezone.utc)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return when < ref

        token_expiry = token_data.get("expires_at")
        if token_expiry is not None and _expired(token_expiry):
            token_data["subscription_expired"] = True
            return token_data

    if daily_limit := limits.get("daily_limit_gb"):
        if daily_limit > 0:
            current_daily_gb = usage.get("daily", {}).get("bytes", 0) / (1024 ** 3)
            if current_daily_gb >= daily_limit:
                token_data["limit_exceeded"] = "daily"
                return token_data

    if monthly_limit := limits.get("monthly_limit_gb"):
        if monthly_limit > 0:
            current_monthly_gb = usage.get("monthly", {}).get("bytes", 0) / (1024 ** 3)
            if current_monthly_gb >= monthly_limit:
                token_data["limit_exceeded"] = "monthly"
                return token_data

    return token_data

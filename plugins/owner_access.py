from datetime import datetime

from config import Config
from helper.database import db
from helper.plans import PLANS, Plan


# The bot creator is not a paid customer. Keep an internal owner plan so
# every existing quota check can continue using the normal plan interface.
OWNER_DAILY_LIMIT = 1 << 62
OWNER_PLAN = Plan(
    key="owner",
    name="👑 Owner",
    stars=0,
    daily_limit=OWNER_DAILY_LIMIT,
    days=0,
)
PLANS["owner"] = OWNER_PLAN


_original_get_subscription = db.get_subscription


async def _owner_get_subscription(user_id: int, bot_id: int) -> dict:
    user_id = int(user_id)
    bot_id = int(bot_id)

    if Config.OWNER_ID and user_id == int(Config.OWNER_ID):
        return {
            "user_id": user_id,
            "bot_id": bot_id,
            "plan": "owner",
            "expires_at": None,
            "stars_paid": 0,
            "owner": True,
        }

    return await _original_get_subscription(user_id, bot_id)


# Keep the existing database API unchanged for every other user.
db.get_subscription = _owner_get_subscription

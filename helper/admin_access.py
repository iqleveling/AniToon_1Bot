from __future__ import annotations

from config import Config


def is_admin(user_id: int | str | None) -> bool:
    """Return True for OWNER_ID or any user listed in ADMIN."""
    if user_id is None:
        return False
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False

    if Config.OWNER_ID and uid == int(Config.OWNER_ID):
        return True
    return uid in {int(x) for x in Config.ADMIN}


def is_owner(user_id: int | str | None) -> bool:
    if user_id is None or not Config.OWNER_ID:
        return False
    try:
        return int(user_id) == int(Config.OWNER_ID)
    except (TypeError, ValueError):
        return False

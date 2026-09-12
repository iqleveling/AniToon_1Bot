import os


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int = 0) -> int:
    value = os.environ.get(name, str(default)).strip()
    try:
        return int(value)
    except ValueError:
        return default


def _env_int_list(name: str) -> list[int]:
    raw = os.environ.get(name, "")
    result: list[int] = []
    for item in raw.replace(",", " ").split():
        try:
            result.append(int(item))
        except ValueError:
            continue
    return result


def _env_str_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]


class Config:
    API_ID = _env_int("API_ID")
    API_HASH = os.environ.get("API_HASH", "").strip()
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

    # Keep the existing Render variable and support MONGO_URI as fallback.
    DATABASE_URL = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("MONGO_URI")
        or ""
    ).strip()

    ADMIN = _env_int_list("ADMIN")
    OWNER_ID = _env_int("OWNER_ID")
    if OWNER_ID and OWNER_ID not in ADMIN:
        ADMIN.append(OWNER_ID)

    MAIN_BOT_USERNAME = (
        os.environ.get("MAIN_BOT_USERNAME", "")
        .strip()
        .lstrip("@")
    )

    # FORCE_SUB accepts one or more usernames/chat IDs separated by commas.
    FORCE_SUB = _env_str_list("FORCE_SUB")

    LOG_CHANNEL = _env_int("LOG_CHANNEL")

    IS_CLONE_ALLOWED = _env_bool("IS_CLONE_ALLOWED", True)

    START_PIC = os.environ.get("START_PIC", "").strip()

    COMPLETED_STR = os.environ.get("COMPLETED_STR", "🔵")
    REMAINING_STR = os.environ.get("REMAINING_STR", "⚪")

    AUDIO_NAME = (
        os.environ.get("AUDIO_NAME", "AniToon Official").strip()
        or "AniToon Official"
    )
    SUBTITLE_NAME = (
        os.environ.get("SUBTITLE_NAME", "AniToon Official").strip()
        or "AniToon Official"
    )

    PORT = _env_int("PORT", 10000)


# Fail early for the three credentials required to start the main bot.
if Config.API_ID <= 0:
    raise RuntimeError("API_ID is missing or invalid.")
if not Config.API_HASH:
    raise RuntimeError("API_HASH is missing.")
if not Config.BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing.")
if not Config.DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing.")

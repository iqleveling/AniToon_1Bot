import os


class Config:
    # --- FOUNDATION SETTINGS ---
    API_ID = int(os.environ.get("API_ID", ""))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    DATABASE_URL = os.environ.get("DATABASE_URL", "")

    # Multiple admins can be added separated by spaces
    ADMIN = [
        int(admin)
        for admin in os.environ.get("ADMIN", "").split()
        if admin
    ]

    # --- CHOICE 1-B: 4GB SUPPORT ---
    # Premium account string session required for large files
    STRING_SESSION = os.environ.get("STRING_SESSION", "")

    # --- CHOICE 4-B: USER GROWTH ---
    # Channel username (without @) for Force Subscribe
    FORCE_SUB = os.environ.get("FORCE_SUB", "")

    # --- CHOICE 7-B & 9-B: TRACE & LOG SYSTEM ---
    # Private channel ID (starts with -100)
    LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0"))

    # --- CHOICE 10-B: TIERED QUOTAS ---
    # Default daily limit for free users
    # Default: 2 GB
    DAILY_LIMIT = int(
        os.environ.get(
            "DAILY_LIMIT",
            2 * 1024 * 1024 * 1024
        )
    )

    # --- CHOICE 3-B: METADATA BRANDING ---
    # Default track names for internal media branding
    AUDIO_NAME = os.environ.get(
        "AUDIO_NAME",
        "AniToon Official"
    )

    SUBTITLE_NAME = os.environ.get(
        "SUBTITLE_NAME",
        "AniToon Official"
    )

    # --- CHOICE 8-B: CUSTOM PROGRESS BAR ---
    # Custom symbols for AniToon progress bars
    COMPLETED_STR = os.environ.get(
        "COMPLETED_STR",
        "🔵"
    )

    REMAINING_STR = os.environ.get(
        "REMAINING_STR",
        "⚪"
    )

    # --- CHOICE 11-B: CLONE ENGINE ---
    # Enable or disable bot cloning
    IS_CLONE_ALLOWED = True

import os


class Config:
    # ============================================================
    # TELEGRAM BOT SETTINGS
    # ============================================================

    API_ID = int(os.environ.get("API_ID", "0"))

    API_HASH = os.environ.get(
        "API_HASH",
        "",
    )

    BOT_TOKEN = os.environ.get(
        "BOT_TOKEN",
        "",
    )


    # ============================================================
    # DATABASE
    # ============================================================

    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        "",
    )


    # ============================================================
    # ADMIN SETTINGS
    # ============================================================

    ADMIN = [
        int(admin_id)
        for admin_id in os.environ.get(
            "ADMIN",
            "",
        ).split()
        if admin_id.strip()
    ]


    # ============================================================
    # PREMIUM USER SESSION
    # ============================================================

    STRING_SESSION = os.environ.get(
        "STRING_SESSION",
        "",
    )


    # ============================================================
    # FORCE SUBSCRIBE
    # ============================================================

    FORCE_SUB = os.environ.get(
        "FORCE_SUB",
        "",
    ).strip().lstrip("@")


    # ============================================================
    # LOG / BACKUP CHANNEL
    # ============================================================

    LOG_CHANNEL = int(
        os.environ.get(
            "LOG_CHANNEL",
            "0",
        )
    )


    # ============================================================
    # DAILY QUOTA
    # Default: 10 GB per day for Free users
    # ============================================================

    DAILY_LIMIT = int(
        os.environ.get(
            "DAILY_LIMIT",
            str(
                10 * 1024 * 1024 * 1024
            ),
        )
    )


    # ============================================================
    # INTERNAL MEDIA BRANDING
    # ============================================================

    AUDIO_NAME = os.environ.get(
        "AUDIO_NAME",
        "AniToon Official",
    )

    SUBTITLE_NAME = os.environ.get(
        "SUBTITLE_NAME",
        "AniToon Official",
    )


    # ============================================================
    # PROGRESS BAR
    # ============================================================

    COMPLETED_STR = os.environ.get(
        "COMPLETED_STR",
        "🔵",
    )

    REMAINING_STR = os.environ.get(
        "REMAINING_STR",
        "⚪",
    )


    # ============================================================
    # BOT CLONE SYSTEM
    # ============================================================

    IS_CLONE_ALLOWED = (
        os.environ.get(
            "IS_CLONE_ALLOWED",
            "true",
        ).lower()
        in (
            "true",
            "1",
            "yes",
            "on",
        )
    )


    # ============================================================
    # START IMAGE
    # ============================================================

    START_PIC = os.environ.get(
        "START_PIC",
        "",
    )

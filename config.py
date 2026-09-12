import os


class Config:
    # ============================================================
    # TELEGRAM
    # ============================================================

    API_ID = int(
        os.environ.get(
            "API_ID",
            "0",
        )
    )

    API_HASH = os.environ.get(
        "API_HASH",
        "",
    ).strip()

    BOT_TOKEN = os.environ.get(
        "BOT_TOKEN",
        "",
    ).strip()

    # ============================================================
    # DATABASE
    # ============================================================

    # DATABASE_URL is the primary Render variable.
    # MONGO_URI is supported as backward compatibility.
    DATABASE_URL = (
        os.environ.get(
            "DATABASE_URL"
        )
        or os.environ.get(
            "MONGO_URI"
        )
        or ""
    ).strip()

    # ============================================================
    # MAIN BOT ADMINS
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
    # MAIN BOT USERNAME
    # ============================================================

    MAIN_BOT_USERNAME = (
        os.environ.get(
            "MAIN_BOT_USERNAME",
            "",
        )
        .strip()
        .lstrip("@")
    )

    # ============================================================
    # FORCE SUBSCRIBE
    # ============================================================

    FORCE_SUB = (
        os.environ.get(
            "FORCE_SUB",
            "",
        )
        .strip()
        .lstrip("@")
    )

    # ============================================================
    # LOG CHANNEL
    # ============================================================

    LOG_CHANNEL = int(
        os.environ.get(
            "LOG_CHANNEL",
            "0",
        )
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
    # CLONE ENGINE
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
    ).strip()

    # ============================================================
    # OPTIONAL OWNER COMPATIBILITY
    # ============================================================

    # Existing project uses ADMIN.
    # OWNER_ID is supported as an additional fallback.
    OWNER_ID = int(
        os.environ.get(
            "OWNER_ID",
            "0",
        )
    )

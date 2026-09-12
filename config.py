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
    # Used by clones to open the central Stars payment page.
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
    )

import os


class Config:
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH", "").strip()
    BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

    DATABASE_URL = (
        os.getenv("DATABASE_URL")
        or os.getenv("MONGO_URI")
        or ""
    ).strip()

    MAIN_BOT_USERNAME = (
        os.getenv("MAIN_BOT_USERNAME", "")
        .strip()
        .lstrip("@")
    )

    LOG_CHANNEL = int(
        os.getenv("LOG_CHANNEL", "0")
    )

    FORCE_SUB = (
        os.getenv("FORCE_SUB", "")
        .strip()
    )

    FORCE_SUB_LINKS = (
        os.getenv("FORCE_SUB_LINKS", "")
        .strip()
    )

    IS_CLONE_ALLOWED = (
        os.getenv("IS_CLONE_ALLOWED", "true").lower()
        in {"true", "1", "yes", "on"}
    )

    ADMIN = [
        int(x)
        for x in os.getenv("ADMIN", "").split()
        if x.strip().isdigit()
    ]

    OWNER_ID = int(
        os.getenv("OWNER_ID", "0")
    )

    START_PIC = os.getenv(
        "START_PIC", ""
    ).strip()

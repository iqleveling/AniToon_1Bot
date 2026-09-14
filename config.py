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

    # Progress display characters are kept for backwards compatibility. The
    # active transfer UI intentionally uses numeric stats without a bar.
    COMPLETED_STR = os.getenv("COMPLETED_STR", "▰")
    REMAINING_STR = os.getenv("REMAINING_STR", "▱")

    # Keep up to 20 user jobs registered, but only transfer a small number at
    # once. This keeps Telegram responses responsive on small Render instances.
    MAX_ACTIVE_JOBS = max(
        1, int(os.getenv("MAX_ACTIVE_JOBS", "20"))
    )
    MAX_CONCURRENT_TRANSMISSIONS = max(
        1, int(os.getenv("MAX_CONCURRENT_TRANSMISSIONS", "3"))
    )

    # Limit CPU-heavy FFmpeg work independently from Telegram transfers.
    MAX_CONCURRENT_PROCESSING = max(
        1, int(os.getenv("MAX_CONCURRENT_PROCESSING", "2"))
    )

    FFMPEG_PRESET = os.getenv("FFMPEG_PRESET", "ultrafast").strip() or "ultrafast"
    FFMPEG_THREADS = max(0, int(os.getenv("FFMPEG_THREADS", "0")))

    # One progress edit roughly every 1.5s is enough for a smooth UI without
    # flooding Telegram with edits or stealing time from the file transfer.
    PROGRESS_UPDATE_INTERVAL = max(
        1.0, float(os.getenv("PROGRESS_UPDATE_INTERVAL", "1.5"))
    )

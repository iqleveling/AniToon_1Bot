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

    # Progress-bar characters used by helper.utils.progress_for_pyrogram.
    COMPLETED_STR = os.getenv("COMPLETED_STR", "▰")
    REMAINING_STR = os.getenv("REMAINING_STR", "▱")

    # Performance controls. The defaults are deliberately moderate so a single
    # Render instance can serve several users without saturating its network.
    # Pyrogram defaults max_concurrent_transmissions to 1; raising it helps
    # throughput when several users are transferring files at the same time.
    MAX_CONCURRENT_TRANSMISSIONS = max(
        1, int(os.getenv("MAX_CONCURRENT_TRANSMISSIONS", "4"))
    )

    # Fast FFmpeg preset for CPU-only hosts. Set FFMPEG_PRESET=faster/veryfast
    # if you prefer smaller output files over maximum conversion speed.
    FFMPEG_PRESET = os.getenv("FFMPEG_PRESET", "ultrafast").strip() or "ultrafast"
    FFMPEG_THREADS = max(0, int(os.getenv("FFMPEG_THREADS", "0")))
    PROGRESS_UPDATE_INTERVAL = max(
        0.5, float(os.getenv("PROGRESS_UPDATE_INTERVAL", "0.8"))
    )

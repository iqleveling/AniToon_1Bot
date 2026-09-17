import os


class Config:
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH", "").strip()
    BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
    DATABASE_URL = (os.getenv("DATABASE_URL") or os.getenv("MONGO_URI") or "").strip()
    MAIN_BOT_USERNAME = os.getenv("MAIN_BOT_USERNAME", "").strip().lstrip("@")
    LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", "0"))
    ARCHIVE_CHANNEL_ID = int(os.getenv("ARCHIVE_CHANNEL_ID", "-1004491486679"))
    FORCE_SUB = os.getenv("FORCE_SUB", "").strip()
    FORCE_SUB_LINKS = os.getenv("FORCE_SUB_LINKS", "").strip()
    FORCE_SUB_PRIVATE_LINK = os.getenv("FORCE_SUB_PRIVATE_LINK", "").strip()
    IS_CLONE_ALLOWED = os.getenv("IS_CLONE_ALLOWED", "true").lower() in {"true", "1", "yes", "on"}
    ADMIN = [int(x) for x in os.getenv("ADMIN", "").split() if x.strip().isdigit()]
    OWNER_ID = int(os.getenv("OWNER_ID", "0"))
    START_PIC = os.getenv("START_PIC", "").strip()
    COMPLETED_STR = os.getenv("COMPLETED_STR", "▰")
    REMAINING_STR = os.getenv("REMAINING_STR", "▱")
    MAX_ACTIVE_JOBS = max(1, int(os.getenv("MAX_ACTIVE_JOBS", "100")))
    MAX_CONCURRENT_TRANSMISSIONS = max(1, int(os.getenv("MAX_CONCURRENT_TRANSMISSIONS", "3")))
    MAX_CONCURRENT_PROCESSING = max(1, int(os.getenv("MAX_CONCURRENT_PROCESSING", "2")))
    FFMPEG_PRESET = os.getenv("FFMPEG_PRESET", "ultrafast").strip() or "ultrafast"
    FFMPEG_THREADS = max(0, int(os.getenv("FFMPEG_THREADS", "0")))
    PROGRESS_UPDATE_INTERVAL = max(1.0, float(os.getenv("PROGRESS_UPDATE_INTERVAL", "1.5")))

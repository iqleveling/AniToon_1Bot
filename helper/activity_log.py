from __future__ import annotations

from datetime import datetime, timedelta

from helper.database import db


async def log_rename_request(*, bot_id: int, job_id: str, user_id: int, user_name: str, username: str | None, original_name: str, new_name: str, file_size: int, output_format: str | None = None):
    now = datetime.utcnow()
    await db.db.file_activity.update_one(
        {"job_id": str(job_id)},
        {"$set": {
            "job_id": str(job_id), "bot_id": int(bot_id), "user_id": int(user_id),
            "user_name": str(user_name or "Unknown"), "username": str(username or "").lstrip("@"),
            "original_name": str(original_name), "new_name": str(new_name), "file_size": int(file_size or 0),
            "output_format": str(output_format or ""), "status": "requested", "created_at": now,
        }},
        upsert=True,
    )


async def mark_rename_completed(job_id: str):
    await db.db.file_activity.update_one({"job_id": str(job_id)}, {"$set": {"status": "completed", "completed_at": datetime.utcnow()}})


async def recent_rename_activity(*, bot_id: int, hours: int = 24, limit: int = 100):
    since = datetime.utcnow() - timedelta(hours=max(1, int(hours)))
    cursor = db.db.file_activity.find({"bot_id": int(bot_id), "created_at": {"$gte": since}}).sort("created_at", -1).limit(max(1, int(limit)))
    return [item async for item in cursor]

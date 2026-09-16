from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from helper.job_state import jobs
from helper.utils import humanbytes


def _is_staff(user_id: int) -> bool:
    return int(user_id) == int(Config.OWNER_ID) or int(user_id) in {int(x) for x in Config.ADMIN}


def _status(job) -> str:
    if not getattr(job, "active", True):
        return "⏸️ Paused"
    action = getattr(job, "selected_action", None)
    extra = getattr(job, "extra", {}) or {}
    if extra.get("processing"):
        return "⚙️ Processing"
    if action:
        return f"⏳ Waiting: {action}"
    return "⏳ Waiting for action"


def _job_size(job) -> int:
    extra = getattr(job, "extra", {}) or {}
    return int(extra.get("telegram_file_size", 0) or 0)


@Client.on_message(filters.private & filters.command("queue"), group=-3100)
async def queue_info_command(client: Client, message: Message):
    user = message.from_user
    if not user or not _is_staff(user.id):
        await message.reply_text("🚫 **Owner/Admin only.**")
        return

    async with jobs._lock:
        queued = sorted(list(jobs._jobs.values()), key=lambda item: item.queued_at)

    if not queued:
        await message.reply_text("📋 **Queue is empty.**")
        return

    total = len(queued)
    lines = [f"📋 **AniToon Queue — {total} file(s)**", "━━━━━━━━━━━━━━━━━━━━"]

    for index, job in enumerate(queued, 1):
        name = getattr(job, "original_name", None) or "Unknown"
        user_id = getattr(job, "user_id", 0)
        bot_id = getattr(job, "bot_id", 0)
        job_id = getattr(job, "job_id", "-")
        size = humanbytes(_job_size(job))
        status = _status(job)
        action = getattr(job, "selected_action", None) or "Not selected"
        output_ext = getattr(job, "output_ext", None) or "-"

        lines.extend([
            f"**#{index}** {status}",
            f"📄 `{name}`",
            f"📦 `{size}`",
            f"👤 User: `{user_id}`",
            f"🤖 Bot: `{bot_id}`",
            f"🆔 Job: `{job_id}`",
            f"🔧 Action: `{action}`",
            f"🎯 Output: `{output_ext}`",
            "━━━━━━━━━━━━━━━━━━━━",
        ])

    text = "\n".join(lines)
    # Telegram message limit safety for very large queues.
    for offset in range(0, len(text), 3800):
        await message.reply_text(text[offset:offset + 3800])

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from helper.job_state import jobs
from helper.utils import humanbytes


def _is_owner(user_id: int) -> bool:
    return int(user_id) == int(Config.OWNER_ID)


def _status(job) -> str:
    if not getattr(job, "active", True):
        return "⏸️ Paused"
    extra = getattr(job, "extra", {}) or {}
    if extra.get("processing"):
        return "⚙️ Processing"
    action = getattr(job, "selected_action", None)
    if action:
        return f"⏳ Waiting: {action}"
    return "⏳ Waiting for action"


def _job_size(job) -> int:
    extra = getattr(job, "extra", {}) or {}
    return int(extra.get("telegram_file_size", 0) or 0)


def _job_sort_key(job):
    return getattr(job, "queued_at", 0) or 0


def _format_job(index: int, job, include_identity: bool = False) -> list[str]:
    name = getattr(job, "original_name", None) or "Unknown"
    size = humanbytes(_job_size(job))
    status = _status(job)
    action = getattr(job, "selected_action", None) or "Not selected"
    output_ext = getattr(job, "output_ext", None) or "-"
    lines = [
        f"**#{index}** {status}",
        f"📄 `{name}`",
        f"📦 `{size}`",
        f"🔧 Action: `{action}`",
        f"🎯 Output: `{output_ext}`",
    ]
    if include_identity:
        lines.extend([
            f"👤 User: `{getattr(job, 'user_id', 0)}`",
            f"🤖 Bot: `{getattr(job, 'bot_id', 0)}`",
            f"🆔 Job: `{getattr(job, 'job_id', '-')}`",
        ])
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return lines


@Client.on_message(filters.private & filters.command("queue"), group=-3100)
async def queue_info_command(client: Client, message: Message):
    user = message.from_user
    if not user:
        return

    owner = _is_owner(user.id)

    async with jobs._lock:
        all_jobs = sorted(list(jobs._jobs.values()), key=_job_sort_key)

    if owner:
        queued = all_jobs
        title = f"📋 **AniToon Full Queue — {len(queued)} file(s)**"
    else:
        queued = [job for job in all_jobs if int(getattr(job, "user_id", 0)) == int(user.id)]
        title = f"📋 **Your Queue — {len(queued)} file(s)**"

    if not queued:
        await message.reply_text("📋 **Your queue is empty.**" if not owner else "📋 **Queue is empty.**")
        return

    lines = [title, "━━━━━━━━━━━━━━━━━━━━"]
    for index, job in enumerate(queued, 1):
        lines.extend(_format_job(index, job, include_identity=owner))

    text = "\n".join(lines)
    for offset in range(0, len(text), 3800):
        await message.reply_text(text[offset:offset + 3800])

from __future__ import annotations

from datetime import datetime

from pyrogram import Client, filters

from config import Config
from helper.activity_log import log_rename_request, recent_rename_activity
from helper.admin_access import is_owner
from helper.job_state import jobs
from helper.utils import humanbytes


def _owner_filter():
    return filters.user([int(Config.OWNER_ID)]) if Config.OWNER_ID else filters.user([])


def _display_user(name: str, username: str | None, user_id: int) -> str:
    name = (name or "Unknown").replace("`", "'")
    tag = f"@{username}" if username else "no username"
    return f"{name} ({tag}) — `{user_id}`"


def _job_status(job) -> str:
    action = job.selected_action or "waiting for action"
    if action in {"custom_name", "convert_name", "rename_output_choice", "rename_format", "advanced_menu"}:
        return f"queued/processing: `{action}`"
    return f"`{action}`"


@Client.on_message(filters.private & filters.text & filters.reply, group=-1300)
async def capture_owner_rename_activity(client, message):
    """Persist rename requests before the normal rename handler consumes them."""
    try:
        job = await jobs.get_user_job(message.from_user.id)
        if not job or job.selected_action not in {"custom_name", "convert_name"}:
            return
        reply_id = getattr(message.reply_to_message, "id", None)
        prompt_id = int((job.extra or {}).get("rename_prompt_message_id", 0) or 0)
        if prompt_id and reply_id and int(reply_id) != prompt_id:
            return
        text = (message.text or "").strip()
        if not text:
            return
        ext = job.output_ext or ""
        new_name = text
        if ext and not new_name.lower().endswith("." + ext.lower()):
            new_name = f"{new_name.rsplit('.', 1)[0] if '.' in new_name else new_name}.{ext}"
        user = message.from_user
        full_name = " ".join(x for x in [user.first_name, user.last_name] if x).strip() or "Unknown"
        await log_rename_request(
            bot_id=int(getattr(client, "bot_id", 0)),
            job_id=job.job_id,
            user_id=int(user.id),
            user_name=full_name,
            username=user.username,
            original_name=job.original_name,
            new_name=new_name,
            file_size=int((job.extra or {}).get("telegram_file_size", 0) or 0),
            output_format=ext or job.mime_type or "",
        )
    except Exception:
        return


@Client.on_message(filters.private & filters.command(["processing", "activity", "renamehistory"]) & _owner_filter(), group=-120)
async def owner_processing_activity(client, message):
    """Owner-only dashboard: live jobs plus rename requests from the last 24 hours."""
    if not is_owner(message.from_user.id):
        return
    bot_id = int(getattr(client, "bot_id", 0))
    jobs_by_user = []
    try:
        async for user in db.get_all_users():
            for job in await jobs.get_user_jobs(int(user.get("id", 0))):
                if int(job.bot_id) == bot_id:
                    jobs_by_user.append(job)
    except Exception:
        jobs_by_user = []

    lines = ["👑 **OWNER PROCESSING DASHBOARD**", "", f"🟢 **Currently in memory:** `{len(jobs_by_user)}`", ""]
    if not jobs_by_user:
        lines.append("No files are currently waiting or processing.")
    else:
        for index, job in enumerate(sorted(jobs_by_user, key=lambda x: x.created_at), 1):
            src = (job.extra or {}).get("source_message")
            user = getattr(src, "from_user", None)
            if user:
                full_name = " ".join(x for x in [user.first_name, user.last_name] if x).strip() or "Unknown"
                username = user.username
            else:
                data = (job.extra or {}).get("user_data") or {}
                full_name = str(data.get("first_name") or data.get("name") or "Unknown")
                username = data.get("username")
            size = int((job.extra or {}).get("telegram_file_size", 0) or 0)
            pos = await jobs.user_queue_position(job.job_id)
            lines.extend([
                f"**{index}.** {_display_user(full_name, username, job.user_id)}",
                f"📄 `{job.original_name}`",
                f"📦 `{humanbytes(size)}`  •  `{job.mime_type or 'unknown'}`",
                f"⚙️ {_job_status(job)}  •  Queue: `#{pos + 1 if pos else 1}`",
                f"🆔 Job: `{job.job_id}`",
                "",
            ])

    try:
        history = await recent_rename_activity(bot_id=bot_id, hours=24, limit=80)
    except Exception:
        history = []
    lines.extend(["", "🕐 **RENAMED FILES — LAST 24 HOURS**", ""])
    if not history:
        lines.append("No rename activity recorded in the last 24 hours.")
    else:
        for index, item in enumerate(history, 1):
            created = item.get("created_at")
            if isinstance(created, datetime):
                stamp = created.strftime("%Y-%m-%d %H:%M UTC")
            else:
                stamp = "unknown time"
            lines.extend([
                f"**{index}.** {_display_user(item.get('user_name'), item.get('username'), int(item.get('user_id', 0)))}",
                f"📄 Old: `{str(item.get('original_name', ''))[:180]}`",
                f"✏️ New: `{str(item.get('new_name', ''))[:180]}`",
                f"📦 Size: `{humanbytes(int(item.get('file_size', 0) or 0))}`  •  Format: `{item.get('output_format') or 'original'}`",
                f"🕐 `{stamp}`  •  Job: `{item.get('job_id', '-')}`",
                "",
            ])

    # Telegram message limit is 4096 characters. Send the dashboard in safe chunks.
    text = "\n".join(lines)
    chunks = [text[i:i + 3900] for i in range(0, len(text), 3900)] or ["👑 No activity data."]
    for chunk in chunks:
        await message.reply_text(chunk)

from __future__ import annotations

import os
import uuid

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from helper.job_state import Job, jobs
from helper.plans import get_plan
from helper.utils import humanbytes
from plugins.rename import _media_from_message, _safe_filename, _user_context
from plugins.ui import file_action_menu


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio), group=-2000)
async def fifo_file_intake(client: Client, message: Message):
    """Create every incoming file as a FIFO job; never discard an older job."""
    user_id = message.from_user.id
    bot_id = int(getattr(client, "bot_id", 0))

    context, error = await _user_context(user_id, bot_id)
    if error:
        await message.reply_text(error)
        raise StopPropagation
    user_data, plan, used = context
    media = _media_from_message(message)
    if not media:
        raise StopPropagation

    expected_size = int(getattr(media, "file_size", 0) or 0)
    if used >= plan.daily_limit:
        await message.reply_text(
            "🚫 **Daily Limit Reached!**\n\n"
            f"Current Plan: {plan.name}\n"
            f"Daily Limit: `{humanbytes(plan.daily_limit)}`\n"
            f"Used: `{humanbytes(used)}`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("💎 Upgrade", callback_data="upgrade")]]
            ),
        )
        raise StopPropagation

    original_name = _safe_filename(
        getattr(media, "file_name", None) or f"file_{message.id}"
    )
    job_id = uuid.uuid4().hex[:12]
    work_dir = os.path.join("downloads", str(user_id), job_id)
    os.makedirs(work_dir, exist_ok=True)
    input_path = os.path.join(work_dir, original_name)

    job = Job(
        job_id=job_id,
        user_id=user_id,
        bot_id=bot_id,
        source_message_id=message.id,
        work_dir=work_dir,
        input_path=input_path,
        original_name=original_name,
        mime_type=getattr(media, "mime_type", None) or "",
        extra={
            "extension": os.path.splitext(original_name)[1].lstrip("."),
            "user_data": user_data,
            "used_before": used,
            "telegram_file_size": expected_size,
        },
    )

    if not await jobs.register(job):
        await message.reply_text("❌ Could not add this file to the queue. Please send it again.")
        raise StopPropagation

    position = await jobs.user_position(job_id) if hasattr(jobs, "user_position") else 1
    if position > 1:
        header = f"⏳ **Queued — position {position}**\n\n"
    else:
        header = "📂 **File Detected**\n\n"

    text = (
        header
        f"📄 `{original_name}`\n"
        f"📦 `{humanbytes(expected_size)}`\n\n"
        "Choose an operation. Your files are processed in the order received."
    )
    prompt = await message.reply_text(text, reply_markup=file_action_menu(job_id))
    await jobs.update(job_id, extra={**job.extra, "prompt_message_id": prompt.id})
    raise StopPropagation

from __future__ import annotations

import os
import shutil
import uuid

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import Message

from helper.archive_result import archive_message
from helper.database import db
from helper.ffmpeg import get_video_info, prepare_video_for_telegram
from helper.job_transfer import upload_job
from helper.large_file import split_file_for_telegram
from helper.large_video import is_large_video, split_video_for_telegram
from helper.job_state import Job, jobs
from helper.message_cleanup import protect_message, protect_result
from helper.utils import humanbytes, reset_progress
from plugins.rename import _ask_name, _base_without_extension, _extension, _media_from_message, _safe_filename, _user_context
from plugins.ui import file_action_menu, rename_output_menu

VIDEO_EXTENSIONS = {"mp4", "mkv", "webm", "mov", "avi", "flv", "ts", "m4v"}


def _video_upload_name(filename: str) -> str:
    return f"{_base_without_extension(filename)}.mp4"


async def _prepare_video(job: Job, path: str, filename: str):
    upload_name = _video_upload_name(filename)
    prepared = os.path.join(job.work_dir, f".telegram_{uuid.uuid4().hex}.mp4")
    upload_path = await prepare_video_for_telegram(path, prepared)
    if not upload_path:
        raise RuntimeError("Could not prepare a valid Telegram-compatible video")
    duration, width, height = await get_video_info(upload_path)
    if duration <= 0 or width <= 0 or height <= 0:
        raise RuntimeError("Video metadata could not be read")
    return upload_path, upload_name, duration, width, height


async def _show_upload_start(status: Message | None, filename: str):
    if status is None:
        return
    try:
        await status.edit_text(f"📤 **Uploading**\n\n📂 `{filename}`\n\n⚡ Preparing Telegram upload...")
    except Exception:
        pass


async def _send_video(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    await _show_upload_start(status, filename)
    upload_path, upload_name, _duration, _width, _height = await _prepare_video(job, path, filename)
    try:
        result = await upload_job(client, job, upload_path, upload_name, status, as_video=True)
        if not result:
            raise RuntimeError("Telegram returned no video message after upload")
        return result
    finally:
        if upload_path != path:
            try:
                os.remove(upload_path)
            except OSError:
                pass


async def _send_plain_output(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise RuntimeError("Processed output is missing or empty")
    ext, mime = _extension(filename), job.mime_type or ""
    if ext == "mp4" or mime == "video/mp4":
        return await _send_video(client, job, path, filename, status)
    await _show_upload_start(status, filename)
    result = await upload_job(client, job, path, filename, status, as_video=False)
    if not result:
        raise RuntimeError("Telegram returned no uploaded result")
    return result


async def _deliver_output(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    if _extension(filename) == "mp4" or (job.mime_type or "") == "video/mp4":
        if is_large_video(path):
            parts = await split_video_for_telegram(path, job.work_dir, filename)
            return [await _send_video(client, job, part, os.path.basename(part), status) for part in parts]
    parts = await split_file_for_telegram(path, job.work_dir, filename)
    if len(parts) > 1:
        return [await _send_plain_output(client, job, part, os.path.basename(part), status) for part in parts]
    return [await _send_plain_output(client, job, path, filename, status)]


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio), group=-10000)
async def repaired_file_download(client: Client, message: Message):
    """File -> information -> action. Download is deferred until name selection."""
    user = message.from_user
    if not user:
        raise StopPropagation
    user_id, bot_id = int(user.id), int(getattr(client, "bot_id", 0))
    context, error = await _user_context(user_id, bot_id)
    if error:
        await message.reply_text(error)
        raise StopPropagation
    user_data, plan, used = context
    media = _media_from_message(message)
    if not media:
        raise StopPropagation
    expected_size = int(getattr(media, "file_size", 0) or 0)
    if used + expected_size > plan.daily_limit:
        await message.reply_text(
            "🚫 **This file exceeds your remaining daily quota.**\n\n"
            f"Plan: {plan.name}\nRemaining: `{humanbytes(max(plan.daily_limit - used, 0))}`\n"
            f"File: `{humanbytes(expected_size)}`"
        )
        raise StopPropagation

    original_name = _safe_filename(getattr(media, "file_name", None) or f"file_{message.id}")
    extension, mime_type = _extension(original_name), getattr(media, "mime_type", None) or ""
    duration = int(getattr(media, "duration", 0) or 0) if message.video else 0
    job_id = uuid.uuid4().hex[:12]
    work_dir = os.path.join("downloads", str(user_id), job_id)
    os.makedirs(work_dir, exist_ok=True)
    job = Job(
        job_id=job_id,
        user_id=user_id,
        bot_id=bot_id,
        source_message_id=message.id,
        work_dir=work_dir,
        input_path=os.path.join(work_dir, original_name),
        original_name=original_name,
        mime_type=mime_type,
        extra={
            "extension": extension,
            "file_id": getattr(media, "file_id", "") or "",
            "source_message": message,
            "user_data": user_data,
            "used_before": used,
            "telegram_file_size": expected_size,
            "duration": duration,
            "source_media_type": "video" if message.video else ("audio" if message.audio else "document"),
        },
    )
    if not await jobs.register(job):
        shutil.rmtree(work_dir, ignore_errors=True)
        await message.reply_text("❌ Could not add this file to the queue.")
        raise StopPropagation
    try:
        all_jobs = await jobs.get_user_jobs(user_id)
        queue_position = len(all_jobs)
        queue_text = f"\n\n📋 **Queue position:** `#{queue_position}`" if queue_position > 1 else ""
        status = await message.reply_text(
            "📂 **File Information**\n\n"
            f"📄 **Name:** `{original_name}`\n"
            f"📦 **Size:** `{humanbytes(expected_size)}`\n"
            f"🎞 **Type:** `{mime_type or extension or 'unknown'}`"
            + (f"\n🎬 **Runtime:** `{duration // 60}m {duration % 60}s`" if duration else "")
            + queue_text + "\n\nChoose an operation:",
            reply_markup=file_action_menu(job_id),
        )
        await jobs.update(job_id, extra={**job.extra, "status_message_id": status.id})
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        await jobs.remove(job_id)
        raise StopPropagation
    raise StopPropagation

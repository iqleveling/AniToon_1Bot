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


async def _send_video(client: Client, job: Job, path: str, filename: str, status: Message | None = None, *, prepared_video: bool = False):
    await _show_upload_start(status, filename)
    if prepared_video:
        upload_path = path
        upload_name = filename
    else:
        upload_path, upload_name, _duration, _width, _height = await _prepare_video(job, path, filename)
    try:
        result = await upload_job(client, job, upload_path, upload_name, status, as_video=True, prepared_video=prepared_video)
        if not result:
            raise RuntimeError("Telegram returned no video message after upload")
        return result
    finally:
        if not prepared_video and upload_path != path:
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


async def _deliver_output(client: Client, job: Job, path: str, filename: str, status: Message | None = None, *, prepared_video: bool = False):
    if _extension(filename) == "mp4" or (job.mime_type or "") == "video/mp4":
        if is_large_video(path):
            parts = await split_video_for_telegram(path, job.work_dir, filename)
            return [await _send_video(client, job, part, os.path.basename(part), status) for part in parts]
        return [await _send_video(client, job, path, filename, status, prepared_video=prepared_video)]
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

    try:
        from plugins.start import get_force_sub_status, make_force_sub_text, make_force_sub_keyboard, _configured_force_sub_channels
        joined_count, missing_channels, failed_channels = await get_force_sub_status(client, user_id)
        if missing_channels or failed_channels or joined_count != len(_configured_force_sub_channels()):
            await message.reply_text(
                make_force_sub_text(joined_count, len(missing_channels), len(failed_channels)),
                reply_markup=make_force_sub_keyboard(missing_channels),
            )
            raise StopPropagation
    except StopPropagation:
        raise
    except Exception:
        await message.reply_text("⚠️ **Channel verification failed.** Please try again in a moment.")
        raise StopPropagation

    context, error = await _user_context(user_id, bot_id)
    if error:
        await message.reply_text(error)
        raise StopPropagation
    user_data, plan, used = context
    media = _media_from_message(message)
    if not media:
        raise StopPropagation
    expected_size = int(getattr(media, "file_size", 0) or 0)
    from config import Config
    if expected_size > Config.MAX_FILE_SIZE_BYTES:
        await message.reply_text("🚫 **File is too large.**\\n\\nMaximum allowed file size is `2 GB` per file.")
        raise StopPropagation
    if used + expected_size > plan.daily_limit:
        await message.reply_text("🚫 **This file exceeds your remaining daily quota.**\n\n" f"Plan: {plan.name}\nRemaining: `{humanbytes(max(plan.daily_limit - used, 0))}`\nFile: `{humanbytes(expected_size)}`")
        raise StopPropagation

    original_name = _safe_filename(getattr(media, "file_name", None) or f"file_{message.id}")
    extension, mime_type = _extension(original_name), getattr(media, "mime_type", None) or ""
    duration = int(getattr(media, "duration", 0) or 0) if message.video else 0
    job_id = uuid.uuid4().hex[:12]
    work_dir = os.path.join("downloads", str(user_id), job_id)
    os.makedirs(work_dir, exist_ok=True)
    job = Job(job_id=job_id, user_id=user_id, bot_id=bot_id, source_message_id=message.id, work_dir=work_dir, input_path=os.path.join(work_dir, original_name), original_name=original_name, mime_type=mime_type, extra={"extension": extension, "file_id": getattr(media, "file_id", "") or "", "source_message": message, "user_data": user_data, "used_before": used, "telegram_file_size": expected_size, "duration": duration, "source_media_type": "video" if message.video else ("audio" if message.audio else "document")})
    if not await jobs.register(job):
        shutil.rmtree(work_dir, ignore_errors=True)
        await message.reply_text("❌ Could not add this file to the queue.")
        raise StopPropagation
    try:
        all_jobs = await jobs.get_user_jobs(user_id)
        queue_position = len(all_jobs)
        queue_text = f"\n\n📋 **Queue position:** `#{queue_position}`" if queue_position > 1 else ""
        runtime_text = f"\n🎬 **Runtime:** `{duration // 60}m {duration % 60}s`" if duration else ""
        status = await message.reply_text("📂 **File Information**\n\n" f"📄 **Name:** `{original_name}`\n" f"📦 **Size:** `{humanbytes(expected_size)}`\n" f"🎞 **Type:** `{mime_type or extension or 'unknown'}`" + runtime_text + queue_text + "\n\nChoose an operation:", reply_markup=file_action_menu(job_id))
        await jobs.update(job_id, extra={**job.extra, "status_message_id": status.id})
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        await jobs.remove(job_id)
        raise StopPropagation
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"), group=-1000)
async def rename_entry_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired or not owned by you.", show_alert=True); raise StopPropagation
    await cb.answer()
    await jobs.update(job.job_id, selected_action="rename_output_choice", extra={**job.extra, "rename_menu_message_id": cb.message.id})
    try: await cb.message.edit_text("✏️ **Rename**\n\nChoose output type:", reply_markup=rename_output_menu(job.job_id))
    except Exception: pass
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^renameoutput:([0-9a-f]+):(file|video)$"), group=-1000)
async def rename_output_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired or not owned by you.", show_alert=True); raise StopPropagation
    mode = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, selected_action="custom_name", extra={**job.extra, "rename_output_mode": mode, "rename_menu_message_id": cb.message.id})
    prompt = await _ask_name(client, job.user_id, "✏️ **Rename**\n\nSend the new filename.", job.job_id, "custom_name")
    await jobs.update(job.job_id, extra={**job.extra, "rename_prompt_message_id": prompt.id, "prompt_message_id": prompt.id})
    try: await cb.message.delete()
    except Exception: pass
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:cancel:([0-9a-f]+)$"), group=-1000)
async def cancel_pending_file(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired or not owned by you.", show_alert=True); raise StopPropagation
    await cb.answer("Cancelled", show_alert=True)
    shutil.rmtree(job.work_dir, ignore_errors=True)
    await jobs.remove(job.job_id)
    try: await cb.message.edit_text("❌ **File job cancelled.**", reply_markup=None)
    except Exception: pass
    raise StopPropagation

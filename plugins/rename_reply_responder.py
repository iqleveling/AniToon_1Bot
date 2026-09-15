from __future__ import annotations

import os
import shutil
import time

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from helper.database import db
from helper.ffmpeg import convert_media
from helper.job_state import jobs
from helper.job_transfer import download_job
from helper.message_cleanup import delete_user_job_messages, protect_message, protect_result
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes
from plugins.file_action_fix import _deliver_output
from plugins.rename import _base_without_extension, _extension, _safe_filename


NAME_ACTIONS = {"custom_name", "convert_name"}
PROCESSING_INTERVAL = 3.0


async def _find_name_job(user_id: int):
    try:
        user_jobs = await jobs.get_user_jobs(user_id)
    except Exception:
        user_jobs = []
    for job in user_jobs:
        if getattr(job, "selected_action", None) in NAME_ACTIONS:
            return job
    return None


async def _download_source(client: Client, message, job, status):
    source = (job.extra or {}).get("source_message")
    if not source:
        source = (job.extra or {}).get("media")
    if not source:
        source = (job.extra or {}).get("file_id")
    if not source:
        source = await client.get_messages(message.chat.id, job.source_message_id)
    if not source:
        raise RuntimeError("Original file could not be located")
    return await download_job(client, source, job, status)


async def _processing_progress(status, job, current, total, start_time, force=False):
    """Show FFmpeg processing progress every 3 seconds.

    The 3x multiplier is display-only.  Actual FFmpeg byte/time processing is
    never changed, so the conversion remains correct while the UI shows the
    requested multiplied MB figure.
    """
    if status is None:
        return
    now = time.time()
    last = getattr(job, "_last_processing_progress", 0.0) or 0.0
    if not force and now - last < PROCESSING_INTERVAL:
        return

    current = max(0.0, float(current or 0.0))
    total = max(0.0, float(total or 0.0))
    percent = min(100.0, (current * 100.0 / total)) if total else 0.0
    shown_current = current * 3.0
    shown_total = total * 3.0 if total else 0.0
    elapsed = max(0.001, now - start_time)
    speed = current / elapsed
    shown_speed = speed * 3.0
    eta = max(0, int((total - current) / speed)) if speed > 0 and total >= current else 0
    minutes, seconds = divmod(eta, 60)
    eta_text = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
    completed = max(0, min(24, int(percent / 100.0 * 24)))
    bar = "█" * completed + "░" * (24 - completed)

    try:
        await status.edit_text(
            "⚙️ **Processing...**\n"
            f"{bar} {percent:.2f}%\n\n"
            f"📦 Processed: `{humanbytes(shown_current)}` / `{humanbytes(shown_total)}`\n"
            f"🚀 Speed: `{humanbytes(shown_speed)}/s`\n"
            f"⏱ ETA: `{eta_text}`"
        )
        job._last_processing_progress = now
    except Exception:
        pass


async def _cleanup_successful_user_input(client, message, job):
    """Delete only the user's source file and filename after a successful result."""
    ids = [job.source_message_id, getattr(message, "id", None)]
    await delete_user_job_messages(client, message.chat.id, ids)


@Client.on_message(filters.private & filters.text, group=-1200)
async def reliable_rename_reply(client, message):
    if not message.text or message.text.startswith("/"):
        return

    job = await _find_name_job(message.from_user.id)
    if not job:
        return

    text = message.text.strip()
    if not text:
        await message.reply_text("❌ **Please send a valid filename.**")
        raise StopPropagation

    action = getattr(job, "selected_action", None)

    if action == "convert_name":
        ext = getattr(job, "output_ext", None)
        if not ext:
            await message.reply_text("❌ **Conversion format expired. Please select Convert again.**")
            raise StopPropagation

        name = _safe_filename(text)
        if _extension(name) != ext:
            name = f"{_base_without_extension(name)}.{ext}"

        status = await message.reply_text(
            "📥 **Downloading...**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job.job_id}")]]),
        )
        await protect_message(status.chat.id, status.id)
        try:
            await _download_source(client, message, job, status)
            await status.edit_text("⚙️ **Processing...**")
            job._last_processing_progress = 0.0
            processing_start = time.time()

            async def processing_callback(current, total):
                await _processing_progress(status, job, current, total, processing_start)

            output_path = os.path.join(job.work_dir, name)
            if not await convert_media(job.input_path, output_path, ext, progress_callback=processing_callback):
                raise RuntimeError("FFmpeg conversion failed")
            await _processing_progress(status, job, 1, 1, processing_start, force=True)

            # Protect the completed status BEFORE sending the result. The
            # auto-cleanup wrapper runs before send_video/send_document.
            await protect_message(status.chat.id, status.id)
            results = await _deliver_output(client, job, output_path, name, status)
            for result in results or []:
                await protect_result(result)
            size = os.path.getsize(output_path)
            await db.update_usage(job.user_id, job.bot_id, size)
            await status.edit_text(f"✅ **Conversion Complete!**\n\n📂 `{name}`\n📦 `{humanbytes(size)}`")
            await protect_result(status)
            await _cleanup_successful_user_input(client, message, job)
        except AniToonTransferCancelled:
            await status.edit_text("❌ **Processing cancelled.**")
        except Exception as exc:
            await status.edit_text(f"❌ **Conversion failed**\n\n`{str(exc)[:1000]}`")
        finally:
            clear_transfer_cancel(job.job_id)
            shutil.rmtree(job.work_dir, ignore_errors=True)
            await jobs.remove(job.job_id)

        raise StopPropagation

    if action == "custom_name":
        ext = _extension(job.original_name)
        name = _safe_filename(text)
        if not _extension(name) and ext:
            name = f"{name}.{ext}"
        elif _extension(name) and ext:
            name = f"{_base_without_extension(name)}.{ext}"

        output_path = os.path.join(job.work_dir, name)
        status = await message.reply_text(
            "📥 **Downloading...**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job.job_id}")]]),
        )
        await protect_message(status.chat.id, status.id)
        try:
            await _download_source(client, message, job, status)
            await status.edit_text("⚙️ **Processing...**")
            os.replace(job.input_path, output_path)
            if job.extra.get("rename_output_mode") == "video":
                job.mime_type = "video/mp4"

            # Keep the status alive while the upload callback edits it.
            await protect_message(status.chat.id, status.id)
            results = await _deliver_output(client, job, output_path, name, status)
            for result in results or []:
                await protect_result(result)
            size = os.path.getsize(output_path)
            await db.update_usage(job.user_id, job.bot_id, size)
            await status.edit_text(f"✅ **Rename Complete!**\n\n📂 `{name}`\n📦 `{humanbytes(size)}`")
            await protect_result(status)
            await _cleanup_successful_user_input(client, message, job)
        except AniToonTransferCancelled:
            await status.edit_text("❌ **Processing cancelled.**")
        except Exception as exc:
            await status.edit_text(f"❌ **Processing failed**\n\n`{str(exc)[:1000]}`")
        finally:
            clear_transfer_cancel(job.job_id)
            shutil.rmtree(job.work_dir, ignore_errors=True)
            await jobs.remove(job.job_id)

        raise StopPropagation

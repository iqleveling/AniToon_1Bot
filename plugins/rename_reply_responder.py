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
from helper.message_cleanup import delete_user_job_messages, protect_message, protect_result, protect_transfer_message
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes, progress_for_pyrogram, reset_progress
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
    source = (job.extra or {}).get("source_message") or (job.extra or {}).get("media") or (job.extra or {}).get("file_id")
    if not source:
        source = await client.get_messages(message.chat.id, job.source_message_id)
    if not source:
        raise RuntimeError("Original file could not be located")
    return await download_job(client, source, job, status)


async def _processing_progress(status, job, current_bytes, total_bytes, start_time, force=False):
    if status is None:
        return
    now = time.time()
    last = getattr(job, "_last_processing_progress", 0.0) or 0.0
    if not force and now - last < PROCESSING_INTERVAL:
        return

    current = max(0.0, float(current_bytes or 0.0))
    total = max(0.0, float(total_bytes or 0.0))
    percent = min(100.0, (current * 100.0 / total)) if total else 0.0
    elapsed = max(0.001, now - start_time)
    speed = current / elapsed
    eta = max(0, int((total - current) / speed)) if speed > 0 and total >= current else 0
    minutes, seconds = divmod(eta, 60)
    eta_text = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
    completed = max(0, min(24, int(percent / 100.0 * 24)))
    bar = "█" * completed + "░" * (24 - completed)

    try:
        await status.edit_text(
            "📥 **Download Progress**\n"
            f"{bar} {percent:.2f}%\n\n"
            f"📦 Size: `{humanbytes(current)}` / `{humanbytes(total)}`\n"
            f"🚀 Speed: `{humanbytes(speed)}/s`\n"
            f"⏱ ETA: `{eta_text}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job.job_id}")]]),
        )
        job._last_processing_progress = now
        await protect_transfer_message(status)
    except Exception:
        pass


def _initial_download_text(expected_size: int) -> str:
    total = max(0, int(expected_size or 0))
    return (
        "📥 **Download Progress**\n"
        "░" * 24 + " 0.00%\n\n"
        f"📦 Size: `0 B` / `{humanbytes(total)}`\n"
        "🚀 Speed: `0 B/s`\n"
        "⏱ ETA: calculating..."
    )


async def _new_transfer_status(message, job, expected_size):
    status = await message.reply_text(
        _initial_download_text(expected_size),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job.job_id}")]]),
    )
    await protect_transfer_message(status)
    reset_progress(job.job_id)
    await progress_for_pyrogram(0, expected_size, "Downloading", status, time.time(), job.job_id)
    await protect_transfer_message(status)
    return status


async def _cleanup_successful_user_input(client, message, job):
    ids = [job.source_message_id, getattr(message, "id", None)]
    await delete_user_job_messages(client, message.chat.id, ids)


async def _finish_delivery(client, message, job, status, name, size, success_text):
    """Remove only the transfer/progress message after a successful delivery.

    The uploaded result is never deleted here. Progress stays visible during the
    entire upload, including 100%, and disappears only after Telegram has
    returned the uploaded result successfully.
    """
    await protect_result(status)
    await _cleanup_successful_user_input(client, message, job)
    try:
        await client.delete_messages(status.chat.id, status.id)
    except Exception:
        # If deletion is temporarily unavailable, leave the completed status in
        # place rather than risking deletion of any uploaded result.
        pass


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

        expected_size = int((job.extra or {}).get("telegram_file_size", 0) or 0)
        status = await _new_transfer_status(message, job, expected_size)
        try:
            await _download_source(client, message, job, status)

            # Keep the Download Progress message visible during local preparation.
            # The upload callback replaces this exact message with Upload Progress
            # when Telegram upload actually begins.
            job._last_processing_progress = 0.0
            processing_start = time.time()
            output_path = os.path.join(job.work_dir, name)
            input_size = max(1, os.path.getsize(job.input_path))

            async def processing_callback(_current_seconds, _total_seconds):
                current_size = os.path.getsize(output_path) if os.path.isfile(output_path) else 0
                await _processing_progress(status, job, current_size, input_size, processing_start)

            if not await convert_media(job.input_path, output_path, ext, progress_callback=processing_callback):
                raise RuntimeError("FFmpeg conversion failed")

            final_size = os.path.getsize(output_path) if os.path.isfile(output_path) else input_size
            await _processing_progress(status, job, final_size, input_size, processing_start, force=True)
            await protect_transfer_message(status)

            results = await _deliver_output(client, job, output_path, name, status)
            for result in results or []:
                await protect_result(result)
            if not results:
                raise RuntimeError("Telegram returned no uploaded result")

            size = os.path.getsize(output_path)
            await db.update_usage(job.user_id, job.bot_id, size)
            await _finish_delivery(client, message, job, status, name, size, f"✅ **Conversion Complete!**\n\n📂 `{name}`\n📦 `{humanbytes(size)}`")
        except AniToonTransferCancelled:
            await status.edit_text("❌ **Processing cancelled.**")
            await protect_transfer_message(status)
        except Exception as exc:
            await status.edit_text(f"❌ **Conversion failed**\n\n`{str(exc)[:1000]}`")
            await protect_transfer_message(status)
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
        expected_size = int((job.extra or {}).get("telegram_file_size", 0) or 0)
        status = await _new_transfer_status(message, job, expected_size)
        try:
            await _download_source(client, message, job, status)

            # Keep Download Progress visible while the local file is prepared;
            # do not display a separate Processing message.
            os.replace(job.input_path, output_path)
            if job.extra.get("rename_output_mode") == "video":
                job.mime_type = "video/mp4"

            results = await _deliver_output(client, job, output_path, name, status)
            for result in results or []:
                await protect_result(result)
            if not results:
                raise RuntimeError("Telegram returned no uploaded result")

            size = os.path.getsize(output_path)
            await db.update_usage(job.user_id, job.bot_id, size)
            await _finish_delivery(client, message, job, status, name, size, f"✅ **Rename Complete!**\n\n📂 `{name}`\n📦 `{humanbytes(size)}`")
        except AniToonTransferCancelled:
            await status.edit_text("❌ **Processing cancelled.**")
            await protect_transfer_message(status)
        except Exception as exc:
            await status.edit_text(f"❌ **Processing failed**\n\n`{str(exc)[:1000]}`")
            await protect_transfer_message(status)
        finally:
            clear_transfer_cancel(job.job_id)
            shutil.rmtree(job.work_dir, ignore_errors=True)
            await jobs.remove(job.job_id)
        raise StopPropagation

from __future__ import annotations

import asyncio
import os
import shutil

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from helper.activity_log import mark_rename_completed
from helper.cancel_manager import register_task, unregister_task
from helper.database import db
from helper.ffmpeg import convert_media, prepare_video_for_telegram
from helper.job_state import jobs
from helper.job_transfer import download_job
from helper.message_cleanup import protect_result, protect_transfer_message
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes, progress_for_pyrogram, reset_progress
from plugins.file_action_fix import _deliver_output
from plugins.rename import _base_without_extension, _extension, _safe_filename

NAME_ACTIONS = {"custom_name", "convert_name"}


async def _find_name_job(user_id: int, message=None):
    jobs_for_user = await jobs.get_user_jobs(user_id)
    reply_id = getattr(getattr(message, "reply_to_message", None), "id", None) if message else None
    if reply_id:
        for job in jobs_for_user:
            if getattr(job, "selected_action", None) in NAME_ACTIONS and not job.extra.get("name_submitted"):
                if int((job.extra or {}).get("rename_prompt_message_id", 0) or 0) == int(reply_id):
                    return job
    for job in jobs_for_user:
        if getattr(job, "selected_action", None) in NAME_ACTIONS and not job.extra.get("name_submitted"):
            return job
    return None


async def _download_source(client, message, job, status):
    source = (job.extra or {}).get("source_message") or (job.extra or {}).get("file_id")
    if not source:
        source = await client.get_messages(message.chat.id, job.source_message_id)
    if not source:
        raise RuntimeError("Original file could not be located")
    return await download_job(client, source, job, status)


def _initial_download_text(expected_size: int) -> str:
    total = max(0, int(expected_size or 0))
    return "📥 **Download Progress**\n" + "░" * 24 + " 0.00%\n\n" + f"📦 Size: `0 B` / `{humanbytes(total)}`\n🚀 Speed: `0 B/s`\n⏱ ETA: calculating..."


async def _delete_message_safely(client, chat_id, message_id):
    if message_id:
        try: await client.delete_messages(chat_id, int(message_id))
        except Exception: pass


async def _new_transfer_status(client, message, job, expected_size):
    status = await message.reply_text(_initial_download_text(expected_size), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏸️ Pause", callback_data=f"transfer:pause:{job.job_id}"), InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job.job_id}")]]))
    await protect_transfer_message(status)
    reset_progress(job.job_id)
    return status


async def _conversion_progress(current: float, total: float, status, job_id: str, label: str):
    if not total or status is None: return
    percent = max(0.0, min(99.9, (float(current) * 100.0) / float(total)))
    try:
        filled = max(0, min(24, int(percent / 100 * 24)))
        await status.edit_text("⚙️ **Converting Video**\n" + "█" * filled + "░" * (24 - filled) + f" {percent:.1f}%\n\n📂 `{label}`\n🎬 The final result will be sent as a playable Telegram video.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]]))
    except Exception: pass


async def _convert_with_progress(job, status, output_path, output_format, label):
    async def report(current, total): await _conversion_progress(current, total, status, job.job_id, label)
    task = await register_task(job.job_id)
    try: return await convert_media(job.input_path, output_path, output_format, report)
    finally: await unregister_task(job.job_id, task)


async def _finish_delivery(client, message, job, status):
    await protect_result(status)
    await _delete_message_safely(client, message.chat.id, (job.extra or {}).get("rename_prompt_message_id"))
    await _delete_message_safely(client, status.chat.id, status.id)


async def _process_named_job(client, message, job):
    action = job.selected_action
    text = message.text.strip()

    if action == "convert_name":
        ext = job.output_ext
        if not ext: raise RuntimeError("Output format is missing")
        name = _safe_filename(text)
        if _extension(name) != ext: name = f"{_base_without_extension(name)}.{ext}"
        status = await _new_transfer_status(client, message, job, int((job.extra or {}).get("telegram_file_size", 0) or 0))
        try:
            await _download_source(client, message, job, status)
            output_path = os.path.join(job.work_dir, name)
            if not await _convert_with_progress(job, status, output_path, ext, name): raise RuntimeError("FFmpeg conversion failed")
            results = await _deliver_output(client, job, output_path, name, status)
            if not results: raise RuntimeError("Telegram returned no uploaded result")
            size = int((job.extra or {}).get("downloaded_size", 0) or os.path.getsize(job.input_path))
            await db.update_usage(job.user_id, job.bot_id, size)
            await mark_rename_completed(job.job_id)
            await _finish_delivery(client, message, job, status)
        except AniToonTransferCancelled:
            try: await status.edit_text("❌ **Processing cancelled.**")
            except Exception: pass
        except asyncio.CancelledError:
            try: await status.edit_text("❌ **Processing cancelled.**")
            except Exception: pass
        except Exception as exc:
            try: await status.edit_text(f"❌ **Conversion failed**\n\n`{str(exc)[:1000]}`")
            except Exception: pass
        finally:
            clear_transfer_cancel(job.job_id); shutil.rmtree(job.work_dir, ignore_errors=True); await jobs.remove(job.job_id)
        return

    if action == "custom_name":
        source_ext = _extension(job.original_name)
        video_mode = (job.extra or {}).get("rename_output_mode") == "video"
        if video_mode:
            name = f"{_base_without_extension(_safe_filename(text))}.mp4"
        else:
            name = _safe_filename(text)
            if not _extension(name) and source_ext: name = f"{name}.{source_ext}"
            elif _extension(name) and source_ext: name = f"{_base_without_extension(name)}.{source_ext}"

        status = await _new_transfer_status(client, message, job, int((job.extra or {}).get("telegram_file_size", 0) or 0))
        try:
            await _download_source(client, message, job, status)

            if video_mode:
                prepared_path = os.path.join(job.work_dir, ".converted_video.mp4")
                async def report(current, total):
                    await _conversion_progress(current, total, status, job.job_id, name)
                prepared = await prepare_video_for_telegram(job.input_path, prepared_path, report)
                if not prepared or not os.path.isfile(prepared):
                    raise RuntimeError("Could not convert the source into a Telegram-compatible MP4 video")
                job.mime_type = "video/mp4"
                results = await _deliver_output(client, job, prepared, name, status, prepared_video=True)
            else:
                output_path = os.path.join(job.work_dir, name)
                os.replace(job.input_path, output_path)
                results = await _deliver_output(client, job, output_path, name, status)

            if not results: raise RuntimeError("Telegram returned no uploaded result")
            size = int((job.extra or {}).get("downloaded_size", 0) or os.path.getsize(job.input_path if os.path.exists(job.input_path) else prepared if video_mode else output_path))
            await db.update_usage(job.user_id, job.bot_id, size)
            await mark_rename_completed(job.job_id)
            await _finish_delivery(client, message, job, status)
        except AniToonTransferCancelled:
            try: await status.edit_text("❌ **Processing cancelled.**")
            except Exception: pass
        except asyncio.CancelledError:
            try: await status.edit_text("❌ **Processing cancelled.**")
            except Exception: pass
        except Exception as exc:
            try: await status.edit_text(f"❌ **Rename failed**\n\n`{str(exc)[:1000]}`")
            except Exception: pass
        finally:
            clear_transfer_cancel(job.job_id); shutil.rmtree(job.work_dir, ignore_errors=True); await jobs.remove(job.job_id)


@Client.on_message(filters.private & filters.text, group=-1200)
async def reliable_rename_reply(client, message):
    if not message.text or message.text.startswith("/"): return
    job = await _find_name_job(message.from_user.id, message)
    if not job: return
    text = message.text.strip()
    if not text:
        await _delete_message_safely(client, message.chat.id, message.id); raise StopPropagation
    await jobs.update(job.job_id, extra={**job.extra, "name_submitted": True})
    queue_position = await jobs.user_queue_position(job.job_id)
    queue_message = None
    if queue_position > 0:
        queue_message = await message.reply_text(f"⏳ **Added to queue — position #{queue_position}**\n\nThe previous file is still processing. This file will start automatically when its turn arrives.")
    user_lock = await jobs.user_lock(message.from_user.id)
    async with user_lock:
        current = await jobs.get(job.job_id)
        if not current: return
        if queue_message:
            try: await queue_message.edit_text("▶️ **Your file is now starting...**")
            except Exception: pass
        task = await register_task(job.job_id)
        try: await _process_named_job(client, message, current)
        finally: await unregister_task(job.job_id, task)
    raise StopPropagation

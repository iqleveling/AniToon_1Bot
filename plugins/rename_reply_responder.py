from __future__ import annotations

import asyncio
import os
import shutil
import time

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from helper.database import db
from helper.ffmpeg import convert_media
from helper.job_state import jobs
from helper.job_transfer import download_job
from helper.message_cleanup import protect_result, protect_transfer_message
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes, progress_for_pyrogram, reset_progress
from plugins.file_action_fix import _deliver_output
from plugins.rename import _base_without_extension, _extension, _safe_filename

NAME_ACTIONS = {"custom_name", "convert_name"}


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


def _initial_download_text(expected_size: int) -> str:
    total = max(0, int(expected_size or 0))
    return (
        "📥 **Download Progress**\n"
        "░" * 24 + " 0.00%\n\n"
        f"📦 Size: `0 B` / `{humanbytes(total)}`\n"
        "🚀 Speed: `0 B/s`\n"
        "⏱ ETA: calculating..."
    )


async def _delete_message_safely(client, chat_id, message_id):
    if not message_id:
        return
    try:
        await client.delete_messages(chat_id, int(message_id))
    except Exception:
        pass


async def _new_transfer_status(client, message, job, expected_size):
    status = await message.reply_text(
        _initial_download_text(expected_size),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job.job_id}")]]),
    )
    await protect_transfer_message(status)
    reset_progress(job.job_id)
    await progress_for_pyrogram(0, expected_size, "Downloading", status, time.time(), job.job_id)
    await protect_transfer_message(status)
    await _delete_message_safely(client, message.chat.id, message.id)
    return status


async def _conversion_progress(current: float, total: float, status, job_id: str, label: str):
    if not total or status is None:
        return
    percent = max(0.0, min(99.9, (float(current) * 100.0) / float(total)))
    try:
        filled = max(0, min(24, int(percent / 100 * 24)))
        await status.edit_text(
            "⚙️ **Converting**\n"
            + ("█" * filled)
            + ("░" * (24 - filled))
            + f" {percent:.1f}%\n\n"
            f"📂 `{label}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]]),
        )
    except Exception:
        pass


async def _convert_with_progress(job, status, output_path, output_format, label):
    async def report(current, total):
        await _conversion_progress(current, total, status, job.job_id, label)
    return await convert_media(job.input_path, output_path, output_format, report)


async def _finish_delivery(client, message, job, status):
    await protect_result(status)
    await _delete_message_safely(client, message.chat.id, (job.extra or {}).get("rename_prompt_message_id"))
    await _delete_message_safely(client, status.chat.id, status.id)


async def _convert_rename_to_video(job, name: str, status):
    if job.extra.get("rename_output_mode") != "video":
        return os.path.join(job.work_dir, name)
    if _extension(job.original_name) == "mp4":
        return os.path.join(job.work_dir, name)
    output_path = os.path.join(job.work_dir, f".rename_video_{job.job_id}.mp4")
    if not await _convert_with_progress(job, status, output_path, "mp4", name):
        raise RuntimeError("Could not convert the renamed source into MP4 video")
    return output_path


@Client.on_message(filters.private & filters.text, group=-1200)
async def reliable_rename_reply(client, message):
    if not message.text or message.text.startswith("/"):
        return

    job = await _find_name_job(message.from_user.id)
    if not job:
        return

    text = message.text.strip()
    if not text:
        await _delete_message_safely(client, message.chat.id, getattr(message, "id", None))
        raise StopPropagation

    action = getattr(job, "selected_action", None)

    if action == "convert_name":
        ext = getattr(job, "output_ext", None)
        if not ext:
            await _delete_message_safely(client, message.chat.id, getattr(message, "id", None))
            raise StopPropagation
        name = _safe_filename(text)
        if _extension(name) != ext:
            name = f"{_base_without_extension(name)}.{ext}"
        expected_size = int((job.extra or {}).get("telegram_file_size", 0) or 0)
        status = await _new_transfer_status(client, message, job, expected_size)
        try:
            await _download_source(client, message, job, status)
            output_path = os.path.join(job.work_dir, name)
            if not await _convert_with_progress(job, status, output_path, ext, name):
                raise RuntimeError("FFmpeg conversion failed")
            results = await _deliver_output(client, job, output_path, name, status)
            for result in results or []:
                await protect_result(result)
            if not results:
                raise RuntimeError("Telegram returned no uploaded result")
            await db.update_usage(job.user_id, job.bot_id, os.path.getsize(output_path))
            await _finish_delivery(client, message, job, status)
        except AniToonTransferCancelled:
            await status.edit_text("❌ **Processing cancelled.**")
            await protect_transfer_message(status)
        except asyncio.CancelledError:
            clear_transfer_cancel(job.job_id)
            try:
                await status.edit_text("❌ **Processing cancelled.**")
            except Exception:
                pass
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

        status = await _new_transfer_status(client, message, job, int((job.extra or {}).get("telegram_file_size", 0) or 0))
        try:
            await _download_source(client, message, job, status)
            if job.extra.get("rename_output_mode") == "video":
                video_path = await _convert_rename_to_video(job, name, status)
                if video_path != os.path.join(job.work_dir, name):
                    name = f"{_base_without_extension(name)}.mp4"
                    output_path = os.path.join(job.work_dir, name)
                    os.replace(video_path, output_path)
                else:
                    output_path = video_path
                job.mime_type = "video/mp4"
            else:
                output_path = os.path.join(job.work_dir, name)
                os.replace(job.input_path, output_path)

            results = await _deliver_output(client, job, output_path, name, status)
            for result in results or []:
                await protect_result(result)
            if not results:
                raise RuntimeError("Telegram returned no uploaded result")
            await db.update_usage(job.user_id, job.bot_id, os.path.getsize(output_path))
            await _finish_delivery(client, message, job, status)
        except AniToonTransferCancelled:
            await status.edit_text("❌ **Processing cancelled.**")
            await protect_transfer_message(status)
        except asyncio.CancelledError:
            clear_transfer_cancel(job.job_id)
            try:
                await status.edit_text("❌ **Processing cancelled.**")
            except Exception:
                pass
        except Exception as exc:
            await status.edit_text(f"❌ **Rename failed**\n\n`{str(exc)[:1000]}`")
            await protect_transfer_message(status)
        finally:
            clear_transfer_cancel(job.job_id)
            shutil.rmtree(job.work_dir, ignore_errors=True)
            await jobs.remove(job.job_id)
        raise StopPropagation

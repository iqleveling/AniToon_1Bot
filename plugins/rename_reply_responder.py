from __future__ import annotations

import os
import shutil

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from helper.database import db
from helper.job_transfer import download_job
from helper.job_state import jobs
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes
from plugins.file_action_fix import _deliver_output
from plugins.rename import _base_without_extension, _extension, _safe_filename
from helper.ffmpeg import convert_media


NAME_ACTIONS = {"custom_name", "convert_name"}


async def _find_name_job(user_id: int):
    """Find the active rename/convert job instead of assuming the first job is it."""
    try:
        user_jobs = await jobs.get_user_jobs(user_id)
    except Exception:
        user_jobs = []
    for job in user_jobs:
        if getattr(job, "selected_action", None) in NAME_ACTIONS:
            return job
    return None


@Client.on_message(filters.private & filters.text, group=-1200)
async def reliable_rename_reply(client: Client, message: Message):
    """Accept the filename whether Telegram sends it as a ForceReply or plain text.

    The active job state is authoritative. This also runs before the older rename
    handlers so duplicate handlers cannot consume the filename first.
    """
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
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job.job_id}")]]
            ),
        )
        try:
            source = await client.get_messages(message.chat.id, job.source_message_id)
            if not source:
                raise RuntimeError("Original file message could not be found")

            await download_job(client, source, job, status)
            await status.edit_text("⚙️ **Processing...**")

            output_path = os.path.join(job.work_dir, name)
            if not await convert_media(job.input_path, output_path, ext):
                raise RuntimeError("FFmpeg conversion failed")

            await _deliver_output(client, job, output_path, name, status)
            await db.update_usage(job.user_id, job.bot_id, os.path.getsize(output_path))
            await status.edit_text(
                f"✅ **Conversion Complete!**\n\n📂 `{name}`\n📦 `{humanbytes(os.path.getsize(output_path))}`"
            )
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
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job.job_id}")]]
            ),
        )
        try:
            source = await client.get_messages(message.chat.id, job.source_message_id)
            if not source:
                raise RuntimeError("Original file message could not be found")

            await download_job(client, source, job, status)
            os.replace(job.input_path, output_path)

            if job.extra.get("rename_output_mode") == "video":
                job.mime_type = "video/mp4"

            await _deliver_output(client, job, output_path, name, status)
            await db.update_usage(job.user_id, job.bot_id, os.path.getsize(output_path))
            await status.edit_text(
                f"✅ **Rename Complete!**\n\n📂 `{name}`\n📦 `{humanbytes(os.path.getsize(output_path))}`"
            )
        except AniToonTransferCancelled:
            await status.edit_text("❌ **Processing cancelled.**")
        except Exception as exc:
            await status.edit_text(f"❌ **Processing failed**\n\n`{str(exc)[:1000]}`")
        finally:
            clear_transfer_cancel(job.job_id)
            shutil.rmtree(job.work_dir, ignore_errors=True)
            await jobs.remove(job.job_id)

        raise StopPropagation

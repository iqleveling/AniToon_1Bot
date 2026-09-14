from __future__ import annotations

import asyncio
import os
import shutil
import time
import uuid

from pyrogram import Client, StopPropagation, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from helper.database import db
from helper.ffmpeg import convert_media
from helper.job_state import Job, jobs
from helper.job_transfer import download_job
from helper.plans import get_plan
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes, progress_for_pyrogram
from plugins.rename import (
    _ask_name,
    _base_without_extension,
    _detect_name,
    _extension,
    _media_from_message,
    _safe_filename,
    _user_context,
)
from plugins.ui import file_action_menu


VIDEO_MIME = {"mp4": "video/mp4", "mkv": "video/x-matroska", "webm": "video/webm", "mov": "video/quicktime"}
AUDIO_MIME = {"mp3": "audio/mpeg", "m4a": "audio/mp4"}
WAITING_ACTIONS = {"rename_format", "custom_name", "convert_name", "rename_output_choice", "convert_menu"}


async def _send_plain_output(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    ext = _extension(filename)
    mime = job.mime_type or ""
    caption = (
        "✅ **AniToon Processed**\n\n"
        f"📂 `{filename}`\n"
        f"📦 `{humanbytes(os.path.getsize(path))}`"
    )
    progress = progress_for_pyrogram if status else None
    args = ("📤 Uploading", status, time.time(), job.job_id) if status else None
    if mime.startswith("video/") or ext in {"mp4", "mkv", "webm", "mov", "avi", "flv", "ts", "m4v"}:
        try:
            return await client.send_video(job.user_id, path, caption=caption, progress=progress, progress_args=args) if progress else await client.send_video(job.user_id, path, caption=caption)
        except Exception:
            return await client.send_document(job.user_id, path, caption=caption, progress=progress, progress_args=args) if progress else await client.send_document(job.user_id, path, caption=caption)
    if mime.startswith("audio/") or ext in {"mp3", "m4a", "aac", "flac", "ogg", "wav", "opus"}:
        try:
            return await client.send_audio(job.user_id, path, caption=caption, progress=progress, progress_args=args) if progress else await client.send_audio(job.user_id, path, caption=caption)
        except Exception:
            return await client.send_document(job.user_id, path, caption=caption, progress=progress, progress_args=args) if progress else await client.send_document(job.user_id, path, caption=caption)
    return await client.send_document(job.user_id, path, caption=caption, progress=progress, progress_args=args) if progress else await client.send_document(job.user_id, path, caption=caption)


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio), group=-1000)
async def repaired_file_download(client: Client, message: Message):
    """Create the job and ask for the operation BEFORE downloading the file."""
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
    original_name = _safe_filename(getattr(media, "file_name", None) or f"file_{message.id}")
    extension = _extension(original_name)
    mime_type = getattr(media, "mime_type", None) or ""

    if used >= plan.daily_limit:
        await message.reply_text(
            "🚫 **Daily Limit Reached!**\n\n"
            f"Current Plan: {plan.name}\nDaily Limit: `{humanbytes(plan.daily_limit)}`\nUsed: `{humanbytes(used)}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Upgrade", callback_data="upgrade")]]),
        )
        raise StopPropagation

    job_id = uuid.uuid4().hex[:12]
    work_dir = os.path.join("downloads", str(user_id), job_id)
    os.makedirs(work_dir, exist_ok=True)
    input_path = os.path.join(work_dir, original_name)
    job = Job(
        job_id=job_id, user_id=user_id, bot_id=bot_id, source_message_id=message.id,
        work_dir=work_dir, input_path=input_path, original_name=original_name, mime_type=mime_type,
        extra={"extension": extension, "user_data": user_data, "used_before": used, "telegram_file_size": expected_size},
    )
    if not await jobs.register(job):
        await message.reply_text("⏳ **You already have an active file job.**\n\nPlease finish or cancel it first.")
        raise StopPropagation

    status = await message.reply_text(
        "🎯 **File received**\n\n"
        f"📂 `{original_name}`\n"
        f"📦 `{humanbytes(expected_size)}`\n\n"
        "Choose an operation **before downloading**:",
        reply_markup=file_action_menu(job_id),
    )
    await jobs.update(job_id, extra={**job.extra, "status_message_id": status.id})
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"), group=-1000)
async def rename_entry_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation
    await cb.answer()
    await jobs.update(job.job_id, selected_action="custom_name")
    await _ask_name(client, job.user_id, "✏️ **Rename**\n\nSend me the new filename.", job.job_id, "custom_name")
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:renameformat:([0-9a-f]+):(document|video)$"), group=-1000)
async def rename_format_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation
    mode = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, extra={**job.extra, "rename_output_mode": mode})
    job.mime_type = "video/mp4" if mode == "video" else "application/octet-stream"
    await _ask_name(client, job.user_id, "✏️ **Rename**\n\nSend me the new filename.", job.job_id, "custom_name")
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:format:([0-9a-f]+):(mp4|mkv|webm|mov|mp3|m4a)$"), group=-1000)
async def convert_entry_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation
    fmt = cb.matches[0].group(2)
    await cb.answer()
    job.output_ext = fmt
    job.mime_type = VIDEO_MIME.get(fmt) or AUDIO_MIME.get(fmt) or "application/octet-stream"
    await _ask_name(
        client, job.user_id,
        f"🔄 **Convert to {fmt.upper()}**\n\nEnter the output filename.\nThe `.{fmt}` extension will be used.",
        job.job_id, "convert_name",
    )
    raise StopPropagation


@Client.on_message(filters.private & filters.reply & filters.text, group=-1000)
async def rename_reply_fix(client, message: Message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in {"custom_name", "convert_name"}:
        return
    text = (message.text or "").strip()
    if not text:
        await message.reply_text("❌ **Please send a valid filename.**")
        raise StopPropagation

    if job.selected_action == "convert_name":
        ext = job.output_ext
        if not ext:
            await message.reply_text("❌ **Conversion format expired. Please select Convert again.**")
            raise StopPropagation
        name = _safe_filename(text)
        if _extension(name) != ext:
            name = f"{_base_without_extension(name)}.{ext}"
        status = await message.reply_text("⏳ **Preparing conversion...**")
        try:
            await download_job(client, await client.get_messages(message.chat.id, job.source_message_id), job, status)
            ok = await convert_media(job.input_path, os.path.join(job.work_dir, name), ext)
            if not ok:
                raise RuntimeError("FFmpeg conversion failed")
            output_path = os.path.join(job.work_dir, name)
            await status.edit_text("📤 **Sending converted file...**")
            await _send_plain_output(client, job, output_path, name, status)
            await db.update_usage(job.user_id, job.bot_id, os.path.getsize(job.input_path))
            await status.edit_text(f"✅ **Conversion Complete!**\n\n📂 `{name}`\n📦 `{humanbytes(os.path.getsize(output_path))}`")
        except AniToonTransferCancelled:
            await status.edit_text("❌ **Processing cancelled.**")
        except Exception as exc:
            await status.edit_text(f"❌ **Conversion failed**\n\n`{str(exc)[:1000]}`")
        finally:
            clear_transfer_cancel(job.job_id)
            shutil.rmtree(job.work_dir, ignore_errors=True)
            await jobs.remove(job.job_id)
        raise StopPropagation

    ext = _extension(job.original_name)
    name = _safe_filename(text)
    if not _extension(name) and ext:
        name = f"{name}.{ext}"
    elif _extension(name) and ext:
        name = f"{_base_without_extension(name)}.{ext}"
    output_path = os.path.join(job.work_dir, name)
    status = await message.reply_text("⏳ **Preparing renamed file...**")
    try:
        await download_job(client, await client.get_messages(message.chat.id, job.source_message_id), job, status)
        shutil.copy2(job.input_path, output_path)
        await status.edit_text("📤 **Sending renamed file...**")
        await _send_plain_output(client, job, output_path, name, status)
        await db.update_usage(job.user_id, job.bot_id, os.path.getsize(job.input_path))
        await status.edit_text(f"✅ **Rename Complete!**\n\n📂 `{name}`\n📦 `{humanbytes(os.path.getsize(output_path))}`")
    except AniToonTransferCancelled:
        await status.edit_text("❌ **Processing cancelled.**")
    except Exception as exc:
        await status.edit_text(f"❌ **Processing failed**\n\n`{str(exc)[:1000]}`")
    finally:
        clear_transfer_cancel(job.job_id)
        shutil.rmtree(job.work_dir, ignore_errors=True)
        await jobs.remove(job.job_id)
    raise StopPropagation


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio), group=-999)
async def retry_file_when_waiting(client, message: Message):
    """Cancel the previous prompt when a new file arrives."""
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in WAITING_ACTIONS:
        return
    shutil.rmtree(job.work_dir, ignore_errors=True)
    await jobs.remove(job.job_id)
    await message.reply_text("🔄 **Previous file job cleared.** Send the new file again to choose an operation.")
    raise StopPropagation

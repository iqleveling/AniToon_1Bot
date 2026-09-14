from __future__ import annotations

import asyncio
import os
import shutil
import time
import uuid

from pyrogram import Client, StopPropagation, filters
from pyrogram.errors import RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from helper.archive_result import archive_message
from helper.database import db
from helper.ffmpeg import convert_media, get_video_info, make_streamable
from helper.job_state import Job, jobs
from helper.job_transfer import download_job
from helper.large_video import is_large_video, make_thumbnail, split_video_for_telegram
from helper.plans import get_plan
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes, progress_for_pyrogram, reset_progress
from plugins.rename import (
    _ask_name,
    _base_without_extension,
    _extension,
    _media_from_message,
    _safe_filename,
    _user_context,
)
from plugins.ui import file_action_menu

VIDEO_MIME = {"mp4": "video/mp4", "mkv": "video/x-matroska", "webm": "video/webm", "mov": "video/quicktime"}
AUDIO_MIME = {"mp3": "audio/mpeg", "m4a": "audio/mp4"}
WAITING_ACTIONS = {"rename_format", "custom_name", "convert_name", "rename_output_choice", "convert_menu"}
VIDEO_EXTENSIONS = {"mp4", "mkv", "webm", "mov", "avi", "flv", "ts", "m4v"}


async def _send_video(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    """Send a native Telegram video, with metadata/thumbnail and a safe fallback."""
    upload_path = path
    upload_name = filename
    ext = _extension(filename)

    if ext != "mp4":
        mp4_name = f"{_base_without_extension(filename)}.mp4"
        mp4_path = os.path.join(job.work_dir, f".upload_{uuid.uuid4().hex}.mp4")
        if not await convert_media(path, mp4_path, "mp4"):
            raise RuntimeError("Could not create a Telegram-compatible MP4 video")
        upload_path = mp4_path
        upload_name = mp4_name

    stream_path = os.path.join(job.work_dir, f".stream_{uuid.uuid4().hex}.mp4")
    ready = await make_streamable(upload_path, stream_path)
    if ready and os.path.isfile(ready) and os.path.getsize(ready) > 0:
        upload_path = ready

    duration, width, height = await get_video_info(upload_path)
    if not duration or not width or not height:
        raise RuntimeError("Video metadata could not be read after processing")

    thumb = await make_thumbnail(upload_path, job.work_dir)
    progress = progress_for_pyrogram if status else None
    progress_args = ("Uploading", status, time.time(), job.job_id) if status else None
    reset_progress(job.job_id)

    kwargs = {
        "caption": None,
        "duration": max(1, int(round(duration))),
        "width": int(width),
        "height": int(height),
        "supports_streaming": True,
        "file_name": upload_name,
    }
    if thumb:
        kwargs["thumb"] = thumb
    if progress:
        kwargs["progress"] = progress
        kwargs["progress_args"] = progress_args

    try:
        return await client.send_video(job.user_id, upload_path, **kwargs)
    except Exception as first_error:
        # Some Telegram media/codec combinations are rejected as a native
        # video. The same processed bytes remain valid as a document.
        try:
            document_kwargs = {"caption": None, "file_name": upload_name}
            if thumb:
                document_kwargs["thumb"] = thumb
            if progress:
                document_kwargs["progress"] = progress
                document_kwargs["progress_args"] = progress_args
            return await client.send_document(job.user_id, upload_path, **document_kwargs)
        except Exception as second_error:
            raise RuntimeError(
                f"Video upload failed: {str(first_error)[:700]} | document fallback: {str(second_error)[:700]}"
            ) from second_error


async def _send_plain_output(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    ext = _extension(filename)
    mime = job.mime_type or ""
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise RuntimeError("Processed output is missing or empty")

    if mime.startswith("video/") or ext in VIDEO_EXTENSIONS:
        return await _send_video(client, job, path, filename, status)

    progress = progress_for_pyrogram if status else None
    args = ("Uploading", status, time.time(), job.job_id) if status else None
    if mime.startswith("audio/") or ext in {"mp3", "m4a", "aac", "flac", "ogg", "wav", "opus"}:
        try:
            return await client.send_audio(job.user_id, path, caption=None, progress=progress, progress_args=args) if progress else await client.send_audio(job.user_id, path, caption=None)
        except RPCError:
            return await client.send_document(job.user_id, path, caption=None, progress=progress, progress_args=args) if progress else await client.send_document(job.user_id, path, caption=None)

    return await client.send_document(job.user_id, path, caption=None, progress=progress, progress_args=args) if progress else await client.send_document(job.user_id, path, caption=None)


async def _deliver_video_parts(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    """Deliver a normal video or split a >2GB-class video into safe parts."""
    if not is_large_video(path):
        sent = await _send_plain_output(client, job, path, filename, status)
        if sent:
            await archive_message(client, sent)
        return [sent]

    parts = await split_video_for_telegram(path, job.work_dir, filename)
    sent_messages = []
    total = len(parts)
    for index, part in enumerate(parts, 1):
        if status:
            await status.edit_text(f"📤 **Uploading part {index}/{total}...**")
        part_name = os.path.basename(part)
        sent = await _send_video(client, job, part, part_name, status)
        if not sent:
            raise RuntimeError(f"Upload returned no message for part {index}/{total}")
        sent_messages.append(sent)
        await archive_message(client, sent)
    return sent_messages


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
    file_id = getattr(media, "file_id", "") or ""

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

    text = (
        "📂 **File Detected**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📄 **Name**\n`{original_name}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 **Size**\n`{humanbytes(expected_size)}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 **File ID**\n`{file_id}`\n\n"
        "Choose an operation before downloading:"
    )
    status = await message.reply_text(text, reply_markup=file_action_menu(job_id))
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
    await _ask_name(client, job.user_id, "Enter new filename:", job.job_id, "custom_name")
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
    await _ask_name(client, job.user_id, "Enter new filename:", job.job_id, "custom_name")
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
    await _ask_name(client, job.user_id, f"Enter new filename for {fmt.upper()}:\nThe `.{fmt}` extension will be used.", job.job_id, "convert_name")
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
        status = await message.reply_text("📥 **Downloading...**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job.job_id}")]]))
        try:
            await download_job(client, await client.get_messages(message.chat.id, job.source_message_id), job, status)
            await status.edit_text("⚙️ **Processing...**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job.job_id}")]]))
            ok = await convert_media(job.input_path, os.path.join(job.work_dir, name), ext)
            if not ok:
                raise RuntimeError("FFmpeg conversion failed")
            output_path = os.path.join(job.work_dir, name)
            await _deliver_video_parts(client, job, output_path, name, status) if ext in VIDEO_MIME else await _send_plain_output(client, job, output_path, name, status)
            if ext not in VIDEO_MIME:
                await archive_message(client, await client.get_messages(job.user_id, status.id)) if False else None
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
    status = await message.reply_text("📥 **Downloading...**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job.job_id}")]]))
    try:
        await download_job(client, await client.get_messages(message.chat.id, job.source_message_id), job, status)
        os.replace(job.input_path, output_path)
        if job.extra.get("rename_output_mode") == "video":
            job.mime_type = "video/mp4"
        await _deliver_video_parts(client, job, output_path, name, status) if (job.mime_type.startswith("video/") or _extension(name) in VIDEO_EXTENSIONS) else _send_plain_output(client, job, output_path, name, status)
        await db.update_usage(job.user_id, job.bot_id, os.path.getsize(output_path))
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
async def retry_file_when_waiting(client: Client, message: Message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in WAITING_ACTIONS:
        return
    shutil.rmtree(job.work_dir, ignore_errors=True)
    await jobs.remove(job.job_id)
    await message.reply_text("🔄 **Previous file job cleared.** Send the new file again to choose an operation.")
    raise StopPropagation

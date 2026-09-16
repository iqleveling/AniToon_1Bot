from __future__ import annotations

import os
import shutil
import time
import uuid

from pyrogram import Client, StopPropagation, filters
from pyrogram.errors import RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from helper.archive_result import archive_message
from helper.database import db
from helper.ffmpeg import convert_media, get_video_info
from helper.job_state import Job, jobs
from helper.large_file import split_file_for_telegram
from helper.large_video import is_large_video, split_video_for_telegram
from helper.message_cleanup import protect_message, protect_result
from helper.plans import get_plan
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes, progress_for_pyrogram, reset_progress
from plugins.rename import _ask_name, _base_without_extension, _extension, _media_from_message, _safe_filename, _user_context
from plugins.ui import file_action_menu

VIDEO_MIME = {"mp4": "video/mp4", "mkv": "video/x-matroska", "webm": "video/webm", "mov": "video/quicktime"}
AUDIO_MIME = {"mp3": "audio/mpeg", "m4a": "audio/mp4"}
WAITING_ACTIONS = {"rename_format", "custom_name", "convert_name", "rename_output_choice", "convert_menu"}
VIDEO_EXTENSIONS = {"mp4", "mkv", "webm", "mov", "avi", "flv", "ts", "m4v"}


def _video_upload_name(filename: str) -> str:
    return f"{_base_without_extension(filename)}.mp4"


async def _prepare_video(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    """Prepare the minimum required data and return immediately to Telegram upload.

    The old pipeline generated an automatic thumbnail after download and performed
    extra FFmpeg work before upload. That made the visible download progress remain
    at 100% while Telegram was not receiving anything. We now probe metadata once,
    reuse a user's saved thumbnail when available, and otherwise send without a
    generated thumbnail so upload can begin immediately.
    """
    upload_path = path
    upload_name = _video_upload_name(filename)

    if _extension(filename) != "mp4":
        mp4_path = os.path.join(job.work_dir, f".upload_{uuid.uuid4().hex}.mp4")
        if not await convert_media(path, mp4_path, "mp4"):
            raise RuntimeError("Could not create a Telegram-compatible MP4 video")
        upload_path = mp4_path

    duration, width, height = await get_video_info(upload_path)
    if not duration or not width or not height:
        raise RuntimeError("Video metadata could not be read after processing")

    # A saved Telegram thumbnail is already available as a file_id. Reuse it
    # directly; never generate a new FFmpeg screenshot on the upload path.
    thumb = await db.get_thumbnail(job.user_id)
    return upload_path, upload_name, duration, width, height, thumb


async def _show_upload_start(job: Job, status: Message | None, path: str) -> None:
    if status is None:
        return
    total = max(1, os.path.getsize(path))
    reset_progress(job.job_id)
    await protect_message(status.chat.id, status.id)
    await progress_for_pyrogram(0, total, "Uploading", status, time.time(), job.job_id)


async def _send_video(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    upload_path, upload_name, duration, width, height, thumb = await _prepare_video(client, job, path, filename, status)
    progress = progress_for_pyrogram if status else None
    progress_args = ("Uploading", status, time.time(), job.job_id) if status else None

    await _show_upload_start(job, status, upload_path)
    if status:
        progress_args = ("Uploading", status, time.time(), job.job_id)

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
        # Keep a real upload path available even when Telegram rejects video
        # metadata/thumb parameters. A document fallback is the final safety net.
        try:
            reset_progress(job.job_id)
            if status:
                await protect_message(status.chat.id, status.id)
                await progress_for_pyrogram(0, max(1, os.path.getsize(upload_path)), "Uploading", status, time.time(), job.job_id)
            document_kwargs = {"caption": None, "file_name": upload_name}
            if progress:
                document_kwargs["progress"] = progress
                document_kwargs["progress_args"] = ("Uploading", status, time.time(), job.job_id)
            return await client.send_document(job.user_id, upload_path, **document_kwargs)
        except Exception as second_error:
            raise RuntimeError(f"Video upload failed: {str(first_error)[:700]} | document fallback: {str(second_error)[:700]}") from second_error


async def _send_plain_output(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    ext = _extension(filename)
    mime = job.mime_type or ""
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise RuntimeError("Processed output is missing or empty")

    progress = progress_for_pyrogram if status else None
    args = ("Uploading", status, time.time(), job.job_id) if status else None
    if status:
        await _show_upload_start(job, status, path)
        args = ("Uploading", status, time.time(), job.job_id)

    if mime.startswith("video/") or ext in VIDEO_EXTENSIONS:
        return await _send_video(client, job, path, filename, status)

    if mime.startswith("audio/") or ext in {"mp3", "m4a", "aac", "flac", "ogg", "wav", "opus"}:
        try:
            return await client.send_audio(job.user_id, path, caption=None, progress=progress, progress_args=args) if progress else await client.send_audio(job.user_id, path, caption=None)
        except RPCError:
            reset_progress(job.job_id)
            if status:
                await protect_message(status.chat.id, status.id)
                await progress_for_pyrogram(0, max(1, os.path.getsize(path)), "Uploading", status, time.time(), job.job_id)
            args = ("Uploading", status, time.time(), job.job_id) if status else None
            return await client.send_document(job.user_id, path, caption=None, progress=progress, progress_args=args) if progress else await client.send_document(job.user_id, path, caption=None)

    return await client.send_document(job.user_id, path, caption=None, progress=progress, progress_args=args) if progress else await client.send_document(job.user_id, path, caption=None)


async def _deliver_output(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    if (job.mime_type or "").startswith("video/") or _extension(filename) in VIDEO_EXTENSIONS:
        if is_large_video(path):
            parts = await split_video_for_telegram(path, job.work_dir, filename)
            sent_messages = []
            total = len(parts)
            for index, part in enumerate(parts, 1):
                sent = await _send_video(client, job, part, os.path.basename(part), status)
                if not sent:
                    raise RuntimeError(f"Upload returned no message for part {index}/{total}")
                await protect_result(sent)
                sent_messages.append(sent)
                await archive_message(client, sent)
            return sent_messages

    if os.path.getsize(path) > 0:
        parts = await split_file_for_telegram(path, job.work_dir, filename)
        if len(parts) > 1:
            sent_messages = []
            total = len(parts)
            for index, part in enumerate(parts, 1):
                part_name = os.path.basename(part)
                sent = await _send_plain_output(client, job, part, part_name, status)
                if not sent:
                    raise RuntimeError(f"Upload returned no message for part {index}/{total}")
                await protect_result(sent)
                sent_messages.append(sent)
                await archive_message(client, sent)
            return sent_messages

    sent = await _send_plain_output(client, job, path, filename, status)
    if sent:
        await protect_result(sent)
        await archive_message(client, sent)
    return [sent] if sent else []


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio), group=-1000)
async def repaired_file_download(client: Client, message: Message):
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
        await message.reply_text("🚫 **Daily Limit Reached!**\n\n" f"Current Plan: {plan.name}\nDaily Limit: `{humanbytes(plan.daily_limit)}`\nUsed: `{humanbytes(used)}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Upgrade", callback_data="upgrade")]]))
        raise StopPropagation

    job_id = uuid.uuid4().hex[:12]
    work_dir = os.path.join("downloads", str(user_id), job_id)
    os.makedirs(work_dir, exist_ok=True)
    input_path = os.path.join(work_dir, original_name)
    job = Job(job_id=job_id, user_id=user_id, bot_id=bot_id, source_message_id=message.id, work_dir=work_dir, input_path=input_path, original_name=original_name, mime_type=mime_type, extra={"extension": extension, "file_id": file_id, "source_message": message, "user_data": user_data, "used_before": used, "telegram_file_size": expected_size})
    if not await jobs.register(job):
        await message.reply_text("⏳ **You already have an active file job.**\n\nPlease finish or cancel it first.")
        raise StopPropagation

    await protect_message(message.chat.id, message.id)

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
    try:
        await cb.message.delete()
    except Exception:
        pass
    await jobs.update(job.job_id, selected_action="custom_name")
    prompt = await _ask_name(client, job.user_id, "✏️ **Rename:**\nSend me the new filename.", job.job_id, "custom_name")
    await jobs.update(job.job_id, extra={**job.extra, "rename_prompt_message_id": prompt.id})
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
    try:
        await cb.message.delete()
    except Exception:
        pass
    prompt = await _ask_name(client, job.user_id, "✏️ **Rename:**\nSend me the new filename.", job.job_id, "custom_name")
    await jobs.update(job.job_id, extra={**job.extra, "rename_prompt_message_id": prompt.id})
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
    try:
        await cb.message.delete()
    except Exception:
        pass
    prompt = await _ask_name(client, job.user_id, f"✏️ **Rename:**\nSend me the new filename for {fmt.upper()}.", job.job_id, "convert_name")
    await jobs.update(job.job_id, extra={**job.extra, "rename_prompt_message_id": prompt.id})
    raise StopPropagation


@Client.on_message(filters.private & filters.reply & filters.text, group=-1000)
async def rename_reply_fix(client, message: Message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in {"custom_name", "convert_name"}:
        return
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

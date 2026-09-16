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
from helper.ffmpeg import convert_media, get_video_info, prepare_video_for_telegram
from helper.job_state import Job, jobs
from helper.large_file import split_file_for_telegram
from helper.large_video import is_large_video, split_video_for_telegram
from helper.message_cleanup import protect_message, protect_result
from helper.plans import get_plan
from helper.utils import humanbytes
from plugins.rename import _ask_name, _base_without_extension, _extension, _media_from_message, _safe_filename, _user_context
from plugins.ui import file_action_menu

VIDEO_MIME = {"mp4": "video/mp4", "mkv": "video/x-matroska", "webm": "video/webm", "mov": "video/quicktime"}
AUDIO_MIME = {"mp3": "audio/mpeg", "m4a": "audio/mp4"}
WAITING_ACTIONS = {"rename_format", "custom_name", "convert_name", "rename_output_choice", "convert_menu"}
VIDEO_EXTENSIONS = {"mp4", "mkv", "webm", "mov", "avi", "flv", "ts", "m4v"}


def _video_upload_name(filename: str) -> str:
    return f"{_base_without_extension(filename)}.mp4"


async def _prepare_video(job: Job, path: str, filename: str):
    """Prepare a Telegram video without doing an unnecessary second encode."""
    upload_path = path
    upload_name = _video_upload_name(filename)

    # prepare_video_for_telegram copies/remuxes H.264 sources and encodes only
    # when the source video codec itself is incompatible with Telegram video.
    if _extension(filename) != "mp4" or not path.lower().endswith(".mp4"):
        mp4_path = os.path.join(job.work_dir, f".telegram_{uuid.uuid4().hex}.mp4")
        prepared = await prepare_video_for_telegram(path, mp4_path)
        if not prepared:
            raise RuntimeError("Could not prepare a valid Telegram video")
        upload_path = prepared
    elif path.lower().endswith(".mp4"):
        # Even for an already-MP4 rename, probe/prepare only if required. The
        # fast path hard-links/copies compatible H.264/AAC without encoding.
        prepared = await prepare_video_for_telegram(path, path)
        if prepared:
            upload_path = prepared

    duration, width, height = await get_video_info(upload_path)
    if duration <= 0 or width <= 0 or height <= 0:
        raise RuntimeError("Video metadata could not be read")
    return upload_path, upload_name, duration, width, height


async def _show_upload_start(job: Job, status: Message | None, path: str):
    if status is None:
        return
    total = max(1, os.path.getsize(path))
    from helper.utils import reset_progress, progress_for_pyrogram
    reset_progress(job.job_id)
    await protect_message(status.chat.id, status.id)
    await progress_for_pyrogram(0, total, "Uploading", status, time.time(), job.job_id)


async def _send_video(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    upload_path, upload_name, duration, width, height = await _prepare_video(job, path, filename)
    from helper.utils import progress_for_pyrogram, reset_progress
    await _show_upload_start(job, status, upload_path)
    progress = progress_for_pyrogram if status else None
    args = ("Uploading", status, time.time(), job.job_id) if status else None
    kwargs = {
        "caption": None,
        "duration": max(1, int(round(duration))),
        "width": int(width),
        "height": int(height),
        "supports_streaming": True,
        "file_name": upload_name,
    }
    saved_thumb = await db.get_thumbnail(job.user_id)
    if saved_thumb:
        kwargs["thumb"] = saved_thumb
    if progress:
        kwargs["progress"] = progress
        kwargs["progress_args"] = args
    try:
        return await client.send_video(job.user_id, upload_path, **kwargs)
    except RPCError as exc:
        # Retry only the Telegram API call without optional thumbnail metadata.
        # Never re-encode or resend the file as a document on a normal video path.
        if saved_thumb:
            kwargs.pop("thumb", None)
            reset_progress(job.job_id)
            await _show_upload_start(job, status, upload_path)
            return await client.send_video(job.user_id, upload_path, **kwargs)
        raise RuntimeError(f"Telegram video upload failed: {exc}") from exc


async def _send_plain_output(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    ext = _extension(filename)
    mime = job.mime_type or ""
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise RuntimeError("Processed output is missing or empty")

    from helper.utils import progress_for_pyrogram
    progress = progress_for_pyrogram if status else None
    args = ("Uploading", status, time.time(), job.job_id) if status else None

    if mime.startswith("video/") or ext in VIDEO_EXTENSIONS:
        return await _send_video(client, job, path, filename, status)

    if mime.startswith("audio/") or ext in {"mp3", "m4a", "aac", "flac", "ogg", "wav", "opus"}:
        return await client.send_audio(job.user_id, path, caption=None, progress=progress, progress_args=args) if progress else await client.send_audio(job.user_id, path, caption=None)

    return await client.send_document(job.user_id, path, caption=None, progress=progress, progress_args=args) if progress else await client.send_document(job.user_id, path, caption=None)


async def _deliver_output(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    if (job.mime_type or "").startswith("video/") or _extension(filename) in VIDEO_EXTENSIONS:
        if is_large_video(path):
            parts = await split_video_for_telegram(path, job.work_dir, filename)
            sent_messages = []
            for part in parts:
                sent = await _send_video(client, job, part, os.path.basename(part), status)
                if not sent:
                    raise RuntimeError("Telegram returned no video message")
                await protect_result(sent)
                await archive_message(client, sent)
                sent_messages.append(sent)
            return sent_messages

    parts = await split_file_for_telegram(path, job.work_dir, filename)
    if len(parts) > 1:
        sent_messages = []
        for part in parts:
            sent = await _send_plain_output(client, job, part, os.path.basename(part), status)
            if not sent:
                raise RuntimeError("Telegram returned no message")
            await protect_result(sent)
            await archive_message(client, sent)
            sent_messages.append(sent)
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
        work_dir=work_dir, input_path=input_path, original_name=original_name,
        mime_type=mime_type,
        extra={"extension": extension, "file_id": file_id, "source_message": message, "user_data": user_data, "used_before": used, "telegram_file_size": expected_size},
    )
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
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired or not owned by you.", show_alert=True)
        raise StopPropagation
    await cb.answer()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await jobs.update(job.job_id, selected_action="custom_name")
    prompt = await _ask_name(client, job.user_id, "✏️ **Rename:**\nSend me the new filename.", job.job_id, "custom_name")
    await jobs.update(job.job_id, extra={**job.extra, "rename_prompt_message_id": prompt.id, "prompt_message_id": prompt.id})
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:renameformat:([0-9a-f]+):(document|video)$"), group=-1000)
async def rename_format_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired or not owned by you.", show_alert=True)
        raise StopPropagation
    mode = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, extra={**job.extra, "rename_output_mode": mode, "rename_menu_message_id": cb.message.id})
    try:
        await cb.message.delete()
    except Exception:
        pass
    prompt = await _ask_name(client, job.user_id, "✏️ **Rename:**\nSend me the new filename.", job.job_id, "custom_name")
    await jobs.update(job.job_id, extra={**job.extra, "rename_output_mode": mode, "rename_prompt_message_id": prompt.id, "prompt_message_id": prompt.id})
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:format:([0-9a-f]+):(mp4|mkv|webm|mov|mp3|m4a)$"), group=-1000)
async def convert_entry_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired or not owned by you.", show_alert=True)
        raise StopPropagation
    fmt = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, output_ext=fmt, selected_action="convert_name", mime_type=VIDEO_MIME.get(fmt) or AUDIO_MIME.get(fmt) or "application/octet-stream")
    try:
        await cb.message.delete()
    except Exception:
        pass
    prompt = await _ask_name(client, job.user_id, f"✏️ **Rename:**\nSend me the new filename for {fmt.upper()}.", job.job_id, "convert_name")
    await jobs.update(job.job_id, extra={**job.extra, "rename_prompt_message_id": prompt.id, "prompt_message_id": prompt.id})
    raise StopPropagation


@Client.on_message(filters.private & filters.reply & filters.text, group=-1000)
async def rename_reply_guard(client, message: Message):
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
    await message.reply_text("🔄 **Previous file job cleared. Send the new file again to choose an operation.**")
    raise StopPropagation

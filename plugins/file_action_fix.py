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
from helper.ffmpeg import convert_media, fix_metadata, get_video_info, inspect_media_streams, prepare_video_for_telegram
from helper.job_state import Job, jobs
from helper.large_file import split_file_for_telegram
from helper.large_video import is_large_video, split_video_for_telegram
from helper.message_cleanup import protect_message, protect_result
from helper.plans import get_plan
from helper.utils import humanbytes, progress_for_pyrogram, reset_progress
from plugins.rename import _ask_name, _base_without_extension, _extension, _media_from_message, _safe_filename, _user_context
from plugins.ui import file_action_menu, rename_output_menu

VIDEO_MIME = {"mp4": "video/mp4", "mkv": "video/x-matroska", "webm": "video/webm", "mov": "video/quicktime"}
AUDIO_MIME = {"mp3": "audio/mpeg", "m4a": "audio/mp4"}
VIDEO_EXTENSIONS = {"mp4", "mkv", "webm", "mov", "avi", "flv", "ts", "m4v"}


async def _output_caption(job: Job, filename: str, size: int, duration: float = 0) -> str:
    saved = await db.get_caption(job.user_id)
    if saved:
        return str(saved).replace("{filename}", filename).replace("{filesize}", humanbytes(size)).replace("{duration}", str(int(duration)))
    return f"✅ **AniToon Processed**\n\n📂 `{filename}`\n📦 `{humanbytes(size)}`"


async def _apply_metadata_settings(job: Job, output_path: str) -> None:
    if not os.path.isfile(output_path):
        return
    if _extension(output_path) not in VIDEO_EXTENSIONS and not str(job.mime_type or "").startswith("video/"):
        return
    temp = None
    try:
        streams = await inspect_media_streams(output_path)
        if not any(item["type"] in {"audio", "subtitle"} for item in streams):
            return
        from helper.metadata import get_metadata
        settings = await get_metadata(job.user_id)
        temp = os.path.join(job.work_dir, ".metadata_applied." + os.path.basename(output_path))
        ok = await fix_metadata(output_path, temp, settings.audio_name, settings.subtitle_name)
        if ok and os.path.isfile(temp) and os.path.getsize(temp) > 0:
            os.replace(temp, output_path)
        elif temp and os.path.exists(temp):
            os.remove(temp)
    except Exception:
        if temp and os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError:
                pass


def _video_upload_name(filename: str) -> str:
    return f"{_base_without_extension(filename)}.mp4"


async def _prepare_video(job: Job, path: str, filename: str):
    upload_name = _video_upload_name(filename)
    if path.lower().endswith(".mp4") and _extension(filename) == "mp4":
        upload_path = path
    else:
        mp4_path = os.path.join(job.work_dir, f".telegram_{uuid.uuid4().hex}.mp4")
        upload_path = await prepare_video_for_telegram(path, mp4_path)
        if not upload_path:
            raise RuntimeError("Could not prepare a valid Telegram video")
    duration, width, height = await get_video_info(upload_path)
    if duration <= 0 or width <= 0 or height <= 0:
        raise RuntimeError("Video metadata could not be read")
    return upload_path, upload_name, duration, width, height


async def _show_upload_start(job: Job, status: Message | None, path: str):
    if status is None:
        return
    total = max(1, os.path.getsize(path))
    reset_progress(job.job_id)
    await protect_message(status.chat.id, status.id)
    await progress_for_pyrogram(0, total, "Uploading", status, time.time(), job.job_id)


async def _send_video(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    upload_path, upload_name, duration, width, height = await _prepare_video(job, path, filename)
    await _show_upload_start(job, status, upload_path)
    progress = progress_for_pyrogram if status else None
    args = ("Uploading", status, time.time(), job.job_id) if status else None
    kwargs = {"caption": await _output_caption(job, upload_name, os.path.getsize(upload_path), duration), "duration": max(1, int(round(duration))), "width": int(width), "height": int(height), "supports_streaming": True, "file_name": upload_name}
    saved_thumb = await db.get_thumbnail(job.user_id)
    if saved_thumb:
        kwargs["thumb"] = saved_thumb
    if progress:
        kwargs["progress"] = progress
        kwargs["progress_args"] = args
    try:
        return await client.send_video(job.user_id, upload_path, **kwargs)
    except RPCError as exc:
        error_text = str(exc).lower()
        if saved_thumb and ("thumb" in error_text or "thumbnail" in error_text):
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
    progress = progress_for_pyrogram if status else None
    args = ("Uploading", status, time.time(), job.job_id) if status else None
    caption = await _output_caption(job, filename, os.path.getsize(path))
    thumb = await db.get_thumbnail(job.user_id)
    if ext == "mp4" or mime == "video/mp4":
        return await _send_video(client, job, path, filename, status)
    if mime.startswith("audio/") or ext in {"mp3", "m4a", "aac", "flac", "ogg", "wav", "opus"}:
        kwargs = {"caption": caption}
        if thumb:
            kwargs["thumb"] = thumb
        if progress:
            kwargs.update(progress=progress, progress_args=args)
        return await client.send_audio(job.user_id, path, **kwargs)
    kwargs = {"caption": caption}
    if thumb:
        kwargs["thumb"] = thumb
    if progress:
        kwargs.update(progress=progress, progress_args=args)
    return await client.send_document(job.user_id, path, **kwargs)


async def _deliver_output(client: Client, job: Job, path: str, filename: str, status: Message | None = None):
    if (job.mime_type or "").startswith("video/") or _extension(filename) in VIDEO_EXTENSIONS:
        await _apply_metadata_settings(job, path)
    if _extension(filename) == "mp4" or (job.mime_type or "") == "video/mp4":
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
    return [sent]


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"), group=-1000)
async def rename_entry_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired or not owned by you.", show_alert=True)
        raise StopPropagation
    await cb.answer()
    await jobs.update(job.job_id, selected_action="rename_output_choice", extra={**job.extra, "rename_menu_message_id": cb.message.id})
    try:
        await cb.message.edit_text("✏️ **Rename**\n\nChoose how you want the renamed file to be sent:", reply_markup=rename_output_menu(job.job_id))
    except Exception:
        pass
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^renameoutput:([0-9a-f]+):(file|video)$"), group=-1000)
async def rename_output_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired or not owned by you.", show_alert=True)
        raise StopPropagation
    mode = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, selected_action="custom_name", extra={**job.extra, "rename_output_mode": mode, "rename_menu_message_id": cb.message.id})
    prompt = await _ask_name(client, job.user_id, "✏️ **Rename:**\nSend me the new filename.", job.job_id, "custom_name")
    await jobs.update(job.job_id, extra={**job.extra, "rename_prompt_message_id": prompt.id, "prompt_message_id": prompt.id, "rename_menu_message_id": cb.message.id})
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
    job.mime_type = "video/mp4" if mode == "video" else "application/octet-stream"
    try:
        await cb.message.delete()
    except Exception:
        pass
    prompt = await _ask_name(client, job.user_id, "✏️ **Rename:**\nSend me the new filename.", job.job_id, "custom_name")
    await jobs.update(job.job_id, extra={**job.extra, "rename_prompt_message_id": prompt.id, "prompt_message_id": prompt.id})
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


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio), group=-999)
async def retry_file_when_waiting(client: Client, message: Message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in {"rename_format", "custom_name", "convert_name", "rename_output_choice", "convert_menu"}:
        return
    shutil.rmtree(job.work_dir, ignore_errors=True)
    await jobs.remove(job.job_id)
    await message.reply_text("🔄 **Previous file job cleared. Send the new file again to choose an operation.**")
    raise StopPropagation

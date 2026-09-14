from __future__ import annotations

import os
import shutil
import time

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from helper.database import db
from helper.ffmpeg import convert_media, get_video_info, make_streamable
from helper.job_state import jobs
from helper.job_transfer import download_job
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes, progress_for_pyrogram, reset_progress
from plugins.rename import _base_without_extension, _extension, _safe_filename
from plugins.ui import rename_format_menu

VIDEO_EXTENSIONS = {"mp4", "mkv", "webm", "mov", "avi", "flv", "ts", "m4v"}
VIDEO_MIME = {"mp4": "video/mp4", "mkv": "video/x-matroska", "webm": "video/webm", "mov": "video/quicktime"}
AUDIO_MIME = {"mp3": "audio/mpeg", "m4a": "audio/mp4"}


async def _send(client, job, path, filename, status):
    ext = _extension(filename)
    reset_progress(job.job_id)
    args = ("Uploading", status, time.time(), job.job_id)
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise RuntimeError("Output file is missing or empty")

    if (job.mime_type or "").startswith("video/") or ext in VIDEO_EXTENSIONS:
        duration, width, height = await get_video_info(path)
        if not duration or not width or not height:
            raise RuntimeError("Output video metadata could not be read")
        upload_path = path
        stream_path = os.path.join(job.work_dir, ".telegram_streamable.mp4")
        ready = await make_streamable(path, stream_path)
        if ready and os.path.isfile(ready) and os.path.getsize(ready) > 0:
            upload_path = ready
            duration, width, height = await get_video_info(upload_path)
        try:
            return await client.send_video(
                job.user_id,
                upload_path,
                caption=None,
                duration=max(1, int(round(duration))),
                width=int(width),
                height=int(height),
                supports_streaming=True,
                progress=progress_for_pyrogram,
                progress_args=args,
            )
        except Exception as exc:
            raise RuntimeError(f"Video upload failed: {str(exc)[:1000]}") from exc

    if (job.mime_type or "").startswith("audio/") or ext in {"mp3", "m4a", "aac", "flac", "ogg", "wav", "opus"}:
        try:
            return await client.send_audio(job.user_id, path, caption=None, progress=progress_for_pyrogram, progress_args=args)
        except Exception as exc:
            raise RuntimeError(f"Audio upload failed: {str(exc)[:1000]}") from exc

    try:
        return await client.send_document(job.user_id, path, caption=None, progress=progress_for_pyrogram, progress_args=args)
    except Exception as exc:
        raise RuntimeError(f"Document upload failed: {str(exc)[:1000]}") from exc


async def _cleanup(job):
    clear_transfer_cancel(job.job_id)
    shutil.rmtree(job.work_dir, ignore_errors=True)
    await jobs.remove(job.job_id)


async def _download(client, job, status):
    source = await client.get_messages(job.user_id, job.source_message_id)
    if not source:
        raise RuntimeError("Original file message is no longer available")
    await download_job(client, source, job, status)
    if not os.path.exists(job.input_path):
        raise RuntimeError("Download completed but the input file is missing")


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"), group=-1100)
async def rename_menu(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired or not owned by you.", show_alert=True)
        raise StopPropagation
    await cb.answer()
    await jobs.update(job.job_id, selected_action="rename_format")
    await cb.message.edit_text("✏️ **Rename**\n\nChoose the output type:", reply_markup=rename_format_menu(job.job_id))
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:renameformat:([0-9a-f]+):(document|video)$"), group=-1100)
async def rename_type(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired or not owned by you.", show_alert=True)
        raise StopPropagation
    mode = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, selected_action="custom_name", extra={**job.extra, "rename_output_mode": mode})
    await client.send_message(job.user_id, "✏️ **Enter new filename:**\n" + ("A valid MP4 video will be created." if mode == "video" else "The original extension will be preserved."), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"job:cancel:{job.job_id}")]]))
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:format:([0-9a-f]+):(mp4|mkv|webm|mov|mp3|m4a)$"), group=-1100)
async def convert_type(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired or not owned by you.", show_alert=True)
        raise StopPropagation
    fmt = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, selected_action="convert_name", output_ext=fmt, mime_type=VIDEO_MIME.get(fmt) or AUDIO_MIME.get(fmt) or "application/octet-stream")
    await client.send_message(job.user_id, f"🔄 **Convert to {fmt.upper()}**\n\nEnter the output filename. The `.{fmt}` extension will be used.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"job:cancel:{job.job_id}")]]))
    raise StopPropagation


@Client.on_message(filters.private & filters.reply & filters.text, group=-1100)
async def filename_reply(client, message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in {"custom_name", "convert_name"}:
        return
    text = _safe_filename(message.text or "")
    if not text:
        await message.reply_text("❌ Please send a valid filename.")
        raise StopPropagation
    status = await message.reply_text("📥 **Downloading...**")
    try:
        await _download(client, job, status)
        if job.selected_action == "convert_name":
            ext = job.output_ext
            name = f"{_base_without_extension(text)}.{ext}"
            output = os.path.join(job.work_dir, name)
            if not await convert_media(job.input_path, output, ext):
                raise RuntimeError("FFmpeg conversion failed")
        else:
            mode = job.extra.get("rename_output_mode", "document")
            if mode == "video":
                name = f"{_base_without_extension(text)}.mp4"
                output = os.path.join(job.work_dir, name)
                if not await convert_media(job.input_path, output, "mp4"):
                    raise RuntimeError("Could not create a valid MP4 video")
                job.mime_type = "video/mp4"
            else:
                source_ext = _extension(job.original_name)
                name = f"{_base_without_extension(text)}.{source_ext}" if source_ext else text
                output = os.path.join(job.work_dir, name)
                os.replace(job.input_path, output)
        await _send(client, job, output, name, status)
        await db.update_usage(job.user_id, job.bot_id, os.path.getsize(output))
        try:
            await status.delete()
        except Exception:
            pass
    except AniToonTransferCancelled:
        try:
            await status.edit_text("❌ **Processing cancelled.**")
        except Exception:
            pass
    except Exception as exc:
        try:
            await status.edit_text(f"❌ **Processing failed**\n\n`{str(exc)[:1200]}`")
        except Exception:
            pass
    finally:
        await _cleanup(job)
    raise StopPropagation

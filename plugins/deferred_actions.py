"""Deferred action workflow: download only after the user chooses an operation/name."""

from __future__ import annotations

import asyncio
import os
import shutil
import time

from pyrogram import Client, StopPropagation, filters
from pyrogram.errors import FloodWait, RPCError

from helper.database import db
from helper.ffmpeg import convert_media
from helper.job_state import jobs
from helper.job_transfer import cancel_markup, download_job
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes, progress_for_pyrogram
from plugins.rename import _base_without_extension, _extension, _safe_filename
from plugins.ui import advanced_menu, convert_menu


async def _source(client, message, job):
    return await client.get_messages(message.chat.id, job.source_message_id)


async def _upload_with_retry(send_func, *, path, caption, status, job_id, **kwargs):
    """Retry only transient Telegram/network failures without hiding upload errors."""
    last_error = None
    for attempt in range(1, 4):
        try:
            return await send_func(
                path,
                caption=caption,
                progress=progress_for_pyrogram,
                progress_args=("Uploading", status, time.time(), job_id),
                **kwargs,
            )
        except AniToonTransferCancelled:
            raise
        except FloodWait as exc:
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(max(1, int(exc.value)))
        except (OSError, TimeoutError, asyncio.TimeoutError, ConnectionError) as exc:
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(1.5 * attempt)
        except RPCError as exc:
            # Bad media/container errors are not useful to retry. Other RPC
            # errors can be transient, so give them a short retry window.
            last_error = exc
            text = str(exc).lower()
            retryable = any(word in text for word in ("timeout", "connection", "tempor", "network", "server"))
            if attempt < 3 and retryable:
                await asyncio.sleep(1.5 * attempt)
            else:
                break
    raise last_error or RuntimeError("Telegram upload failed")


async def _send_file(client, job, path, filename, status):
    caption = f"✅ **AniToon Processed**\n\n📂 `{filename}`\n📦 `{humanbytes(os.path.getsize(path))}`"
    ext = _extension(filename)
    is_video = (job.mime_type or "").startswith("video/") or ext in {"mp4", "mkv", "webm", "mov", "avi", "flv", "ts", "m4v"}
    is_audio = (job.mime_type or "").startswith("audio/") or ext in {"mp3", "m4a", "aac", "flac", "ogg", "wav", "opus"}

    if is_video:
        try:
            return await _upload_with_retry(
                client.send_video,
                path=path,
                caption=caption,
                status=status,
                job_id=job.job_id,
                chat_id=job.user_id,
            )
        except AniToonTransferCancelled:
            raise
        except RPCError as exc:
            # Only a Telegram media-validation RPC error should trigger a
            # document fallback. Network failures must not restart from zero.
            text = str(exc).lower()
            if not any(word in text for word in ("video", "media", "document", "mime", "codec", "thumbnail")):
                raise

    if is_audio:
        try:
            return await _upload_with_retry(
                client.send_audio,
                path=path,
                caption=caption,
                status=status,
                job_id=job.job_id,
                chat_id=job.user_id,
            )
        except AniToonTransferCancelled:
            raise
        except RPCError as exc:
            text = str(exc).lower()
            if not any(word in text for word in ("audio", "media", "document", "mime", "codec", "thumbnail")):
                raise

    return await _upload_with_retry(
        client.send_document,
        path=path,
        caption=caption,
        status=status,
        job_id=job.job_id,
        chat_id=job.user_id,
    )


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"), group=-5000)
async def deferred_rename(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation
    await cb.answer()
    await jobs.update(job.job_id, selected_action="custom_name", extra={**job.extra, "rename_output_mode": "file"})
    await cb.message.edit_text("Enter new filename:", reply_markup=cancel_markup(job.job_id))
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:convert:([0-9a-f]+)$"), group=-5000)
async def deferred_convert(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
    else:
        await cb.answer()
        await jobs.update(job.job_id, selected_action="convert_menu")
        await cb.message.edit_text("🔄 **Convert File**\n\nChoose the output format:", reply_markup=convert_menu(job.job_id))
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:advanced:([0-9a-f]+)$"), group=-5000)
async def deferred_advanced(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation
    await cb.answer()
    status = await cb.message.edit_text("⏳ **Preparing advanced tools...**", reply_markup=cancel_markup(job.job_id))
    try:
        source = await client.get_messages(cb.message.chat.id, job.source_message_id)
        await download_job(client, source, job, status)
        await jobs.update(job.job_id, selected_action="advanced_menu")
        await status.edit_text("🛠 **Advanced**\n\nChoose what you want to do:", reply_markup=advanced_menu(job.job_id))
    except AniToonTransferCancelled:
        await status.edit_text("❌ **Processing cancelled.**")
        shutil.rmtree(job.work_dir, ignore_errors=True)
        await jobs.remove(job.job_id)
    except Exception as exc:
        await status.edit_text(f"❌ **Download failed**\n\n`{str(exc)[:1000]}`")
        shutil.rmtree(job.work_dir, ignore_errors=True)
        await jobs.remove(job.job_id)
    raise StopPropagation


@Client.on_message(filters.private & filters.reply & filters.text, group=-5000)
async def deferred_name(client, message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in {"custom_name", "convert_name"}:
        return
    text = _safe_filename(message.text or "")
    if not text:
        await message.reply_text("❌ **Please send a valid filename.**")
        raise StopPropagation

    status = await message.reply_text("Downloading...", reply_markup=cancel_markup(job.job_id))
    try:
        source = await _source(client, message, job)
        await download_job(client, source, job, status)

        if job.selected_action == "convert_name":
            ext = job.output_ext
            if not ext:
                raise RuntimeError("Conversion format expired. Please select Convert again.")
            name = _safe_filename(text)
            if _extension(name) != ext:
                name = f"{_base_without_extension(name)}.{ext}"
            await status.edit_text("⚙️ **Processing...**", reply_markup=cancel_markup(job.job_id))
            if not await convert_media(job.input_path, os.path.join(job.work_dir, name), ext):
                raise RuntimeError("FFmpeg conversion failed")
            output_path = os.path.join(job.work_dir, name)
            await _send_file(client, job, output_path, name, status)
        else:
            ext = _extension(job.original_name)
            name = text
            if _extension(name) != ext:
                name = f"{_base_without_extension(name)}.{ext}" if ext else name
            output_path = os.path.join(job.work_dir, name)
            os.replace(job.input_path, output_path)
            await _send_file(client, job, output_path, name, status)

        input_size = int(job.extra.get("downloaded_size", 0) or 0)
        await db.update_usage(job.user_id, job.bot_id, input_size)
        await status.edit_text(
            f"✅ **Processing Complete!**\n\n📂 `{name}`\n📦 `{humanbytes(os.path.getsize(output_path))}`"
        )
    except AniToonTransferCancelled:
        try:
            await status.edit_text("❌ **Processing cancelled.**")
        except Exception:
            pass
    except Exception as exc:
        try:
            await status.edit_text(f"❌ **Processing failed**\n\n`{str(exc)[:1000]}`")
        except Exception:
            pass
    finally:
        clear_transfer_cancel(job.job_id)
        shutil.rmtree(job.work_dir, ignore_errors=True)
        await jobs.remove(job.job_id)
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^transfer:cancel:([0-9a-f]+)$"), group=-5000)
async def deferred_cancel(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("This file job is no longer active.", show_alert=True)
        raise StopPropagation

    from helper.utils import request_transfer_cancel
    request_transfer_cancel(job.job_id)

    # A waiting job has no transfer callback running, so remove it immediately.
    if not os.path.exists(job.input_path):
        await jobs.remove(job.job_id)
        shutil.rmtree(job.work_dir, ignore_errors=True)
        clear_transfer_cancel(job.job_id)
        try:
            await cb.message.edit_text("❌ **Processing cancelled.**")
        except Exception:
            pass
    else:
        try:
            await cb.message.edit_text("❌ **Cancelling processing...**")
        except Exception:
            pass

    await cb.answer("Cancelled" if not os.path.exists(job.input_path) else "Cancelling...")
    raise StopPropagation

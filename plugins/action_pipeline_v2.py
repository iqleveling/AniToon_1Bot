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
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, progress_for_pyrogram
from plugins.rename import _base_without_extension, _extension, _safe_filename
from plugins.ui import rename_format_menu

AUDIO = {"mp3", "m4a"}
VIDEO = {"mp4", "mkv", "webm", "mov"}


def cancel(job_id: str):
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]])


async def _delete(client, chat_id: int, *ids: int | None):
    values = [int(x) for x in ids if x]
    if not values:
        return
    try:
        await client.delete_messages(chat_id, values)
    except Exception:
        for value in values:
            try:
                await client.delete_messages(chat_id, value)
            except Exception:
                pass


async def _safe_edit(message, text: str, reply_markup=None):
    """Ignore harmless Telegram MESSAGE_NOT_MODIFIED edits."""
    try:
        current = getattr(message, "text", None) or getattr(message, "caption", None)
        if current == text:
            return
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception as exc:
        if "MESSAGE_NOT_MODIFIED" not in str(exc).upper():
            raise


async def _finish_cleanup(client, job):
    clear_transfer_cancel(job.job_id)
    await _delete(
        client,
        job.user_id,
        job.source_message_id,
        job.extra.get("prompt_message_id"),
        job.extra.get("input_message_id"),
        job.extra.get("status_message_id"),
    )
    shutil.rmtree(job.work_dir, ignore_errors=True)
    await jobs.remove(job.job_id)


async def _send_result(client, job, path: str, name: str, status, kind: str):
    args = ("📤 Uploading", status, time.time(), job.job_id)

    if kind == "video":
        duration, width, height = await get_video_info(path)
        if not duration or not width or not height:
            raise RuntimeError("Output is not a valid video with duration and dimensions")

        upload_path = path
        if not path.lower().endswith(".mp4"):
            stream_path = os.path.join(job.work_dir, "streamable.mp4")
            ready = await make_streamable(path, stream_path)
            if ready:
                upload_path = ready
                duration, width, height = await get_video_info(upload_path)

        if not duration or not width or not height:
            raise RuntimeError("Could not prepare a valid Telegram video")

        return await client.send_video(
            job.user_id,
            upload_path,
            caption=None,
            duration=max(1, int(round(duration))),
            width=width,
            height=height,
            supports_streaming=True,
            progress=progress_for_pyrogram,
            progress_args=args,
        )

    if kind == "audio":
        return await client.send_audio(job.user_id, path, caption=None, progress=progress_for_pyrogram, progress_args=args)

    return await client.send_document(job.user_id, path, caption=None, progress=progress_for_pyrogram, progress_args=args)


async def _run(client, job, status, name: str, kind: str, convert: bool):
    source = await client.get_messages(job.user_id, job.source_message_id)
    if not source:
        raise RuntimeError("Original file message is no longer available")

    await _safe_edit(status, "📥 **Downloading...**", reply_markup=cancel(job.job_id))
    await download_job(client, source, job, status)

    output = os.path.join(job.work_dir, name)
    if convert:
        ext = os.path.splitext(name)[1].lstrip(".").lower()
        if not await convert_media(job.input_path, output, ext):
            raise RuntimeError("FFmpeg conversion failed")
    else:
        os.replace(job.input_path, output)

    await _safe_edit(status, "📤 **Uploading... 0%**", reply_markup=cancel(job.job_id))
    await _send_result(client, job, output, name, status, kind)
    await db.update_usage(job.user_id, job.bot_id, os.path.getsize(output))


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"), group=-1400)
async def rename_entry_v2(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired.", show_alert=True)
        raise StopPropagation
    await cb.answer()
    await jobs.update(job.job_id, selected_action="rename_format")
    await cb.message.edit_text("✏️ **Rename**\n\nChoose output type:", reply_markup=rename_format_menu(job.job_id))
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:renameformat:([0-9a-f]+):(document|video)$"), group=-1400)
async def rename_type_v2(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired.", show_alert=True)
        raise StopPropagation
    mode = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, selected_action="custom_name", extra={**job.extra, "rename_output_mode": mode})
    prompt = await client.send_message(
        job.user_id,
        "✏️ **Enter new filename:**\n\n" + (
            "The file will be converted to a real streamable MP4 video."
            if mode == "video"
            else "The original extension will be preserved."
        ),
        reply_markup=cancel(job.job_id),
    )
    await jobs.update(job.job_id, extra={**job.extra, "prompt_message_id": prompt.id})
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:format:([0-9a-f]+):(mp4|mkv|webm|mov|mp3|m4a)$"), group=-1400)
async def convert_type_v2(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired.", show_alert=True)
        raise StopPropagation
    fmt = cb.matches[0].group(2)
    await cb.answer()
    mime = "video/mp4" if fmt == "mp4" else "audio/mpeg" if fmt == "mp3" else "audio/mp4" if fmt == "m4a" else "application/octet-stream"
    await jobs.update(job.job_id, selected_action="convert_name", output_ext=fmt, mime_type=mime)
    prompt = await client.send_message(
        job.user_id,
        f"🔄 **Convert to {fmt.upper()}**\n\nEnter the output filename. The `.{fmt}` extension will be used.",
        reply_markup=cancel(job.job_id),
    )
    await jobs.update(job.job_id, extra={**job.extra, "prompt_message_id": prompt.id})
    raise StopPropagation


@Client.on_message(filters.private & filters.text, group=-1400)
async def filename_v2(client, message):
    if (message.text or "").strip().startswith("/"):
        return

    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in {"custom_name", "convert_name"}:
        return

    text = _safe_filename(message.text or "")
    if not text:
        await message.reply_text("❌ Please send a valid filename.")
        raise StopPropagation

    await jobs.update(job.job_id, extra={**job.extra, "input_message_id": message.id})
    status = await message.reply_text("📥 **Downloading...**", reply_markup=cancel(job.job_id))
    await jobs.update(job.job_id, extra={**job.extra, "status_message_id": status.id})

    user_lock = None
    try:
        if hasattr(jobs, "acquire_user"):
            user_lock = await jobs.acquire_user(message.from_user.id)

        if job.selected_action == "convert_name":
            ext = (job.output_ext or "").lower()
            if not ext:
                raise RuntimeError("Conversion format expired")
            name = f"{_base_without_extension(text)}.{ext}"
            kind = "video" if ext == "mp4" else "audio" if ext in AUDIO else "document"
            await _run(client, job, status, name, kind, True)
        elif job.extra.get("rename_output_mode") == "video":
            name = f"{_base_without_extension(text)}.mp4"
            await _run(client, job, status, name, "video", True)
        else:
            ext = _extension(job.original_name)
            name = f"{_base_without_extension(text)}.{ext}" if ext else text
            await _run(client, job, status, name, "document", False)

        await _finish_cleanup(client, job)

    except AniToonTransferCancelled:
        try:
            await _safe_edit(status, "❌ **Processing cancelled.**")
        except Exception:
            pass
        clear_transfer_cancel(job.job_id)
        shutil.rmtree(job.work_dir, ignore_errors=True)
        await jobs.remove(job.job_id)
    except Exception as exc:
        try:
            await _safe_edit(status, f"❌ **Processing failed**\n\n`{str(exc)[:1200]}`")
        except Exception:
            pass
        clear_transfer_cancel(job.job_id)
        shutil.rmtree(job.work_dir, ignore_errors=True)
        await jobs.remove(job.job_id)
    finally:
        if user_lock is not None:
            try:
                user_lock.release()
            except RuntimeError:
                pass

    raise StopPropagation

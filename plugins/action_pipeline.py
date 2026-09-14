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
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes, progress_for_pyrogram
from plugins.rename import _base_without_extension, _extension, _safe_filename
from plugins.ui import rename_format_menu

AUDIO = {"mp3", "m4a"}
VIDEO = {"mp4", "mkv", "webm", "mov"}


def cancel(job_id):
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]])


async def cleanup(client, job, remove_source=False):
    clear_transfer_cancel(job.job_id)
    if remove_source:
        for mid in (job.source_message_id, job.extra.get("prompt_message_id")):
            if mid:
                try:
                    await client.delete_messages(job.user_id, mid)
                except Exception:
                    pass
    shutil.rmtree(job.work_dir, ignore_errors=True)
    await jobs.remove(job.job_id)


async def upload(client, job, path, name, status, kind):
    size = os.path.getsize(path)
    caption = f"✅ **AniToon Processed**\n\n📂 `{name}`\n📦 `{humanbytes(size)}`"
    args = ("Uploading", status, time.time(), job.job_id)
    if kind == "video":
        duration, width, height = await get_video_info(path)
        if not duration or not width or not height:
            raise RuntimeError("Output is not a valid video")
        stream = os.path.join(job.work_dir, "streamable.mp4")
        ready = await make_streamable(path, stream)
        if ready:
            path = ready
            duration, width, height = await get_video_info(path)
        return await client.send_video(job.user_id, path, caption=caption, duration=max(1, int(duration)), width=width, height=height, supports_streaming=True, progress=progress_for_pyrogram, progress_args=args)
    if kind == "audio":
        return await client.send_audio(job.user_id, path, caption=caption, progress=progress_for_pyrogram, progress_args=args)
    return await client.send_document(job.user_id, path, caption=caption, progress=progress_for_pyrogram, progress_args=args)


async def process(client, job, status, name, kind, convert):
    await status.edit_text("📥 **Downloading...**", reply_markup=cancel(job.job_id))
    source = await client.get_messages(job.user_id, job.source_message_id)
    await download_job(client, source, job, status)
    output = os.path.join(job.work_dir, name)
    if convert:
        await status.edit_text("⚙️ **Processing...**", reply_markup=cancel(job.job_id))
        ext = os.path.splitext(name)[1].lstrip(".")
        if not await convert_media(job.input_path, output, ext):
            raise RuntimeError("FFmpeg conversion failed")
    else:
        os.replace(job.input_path, output)
    await status.edit_text("📤 **Uploading...**", reply_markup=cancel(job.job_id))
    await upload(client, job, output, name, status, kind)
    await db.update_usage(job.user_id, job.bot_id, os.path.getsize(output))
    await status.edit_text(f"✅ **Completed!**\n\n📂 `{name}`\n📦 `{humanbytes(os.path.getsize(output))}`")


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"), group=-1300)
async def rename_entry(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired.", show_alert=True); raise StopPropagation
    await cb.answer()
    await jobs.update(job.job_id, selected_action="rename_format")
    await cb.message.edit_text("✏️ **Rename**\n\nChoose output type:", reply_markup=rename_format_menu(job.job_id))
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:renameformat:([0-9a-f]+):(document|video)$"), group=-1300)
async def rename_type(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired.", show_alert=True); raise StopPropagation
    mode = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, selected_action="custom_name", extra={**job.extra, "rename_output_mode": mode})
    prompt = await client.send_message(job.user_id, "✏️ **Enter new filename:**\n\n" + ("A real MP4 video will be created and sent as video." if mode == "video" else "The result will be sent as a document."), reply_markup=cancel(job.job_id))
    await jobs.update(job.job_id, extra={**job.extra, "rename_output_mode": mode, "prompt_message_id": prompt.id})
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:format:([0-9a-f]+):(mp4|mkv|webm|mov|mp3|m4a)$"), group=-1300)
async def convert_type(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired.", show_alert=True); raise StopPropagation
    fmt = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, selected_action="convert_name", output_ext=fmt, mime_type=("video/mp4" if fmt == "mp4" else "audio/mpeg" if fmt == "mp3" else "audio/mp4" if fmt == "m4a" else "application/octet-stream"))
    prompt = await client.send_message(job.user_id, f"🔄 **Convert to {fmt.upper()}**\n\nEnter the output filename. The `.{fmt}` extension will be used.", reply_markup=cancel(job.job_id))
    await jobs.update(job.job_id, extra={**job.extra, "prompt_message_id": prompt.id})
    raise StopPropagation


@Client.on_message(filters.private & filters.text, group=-1300)
async def filename_input(client, message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in {"custom_name", "convert_name"}:
        return
    text = _safe_filename(message.text or "")
    status = await message.reply_text("📥 **Starting...**", reply_markup=cancel(job.job_id))
    try:
        if job.selected_action == "convert_name":
            ext = job.output_ext
            name = f"{_base_without_extension(text)}.{ext}"
            kind = "video" if ext in VIDEO else "audio" if ext in AUDIO else "document"
            await process(client, job, status, name, kind, True)
        elif job.extra.get("rename_output_mode") == "video":
            name = f"{_base_without_extension(text)}.mp4"
            await process(client, job, status, name, "video", True)
        else:
            ext = _extension(job.original_name)
            name = f"{_base_without_extension(text)}.{ext}" if ext else text
            await process(client, job, status, name, "document", False)
        await cleanup(client, job, True)
        try:
            await client.delete_messages(message.chat.id, message.id)
        except Exception:
            pass
    except AniToonTransferCancelled:
        await status.edit_text("❌ **Processing cancelled.**")
        await cleanup(client, job)
    except Exception as exc:
        await status.edit_text(f"❌ **Processing failed**\n\n`{str(exc)[:1500]}`")
        await cleanup(client, job)
    raise StopPropagation

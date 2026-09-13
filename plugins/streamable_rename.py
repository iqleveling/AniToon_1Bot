"""Reliable rename output flow: Telegram document or streamable MP4 video."""

from __future__ import annotations

import asyncio
import os
import shutil
import time

from pyrogram import Client, StopPropagation, filters
from pyrogram.errors import FloodWait
from pyrogram.types import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from helper.database import db
from helper.ffmpeg import convert_media, get_video_info, take_screenshot
from helper.job_state import jobs
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes, progress_for_pyrogram
from plugins.rename import _base_without_extension, _extension, _safe_filename
from plugins.ui import rename_output_menu


def _cancel_menu(job_id: str):
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]])


async def _send_output(client, job, path, filename, status, as_video=False):
    size = os.path.getsize(path)
    if as_video:
        duration, width, height = await get_video_info(path)
        thumb = await take_screenshot(path, os.path.join(job.work_dir, "stream_thumb.jpg"), duration) if duration else None
        caption = f"✅ **AniToon Processed**\n\n📂 `{filename}`\n📦 `{humanbytes(size)}`"
        return await client.send_video(
            job.user_id,
            path,
            caption=caption,
            thumb=thumb,
            duration=int(duration) if duration else None,
            width=width or None,
            height=height or None,
            supports_streaming=True,
            progress=progress_for_pyrogram,
            progress_args=("📤 Uploading", status, time.time(), job.job_id),
        )

    caption = f"✅ **AniToon Processed**\n\n📂 `{filename}`\n📦 `{humanbytes(size)}`"
    return await client.send_document(
        job.user_id,
        path,
        caption=caption,
        progress=progress_for_pyrogram,
        progress_args=("📤 Uploading", status, time.time(), job.job_id),
    )


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"), group=-3000)
async def rename_output_chooser(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation
    await cb.answer()
    await jobs.update(job.job_id, selected_action="rename_output_choice")
    await cb.message.edit_text(
        "✏️ **Rename**\n\nChoose how you want the renamed file to be sent:",
        reply_markup=rename_output_menu(job.job_id),
    )
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^renameoutput:([0-9a-f]+):(file|video)$"), group=-3000)
async def choose_rename_output(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation
    mode = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, selected_action="custom_name", extra={**job.extra, "rename_output_mode": mode})
    await client.send_message(
        job.user_id,
        "✏️ **Rename:**\nSend me the new filename.",
        reply_markup=ForceReply(selective=True),
    )
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^transfer:cancel:([0-9a-f]+)$"), group=-3000)
async def cancel_transfer(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("This transfer is no longer active.", show_alert=True)
        raise StopPropagation
    from helper.utils import request_transfer_cancel
    request_transfer_cancel(job.job_id)
    await cb.answer("Cancelling...", show_alert=False)
    try:
        await cb.message.edit_text("❌ **Cancelling transfer...**")
    except Exception:
        pass
    raise StopPropagation


@Client.on_message(filters.private & filters.reply & filters.text, group=-3000)
async def renamed_output_reply(client, message: Message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action != "custom_name":
        return

    text = _safe_filename(message.text or "")
    if not text:
        await message.reply_text("❌ **Please send a valid filename.**")
        raise StopPropagation

    mode = job.extra.get("rename_output_mode", "file")
    original_ext = _extension(job.original_name)
    if mode == "video":
        name = f"{_base_without_extension(text)}.mp4"
        output_path = os.path.join(job.work_dir, name)
        status = await message.reply_text("🎬 **Converting to streamable MP4...**")
        try:
            # MP4 is encoded H.264/AAC + faststart in convert_media.
            ok = await convert_media(job.input_path, output_path, "mp4")
            if not ok or not os.path.isfile(output_path):
                raise RuntimeError("FFmpeg could not create the streamable MP4")
            duration, width, height = await get_video_info(output_path)
            if not duration or not width or not height:
                raise RuntimeError("Converted MP4 failed video validation")
            await status.edit_text(
                "📤 **Uploading streamable MP4...**",
                reply_markup=_cancel_menu(job.job_id),
            )
            clear_transfer_cancel(job.job_id)
            await _send_output(client, job, output_path, name, status, as_video=True)
            await db.update_usage(job.user_id, job.bot_id, os.path.getsize(job.input_path))
            await status.edit_text(
                "✅ **Video Complete!**\n\n"
                f"📂 `{name}`\n"
                f"⏱️ Runtime: `{int(duration)//60:02d}:{int(duration)%60:02d}`\n"
                f"📦 `{humanbytes(os.path.getsize(output_path))}`"
            )
        except AniToonTransferCancelled:
            await status.edit_text("❌ **Upload cancelled.**")
        except FloodWait as exc:
            await status.edit_text(f"⏳ **Telegram FloodWait**\nWaiting `{exc.value}` seconds...")
            await asyncio.sleep(exc.value)
        except Exception as exc:
            await status.edit_text(f"❌ **Video conversion/upload failed**\n\n`{str(exc)[:1000]}`")
        finally:
            clear_transfer_cancel(job.job_id)
            shutil.rmtree(job.work_dir, ignore_errors=True)
            await jobs.remove(job.job_id)
        raise StopPropagation

    name = text
    if not _extension(name) and original_ext:
        name = f"{name}.{original_ext}"
    elif _extension(name) and original_ext:
        name = f"{_base_without_extension(name)}.{original_ext}"
    output_path = os.path.join(job.work_dir, name)
    status = await message.reply_text("📤 **Uploading file...**", reply_markup=_cancel_menu(job.job_id))
    try:
        shutil.copy2(job.input_path, output_path)
        clear_transfer_cancel(job.job_id)
        await _send_output(client, job, output_path, name, status, as_video=False)
        await db.update_usage(job.user_id, job.bot_id, os.path.getsize(job.input_path))
        await status.edit_text(f"✅ **File Complete!**\n\n📂 `{name}`\n📦 `{humanbytes(os.path.getsize(output_path))}`")
    except AniToonTransferCancelled:
        await status.edit_text("❌ **Upload cancelled.**")
    except Exception as exc:
        await status.edit_text(f"❌ **File upload failed**\n\n`{str(exc)[:1000]}`")
    finally:
        clear_transfer_cancel(job.job_id)
        shutil.rmtree(job.work_dir, ignore_errors=True)
        await jobs.remove(job.job_id)
    raise StopPropagation

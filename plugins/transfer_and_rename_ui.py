"""High-priority transfer controls and the simple Rename output chooser.

This layer intentionally runs before the older rename handlers. It keeps the
existing advanced/conversion implementation intact while giving the normal
Rename flow cancellable transfers and proper Telegram video output.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
import uuid

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyrogram.errors import FloodWait

from config import Config
from helper.database import db
from helper.ffmpeg import convert_media, get_video_info, make_streamable, take_screenshot
from helper.job_state import Job, jobs
from helper.plans import get_plan
from helper.utils import (
    AniToonTransferCancelled,
    clear_transfer_cancel,
    humanbytes,
    progress_for_pyrogram,
    request_transfer_cancel,
)
from plugins.rename import (
    _base_without_extension,
    _extension,
    _media_from_message,
    _safe_filename,
    _user_context,
)


WAITING_RENAME = {"rename_output_choice", "rename_document", "rename_video"}
VIDEO_EXTENSIONS = {"mp4", "mkv", "webm", "mov", "avi", "flv", "ts", "m4v"}


def _rename_choice(job_id: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📄 Convert into File", callback_data=f"renameout:file:{job_id}"),
            InlineKeyboardButton("🎬 Convert into Video", callback_data=f"renameout:video:{job_id}"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")],
    ])


def _transfer_cancel_markup(job_id: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]
    ])


async def _find_downloaded_file(work_dir: str, result):
    if isinstance(result, str) and os.path.isfile(result):
        return result
    candidates = []
    for entry in os.listdir(work_dir):
        if entry.endswith(".part") or entry.startswith(".anitoon_download_"):
            continue
        path = os.path.join(work_dir, entry)
        if os.path.isfile(path):
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


@Client.on_message(
    filters.private & (filters.document | filters.video | filters.audio),
    group=-3000,
)
async def cancellable_file_intake(client: Client, message: Message):
    """Replace the older intake so the download itself has a working Cancel button."""
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

    # If a rename prompt is waiting, replace it with this new file.
    old_job = await jobs.get_user_job(user_id)
    if old_job and old_job.selected_action in WAITING_RENAME:
        request_transfer_cancel(old_job.job_id)
        shutil.rmtree(old_job.work_dir, ignore_errors=True)
        await jobs.remove(old_job.job_id)

    if used >= plan.daily_limit:
        await message.reply_text(
            "🚫 **Daily Limit Reached!**\n\n"
            f"Current Plan: {plan.name}\n"
            f"Daily Limit: `{humanbytes(plan.daily_limit)}`\n"
            f"Used: `{humanbytes(used)}`"
        )
        raise StopPropagation

    job_id = uuid.uuid4().hex[:12]
    work_dir = os.path.join("downloads", str(user_id), job_id)
    os.makedirs(work_dir, exist_ok=True)
    input_path = os.path.join(work_dir, original_name)
    job = Job(
        job_id=job_id,
        user_id=user_id,
        bot_id=bot_id,
        source_message_id=message.id,
        work_dir=work_dir,
        input_path=input_path,
        original_name=original_name,
        mime_type=mime_type,
        extra={
            "extension": extension,
            "user_data": user_data,
            "used_before": used,
            "telegram_file_size": expected_size,
        },
    )
    if not await jobs.register(job):
        await message.reply_text("⏳ **You already have an active file job.** Please finish or cancel it first.")
        raise StopPropagation

    clear_transfer_cancel(job_id)
    status = await message.reply_text("📥 **Downloading**\n━━━━━━━━━━━━━━━━━━━━\n[░░░░░░░░░░░░░░░░░░░░] 0%", reply_markup=_transfer_cancel_markup(job_id))
    await jobs.acquire()
    try:
        result = await client.download_media(
            message=message,
            file_name=work_dir,
            progress=progress_for_pyrogram,
            progress_args=("📥 Downloading", status, time.time(), job_id),
        )
        downloaded = await _find_downloaded_file(work_dir, result)
        if not downloaded:
            raise RuntimeError("Telegram download completed but no local file was found")

        actual_size = os.path.getsize(downloaded)
        if expected_size and actual_size != expected_size:
            raise RuntimeError(f"Incomplete download: expected {expected_size} bytes, got {actual_size} bytes")

        if downloaded != input_path:
            os.replace(downloaded, input_path)
        await jobs.update(job_id, extra={**job.extra, "downloaded_size": actual_size})

        if used + actual_size > plan.daily_limit:
            await status.edit_text(
                "🚫 **This file exceeds your remaining daily quota.**\n\n"
                f"Remaining: `{humanbytes(max(plan.daily_limit - used, 0))}`\n"
                f"File: `{humanbytes(actual_size)}`"
            )
            await jobs.remove(job_id)
            shutil.rmtree(work_dir, ignore_errors=True)
            raise StopPropagation

        await status.edit_text(
            "✅ **Download Completed!**\n\n"
            f"📂 **Original:** `{original_name}`\n"
            f"📦 **Size:** `{humanbytes(actual_size)}`\n\n"
            "Choose what you want to do:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Rename", callback_data=f"job:rename:{job_id}"),
                 InlineKeyboardButton("🛠 Advanced", callback_data=f"job:advanced:{job_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")],
            ]),
        )
    except AniToonTransferCancelled:
        await status.edit_text("❌ **Download cancelled.**")
        await jobs.remove(job_id)
        shutil.rmtree(work_dir, ignore_errors=True)
    except FloodWait as exc:
        await status.edit_text(f"⏳ **Telegram FloodWait**\n\nWaiting `{exc.value}` seconds...")
        await asyncio.sleep(exc.value)
        await jobs.remove(job_id)
        shutil.rmtree(work_dir, ignore_errors=True)
    except Exception as exc:
        await status.edit_text(f"❌ **Download failed**\n\n`{str(exc)[:1000]}`")
        await jobs.remove(job_id)
        shutil.rmtree(work_dir, ignore_errors=True)
    finally:
        clear_transfer_cancel(job_id)
        jobs.release()
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^transfer:cancel:([0-9a-f]+)$"), group=-3000)
async def cancel_transfer(client, cb):
    job_id = cb.matches[0].group(1)
    job = await jobs.get(job_id)
    if not job:
        await cb.answer("This job is already finished.", show_alert=True)
        raise StopPropagation
    request_transfer_cancel(job_id)
    job.active = False
    await cb.answer("Cancelling…")
    try:
        await cb.message.edit_text("🛑 **Cancelling transfer...**")
    except Exception:
        pass
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"), group=-3000)
async def rename_output_choice(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation
    await cb.answer()
    await jobs.update(job.job_id, selected_action="rename_output_choice")
    try:
        await cb.message.edit_text(
            "✏️ **Rename**\n\nChoose how the renamed file should be sent:",
            reply_markup=_rename_choice(job.job_id),
        )
    except Exception:
        await cb.message.reply_text(
            "✏️ **Rename**\n\nChoose how the renamed file should be sent:",
            reply_markup=_rename_choice(job.job_id),
        )
    raise StopPropagation


async def _ask_rename_name(client, cb, job, mode):
    await jobs.update(job.job_id, selected_action=mode)
    label = "📄 **Convert into File**" if mode == "rename_document" else "🎬 **Convert into Video**"
    await cb.message.reply_text(
        f"{label}\n\n✏️ **Rename:**\nSend me the new filename."
    )


@Client.on_callback_query(filters.regex(r"^renameout:(file|video):([0-9a-f]+)$"), group=-3000)
async def choose_rename_output(client, cb):
    mode = "rename_document" if cb.matches[0].group(1) == "file" else "rename_video"
    job = await jobs.get(cb.matches[0].group(2))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation
    await cb.answer()
    await _ask_rename_name(client, cb, job, mode)
    raise StopPropagation


@Client.on_message(filters.private & filters.text, group=-3000)
async def rename_name_handler(client, message: Message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in {"rename_document", "rename_video"}:
        return

    text = _safe_filename((message.text or "").strip())
    if not text:
        await message.reply_text("❌ **Please send a valid filename.**")
        raise StopPropagation

    source_ext = _extension(job.original_name)
    mode = job.selected_action
    if mode == "rename_document":
        ext = source_ext or "mkv"
        if _extension(text):
            text = f"{_base_without_extension(text)}.{ext}"
        else:
            text = f"{text}.{ext}"
        output_path = os.path.join(job.work_dir, text)
        try:
            shutil.copy2(job.input_path, output_path)
            status = await message.reply_text("📤 **Uploading**\n━━━━━━━━━━━━━━━━━━━━\n[░░░░░░░░░░░░░░░░░░░░] 0%", reply_markup=_transfer_cancel_markup(job.job_id))
            clear_transfer_cancel(job.job_id)
            await client.send_document(
                job.user_id,
                output_path,
                caption=f"✅ **AniToon Processed**\n\n📂 `{text}`\n📦 `{humanbytes(os.path.getsize(output_path))}`",
                progress=progress_for_pyrogram,
                progress_args=("📤 Uploading", status, time.time(), job.job_id),
            )
            await status.edit_text(f"✅ **Rename Complete!**\n\n📂 `{text}`\n📦 `{humanbytes(os.path.getsize(output_path))}`")
        except AniToonTransferCancelled:
            await message.reply_text("❌ **Upload cancelled.**")
        except Exception as exc:
            await message.reply_text(f"❌ **Processing failed**\n\n`{str(exc)[:1000]}`")
        finally:
            clear_transfer_cancel(job.job_id)
            shutil.rmtree(job.work_dir, ignore_errors=True)
            await jobs.remove(job.job_id)
        raise StopPropagation

    # Video mode always produces MP4, regardless of the original extension.
    name = _base_without_extension(text) + ".mp4"
    output_path = os.path.join(job.work_dir, name)
    status = await message.reply_text("🎬 **Converting to streamable MP4...**\n\n❌ Cancel is available during upload.")
    try:
        ok = await convert_media(job.input_path, output_path, "mp4")
        if not ok or not os.path.isfile(output_path):
            raise RuntimeError("FFmpeg MP4 conversion failed")

        streamable_path = os.path.join(job.work_dir, f".streamable_{uuid.uuid4().hex}.mp4")
        converted = await make_streamable(output_path, streamable_path)
        if converted and os.path.isfile(converted):
            os.replace(converted, output_path)

        duration, width, height = await get_video_info(output_path)
        thumb = await take_screenshot(output_path, os.path.join(job.work_dir, "thumb.jpg"), duration) if duration else None

        clear_transfer_cancel(job.job_id)
        await status.edit_text(
            "📤 **Uploading**\n━━━━━━━━━━━━━━━━━━━━\n[░░░░░░░░░░░░░░░░░░░░] 0%",
            reply_markup=_transfer_cancel_markup(job.job_id),
        )
        await client.send_video(
            job.user_id,
            output_path,
            caption=f"✅ **AniToon Processed**\n\n📂 `{name}`\n📦 `{humanbytes(os.path.getsize(output_path))}`",
            thumb=thumb,
            duration=int(duration) if duration else None,
            width=width or None,
            height=height or None,
            supports_streaming=True,
            progress=progress_for_pyrogram,
            progress_args=("📤 Uploading", status, time.time(), job.job_id),
        )
        await status.edit_text(
            "✅ **Video Ready!**\n\n"
            f"📂 `{name}`\n"
            f"📦 `{humanbytes(os.path.getsize(output_path))}`\n"
            f"⏱️ **Runtime:** `{int(duration // 60):02d}:{int(duration % 60):02d}`"
        )
    except AniToonTransferCancelled:
        await status.edit_text("❌ **Upload cancelled.**")
    except Exception as exc:
        await status.edit_text(f"❌ **Video processing failed**\n\n`{str(exc)[:1000]}`")
    finally:
        clear_transfer_cancel(job.job_id)
        shutil.rmtree(job.work_dir, ignore_errors=True)
        await jobs.remove(job.job_id)
    raise StopPropagation

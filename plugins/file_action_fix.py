from __future__ import annotations

import asyncio
import os
import shutil
import time
import uuid

from pyrogram import Client, StopPropagation, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from helper.database import db
from helper.ffmpeg import convert_media
from helper.job_state import Job, jobs
from helper.plans import get_plan
from helper.utils import humanbytes, progress_for_pyrogram
from plugins.rename import (
    _ask_name,
    _base_without_extension,
    _detect_name,
    _extension,
    _media_from_message,
    _safe_filename,
    _user_context,
)
from plugins.ui import file_action_menu


VIDEO_MIME = {
    "mp4": "video/mp4",
    "mkv": "video/x-matroska",
    "webm": "video/webm",
    "mov": "video/quicktime",
}

AUDIO_MIME = {
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
}

WAITING_ACTIONS = {"rename_format", "custom_name", "convert_name"}


async def _download_verified(client: Client, message: Message, path: str, status: Message, expected_size: int) -> int:
    """Download the Telegram media and verify the complete byte count."""
    last_error = None
    for attempt in range(1, 4):
        try:
            if os.path.exists(path):
                os.remove(path)
            await status.edit_text(
                "📥 **AniToon: Downloading...**"
                + (f"\n\nRetry `{attempt}/3`" if attempt > 1 else "")
            )
            result = await client.download_media(
                message=message,
                file_name=path,
                progress=progress_for_pyrogram,
                progress_args=("📥 Downloading", status, time.time()),
            )
            if isinstance(result, str) and os.path.isfile(result) and result != path:
                if os.path.exists(path):
                    os.remove(path)
                shutil.move(result, path)

            if not os.path.isfile(path):
                raise RuntimeError("Telegram did not create the downloaded file")

            actual = os.path.getsize(path)
            if expected_size and actual != expected_size:
                last_error = RuntimeError(
                    f"Incomplete Telegram download: expected {expected_size} bytes, got {actual} bytes"
                )
                continue
            return actual
        except FloodWait:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(1)

    raise last_error or RuntimeError("Download failed")


async def _send_plain_output(client: Client, job: Job, path: str, filename: str):
    """Reliable rename sender without the progress/thumbnail path that can fail."""
    ext = _extension(filename)
    mime = job.mime_type or ""
    caption = (
        "✅ **AniToon Processed**\n\n"
        f"📂 `{filename}`\n"
        f"📦 `{humanbytes(os.path.getsize(path))}`"
    )

    if mime.startswith("video/") or ext in {"mp4", "mkv", "webm", "mov", "avi", "flv", "ts", "m4v"}:
        try:
            return await client.send_video(job.user_id, path, caption=caption)
        except Exception:
            return await client.send_document(job.user_id, path, caption=caption)

    if mime.startswith("audio/") or ext in {"mp3", "m4a", "aac", "flac", "ogg", "wav", "opus"}:
        try:
            return await client.send_audio(job.user_id, path, caption=caption)
        except Exception:
            return await client.send_document(job.user_id, path, caption=caption)

    return await client.send_document(job.user_id, path, caption=caption)


@Client.on_message(
    filters.private & (filters.document | filters.video | filters.audio),
    group=-1000,
)
async def repaired_file_download(client: Client, message: Message):
    """High-priority intake: use Telegram's real file size and verify the download."""
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
    original_name = _safe_filename(
        getattr(media, "file_name", None) or f"file_{message.id}"
    )
    extension = _extension(original_name)
    mime_type = getattr(media, "mime_type", None) or ""

    if used >= plan.daily_limit:
        await message.reply_text(
            "🚫 **Daily Limit Reached!**\n\n"
            f"Current Plan: {plan.name}\n"
            f"Daily Limit: `{humanbytes(plan.daily_limit)}`\n"
            f"Used: `{humanbytes(used)}`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("💎 Upgrade", callback_data="upgrade")]]
            ),
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
        await message.reply_text(
            "⏳ **You already have an active file job.**\n\n"
            "Please finish or cancel it first."
        )
        raise StopPropagation

    status = await message.reply_text("⏳ **AniToon: Starting download...**")
    await jobs.acquire()
    try:
        actual_size = await _download_verified(
            client, message, input_path, status, expected_size
        )
        if used + actual_size > plan.daily_limit:
            await status.edit_text(
                "🚫 **This file exceeds your remaining daily quota.**\n\n"
                f"Plan: {plan.name}\n"
                f"Remaining: `{humanbytes(max(plan.daily_limit - used, 0))}`\n"
                f"File: `{humanbytes(actual_size)}`"
            )
            await jobs.remove(job_id)
            shutil.rmtree(work_dir, ignore_errors=True)
            raise StopPropagation

        auto_name, detected = _detect_name(original_name)
        await jobs.update(
            job_id,
            detected_name=f"{auto_name}.{extension}" if extension else auto_name,
            extra={
                **job.extra,
                "downloaded_size": actual_size,
                "detected": detected,
            },
        )
        await status.edit_text(
            "✅ **Download Completed!**\n\n"
            f"📂 **Original:** `{original_name}`\n"
            f"📦 **Size:** `{humanbytes(actual_size)}`\n\n"
            "Choose what you want to do:",
            reply_markup=file_action_menu(job_id),
        )
    except StopPropagation:
        raise
    except FloodWait as exc:
        await status.edit_text(
            f"⏳ **Telegram FloodWait**\n\nWaiting `{exc.value}` seconds..."
        )
        await asyncio.sleep(exc.value)
    except Exception as exc:
        await status.edit_text(f"❌ **Download failed**\n\n`{str(exc)[:1000]}`")
        await jobs.remove(job_id)
        shutil.rmtree(work_dir, ignore_errors=True)
    finally:
        jobs.release()

    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"), group=-1000)
async def rename_entry_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation

    await cb.answer()
    await jobs.update(job.job_id, selected_action="custom_name")
    await _ask_name(
        client,
        job.user_id,
        "✏️ **Rename:**\nSend me the new filename.",
        job.job_id,
        "custom_name",
    )
    raise StopPropagation


@Client.on_callback_query(
    filters.regex(r"^job:renameformat:([0-9a-f]+):(document|video)$"),
    group=-1000,
)
async def rename_format_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation

    mode = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, extra={**job.extra, "rename_output_mode": mode})
    job.mime_type = VIDEO_MIME["mp4"] if mode == "video" else "application/octet-stream"
    await _ask_name(
        client,
        job.user_id,
        "✏️ **Rename:**\nSend me the new filename.",
        job.job_id,
        "custom_name",
    )
    raise StopPropagation


@Client.on_callback_query(
    filters.regex(r"^job:format:([0-9a-f]+):(mp4|mkv|webm|mov|mp3|m4a)$"),
    group=-1000,
)
async def convert_entry_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation

    fmt = cb.matches[0].group(2)
    await cb.answer()
    job.output_ext = fmt
    job.mime_type = VIDEO_MIME.get(fmt) or AUDIO_MIME.get(fmt) or "application/octet-stream"
    await _ask_name(
        client,
        job.user_id,
        f"🔄 **Convert to {fmt.upper()}**\n\nEnter the output filename.\nThe `.{fmt}` extension will be used.",
        job.job_id,
        "convert_name",
    )
    raise StopPropagation


@Client.on_message(filters.private & filters.reply & filters.text, group=-1000)
async def rename_reply_fix(client, message: Message):
    """Handle rename text without depending on ForceReply internals."""
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
        output_path = os.path.join(job.work_dir, name)
        status = await message.reply_text(f"🔄 **Converting to {ext.upper()}...**")
        try:
            ok = await convert_media(job.input_path, output_path, ext)
            if not ok:
                raise RuntimeError("FFmpeg conversion failed")
            await _send_plain_output(client, job, output_path, name)
            await db.update_usage(job.user_id, job.bot_id, os.path.getsize(job.input_path))
            await status.edit_text(
                "✅ **Conversion Complete!**\n\n"
                f"📂 `{name}`\n📦 `{humanbytes(os.path.getsize(output_path))}`"
            )
        except Exception as exc:
            await status.edit_text(f"❌ **Conversion failed**\n\n`{str(exc)[:1000]}`")
        finally:
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
    status = await message.reply_text("📦 **Preparing renamed file...**")
    try:
        shutil.copy2(job.input_path, output_path)
        await _send_plain_output(client, job, output_path, name)
        await db.update_usage(job.user_id, job.bot_id, os.path.getsize(job.input_path))
        await status.edit_text(
            "✅ **Rename Complete!**\n\n"
            f"📂 `{name}`\n📦 `{humanbytes(os.path.getsize(output_path))}`"
        )
    except Exception as exc:
        await status.edit_text(f"❌ **Processing failed**\n\n`{str(exc)[:1000]}`")
    finally:
        shutil.rmtree(job.work_dir, ignore_errors=True)
        await jobs.remove(job.job_id)
    raise StopPropagation


@Client.on_message(
    filters.private & (filters.document | filters.video | filters.audio),
    group=-999,
)
async def retry_file_when_waiting(client, message: Message):
    """A new file replaces an abandoned rename/convert prompt."""
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in WAITING_ACTIONS:
        return
    shutil.rmtree(job.work_dir, ignore_errors=True)
    await jobs.remove(job.job_id)
    await message.reply_text("🔄 **Previous rename request cleared. Starting the new file...**")
    raise StopPropagation

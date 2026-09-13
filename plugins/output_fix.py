"""Output delivery repair layer.

Keeps converted videos as real Telegram videos instead of sending them through
an ordinary document-style output path.  It also supplies duration, dimensions
and a generated thumbnail so Telegram can show the normal video preview.
"""

from __future__ import annotations

import os
import shutil
import time

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import Message

from helper.database import db
from helper.ffmpeg import convert_media, get_video_info, take_screenshot
from helper.job_state import jobs
from helper.utils import humanbytes, progress_for_pyrogram
from plugins.rename import _ask_name, _base_without_extension, _extension, _safe_filename

VIDEO_FORMATS = {"mp4", "mkv", "webm", "mov"}
AUDIO_FORMATS = {"mp3", "m4a"}


@Client.on_callback_query(
    filters.regex(r"^job:format:([0-9a-f]+):(mp4|mkv|webm|mov|mp3|m4a)$"),
    group=-2000,
)
async def converted_format_prompt(client, cb):
    """Capture the selected conversion format before older handlers run."""
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation

    fmt = cb.matches[0].group(2)
    await cb.answer()
    job.output_ext = fmt
    job.mime_type = (
        "video/mp4" if fmt == "mp4" else
        "video/x-matroska" if fmt == "mkv" else
        "video/webm" if fmt == "webm" else
        "video/quicktime" if fmt == "mov" else
        "audio/mpeg" if fmt == "mp3" else
        "audio/mp4"
    )
    await _ask_name(
        client,
        job.user_id,
        f"🔄 **Convert to {fmt.upper()}**\n\nEnter the output filename.\nThe `.{fmt}` extension will be used.",
        job.job_id,
        "convert_name",
    )
    raise StopPropagation


@Client.on_message(filters.private & filters.reply & filters.text, group=-2000)
async def converted_file_reply(client, message: Message):
    """Convert and send a video with Telegram's normal video preview metadata."""
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action != "convert_name":
        return

    text = (message.text or "").strip()
    fmt = job.output_ext
    if not text or not fmt:
        await message.reply_text("❌ **Please send a valid filename.**")
        raise StopPropagation

    name = _safe_filename(text)
    if _extension(name) != fmt:
        name = f"{_base_without_extension(name)}.{fmt}"
    output_path = os.path.join(job.work_dir, name)
    status = await message.reply_text(f"🔄 **Converting to {fmt.upper()}...**")

    try:
        ok = await convert_media(job.input_path, output_path, fmt)
        if not ok or not os.path.isfile(output_path):
            raise RuntimeError("FFmpeg conversion failed")

        # For video outputs, probe the converted file and generate a real
        # thumbnail.  This makes Telegram render it as a normal playable video
        # instead of a blank/zero-duration media card.
        duration = width = height = 0
        thumb = None
        if fmt in VIDEO_FORMATS:
            duration, width, height = await get_video_info(output_path)
            if duration > 0:
                thumb = await take_screenshot(
                    output_path,
                    os.path.join(job.work_dir, "converted_thumb.jpg"),
                    duration,
                )

        from plugins.rename import _send_output

        await _send_output(
            client,
            message,
            job,
            output_path,
            name,
            status,
            duration,
            width,
            height,
            thumb,
        )

        input_size = os.path.getsize(job.input_path)
        await db.update_usage(job.user_id, job.bot_id, input_size)
        await status.edit_text(
            "✅ **Conversion Complete!**\n\n"
            f"📂 `{name}`\n"
            f"📦 `{humanbytes(os.path.getsize(output_path))}`"
        )
    except Exception as exc:
        await status.edit_text(f"❌ **Conversion failed**\n\n`{str(exc)[:1000]}`")
    finally:
        shutil.rmtree(job.work_dir, ignore_errors=True)
        await jobs.remove(job.job_id)

    raise StopPropagation

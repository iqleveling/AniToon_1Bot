from __future__ import annotations

import os
import shutil

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import Message

from helper.job_state import jobs
from helper.ffmpeg import convert_media
from helper.utils import humanbytes
from plugins.rename import _ask_name, _finish_job, _extension, _safe_filename, _base_without_extension


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


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"), group=-1000)
async def rename_entry_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        await cb.answer("Job expired. Send the file again.", show_alert=True)
        raise StopPropagation

    from plugins.ui import rename_format_menu, edit_callback_message

    await cb.answer()
    await jobs.update(job.job_id, selected_action="rename_format")
    await edit_callback_message(
        cb,
        "✏️ **Rename File**\n\nChoose how you want the renamed file to be sent:",
        rename_format_menu(job.job_id),
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
    await jobs.update(
        job.job_id,
        extra={**job.extra, "rename_output_mode": mode},
    )

    if mode == "video":
        job.mime_type = VIDEO_MIME["mp4"]
    else:
        job.mime_type = "application/octet-stream"

    # The Rename flow intentionally asks only for the filename after the mode choice.
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

    if fmt in VIDEO_MIME:
        job.mime_type = VIDEO_MIME[fmt]
    elif fmt in AUDIO_MIME:
        job.mime_type = AUDIO_MIME[fmt]
    else:
        job.mime_type = "application/octet-stream"

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
    """Reliable filename reply handler.

    The old handler relied on the replied-to message still exposing ForceReply.
    Telegram clients can omit that markup when the message is edited/replied to,
    which left the job active forever. The selected job action is the authoritative
    state here.
    """
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
            await _finish_job(client, message, job, output_path, name)
        except Exception as exc:
            await status.edit_text(f"❌ **Conversion failed**\n\n`{str(exc)[:1000]}`")
        raise StopPropagation

    ext = _extension(job.original_name)
    name = _safe_filename(text)
    if not _extension(name) and ext:
        name = f"{name}.{ext}"

    output_path = os.path.join(job.work_dir, name)
    try:
        shutil.copy2(job.input_path, output_path)
        await _finish_job(client, message, job, output_path, name)
    except Exception as exc:
        await message.reply_text(f"❌ **Rename failed**\n\n`{str(exc)[:1000]}`")
    raise StopPropagation


@Client.on_message(
    filters.private & (filters.document | filters.video | filters.audio),
    group=-1000,
)
async def retry_file_when_waiting(client, message: Message):
    """Allow a user to retry a file when a previous rename prompt was abandoned."""
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in WAITING_ACTIONS:
        return

    try:
        shutil.rmtree(job.work_dir, ignore_errors=True)
    finally:
        await jobs.remove(job.job_id)

    # Let the normal file router/download handler process the replacement file.
    raise StopPropagation

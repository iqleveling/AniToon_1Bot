from __future__ import annotations

from pyrogram import Client, StopPropagation, filters

from helper.job_state import jobs
from plugins.rename import _ask_name


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
        prompt = (
            "🎬 **Rename as Video**\n\n"
            "Enter the new filename.\n"
            "The file will be sent as a video."
        )
    else:
        job.mime_type = "application/octet-stream"
        prompt = (
            "📄 **Rename as Document**\n\n"
            "Enter the new filename.\n"
            "The file will be sent as a document."
        )

    await _ask_name(
        client,
        job.user_id,
        prompt,
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
        f"🔄 **Convert to {fmt.upper()}**\n\n"
        f"Enter the output filename.\n"
        f"The `.{fmt}` extension will be used.",
        job.job_id,
        "convert_name",
    )
    raise StopPropagation

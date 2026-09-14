from __future__ import annotations

import os
import time

from pyrogram import Client, StopPropagation, filters

from helper.ffmpeg import get_video_info, make_streamable
from helper.job_state import jobs
from helper.utils import progress_for_pyrogram


@Client.on_callback_query(filters.regex(r"^job:sendvideo:([0-9a-f]+)$"), group=-1300)
async def send_video_fix(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("Job expired.", show_alert=True)
        raise StopPropagation
    path = job.input_path
    duration, width, height = await get_video_info(path)
    if duration <= 0 or width <= 0 or height <= 0:
        await cb.answer("Invalid video file.", show_alert=True)
        raise StopPropagation
    await cb.answer()
    streamable = os.path.join(job.work_dir, "telegram_streamable.mp4")
    remuxed = await make_streamable(path, streamable)
    if remuxed:
        path = remuxed
        duration, width, height = await get_video_info(path)
    await client.send_video(
        job.user_id,
        path,
        caption=f"✅ **AniToon Processed**\n\n📂 `{os.path.basename(path)}`",
        duration=max(1, int(round(duration))),
        width=width,
        height=height,
        supports_streaming=True,
        progress=progress_for_pyrogram,
        progress_args=("Uploading", cb.message, time.time(), job.job_id),
    )
    raise StopPropagation

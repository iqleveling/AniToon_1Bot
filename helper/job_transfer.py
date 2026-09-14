from __future__ import annotations

import os
import time

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from helper.job_state import Job, jobs
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel, humanbytes, progress_for_pyrogram


def cancel_markup(job_id: str):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]]
    )


async def download_job(client: Client, message: Message, job: Job, status: Message) -> int:
    """Download a job only after the user has selected an operation/name."""
    if os.path.isfile(job.input_path):
        return os.path.getsize(job.input_path)

    expected_size = int(job.extra.get("telegram_file_size", 0) or 0)
    os.makedirs(job.work_dir, exist_ok=True)
    await jobs.acquire()
    try:
        # Do not add a separate "Downloading..." message here. The same status
        # message is reused by progress_for_pyrogram for the live transfer stats.
        clear_transfer_cancel(job.job_id)
        result = await client.download_media(
            message=message,
            file_name=job.input_path,
            progress=progress_for_pyrogram,
            progress_args=("Downloading", status, time.time(), job.job_id),
        )
        path = result if isinstance(result, str) and os.path.isfile(result) else job.input_path
        if path != job.input_path and os.path.isfile(path):
            os.replace(path, job.input_path)
        if not os.path.isfile(job.input_path):
            raise RuntimeError("Telegram download completed but the local file was not found")
        actual = os.path.getsize(job.input_path)
        if expected_size and actual != expected_size:
            raise RuntimeError(f"Incomplete download: expected {humanbytes(expected_size)}, got {humanbytes(actual)}")
        await jobs.update(job.job_id, extra={**job.extra, "downloaded_size": actual})
        return actual
    except AniToonTransferCancelled:
        try:
            await status.edit_text("❌ **Processing cancelled.**")
        except Exception:
            pass
        raise
    except FloodWait:
        raise
    finally:
        clear_transfer_cancel(job.job_id)
        jobs.release()


async def cancel_job(job_id: str, user_id: int, status: Message | None = None) -> bool:
    job = await jobs.get(job_id)
    if not job or job.user_id != user_id:
        return False
    from helper.utils import request_transfer_cancel
    request_transfer_cancel(job_id)
    if status:
        try:
            await status.edit_text("❌ **Cancelling processing...**")
        except Exception:
            pass
    return True

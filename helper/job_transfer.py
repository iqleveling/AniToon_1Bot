from __future__ import annotations

import os
import time

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from helper.job_state import Job, jobs
from helper.message_cleanup import protect_transfer_message
from helper.utils import AniToonTransferCancelled, humanbytes, progress_for_pyrogram, reset_progress


def cancel_markup(job_id: str):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]]
    )


async def _show_processing(status: Message | None):
    """Deprecated visual state: intentionally do not show a Processing message.

    The download progress message remains visible while FFmpeg/preparation runs.
    The upload progress callback replaces it as soon as Telegram upload begins.
    """
    if status is None:
        return
    await protect_transfer_message(status)


async def download_job(client: Client, message: Message, job: Job, status: Message) -> int:
    """Download a deferred job without replacing the progress UI with Processing."""
    if os.path.isfile(job.input_path):
        actual = os.path.getsize(job.input_path)
        await protect_transfer_message(status)
        return actual

    expected_size = int(job.extra.get("telegram_file_size", 0) or 0)
    source = job.extra.get("source_message") or job.extra.get("file_id") or message

    os.makedirs(job.work_dir, exist_ok=True)
    await jobs.acquire()
    try:
        from helper.utils import is_transfer_cancelled
        if is_transfer_cancelled(job.job_id):
            raise AniToonTransferCancelled("Transfer cancelled by user")

        reset_progress(job.job_id)
        started = time.time()
        if expected_size:
            await progress_for_pyrogram(0, expected_size, "Downloading", status, started, job.job_id)

        result = await client.download_media(
            message=source,
            file_name=job.input_path,
            progress=progress_for_pyrogram,
            progress_args=("Downloading", status, started, job.job_id),
        )
        path = result if isinstance(result, str) and os.path.isfile(result) else job.input_path
        if path != job.input_path and os.path.isfile(path):
            os.replace(path, job.input_path)
        if not os.path.isfile(job.input_path):
            raise RuntimeError("Telegram download completed but the local file was not found")

        actual = os.path.getsize(job.input_path)
        if expected_size and actual != expected_size:
            raise RuntimeError(
                f"Incomplete download: expected {humanbytes(expected_size)}, got {humanbytes(actual)}"
            )

        # Keep the same Download Progress message at 100% while any conversion,
        # remuxing, thumbnail preparation, or other local processing happens.
        # _deliver_output will switch this exact message to Upload Progress when
        # client.send_* actually starts uploading the prepared result.
        await progress_for_pyrogram(
            actual,
            expected_size or actual,
            "Downloading",
            status,
            started,
            job.job_id,
        )
        await jobs.update(job.job_id, extra={**job.extra, "downloaded_size": actual})
        await protect_transfer_message(status)
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

"""User-facing cancellation command for the current file job."""

import os
import shutil

from pyrogram import Client, StopPropagation, filters

from helper.job_state import jobs
from helper.utils import clear_transfer_cancel, request_transfer_cancel


async def _cancel_job(client, message, job):
    request_transfer_cancel(job.job_id)

    # If the file has not started downloading yet, there is no transfer loop
    # to observe the cancellation flag, so remove the waiting job immediately.
    if not os.path.exists(job.input_path):
        await jobs.remove(job.job_id)
        shutil.rmtree(job.work_dir, ignore_errors=True)
        clear_transfer_cancel(job.job_id)
        await message.reply_text("❌ **Current file processing has been cancelled.**")
        return

    # During an active transfer, keep the Job registered until download/upload
    # unwinds. Removing it here can allow a second file to start concurrently.
    await message.reply_text("❌ **Cancelling current file processing...**")


@Client.on_message(filters.private & filters.command("cancel"), group=-4000)
async def cancel_command(client, message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job:
        await message.reply_text("ℹ️ **No active file processing job.**")
        raise StopPropagation

    await _cancel_job(client, message, job)
    raise StopPropagation

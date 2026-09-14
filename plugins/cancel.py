"""User-facing cancellation command for the current file job."""

import os
import shutil

from pyrogram import Client, StopPropagation, filters

from helper.job_state import jobs
from helper.utils import request_transfer_cancel


@Client.on_message(filters.private & filters.command("cancel"), group=-4000)
async def cancel_command(client, message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job:
        await message.reply_text("ℹ️ **No active file processing job.**")
        raise StopPropagation

    request_transfer_cancel(job.job_id)
    await jobs.remove(job.job_id)
    shutil.rmtree(job.work_dir, ignore_errors=True)
    await message.reply_text("❌ **Current file processing has been cancelled.**")
    raise StopPropagation

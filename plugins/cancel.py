"""Reliable user cancellation for queued and active AniToon jobs."""

from __future__ import annotations

import os
import shutil

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from helper.cancel_manager import cancel_job_tasks
from helper.job_state import jobs
from helper.utils import clear_transfer_cancel, request_transfer_cancel


def _cancel_markup(job_id: str):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]]
    )


async def _request_cancel(client, user_id: int, job, response_message=None):
    # Set the cooperative flag first, then cancel the asyncio task. This covers
    # both Pyrogram transfers (which may be awaiting Telegram I/O) and FFmpeg.
    request_transfer_cancel(job.job_id)
    cancelled_tasks = await cancel_job_tasks(job.job_id)

    if response_message is not None:
        try:
            await response_message.edit_text("❌ **Cancelling current file...**")
        except Exception:
            pass

    # A job that has not started yet has no transfer task to unwind, so it is
    # safe to remove immediately. Active jobs are cleaned by their owner task.
    input_exists = os.path.isfile(job.input_path)
    processing = bool((getattr(job, "extra", {}) or {}).get("processing"))
    if not input_exists and not processing and cancelled_tasks == 0:
        await jobs.remove(job.job_id)
        shutil.rmtree(job.work_dir, ignore_errors=True)
        clear_transfer_cancel(job.job_id)
        return True

    return True


@Client.on_callback_query(filters.regex(r"^transfer:cancel:([0-9a-f]+)$"), group=-5000)
async def cancel_transfer_callback(client, cb):
    job_id = cb.matches[0].group(1)
    job = await jobs.get(job_id)
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("This file is no longer active.", show_alert=True)
        raise StopPropagation

    await cb.answer("Cancelling...", show_alert=False)
    await _request_cancel(client, cb.from_user.id, job, cb.message)
    raise StopPropagation


@Client.on_message(filters.private & filters.command("cancel"), group=-5000)
async def cancel_command(client, message):
    user_id = int(message.from_user.id)
    job = await jobs.get_user_job(user_id)
    if not job:
        await message.reply_text("ℹ️ **No active file processing job.**")
        raise StopPropagation

    status = await message.reply_text("❌ **Cancelling current file...**")
    await _request_cancel(client, user_id, job, status)
    raise StopPropagation

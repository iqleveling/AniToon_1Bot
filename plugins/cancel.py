"""Reliable cancellation and cooperative download pause/resume."""
from __future__ import annotations

import shutil

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from helper.cancel_manager import cancel_job_tasks
from helper.job_state import jobs
from helper.utils import clear_transfer_cancel, request_transfer_cancel, request_transfer_pause, request_transfer_resume


def _transfer_markup(job_id: str, paused: bool = False):
    action = "resume" if paused else "pause"
    label = "▶️ Resume" if paused else "⏸️ Pause"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"transfer:{action}:{job_id}"), InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]])


async def _delete_job_ui(client, job):
    extra = getattr(job, "extra", {}) or {}
    ids = {getattr(job, "source_message_id", None), extra.get("prompt_message_id"), extra.get("rename_prompt_message_id"), extra.get("rename_menu_message_id"), extra.get("status_message_id")}
    for message_id in ids:
        if message_id:
            try: await client.delete_messages(job.user_id, int(message_id))
            except Exception: pass


async def _request_cancel(client, user_id: int, job, response_message=None):
    request_transfer_cancel(job.job_id)
    cancelled = await cancel_job_tasks(job.job_id)
    if response_message is not None:
        try: await response_message.edit_text("❌ **Cancelling current file...**")
        except Exception: pass
    if cancelled == 0:
        await _delete_job_ui(client, job)
        await jobs.remove(job.job_id)
        shutil.rmtree(job.work_dir, ignore_errors=True)
        clear_transfer_cancel(job.job_id)
    return True


@Client.on_callback_query(filters.regex(r"^transfer:(pause|resume):([0-9a-f]+)$"), group=-5000)
async def transfer_pause_resume(client, cb):
    job = await jobs.get(cb.matches[0].group(2))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("This file is no longer active.", show_alert=True)
        raise StopPropagation
    action = cb.matches[0].group(1)
    if action == "pause":
        request_transfer_pause(job.job_id)
        await cb.answer("Download paused")
        try: await cb.message.edit_reply_markup(_transfer_markup(job.job_id, paused=True))
        except Exception: pass
    else:
        request_transfer_resume(job.job_id)
        await cb.answer("Download resumed")
        try: await cb.message.edit_reply_markup(_transfer_markup(job.job_id, paused=False))
        except Exception: pass
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^transfer:cancel:([0-9a-f]+)$"), group=-5000)
async def cancel_transfer_callback(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer("This file is no longer active.", show_alert=True)
        raise StopPropagation
    await cb.answer("Cancelling...")
    await _request_cancel(client, cb.from_user.id, job, cb.message)
    raise StopPropagation


@Client.on_message(filters.private & filters.command("cancel"), group=-5000)
async def cancel_command(client, message):
    job = await jobs.get_user_job(int(message.from_user.id))
    if not job:
        await message.reply_text("ℹ️ **No active file processing job.**")
        raise StopPropagation
    await _request_cancel(client, int(message.from_user.id), job)
    try: await message.delete()
    except Exception: pass
    raise StopPropagation

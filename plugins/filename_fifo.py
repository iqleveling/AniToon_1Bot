from __future__ import annotations

from pyrogram import Client, StopPropagation, filters

from helper.job_state import jobs
from helper.utils import AniToonTransferCancelled, clear_transfer_cancel
from plugins import action_pipeline_v2 as pipeline
from plugins.rename import _base_without_extension, _extension, _safe_filename


async def _next_waiting(user_id: int):
    for job in await jobs.get_user_jobs(user_id):
        if job.selected_action and not job.extra.get("processing"):
            return job
    return None


@Client.on_message(filters.private & filters.text, group=-1600)
async def fifo_filename_input(client, message):
    # Commands must always remain commands. Previously this handler saw /start
    # while a queued rename was waiting and incorrectly treated it as the
    # requested filename, which made /start appear to do nothing.
    text_value = (message.text or "").strip()
    if text_value.startswith("/"):
        return

    job = await _next_waiting(message.from_user.id)
    if not job:
        return

    text = _safe_filename(text_value)
    if not text:
        await message.reply_text("❌ Please send a valid filename.")
        raise StopPropagation

    await jobs.update(job.job_id, extra={**job.extra, "processing": True, "input_message_id": message.id})
    status = await message.reply_text("⏳ **Queued. Waiting for previous file...**")
    await jobs.update(job.job_id, extra={**job.extra, "status_message_id": status.id})

    lock = None
    try:
        if hasattr(jobs, "acquire_user"):
            lock = await jobs.acquire_user(message.from_user.id)

        if job.selected_action == "convert_name":
            ext = (job.output_ext or "").lower()
            if not ext:
                raise RuntimeError("Conversion format expired")
            name = f"{_base_without_extension(text)}.{ext}"
            kind = "video" if ext == "mp4" else "audio" if ext in pipeline.AUDIO else "document"
            await pipeline._run(client, job, status, name, kind, True)
        elif job.extra.get("rename_output_mode") == "video":
            name = f"{_base_without_extension(text)}.mp4"
            await pipeline._run(client, job, status, name, "video", True)
        else:
            ext = _extension(job.original_name)
            name = f"{_base_without_extension(text)}.{ext}" if ext else text
            await pipeline._run(client, job, status, name, "document", False)

        await pipeline._finish_cleanup(client, job)
    except AniToonTransferCancelled:
        try:
            await status.edit_text("❌ **Processing cancelled.**")
        except Exception:
            pass
        clear_transfer_cancel(job.job_id)
        await jobs.remove(job.job_id)
    except Exception as exc:
        try:
            await status.edit_text(f"❌ **Processing failed**\n\n`{str(exc)[:1200]}`")
        except Exception:
            pass
        clear_transfer_cancel(job.job_id)
        await jobs.remove(job.job_id)
    finally:
        if lock is not None:
            try:
                lock.release()
            except RuntimeError:
                pass

    raise StopPropagation

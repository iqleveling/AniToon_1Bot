from __future__ import annotations

import asyncio
import os
import shutil
import struct
import time

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from helper.cancel_manager import register_task, unregister_task
from helper.job_state import Job, jobs
from helper.message_cleanup import protect_transfer_message
from helper.utils import AniToonTransferCancelled, humanbytes, progress_for_pyrogram, reset_progress, request_transfer_resume, set_transfer_runtime


def cancel_markup(job_id: str):
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]])


async def _show_processing(status: Message | None):
    if status is not None:
        await protect_transfer_message(status)


async def _delete_rename_source(client: Client, job: Job) -> None:
    if getattr(job, "selected_action", None) not in {"rename_output_choice", "rename_format", "custom_name", "convert_name"}:
        return
    message_id = getattr(job, "source_message_id", None)
    if not message_id:
        return
    try:
        await client.delete_messages(job.user_id, int(message_id))
    except Exception:
        pass


def _needs_faststart(path: str) -> bool:
    """Return True when MP4 has mdat before moov and therefore needs fast-start remux."""
    if not path.lower().endswith(".mp4"):
        return False
    try:
        with open(path, "rb") as stream:
            offset = 0
            saw_mdat = False
            file_size = os.path.getsize(path)
            for _ in range(256):
                stream.seek(offset)
                header = stream.read(8)
                if len(header) < 8:
                    return False
                size, atom = struct.unpack(">I4s", header)
                header_size = 8
                if size == 1:
                    extended = stream.read(8)
                    if len(extended) < 8:
                        return False
                    size = struct.unpack(">Q", extended)[0]
                    header_size = 16
                elif size == 0:
                    return False
                if size < header_size or offset + size > file_size:
                    return False
                atom = atom.decode("latin1")
                if atom == "mdat":
                    saw_mdat = True
                elif atom == "moov":
                    return saw_mdat
                offset += size
                if offset >= file_size:
                    return False
    except (OSError, ValueError, struct.error):
        return False
    return False


async def download_job(client: Client, message: Message, job: Job, status: Message) -> int:
    if os.path.isfile(job.input_path) and os.path.getsize(job.input_path) > 0:
        actual = os.path.getsize(job.input_path)
        await jobs.update(job.job_id, extra={**job.extra, "downloaded_size": actual})
        await _delete_rename_source(client, job)
        await protect_transfer_message(status)
        return actual

    expected_size = int(job.extra.get("telegram_file_size", 0) or 0)
    source = job.extra.get("source_message") or job.extra.get("file_id") or message
    os.makedirs(job.work_dir, exist_ok=True)

    media = getattr(source, "video", None) or getattr(source, "document", None)
    duration = getattr(media, "duration", None) if media is not None else None
    if duration:
        set_transfer_runtime(job.job_id, duration)

    request_transfer_resume(job.job_id)
    task = await register_task(job.job_id)
    acquired = False
    try:
        from helper.utils import is_transfer_cancelled
        if is_transfer_cancelled(job.job_id):
            raise AniToonTransferCancelled("Transfer cancelled by user")
        await jobs.acquire()
        acquired = True
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
        if is_transfer_cancelled(job.job_id):
            raise AniToonTransferCancelled("Transfer cancelled by user")
        path = result if isinstance(result, str) and os.path.isfile(result) else job.input_path
        if path != job.input_path and os.path.isfile(path):
            os.replace(path, job.input_path)
        if not os.path.isfile(job.input_path):
            raise RuntimeError("Telegram download completed but the local file was not found")
        actual = os.path.getsize(job.input_path)
        if expected_size and actual != expected_size:
            raise RuntimeError(f"Incomplete download: expected {humanbytes(expected_size)}, got {humanbytes(actual)}")
        await jobs.update(job.job_id, extra={**job.extra, "downloaded_size": actual})
        await progress_for_pyrogram(actual, expected_size or actual, "Downloading", status, started, job.job_id)
        await _delete_rename_source(client, job)
        await protect_transfer_message(status)
        return actual
    except AniToonTransferCancelled:
        try:
            await status.edit_text("❌ **Processing cancelled.**")
        except Exception:
            pass
        raise
    except asyncio.CancelledError:
        await jobs.remove(job.job_id)
        shutil.rmtree(job.work_dir, ignore_errors=True)
        raise
    except FloodWait:
        raise
    finally:
        await unregister_task(job.job_id, task)
        if acquired:
            jobs.release()


async def upload_job(client: Client, job: Job, path: str, filename: str, status: Message | None = None, *, as_video: bool = False, prepared_video: bool = False):
    """Upload a file. When as_video=True, send a real streamable Telegram video."""
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise RuntimeError("Upload source is missing or empty")
    acquired = False
    task = await register_task(job.job_id)
    upload_path = path
    temporary_streamable = None
    try:
        await jobs.acquire()
        acquired = True
        reset_progress(job.job_id)
        started = time.time()

        # prepare_video_for_telegram() already guarantees fast-start MP4 output.
        # Skip a second atom scan/remux for outputs prepared by _send_video().
        if as_video and not prepared_video and _needs_faststart(path):
            from helper.ffmpeg import make_streamable
            temporary_streamable = os.path.join(job.work_dir, f".streamable_{job.job_id}.mp4")
            prepared = await make_streamable(path, temporary_streamable)
            if prepared and os.path.isfile(prepared):
                upload_path = prepared

        size = os.path.getsize(upload_path)
        kwargs = {
            "progress": progress_for_pyrogram,
            "progress_args": ("Uploading", status, started, job.job_id),
        }
        if as_video:
            from helper.ffmpeg import get_video_info
            duration, width, height = await get_video_info(upload_path)
            if duration <= 0 or width <= 0 or height <= 0:
                raise RuntimeError("Video metadata could not be read before upload")
            set_transfer_runtime(job.job_id, duration)
            kwargs.update({
                "caption": f"✅ **AniToon Processed**\n\n📂 `{filename}`\n📦 `{humanbytes(size)}`\n⏱ `{int(duration // 60):02d}:{int(duration % 60):02d}`",
                "duration": max(1, int(round(duration))),
                "width": int(width),
                "height": int(height),
                "supports_streaming": True,
            })
            thumb = None
            try:
                from helper.database import db
                thumb = await db.get_thumbnail(job.user_id)
            except Exception:
                thumb = None
            if thumb:
                kwargs["thumb"] = thumb
            try:
                # send_video creates Telegram's native video message. With
                # supports_streaming=True + fast-start MP4, Telegram clients
                # can begin playback while the recipient is downloading it.
                return await client.send_video(job.user_id, upload_path, **kwargs)
            except Exception as exc:
                if thumb and "thumb" in str(exc).lower():
                    kwargs.pop("thumb", None)
                    return await client.send_video(job.user_id, upload_path, **kwargs)
                raise RuntimeError(f"Telegram video upload failed: {exc}") from exc

        kwargs["caption"] = f"✅ **AniToon Processed**\n\n📂 `{filename}`\n📦 `{humanbytes(size)}`"
        ext = os.path.splitext(filename)[1].lower()
        mime = (job.mime_type or "").lower()
        if mime.startswith("audio/") or ext in {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wav", ".opus"}:
            return await client.send_audio(job.user_id, upload_path, **kwargs)
        return await client.send_document(job.user_id, upload_path, **kwargs)
    finally:
        if temporary_streamable and temporary_streamable != path:
            try:
                os.remove(temporary_streamable)
            except OSError:
                pass
        await unregister_task(job.job_id, task)
        if acquired:
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

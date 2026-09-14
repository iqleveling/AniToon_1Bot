import math
import time
import os
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import Config


class AniToonTransferCancelled(Exception):
    """Raised by the progress callback when the user cancels a transfer."""


_CANCELLED_TRANSFERS = set()
_LAST_PROGRESS_UPDATE = {}


def request_transfer_cancel(job_id: str):
    if job_id:
        _CANCELLED_TRANSFERS.add(str(job_id))


def clear_transfer_cancel(job_id: str):
    if job_id:
        key = str(job_id)
        _CANCELLED_TRANSFERS.discard(key)
        _LAST_PROGRESS_UPDATE.pop(key, None)


def is_transfer_cancelled(job_id: str) -> bool:
    return bool(job_id and str(job_id) in _CANCELLED_TRANSFERS)


# --- HUMAN READABLE DATA ---
def humanbytes(size):
    """Convert raw bytes to a compact human-readable value."""
    if not size:
        return "0 B"
    size = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.2f} {unit}"


def time_formatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds:
        parts.append(f"{seconds}s")
    if milliseconds and not parts:
        parts.append(f"{milliseconds}ms")
    return " ".join(parts) or "0s"


def _progress_bar(percentage: float) -> str:
    completed_str = getattr(Config, "COMPLETED_STR", "█") or "█"
    remaining_str = getattr(Config, "REMAINING_STR", "░") or "░"
    completed = max(0, min(20, int(percentage / 5)))
    return completed_str * completed + remaining_str * (20 - completed)


def _progress_text(current, total, ud_type, start):
    current = max(0, int(current or 0))
    total = max(0, int(total or 0))
    elapsed = max(0.001, time.time() - start)
    speed = current / elapsed
    percentage = (current * 100 / total) if total else 0.0

    if speed > 0 and total >= current:
        eta = max(0, int((total - current) / speed))
        eta_text = time_formatter(eta * 1000)
    else:
        eta_text = "calculating..."

    title = "Uploading..." if "upload" in str(ud_type).lower() else "Downloading..."
    return (
        f"{title}\n"
        f"Size: {humanbytes(current)} | {humanbytes(total)}\n"
        f"Done: {percentage:.2f}%\n"
        f"Speed: {humanbytes(speed)}/s\n"
        f"ETA: {eta_text}"
    )


async def progress_for_pyrogram(
    current,
    total,
    ud_type,
    message,
    start,
    job_id=None,
):
    """Update one transfer message at a low frequency and watch for cancellation."""
    if job_id and is_transfer_cancelled(job_id):
        raise AniToonTransferCancelled("Transfer cancelled by user")

    if message is None:
        return

    key = str(job_id) if job_id else str(id(message))
    now = time.time()
    interval = getattr(Config, "PROGRESS_UPDATE_INTERVAL", 1.5)
    last = _LAST_PROGRESS_UPDATE.get(key, 0.0)

    # Keep Telegram edits low while still giving the user useful progress.
    if current < total and now - last < interval:
        return

    try:
        await message.edit_text(_progress_text(current, total, ud_type, start))
        _LAST_PROGRESS_UPDATE[key] = now
    except Exception:
        # A progress update must never interrupt the transfer itself.
        pass

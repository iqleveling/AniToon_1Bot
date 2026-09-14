import math
import time
import os
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import Config


class AniToonTransferCancelled(Exception):
    """Raised by the progress callback when the user cancels a transfer."""


_CANCELLED_TRANSFERS = set()


def request_transfer_cancel(job_id: str):
    if job_id:
        _CANCELLED_TRANSFERS.add(str(job_id))


def clear_transfer_cancel(job_id: str):
    if job_id:
        _CANCELLED_TRANSFERS.discard(str(job_id))


def is_transfer_cancelled(job_id: str) -> bool:
    return bool(job_id and str(job_id) in _CANCELLED_TRANSFERS)


# --- HUMAN READABLE DATA ---
def humanbytes(size):
    """Convert raw bytes to a compact human-readable value."""
    if not size:
        return "0 B"
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


async def progress_for_pyrogram(
    current,
    total,
    ud_type,
    message,
    start,
    job_id=None,
):
    """Very light progress callback: no progress bar/message spam; only cancel detection."""
    if job_id and is_transfer_cancelled(job_id):
        raise AniToonTransferCancelled("Transfer cancelled by user")
    return

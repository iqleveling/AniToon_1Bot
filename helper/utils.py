import time

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


def reset_progress(job_id: str):
    """Allow the next transfer stage to update immediately."""
    if job_id:
        _LAST_PROGRESS_UPDATE.pop(str(job_id), None)


def is_transfer_cancelled(job_id: str) -> bool:
    return bool(job_id and str(job_id) in _CANCELLED_TRANSFERS)


def humanbytes(size):
    """Convert raw bytes to a compact human-readable value."""
    if not size:
        return "0 B"
    size = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
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
    """Render a readable 24-cell progress bar without the old zero-percent UI."""
    completed = max(0, min(24, int((percentage / 100.0) * 24)))
    return "█" * completed + "░" * (24 - completed)


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

    title = "📥 Downloading..." if "upload" not in str(ud_type).lower() else "📤 Uploading..."
    return (
        f"{title}\n"
        f"{_progress_bar(percentage)} {percentage:.2f}%\n\n"
        f"📦 Size: {humanbytes(current)} / {humanbytes(total)}\n"
        f"✅ Completed: {percentage:.2f}%\n"
        f"🚀 Speed: {humanbytes(speed)}/s\n"
        f"⏱ ETA: {eta_text}"
    )


def _cancel_markup(job_id):
    if not job_id:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]]
    )


async def progress_for_pyrogram(
    current,
    total,
    ud_type,
    message,
    start,
    job_id=None,
):
    """Update one status message with full numeric transfer details."""
    if job_id and is_transfer_cancelled(job_id):
        raise AniToonTransferCancelled("Transfer cancelled by user")

    if message is None:
        return

    key = str(job_id) if job_id else str(id(message))
    now = time.time()
    interval = getattr(Config, "PROGRESS_UPDATE_INTERVAL", 1.5)
    last = _LAST_PROGRESS_UPDATE.get(key, 0.0)

    if current < total and now - last < interval:
        return

    try:
        await message.edit_text(
            _progress_text(current, total, ud_type, start),
            reply_markup=_cancel_markup(job_id),
        )
        _LAST_PROGRESS_UPDATE[key] = now
    except Exception:
        pass

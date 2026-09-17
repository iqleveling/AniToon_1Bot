import asyncio
import time

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config


class AniToonTransferCancelled(Exception):
    """Raised by the progress callback when the user cancels a transfer."""


_CANCELLED_TRANSFERS = set()
_LAST_PROGRESS_UPDATE = {}
_PAUSE_EVENTS = {}
_TRANSFER_RUNTIME = {}


def request_transfer_cancel(job_id: str):
    if job_id:
        _CANCELLED_TRANSFERS.add(str(job_id))
        event = _PAUSE_EVENTS.get(str(job_id))
        if event is not None:
            event.set()


def clear_transfer_cancel(job_id: str):
    if job_id:
        key = str(job_id)
        _CANCELLED_TRANSFERS.discard(key)
        _LAST_PROGRESS_UPDATE.pop(key, None)
        _TRANSFER_RUNTIME.pop(key, None)
        event = _PAUSE_EVENTS.pop(key, None)
        if event is not None:
            event.set()


def reset_progress(job_id: str):
    if job_id:
        _LAST_PROGRESS_UPDATE.pop(str(job_id), None)


def set_transfer_runtime(job_id: str, seconds: float | int | None):
    if not job_id:
        return
    try:
        value = int(round(float(seconds or 0)))
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        _TRANSFER_RUNTIME[str(job_id)] = value


def is_transfer_cancelled(job_id: str) -> bool:
    return bool(job_id and str(job_id) in _CANCELLED_TRANSFERS)


def _pause_event(job_id: str) -> asyncio.Event:
    key = str(job_id)
    event = _PAUSE_EVENTS.get(key)
    if event is None:
        event = asyncio.Event()
        event.set()
        _PAUSE_EVENTS[key] = event
    return event


def request_transfer_pause(job_id: str):
    if job_id:
        _pause_event(job_id).clear()


def request_transfer_resume(job_id: str):
    if job_id:
        _pause_event(job_id).set()


def is_transfer_paused(job_id: str) -> bool:
    return bool(job_id and not _pause_event(job_id).is_set())


def humanbytes(size):
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
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    if seconds: parts.append(f"{seconds}s")
    if milliseconds and not parts: parts.append(f"{milliseconds}ms")
    return " ".join(parts) or "0s"


def _progress_bar(percentage: float) -> str:
    completed = max(0, min(24, int((percentage / 100.0) * 24)))
    return "█" * completed + "░" * (24 - completed)


def _progress_text(current, total, ud_type, start, job_id=None):
    current = max(0, int(current or 0))
    total = max(0, int(total or 0))
    elapsed = max(0.001, time.time() - start)
    speed = current / elapsed
    percentage = (current * 100 / total) if total else 0.0
    eta_text = "calculating..."
    if speed > 0 and total >= current:
        eta_text = time_formatter(max(0, int((total - current) / speed)) * 1000)
    title = "📤 Upload Progress" if "upload" in str(ud_type).lower() else "📥 Download Progress"
    runtime = _TRANSFER_RUNTIME.get(str(job_id)) if job_id else None
    runtime_line = f"🎬 Runtime: {time_formatter(runtime * 1000)}\n" if runtime else ""
    return f"{title}\n{_progress_bar(percentage)} {percentage:.2f}%\n\n📦 Size: {humanbytes(current)} / {humanbytes(total)}\n{runtime_line}🚀 Speed: {humanbytes(speed)}/s\n⏱ ETA: {eta_text}"


def _transfer_markup(job_id, ud_type):
    if not job_id:
        return None
    if "upload" in str(ud_type).lower():
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]])
    paused = is_transfer_paused(job_id)
    action = "resume" if paused else "pause"
    label = "▶️ Resume" if paused else "⏸️ Pause"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"transfer:{action}:{job_id}"), InlineKeyboardButton("❌ Cancel", callback_data=f"transfer:cancel:{job_id}")]])


async def progress_for_pyrogram(current, total, ud_type, message, start, job_id=None):
    if job_id and is_transfer_cancelled(job_id):
        raise AniToonTransferCancelled("Transfer cancelled by user")
    if job_id and "upload" not in str(ud_type).lower():
        await _pause_event(job_id).wait()
        if is_transfer_cancelled(job_id):
            raise AniToonTransferCancelled("Transfer cancelled by user")
    if message is None:
        return
    key = str(job_id) if job_id else str(id(message))
    now = time.time()
    interval = max(1.0, float(getattr(Config, "PROGRESS_UPDATE_INTERVAL", 1.5)))
    last = _LAST_PROGRESS_UPDATE.get(key)
    is_final = bool(total and current >= total)
    if last is not None and not is_final and now - last < interval:
        return
    try:
        await message.edit_text(_progress_text(current, total, ud_type, start, job_id), reply_markup=_transfer_markup(job_id, ud_type))
        _LAST_PROGRESS_UPDATE[key] = now
    except Exception:
        pass

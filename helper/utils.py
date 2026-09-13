import math
import time
import os
from config import Config


# --- HUMAN READABLE DATA ---
def humanbytes(size):
    """Convert raw bytes into a compact human-readable value."""
    if not size:
        return "0 B"

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            break
        size /= 1024.0

    return f"{size:.2f} {unit}"


def time_formatter(milliseconds: int) -> str:
    """Convert milliseconds into a compact readable duration."""
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
    """Render the 20-character progress bar used by AniToon."""
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
):
    """Update a clean download/upload progress message.

    The same layout is intentionally used for both stages so users see:
    Downloading -> Uploading without the old square-bracket progress style.
    """
    if not total:
        return

    now = time.time()
    diff = max(now - start, 0.001)

    # Update at most once per second, but always update at completion.
    if diff < 1 and current != total:
        return

    percentage = min(100.0, current * 100 / total)
    speed = current / diff
    remaining = max(total - current, 0)
    eta_seconds = remaining / speed if speed > 0 else 0

    bar = _progress_bar(percentage)
    stage = str(ud_type or "📥 Downloading")
    if not stage.startswith(("📥", "📤")):
        stage = f"📥 {stage}"

    text = (
        f"**{stage}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"[{bar}] {percentage:.0f}%\n\n"
        f"📦 **Size:** {humanbytes(current)} / {humanbytes(total)}\n"
        f"🚀 **Speed:** {humanbytes(speed)}/s\n"
        f"⏳ **ETA:** {time_formatter(eta_seconds * 1000)}\n"
        f"⏱️ **Elapsed:** {time_formatter(diff * 1000)}"
    )

    try:
        await message.edit_text(text)
    except Exception:
        pass

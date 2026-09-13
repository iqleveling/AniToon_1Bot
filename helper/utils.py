import math
import time
import os
from config import Config


# --- Choice 10-B: HUMAN READABLE DATA ---
def humanbytes(size):
    """
    Converts raw bytes into a human-readable format.
    """
    if not size:
        return "0 B"

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            break
        size /= 1024.0

    return f"{size:.2f} {unit}"


def time_formatter(milliseconds: int) -> str:
    """
    Converts milliseconds into a readable time format.
    """
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    tmp = (
        (str(days) + "d, " if days else "")
        + (str(hours) + "h, " if hours else "")
        + (str(minutes) + "m, " if minutes else "")
        + (str(seconds) + "s, " if seconds else "")
        + (str(milliseconds) + "ms, " if milliseconds else "")
    )

    return tmp[:-2] if tmp else "0 s"


# --- Choice 8-B: PROGRESS BAR ---
async def progress_for_pyrogram(
    current,
    total,
    ud_type,
    message,
    start
):
    """
    Updates the Telegram message with download/upload progress.
    """

    now = time.time()
    diff = now - start

    # Avoid unnecessary Telegram message edits.
    if diff < 1 or current == total:
        return

    percentage = current * 100 / total
    speed = current / diff
    elapsed_time = round(diff * 1000)

    if speed > 0:
        time_to_completion = round(
            (total - current) / speed
        ) * 1000
    else:
        time_to_completion = 0

    estimated_total_time = (
        elapsed_time + time_to_completion
    )

    elapsed_time_str = time_formatter(elapsed_time)
    estimated_total_time_str = time_formatter(
        estimated_total_time
    )

    completed = math.floor(percentage / 10)

    # Safe fallbacks prevent a missing Config attribute from aborting
    # Pyrogram's internal get_file/download operation.
    completed_str = getattr(Config, "COMPLETED_STR", "▰")
    remaining_str = getattr(Config, "REMAINING_STR", "▱")

    progress = (
        "["
        + completed_str * completed
        + remaining_str * (10 - completed)
        + "]\n"
        + f"**📊 Progress**: {percentage:.2f}%\n"
    )

    tmp = (
        progress
        + f"**{ud_type}**: "
        f"{humanbytes(current)} of "
        f"{humanbytes(total)}\n"
        + f"**🚀 Speed**: {humanbytes(speed)}/s\n"
        + f"**⏳ ETA**: "
        f"{estimated_total_time_str or '0 s'}\n"
        + f"**⏱️ Elapsed**: "
        f"{elapsed_time_str or '0 s'}"
    )

    try:
        await message.edit_text(
            f"**AniToon Promax Processing...**\n\n{tmp}"
        )
    except Exception:
        pass

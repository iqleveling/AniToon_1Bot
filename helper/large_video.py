from __future__ import annotations

import asyncio
import glob
import logging
import os
from pathlib import Path

from helper.ffmpeg import get_video_info, take_screenshot

log = logging.getLogger("AniToon.large_video")

MAX_PART_BYTES = int(os.getenv("TELEGRAM_MAX_PART_BYTES", str(1_900 * 1024 * 1024)))
TARGET_PART_BYTES = int(os.getenv("TELEGRAM_TARGET_PART_BYTES", str(1_750 * 1024 * 1024)))
MIN_SPLIT_BYTES = int(os.getenv("TELEGRAM_SPLIT_THRESHOLD", str(1_850 * 1024 * 1024)))


def is_large_video(path: str) -> bool:
    try:
        return os.path.getsize(path) > MIN_SPLIT_BYTES
    except OSError:
        return False


async def make_thumbnail(video_path: str, work_dir: str) -> str | None:
    thumb = os.path.join(work_dir, ".telegram_thumb.jpg")
    try:
        duration, _, _ = await get_video_info(video_path)
        result = await take_screenshot(video_path, thumb, duration)
        if not result or not os.path.isfile(result):
            return None
        if os.path.getsize(result) >= 200_000:
            os.remove(result)
            return None
        return result
    except Exception as exc:
        log.warning("Thumbnail generation failed: %s", exc)
        return None


async def split_video_for_telegram(video_path: str, work_dir: str, filename: str) -> list[str]:
    size = os.path.getsize(video_path)
    if size <= MIN_SPLIT_BYTES:
        return [video_path]

    duration, _, _ = await get_video_info(video_path)
    if duration <= 0:
        raise RuntimeError("Could not determine video duration for large-file splitting")

    ext = Path(filename).suffix.lower() or ".mp4"
    stem = Path(filename).stem
    pattern = os.path.join(work_dir, f".part_{stem}_%03d{ext}")
    ratio = min(0.90, TARGET_PART_BYTES / max(size, 1))
    segment_time = max(30.0, duration * ratio)

    for _ in range(5):
        for old in glob.glob(os.path.join(work_dir, f".part_{stem}_*{ext}")):
            try:
                os.remove(old)
            except OSError:
                pass

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-map", "0", "-c", "copy", "-f", "segment",
            "-segment_time", f"{segment_time:.3f}",
            "-reset_timestamps", "1", "-avoid_negative_ts", "make_zero", pattern,
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            log.error("Large video split failed: %s", stderr.decode(errors="ignore")[-4000:])
            raise RuntimeError("FFmpeg could not split the large video")

        parts = sorted(glob.glob(os.path.join(work_dir, f".part_{stem}_*{ext}")))
        parts = [p for p in parts if os.path.isfile(p) and os.path.getsize(p) > 0]
        if not parts:
            raise RuntimeError("FFmpeg created no video parts")

        too_large = [p for p in parts if os.path.getsize(p) > MAX_PART_BYTES]
        if not too_large:
            final_parts = []
            for index, part in enumerate(parts, 1):
                final_name = os.path.join(work_dir, f"{stem}.part{index:02d}{ext}")
                os.replace(part, final_name)
                final_parts.append(final_name)
            return final_parts

        worst = max(os.path.getsize(p) for p in too_large)
        segment_time *= max(0.25, min(0.85, MAX_PART_BYTES / worst * 0.92))

    raise RuntimeError("Could not create Telegram-safe video parts below the upload limit")

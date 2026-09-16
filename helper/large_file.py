from __future__ import annotations

import asyncio
import os
from pathlib import Path

from helper.large_video import MAX_PART_BYTES, MIN_SPLIT_BYTES


async def split_file_for_telegram(file_path: str, work_dir: str, filename: str) -> list[str]:
    """Split any non-video output into Telegram-safe binary parts."""
    size = os.path.getsize(file_path)
    if size <= MIN_SPLIT_BYTES:
        return [file_path]

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    part_size = MAX_PART_BYTES

    def _split() -> list[str]:
        parts: list[str] = []
        index = 1
        with open(file_path, "rb") as source:
            while True:
                data_path = os.path.join(work_dir, f"{stem}.part{index:02d}{suffix or '.part'}")
                written = 0
                try:
                    with open(data_path, "wb") as target:
                        while written < part_size:
                            chunk = source.read(min(16 * 1024 * 1024, part_size - written))
                            if not chunk:
                                break
                            target.write(chunk)
                            written += len(chunk)
                except Exception:
                    try:
                        os.remove(data_path)
                    except OSError:
                        pass
                    raise

                if written <= 0:
                    try:
                        os.remove(data_path)
                    except OSError:
                        pass
                    break

                if os.path.getsize(data_path) > MAX_PART_BYTES:
                    raise RuntimeError("Generated file part exceeds Telegram-safe size")
                parts.append(data_path)
                index += 1

                if written < part_size:
                    break

        if len(parts) < 2:
            return [file_path]
        return parts

    return await asyncio.to_thread(_split)

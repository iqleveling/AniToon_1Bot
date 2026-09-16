from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Awaitable, Callable

DEFAULT_METADATA_NAME = "AniToon Official"
ProgressCallback = Callable[[float, float], Awaitable[None]]


async def _run_ffmpeg(cmd: list[str], progress_callback: ProgressCallback | None = None, duration: float = 0.0) -> bool:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def read_progress():
        if process.stdout is None:
            return
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            if progress_callback and line.startswith(b"out_time_ms=") and duration > 0:
                try:
                    current = int(line.split(b"=", 1)[1]) / 1_000_000
                    await progress_callback(min(current, duration), duration)
                except Exception:
                    pass

    if process.stdout is not None:
        await asyncio.gather(read_progress(), process.stderr.read())
    else:
        await process.communicate()
    await process.wait()

    if process.returncode == 0:
        return True
    try:
        stderr = await process.stderr.read() if process.stderr else b""
    except Exception:
        stderr = b""
    logging.error("FFmpeg error: %s", stderr.decode(errors="ignore")[-4000:])
    return False


async def _probe(file_path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", file_path,
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    stdout, _ = await process.communicate()
    try:
        return json.loads(stdout.decode(errors="ignore"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


async def _duration(file_path: str) -> float:
    data = await _probe(file_path)
    try:
        return float(data.get("format", {}).get("duration", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


async def fix_metadata(input_file, output_file, audio_name=DEFAULT_METADATA_NAME, subtitle_name=DEFAULT_METADATA_NAME):
    audio_name = str(audio_name).strip() or DEFAULT_METADATA_NAME
    subtitle_name = str(subtitle_name).strip() or DEFAULT_METADATA_NAME
    cmd = [
        "ffmpeg", "-y", "-i", input_file, "-map", "0", "-c", "copy",
        "-metadata", f"title={audio_name}",
        "-metadata:s:a", f"title={audio_name}",
        "-metadata:s:s", f"title={subtitle_name}", output_file,
    ]
    return await _run_ffmpeg(cmd)


async def make_streamable(input_file, output_file):
    """Fast remux for an MP4; never re-encodes the media."""
    target = output_file
    replace_input = os.path.abspath(target) == os.path.abspath(input_file)
    if replace_input:
        target = os.path.join(os.path.dirname(input_file), ".streamable." + os.path.basename(input_file))

    cmd = [
        "ffmpeg", "-y", "-i", input_file,
        "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
        "-movflags", "+faststart", "-sn", target,
    ]
    ok = await _run_ffmpeg(cmd)
    if ok and os.path.isfile(target):
        if replace_input:
            os.replace(target, input_file)
            return input_file
        return target
    return None


async def get_video_info(file_path):
    data = await _probe(file_path)
    try:
        duration = float(data.get("format", {}).get("duration", 0) or 0)
    except (TypeError, ValueError):
        duration = 0.0
    width = height = 0
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            try:
                width = int(stream.get("width", 0) or 0)
                height = int(stream.get("height", 0) or 0)
            except (TypeError, ValueError):
                pass
            break
    return duration, width, height


async def take_screenshot(video_file, output_file, duration):
    seek_time = max(float(duration) * 0.1, 0)
    cmd = [
        "ffmpeg", "-y", "-ss", str(seek_time), "-i", video_file,
        "-frames:v", "1", "-q:v", "2", output_file,
    ]
    ok = await _run_ffmpeg(cmd)
    return output_file if ok and os.path.exists(output_file) else None


async def inspect_media_streams(file_path):
    data = await _probe(file_path)
    result = []
    for stream in data.get("streams", []):
        kind = stream.get("codec_type")
        if kind not in {"audio", "subtitle"}:
            continue
        tags = stream.get("tags") or {}
        result.append({
            "index": int(stream.get("index", -1)),
            "type": kind,
            "codec": stream.get("codec_name") or "unknown",
            "language": tags.get("language") or "und",
            "title": tags.get("title") or "",
        })
    return result


async def remux_with_track_names(input_file, output_file, track_titles: dict[int, str], global_title: str | None = None):
    cmd = ["ffmpeg", "-y", "-i", input_file, "-map", "0", "-c", "copy"]
    if global_title:
        cmd += ["-metadata", f"title={global_title}"]
    for stream_index, title in track_titles.items():
        clean = str(title).strip()
        if not clean:
            continue
        prefix, idx = (stream_index.split(":", 1) + ["0"])[:2]
        prefix = {"audio": "a", "subtitle": "s"}.get(prefix, prefix)
        cmd += [f"-metadata:s:{prefix}:{idx}", f"title={clean}"]
    cmd.append(output_file)
    return await _run_ffmpeg(cmd)


async def _video_codecs(file_path: str) -> tuple[str, str | None]:
    data = await _probe(file_path)
    video_codec = ""
    audio_codec = None
    for stream in data.get("streams", []):
        kind = stream.get("codec_type")
        if kind == "video" and not video_codec:
            video_codec = str(stream.get("codec_name") or "").lower()
        elif kind == "audio" and audio_codec is None:
            audio_codec = str(stream.get("codec_name") or "").lower()
    return video_codec, audio_codec


async def prepare_video_for_telegram(input_file: str, output_file: str, progress_callback: ProgressCallback | None = None) -> str | None:
    """Prepare the fastest Telegram-video-safe MP4.

    Fast path: H.264 video + AAC audio is copied directly into MP4, so there is
    no video encoding. Only the container is rewritten. If the audio alone is
    incompatible, the video is still copied and only audio is encoded. Full
    H.264 encoding is used only when the source video codec itself is not safe.
    """
    if not os.path.isfile(input_file) or os.path.getsize(input_file) <= 0:
        return None

    duration = await _duration(input_file)
    video_codec, audio_codec = await _video_codecs(input_file)
    ext = os.path.splitext(input_file)[1].lower()

    if ext == ".mp4" and video_codec == "h264" and audio_codec in {None, "", "aac"}:
        if os.path.abspath(input_file) != os.path.abspath(output_file):
            try:
                os.link(input_file, output_file)
            except OSError:
                try:
                    import shutil
                    shutil.copy2(input_file, output_file)
                except Exception:
                    return None
        if progress_callback and duration > 0:
            await progress_callback(duration, duration)
        return output_file

    if video_codec == "h264" and audio_codec in {None, "", "aac"}:
        cmd = [
            "ffmpeg", "-y", "-i", input_file,
            "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
            "-movflags", "+faststart", "-sn", output_file,
        ]
        if await _run_ffmpeg(cmd, progress_callback, duration) and os.path.isfile(output_file):
            return output_file

    if video_codec == "h264":
        # Preserve the video bitstream and encode only incompatible audio.
        cmd = [
            "ffmpeg", "-y", "-i", input_file,
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", "-sn", output_file,
        ]
        if await _run_ffmpeg(cmd, progress_callback, duration) and os.path.isfile(output_file):
            return output_file

    # Last resort: actual video encoding. This is intentionally the only path
    # that re-encodes video, because it is the expensive operation the bot was
    # previously doing for every MKV -> Video rename.
    cmd = [
        "ffmpeg", "-y", "-i", input_file,
        "-map", "0:v:0?", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-pix_fmt", "yuv420p", "-sn",
        "-progress", "pipe:1", "-nostats", output_file,
    ]
    if await _run_ffmpeg(cmd, progress_callback, duration) and os.path.isfile(output_file):
        return output_file
    return None


async def convert_media(input_file, output_file, output_format: str, progress_callback=None):
    """Convert media, using stream copy whenever the requested format allows it."""
    output_format = output_format.lower().lstrip(".")
    video_formats = {"mp4", "mkv", "webm", "mov"}
    audio_formats = {"mp3", "m4a", "aac", "flac", "ogg"}
    if output_format not in video_formats | audio_formats:
        raise ValueError("Unsupported output format")

    if output_format == "mp4":
        prepared = await prepare_video_for_telegram(input_file, output_file, progress_callback)
        return bool(prepared)

    duration = await _duration(input_file)
    if output_format in {"mkv", "mov"}:
        cmd = [
            "ffmpeg", "-y", "-i", input_file,
            "-map", "0", "-c", "copy", "-progress", "pipe:1", "-nostats", output_file,
        ]
    elif output_format == "webm":
        cmd = [
            "ffmpeg", "-y", "-i", input_file,
            "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "4",
            "-c:a", "libopus", "-progress", "pipe:1", "-nostats", output_file,
        ]
    elif output_format == "mp3":
        cmd = ["ffmpeg", "-y", "-i", input_file, "-vn", "-c:a", "libmp3lame", "-q:a", "2", "-progress", "pipe:1", "-nostats", output_file]
    elif output_format == "m4a":
        cmd = ["ffmpeg", "-y", "-i", input_file, "-vn", "-c:a", "aac", "-b:a", "192k", "-progress", "pipe:1", "-nostats", output_file]
    elif output_format == "aac":
        cmd = ["ffmpeg", "-y", "-i", input_file, "-vn", "-c:a", "aac", "-b:a", "192k", "-progress", "pipe:1", "-nostats", output_file]
    else:
        cmd = ["ffmpeg", "-y", "-i", input_file, "-vn", "-c:a", "flac", "-progress", "pipe:1", "-nostats", output_file]

    return await _run_ffmpeg(cmd, progress_callback, duration)

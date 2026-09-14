import os
import asyncio
import logging
import json

DEFAULT_METADATA_NAME = "AniToon Official"


async def fix_metadata(input_file, output_file, audio_name=DEFAULT_METADATA_NAME, subtitle_name=DEFAULT_METADATA_NAME):
    audio_name = str(audio_name).strip() or DEFAULT_METADATA_NAME
    subtitle_name = str(subtitle_name).strip() or DEFAULT_METADATA_NAME
    cmd = ["ffmpeg", "-y", "-i", input_file, "-map", "0", "-c", "copy", "-metadata", f"title={audio_name}", "-metadata:s:a", f"title={audio_name}", "-metadata:s:s", f"title={subtitle_name}", output_file]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await process.communicate()
    if process.returncode == 0:
        return True
    logging.error("FFmpeg Metadata Error: %s", stderr.decode(errors="ignore"))
    return False


async def make_streamable(input_file, output_file):
    """Remux a valid MP4 with faststart."""
    target = output_file
    replace_input = os.path.abspath(target) == os.path.abspath(input_file)
    if replace_input:
        target = os.path.join(os.path.dirname(input_file), ".streamable." + os.path.basename(input_file))

    cmd = ["ffmpeg", "-y", "-i", input_file, "-map", "0", "-c", "copy", "-movflags", "+faststart", target]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await process.communicate()
    if process.returncode == 0 and os.path.isfile(target):
        if replace_input:
            os.replace(target, input_file)
            return input_file
        return target
    logging.error("FFmpeg Streamable Error: %s", stderr.decode(errors="ignore"))
    return None


async def get_video_info(file_path):
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", file_path]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, _ = await process.communicate()
    try:
        data = json.loads(stdout.decode(errors="ignore"))
        duration = float(data.get("format", {}).get("duration", 0))
        width = height = 0
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = int(stream.get("width", 0) or 0)
                height = int(stream.get("height", 0) or 0)
                break
        return duration, width, height
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0, 0, 0


async def take_screenshot(video_file, output_file, duration):
    seek_time = max(float(duration) * 0.1, 0)
    cmd = ["ffmpeg", "-y", "-ss", str(seek_time), "-i", video_file, "-frames:v", "1", "-q:v", "2", output_file]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await process.communicate()
    if process.returncode != 0:
        logging.error("Screenshot Error: %s", stderr.decode(errors="ignore"))
        return None
    return output_file if os.path.exists(output_file) else None


async def inspect_media_streams(file_path):
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", file_path]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, _ = await process.communicate()
    try:
        data = json.loads(stdout.decode(errors="ignore"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    result = []
    for stream in data.get("streams", []):
        kind = stream.get("codec_type")
        if kind not in {"audio", "subtitle"}:
            continue
        tags = stream.get("tags") or {}
        result.append({"index": int(stream.get("index", -1)), "type": kind, "codec": stream.get("codec_name") or "unknown", "language": tags.get("language") or "und", "title": tags.get("title") or ""})
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
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await process.communicate()
    if process.returncode == 0:
        return True
    logging.error("FFmpeg track rename error: %s", stderr.decode(errors="ignore"))
    return False


async def convert_media(input_file, output_file, output_format: str, progress_callback=None):
    """Convert media and optionally report FFmpeg progress."""
    output_format = output_format.lower().lstrip(".")
    video_formats = {"mp4", "mkv", "webm", "mov"}
    audio_formats = {"mp3", "m4a", "aac", "flac", "ogg"}
    if output_format not in video_formats | audio_formats:
        raise ValueError("Unsupported output format")

    if output_format == "mp4":
        cmd = ["ffmpeg", "-y", "-i", input_file, "-map", "0:v:0?", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-movflags", "+faststart", "-pix_fmt", "yuv420p", "-progress", "pipe:1", "-nostats", output_file]
    else:
        cmd = ["ffmpeg", "-y", "-i", input_file]
        if output_format == "webm":
            cmd += ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "4", "-c:a", "libopus"]
        elif output_format in {"mkv", "mov"}:
            cmd += ["-c", "copy"]
        elif output_format == "mp3":
            cmd += ["-vn", "-c:a", "libmp3lame", "-q:a", "2"]
        elif output_format == "m4a":
            cmd += ["-vn", "-c:a", "aac", "-b:a", "192k"]
        elif output_format == "aac":
            cmd += ["-vn", "-c:a", "aac", "-b:a", "192k"]
        elif output_format == "flac":
            cmd += ["-vn", "-c:a", "flac"]
        else:
            cmd += ["-vn", "-c:a", "libopus"]
        cmd += ["-progress", "pipe:1", "-nostats", output_file]

    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    duration = 0.0
    try:
        probe = await asyncio.create_subprocess_exec("ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_file, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        raw, _ = await probe.communicate()
        duration = float(raw.decode().strip() or 0)
    except Exception:
        duration = 0.0

    async def read_progress():
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            if progress_callback and line.startswith(b"out_time_ms="):
                try:
                    current = int(line.split(b"=", 1)[1]) / 1_000_000
                    await progress_callback(current, duration)
                except Exception:
                    pass

    await asyncio.gather(read_progress(), process.stderr.read())
    await process.wait()
    if process.returncode == 0 and os.path.isfile(output_file):
        return True
    logging.error("FFmpeg conversion failed with return code %s", process.returncode)
    return False

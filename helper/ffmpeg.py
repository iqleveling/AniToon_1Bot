import os
import asyncio
import logging
import json


DEFAULT_METADATA_NAME = "AniToon Official"


async def fix_metadata(
    input_file,
    output_file,
    audio_name=DEFAULT_METADATA_NAME,
    subtitle_name=DEFAULT_METADATA_NAME,
):
    """
    Rewrite media metadata without re-encoding.

    Audio and subtitle names are passed per-user so the global
    Config object is not required for this feature.
    """

    audio_name = (
        str(audio_name).strip()
        or DEFAULT_METADATA_NAME
    )

    subtitle_name = (
        str(subtitle_name).strip()
        or DEFAULT_METADATA_NAME
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_file,
        "-map",
        "0",
        "-c",
        "copy",
        "-metadata",
        f"title={audio_name}",
        "-metadata:s:a",
        f"title={audio_name}",
        "-metadata:s:s",
        f"title={subtitle_name}",
        output_file,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await process.communicate()

    if process.returncode == 0:
        return True

    logging.error(
        "FFmpeg Metadata Error: %s",
        stderr.decode(errors="ignore"),
    )
    return False


async def make_streamable(input_file, output_file):
    """
    Moves MP4/MOV metadata to the beginning of the file.
    """

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_file,
        "-c",
        "copy",
        "-movflags",
        "faststart",
        output_file,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await process.communicate()

    if process.returncode == 0:
        return output_file

    logging.error(
        "FFmpeg Streamable Error: %s",
        stderr.decode(errors="ignore"),
    )

    return input_file


async def get_video_info(file_path):
    """
    Returns:
        duration, width, height
    """

    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        file_path,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, _ = await process.communicate()

    try:
        data = json.loads(
            stdout.decode(errors="ignore")
        )

        duration = float(
            data.get("format", {}).get("duration", 0)
        )

        width = 0
        height = 0

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = int(stream.get("width", 0))
                height = int(stream.get("height", 0))
                break

        return duration, width, height

    except (
        json.JSONDecodeError,
        ValueError,
        TypeError,
    ) as e:
        logging.error(
            "Video Probe Error: %s",
            e,
        )
        return 0, 0, 0


async def take_screenshot(
    video_file,
    output_file,
    duration,
):
    """
    Generate a preview frame at 10% of the video's duration.
    """

    seek_time = max(float(duration) * 0.1, 0)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(seek_time),
        "-i",
        video_file,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        output_file,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await process.communicate()

    if process.returncode != 0:
        logging.error(
            "Screenshot Error: %s",
            stderr.decode(errors="ignore"),
        )
        return None

    return (
        output_file
        if os.path.exists(output_file)
        else None
    )


async def inspect_media_streams(file_path):
    """Return audio/subtitle streams with their indexes and current titles."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", file_path,
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
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
        result.append({
            "index": int(stream.get("index", -1)),
            "type": kind,
            "codec": stream.get("codec_name") or "unknown",
            "language": tags.get("language") or "und",
            "title": tags.get("title") or "",
        })
    return result


async def remux_with_track_names(
    input_file,
    output_file,
    track_titles: dict[int, str],
    global_title: str | None = None,
):
    """Remux without re-encoding and rename selected stream titles."""
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

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode == 0:
        return True
    logging.error("FFmpeg track rename error: %s", stderr.decode(errors="ignore"))
    return False


async def convert_media(input_file, output_file, output_format: str):
    """Convert common media formats using sensible stream mapping."""
    output_format = output_format.lower().lstrip(".")
    video_formats = {"mp4", "mkv", "webm", "mov"}
    audio_formats = {"mp3", "m4a", "aac", "flac", "ogg"}
    if output_format not in video_formats | audio_formats:
        raise ValueError("Unsupported output format")

    cmd = ["ffmpeg", "-y", "-i", input_file]
    if output_format in video_formats:
        if output_format == "mp4":
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac"]
        elif output_format == "webm":
            cmd += ["-c:v", "libvpx-vp9", "-c:a", "libopus"]
        else:
            cmd += ["-c", "copy"]
    else:
        if output_format == "mp3":
            cmd += ["-vn", "-c:a", "libmp3lame", "-q:a", "2"]
        elif output_format == "m4a":
            cmd += ["-vn", "-c:a", "aac", "-b:a", "192k"]
        elif output_format == "aac":
            cmd += ["-vn", "-c:a", "aac", "-b:a", "192k"]
        elif output_format == "flac":
            cmd += ["-vn", "-c:a", "flac"]
        else:
            cmd += ["-vn", "-c:a", "libopus"]
    cmd.append(output_file)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode == 0:
        return True
    logging.error("FFmpeg conversion error: %s", stderr.decode(errors="ignore"))
    return False

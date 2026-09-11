import os
import asyncio
import logging
import json

from config import Config


# --- Choice 3-B: INTERNAL METADATA BRANDING ---
async def fix_metadata(input_file, output_file):
    """
    Rewrites the internal title of audio and subtitle streams
    without re-encoding the media.
    """

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
        f"title={Config.AUDIO_NAME}",
        "-metadata:s:a",
        f"title={Config.AUDIO_NAME}",
        "-metadata:s:s",
        f"title={Config.SUBTITLE_NAME}",
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


# --- Choice 5-A: STREAMABLE VIDEO ---
async def make_streamable(input_file, output_file):
    """
    Moves the MP4/MOV metadata index to the beginning of the file.
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


# --- PROMAX UTILITY: VIDEO PROBING ---
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

    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logging.error(
            "Video Probe Error: %s",
            e,
        )
        return 0, 0, 0


# --- THUMBNAIL / SCREENSHOT ---
async def take_screenshot(
    video_file,
    output_file,
    duration,
):
    """
    Generates a preview frame at 10% of the video's duration.
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

    return output_file if os.path.exists(output_file) else None

from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
import uuid

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from helper.database import db
from helper.ffmpeg import (
    convert_media,
    fix_metadata,
    get_video_info,
    inspect_media_streams,
    remux_with_track_names,
    take_screenshot,
)
from helper.job_state import Job, jobs
from helper.plans import get_plan
from helper.splitter import split_file
from helper.utils import humanbytes, progress_for_pyrogram
from plugins.ui import advanced_menu, auto_preview_menu, convert_menu, edit_callback_message, file_action_menu


SUPPORTED_VIDEO = {"mp4", "mkv", "webm", "mov", "avi", "flv", "ts", "m4v"}
SUPPORTED_AUDIO = {"mp3", "m4a", "aac", "flac", "ogg", "wav", "opus"}
SUPPORTED_EXTENSIONS = SUPPORTED_VIDEO | SUPPORTED_AUDIO


def _safe_filename(value: str, fallback: str = "output") -> str:
    value = value.strip().replace("/", "_").replace("\\", "_")
    value = re.sub(r"[\x00-\x1f\x7f]", "", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value[:240] or fallback


def _extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower().lstrip(".")


def _base_without_extension(filename: str) -> str:
    return os.path.splitext(filename)[0]


def _detect_name(filename: str) -> tuple[str, list[str]]:
    """Conservative but useful anime-style filename normalizer."""
    base = _base_without_extension(filename)
    detected: list[str] = []
    text = re.sub(r"[._]+", " ", base)
    text = re.sub(r"\s+", " ", text).strip()

    season = re.search(r"\bS(\d{1,2})\b", text, re.I)
    episode = re.search(r"\b(?:E|EP|Episode)\s*([0-9]{1,4})\b", text, re.I)
    resolution = re.search(r"\b(2160p|1440p|1080p|720p|576p|480p)\b", text, re.I)
    audio = re.search(r"\b(Dual Audio|Multi Audio|Dub(?:bed)?|Sub(?:bed)?)\b", text, re.I)
    codec = re.search(r"\b(x264|x265|H\.264|H\.265|HEVC|AV1)\b", text, re.I)

    for label, match in (("Season", season), ("Episode", episode), ("Resolution", resolution), ("Audio", audio), ("Codec", codec)):
        if match:
            value = match.group(0)
            detected.append(f"{label}: {value}")

    cleaned = re.sub(r"\[(.*?)\]", " ", text)
    cleaned = re.sub(r"\((.*?)\)", " ", cleaned)
    cleaned = re.sub(r"\b(?:S\d{1,2}|E(?:P|pisode)?\s*\d{1,4}|2160p|1440p|1080p|720p|576p|480p|x264|x265|H\.264|H\.265|HEVC|AV1)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_ .")

    if not cleaned:
        cleaned = base
    return _safe_filename(cleaned, "AniToon_Output"), detected


def _media_from_message(message: Message):
    return message.document or message.video or message.audio


async def _user_context(user_id: int, bot_id: int):
    await db.add_user(user_id)
    user = await db.get_user_data(user_id) or {}
    if user.get("is_banned"):
        return None, "❌ **You are banned from using this bot.**"
    sub = await db.get_subscription(user_id, bot_id)
    plan = get_plan(sub.get("plan", "free"))
    used = await db.get_usage(user_id, bot_id)
    return (user, plan, used), None


async def _download_job(client: Client, message: Message):
    user_id = message.from_user.id
    bot_id = int(getattr(client, "bot_id", 0))
    context, error = await _user_context(user_id, bot_id)
    if error:
        await message.reply_text(error)
        return
    user_data, plan, used = context

    if used >= plan.daily_limit:
        await message.reply_text(
            "🚫 **Daily Limit Reached!**\n\n"
            f"Current Plan: {plan.name}\n"
            f"Daily Limit: `{humanbytes(plan.daily_limit)}`\n"
            f"Used: `{humanbytes(used)}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Upgrade", callback_data="upgrade")]]),
        )
        return

    media = _media_from_message(message)
    if not media:
        return
    original_name = _safe_filename(getattr(media, "file_name", None) or f"file_{message.id}")
    extension = _extension(original_name)
    mime_type = getattr(media, "mime_type", None) or ""

    job_id = uuid.uuid4().hex[:12]
    work_dir = os.path.join("downloads", str(user_id), job_id)
    os.makedirs(work_dir, exist_ok=True)
    input_path = os.path.join(work_dir, original_name)
    job = Job(
        job_id=job_id,
        user_id=user_id,
        bot_id=bot_id,
        source_message_id=message.id,
        work_dir=work_dir,
        input_path=input_path,
        original_name=original_name,
        mime_type=mime_type,
        extra={"extension": extension, "user_data": user_data, "used_before": used},
    )
    if not await jobs.register(job):
        return await message.reply_text("⏳ **You already have an active file job.** Please finish or cancel it first.")

    status = await message.reply_text("⏳ **AniToon: Waiting for a processing slot...**")
    await jobs.acquire()
    try:
        position = await jobs.position(job_id)
        if position > 1:
            await status.edit_text(f"📥 **Queued**\n\nPosition: `{position}`\n\nStarting download as soon as a slot is available...")
        else:
            await status.edit_text("📥 **AniToon: Starting download...**")

        await client.download_media(
            message=message,
            file_name=input_path,
            progress=progress_for_pyrogram,
            progress_args=("📥 Downloading", status, time.time()),
        )
        file_size = os.path.getsize(input_path)
        await jobs.update(job_id, extra={**job.extra, "downloaded_size": file_size})

        if used + file_size > plan.daily_limit:
            await status.edit_text(
                "🚫 **This file exceeds your remaining daily quota.**\n\n"
                f"Plan: {plan.name}\n"
                f"Remaining: `{humanbytes(max(plan.daily_limit - used, 0))}`\n"
                f"File: `{humanbytes(file_size)}`"
            )
            return

        auto_name, detected = _detect_name(original_name)
        await jobs.update(job_id, detected_name=f"{auto_name}.{extension}" if extension else auto_name, extra={**job.extra, "detected": detected, "downloaded_size": file_size})

        await status.edit_text(
            "✅ **Download Completed!**\n\n"
            f"📂 Original: `{original_name}`\n"
            f"📦 Size: `{humanbytes(file_size)}`\n\n"
            "Choose what you want to do:",
            reply_markup=file_action_menu(job_id),
        )
    except FloodWait as e:
        await status.edit_text(f"⏳ **Telegram FloodWait**\n\nWaiting `{e.value}` seconds...")
        await asyncio.sleep(e.value)
    except Exception as exc:
        await status.edit_text(f"❌ **Download failed**\n\n`{str(exc)[:1000]}`")
    finally:
        jobs.release()
        # Keep downloaded job until action completes/cancelled.


@Client.on_message(
    filters.private & (filters.document | filters.video | filters.audio)
)
async def auto_detect(client, message):
    try:
        await _download_job(client, message)
    except Exception:
        try:
            await message.reply_text("❌ **Unable to start this file job.**")
        except Exception:
            pass


async def _ask_name(client, user_id: int, prompt: str, job_id: str, state: str):
    await jobs.update(job_id, selected_action=state)
    return await client.send_message(
        user_id,
        prompt,
        reply_markup=ForceReply(selective=True),
    )


async def _output_caption(user_id: int, filename: str, size: int, duration: float):
    saved = await db.get_caption(user_id)
    if saved:
        return (
            saved.replace("{filename}", filename)
            .replace("{filesize}", humanbytes(size))
            .replace("{duration}", str(int(duration)))
        )
    return f"✅ **AniToon Processed**\n\n📂 `{filename}`\n📦 `{humanbytes(size)}`"


async def _send_output(client, message: Message, job: Job, path: str, filename: str, status, duration=0, width=0, height=0, thumb=None):
    mime = job.mime_type or ""
    size = os.path.getsize(path)
    caption = await _output_caption(job.user_id, filename, size, duration)
    if mime.startswith("video/") or _extension(filename) in SUPPORTED_VIDEO:
        sent = await client.send_video(
            job.user_id, path, caption=caption, thumb=thumb,
            duration=int(duration) if duration else None,
            width=width or None, height=height or None,
            supports_streaming=True,
            progress=progress_for_pyrogram,
            progress_args=("📤 Uploading", status, time.time()),
        )
    elif mime.startswith("audio/") or _extension(filename) in SUPPORTED_AUDIO:
        sent = await client.send_audio(
            job.user_id, path, caption=caption, thumb=thumb,
            progress=progress_for_pyrogram,
            progress_args=("📤 Uploading", status, time.time()),
        )
    else:
        sent = await client.send_document(
            job.user_id, path, caption=caption, thumb=thumb,
            progress=progress_for_pyrogram,
            progress_args=("📤 Uploading", status, time.time()),
        )
    if Config.LOG_CHANNEL:
        try:
            await sent.copy(Config.LOG_CHANNEL)
            user = getattr(message, "from_user", None)
            display_name = " ".join(x for x in [getattr(user, "first_name", ""), getattr(user, "last_name", "")] if x).strip() or "Unknown"
            await client.send_message(
                Config.LOG_CHANNEL,
                "📦 **Processed File Log**\n\n"
                f"👤 **User:** `{display_name}`\n"
                f"🆔 **ID:** `{job.user_id}`\n"
                f"📂 **Filename:** `{filename}`",
            )
        except Exception:
            pass
    return sent


async def _finish_job(client, message: Message, job: Job, output_path: str, output_name: str):
    status = await message.reply_text("📦 **Preparing output...**")
    try:
        input_size = os.path.getsize(job.input_path)
        # Count original input once per job.
        used = int(job.extra.get("used_before", 0))
        plan = get_plan((await db.get_subscription(job.user_id, job.bot_id)).get("plan", "free"))
        if used + input_size > plan.daily_limit:
            return await status.edit_text("🚫 **Daily quota exceeded for this job.**")

        duration = width = height = 0
        if (job.mime_type or "").startswith("video/"):
            duration, width, height = await get_video_info(output_path)
        thumb = await db.get_thumbnail(job.user_id)
        if not thumb and duration:
            thumb = await take_screenshot(output_path, os.path.join(job.work_dir, "thumb.jpg"), duration)

        parts = [output_path]
        final_size = os.path.getsize(output_path)
        if final_size > 2_000_000_000:
            await status.edit_text("✂️ **Large file detected. Splitting into parts...**")
            parts = await split_file(output_path, 2_000_000_000)

        for index, part in enumerate(parts, 1):
            name = os.path.basename(part)
            if len(parts) > 1:
                stem, ext = os.path.splitext(output_name)
                name = f"{stem}.part{index:03d}{ext or ''}"
            await _send_output(client, message, job, part, name, status, duration if index == 1 else 0, width if index == 1 else 0, height if index == 1 else 0, thumb if index == 1 else None)

        await db.update_usage(job.user_id, job.bot_id, input_size)
        await status.edit_text(
            "✅ **Processing Complete!**\n\n"
            f"📂 `{output_name}`\n"
            f"📦 `{humanbytes(final_size)}`\n"
            f"🧩 Parts: `{len(parts)}`"
        )
    except FloodWait as exc:
        await status.edit_text(f"⏳ **FloodWait**\nWaiting `{exc.value}` seconds...")
        await asyncio.sleep(exc.value)
    except Exception as exc:
        await status.edit_text(f"❌ **Processing failed**\n\n`{str(exc)[:1000]}`")
    finally:
        try:
            shutil.rmtree(job.work_dir, ignore_errors=True)
        finally:
            await jobs.remove(job.job_id)


async def _start_custom_rename(client, cb, job: Job):
    await cb.answer()
    ext = _extension(job.original_name)
    await _ask_name(
        client,
        job.user_id,
        "✏️ **Custom Rename**\n\nEnter the filename **without or with an extension**.\n"
        f"Available extension: `.{ext}`",
        job.job_id,
        "custom_name",
    )


async def _start_advanced(client, cb, job: Job):
    await cb.answer()
    await jobs.update(job.job_id, selected_action="advanced_menu")
    await edit_callback_message(cb, "🛠 **Advanced Rename**\n\nChoose what you want to rename:", advanced_menu(job.job_id))


async def _start_convert(client, cb, job: Job):
    await cb.answer()
    await jobs.update(job.job_id, selected_action="convert_menu")
    await edit_callback_message(cb, "🔄 **Convert File**\n\nChoose the output format:", convert_menu(job.job_id))


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"))
async def cb_job_rename(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        return await cb.answer("Job expired. Send the file again.", show_alert=True)
    await _start_custom_rename(client, cb, job)


@Client.on_callback_query(filters.regex(r"^job:auto:([0-9a-f]+)$"))
async def cb_job_auto(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        return await cb.answer("Job expired. Send the file again.", show_alert=True)
    await cb.answer()
    detected = job.detected_name or job.original_name
    info = job.extra.get("detected", [])
    detected_text = "\n".join(f"• {x}" for x in info) or "• No special tags detected"
    await jobs.update(job.job_id, selected_action="auto_preview")
    await edit_callback_message(cb, f"🤖 **Auto Rename Preview**\n\nOld:\n`{job.original_name}`\n\nNew:\n`{detected}`\n\n🔎 **Detected:**\n{detected_text}", auto_preview_menu(job.job_id))


@Client.on_callback_query(filters.regex(r"^job:confirmauto:([0-9a-f]+)$"))
async def cb_job_confirm_auto(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        return await cb.answer("Job expired. Send the file again.", show_alert=True)
    await cb.answer("Starting...")
    output_name = job.detected_name or job.original_name
    output_path = os.path.join(job.work_dir, _safe_filename(output_name))
    try:
        if output_path != job.input_path:
            shutil.copy2(job.input_path, output_path)
        await _finish_job(client, cb.message, job, output_path, _safe_filename(output_name))
    except Exception as exc:
        await cb.message.reply_text(f"❌ `{str(exc)[:1000]}`")


@Client.on_callback_query(filters.regex(r"^job:convert:([0-9a-f]+)$"))
async def cb_job_convert(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        return await cb.answer("Job expired. Send the file again.", show_alert=True)
    await _start_convert(client, cb, job)


@Client.on_callback_query(filters.regex(r"^job:advanced:([0-9a-f]+)$"))
async def cb_job_advanced(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        return await cb.answer("Job expired. Send the file again.", show_alert=True)
    await _start_advanced(client, cb, job)


@Client.on_callback_query(filters.regex(r"^job:back:([0-9a-f]+)$"))
async def cb_job_back(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        return await cb.answer("Job expired. Send the file again.", show_alert=True)
    await cb.answer()
    await jobs.update(job.job_id, selected_action=None)
    await edit_callback_message(cb, "✅ **File is ready. Choose an action:**", file_action_menu(job.job_id))


@Client.on_callback_query(filters.regex(r"^job:cancel:([0-9a-f]+)$"))
async def cb_job_cancel(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        return await cb.answer("Job already removed.")
    await cb.answer("Cancelled", show_alert=True)
    shutil.rmtree(job.work_dir, ignore_errors=True)
    await jobs.remove(job.job_id)
    await edit_callback_message(cb, "❌ **File job cancelled and temporary files removed.**", None)


@Client.on_callback_query(filters.regex(r"^job:format:([0-9a-f]+):(mp4|mkv|webm|mov|mp3|m4a)$"))
async def cb_job_format(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        return await cb.answer("Job expired. Send the file again.", show_alert=True)
    fmt = cb.matches[0].group(2)
    await cb.answer()
    await jobs.update(job.job_id, output_ext=fmt, selected_action="convert_name")
    await _ask_name(
        client,
        job.user_id,
        f"🔄 **Convert to {fmt.upper()}**\n\nEnter the output name.\nThe `.{fmt}` extension will be used.",
        job.job_id,
        "convert_name",
    )


@Client.on_callback_query(filters.regex(r"^job:advancedfile:([0-9a-f]+)$"))
async def cb_job_advancedfile(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        return await cb.answer("Job expired. Send the file again.", show_alert=True)
    await cb.answer()
    await _ask_name(client, job.user_id, "🛠 **Advanced Rename**\n\nEnter the new file name.", job.job_id, "advanced_file")


async def _track_prompt(client, job: Job, kind: str):
    streams = await inspect_media_streams(job.input_path)
    selected = [s for s in streams if s["type"] == kind]
    if not selected:
        return await client.send_message(job.user_id, f"❌ No {kind} tracks were found in this file.", reply_markup=file_action_menu(job.job_id))
    await jobs.update(job.job_id, extra={**job.extra, "track_candidates": selected, "track_kind": kind})
    lines = [f"{i + 1}. {s['title'] or '[no title]'} ({s['language']})" for i, s in enumerate(selected)]
    return await client.send_message(
        job.user_id,
        f"🛠 **Rename {kind.title()} Track**\n\n" + "\n".join(lines) + "\n\nReply as `number | new name`. Example: `1 | Japanese Audio`",
        reply_markup=ForceReply(selective=True),
    )


@Client.on_callback_query(filters.regex(r"^job:finishadvanced:([0-9a-f]+)$"))
async def cb_job_finish_advanced(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job:
        return await cb.answer("Job expired. Send the file again.", show_alert=True)
    await cb.answer("Processing...")
    output_name = job.extra.get("advanced_output") or job.original_name
    output_path = os.path.join(job.work_dir, _safe_filename(output_name))
    try:
        current_input = job.input_path
        track_titles = job.extra.get("track_titles", {})
        if track_titles:
            renamed_path = os.path.join(job.work_dir, "advanced_tracks." + (_extension(output_name) or _extension(job.original_name) or "mkv"))
            ok = await remux_with_track_names(current_input, renamed_path, track_titles)
            if not ok:
                raise RuntimeError("Could not apply track names")
            current_input = renamed_path
        if os.path.abspath(current_input) != os.path.abspath(output_path):
            shutil.copy2(current_input, output_path)
        await _finish_job(client, cb.message, job, output_path, _safe_filename(output_name))
    except Exception as exc:
        await cb.message.reply_text(f"❌ **Advanced processing failed**\n\n`{str(exc)[:1000]}`")


@Client.on_callback_query(filters.regex(r"^job:(audio|subtitle):([0-9a-f]+)$"))
async def cb_job_tracks(client, cb):
    job = await jobs.get(cb.matches[0].group(2))
    if not job:
        return await cb.answer("Job expired. Send the file again.", show_alert=True)
    await cb.answer()
    await jobs.update(job.job_id, selected_action="track_rename")
    await _track_prompt(client, job, "audio" if cb.matches[0].group(1) == "audio" else "subtitle")


@Client.on_message(filters.private & filters.reply & filters.text)
async def process_rename(client, message):
    reply = message.reply_to_message
    if not reply or not isinstance(reply.reply_markup, ForceReply):
        return
    job = await jobs.get_user_job(message.from_user.id)
    if not job:
        return
    text = message.text.strip()
    action = job.selected_action
    if not action:
        return

    if action in {"custom_name", "advanced_file", "convert_name"}:
        if action == "convert_name":
            ext = job.output_ext
            name = _safe_filename(text)
            if "." not in name or _extension(name) != ext:
                name = f"{_base_without_extension(name)}.{ext}"
            output_path = os.path.join(job.work_dir, name)
            status = await message.reply_text(f"🔄 **Converting to {ext.upper()}...**")
            try:
                ok = await convert_media(job.input_path, output_path, ext)
                if not ok:
                    raise RuntimeError("FFmpeg conversion failed")
                await _finish_job(client, message, job, output_path, name)
            except Exception as exc:
                await status.edit_text(f"❌ **Conversion failed**\n\n`{str(exc)[:1000]}`")
            return

        ext = _extension(job.original_name)
        name = _safe_filename(text)
        if "." not in name:
            name = f"{name}.{ext}" if ext else name
        else:
            if action == "advanced_file" and ext:
                name = f"{_base_without_extension(name)}.{ext}"
        output_path = os.path.join(job.work_dir, name)
        try:
            shutil.copy2(job.input_path, output_path)
            if action == "custom_name":
                await _finish_job(client, message, job, output_path, name)
                return
            await jobs.update(job.job_id, extra={**job.extra, "advanced_output": name})
            await message.reply_text(
                "✅ **File name saved.**\n\n"
                f"📂 `{name}`\n\n"
                "You can now change audio or subtitle track names from the Advanced menu."
            )
            await jobs.update(job.job_id, selected_action="advanced_menu")
            await message.reply_text("🛠 **Advanced Rename**", reply_markup=advanced_menu(job.job_id))
        except Exception as exc:
            await message.reply_text(f"❌ `{str(exc)[:1000]}`")
        return

    if action == "track_rename":
        try:
            number_text, new_title = [x.strip() for x in text.split("|", 1)]
            number = int(number_text)
            candidates = job.extra.get("track_candidates", [])
            if number < 1 or number > len(candidates):
                raise ValueError("Invalid track number")
            stream = candidates[number - 1]
            base = job.extra.get("advanced_output") or job.input_path
            # If the output is not ready yet, create it from the input.
            output_name = job.extra.get("advanced_output") or job.original_name
            output_path = os.path.join(job.work_dir, _safe_filename(output_name))
            if base != output_path:
                shutil.copy2(job.input_path, output_path)
            track_titles = dict(job.extra.get("track_titles", {}))
            stream_type_index = sum(1 for s in candidates[:number] if s["type"] == stream["type"]) - 1
            key = f"{stream['type']}:{stream_type_index}"
            track_titles[key] = new_title
            job.extra["track_titles"] = track_titles
            await message.reply_text(f"✅ Updated `{key}` to `{new_title}`")
            await message.reply_text("🛠 **Advanced Rename**", reply_markup=advanced_menu(job.job_id))
        except Exception as exc:
            await message.reply_text(f"❌ Use this format: `1 | Track Name`\n\n`{str(exc)[:500]}`")
        return


@Client.on_message(filters.private & filters.command("advanced"))
async def advanced_command(client, message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job:
        return await message.reply_text("❌ Send a file first.")
    await message.reply_text("🛠 **Advanced Rename**", reply_markup=advanced_menu(job.job_id))

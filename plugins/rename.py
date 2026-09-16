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
from helper.cancel_manager import register_task, unregister_task
from helper.database import db
from helper.ffmpeg import convert_media, fix_metadata, get_video_info, inspect_media_streams, remux_with_track_names, take_screenshot
from helper.job_state import Job, jobs
from helper.job_transfer import download_job
from helper.metadata import get_metadata
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
            detected.append(f"{label}: {match.group(0)}")
    cleaned = re.sub(r"\[(.*?)\]", " ", text)
    cleaned = re.sub(r"\((.*?)\)", " ", cleaned)
    cleaned = re.sub(r"\b(?:S\d{1,2}|E(?:P|pisode)?\s*\d{1,4}|2160p|1440p|1080p|720p|576p|480p|x264|x265|H\.264|H\.265|HEVC|AV1)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_ .")
    return _safe_filename(cleaned or base, "AniToon_Output"), detected


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
    media = _media_from_message(message)
    if not media:
        return
    expected_size = int(getattr(media, "file_size", 0) or 0)
    if used + expected_size > plan.daily_limit:
        await message.reply_text("🚫 **This file exceeds your remaining daily quota.**\n\n" f"Plan: {plan.name}\nRemaining: `{humanbytes(max(plan.daily_limit - used, 0))}`\nFile: `{humanbytes(expected_size)}`")
        return
    original_name = _safe_filename(getattr(media, "file_name", None) or f"file_{message.id}")
    extension = _extension(original_name)
    mime_type = getattr(media, "mime_type", None) or ""
    job_id = uuid.uuid4().hex[:12]
    work_dir = os.path.join("downloads", str(user_id), job_id)
    os.makedirs(work_dir, exist_ok=True)
    input_path = os.path.join(work_dir, original_name)
    job = Job(job_id=job_id, user_id=user_id, bot_id=bot_id, source_message_id=message.id, work_dir=work_dir, input_path=input_path, original_name=original_name, mime_type=mime_type, extra={"extension": extension, "user_data": user_data, "used_before": used, "source_message": message, "telegram_file_size": expected_size})
    if not await jobs.register(job):
        return await message.reply_text("⏳ **You already have an active file job.** Please finish or cancel it first.")
    status = await message.reply_text("⏳ **AniToon: Waiting for a processing slot...**")
    try:
        await download_job(client, message, job, status)
        file_size = os.path.getsize(input_path)
        auto_name, detected = _detect_name(original_name)
        await jobs.update(job_id, detected_name=f"{auto_name}.{extension}" if extension else auto_name, extra={**job.extra, "detected": detected, "downloaded_size": file_size})
        await status.edit_text("✅ **Download Completed!**\n\n" f"📂 Original: `{original_name}`\n" f"📦 Size: `{humanbytes(file_size)}`\n\nChoose what you want to do:", reply_markup=file_action_menu(job_id))
    except FloodWait as exc:
        await status.edit_text(f"⏳ **Telegram FloodWait**\n\nWaiting `{exc.value}` seconds...")
        await asyncio.sleep(exc.value)
    except Exception as exc:
        await status.edit_text(f"❌ **Download failed**\n\n`{str(exc)[:1000]}`")
        shutil.rmtree(work_dir, ignore_errors=True)
        await jobs.remove(job_id)


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
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
    return await client.send_message(user_id, prompt, reply_markup=ForceReply(selective=True))


async def _apply_metadata_settings(job: Job, output_path: str) -> None:
    if not os.path.isfile(output_path):
        return
    if _extension(output_path) not in SUPPORTED_VIDEO and not str(job.mime_type or "").startswith("video/"):
        return
    temp = None
    try:
        streams = await inspect_media_streams(output_path)
        if not any(item["type"] in {"audio", "subtitle"} for item in streams):
            return
        settings = await get_metadata(job.user_id)
        temp = os.path.join(job.work_dir, ".metadata_applied." + os.path.basename(output_path))
        if await fix_metadata(output_path, temp, settings.audio_name, settings.subtitle_name) and os.path.isfile(temp) and os.path.getsize(temp) > 0:
            os.replace(temp, output_path)
        elif temp and os.path.exists(temp):
            os.remove(temp)
    except Exception:
        if temp and os.path.exists(temp):
            try: os.remove(temp)
            except OSError: pass


async def _output_caption(user_id: int, filename: str, size: int, duration: float):
    saved = await db.get_caption(user_id)
    if saved:
        return str(saved).replace("{filename}", filename).replace("{filesize}", humanbytes(size)).replace("{duration}", str(int(duration)))
    return f"✅ **AniToon Processed**\n\n📂 `{filename}`\n📦 `{humanbytes(size)}`"


async def _send_output(client, message: Message, job: Job, path: str, filename: str, status, duration=0, width=0, height=0, thumb=None):
    mime = job.mime_type or ""
    caption = await _output_caption(job.user_id, filename, os.path.getsize(path), duration)
    if mime == "video/mp4" or _extension(filename) == "mp4":
        sent = await client.send_video(job.user_id, path, caption=caption, thumb=thumb, duration=int(duration) if duration else None, width=width or None, height=height or None, supports_streaming=True, progress=progress_for_pyrogram, progress_args=("📤 Uploading", status, time.time(), job.job_id))
    elif mime.startswith("audio/") or _extension(filename) in SUPPORTED_AUDIO:
        sent = await client.send_audio(job.user_id, path, caption=caption, thumb=thumb, progress=progress_for_pyrogram, progress_args=("📤 Uploading", status, time.time(), job.job_id))
    else:
        sent = await client.send_document(job.user_id, path, caption=caption, thumb=thumb, progress=progress_for_pyrogram, progress_args=("📤 Uploading", status, time.time(), job.job_id))
    if Config.LOG_CHANNEL:
        try:
            await sent.copy(Config.LOG_CHANNEL)
        except Exception:
            pass
    return sent


async def _finish_job(client, message: Message, job: Job, output_path: str, output_name: str):
    task = await register_task(job.job_id)
    try:
        status = await message.reply_text("📦 **Preparing output...**")
        try:
            input_size = int(job.extra.get("downloaded_size", 0) or os.path.getsize(job.input_path))
            used = int(job.extra.get("used_before", 0))
            plan = get_plan((await db.get_subscription(job.user_id, job.bot_id)).get("plan", "free"))
            if used + input_size > plan.daily_limit:
                return await status.edit_text("🚫 **Daily quota exceeded for this job.**")
            await _apply_metadata_settings(job, output_path)
            duration = width = height = 0
            if (job.mime_type or "").startswith("video/") or _extension(output_name) == "mp4":
                duration, width, height = await get_video_info(output_path)
            thumb = await db.get_thumbnail(job.user_id)
            if not thumb and duration:
                thumb = await take_screenshot(output_path, os.path.join(job.work_dir, "thumb.jpg"), duration)
            parts = [output_path]
            if os.path.getsize(output_path) > 2_000_000_000:
                await status.edit_text("✂️ **Large file detected. Splitting into parts...**")
                parts = await split_file(output_path, 2_000_000_000)
            for index, part in enumerate(parts, 1):
                name = os.path.basename(part)
                if len(parts) > 1:
                    stem, ext = os.path.splitext(output_name)
                    name = f"{stem}.part{index:03d}{ext or ''}"
                await _send_output(client, message, job, part, name, status, duration if index == 1 else 0, width if index == 1 else 0, height if index == 1 else 0, thumb if index == 1 else None)
            if not job.extra.get("usage_charged"):
                await db.update_usage(job.user_id, job.bot_id, input_size)
                await jobs.update(job.job_id, extra={**job.extra, "usage_charged": True})
            await status.edit_text("✅ **Processing Complete!**\n\n" f"📂 `{output_name}`\n" f"📦 `{humanbytes(os.path.getsize(output_path))}`\n" f"🧩 Parts: `{len(parts)}`")
        except FloodWait as exc:
            await status.edit_text(f"⏳ **FloodWait**\nWaiting `{exc.value}` seconds...")
            await asyncio.sleep(exc.value)
        except Exception as exc:
            await status.edit_text(f"❌ **Processing failed**\n\n`{str(exc)[:1000]}`")
        finally:
            shutil.rmtree(job.work_dir, ignore_errors=True)
            await jobs.remove(job.job_id)
    finally:
        await unregister_task(job.job_id, task)


async def _start_custom_rename(client, cb, job: Job):
    await cb.answer()
    ext = _extension(job.original_name)
    await _ask_name(client, job.user_id, "✏️ **Custom Rename**\n\nEnter the filename **without or with an extension**.\n" f"Available extension: `.{ext}`", job.job_id, "custom_name")


async def _start_advanced(client, cb, job: Job):
    await cb.answer()
    await jobs.update(job.job_id, selected_action="advanced_menu")
    await edit_callback_message(cb, "🛠 **Advanced Rename**\n\nChoose what you want to rename:", advanced_menu(job.job_id))


async def _start_convert(client, cb, job: Job):
    await cb.answer()
    await jobs.update(job.job_id, selected_action="convert_menu")
    await edit_callback_message(cb, "🔄 **Convert File**\n\nChoose the output format:", convert_menu(job.job_id))


@Client.on_callback_query(filters.regex(r"^job:auto:([0-9a-f]+)$"))
async def cb_job_auto(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        return await cb.answer("Job expired or not owned by you.", show_alert=True)
    await cb.answer()
    detected = job.detected_name or job.original_name
    info = job.extra.get("detected", [])
    detected_text = "\n".join(f"• {x}" for x in info) or "• No special tags detected"
    await jobs.update(job.job_id, selected_action="auto_preview")
    await edit_callback_message(cb, f"🤖 **Auto Rename Preview**\n\nOld:\n`{job.original_name}`\n\nNew:\n`{detected}`\n\n🔎 **Detected:**\n{detected_text}", auto_preview_menu(job.job_id))


@Client.on_callback_query(filters.regex(r"^job:confirmauto:([0-9a-f]+)$"))
async def cb_job_confirm_auto(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        return await cb.answer("Job expired or not owned by you.", show_alert=True)
    await cb.answer("Starting download...")
    output_name = _safe_filename(job.detected_name or job.original_name)
    output_path = os.path.join(job.work_dir, output_name)
    try:
        status = await cb.message.reply_text("📥 **Downloading file for Auto Rename...**")
        source = job.extra.get("source_message") or await client.get_messages(job.user_id, job.source_message_id)
        if not source:
            raise RuntimeError("Original file message is no longer available.")
        await download_job(client, source, job, status)
        if os.path.abspath(output_path) != os.path.abspath(job.input_path):
            shutil.copy2(job.input_path, output_path)
        await _finish_job(client, cb.message, job, output_path, output_name)
    except Exception as exc:
        try: await cb.message.reply_text(f"❌ **Auto Rename failed**\n\n`{str(exc)[:1000]}`")
        except Exception: pass


@Client.on_callback_query(filters.regex(r"^job:rename:([0-9a-f]+)$"))
async def cb_job_rename(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        return await cb.answer("Job expired or not owned by you.", show_alert=True)
    await _start_custom_rename(client, cb, job)


@Client.on_callback_query(filters.regex(r"^job:convert:([0-9a-f]+)$"))
async def cb_job_convert(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        return await cb.answer("Job expired or not owned by you.", show_alert=True)
    await _start_convert(client, cb, job)


@Client.on_callback_query(filters.regex(r"^job:advanced:([0-9a-f]+)$"))
async def cb_job_advanced(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        return await cb.answer("Job expired or not owned by you.", show_alert=True)
    await _start_advanced(client, cb, job)


@Client.on_callback_query(filters.regex(r"^job:back:([0-9a-f]+)$"))
async def cb_job_back(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        return await cb.answer("Job expired or not owned by you.", show_alert=True)
    await cb.answer()
    await jobs.update(job.job_id, selected_action=None)
    await edit_callback_message(cb, "✅ **File is ready. Choose an action:**", file_action_menu(job.job_id))


@Client.on_callback_query(filters.regex(r"^job:cancel:([0-9a-f]+)$"))
async def cb_job_cancel(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        return await cb.answer("Job expired or not owned by you.", show_alert=True)
    await cb.answer("Cancelled", show_alert=True)
    shutil.rmtree(job.work_dir, ignore_errors=True)
    await jobs.remove(job.job_id)
    await edit_callback_message(cb, "❌ **File job cancelled and temporary files removed.**", None)


@Client.on_callback_query(filters.regex(r"^job:format:([0-9a-f]+):(mp4|mkv|webm|mov|mp3|m4a)$"))
async def cb_job_format(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        return await cb.answer("Job expired or not owned by you.", show_alert=True)
    fmt = cb.matches[0].group(2)
    await cb.answer()
    mime = {"mp4": "video/mp4", "mkv": "video/x-matroska", "webm": "video/webm", "mov": "video/quicktime", "mp3": "audio/mpeg", "m4a": "audio/mp4"}.get(fmt, "application/octet-stream")
    await jobs.update(job.job_id, output_ext=fmt, selected_action="convert_name", mime_type=mime)
    await _ask_name(client, job.user_id, f"🔄 **Convert to {fmt.upper()}**\n\nEnter the output name.\nThe `.{fmt}` extension will be used.", job.job_id, "convert_name")


async def _track_prompt(client, job: Job, kind: str):
    streams = await inspect_media_streams(job.input_path)
    selected = [s for s in streams if s["type"] == kind]
    if not selected:
        return await client.send_message(job.user_id, f"❌ No {kind} tracks were found in this file.", reply_markup=file_action_menu(job.job_id))
    await jobs.update(job.job_id, extra={**job.extra, "track_candidates": selected, "track_kind": kind})
    lines = [f"{i + 1}. {s['title'] or '[no title]'} ({s['language']})" for i, s in enumerate(selected)]
    return await client.send_message(job.user_id, f"🛠 **Rename {kind.title()} Track**\n\n" + "\n".join(lines) + "\n\nReply as `number | new name`. Example: `1 | Japanese Audio`", reply_markup=ForceReply(selective=True))


@Client.on_callback_query(filters.regex(r"^job:advancedfile:([0-9a-f]+)$"))
async def cb_job_advancedfile(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        return await cb.answer("Job expired or not owned by you.", show_alert=True)
    await cb.answer()
    await _ask_name(client, job.user_id, "🛠 **Advanced Rename**\n\nEnter the new file name.", job.job_id, "advanced_file")


@Client.on_callback_query(filters.regex(r"^job:finishadvanced:([0-9a-f]+)$"))
async def cb_job_finish_advanced(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        return await cb.answer("Job expired or not owned by you.", show_alert=True)
    await cb.answer("Processing...")
    output_name = job.extra.get("advanced_output") or job.original_name
    output_path = os.path.join(job.work_dir, _safe_filename(output_name))
    try:
        current_input = job.input_path
        track_titles = job.extra.get("track_titles", {})
        if track_titles:
            renamed_path = os.path.join(job.work_dir, "advanced_tracks." + (_extension(output_name) or _extension(job.original_name) or "mkv"))
            if not await remux_with_track_names(current_input, renamed_path, track_titles):
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
    if not job or job.user_id != cb.from_user.id:
        return await cb.answer("Job expired or not owned by you.", show_alert=True)
    await cb.answer()
    await jobs.update(job.job_id, selected_action="track_rename")
    await _track_prompt(client, job, "audio" if cb.matches[0].group(1) == "audio" else "subtitle")


@Client.on_message(filters.private & filters.reply & filters.text)
async def process_rename(client, message):
    reply = message.reply_to_message
    if not reply or not isinstance(reply.reply_markup, ForceReply):
        return
    job = await jobs.get_user_job(message.from_user.id)
    if not job or not job.selected_action:
        return
    text = message.text.strip()
    action = job.selected_action
    if action in {"custom_name", "advanced_file", "convert_name"}:
        if action == "convert_name":
            ext = job.output_ext
            name = _safe_filename(text)
            if _extension(name) != ext:
                name = f"{_base_without_extension(name)}.{ext}"
            output_path = os.path.join(job.work_dir, name)
            status = await message.reply_text(f"🔄 **Converting to {ext.upper()}...**")
            try:
                if not await convert_media(job.input_path, output_path, ext):
                    raise RuntimeError("FFmpeg conversion failed")
                await _finish_job(client, message, job, output_path, name)
            except Exception as exc:
                await status.edit_text(f"❌ **Conversion failed**\n\n`{str(exc)[:1000]}`")
            return
        ext = _extension(job.original_name)
        name = _safe_filename(text)
        if not _extension(name):
            name = f"{name}.{ext}" if ext else name
        elif action == "advanced_file" and ext:
            name = f"{_base_without_extension(name)}.{ext}"
        output_path = os.path.join(job.work_dir, name)
        try:
            shutil.copy2(job.input_path, output_path)
            if action == "custom_name":
                await _finish_job(client, message, job, output_path, name)
                return
            await jobs.update(job.job_id, extra={**job.extra, "advanced_output": name}, selected_action="advanced_menu")
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
            track_titles = dict(job.extra.get("track_titles", {}))
            stream_type_index = sum(1 for item in candidates[:number] if item["type"] == stream["type"]) - 1
            track_titles[f"{stream['type']}:{stream_type_index}"] = new_title
            await jobs.update(job.job_id, extra={**job.extra, "track_titles": track_titles})
            await message.reply_text(f"✅ Updated `{stream['type']}:{stream_type_index}` to `{new_title}`", reply_markup=advanced_menu(job.job_id))
        except Exception as exc:
            await message.reply_text(f"❌ Use this format: `1 | Track Name`\n\n`{str(exc)[:500]}`")


@Client.on_message(filters.private & filters.command("advanced"))
async def advanced_command(client, message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job:
        return await message.reply_text("❌ Send a file first.")
    await message.reply_text("🛠 **Advanced Rename**", reply_markup=advanced_menu(job.job_id))

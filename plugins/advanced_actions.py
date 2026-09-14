from __future__ import annotations

import os
import re
import shutil

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import ForceReply

from helper.ffmpeg import get_video_info, inspect_media_streams
from helper.job_state import jobs
from helper.job_transfer import cancel_markup
from plugins.ui import advanced_menu


def _safe(value: str) -> str:
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', (value or '').strip())
    return value[:220] or 'output'


async def _job(client, cb):
    job = await jobs.get(cb.matches[0].group(1))
    if not job or job.user_id != cb.from_user.id:
        await cb.answer('Job expired or not owned by you.', show_alert=True)
        return None
    return job


async def _run_ffmpeg(*args):
    import asyncio
    process = await asyncio.create_subprocess_exec('ffmpeg', '-y', *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode(errors='ignore')[-1800:] or 'FFmpeg failed')


async def _send_result(client, job, path, caption):
    ext = os.path.splitext(path)[1].lower()
    if ext in {'.mp3', '.m4a', '.aac', '.flac', '.ogg', '.wav', '.opus'}:
        return await client.send_audio(job.user_id, path, caption=caption)
    if ext in {'.mp4', '.mkv', '.webm', '.mov', '.avi'}:
        return await client.send_video(job.user_id, path, caption=caption, supports_streaming=True)
    return await client.send_document(job.user_id, path, caption=caption)


@Client.on_callback_query(filters.regex(r'^job:advinfo:([0-9a-f]+)$'), group=-4900)
async def media_info(client, cb):
    job = await _job(client, cb)
    if not job:
        raise StopPropagation
    await cb.answer()
    duration, width, height = await get_video_info(job.input_path)
    streams = await inspect_media_streams(job.input_path)
    lines = [
        'ℹ️ **Media Information**',
        '',
        f'📂 `{job.original_name}`',
        f'📦 `{os.path.getsize(job.input_path):,} bytes`',
        f'🎞 Video: `{width}×{height}`',
        f'⏱ Duration: `{duration:.2f} sec`',
        '',
        f'🎵 Audio tracks: `{sum(1 for x in streams if x["type"] == "audio")}`',
        f'💬 Subtitle tracks: `{sum(1 for x in streams if x["type"] == "subtitle")}`',
    ]
    await cb.message.edit_text('\n'.join(lines), reply_markup=advanced_menu(job.job_id))
    raise StopPropagation


@Client.on_callback_query(filters.regex(r'^job:extractaudio:([0-9a-f]+)$'), group=-4900)
async def extract_audio(client, cb):
    job = await _job(client, cb)
    if not job:
        raise StopPropagation
    await cb.answer('Extracting audio...')
    streams = await inspect_media_streams(job.input_path)
    audio = [x for x in streams if x['type'] == 'audio']
    if not audio:
        await cb.message.edit_text('❌ No audio tracks found.', reply_markup=advanced_menu(job.job_id))
        raise StopPropagation
    for n, stream in enumerate(audio, 1):
        out = os.path.join(job.work_dir, f'audio_{n}.m4a')
        await _run_ffmpeg('-i', job.input_path, '-map', f'0:{stream["index"]}', '-vn', '-c:a', 'copy', out)
        await _send_result(client, job, out, f'🎵 **Extracted Audio {n}**\n`{stream["title"] or stream["language"]}`')
    await cb.message.edit_text('✅ **All audio tracks extracted.**', reply_markup=advanced_menu(job.job_id))
    raise StopPropagation


@Client.on_callback_query(filters.regex(r'^job:extractsubtitle:([0-9a-f]+)$'), group=-4900)
async def extract_subtitles(client, cb):
    job = await _job(client, cb)
    if not job:
        raise StopPropagation
    await cb.answer('Extracting subtitles...')
    streams = await inspect_media_streams(job.input_path)
    subs = [x for x in streams if x['type'] == 'subtitle']
    if not subs:
        await cb.message.edit_text('❌ No subtitle tracks found.', reply_markup=advanced_menu(job.job_id))
        raise StopPropagation
    for n, stream in enumerate(subs, 1):
        out = os.path.join(job.work_dir, f'subtitle_{n}.srt')
        await _run_ffmpeg('-i', job.input_path, '-map', f'0:{stream["index"]}', '-c:s', 'srt', out)
        await client.send_document(job.user_id, out, caption=f'💬 **Extracted Subtitle {n}**\n`{stream["title"] or stream["language"]}`')
    await cb.message.edit_text('✅ **All subtitle tracks extracted.**', reply_markup=advanced_menu(job.job_id))
    raise StopPropagation


@Client.on_callback_query(filters.regex(r'^job:addaudio:([0-9a-f]+)$'), group=-4900)
async def ask_audio(client, cb):
    job = await _job(client, cb)
    if not job:
        raise StopPropagation
    await cb.answer()
    await jobs.update(job.job_id, selected_action='advanced_add_audio')
    await cb.message.edit_text('➕ **Add Audio**\n\nSend the audio file now.', reply_markup=cancel_markup(job.job_id))
    raise StopPropagation


@Client.on_callback_query(filters.regex(r'^job:addsubtitle:([0-9a-f]+)$'), group=-4900)
async def ask_subtitle(client, cb):
    job = await _job(client, cb)
    if not job:
        raise StopPropagation
    await cb.answer()
    await jobs.update(job.job_id, selected_action='advanced_add_subtitle')
    await cb.message.edit_text('➕ **Add Subtitle**\n\nSend the subtitle file now.', reply_markup=cancel_markup(job.job_id))
    raise StopPropagation


@Client.on_message(filters.private & (filters.document | filters.audio), group=-4900)
async def receive_added_track(client, message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in {'advanced_add_audio', 'advanced_add_subtitle'}:
        return
    media = message.document or message.audio
    if not media:
        return
    source = await client.download_media(message, file_name=os.path.join(job.work_dir, 'added_track'))
    action = job.selected_action
    out = os.path.join(job.work_dir, 'advanced_added.mkv')
    try:
        if action == 'advanced_add_audio':
            await _run_ffmpeg('-i', job.input_path, '-i', source, '-map', '0', '-map', '1:a:0', '-c', 'copy', out)
        else:
            await _run_ffmpeg('-i', job.input_path, '-i', source, '-map', '0', '-map', '1:s:0', '-c', 'copy', out)
        final = os.path.join(job.work_dir, _safe(os.path.splitext(job.original_name)[0]) + '_advanced.mkv')
        os.replace(out, final)
        await _send_result(client, job, final, '🛠 **Advanced processing complete.**')
        await message.reply_text('✅ **Advanced operation completed.**')
    except Exception as exc:
        await message.reply_text(f'❌ **Advanced operation failed**\n\n`{str(exc)[:1500]}`')
    finally:
        shutil.rmtree(job.work_dir, ignore_errors=True)
        await jobs.remove(job.job_id)
    raise StopPropagation


@Client.on_callback_query(filters.regex(r'^job:trim:([0-9a-f]+)$'), group=-4900)
async def ask_trim(client, cb):
    job = await _job(client, cb)
    if not job:
        raise StopPropagation
    await cb.answer()
    await jobs.update(job.job_id, selected_action='advanced_trim')
    await cb.message.edit_text('✂️ **Trim Video**\n\nSend `start | end` in seconds. Example: `10 | 120`', reply_markup=cancel_markup(job.job_id))
    raise StopPropagation


@Client.on_message(filters.private & filters.text, group=-4900)
async def trim_input(client, message):
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action != 'advanced_trim':
        return
    try:
        start_s, end_s = [float(x.strip()) for x in (message.text or '').split('|', 1)]
        if start_s < 0 or end_s <= start_s:
            raise ValueError('End time must be greater than start time.')
        ext = os.path.splitext(job.original_name)[1] or '.mp4'
        out = os.path.join(job.work_dir, 'trimmed' + ext)
        await _run_ffmpeg('-ss', str(start_s), '-to', str(end_s), '-i', job.input_path, '-map', '0', '-c', 'copy', out)
        await _send_result(client, job, out, '✂️ **Trimmed video**')
        await message.reply_text('✅ **Trim completed.**')
        shutil.rmtree(job.work_dir, ignore_errors=True)
        await jobs.remove(job.job_id)
    except Exception as exc:
        await message.reply_text(f'❌ **Trim failed**\n\n`{str(exc)[:1500]}`')
    raise StopPropagation

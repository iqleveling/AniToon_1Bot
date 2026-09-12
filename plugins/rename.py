import os
import time
import asyncio
import shutil

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
)
from pyrogram.errors import FloodWait

from config import Config
from helper.database import db
from helper.plans import get_plan
from helper.utils import (
    progress_for_pyrogram,
    humanbytes,
)
from helper.ffmpeg import (
    fix_metadata,
    get_video_info,
    take_screenshot,
)
from helper.splitter import split_file


# ============================================================
# AUTOMATIC MEDIA DETECTION
# ============================================================

@Client.on_message(
    filters.private
    & (
        filters.document
        | filters.video
        | filters.audio
    )
)
async def auto_detect(
    client,
    message,
):
    user_id = message.from_user.id

    bot_id = getattr(
        client,
        "bot_id",
        0,
    )

    if not await db.is_user_exist(
        user_id
    ):
        await db.add_user(
            user_id
        )

    user_data = await db.get_user_data(
        user_id
    )

    if not user_data:
        return

    if user_data.get(
        "is_banned",
        False,
    ):
        return await message.reply_text(
            "❌ **You are banned from using this bot.**"
        )

    subscription = (
        await db.get_subscription(
            user_id,
            bot_id,
        )
    )

    plan = get_plan(
        subscription.get(
            "plan",
            "free",
        )
    )

    used = await db.get_usage(
        user_id,
        bot_id,
    )

    if used >= plan.daily_limit:
        return await message.reply_text(
            "🚫 **Daily Limit Reached!**\n\n"
            f"Current Plan: {plan.name}\n"
            f"Daily Limit: "
            f"`{humanbytes(plan.daily_limit)}`\n"
            f"Used: "
            f"`{humanbytes(used)}`\n\n"
            "Upgrade your plan for a higher daily limit.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "💎 Upgrade",
                            callback_data="upgrade",
                        )
                    ]
                ]
            ),
        )

    media = (
        message.document
        or message.video
        or message.audio
    )

    if not media:
        return

    filename = getattr(
        media,
        "file_name",
        None,
    ) or f"file_{message.id}"

    await message.reply_text(
        "📂 **File Detected**\n\n"
        f"📄 `{filename}`\n\n"
        "✏️ Enter the **new filename**.\n\n"
        "Example:\n"
        "`Episode 01.mkv`",
        reply_to_message_id=message.id,
        reply_markup=ForceReply(
            selective=True
        ),
    )


# ============================================================
# RENAME PROCESS
# ============================================================

@Client.on_message(
    filters.private
    & filters.reply
    & filters.text
)
async def process_rename(
    client,
    message,
):
    reply = message.reply_to_message

    if not reply:
        return

    if not reply.reply_markup:
        return

    if not isinstance(
        reply.reply_markup,
        ForceReply,
    ):
        return

    new_name = message.text.strip()

    if (
        not new_name
        or "." not in new_name
    ):
        return await message.reply_text(
            "❌ **Invalid filename.**\n\n"
            "Include a file extension such as "
            "`.mkv` or `.mp4`."
        )

    user_id = message.from_user.id

    bot_id = getattr(
        client,
        "bot_id",
        0,
    )

    media = (
        reply.document
        or reply.video
        or reply.audio
    )

    if not media:
        return await message.reply_text(
            "❌ Original media could not be found."
        )

    user_data = await db.get_user_data(
        user_id
    )

    if not user_data:
        await db.add_user(
            user_id
        )
        user_data = await db.get_user_data(
            user_id
        )

    if user_data.get(
        "is_banned",
        False,
    ):
        return await message.reply_text(
            "❌ **You are banned from using this bot.**"
        )

    subscription = (
        await db.get_subscription(
            user_id,
            bot_id,
        )
    )

    plan = get_plan(
        subscription.get(
            "plan",
            "free",
        )
    )

    used = await db.get_usage(
        user_id,
        bot_id,
    )

    if used >= plan.daily_limit:
        return await message.reply_text(
            "🚫 **Daily Limit Reached!**"
        )

    original_name = getattr(
        media,
        "file_name",
        None,
    ) or f"file_{reply.id}"

    work_dir = os.path.join(
        "downloads",
        str(user_id),
        str(
            int(
                time.time() * 1000
            )
        ),
    )

    os.makedirs(
        work_dir,
        exist_ok=True,
    )

    download_path = os.path.join(
        work_dir,
        original_name,
    )

    output_path = os.path.join(
        work_dir,
        new_name,
    )

    status = await message.reply_text(
        "📥 **AniToon: Preparing download...**"
    )

    try:
        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        await client.download_media(
            message=reply,
            file_name=download_path,
            progress=progress_for_pyrogram,
            progress_args=(
                "📥 Downloading",
                status,
                time.time(),
            ),
        )

        downloaded_size = os.path.getsize(
            download_path
        )

        if (
            used + downloaded_size
            > plan.daily_limit
        ):
            return await status.edit_text(
                "🚫 **This file exceeds your remaining daily quota.**\n\n"
                f"Plan: {plan.name}\n"
                f"Remaining: "
                f"`{humanbytes(max(plan.daily_limit - used, 0))}`\n"
                f"File: "
                f"`{humanbytes(downloaded_size)}`"
            )

        # ----------------------------------------------------
        # METADATA
        # ----------------------------------------------------

        mime_type = getattr(
            media,
            "mime_type",
            None,
        )

        processing_path = download_path

        if mime_type and (
            mime_type.startswith("video/")
            or mime_type.startswith("audio/")
        ):
            await status.edit_text(
                "🏷️ **AniToon: Processing metadata...**"
            )

            audio_name = user_data.get(
                "audio_name",
                "AniToon Official",
            )

            subtitle_name = user_data.get(
                "sub_name",
                "AniToon Official",
            )

            success = await fix_metadata(
                download_path,
                output_path,
                audio_name=audio_name,
                subtitle_name=subtitle_name,
            )

            if success:
                processing_path = output_path

        # ----------------------------------------------------
        # VIDEO INFORMATION
        # ----------------------------------------------------

        duration = 0
        width = 0
        height = 0

        if (
            mime_type
            and mime_type.startswith(
                "video/"
            )
        ):
            (
                duration,
                width,
                height,
            ) = await get_video_info(
                processing_path
            )

        # ----------------------------------------------------
        # THUMBNAIL
        # ----------------------------------------------------

        thumb = await db.get_thumbnail(
            user_id
        )

        if not thumb and duration > 0:
            thumb = await take_screenshot(
                processing_path,
                os.path.join(
                    work_dir,
                    "thumb.jpg",
                ),
                duration,
            )

        # ----------------------------------------------------
        # CAPTION
        # ----------------------------------------------------

        final_size = os.path.getsize(
            processing_path
        )

        saved_caption = await db.get_caption(
            user_id
        )

        if saved_caption:
            caption = (
                saved_caption
                .replace(
                    "{filename}",
                    new_name,
                )
                .replace(
                    "{filesize}",
                    humanbytes(final_size),
                )
                .replace(
                    "{duration}",
                    str(duration),
                )
            )
        else:
            caption = (
                "✅ **Renamed by AniToon**\n\n"
                f"📂 `{new_name}`\n"
                f"📦 `{humanbytes(final_size)}`\n\n"
                "📥 Uploaded By : @AniToon_Edit"
            )

        # ----------------------------------------------------
        # SPLIT
        # ----------------------------------------------------

        split_limit = (
            2_000_000_000
        )

        if final_size > split_limit:
            await status.edit_text(
                "✂️ **Large file detected.**\n\n"
                "Splitting into smaller parts..."
            )

            parts = await split_file(
                processing_path,
                chunk_size=split_limit,
            )
        else:
            parts = [
                processing_path
            ]

        # ----------------------------------------------------
        # UPLOAD
        # ----------------------------------------------------

        total_parts = len(parts)

        for index, part in enumerate(
            parts,
            start=1,
        ):
            part_name = os.path.basename(
                part
            )

            await status.edit_text(
                "📤 **AniToon: Uploading...**\n\n"
                f"📦 Part `{index}/{total_parts}`\n"
                f"📂 `{part_name}`"
            )

            part_caption = (
                caption
                + "\n\n"
                f"📦 Part: `{index}/{total_parts}`"
            )

            if (
                mime_type
                and mime_type.startswith(
                    "video/"
                )
            ):
                sent = (
                    await client.send_video(
                        chat_id=message.chat.id,
                        video=part,
                        thumb=(
                            thumb
                            if index == 1
                            else None
                        ),
                        caption=part_caption,
                        duration=(
                            int(duration)
                            if index == 1
                            else None
                        ),
                        width=(
                            width
                            if index == 1
                            else None
                        ),
                        height=(
                            height
                            if index == 1
                            else None
                        ),
                        supports_streaming=True,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            f"📤 Part {index}",
                            status,
                            time.time(),
                        ),
                    )
                )

            elif (
                mime_type
                and mime_type.startswith(
                    "audio/"
                )
            ):
                sent = (
                    await client.send_audio(
                        chat_id=message.chat.id,
                        audio=part,
                        thumb=(
                            thumb
                            if index == 1
                            else None
                        ),
                        caption=part_caption,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            f"📤 Part {index}",
                            status,
                            time.time(),
                        ),
                    )
                )

            else:
                sent = (
                    await client.send_document(
                        chat_id=message.chat.id,
                        document=part,
                        thumb=(
                            thumb
                            if index == 1
                            else None
                        ),
                        caption=part_caption,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            f"📤 Part {index}",
                            status,
                            time.time(),
                        ),
                    )
                )

            if Config.LOG_CHANNEL:
                try:
                    await sent.copy(
                        Config.LOG_CHANNEL
                    )
                except Exception as e:
                    print(
                        f"Log backup error: {e}"
                    )

        # ----------------------------------------------------
        # UPDATE USAGE
        # ----------------------------------------------------

        await db.update_usage(
            user_id,
            bot_id,
            final_size,
        )

        await status.edit_text(
            "✅ **Processing Complete!**\n\n"
            f"💎 Plan: {plan.name}\n"
            f"📦 Parts: `{total_parts}`\n"
            f"💾 Size: `{humanbytes(final_size)}`"
        )

    except FloodWait as e:
        await status.edit_text(
            "⏳ **Telegram FloodWait**\n\n"
            f"Waiting `{e.value}` seconds..."
        )

        await asyncio.sleep(
            e.value
        )

    except Exception as e:
        print(
            f"Rename error: {e}"
        )

        try:
            await status.edit_text(
                "❌ **Processing Failed**\n\n"
                f"`{str(e)[:1000]}`"
            )
        except Exception:
            pass

    finally:
        try:
            if os.path.exists(
                work_dir
            ):
                shutil.rmtree(
                    work_dir
                )
        except Exception:
            pass

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
from helper.utils import (
    progress_for_pyrogram,
    humanbytes,
)
from helper.ffmpeg import (
    fix_metadata,
    get_video_info,
    take_screenshot,
)


# --- AUTOMATIC MEDIA DETECTION ---
@Client.on_message(
    filters.private
    & (
        filters.document
        | filters.video
        | filters.audio
    )
)
async def auto_detect(client, message):
    """
    Detect incoming files and check the user's
    account status and daily quota.
    """

    user_id = message.from_user.id

    # Make sure the user exists in the database.
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id)

    user_data = await db.get_user_data(user_id)

    if not user_data:
        return await message.reply_text(
            "❌ Unable to load your account data."
        )

    # --- BAN CHECK ---
    if user_data.get("is_banned", False):
        return await message.reply_text(
            "❌ **You are banned from using this bot.**"
        )

    # --- DAILY QUOTA CHECK ---
    used = await db.get_usage(user_id)
    is_premium = user_data.get("is_premium", False)

    if not is_premium and used >= Config.DAILY_LIMIT:
        return await message.reply_text(
            "🚫 **Daily Limit Reached!**\n\n"
            f"You have used your free "
            f"**{humanbytes(Config.DAILY_LIMIT)}** quota today.\n\n"
            "💎 Upgrade to Premium for higher limits.",
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

    # --- DETECT MEDIA ---
    try:
        media = message.document or message.video or message.audio

        if not media:
            return

        filename = getattr(
            media,
            "file_name",
            None,
        ) or f"file_{message.id}"

    except Exception:
        return await message.reply_text(
            "❌ Unable to detect the file."
        )

    # --- RENAME PROMPT ---
    await message.reply_text(
        f"📂 **File Detected**\n\n"
        f"**Name:** `{filename}`\n\n"
        "✏️ Please enter the **new filename**.\n\n"
        "Example:\n"
        "`My Anime Episode 01.mkv`",
        reply_to_message_id=message.id,
        reply_markup=ForceReply(
            selective=True
        ),
    )


# --- RENAME PROCESS ---
@Client.on_message(
    filters.private
    & filters.reply
    & filters.text
)
async def process_rename(client, message):
    """
    Downloads the replied file, applies metadata,
    then uploads the renamed file.
    """

    reply = message.reply_to_message

    if not reply:
        return

    # Only process replies to our ForceReply prompt.
    if not reply.reply_markup:
        return

    if not isinstance(
        reply.reply_markup,
        ForceReply,
    ):
        return

    new_name = message.text.strip()

    if not new_name:
        return await message.reply_text(
            "❌ **Filename cannot be empty.**"
        )

    # Require a file extension.
    if "." not in new_name:
        return await message.reply_text(
            "❌ **Invalid filename.**\n\n"
            "Please include a file extension.\n"
            "Example: `Episode 01.mkv`"
        )

    user_id = message.from_user.id

    # --- GET ORIGINAL MEDIA ---
    media = (
        reply.document
        or reply.video
        or reply.audio
    )

    if not media:
        return await message.reply_text(
            "❌ Original media could not be found."
        )

    original_name = getattr(
        media,
        "file_name",
        None,
    ) or f"file_{reply.id}"

    # --- CHECK USER AGAIN ---
    user_data = await db.get_user_data(user_id)

    if not user_data:
        await db.add_user(user_id)
        user_data = await db.get_user_data(user_id)

    if user_data.get("is_banned", False):
        return await message.reply_text(
            "❌ **You are banned from using this bot.**"
        )

    used = await db.get_usage(user_id)

    if (
        not user_data.get("is_premium", False)
        and used >= Config.DAILY_LIMIT
    ):
        return await message.reply_text(
            "🚫 **Daily Limit Reached!**"
        )

    # --- CREATE WORKING DIRECTORY ---
    timestamp = str(int(time.time() * 1000))

    path = os.path.join(
        "downloads",
        str(user_id),
        timestamp,
    )

    os.makedirs(
        path,
        exist_ok=True,
    )

    download_path = os.path.join(
        path,
        original_name,
    )

    output_path = os.path.join(
        path,
        new_name,
    )

    status_message = await message.reply_text(
        "📥 **AniToon: Preparing download...**"
    )

    try:
        # --- DOWNLOAD ---
        start_time = time.time()

        await client.download_media(
            message=reply,
            file_name=download_path,
            progress=progress_for_pyrogram,
            progress_args=(
                "📥 Downloading",
                status_message,
                start_time,
            ),
        )

        if not os.path.exists(download_path):
            raise FileNotFoundError(
                "Downloaded file was not created."
            )

        downloaded_size = os.path.getsize(
            download_path
        )

        # Check quota against actual file size.
        if (
            not user_data.get("is_premium", False)
            and used + downloaded_size
            > Config.DAILY_LIMIT
        ):
            return await status_message.edit_text(
                "🚫 **Daily Limit Exceeded**\n\n"
                f"File Size: `{humanbytes(downloaded_size)}`\n"
                f"Remaining: `{humanbytes(max(Config.DAILY_LIMIT - used, 0))}`"
            )

        # --- METADATA ---
        await status_message.edit_text(
            "🏷️ **AniToon: Processing metadata...**"
        )

        metadata_success = await fix_metadata(
            download_path,
            output_path,
        )

        if metadata_success:
            processing_path = output_path
        else:
            # Fallback to original file if FFmpeg
            # could not process the metadata.
            processing_path = download_path
            output_path = download_path

            # The requested new filename is still used
            # later during upload.
            await status_message.edit_text(
                "⚠️ **Metadata processing failed.**\n"
                "Continuing with the renamed file..."
            )

        # --- VIDEO INFORMATION ---
        duration = 0
        width = 0
        height = 0

        if media.mime_type and media.mime_type.startswith(
            "video/"
        ):
            (
                duration,
                width,
                height,
            ) = await get_video_info(
                processing_path
            )

        # --- THUMBNAIL ---
        user_thumb = await db.get_thumbnail(
            user_id
        )

        generated_thumb = None

        if (
            not user_thumb
            and duration > 0
        ):
            generated_thumb = await take_screenshot(
                processing_path,
                os.path.join(
                    path,
                    "thumb.jpg",
                ),
                duration,
            )

            user_thumb = generated_thumb

        # --- UPLOAD ---
        await status_message.edit_text(
            "📤 **AniToon: Starting upload...**"
        )

        file_size = os.path.getsize(
            processing_path
        )

        # Use the user client for large uploads
        # when the premium session is available.
        upload_client = client

        if (
            file_size > 2 * 1024 * 1024 * 1024
            and hasattr(client, "USER")
            and client.USER
        ):
            upload_client = client.USER

        upload_caption = (
            f"✅ **Renamed by AniToon**\n\n"
            f"📂 `{new_name}`\n"
            f"📦 `{humanbytes(file_size)}`\n\n"
            f"📥 Uploaded By : @AniToon_Edit"
        )

        # Apply saved user caption when available.
        saved_caption = await db.get_caption(
            user_id
        )

        if saved_caption:
            upload_caption = (
                saved_caption
                .replace(
                    "{filename}",
                    new_name,
                )
                .replace(
                    "{filesize}",
                    humanbytes(file_size),
                )
                .replace(
                    "{duration}",
                    str(duration),
                )
            )

        # --- SEND FILE ---
        if media.mime_type and media.mime_type.startswith(
            "video/"
        ):
            sent_file = await upload_client.send_video(
                chat_id=message.chat.id,
                video=processing_path,
                thumb=user_thumb,
                caption=upload_caption,
                duration=int(duration),
                width=width,
                height=height,
                supports_streaming=True,
                progress=progress_for_pyrogram,
                progress_args=(
                    "📤 Uploading",
                    status_message,
                    time.time(),
                ),
            )

        elif media.mime_type and media.mime_type.startswith(
            "audio/"
        ):
            sent_file = await upload_client.send_audio(
                chat_id=message.chat.id,
                audio=processing_path,
                thumb=user_thumb,
                caption=upload_caption,
                progress=progress_for_pyrogram,
                progress_args=(
                    "📤 Uploading",
                    status_message,
                    time.time(),
                ),
            )

        else:
            sent_file = await upload_client.send_document(
                chat_id=message.chat.id,
                document=processing_path,
                thumb=user_thumb,
                caption=upload_caption,
                progress=progress_for_pyrogram,
                progress_args=(
                    "📤 Uploading",
                    status_message,
                    time.time(),
                ),
            )

        # --- PRIVATE LOG BACKUP ---
        if Config.LOG_CHANNEL:
            try:
                await sent_file.copy(
                    Config.LOG_CHANNEL
                )
            except Exception as e:
                print(
                    f"Log channel backup failed: {e}"
                )

        # --- UPDATE USER QUOTA ---
        await db.update_usage(
            user_id,
            file_size,
        )

        await status_message.delete()

    except FloodWait as e:
        await status_message.edit_text(
            f"⏳ **Telegram FloodWait**\n\n"
            f"Please wait `{e.value}` seconds."
        )

    except Exception as e:
        print(
            f"Rename Error for {user_id}: {e}"
        )

        try:
            await status_message.edit_text(
                "❌ **Processing Failed**\n\n"
                f"`{str(e)[:1000]}`"
            )
        except Exception:
            pass

    finally:
        # --- CLEANUP ---
        try:
            if os.path.exists(path):
                shutil.rmtree(path)
        except Exception as e:
            print(
                f"Cleanup Error: {e}"
            )

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
async def auto_detect(client, message):
    """
    Detects incoming media and asks the user
    for the new filename.
    """

    user_id = message.from_user.id

    # Create the user if necessary.
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id)

    user_data = await db.get_user_data(user_id)

    if not user_data:
        return await message.reply_text(
            "❌ **Unable to load your account data.**"
        )

    # --------------------------------------------------------
    # BAN CHECK
    # --------------------------------------------------------

    if user_data.get("is_banned", False):
        return await message.reply_text(
            "❌ **You are banned from using this bot.**"
        )

    # --------------------------------------------------------
    # DAILY QUOTA CHECK
    # --------------------------------------------------------

    used = await db.get_usage(user_id)
    is_premium = user_data.get(
        "is_premium",
        False,
    )

    if (
        not is_premium
        and used >= Config.DAILY_LIMIT
    ):
        return await message.reply_text(
            "🚫 **Daily Limit Reached!**\n\n"
            f"Your free daily quota of "
            f"**{humanbytes(Config.DAILY_LIMIT)}** "
            "has been used.\n\n"
            "💎 Upgrade to Premium for higher access.",
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

    # --------------------------------------------------------
    # MEDIA DETECTION
    # --------------------------------------------------------

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
    )

    if not filename:
        filename = f"file_{message.id}"

    # --------------------------------------------------------
    # RENAME PROMPT
    # --------------------------------------------------------

    await message.reply_text(
        "📂 **File Detected**\n\n"
        f"📄 **Current Name:** `{filename}`\n\n"
        "✏️ Please enter the **new filename**.\n\n"
        "Example:\n"
        "`My Anime Episode 01.mkv`",
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
async def process_rename(client, message):
    """
    Downloads, processes, renames, optionally splits,
    uploads and cleans up the file.
    """

    reply = message.reply_to_message

    if not reply:
        return

    # --------------------------------------------------------
    # VERIFY RENAME PROMPT
    # --------------------------------------------------------

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

    if "." not in new_name:
        return await message.reply_text(
            "❌ **Invalid filename.**\n\n"
            "Please include the file extension.\n\n"
            "Example:\n"
            "`Episode 01.mkv`"
        )

    user_id = message.from_user.id

    # --------------------------------------------------------
    # GET ORIGINAL MEDIA
    # --------------------------------------------------------

    media = (
        reply.document
        or reply.video
        or reply.audio
    )

    if not media:
        return await message.reply_text(
            "❌ **Original media could not be found.**"
        )

    original_name = getattr(
        media,
        "file_name",
        None,
    )

    if not original_name:
        original_name = f"file_{reply.id}"

    # --------------------------------------------------------
    # GET USER DATA
    # --------------------------------------------------------

    user_data = await db.get_user_data(user_id)

    if not user_data:
        await db.add_user(user_id)
        user_data = await db.get_user_data(user_id)

    if not user_data:
        return await message.reply_text(
            "❌ **Unable to load your account.**"
        )

    if user_data.get(
        "is_banned",
        False,
    ):
        return await message.reply_text(
            "❌ **You are banned from using this bot.**"
        )

    used = await db.get_usage(user_id)
    is_premium = user_data.get(
        "is_premium",
        False,
    )

    if (
        not is_premium
        and used >= Config.DAILY_LIMIT
    ):
        return await message.reply_text(
            "🚫 **Daily Limit Reached!**"
        )

    # --------------------------------------------------------
    # WORK DIRECTORY
    # --------------------------------------------------------

    timestamp = str(
        int(time.time() * 1000)
    )

    work_dir = os.path.join(
        "downloads",
        str(user_id),
        timestamp,
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

    status_message = await message.reply_text(
        "📥 **AniToon: Preparing download...**"
    )

    try:
        # ====================================================
        # STEP 1: DOWNLOAD
        # ====================================================

        download_start = time.time()

        await client.download_media(
            message=reply,
            file_name=download_path,
            progress=progress_for_pyrogram,
            progress_args=(
                "📥 Downloading",
                status_message,
                download_start,
            ),
        )

        if not os.path.exists(
            download_path
        ):
            raise FileNotFoundError(
                "Downloaded file was not created."
            )

        downloaded_size = os.path.getsize(
            download_path
        )

        # ----------------------------------------------------
        # QUOTA CHECK USING ACTUAL FILE SIZE
        # ----------------------------------------------------

        if (
            not is_premium
            and (
                used + downloaded_size
                > Config.DAILY_LIMIT
            )
        ):
            return await status_message.edit_text(
                "🚫 **Daily Quota Exceeded**\n\n"
                f"📦 File Size: "
                f"`{humanbytes(downloaded_size)}`\n"
                f"⏳ Remaining: "
                f"`{humanbytes(max(Config.DAILY_LIMIT - used, 0))}`"
            )

        # ====================================================
        # STEP 2: METADATA PROCESSING
        # ====================================================

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
            processing_path = download_path

            # If FFmpeg could not create the output file,
            # continue using the downloaded source.
            await status_message.edit_text(
                "⚠️ **Metadata processing failed.**\n\n"
                "Continuing with the original media..."
            )

        # ====================================================
        # STEP 3: VIDEO INFORMATION
        # ====================================================

        duration = 0
        width = 0
        height = 0

        mime_type = getattr(
            media,
            "mime_type",
            None,
        )

        if (
            mime_type
            and mime_type.startswith("video/")
        ):
            (
                duration,
                width,
                height,
            ) = await get_video_info(
                processing_path
            )

        # ====================================================
        # STEP 4: THUMBNAIL
        # ====================================================

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
                    work_dir,
                    "thumb.jpg",
                ),
                duration,
            )

            user_thumb = generated_thumb

        # ====================================================
        # STEP 5: PREPARE UPLOAD
        # ====================================================

        await status_message.edit_text(
            "📤 **AniToon: Preparing upload...**"
        )

        final_size = os.path.getsize(
            processing_path
        )

        # ----------------------------------------------------
        # CAPTION
        # ----------------------------------------------------

        upload_caption = (
            "✅ **Renamed by AniToon**\n\n"
            f"📂 `{new_name}`\n"
            f"📦 `{humanbytes(final_size)}`\n\n"
            "📥 Uploaded By : @AniToon_Edit"
        )

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
                    humanbytes(final_size),
                )
                .replace(
                    "{duration}",
                    str(duration),
                )
            )

        # ====================================================
        # STEP 6: SPLIT LARGE FILE
        # ====================================================

        # Keep parts under approximately 2 GB.
        split_limit = 2_000_000_000

        if final_size > split_limit:
            await status_message.edit_text(
                "✂️ **Large File Detected**\n\n"
                f"📦 Size: `{humanbytes(final_size)}`\n"
                "Splitting into smaller parts..."
            )

            file_parts = await split_file(
                processing_path,
                chunk_size=split_limit,
            )

        else:
            file_parts = [
                processing_path
            ]

        # ====================================================
        # STEP 7: UPLOAD PARTS
        # ====================================================

        total_parts = len(
            file_parts
        )

        for index, part_path in enumerate(
            file_parts,
            start=1,
        ):
            part_name = os.path.basename(
                part_path
            )

            part_size = os.path.getsize(
                part_path
            )

            await status_message.edit_text(
                "📤 **AniToon: Uploading...**\n\n"
                f"📦 **Part:** `{index}/{total_parts}`\n"
                f"📂 `{part_name}`\n"
                f"💾 `{humanbytes(part_size)}`"
            )

            part_caption = (
                upload_caption
                + "\n\n"
                f"📦 **Part:** `{index}/{total_parts}`"
            )

            # ------------------------------------------------
            # CHOOSE UPLOAD CLIENT
            # ------------------------------------------------

            upload_client = client

            if (
                part_size
                > 2_000_000_000
                and hasattr(
                    client,
                    "USER",
                )
                and client.USER
            ):
                upload_client = client.USER

            # ------------------------------------------------
            # UPLOAD
            # ------------------------------------------------

            try:
                if (
                    mime_type
                    and mime_type.startswith(
                        "video/"
                    )
                ):
                    sent_file = (
                        await upload_client.send_video(
                            chat_id=message.chat.id,
                            video=part_path,
                            thumb=(
                                user_thumb
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
                            progress=(
                                progress_for_pyrogram
                            ),
                            progress_args=(
                                f"📤 Uploading Part {index}",
                                status_message,
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
                    sent_file = (
                        await upload_client.send_audio(
                            chat_id=message.chat.id,
                            audio=part_path,
                            thumb=(
                                user_thumb
                                if index == 1
                                else None
                            ),
                            caption=part_caption,
                            progress=(
                                progress_for_pyrogram
                            ),
                            progress_args=(
                                f"📤 Uploading Part {index}",
                                status_message,
                                time.time(),
                            ),
                        )
                    )

                else:
                    sent_file = (
                        await upload_client.send_document(
                            chat_id=message.chat.id,
                            document=part_path,
                            thumb=(
                                user_thumb
                                if index == 1
                                else None
                            ),
                            caption=part_caption,
                            progress=(
                                progress_for_pyrogram
                            ),
                            progress_args=(
                                f"📤 Uploading Part {index}",
                                status_message,
                                time.time(),
                            ),
                        )
                    )

            except FloodWait as e:
                await status_message.edit_text(
                    "⏳ **Telegram FloodWait**\n\n"
                    f"Waiting `{e.value}` seconds..."
                )

                await asyncio.sleep(
                    e.value
                )

                # Retry using document upload.
                sent_file = (
                    await upload_client.send_document(
                        chat_id=message.chat.id,
                        document=part_path,
                        caption=part_caption,
                    )
                )

            # ------------------------------------------------
            # LOG CHANNEL BACKUP
            # ------------------------------------------------

            if Config.LOG_CHANNEL:
                try:
                    await sent_file.copy(
                        Config.LOG_CHANNEL
                    )
                except Exception as e:
                    print(
                        f"Log backup failed: {e}"
                    )

        # ====================================================
        # STEP 8: UPDATE QUOTA
        # ====================================================

        total_processed_size = sum(
            os.path.getsize(part)
            for part in file_parts
            if os.path.exists(part)
        )

        await db.update_usage(
            user_id,
            total_processed_size,
        )

        # ====================================================
        # STEP 9: COMPLETE
        # ====================================================

        await status_message.edit_text(
            "✅ **Processing Complete!**\n\n"
            f"📦 **Parts:** `{total_parts}`\n"
            f"💾 **Total Size:** "
            f"`{humanbytes(final_size)}`"
        )

    # ========================================================
    # ERROR HANDLING
    # ========================================================

    except FloodWait as e:
        try:
            await status_message.edit_text(
                "⏳ **Telegram FloodWait**\n\n"
                f"Please wait `{e.value}` seconds."
            )
        except Exception:
            pass

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

    # ========================================================
    # CLEANUP
    # ========================================================

    finally:
        try:
            if os.path.exists(
                work_dir
            ):
                shutil.rmtree(
                    work_dir
                )
        except Exception as e:
            print(
                f"Cleanup Error: {e}"
            )

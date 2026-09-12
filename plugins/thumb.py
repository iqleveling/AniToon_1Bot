from pyrogram import Client, filters
from pyrogram.types import Message

from helper.database import db


# ============================================================
# SAVE THUMBNAIL
# ============================================================

@Client.on_message(
    filters.private & filters.photo
)
async def save_photo(
    client: Client,
    message: Message,
):
    """
    Saves the user's selected photo as a permanent thumbnail.
    """

    user_id = message.from_user.id

    # Make sure the user exists.
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id)

    status = await message.reply_text(
        "🔄 **AniToon: Saving your thumbnail...**"
    )

    try:
        await db.set_thumbnail(
            user_id,
            message.photo.file_id,
        )

        await status.edit_text(
            "✅ **Thumbnail Saved Successfully!**\n\n"
            "This thumbnail will be used for your renamed files."
        )

    except Exception as e:
        await status.edit_text(
            "❌ **Failed to save thumbnail.**\n\n"
            f"`{str(e)[:1000]}`"
        )


# ============================================================
# VIEW THUMBNAIL
# ============================================================

@Client.on_message(
    filters.private
    & filters.command(
        ["setthumb", "set_thumb"]
    )
)
async def set_thumbnail_command(
    client: Client,
    message: Message,
):
    await message.reply_text(
        "🖼️ **Send me an image now.**\n\n"
        "I will save it as your custom thumbnail."
    )


@Client.on_message(
    filters.private
    & filters.command(
        ["viewthumb", "view_thumb", "showthumb"]
    )
)
async def view_thumbnail(
    client: Client,
    message: Message,
):
    """
    Displays the user's currently saved thumbnail.
    """

    user_id = message.from_user.id

    thumb = await db.get_thumbnail(
        user_id
    )

    if thumb:
        await message.reply_photo(
            photo=thumb,
            caption=(
                "🖼️ **Your Current Custom Thumbnail**\n\n"
                "Use `/delthumb` to remove it."
            ),
        )

    else:
        await message.reply_text(
            "❌ **No Custom Thumbnail Set**\n\n"
            "Send me any image to save it as your permanent thumbnail."
        )


# ============================================================
# DELETE THUMBNAIL
# ============================================================

@Client.on_message(
    filters.private
    & filters.command(
        ["delthumb", "del_thumb", "deletethumb"]
    )
)
async def delete_thumbnail(
    client: Client,
    message: Message,
):
    """
    Removes the user's saved thumbnail.
    """

    user_id = message.from_user.id

    await db.set_thumbnail(
        user_id,
        None,
    )

    await message.reply_text(
        "🗑️ **Custom Thumbnail Deleted.**\n\n"
        "Your files will now use automatically generated "
        "or original thumbnails."
    )

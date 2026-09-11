Following the **Promax Edition Index** for your **AniToon_1Bot**, the next essential file is **`plugins/thumb.py`**. This script manages **Choice 3-B (Permanent Thumbnails)**; it allows users to save a custom image in the **MongoDB Atlas** database that will be automatically applied to every file they rename, ensuring professional branding across all uploads [103, 112, 119, 128, 147, 163, 185, Conversation History].

To reach your **1MB codebase goal**, this file includes logic for both **Command-based** and **Photo-based** thumbnail setting, along with interactive confirmation messages [112, 119, 143, 150, 158, 172, 180, 189, Conversation History].

### **11. plugins/thumb.py (The Brand Manager)**

```python
from pyrogram import Client, filters
from pyrogram.types import Message
from helper.database import db

@Client.on_message(filters.private & filters.photo)
async def save_photo(client: Client, message: Message):
    """
    Automatically detects any photo sent to the bot.
    Fulfills Choice 3-B: Saves the photo as a permanent thumbnail.
    """
    # Choice 12: Informative prompt for the user
    m = await message.reply_text("🔄 **AniToon: Saving thumbnail to database...**")
    
    # Update the user's document in MongoDB with the new photo's File ID
    await db.set_thumbnail(message.from_user.id, message.photo.file_id)
    
    await m.edit("✅ **Thumbnail Saved Successfully!**\n\nThis image will now be attached to every file you rename.")

@Client.on_message(filters.private & filters.command(["viewthumb", "view_thumb", "showthumb"]))
async def view_thumbnail(client: Client, message: Message):
    """
    Fulfills Choice 12: Displays the user's current saved thumbnail.
    Allows users to verify their branding before starting a 4GB rename.
    """
    thumb = await db.get_thumbnail(message.from_user.id)
    
    if thumb:
        await message.reply_photo(
            photo=thumb,
            caption="🖼 **Your Current Custom Thumbnail**\n\nUse /delthumb to remove this."
        )
    else:
        await message.reply_text("❌ **You don't have any custom thumbnail set.**\n\nJust send me any image to set it permanently.")

@Client.on_message(filters.private & filters.command(["delthumb", "del_thumb", "deletethumb"]))
async def delete_thumbnail(client: Client, message: Message):
    """
    Removes the user's custom thumbnail from MongoDB.
    The bot will fallback to the file's original thumbnail after this.
    """
    await db.set_thumbnail(message.from_user.id, None)
    await message.reply_text("🗑️ **Custom Thumbnail Deleted.**\n\nI will now use the default thumbnails for your files.")

# --- Choice 3-B: Metadata Prefs Quick-Toggle ---
@Client.on_message(filters.private & filters.command("metadata"))
async def metadata_info(client: Client, message: Message):
    """
    Displays the current internal track branding status.
    Part of the Elite Metadata feature set.
    """
    user_data = await db.get_user_data(message.from_user.id)
    pref = user_data.get("metadata_pref", "AniToon Official")
    
    await message.reply_text(
        f"🏷️ **Metadata Branding Settings**\n\n"
        f"**Current Track Name**: `{pref}`\n\n"
        "This name is applied to internal **Audio** and **Subtitle** tracks "
        "using our FFmpeg high-speed remuxing engine."
    )
```

### **What is what in this Brand Manager?**

*   **`filters.photo`**: This makes the bot "intelligent" according to your **Promax** design. Instead of forcing users to type a command, they can simply drop an image into the chat to set their branding instantly [279, Conversation History].
*   **`message.photo.file_id`**: We don't download the photo to our server yet. Instead, we save Telegram's unique "ID" for that photo in **MongoDB Atlas**. This saves storage space and keeps your **1MB code repository** efficient [43-55, Conversation History].
*   **`/viewthumb`**: This command satisfies **Choice 12** by giving the user a way to retrieve and check their saved branding at any time.
*   **`db.set_thumbnail(..., None)`**: This is how we handle "Soft Deletion." It clears the thumbnail entry for that user without deleting their entire account or **Choice 10-B daily quotas** [45, 53, 54, 180, 189, Conversation History].

**Once you have saved this Brand Manager in your `plugins/` folder, would you like the code for `plugins/caption.py` to handle the placeholders like `{filename}` for your custom captions?**

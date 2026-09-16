# Telegram Auto-Rename & Router Script (Pyrogram)
# Requirements: pip install pyrogram tgcrypto

import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# --- CONFIGURATION ---
API_ID = 1234567          # Replace with your Telegram API ID
API_HASH = "your_hash"    # Replace with your Telegram API HASH
BOT_TOKEN = "your_token"  # Replace with your Telegram Bot Token

# If running a local Telegram Bot API Server for maximum speed and bypassing 50MB limit:
# LOCAL_API_SERVER = "http://localhost:8081" 
# app = Client("rename_router", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, api_server=LOCAL_API_SERVER)

app = Client("rename_router", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# In-memory session tracker to store new names from users
# Format: { user_id: {"file_id": str, "new_name": str} }
user_sessions = {}

@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def catch_file(client: Client, message: Message):
    """Intercepts an incoming file and requests a new name."""
    file = message.document or message.video or message.audio
    user_sessions[message.from_user.id] = {
        "file_message": message,
        "original_name": file.file_name if hasattr(file, "file_name") else "file"
    }
    
    await message.reply_text(
        f"📥 **File Received:** `{user_sessions[message.from_user.id]['original_name']}`

"
        "Please send the **new filename** (including extension, e.g., `movie.mp4`):"
    )

@app.on_message(filters.private & filters.text & ~filters.command([]))
async def rename_process(client: Client, message: Message):
    """Processes the renaming, downloads, and re-uploads at local VPS speeds."""
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        await message.reply_text("Please send a file first!")
        return
        
    new_name = message.text.strip()
    session = user_sessions[user_id]
    file_msg = session["file_message"]
    
    status_msg = await message.reply_text("⚡ *Downloading file to local router server...*")
    
    # Define local path
    download_path = os.path.join(".", new_name)
    
    try:
        # Progress callback for download
        async def progress(current, total):
            try:
                percentage = (current / total) * 100
                await status_msg.edit_text(f"📥 *Downloading:* {percentage:.1f}%")
            except Exception:
                pass

        # Step 1: Download
        await file_msg.download(file_name=download_path, progress=progress)
        
        # Step 2: Upload under new name
        await status_msg.edit_text("📤 *Uploading renamed file to Telegram...*")
        
        async def upload_progress(current, total):
            try:
                percentage = (current / total) * 100
                await status_msg.edit_text(f"📤 *Uploading:* {percentage:.1f}%")
            except Exception:
                pass
                
        await client.send_document(
            chat_id=message.chat.id,
            document=download_path,
            caption=f"✅ **Renamed successfully!**
📄 `{new_name}`",
            progress=upload_progress
        )
        
        await status_msg.delete()
        
    except Exception as e:
        await status_msg.edit_text(f"❌ **An error occurred:** `{str(e)}`")
        
    finally:
        # Clean up the file from the local server to prevent storage issues
        if os.path.exists(download_path):
            os.remove(download_path)
        del user_sessions[user_id]

if __name__ == "__main__":
    print("🚀 Local Renaming Router Bot Started...")
    app.run()

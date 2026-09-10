from pyrogram import Client, filters
from config import Config

# Initialize the Bot Client
app = Client(
    "AniToon_1Bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text(f"Hello {message.from_user.first_name}! I am the AniToon Rename Bot. Send me a file to begin.")

@app.on_message(filters.command("id") & filters.private)
async def get_id(client, message):
    await message.reply_text(f"Your Telegram ID is: `{message.from_user.id}`")

if __name__ == "__main__":
    print("Bot is starting...")
    app.run()

"""Small set of public command helpers."""

from pyrogram import Client, filters


@Client.on_message(
    filters.private & filters.command("help"),
    group=-90,
)
async def command_help(client, message):
    await message.reply_text(
        "🛠 **AniToon Help**\n\n"
        "📂 Send a document, video or audio to process it.\n"
        "✏️ Choose Custom Rename, Auto Rename, Convert or Advanced Rename.\n"
        "🖼 Send an image to save a custom thumbnail.\n"
        "📝 Use `/setcaption` to manage your caption.\n"
        "🏷 Use `/metadata` to manage audio/subtitle names.\n"
        "💎 Use `/plan` or `/status` to view your quota.\n"
        "🤖 Use `/clone` to create a clone from the main bot.\n\n"
        "Send a file after joining all required channels."
    )

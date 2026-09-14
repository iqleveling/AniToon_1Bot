from pyrogram import Client, StopPropagation, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config


def is_owner(user_id: int) -> bool:
    return bool(Config.OWNER_ID and int(user_id) == int(Config.OWNER_ID))


@Client.on_message(filters.private & filters.command("start"), group=-300)
async def owner_start_page(client, message):
    if not getattr(client, "is_main_bot", False) or not is_owner(message.from_user.id):
        return
    await message.reply_text(
        "🔥 **Welcome to AniToon Bot** 🔥\n\n"
        "👑 **Owner access detected**\n"
        "⚡ Unlimited owner access\n\n"
        "Use the owner controls below.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛠 Help", callback_data="help"), InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
            [InlineKeyboardButton("✏️ Rename", callback_data="start_rename")],
            [InlineKeyboardButton("🤖 Create Your Own Clone Bot", callback_data="create_clone")],
            [InlineKeyboardButton("👑 Owner Panel", callback_data="owner:panel")],
        ]),
    )
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^owner:panel$"), group=-300)
async def owner_panel_entry(client, callback_query):
    if not getattr(client, "is_main_bot", False) or not is_owner(callback_query.from_user.id):
        await callback_query.answer("Owner access only.", show_alert=True)
        raise StopPropagation
    await callback_query.answer()
    await callback_query.message.edit_text(
        "👑 **AniToon Owner Panel**\n\n"
        "Owner-only controls are available here.\n\n"
        "📊 Use `/users` for statistics.\n"
        "👤 Use `/user <id>` for user details.\n"
        "💎 Use `/setplan <id> <free|pro|premium|ultra>` to change a plan.\n"
        "📣 Use `/broadcast` to broadcast a replied message.\n"
        "🤖 Use `/clone <BOT_TOKEN>` to manage clone creation.\n\n"
        "This panel is restricted to `Config.OWNER_ID`.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Home", callback_data="start")]]),
    )
    raise StopPropagation

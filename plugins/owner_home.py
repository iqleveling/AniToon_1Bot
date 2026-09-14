from pyrogram import Client, StopPropagation, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config


def is_owner(user_id: int) -> bool:
    return bool(Config.OWNER_ID and int(user_id) == int(Config.OWNER_ID))


def owner_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠 Help", callback_data="help"), InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("✏️ Rename", callback_data="start_rename")],
        [InlineKeyboardButton("🤖 Create Your Own Clone Bot", callback_data="create_clone")],
        [InlineKeyboardButton("👑 Owner Panel", callback_data="owner:panel")],
    ])


def panel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistics", callback_data="owner:stats")],
        [InlineKeyboardButton("💎 Plans & Stars", callback_data="owner:plans")],
        [InlineKeyboardButton("🤖 Bot Details", callback_data="owner:bots")],
        [InlineKeyboardButton("📣 Broadcast Users", callback_data="owner:broadcast")],
        [InlineKeyboardButton("🔙 Home", callback_data="start")],
    ])


async def show_owner_home(message):
    await message.edit_text(
        "🔥 **Welcome to AniToon Bot** 🔥\n\n👑 **Owner access detected**\n⚡ Unlimited owner access\n\nUse the owner controls below.",
        reply_markup=owner_keyboard(),
    )


@Client.on_message(filters.private & filters.command("start"), group=-300)
async def owner_start_page(client, message):
    if not getattr(client, "is_main_bot", False) or not is_owner(message.from_user.id):
        return
    await message.reply_text(
        "🔥 **Welcome to AniToon Bot** 🔥\n\n👑 **Owner access detected**\n⚡ Unlimited owner access\n\nUse the owner controls below.",
        reply_markup=owner_keyboard(),
    )
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^owner:panel$"), group=-300)
async def owner_panel_entry(client, callback_query):
    if not getattr(client, "is_main_bot", False) or not is_owner(callback_query.from_user.id):
        await callback_query.answer("Owner access only.", show_alert=True)
        raise StopPropagation
    await callback_query.answer()
    await callback_query.message.edit_text(
        "👑 **AniToon Owner Panel**\n\nOnly `Config.OWNER_ID` can use these controls.",
        reply_markup=panel_keyboard(),
    )
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^owner:(stats|plans|bots|broadcast)$"), group=-300)
async def owner_panel_help(client, callback_query):
    if not getattr(client, "is_main_bot", False) or not is_owner(callback_query.from_user.id):
        await callback_query.answer("Owner access only.", show_alert=True)
        raise StopPropagation
    await callback_query.answer()
    action = callback_query.matches[0].group(1)
    if action == "stats":
        text = "📊 **Statistics**\n\nUse `/users` for total users and `/user <id>` for detailed user information."
    elif action == "plans":
        text = "💎 **Plans & Stars**\n\nUse `/ownerplans` to view plans.\nUse `/ownerstars <pro|premium|ultra> <stars>` to change a price.\nUse `/ownerlimit <pro|premium|ultra> <gb>` to change a daily limit."
    elif action == "bots":
        text = "🤖 **Bot Details**\n\nUse `/ownerbots` to view registered clone bots and their status."
    else:
        text = "📣 **Broadcast Users**\n\nReply to the message you want to send and use `/broadcast`."
    await callback_query.message.edit_text(text, reply_markup=panel_keyboard())
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^start$"), group=-300)
async def owner_home_callback(client, callback_query):
    if not getattr(client, "is_main_bot", False) or not is_owner(callback_query.from_user.id):
        return
    await callback_query.answer()
    await show_owner_home(callback_query.message)
    raise StopPropagation

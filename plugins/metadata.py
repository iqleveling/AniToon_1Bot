from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply, Message
from helper.database import db
from helper.metadata import MetadataSettings, get_metadata, reset_metadata, update_metadata_part
from plugins.ui import edit_callback_message


def metadata_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎵 Edit Audio", callback_data="meta:audio")],
        [InlineKeyboardButton("📜 Edit Subtitle", callback_data="meta:subtitle")],
        [InlineKeyboardButton("🔄 Reset Defaults", callback_data="reset_metadata")],
        [InlineKeyboardButton("🔙 Back", callback_data="settings")],
    ])


def _text(s: MetadataSettings):
    return f"🏷️ **Metadata Settings**\n\n🎵 **Audio Track:** `{s.audio_name}`\n📜 **Subtitle Track:** `{s.subtitle_name}`\n\nCustomize prefix and language independently."


async def show_metadata(client: Client, chat_id: int, message=None):
    text = _text(await get_metadata(int(chat_id)))
    if message: await message.reply_text(text, reply_markup=metadata_keyboard())
    else: await client.send_message(int(chat_id), text, reply_markup=metadata_keyboard())


@Client.on_message(filters.private & filters.command(["metadata", "metasettings"]), group=-3000)
async def metadata_settings(client: Client, message: Message):
    await show_metadata(client, message.from_user.id, message)


@Client.on_callback_query(filters.regex(r"^metadata_settings$"), group=-3000)
async def cb_metadata_settings(client, cb):
    await cb.answer()
    await edit_callback_message(cb, _text(await get_metadata(cb.from_user.id)), reply_markup=metadata_keyboard())


@Client.on_callback_query(filters.regex(r"^meta:(audio|subtitle)$"), group=-3000)
async def cb_metadata_section(client, cb):
    kind = cb.matches[0].group(1)
    s = await get_metadata(cb.from_user.id)
    if kind == "audio":
        text = f"🎵 **Edit Audio Track**\n\nPrefix: `{s.audio_prefix}`\nLanguage: `{s.audio_language}`\nFinal: `{s.audio_name}`"
    else:
        text = f"📜 **Edit Subtitle Track**\n\nPrefix: `{s.subtitle_prefix}`\nLanguage: `{s.subtitle_language}`\nFinal: `{s.subtitle_name}`"
    rows = [[InlineKeyboardButton("🏷 Change Prefix", callback_data=f"metaedit:{kind}:prefix")], [InlineKeyboardButton("🌐 Change Language", callback_data=f"metaedit:{kind}:language")], [InlineKeyboardButton("🔙 Metadata", callback_data="metadata_settings")]]
    await cb.answer()
    await edit_callback_message(cb, text, reply_markup=InlineKeyboardMarkup(rows))


@Client.on_callback_query(filters.regex(r"^metaedit:(audio|subtitle):(prefix|language)$"), group=-3000)
async def cb_metadata_edit(client, cb):
    kind, field = cb.matches[0].group(1), cb.matches[0].group(2)
    label = "Prefix" if field == "prefix" else "Language"
    prompt = await client.send_message(cb.from_user.id, f"⌨️ Enter {kind.title()} {label}:", reply_markup=ForceReply(selective=True))
    await db.col.update_one({"id": int(cb.from_user.id)}, {"$set": {"metadata_prompt": {"kind": kind, "field": field, "message_id": prompt.id}}}, upsert=True)
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^reset_metadata$"), group=-3000)
async def cb_reset_meta(client, cb):
    s = await reset_metadata(cb.from_user.id)
    await cb.answer("Metadata reset successfully ✅", show_alert=True)
    await edit_callback_message(cb, _text(s), reply_markup=metadata_keyboard())


@Client.on_message(filters.private & filters.text, group=-3000)
async def handle_meta_replies(client, message: Message):
    if not message.from_user: return
    u = await db.get_user_data(message.from_user.id) or {}
    p = u.get("metadata_prompt")
    if not p: return
    if message.reply_to_message and p.get("message_id") != message.reply_to_message.id: return
    value = (message.text or "").strip()
    if not value:
        await message.reply_text("❌ **Value cannot be empty.**")
        return
    s = await update_metadata_part(message.from_user.id, p["kind"], p["field"], value)
    await db.col.update_one({"id": int(message.from_user.id)}, {"$unset": {"metadata_prompt": ""}})
    await message.reply_text(_text(s), reply_markup=metadata_keyboard())

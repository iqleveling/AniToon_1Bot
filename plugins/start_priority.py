"""High-priority /start dispatcher and private message tracker."""

from pyrogram import Client, StopPropagation, filters

from config import Config
from helper.message_cleanup import install_auto_cleanup, remember_user_message
from plugins.ui import main_menu


def _apply_force_sub_links():
    """Apply FORCE_SUB_LINKS without changing the existing start flow."""
    try:
        from plugins.start import FORCE_SUB_CHANNELS

        links = [
            item.strip()
            for item in Config.FORCE_SUB_LINKS.split(",")
            if item.strip()
        ]

        # The configured order is Channel 1, 2, 3, 4.
        for index, link in enumerate(links[:len(FORCE_SUB_CHANNELS)]):
            FORCE_SUB_CHANNELS[index]["link"] = link
    except Exception:
        # Never prevent /start from running because of optional link config.
        pass


@Client.on_message(filters.private, group=-30000)
async def track_private_message(client, message):
    """Remember the latest private user message for the next bot response."""
    try:
        install_auto_cleanup(client)
        if message.from_user and not message.from_user.is_bot:
            await remember_user_message(message.chat.id, message.id)
    except Exception:
        pass


@Client.on_message(
    filters.private & filters.command("start"),
    group=-100,
)
async def priority_start(client, message):
    install_auto_cleanup(client)
    try:
        if message.from_user and not message.from_user.is_bot:
            await remember_user_message(message.chat.id, message.id)
    except Exception:
        pass

    # Clones are already created by an owner who has passed the main-bot
    # ForceSub gate. Requiring every clone to be an administrator in the
    # same four channels would make newly created clones appear dead.
    if not getattr(client, "is_main_bot", False):
        user = message.from_user
        await message.reply_text(
            "🔥 **Welcome to AniToon Clone** 🔥\n\n"
            f"👋 Hello **{user.first_name}**!\n\n"
            "📂 Send me any file, video or audio to get started.",
            reply_markup=main_menu(False),
        )
        raise StopPropagation

    _apply_force_sub_links()

    from plugins.start import start

    await start(client, message)
    raise StopPropagation

"""High-priority /start dispatcher."""

from pyrogram import Client, StopPropagation, filters

from config import Config
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


@Client.on_message(
    filters.private & filters.command("start"),
    group=-100,
)
async def priority_start(client, message):
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

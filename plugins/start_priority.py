"""High-priority /start dispatcher."""

from pyrogram import Client, filters, StopPropagation

from config import Config



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
    _apply_force_sub_links()

    from plugins.start import start

    await start(client, message)
    raise StopPropagation

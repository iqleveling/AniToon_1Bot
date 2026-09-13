import logging

from pyrogram import Client
from pyrogram.types import BotCommand

from config import Config
from helper.database import db


log = logging.getLogger(__name__)


CLONE_COMMANDS = [
    BotCommand("start", "Start AniToon"),
    BotCommand("help", "Show help and usage"),
    BotCommand("plan", "View your current plan"),
    BotCommand("status", "View plan and daily usage"),
    BotCommand("setcaption", "Set your custom caption"),
    BotCommand("metadata", "Manage audio/subtitle metadata"),
]


class CloneManager:
    def __init__(self, main_client):
        self.main_client = main_client
        self.clones: dict[int, Client] = {}

    async def _setup_clone_commands(self, client: Client):
        """Install only commands that are actually available on clones."""
        try:
            await client.delete_bot_commands()
            await client.set_bot_commands(CLONE_COMMANDS)
        except Exception:
            # A command-menu problem must not make an otherwise healthy clone
            # unusable.
            log.exception("Could not update clone command menu")

    async def start_clone(self, bot_token: str):
        client = None
        try:
            # Never log the token or include it in an exception message.
            token_prefix = bot_token.split(":", 1)[0]
            client = Client(
                name=f"clone_{token_prefix}",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=bot_token,
                in_memory=True,
                workers=100,
                plugins={"root": "plugins"},
            )
            client.is_main_bot = False
            client.is_clone_bot = True
            client.bot_id = 0
            client.bot_username = None
            client.clone_manager = None

            await client.start()
            me = await client.get_me()
            client.bot_id = me.id
            client.bot_username = me.username
            self.clones[me.id] = client

            await self._setup_clone_commands(client)
            await db.set_clone_status(me.id, "online")
            log.info("Clone started: @%s", me.username or me.id)
            return client
        except Exception:
            log.exception("Clone startup failed; main bot will continue running.")
            if client is not None:
                try:
                    await client.stop()
                except Exception:
                    pass
            return None

    async def add_clone(self, owner_id: int, bot_token: str):
        client = await self.start_clone(bot_token)
        if not client:
            return None
        me = await client.get_me()
        await db.add_clone(
            owner_id=owner_id,
            bot_id=me.id,
            bot_username=me.username,
            bot_name=me.first_name,
            bot_token=bot_token,
        )
        return client

    async def start_all(self):
        try:
            async for clone in db.get_all_clones():
                token = clone.get("bot_token")
                if not token:
                    continue
                bot_id = clone.get("bot_id")
                if bot_id in self.clones:
                    continue
                client = await self.start_clone(token)
                if client is None and bot_id:
                    try:
                        await db.set_clone_status(bot_id, "offline")
                    except Exception:
                        pass
        except Exception:
            log.exception("Could not load saved clones; main bot remains online.")

    async def stop_all(self):
        for bot_id, client in list(self.clones.items()):
            try:
                await client.stop()
            except Exception:
                log.exception("Clone stop failed for %s", bot_id)
            try:
                await db.set_clone_status(bot_id, "offline")
            except Exception:
                pass
        self.clones.clear()

import asyncio
import logging

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import BotCommand

from config import Config
from helper.clone_manager import CloneManager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("AniToon")


# ============================================================
# BOT COMMAND MENU
# ============================================================

BOT_COMMANDS = [
    BotCommand("start", "Start AniToon"),
    BotCommand("help", "Show help and usage"),
    BotCommand("plan", "View your current plan"),
    BotCommand("status", "View plan and daily usage"),
    BotCommand("clone", "Create your AniToon clone"),
    BotCommand("setcaption", "Set your custom caption"),
    BotCommand("metadata", "Manage audio/subtitle metadata"),
    BotCommand("paysupport", "Get payment support"),
]


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="AniToon_1Bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=100,
            plugins={"root": "plugins"},
        )
        self.is_main_bot = True
        self.is_clone_bot = False
        self.bot_id = 0
        self.bot_username = None
        self.clone_manager = None

    async def _setup_commands(self):
        """
        Replace the old Telegram command menu completely.
        delete_bot_commands() clears the previous default scope,
        then set_bot_commands() installs the current clean menu.
        """
        try:
            await self.delete_bot_commands()
            await self.set_bot_commands(BOT_COMMANDS)
            log.info(
                "✅ Telegram command menu reset and updated: %s commands",
                len(BOT_COMMANDS),
            )
        except Exception:
            # A command-menu failure must never stop the bot itself.
            log.exception("Could not update Telegram bot commands")

    async def start(self):
        while True:
            try:
                await super().start()
                me = await self.get_me()
                self.bot_id = me.id
                self.bot_username = me.username

                log.info(
                    "✅ Main bot started: @%s (ID: %s)",
                    me.username or "unknown",
                    me.id,
                )

                await self._setup_commands()

                if Config.IS_CLONE_ALLOWED:
                    self.clone_manager = CloneManager(self)
                    await self.clone_manager.start_all()
                    log.info("🤖 Clone Engine: enabled")

                return

            except FloodWait as e:
                wait_time = int(getattr(e, "value", 0) or 0)
                log.error(
                    "Telegram FloodWait during startup: %s seconds",
                    wait_time,
                )
                if wait_time <= 0:
                    raise
                await asyncio.sleep(wait_time)

            except Exception:
                log.exception("Main bot startup failed")
                raise

    async def stop(self, *args):
        if self.clone_manager:
            await self.clone_manager.stop_all()
            self.clone_manager = None
        await super().stop()
        log.info("AniToon_1Bot stopped")


if __name__ == "__main__":
    Bot().run()

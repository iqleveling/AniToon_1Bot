import asyncio
import logging

from pyrogram import Client

from config import Config
from helper.clone_manager import CloneManager


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
)


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="AniToon_1Bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=100,
            plugins={
                "root": "plugins"
            },
        )

        self.is_main_bot = True
        self.is_clone_bot = False

        self.clone_manager = None


    async def start(self):
        await super().start()

        me = await self.get_me()

        print(
            f"✅ {me.first_name} "
            "[Promax Edition] Started Successfully!"
        )

        # --------------------------------------------------------
        # CLONE MANAGER
        # --------------------------------------------------------

        if Config.IS_CLONE_ALLOWED:
            self.clone_manager = CloneManager(
                self
            )

            await self.clone_manager.start_all()

            print(
                "🤖 Clone Engine: Enabled"
            )

        else:
            print(
                "🤖 Clone Engine: Disabled"
            )


    async def stop(self, *args):
        if self.clone_manager:
            await self.clone_manager.stop_all()

        await super().stop()

        print(
            "❌ AniToon_1Bot stopped."
        )


if __name__ == "__main__":
    Bot().run()

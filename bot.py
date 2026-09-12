import asyncio
import logging

from pyrogram import Client
from pyrogram.errors import FloodWait

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
        self.bot_id = 0
        self.clone_manager = None


    async def start(self):
        while True:
            try:
                await super().start()

                me = await self.get_me()

                self.bot_id = me.id

                print(
                    f"✅ {me.first_name} "
                    "[Promax Edition] Started Successfully!"
                )

                if Config.IS_CLONE_ALLOWED:
                    self.clone_manager = (
                        CloneManager(self)
                    )

                    await self.clone_manager.start_all()

                    print(
                        "🤖 Clone Engine: Enabled"
                    )

                return

            except FloodWait as e:
                wait_time = int(
                    e.value
                )

                logging.error(
                    "Telegram FloodWait: "
                    f"{wait_time} seconds"
                )

                logging.error(
                    "Do not redeploy repeatedly. "
                    "Waiting before retry..."
                )

                await asyncio.sleep(
                    wait_time
                )

            except Exception:
                logging.exception(
                    "Main bot startup failed."
                )
                raise


    async def stop(self, *args):
        if self.clone_manager:
            await self.clone_manager.stop_all()

        await super().stop()

        print(
            "❌ AniToon_1Bot stopped."
        )


if __name__ == "__main__":
    Bot().run()

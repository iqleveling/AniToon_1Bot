from pyrogram import Client
from config import Config
import logging

# Set up logging to track internal errors and performance
logging.basicConfig(level=logging.ERROR)


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="AniToon_1Bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=100,
            plugins=dict(root="plugins")
        )

    async def start(self):
        await super().start()

        me = await self.get_me()
        print(f"✅ {me.first_name} [Promax Edition] Started Successfully!")

        # Initialize the Premium User Client
        if Config.STRING_SESSION:
            print("💎 Initializing Premium Client...")

            self.USER = Client(
                name="Premium_User",
                session_string=Config.STRING_SESSION,
                api_id=Config.API_ID,
                api_hash=Config.API_HASH
            )

            await self.USER.start()
            print("✅ Premium Session Active!")

    async def stop(self, *args):
        # Stop the bot
        await super().stop()

        # Stop the Premium User Client safely
        if hasattr(self, "USER"):
            await self.USER.stop()

        print("❌ Bot Stopped.")


if __name__ == "__main__":
    Bot().run()

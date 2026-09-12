from datetime import datetime, timedelta

import motor.motor_asyncio

from config import Config


DB_NAME = "AniToon_Promax_DB"
DEFAULT_METADATA_NAME = "AniToon Official"


class Database:
    def __init__(self, uri: str, database_name: str = DB_NAME):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=10000,
        )
        self.db = self._client[database_name]
        self.col = self.db.user
        self.subscriptions = self.db.subscriptions
        self.usage = self.db.usage
        self.payments = self.db.payments
        self.clones = self.db.clones

    # ---------- users ----------
    @staticmethod
    def new_user(user_id: int) -> dict:
        return {
            "id": int(user_id),
            "join_date": datetime.utcnow(),
            "thumb": None,
            "caption": None,
            "audio_name": DEFAULT_METADATA_NAME,
            "sub_name": DEFAULT_METADATA_NAME,
            "is_banned": False,
        }

    async def add_user(self, user_id: int):
        await self.col.update_one(
            {"id": int(user_id)},
            {"$setOnInsert": self.new_user(user_id)},
            upsert=True,
        )

    async def is_user_exist(self, user_id: int) -> bool:
        return await self.col.count_documents({"id": int(user_id)}, limit=1) > 0

    async def get_user_data(self, user_id: int):
        return await self.col.find_one({"id": int(user_id)})

    async def total_users_count(self) -> int:
        return await self.col.count_documents({})

    def get_all_users(self):
        return self.col.find({})

    # ---------- subscriptions ----------
    async def get_subscription(self, user_id: int, bot_id: int) -> dict:
        user_id = int(user_id)
        bot_id = int(bot_id)
        record = await self.subscriptions.find_one(
            {"user_id": user_id, "bot_id": bot_id}
        )
        if not record:
            return {
                "user_id": user_id,
                "bot_id": bot_id,
                "plan": "free",
                "expires_at": None,
                "stars_paid": 0,
            }

        plan_key = record.get("plan", "free")
        expires_at = record.get("expires_at")
        if plan_key != "free" and expires_at and expires_at <= datetime.utcnow():
            await self.subscriptions.update_one(
                {"user_id": user_id, "bot_id": bot_id},
                {"$set": {"plan": "free", "expires_at": None}},
            )
            record["plan"] = "free"
            record["expires_at"] = None
            record["stars_paid"] = 0
        return record

    async def set_plan(
        self,
        user_id: int,
        bot_id: int,
        plan_key: str,
        stars_paid: int = 0,
        payment_id: str | None = None,
    ):
        from helper.plans import get_plan

        user_id = int(user_id)
        bot_id = int(bot_id)
        plan = get_plan(plan_key)
        now = datetime.utcnow()

        if plan_key == "free":
            expires_at = None
        else:
            current = await self.subscriptions.find_one(
                {"user_id": user_id, "bot_id": bot_id}
            )
            current_expiry = current.get("expires_at") if current else None
            start = current_expiry if current_expiry and current_expiry > now else now
            expires_at = start + timedelta(days=plan.days)

        await self.subscriptions.update_one(
            {"user_id": user_id, "bot_id": bot_id},
            {
                "$set": {
                    "user_id": user_id,
                    "bot_id": bot_id,
                    "plan": plan_key,
                    "expires_at": expires_at,
                    "stars_paid": int(stars_paid),
                    "payment_id": payment_id,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

    # ---------- daily usage ----------
    async def get_usage(self, user_id: int, bot_id: int) -> int:
        today = datetime.utcnow().date().isoformat()
        record = await self.usage.find_one(
            {"user_id": int(user_id), "bot_id": int(bot_id), "date": today}
        )
        return int(record.get("bytes", 0)) if record else 0

    async def update_usage(self, user_id: int, bot_id: int, bytes_count: int):
        today = datetime.utcnow().date().isoformat()
        await self.usage.update_one(
            {"user_id": int(user_id), "bot_id": int(bot_id), "date": today},
            {"$inc": {"bytes": int(bytes_count)}},
            upsert=True,
        )

    # ---------- thumbnail / caption / metadata ----------
    async def set_thumbnail(self, user_id: int, file_id: str | None):
        await self.col.update_one(
            {"id": int(user_id)},
            {"$set": {"thumb": file_id}},
            upsert=True,
        )

    async def get_thumbnail(self, user_id: int):
        user = await self.col.find_one({"id": int(user_id)}, {"thumb": 1})
        return user.get("thumb") if user else None

    async def set_caption(self, user_id: int, caption: str | None):
        await self.col.update_one(
            {"id": int(user_id)},
            {"$set": {"caption": caption}},
            upsert=True,
        )

    async def get_caption(self, user_id: int):
        user = await self.col.find_one({"id": int(user_id)}, {"caption": 1})
        return user.get("caption") if user else None

    async def set_audio_name(self, user_id: int, audio_name: str):
        await self.col.update_one(
            {"id": int(user_id)},
            {"$set": {"audio_name": str(audio_name)}},
            upsert=True,
        )

    async def set_subtitle_name(self, user_id: int, subtitle_name: str):
        await self.col.update_one(
            {"id": int(user_id)},
            {"$set": {"sub_name": str(subtitle_name)}},
            upsert=True,
        )

    async def set_metadata(self, user_id: int, audio_name: str, subtitle_name: str):
        await self.col.update_one(
            {"id": int(user_id)},
            {
                "$set": {
                    "audio_name": str(audio_name),
                    "sub_name": str(subtitle_name),
                }
            },
            upsert=True,
        )

    # ---------- ban ----------
    async def ban_user(self, user_id: int):
        await self.col.update_one(
            {"id": int(user_id)}, {"$set": {"is_banned": True}}, upsert=True
        )

    async def unban_user(self, user_id: int):
        await self.col.update_one(
            {"id": int(user_id)}, {"$set": {"is_banned": False}}, upsert=True
        )

    # ---------- payments ----------
    async def payment_exists(self, charge_id: str) -> bool:
        return bool(await self.payments.find_one({"charge_id": charge_id}, {"_id": 1}))

    async def record_payment(
        self,
        user_id: int,
        bot_id: int,
        plan_key: str,
        stars: int,
        charge_id: str,
    ) -> bool:
        if await self.payment_exists(charge_id):
            return False
        await self.payments.insert_one(
            {
                "user_id": int(user_id),
                "bot_id": int(bot_id),
                "plan": plan_key,
                "stars": int(stars),
                "charge_id": charge_id,
                "created_at": datetime.utcnow(),
            }
        )
        return True

    # ---------- clones ----------
    async def add_clone(
        self,
        owner_id: int,
        bot_id: int,
        bot_username: str | None,
        bot_name: str | None,
        bot_token: str,
    ):
        now = datetime.utcnow()
        await self.clones.update_one(
            {"bot_id": int(bot_id)},
            {
                "$set": {
                    "owner_id": int(owner_id),
                    "bot_id": int(bot_id),
                    "bot_username": bot_username,
                    "bot_name": bot_name,
                    "bot_token": bot_token,
                    "status": "online",
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def get_clone(self, owner_id: int):
        return await self.clones.find_one({"owner_id": int(owner_id)})

    async def get_clone_by_bot_id(self, bot_id: int):
        return await self.clones.find_one({"bot_id": int(bot_id)})

    def get_all_clones(self):
        return self.clones.find({})

    async def set_clone_status(self, bot_id: int, status: str):
        await self.clones.update_one(
            {"bot_id": int(bot_id)},
            {"$set": {"status": status, "updated_at": datetime.utcnow()}},
        )

    async def remove_clone(self, bot_id: int):
        await self.clones.delete_one({"bot_id": int(bot_id)})


# DATABASE_URL is already the existing Render environment variable.
db = Database(Config.DATABASE_URL, DB_NAME)

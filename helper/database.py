import motor.motor_asyncio

from datetime import datetime, timedelta


class Database:
    def __init__(
        self,
        uri,
        database_name,
    ):
        self._client = (
            motor.motor_asyncio.AsyncIOMotorClient(
                uri
            )
        )

        self.db = self._client[
            database_name
        ]

        self.col = self.db.user
        self.subscriptions = self.db.subscriptions
        self.usage = self.db.usage
        self.payments = self.db.payments
        self.clones = self.db.clones

    # ============================================================
    # USERS
    # ============================================================

    def new_user(self, user_id):
        return {
            "id": int(user_id),
            "join_date": datetime.now(),
            "thumb": None,
            "caption": None,
            "is_banned": False,
        }

    async def add_user(self, user_id):
        await self.col.update_one(
            {
                "id": int(user_id)
            },
            {
                "$setOnInsert": self.new_user(
                    user_id
                )
            },
            upsert=True,
        )

    async def is_user_exist(self, user_id):
        user = await self.col.find_one(
            {
                "id": int(user_id)
            }
        )

        return bool(user)

    async def get_user_data(self, user_id):
        return await self.col.find_one(
            {
                "id": int(user_id)
            }
        )

    async def total_users_count(self):
        return await self.col.count_documents({})

    async def get_all_users(self):
        return self.col.find({})

    # ============================================================
    # PLANS
    # ============================================================

    async def get_subscription(
        self,
        user_id,
        bot_id,
    ):
        user_id = int(user_id)
        bot_id = int(bot_id)

        subscription = (
            await self.subscriptions.find_one(
                {
                    "user_id": user_id,
                    "bot_id": bot_id,
                }
            )
        )

        if not subscription:
            return {
                "user_id": user_id,
                "bot_id": bot_id,
                "plan": "free",
                "expires_at": None,
                "stars_paid": 0,
            }

        expires_at = subscription.get(
            "expires_at"
        )

        plan = subscription.get(
            "plan",
            "free",
        )

        if (
            plan != "free"
            and expires_at
            and expires_at <= datetime.now()
        ):
            await self.subscriptions.update_one(
                {
                    "user_id": user_id,
                    "bot_id": bot_id,
                },
                {
                    "$set": {
                        "plan": "free",
                        "expires_at": None,
                    }
                },
            )

            return {
                "user_id": user_id,
                "bot_id": bot_id,
                "plan": "free",
                "expires_at": None,
                "stars_paid": 0,
            }

        return subscription

    async def set_plan(
        self,
        user_id,
        bot_id,
        plan_key,
        stars_paid=0,
        payment_id=None,
    ):
        from helper.plans import get_plan

        user_id = int(user_id)
        bot_id = int(bot_id)

        plan = get_plan(
            plan_key
        )

        now = datetime.now()

        current = (
            await self.subscriptions.find_one(
                {
                    "user_id": user_id,
                    "bot_id": bot_id,
                }
            )
        )

        if plan_key == "free":
            expires_at = None

        else:
            current_expiry = (
                current.get(
                    "expires_at"
                )
                if current
                else None
            )

            if (
                current_expiry
                and current_expiry > now
            ):
                start_date = current_expiry
            else:
                start_date = now

            expires_at = (
                start_date
                + timedelta(
                    days=plan.days
                )
            )

        await self.subscriptions.update_one(
            {
                "user_id": user_id,
                "bot_id": bot_id,
            },
            {
                "$set": {
                    "user_id": user_id,
                    "bot_id": bot_id,
                    "plan": plan_key,
                    "expires_at": expires_at,
                    "stars_paid": int(
                        stars_paid
                    ),
                    "payment_id": payment_id,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

    # ============================================================
    # DAILY USAGE
    # ============================================================

    async def get_usage(
        self,
        user_id,
        bot_id,
    ):
        today = (
            datetime.now()
            .date()
            .isoformat()
        )

        record = await self.usage.find_one(
            {
                "user_id": int(user_id),
                "bot_id": int(bot_id),
                "date": today,
            }
        )

        if not record:
            return 0

        return int(
            record.get(
                "bytes",
                0,
            )
        )

    async def update_usage(
        self,
        user_id,
        bot_id,
        bytes_count,
    ):
        today = (
            datetime.now()
            .date()
            .isoformat()
        )

        await self.usage.update_one(
            {
                "user_id": int(user_id),
                "bot_id": int(bot_id),
                "date": today,
            },
            {
                "$inc": {
                    "bytes": int(
                        bytes_count
                    )
                }
            },
            upsert=True,
        )

    # ============================================================
    # THUMBNAIL
    # ============================================================

    async def set_thumbnail(
        self,
        user_id,
        file_id,
    ):
        await self.col.update_one(
            {
                "id": int(user_id)
            },
            {
                "$set": {
                    "thumb": file_id
                }
            },
            upsert=True,
        )

    async def get_thumbnail(
        self,
        user_id,
    ):
        user = await self.col.find_one(
            {
                "id": int(user_id)
            }
        )

        if not user:
            return None

        return user.get(
            "thumb"
        )

    # ============================================================
    # CAPTION
    # ============================================================

    async def set_caption(
        self,
        user_id,
        caption,
    ):
        await self.col.update_one(
            {
                "id": int(user_id)
            },
            {
                "$set": {
                    "caption": caption
                }
            },
            upsert=True,
        )

    async def get_caption(
        self,
        user_id,
    ):
        user = await self.col.find_one(
            {
                "id": int(user_id)
            }
        )

        if not user:
            return None

        return user.get(
            "caption"
        )

    # ============================================================
    # BAN
    # ============================================================

    async def ban_user(
        self,
        user_id,
    ):
        await self.col.update_one(
            {
                "id": int(user_id)
            },
            {
                "$set": {
                    "is_banned": True
                }
            },
            upsert=True,
        )

    async def unban_user(
        self,
        user_id,
    ):
        await self.col.update_one(
            {
                "id": int(user_id)
            },
            {
                "$set": {
                    "is_banned": False
                }
            },
            upsert=True,
        )

    # ============================================================
    # PAYMENTS
    # ============================================================

    async def payment_exists(
        self,
        charge_id,
    ):
        result = (
            await self.payments.find_one(
                {
                    "charge_id": charge_id
                }
            )
        )

        return bool(result)

    async def record_payment(
        self,
        user_id,
        bot_id,
        plan_key,
        stars,
        charge_id,
    ):
        if await self.payment_exists(
            charge_id
        ):
            return False

        await self.payments.insert_one(
            {
                "user_id": int(user_id),
                "bot_id": int(bot_id),
                "plan": plan_key,
                "stars": int(stars),
                "charge_id": charge_id,
                "created_at": datetime.now(),
            }
        )

        return True

    # ============================================================
    # CLONES
    # ============================================================

    async def add_clone(
        self,
        owner_id,
        bot_id,
        bot_username,
        bot_name,
        bot_token,
    ):
        await self.clones.update_one(
            {
                "bot_id": int(bot_id)
            },
            {
                "$set": {
                    "owner_id": int(owner_id),
                    "bot_id": int(bot_id),
                    "bot_username": bot_username,
                    "bot_name": bot_name,
                    "bot_token": bot_token,
                    "status": "online",
                    "updated_at": datetime.now(),
                },
                "$setOnInsert": {
                    "created_at": datetime.now(),
                },
            },
            upsert=True,
        )

    async def get_clone(
        self,
        owner_id,
    ):
        return await self.clones.find_one(
            {
                "owner_id": int(owner_id)
            }
        )

    async def get_clone_by_bot_id(
        self,
        bot_id,
    ):
        return await self.clones.find_one(
            {
                "bot_id": int(bot_id)
            }
        )

    def get_all_clones(self):
        return self.clones.find({})

    async def set_clone_status(
        self,
        bot_id,
        status,
    ):
        await self.clones.update_one(
            {
                "bot_id": int(bot_id)
            },
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.now(),
                }
            },
        )

    async def remove_clone(
        self,
        bot_id,
    ):
        await self.clones.delete_one(
            {
                "bot_id": int(bot_id)
            }
        )


# ============================================================
# DATABASE INSTANCE
# ============================================================

db = Database(
    Config.DATABASE_URL,
    "AniToon_Promax_DB",
)

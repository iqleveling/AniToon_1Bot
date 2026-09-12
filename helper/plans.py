from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    stars: int
    daily_limit: int
    days: int = 30


GB = 1024 * 1024 * 1024


PLANS = {
    "free": Plan(
        key="free",
        name="🆓 Free",
        stars=0,
        daily_limit=10 * GB,
        days=0,
    ),
    "pro": Plan(
        key="pro",
        name="⚡ Pro",
        stars=10,
        daily_limit=20 * GB,
    ),
    "premium": Plan(
        key="premium",
        name="💎 Premium",
        stars=20,
        daily_limit=40 * GB,
    ),
    "ultra": Plan(
        key="ultra",
        name="👑 Ultra",
        stars=30,
        daily_limit=60 * GB,
    ),
}


def get_plan(plan_key: str) -> Plan:
    return PLANS.get(
        plan_key,
        PLANS["free"],
    )


def all_paid_plans():
    return [
        PLANS["pro"],
        PLANS["premium"],
        PLANS["ultra"],
    ]

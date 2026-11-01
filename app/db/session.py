import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.config import get_settings
from app.db.models import Admin, Base, BotSetting, Category

s = get_settings()
if s.db_url.startswith("sqlite"):
    os.makedirs("data", exist_ok=True)
engine = create_async_engine(s.db_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

SEED = [
    ("clients", "Minecraft Clients", "🎮", ["Apollon Client", "Atlas Client", "Unity Client", "Flarial Client", "WClient", "Other Clients"]),
    ("patches", "Minecraft Patches", "📦", ["Latest Minecraft Version", "64-bit", "32-bit", "With Music", "Without Music"]),
    ("textures", "Texture Packs", "🎨", ["PvP Texture Packs", "FPS Texture Packs", "Realistic Texture Packs", "Sky Textures", "Custom UI"]),
    ("fps", "FPS Boosters", "⚡", ["Nitrogen FPS Booster", "Performance Tools", "Optimization Packs"]),
    ("apk", "APK & Applications", "📱", ["Android Applications", "Minecraft Utilities", "Other APKs"]),
    ("tools", "Tools & Utilities", "🛠️", []),
]


async def init_db():
    """Dev convenience: create tables if missing. In production run `alembic upgrade head`."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        if (await db.execute(select(Category.id).limit(1))).first() is None:
            for i, (key, name, emoji, subs) in enumerate(SEED):
                parent = Category(key=key, name=name, emoji=emoji, sort=i)
                db.add(parent)
                await db.flush()
                for j, sub in enumerate(subs):
                    db.add(Category(parent_id=parent.id, name=sub, emoji="📂", sort=j))
        await db.commit()


async def get_setting(db, key: str, default: str = "") -> str:
    row = await db.get(BotSetting, key)
    return row.value if row else default


async def set_setting(db, key: str, value: str):
    row = await db.get(BotSetting, key)
    if row:
        row.value = value
    else:
        db.add(BotSetting(key=key, value=value))
    await db.commit()

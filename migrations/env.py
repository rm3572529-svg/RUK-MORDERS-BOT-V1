import asyncio
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import get_settings
from app.db.models import Base

target_metadata = Base.metadata
url = get_settings().db_url


def run_sync(conn):
    context.configure(connection=conn, target_metadata=target_metadata, compare_type=True,
                      render_as_batch=url.startswith("sqlite"))
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        await conn.run_sync(run_sync)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())

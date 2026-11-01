import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from app import state
from app.bot import account, files, search, start, verify
from app.bot.common import GuardMiddleware
from app.config import get_settings
from app.db.models import Admin, User
from app.db.session import SessionLocal, init_db
from app.logging_setup import setup_logging
from app.services.security import hash_password
from app.web.app import create_app

log = logging.getLogger("main")


async def bootstrap():
    s = get_settings()
    await init_db()
    async with SessionLocal() as db:
        a = await db.get(Admin, s.admin_id) or Admin(telegram_id=s.admin_id, name="Owner")
        a.role, a.password_hash = "super", hash_password(s.admin_panel_password)  # env is the source of truth
        db.add(a)
        await db.commit()
        state.BANNED.update((await db.execute(select(User.id).where(User.banned.is_(True)))).scalars().all())


async def main():
    setup_logging()
    s = get_settings()
    await bootstrap()
    session = AiohttpSession(api=TelegramAPIServer.from_base(s.local_bot_api_url, is_local=True)) if s.local_bot_api_url else None
    bot = Bot(s.bot_token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    guard = GuardMiddleware()
    dp.message.middleware(guard)
    dp.callback_query.middleware(guard)
    for r in (start.router, files.router, verify.router, account.router, search.router):  # search = catch-all, keep last
        dp.include_router(r)

    @dp.errors()
    async def on_error(event):
        log.exception("Unhandled error: %s", type(event.exception).__name__)
        return True

    server = uvicorn.Server(uvicorn.Config(create_app(bot), host="0.0.0.0", port=s.port, log_level="info",
                                           proxy_headers=True, forwarded_allow_ips="*"))
    await bot.delete_webhook()
    log.info("Starting bot + dashboard on :%s", s.port)
    tasks = [asyncio.create_task(dp.start_polling(bot, handle_signals=False)), asyncio.create_task(server.serve())]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for p in pending:
        p.cancel()
    await bot.session.close()
    for d in done:
        d.result()


if __name__ == "__main__":
    asyncio.run(main())

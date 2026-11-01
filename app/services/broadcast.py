import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbidden, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.db.models import Broadcast, User
from app.db.session import SessionLocal
from app.services.security import is_http_url

log = logging.getLogger("broadcast")


def parse_buttons(spec: str) -> InlineKeyboardMarkup | None:
    """One button per line: `Label | https://url`  or  `Label | cb:file:12`."""
    rows = []
    for line in (spec or "").splitlines():
        if "|" not in line:
            continue
        label, target = (x.strip() for x in line.split("|", 1))
        if not label:
            continue
        if is_http_url(target):
            rows.append([InlineKeyboardButton(text=label[:60], url=target)])
        elif target.startswith("cb:"):
            rows.append([InlineKeyboardButton(text=label[:60], callback_data=target[3:][:60])])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def run_broadcast(bot: Bot, bid: int):
    async with SessionLocal() as db:
        b = await db.get(Broadcast, bid)
        ids = (await db.execute(select(User.id).where(User.banned.is_(False), User.blocked_bot.is_(False)))).scalars().all()
        b.status = "sending"
        await db.commit()
        kb = parse_buttons(b.buttons)
        sent = failed = 0
        for uid in ids:
            try:
                for attempt in range(2):
                    try:
                        if b.media_kind == "photo":
                            await bot.send_photo(uid, b.media_file_id, caption=b.text[:1024], reply_markup=kb)
                        elif b.media_kind == "video":
                            await bot.send_video(uid, b.media_file_id, caption=b.text[:1024], reply_markup=kb)
                        else:
                            await bot.send_message(uid, b.text[:4000], reply_markup=kb)
                        sent += 1
                        break
                    except TelegramRetryAfter as e:
                        await asyncio.sleep(e.retry_after + 1)
            except TelegramForbidden:
                failed += 1
                u = await db.get(User, uid)
                if u:
                    u.blocked_bot = True
            except (TelegramBadRequest, Exception) as e:
                failed += 1
                log.warning("broadcast to %s failed: %s", uid, type(e).__name__)
            await asyncio.sleep(0.05)  # ~20 msg/s, below Telegram's global limit
        b.sent, b.failed, b.status = sent, failed, "done"
        await db.commit()


async def announce_file(bot: Bot, file, admin_id: int):
    async with SessionLocal() as db:
        b = Broadcast(text=f"🆕 <b>New file published!</b>\n\n📦 {file.name} {file.version}".strip(),
                      buttons=f"📥 Open | cb:file:{file.id}", created_by=admin_id)
        db.add(b)
        await db.commit()
        bid = b.id
    asyncio.create_task(run_broadcast(bot, bid))

import html
import time
from datetime import datetime, timezone

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app import state
from app.db.models import Category, User
from app.db.session import SessionLocal, get_setting
from app.i18n import t

PAGE = 8


class Flow(StatesGroup):
    search = State()
    ask = State()
    screenshot = State()


def btn(text: str, cb: str | None = None, url: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text[:60], callback_data=cb, url=url)


def markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def nav(lang: str, back: str | None = None) -> list[InlineKeyboardButton]:
    row = []
    if back:
        row.append(btn("⬅️ " + t(lang, "back"), back))
    row.append(btn("🏠 " + t(lang, "home"), "home"))
    return row


def fmt_size(n: int) -> str:
    if not n:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


def esc(x) -> str:
    return html.escape(str(x or ""))


def fdate(d: datetime | None) -> str:
    return d.strftime("%d %b %Y") if d else "—"


async def upsert_user(db, tg) -> User:
    u = await db.get(User, tg.id)
    if not u:
        u = User(id=tg.id)
        db.add(u)
    u.username, u.first_name, u.last_seen = tg.username, (tg.first_name or "")[:128], datetime.now(timezone.utc)
    await db.commit()
    return u


async def render(ev, text: str, kb: InlineKeyboardMarkup | None = None):
    """Edit the current message if possible, otherwise send a fresh one."""
    if isinstance(ev, CallbackQuery):
        m = ev.message
        try:
            if m.photo or m.document or m.video:
                await m.delete()
                await m.answer(text, reply_markup=kb)
            else:
                await m.edit_text(text, reply_markup=kb)
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                await m.answer(text, reply_markup=kb)
        await ev.answer()
    else:
        await ev.answer(text, reply_markup=kb)


async def main_menu(lang: str, db) -> InlineKeyboardMarkup:
    roots = (await db.execute(select(Category).where(Category.parent_id.is_(None)).order_by(Category.sort, Category.id))).scalars().all()
    buttons = []
    for c in roots:
        label = t(lang, f"m_{c.key}") if c.key else c.name
        buttons.append(btn(f"{c.emoji} {label}", f"cat:{c.id}:0"))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([btn("🔍 " + t(lang, "m_search"), "search")])
    rows.append([btn("❤️ " + t(lang, "m_support"), "support")])
    rows.append([btn("👤 " + t(lang, "m_account"), "acct"), btn("⚙️ " + t(lang, "m_settings"), "settings")])
    return markup(rows)


async def send_home(ev, lang: str, db):
    name = ev.from_user.first_name if ev.from_user else ""
    text = t(lang, "welcome_msg", welcome=t(lang, "welcome"), name=esc(name))
    await render(ev, text, await main_menu(lang, db))


async def verified_ok(db, user: User) -> bool:
    api_only = await get_setting(db, "api_required", "0") == "1"
    return user.verification_status == "api" or (user.verification_status == "visual" and not api_only)


class GuardMiddleware(BaseMiddleware):
    """Rate limiting + ban check for every message/callback."""

    def __init__(self, limit: int = 15, window: float = 10.0):
        self.limit, self.window, self.hits = limit, window, {}

    async def __call__(self, handler, event, data):
        u = data.get("event_from_user")
        if u:
            if u.id in state.BANNED:
                return await self._say(event, t(None, "banned"))
            now = time.monotonic()
            q = [x for x in self.hits.get(u.id, []) if now - x < self.window]
            if len(q) >= self.limit:
                return await self._say(event, t(None, "too_fast"))
            q.append(now)
            self.hits[u.id] = q
            if len(self.hits) > 5000:
                self.hits.clear()
        return await handler(event, data)

    @staticmethod
    async def _say(event, text):
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=False)
        elif isinstance(event, Message):
            await event.answer(text)

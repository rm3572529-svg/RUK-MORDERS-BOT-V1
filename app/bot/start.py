from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Admin
from app.db.session import SessionLocal, get_setting
from app.i18n import ALL_LANGS, LANGS, MORE_LANGS, t
from app.bot.common import btn, markup, render, send_home, upsert_user

router = Router()


async def lang_keyboard(db, more: bool = False):
    enabled = (await get_setting(db, "enabled_langs", "")).split(",")
    pool = MORE_LANGS if more else LANGS
    items = [(c, n) for c, n in pool.items() if not enabled[0] or c in enabled]
    rows = [[btn(n, f"lang:{c}") for c, n in items[i:i + 2]] for i in range(0, len(items), 2)]
    rows.append([btn("⬅️ " + LANGS["en"], "langmore:0")] if more else [btn(t(None, "more_langs"), "langmore:1")])
    return markup(rows)


@router.message(Command("start"))
async def start(m: Message, state: FSMContext):
    await state.clear()
    async with SessionLocal() as db:
        u = await upsert_user(db, m.from_user)
        if not u.language:
            await m.answer("👋 <b>Welcome to RUK MODERS GANG!</b>\n\n" + t("en", "pick_lang"),
                           reply_markup=await lang_keyboard(db))
            return
        await send_home(m, u.language, db)


@router.callback_query(F.data.startswith("langmore:"))
async def more(cb: CallbackQuery):
    async with SessionLocal() as db:
        await render(cb, t("en", "pick_lang"), await lang_keyboard(db, cb.data.endswith("1")))


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(cb: CallbackQuery):
    code = cb.data.split(":")[1]
    if code not in ALL_LANGS:
        return await cb.answer()
    async with SessionLocal() as db:
        u = await upsert_user(db, cb.from_user)
        u.language = code
        await db.commit()
        await send_home(cb, code, db)


@router.callback_query(F.data == "home")
async def home(cb: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    async with SessionLocal() as db:
        u = await upsert_user(db, cb.from_user)
        if not u.language:
            return await render(cb, t("en", "pick_lang"), await lang_keyboard(db))
        await send_home(cb, u.language, db)


@router.message(Command("admin"))
async def admin_link(m: Message):
    async with SessionLocal() as db:
        a = (await db.execute(select(Admin).where(Admin.telegram_id == m.from_user.id))).scalar_one_or_none()
    if a:  # ordinary users get no response at all
        await m.answer(f"🔐 Dashboard: {get_settings().public_base_url}/admin\nRole: <b>{a.role}</b>")

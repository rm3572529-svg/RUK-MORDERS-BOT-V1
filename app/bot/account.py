from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.common import Flow, btn, esc, fdate, markup, nav, render, upsert_user
from app.bot.start import lang_keyboard
from app.config import get_settings
from app.db.models import File
from app.db.session import SessionLocal, get_setting
from app.i18n import ALL_LANGS, t
from app.services.ai import AIError, AIService
from app.services.security import looks_spammy

router = Router()
VSTATUS = {"none": "❌ Not verified", "visual": "🟡 Screenshot-verified", "api": "✅ Confirmed via YouTube API"}


@router.callback_query(F.data == "acct")
async def account(cb: CallbackQuery):
    async with SessionLocal() as db:
        u = await upsert_user(db, cb.from_user)
    lang = u.language or "en"
    text = (f"👤 <b>{t(lang, 'm_account')}</b>\n\n🆔 <code>{u.id}</code>\n"
            f"🔖 @{esc(u.username) if u.username else '—'}\n🙋 {esc(u.first_name)}\n"
            f"🌍 {ALL_LANGS.get(u.language, '—')}\n📅 {fdate(u.joined_at)}\n"
            f"📥 Downloads: <b>{u.total_downloads}</b>\n🛡 {VSTATUS.get(u.verification_status, '—')}")
    await render(cb, text, markup([nav(lang)]))


@router.callback_query(F.data == "settings")
async def settings(cb: CallbackQuery):
    async with SessionLocal() as db:
        lang = (await upsert_user(db, cb.from_user)).language or "en"
    await render(cb, t(lang, "settings_title"), markup([[btn(t(lang, "change_lang"), "setlang")], nav(lang)]))


@router.callback_query(F.data == "setlang")
async def setlang(cb: CallbackQuery):
    async with SessionLocal() as db:
        await render(cb, t("en", "pick_lang"), await lang_keyboard(db))


@router.callback_query(F.data == "support")
async def support(cb: CallbackQuery):
    s = get_settings()
    async with SessionLocal() as db:
        lang = (await upsert_user(db, cb.from_user)).language or "en"
    rows = [[btn("▶️ Subscribe to YouTube", url=s.youtube_url)],
            [btn("📢 Join WhatsApp Channel", url=s.whatsapp_url)],
            [btn(t(lang, "ask_ai"), "ask")], nav(lang)]
    await render(cb, t(lang, "support_title"), markup(rows))


@router.callback_query(F.data == "ask")
async def ask(cb: CallbackQuery, state: FSMContext):
    async with SessionLocal() as db:
        lang = (await upsert_user(db, cb.from_user)).language or "en"
    if not AIService().enabled:
        return await render(cb, t(lang, "ai_unavailable"), markup([nav(lang, "support")]))
    await state.set_state(Flow.ask)
    await render(cb, t(lang, "ask_ai_prompt"), markup([nav(lang, "support")]))


@router.message(Flow.ask, F.text, ~F.text.startswith("/"))
async def answer(m: Message, state: FSMContext):
    text = m.text.strip()[:500]
    async with SessionLocal() as db:
        lang = (await upsert_user(db, m.from_user)).language or "en"
        if looks_spammy(text):
            return await m.answer("🚫 Please ask a normal question.")
        overrides = {k: await get_setting(db, k) for k in ("ai_provider", "ai_model", "ai_base_url")}
        ai = AIService(overrides)
        names = (await db.execute(select(File.name, File.version).where(File.published.is_(True)).limit(40))).all()
    catalog = "; ".join(f"{n} {v}".strip() for n, v in names)
    try:
        if len(text) > 80 and await ai.is_spam(text):
            return await m.answer("🚫 Message looks like spam.")
        reply = await ai.assist(text, lang, catalog)
    except (AIError, ValueError):
        reply = t(lang, "error")
    await m.answer(reply[:3500], reply_markup=markup([nav(lang, "support")]), parse_mode=None)

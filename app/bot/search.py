from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.common import PAGE, Flow, btn, markup, nav, render, upsert_user
from app.db.session import SessionLocal, get_setting
from app.i18n import t
from app.services.ai import AIError, AIService
from app.services.search import search_files, terms_of
from app.services.security import looks_spammy

router = Router()


def results_view(files, page: int, lang: str):
    pages = max(1, -(-len(files) // PAGE))
    chunk = files[page * PAGE:(page + 1) * PAGE]
    rows = [[btn(f"📦 {f.name} {f.version}".strip(), f"file:{f.id}")] for f in chunk]
    if pages > 1:
        pr = []
        if page > 0:
            pr.append(btn("◀️", f"sr:{page - 1}"))
        pr.append(btn(t(lang, "page", p=page + 1, n=pages), "noop"))
        if page + 1 < pages:
            pr.append(btn("▶️", f"sr:{page + 1}"))
        rows.append(pr)
    rows.append(nav(lang))
    return f"🔍 <b>{len(files)}</b> result(s)", markup(rows)


@router.callback_query(F.data == "search")
async def ask(cb: CallbackQuery, state: FSMContext):
    async with SessionLocal() as db:
        lang = (await upsert_user(db, cb.from_user)).language or "en"
    await state.set_state(Flow.search)
    await render(cb, t(lang, "search_prompt"), markup([nav(lang)]))


async def _find(db, text: str):
    files = await search_files(db, terms_of(text))
    if not files:  # multilingual / natural-language fallback via AI
        overrides = {k: await get_setting(db, k) for k in ("ai_provider", "ai_model", "ai_base_url")}
        ai = AIService(overrides)
        if ai.enabled:
            try:
                files = await search_files(db, [k.lower() for k in await ai.expand_query(text)])
            except (AIError, ValueError):
                pass
    return files


@router.message(StateFilter(None, Flow.search), F.text, ~F.text.startswith("/"))
async def do_search(m: Message, state: FSMContext):
    text = m.text.strip()[:200]
    async with SessionLocal() as db:
        lang = (await upsert_user(db, m.from_user)).language or "en"
        if looks_spammy(text):
            return await m.answer("🚫 Please send a normal search term.")
        files = await _find(db, text)
    await state.set_state(None)
    if not files:
        return await m.answer(t(lang, "no_results"), reply_markup=markup([nav(lang)]))
    await state.update_data(ids=[f.id for f in files])
    title, kb = results_view(files, 0, lang)
    await m.answer(title, reply_markup=kb)


@router.callback_query(F.data.startswith("sr:"))
async def page(cb: CallbackQuery, state: FSMContext):
    from sqlalchemy import select
    from app.db.models import File
    ids = (await state.get_data()).get("ids")
    async with SessionLocal() as db:
        lang = (await upsert_user(db, cb.from_user)).language or "en"
        if not ids:
            return await render(cb, t(lang, "search_prompt"), markup([nav(lang)]))
        rows = (await db.execute(select(File).where(File.id.in_(ids), File.published.is_(True)))).scalars().all()
    order = {i: n for n, i in enumerate(ids)}
    files = sorted(rows, key=lambda f: order[f.id])
    title, kb = results_view(files, int(cb.data.split(":")[1]), lang)
    await render(cb, title, kb)

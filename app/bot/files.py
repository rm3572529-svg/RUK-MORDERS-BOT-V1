from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import func, select, update

from app.bot.common import PAGE, btn, esc, fdate, fmt_size, markup, nav, render, upsert_user, verified_ok
from app.config import get_settings
from app.db.models import Category, Download, File, User
from app.db.session import SessionLocal, get_setting
from app.i18n import t

router = Router()


@router.callback_query(F.data.startswith("cat:"))
async def category(cb: CallbackQuery):
    _, cid, page = cb.data.split(":")
    page = int(page)
    async with SessionLocal() as db:
        u = await upsert_user(db, cb.from_user)
        lang = u.language or "en"
        cat = await db.get(Category, int(cid))
        if not cat:
            return await cb.answer()
        total = (await db.execute(select(func.count()).select_from(File).where(
            File.category_id == cat.id, File.published.is_(True)))).scalar_one()
        files = (await db.execute(select(File).where(File.category_id == cat.id, File.published.is_(True))
                                  .order_by(File.created_at.desc()).offset(page * PAGE).limit(PAGE))).scalars().all()
        subs = sorted(cat.children, key=lambda c: (c.sort, c.id)) if page == 0 else []
        rows = [[btn(f"{c.emoji} {c.name}", f"cat:{c.id}:0")] for c in subs]
        rows += [[btn(f"📦 {f.name} {f.version}".strip(), f"file:{f.id}")] for f in files]
        pages = max(1, -(-total // PAGE))
        if pages > 1:
            pr = []
            if page > 0:
                pr.append(btn("◀️", f"cat:{cat.id}:{page - 1}"))
            pr.append(btn(t(lang, "page", p=page + 1, n=pages), "noop"))
            if page + 1 < pages:
                pr.append(btn("▶️", f"cat:{cat.id}:{page + 1}"))
            rows.append(pr)
        rows.append(nav(lang, f"cat:{cat.parent_id}:0" if cat.parent_id else None))
        title = f"{cat.emoji} <b>{esc(cat.name)}</b>"
        body = "" if (subs or files) else "\n\n" + t(lang, "empty")
        await render(cb, title + body, markup(rows))


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()


def file_text(f: File, lang: str, locked: bool) -> str:
    parts = [f"📦 <b>{esc(f.name)}</b>"]
    if f.version:
        parts.append(f"📌 <b>Version:</b> {esc(f.version)}")
    if f.architecture:
        parts.append(f"📱 <b>Architecture:</b> {esc(f.architecture)}")
    parts.append(f"💾 <b>Size:</b> {fmt_size(f.size_bytes)}")
    if f.description:
        parts.append(f"\n📝 {esc(f.description)[:500]}")
    if f.changelog:
        parts.append(f"\n🆕 <b>Changelog</b>\n{esc(f.changelog)[:300]}")
    parts.append(f"\n📅 <b>Uploaded:</b> {fdate(f.created_at)}")
    if locked:
        parts.append("🔒 <i>Subscribe to our YouTube channel to unlock this download.</i>")
    return "\n".join(parts)[:1000]


@router.callback_query(F.data.startswith("file:"))
async def file_view(cb: CallbackQuery):
    async with SessionLocal() as db:
        u = await upsert_user(db, cb.from_user)
        lang = u.language or "en"
        f = await db.get(File, int(cb.data.split(":")[1]))
        if not f or not f.published:
            return await render(cb, t(lang, "not_found"), markup([nav(lang)]))
        need = f.restricted and await get_setting(db, "verification_required", "1") == "1"
        locked = need and not await verified_ok(db, u)
        rows = [[btn("📥 " + t(lang, "download"), f"dl:{f.id}")]]
        if f.youtube_url:
            rows.append([btn("▶️ Tutorial", url=f.youtube_url)])
        rows.append(nav(lang, f"cat:{f.category_id}:0" if f.category_id else None))
        text = file_text(f, lang, locked)
        if f.thumbnail_file_id:
            try:
                await cb.message.delete()
            except Exception:
                pass
            await cb.message.answer_photo(f.thumbnail_file_id, caption=text, reply_markup=markup(rows))
            await cb.answer()
        else:
            await render(cb, text, markup(rows))


@router.callback_query(F.data.startswith("dl:"))
async def download(cb: CallbackQuery):
    from app.bot.verify import verify_screen
    async with SessionLocal() as db:
        u = await upsert_user(db, cb.from_user)
        lang = u.language or "en"
        f = await db.get(File, int(cb.data.split(":")[1]))
        if not f or not f.published:
            return await render(cb, t(lang, "not_found"), markup([nav(lang)]))
        need = f.restricted and await get_setting(db, "verification_required", "1") == "1"
        if need and not await verified_ok(db, u):
            return await verify_screen(cb, lang, f.id)
        await cb.answer("📥 Sending…")
        sent = False
        for a in f.assets:
            await cb.message.answer_document(a.tg_file_id, caption=f"📦 {esc(f.name)} {esc(f.version)}")
            sent = True
        if f.external_url:
            await cb.message.answer(f"🔗 <b>{esc(f.name)}</b>", reply_markup=markup([[btn("⬇️ " + t(lang, "download"), url=f.external_url)]]))
            sent = True
        if not sent:
            return await cb.message.answer(t(lang, "not_found"))
        db.add(Download(user_id=u.id, file_id=f.id))
        f.download_count += 1
        u.total_downloads += 1
        await db.commit()
        await cb.message.answer("✅ Done!", reply_markup=markup([nav(lang, f"cat:{f.category_id}:0" if f.category_id else None)]))

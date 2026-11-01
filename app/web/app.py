import asyncio
import hmac
import logging
import os
import secrets
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

import httpx
from aiogram import Bot
from aiogram.types import FSInputFile
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import delete, func, select
from starlette.middleware.sessions import SessionMiddleware

from app import state
from app.config import get_settings
from app.db.models import (Admin, Broadcast, Category, Download, File, FileAsset, User, Verification)
from app.db.session import SessionLocal, get_setting, set_setting
from app.i18n import ALL_LANGS, TABLE
from app.services.ai import AIError, AIService
from app.services.broadcast import announce_file, run_broadcast
from app.services.security import (ALLOWED_EXT, IMAGE_EXT, VIDEO_EXT, clean, ext_of, hash_password,
                                   is_http_url, safe_filename, verify_password)

log = logging.getLogger("web")
BASE = Path(__file__).parent
ROLE = {"moderator": 1, "admin": 2, "super": 3}
NAV = [("/admin", "📊 Overview", 1), ("/admin/files", "📁 Files", 1), ("/admin/categories", "📂 Categories", 2),
       ("/admin/files/new", "📤 Upload", 2), ("/admin/users", "👥 Users", 1), ("/admin/ai", "🤖 AI", 3),
       ("/admin/verifications", "📸 Verifications", 1), ("/admin/broadcast", "📢 Broadcast", 2),
       ("/admin/stats", "📈 Stats", 2), ("/admin/languages", "🌍 Languages", 2),
       ("/admin/settings", "⚙️ Settings", 2), ("/admin/admins", "🔐 Admins", 3)]
_fails: dict[str, list[float]] = {}


def go(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def flash(request: Request, msg: str, kind: str = "ok"):
    request.session["flash"] = [kind, msg]


def create_app(bot: Bot) -> FastAPI:
    s = get_settings()
    app = FastAPI(title="RUK MODERS GANG Admin", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SessionMiddleware, secret_key=s.secret_key, same_site="strict", max_age=8 * 3600,
                       https_only=s.public_base_url.startswith("https"), session_cookie="rmg_admin")
    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
    tpl = Jinja2Templates(directory=BASE / "templates")

    # ---------- helpers ----------
    async def guard(request: Request, level: str = "moderator"):
        aid = request.session.get("aid")
        if not aid:
            raise HTTPException(303, headers={"Location": "/admin/login"})
        async with SessionLocal() as db:
            admin = await db.get(Admin, aid)
        if not admin or ROLE.get(admin.role, 0) < ROLE[level]:
            raise HTTPException(403, "Forbidden")
        form = None
        if request.method == "POST":
            form = await request.form()
            if not hmac.compare_digest(str(form.get("csrf", "")), request.session.get("csrf", "x")):
                raise HTTPException(403, "Bad CSRF token")
        return admin, form

    def page(request: Request, name: str, admin: Admin | None, **ctx):
        fl = request.session.pop("flash", None)
        nav = [(u, l) for u, l, lv in NAV if admin and ROLE[admin.role] >= lv]
        return tpl.TemplateResponse(request, name, {"admin": admin, "nav": nav, "flash": fl,
                                                    "csrf": request.session.get("csrf", ""), **ctx})

    async def store_upload(up, kind: str):
        name = safe_filename(up.filename)
        ext = ext_of(name)
        if ext not in ALLOWED_EXT:
            raise ValueError(f"File type '{ext or '?'}' is not allowed")
        if kind in ("thumb", "media-image") and ext not in IMAGE_EXT:
            raise ValueError("This field needs an image (png/jpg/webp)")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        try:
            await run_in_threadpool(shutil.copyfileobj, up.file, tmp)
            tmp.close()
            size = os.path.getsize(tmp.name)
            if size > s.max_upload_mb * 1024 * 1024:
                raise ValueError(f"{name}: larger than {s.max_upload_mb} MB limit (see LOCAL_BOT_API_URL)")
            inp = FSInputFile(tmp.name, filename=name)
            if ext in IMAGE_EXT and kind != "asset":
                m = await bot.send_photo(s.storage_chat, inp)
                return m.photo[-1].file_id, name, size, "photo"
            if ext in VIDEO_EXT and kind == "media":
                m = await bot.send_video(s.storage_chat, inp)
                return m.video.file_id, name, size, "video"
            m = await bot.send_document(s.storage_chat, inp)
            return m.document.file_id, name, size, "document"
        finally:
            tmp.close()
            os.unlink(tmp.name)

    def has_file(x) -> bool:
        return hasattr(x, "filename") and bool(x.filename)

    async def cat_choices(db):
        cats = (await db.execute(select(Category).order_by(Category.sort, Category.id))).scalars().all()
        by = {c.id: c for c in cats}
        return [(c.id, (f"{by[c.parent_id].name} › " if c.parent_id in by else "") + c.name) for c in cats]

    # ---------- public ----------
    @app.get("/healthz")
    async def health():
        return {"ok": True}

    @app.get("/")
    async def root():
        return go("/admin")

    # ---------- auth ----------
    @app.get("/admin/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return page(request, "login.html", None)

    @app.post("/admin/login")
    async def login(request: Request):
        ip = request.client.host if request.client else "?"
        now = time.time()
        _fails[ip] = [t for t in _fails.get(ip, []) if now - t < 600]
        if len(_fails[ip]) >= 5:
            flash(request, "Too many attempts. Try again in 10 minutes.", "err")
            return go("/admin/login")
        form = await request.form()
        try:
            tid = int(str(form.get("telegram_id", "")).strip())
        except ValueError:
            tid = 0
        async with SessionLocal() as db:
            admin = await db.get(Admin, tid)
        ok = bool(admin) and verify_password(str(form.get("password", "")), admin.password_hash)
        if not ok:
            _fails[ip].append(now)
            flash(request, "Invalid credentials.", "err")
            return go("/admin/login")
        request.session.clear()
        request.session["aid"] = admin.telegram_id
        request.session["csrf"] = secrets.token_urlsafe(24)
        return go("/admin")

    @app.post("/admin/logout")
    async def logout(request: Request):
        request.session.clear()
        return go("/admin/login")

    # ---------- overview ----------
    @app.get("/admin", response_class=HTMLResponse)
    async def overview(request: Request):
        admin, _ = await guard(request)
        async with SessionLocal() as db:
            c = lambda q: db.scalar(q)  # noqa: E731
            day = datetime.now(timezone.utc) - timedelta(days=1)
            data = {
                "users": await c(select(func.count()).select_from(User)),
                "files": await c(select(func.count()).select_from(File)),
                "published": await c(select(func.count()).select_from(File).where(File.published.is_(True))),
                "downloads": await c(select(func.count()).select_from(Download)),
                "downloads24": await c(select(func.count()).select_from(Download).where(Download.created_at >= day)),
                "pending": await c(select(func.count()).select_from(Verification).where(Verification.result.in_(["review", "unavailable"]))),
                "verified": await c(select(func.count()).select_from(User).where(User.verification_status != "none")),
            }
        return page(request, "overview.html", admin, d=data)

    # ---------- files ----------
    @app.get("/admin/files", response_class=HTMLResponse)
    async def files(request: Request):
        admin, _ = await guard(request)
        q = request.query_params.get("q", "").strip()[:80]
        async with SessionLocal() as db:
            stmt = select(File).order_by(File.created_at.desc()).limit(200)
            if q:
                stmt = select(File).where(File.name.ilike(f"%{q}%")).order_by(File.created_at.desc()).limit(200)
            rows = (await db.execute(stmt)).scalars().all()
        return page(request, "files.html", admin, files=rows, q=q)

    @app.get("/admin/files/new", response_class=HTMLResponse)
    async def file_new(request: Request):
        admin, _ = await guard(request, "admin")
        async with SessionLocal() as db:
            cats = await cat_choices(db)
        return page(request, "file_form.html", admin, f=None, cats=cats, max_mb=s.max_upload_mb)

    @app.get("/admin/files/{fid}/edit", response_class=HTMLResponse)
    async def file_edit(request: Request, fid: int):
        admin, _ = await guard(request, "admin")
        async with SessionLocal() as db:
            f = await db.get(File, fid)
            if not f:
                raise HTTPException(404)
            cats = await cat_choices(db)
        return page(request, "file_form.html", admin, f=f, cats=cats, max_mb=s.max_upload_mb)

    @app.post("/admin/files/save")
    async def file_save(request: Request):
        admin, form = await guard(request, "admin")
        g = lambda k, n=500: clean(str(form.get(k, "")), n)  # noqa: E731
        name = g("name", 200)
        if not name:
            flash(request, "Name is required.", "err")
            return go(request.headers.get("referer", "/admin/files/new"))
        for k in ("youtube_url", "external_url"):
            if g(k) and not is_http_url(g(k)):
                flash(request, f"{k} must start with http:// or https://", "err")
                return go(request.headers.get("referer", "/admin/files/new"))
        try:
            cid = int(g("category_id") or 0) or None
        except ValueError:
            cid = None
        async with SessionLocal() as db:
            fid = int(g("id") or 0)
            f = await db.get(File, fid) if fid else File()
            if fid and not f:
                raise HTTPException(404)
            was_published = bool(f.published) if fid else False
            if cid and not await db.get(Category, cid):
                cid = None
            f.name, f.version, f.architecture = name, g("version", 50), g("architecture", 100)
            f.description, f.changelog, f.aliases = g("description", 2000), g("changelog", 2000), g("aliases", 1000)
            f.youtube_url, f.external_url, f.category_id = g("youtube_url"), g("external_url"), cid
            f.restricted = form.get("restricted") == "on"
            f.published = form.get("publish") == "on"
            if not fid:
                db.add(f)
            await db.flush()
            errors = []
            thumb = form.get("thumb")
            if has_file(thumb):
                try:
                    f.thumbnail_file_id = (await store_upload(thumb, "thumb"))[0]
                except Exception as e:  # noqa: BLE001
                    errors.append(f"thumbnail: {e}")
            for up in form.getlist("files"):
                if has_file(up):
                    try:
                        tg_id, fname, size, _ = await store_upload(up, "asset")
                        db.add(FileAsset(file_id=f.id, tg_file_id=tg_id, file_name=fname, size=size))
                    except Exception as e:  # noqa: BLE001
                        errors.append(f"{up.filename}: {e}")
            if g("tg_file_id", 300):
                db.add(FileAsset(file_id=f.id, tg_file_id=g("tg_file_id", 300), file_name=g("tg_file_name", 200) or "file", size=0))
            await db.commit()
            n_assets = await db.scalar(select(func.count()).select_from(FileAsset).where(FileAsset.file_id == f.id))
            if f.published and not n_assets and not f.external_url:
                f.published = False
                await db.commit()
                errors.append("Not published: add at least one file or a download link.")
            if f.published and not was_published and form.get("notify") == "on":
                await announce_file(bot, f, admin.telegram_id)
        flash(request, "Saved." + ("  ⚠️ " + " | ".join(errors) if errors else ""), "err" if errors else "ok")
        return go(f"/admin/files/{f.id}/edit")

    @app.post("/admin/files/{fid}/toggle")
    async def file_toggle(request: Request, fid: int):
        await guard(request, "admin")
        async with SessionLocal() as db:
            f = await db.get(File, fid)
            if f:
                if not f.published and not f.assets and not f.external_url:
                    flash(request, "Add a file or link before publishing.", "err")
                else:
                    f.published = not f.published
                    await db.commit()
        return go("/admin/files")

    @app.post("/admin/files/{fid}/delete")
    async def file_delete(request: Request, fid: int):
        await guard(request, "admin")
        async with SessionLocal() as db:
            await db.execute(delete(Download).where(Download.file_id == fid))
            f = await db.get(File, fid)
            if f:
                await db.delete(f)
            await db.commit()
        flash(request, "File deleted.")
        return go("/admin/files")

    @app.post("/admin/assets/{aid}/delete")
    async def asset_delete(request: Request, aid: int):
        await guard(request, "admin")
        async with SessionLocal() as db:
            a = await db.get(FileAsset, aid)
            fid = a.file_id if a else 0
            if a:
                await db.delete(a)
                await db.commit()
        return go(f"/admin/files/{fid}/edit")

    # ---------- categories ----------
    @app.get("/admin/categories", response_class=HTMLResponse)
    async def categories(request: Request):
        admin, _ = await guard(request, "admin")
        async with SessionLocal() as db:
            cats = (await db.execute(select(Category).where(Category.parent_id.is_(None)).order_by(Category.sort, Category.id))).scalars().all()
        return page(request, "categories.html", admin, cats=cats)

    @app.post("/admin/categories/add")
    async def cat_add(request: Request):
        _, form = await guard(request, "admin")
        name = clean(str(form.get("name", "")), 100)
        if name:
            async with SessionLocal() as db:
                pid = int(form.get("parent_id") or 0) or None
                db.add(Category(name=name, emoji=clean(str(form.get("emoji", "")), 8) or "📁", parent_id=pid,
                                sort=int(form.get("sort") or 0)))
                await db.commit()
        return go("/admin/categories")

    @app.post("/admin/categories/{cid}/save")
    async def cat_save(request: Request, cid: int):
        _, form = await guard(request, "admin")
        async with SessionLocal() as db:
            c = await db.get(Category, cid)
            if c:
                c.name = clean(str(form.get("name", "")), 100) or c.name
                c.emoji = clean(str(form.get("emoji", "")), 8) or c.emoji
                c.sort = int(form.get("sort") or 0)
                await db.commit()
        return go("/admin/categories")

    @app.post("/admin/categories/{cid}/delete")
    async def cat_delete(request: Request, cid: int):
        await guard(request, "admin")
        async with SessionLocal() as db:
            c = await db.get(Category, cid)
            if c:
                await db.delete(c)
                await db.commit()
        return go("/admin/categories")

    # ---------- users ----------
    @app.get("/admin/users", response_class=HTMLResponse)
    async def users(request: Request):
        admin, _ = await guard(request)
        q = request.query_params.get("q", "").strip()[:60]
        pg = int(request.query_params.get("p", "0")) if request.query_params.get("p", "0").isdigit() else 0
        async with SessionLocal() as db:
            stmt = select(User).order_by(User.joined_at.desc())
            if q.isdigit():
                stmt = stmt.where(User.id == int(q))
            elif q:
                stmt = stmt.where(User.username.ilike(f"%{q.lstrip('@')}%") | User.first_name.ilike(f"%{q}%"))
            rows = (await db.execute(stmt.offset(pg * 50).limit(50))).scalars().all()
        return page(request, "users.html", admin, users=rows, q=q, p=pg, langs=ALL_LANGS)

    @app.post("/admin/users/{uid}/{action}")
    async def user_action(request: Request, uid: int, action: str):
        admin, _ = await guard(request, "admin")
        async with SessionLocal() as db:
            u = await db.get(User, uid)
            if u:
                if action == "ban":
                    u.banned = True
                    state.BANNED.add(uid)
                elif action == "unban":
                    u.banned = False
                    state.BANNED.discard(uid)
                elif action == "verify":
                    u.verification_status = "visual"
                elif action == "unverify":
                    u.verification_status = "none"
                await db.commit()
        return go(request.headers.get("referer", "/admin/users"))

    # ---------- verifications ----------
    @app.get("/admin/verifications", response_class=HTMLResponse)
    async def verifications(request: Request):
        admin, _ = await guard(request)
        flt = request.query_params.get("r", "")
        async with SessionLocal() as db:
            stmt = select(Verification).order_by(Verification.created_at.desc()).limit(100)
            if flt:
                stmt = select(Verification).where(Verification.result == flt).order_by(Verification.created_at.desc()).limit(100)
            rows = (await db.execute(stmt)).scalars().all()
        return page(request, "verifications.html", admin, rows=rows, flt=flt)

    @app.get("/admin/shot/{vid}")
    async def shot(request: Request, vid: int):
        await guard(request)
        async with SessionLocal() as db:
            v = await db.get(Verification, vid)
        if not v or not v.screenshot_file_id:
            raise HTTPException(404)
        buf = BytesIO()
        await bot.download(v.screenshot_file_id, destination=buf)
        return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})

    @app.post("/admin/verifications/{vid}/{decision}")
    async def review(request: Request, vid: int, decision: str):
        await guard(request)
        async with SessionLocal() as db:
            v = await db.get(Verification, vid)
            u = await db.get(User, v.user_id) if v else None
            if v and u and decision in ("approve", "reject"):
                v.result = "pass" if decision == "approve" else "fail"
                v.method = "manual" if v.method == "screenshot" else v.method
                if decision == "approve" and u.verification_status == "none":
                    u.verification_status = "visual"
                await db.commit()
                try:
                    await bot.send_message(u.id, "✅ Your subscription was approved. You can download now!" if decision == "approve"
                                           else "❌ Your screenshot was rejected. Please upload a clearer, unedited screenshot.")
                except Exception:  # noqa: BLE001
                    pass
        return go("/admin/verifications")

    # ---------- broadcast ----------
    @app.get("/admin/broadcast", response_class=HTMLResponse)
    async def broadcast_page(request: Request):
        admin, _ = await guard(request, "admin")
        async with SessionLocal() as db:
            rows = (await db.execute(select(Broadcast).order_by(Broadcast.created_at.desc()).limit(30))).scalars().all()
        return page(request, "broadcast.html", admin, rows=rows)

    @app.post("/admin/broadcast/send")
    async def broadcast_send(request: Request):
        admin, form = await guard(request, "admin")
        text = clean(str(form.get("text", "")), 4000)
        media = form.get("media")
        kind, fid = "", ""
        if has_file(media):
            try:
                fid, _, _, kind = await store_upload(media, "media")
                if kind == "document":
                    raise ValueError("Use an image or mp4 video")
            except Exception as e:  # noqa: BLE001
                flash(request, f"Media error: {e}", "err")
                return go("/admin/broadcast")
        if not text and not fid:
            flash(request, "Write a message or attach media.", "err")
            return go("/admin/broadcast")
        async with SessionLocal() as db:
            b = Broadcast(text=text, media_kind=kind, media_file_id=fid, buttons=clean(str(form.get("buttons", "")), 1000),
                          created_by=admin.telegram_id)
            db.add(b)
            await db.commit()
            bid = b.id
        asyncio.create_task(run_broadcast(bot, bid))
        flash(request, "Broadcast started.")
        return go("/admin/broadcast")

    # ---------- stats ----------
    @app.get("/admin/stats", response_class=HTMLResponse)
    async def stats(request: Request):
        admin, _ = await guard(request, "admin")
        since = datetime.now(timezone.utc) - timedelta(days=14)
        async with SessionLocal() as db:
            ds = (await db.execute(select(Download.created_at).where(Download.created_at >= since))).scalars().all()
            top = (await db.execute(select(File.name, File.version, File.download_count).order_by(File.download_count.desc()).limit(10))).all()
            langs = (await db.execute(select(User.language, func.count()).group_by(User.language))).all()
        per = {}
        for d in ds:
            per[d.strftime("%Y-%m-%d")] = per.get(d.strftime("%Y-%m-%d"), 0) + 1
        days = [((datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")) for i in range(13, -1, -1)]
        series = [(d, per.get(d, 0)) for d in days]
        return page(request, "stats.html", admin, series=series, mx=max([n for _, n in series] + [1]), top=top, langs=langs)

    # ---------- languages / settings ----------
    @app.get("/admin/languages", response_class=HTMLResponse)
    async def languages(request: Request):
        admin, _ = await guard(request, "admin")
        async with SessionLocal() as db:
            en = (await get_setting(db, "enabled_langs", "")).split(",")
        return page(request, "languages.html", admin, langs=ALL_LANGS, enabled=en, translated=set(TABLE))

    @app.post("/admin/languages")
    async def languages_save(request: Request):
        _, form = await guard(request, "admin")
        chosen = [c for c in form.getlist("lang") if c in ALL_LANGS]
        async with SessionLocal() as db:
            await set_setting(db, "enabled_langs", ",".join(chosen) if chosen else "en")
        flash(request, "Languages updated.")
        return go("/admin/languages")

    @app.get("/admin/settings", response_class=HTMLResponse)
    async def bot_settings(request: Request):
        admin, _ = await guard(request, "admin")
        async with SessionLocal() as db:
            vals = {k: await get_setting(db, k, d) for k, d in (("verification_required", "1"), ("api_required", "0"))}
        return page(request, "settings.html", admin, v=vals, oauth=s.oauth_ready, s=s)

    @app.post("/admin/settings")
    async def bot_settings_save(request: Request):
        _, form = await guard(request, "admin")
        async with SessionLocal() as db:
            await set_setting(db, "verification_required", "1" if form.get("verification_required") == "on" else "0")
            await set_setting(db, "api_required", "1" if form.get("api_required") == "on" and s.oauth_ready else "0")
        flash(request, "Settings saved.")
        return go("/admin/settings")

    # ---------- AI ----------
    async def ai_overrides(db):
        return {k: await get_setting(db, k) for k in ("ai_provider", "ai_model", "ai_vision_model", "ai_base_url")}

    @app.get("/admin/ai", response_class=HTMLResponse)
    async def ai_page(request: Request):
        admin, _ = await guard(request, "super")
        async with SessionLocal() as db:
            o = await ai_overrides(db)
        return page(request, "ai.html", admin, o=o, s=s, key_set=bool(s.ai_api_key), result=None)

    @app.post("/admin/ai/{action}")
    async def ai_action(request: Request, action: str):
        admin, form = await guard(request, "super")
        async with SessionLocal() as db:
            if action == "save":
                for k in ("ai_provider", "ai_model", "ai_vision_model", "ai_base_url"):
                    v = clean(str(form.get(k, "")), 200)
                    if k == "ai_base_url" and v and not is_http_url(v):
                        flash(request, "Base URL must be http(s).", "err")
                        return go("/admin/ai")
                    await set_setting(db, k, v)
                flash(request, "AI settings saved (API key is only read from the environment).")
                return go("/admin/ai")
            o = await ai_overrides(db)
            cats = [c for _, c in await cat_choices(db)]
        ai = AIService(o)
        result = ""
        try:
            notes = clean(str(form.get("notes", "")), 1500)
            if action == "test":
                result = await ai._need().chat("Reply with the single word: pong", "ping", 10)
            elif action == "describe":
                result = await ai.describe(notes)
            elif action == "suggest":
                result = await ai.suggest_category(notes, cats)
        except AIError as e:
            result = f"Error: {e}"
        return page(request, "ai.html", admin, o=o, s=s, key_set=bool(s.ai_api_key), result=result)

    # ---------- admins ----------
    @app.get("/admin/admins", response_class=HTMLResponse)
    async def admins(request: Request):
        admin, _ = await guard(request, "super")
        async with SessionLocal() as db:
            rows = (await db.execute(select(Admin).order_by(Admin.created_at))).scalars().all()
        return page(request, "admins.html", admin, rows=rows, root=s.admin_id)

    @app.post("/admin/admins/add")
    async def admin_add(request: Request):
        _, form = await guard(request, "super")
        try:
            tid = int(str(form.get("telegram_id", "")).strip())
        except ValueError:
            tid = 0
        role, pw = str(form.get("role", "")), str(form.get("password", ""))
        if not tid or role not in ("admin", "moderator") or len(pw) < 10:
            flash(request, "Need a Telegram ID, role (admin/moderator) and a password of 10+ characters.", "err")
            return go("/admin/admins")
        async with SessionLocal() as db:
            a = await db.get(Admin, tid) or Admin(telegram_id=tid)
            if a.role == "super":
                return go("/admin/admins")
            a.name, a.role, a.password_hash = clean(str(form.get("name", "")), 100), role, hash_password(pw)
            db.add(a)
            await db.commit()
        flash(request, "Admin saved.")
        return go("/admin/admins")

    @app.post("/admin/admins/{tid}/delete")
    async def admin_delete(request: Request, tid: int):
        await guard(request, "super")
        if tid != s.admin_id:
            async with SessionLocal() as db:
                a = await db.get(Admin, tid)
                if a:
                    await db.delete(a)
                    await db.commit()
        return go("/admin/admins")

    # ---------- YouTube OAuth (API-confirmed verification) ----------
    ser = URLSafeTimedSerializer(s.secret_key, salt="yt-oauth")
    redirect_uri = f"{s.public_base_url.rstrip('/')}/oauth/youtube/callback"

    @app.get("/oauth/youtube/start")
    async def yt_start(t: str = ""):
        if not s.oauth_ready:
            raise HTTPException(404)
        try:
            ser.loads(t, max_age=900)
        except BadSignature:
            return HTMLResponse("Link expired. Go back to the bot and press Verify again.", 400)
        q = urlencode({"client_id": s.google_client_id, "redirect_uri": redirect_uri, "response_type": "code",
                       "scope": "https://www.googleapis.com/auth/youtube.readonly", "state": t,
                       "prompt": "select_account", "access_type": "online"})
        return go("https://accounts.google.com/o/oauth2/v2/auth?" + q)

    @app.get("/oauth/youtube/callback", response_class=HTMLResponse)
    async def yt_callback(code: str = "", state: str = ""):  # noqa: F811
        try:
            uid = ser.loads(state, max_age=900)
        except BadSignature:
            return HTMLResponse("Invalid or expired request.", 400)
        if not code:
            return HTMLResponse("Authorization was cancelled. You can close this page.")
        async with httpx.AsyncClient(timeout=20) as c:
            tr = await c.post("https://oauth2.googleapis.com/token", data={
                "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
            if tr.status_code != 200:
                return HTMLResponse("Google sign-in failed. Please try again from the bot.", 400)
            r = await c.get("https://www.googleapis.com/youtube/v3/subscriptions",
                            params={"part": "snippet", "mine": "true", "forChannelId": s.youtube_channel_id},
                            headers={"Authorization": f"Bearer {tr.json()['access_token']}"})
        if r.status_code != 200:
            return HTMLResponse("Could not read your subscriptions (YouTube API error).", 400)
        subscribed = bool(r.json().get("items"))
        async with SessionLocal() as db:
            u = await db.get(User, uid)
            if u:
                db.add(Verification(user_id=uid, method="oauth", result="pass" if subscribed else "fail", confidence=1.0,
                                    reasons="YouTube Data API subscriptions.list"))
                if subscribed:
                    u.verification_status = "api"
                await db.commit()
        try:
            await bot.send_message(uid, "✅ Subscription confirmed via YouTube! You can download now." if subscribed
                                   else "❌ We couldn't find a subscription to our channel on that Google account.")
        except Exception:  # noqa: BLE001
            pass
        return HTMLResponse("<h2>✅ Subscribed — return to Telegram.</h2>" if subscribed
                            else "<h2>❌ Not subscribed on this Google account.</h2><p>Subscribe, then try again.</p>")

    return app

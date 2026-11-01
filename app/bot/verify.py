import logging
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import select

from app.bot.common import Flow, btn, esc, markup, nav, render, upsert_user, verified_ok
from app.config import get_settings
from app.db.models import Verification
from app.db.session import SessionLocal, get_setting
from app.i18n import t
from app.services.ai import AIError, AIService

router = Router()
log = logging.getLogger("verify")


def make_token(user_id: int) -> str:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="yt-oauth").dumps(user_id)


async def verify_screen(ev, lang: str, file_id: int | None = None):
    s = get_settings()
    rows = [[btn(t(lang, "verify_btn_sub"), url=s.youtube_url)],
            [btn(t(lang, "verify_btn_ss"), "ver:ss")],
            [btn(t(lang, "verify_btn_check"), "ver:check")],
            nav(lang, f"file:{file_id}" if file_id else None)]
    await render(ev, t(lang, "verify_title"), markup(rows))


@router.callback_query(F.data == "ver:ss")
async def ask_ss(cb: CallbackQuery, state: FSMContext):
    async with SessionLocal() as db:
        lang = (await upsert_user(db, cb.from_user)).language or "en"
    await state.set_state(Flow.screenshot)
    await render(cb, t(lang, "send_ss"), markup([nav(lang, "ver:menu")]))


@router.callback_query(F.data == "ver:menu")
async def menu(cb: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    async with SessionLocal() as db:
        lang = (await upsert_user(db, cb.from_user)).language or "en"
    await verify_screen(cb, lang)


@router.callback_query(F.data == "ver:check")
async def check(cb: CallbackQuery):
    s = get_settings()
    async with SessionLocal() as db:
        u = await upsert_user(db, cb.from_user)
        lang = u.language or "en"
        api_only = await get_setting(db, "api_required", "0") == "1"
        if await verified_ok(db, u):
            label = "API-confirmed ✅" if u.verification_status == "api" else "screenshot-verified 🟡"
            return await render(cb, f"✅ You're {label}. You can download now!", markup([nav(lang)]))
    rows = []
    if s.oauth_ready:
        link = f"{s.public_base_url}/oauth/youtube/start?t={make_token(cb.from_user.id)}"
        rows.append([btn("🔐 Confirm with YouTube (Google)", url=link)])
        text = ("🔍 <b>Not verified yet.</b>\n\nTap the button to sign in with Google. We only check whether you "
                "follow our channel (read-only) and store no Google tokens. Then press Verify again.")
    elif api_only:
        text = "🔍 <b>Not verified yet.</b>\n\nAPI verification is required but isn't set up. Please contact support."
    else:
        text = ("🔍 <b>Not verified yet.</b>\n\nUpload a clear screenshot of our channel showing the "
                "<b>Subscribed</b> state. It's checked automatically or by an admin.")
    rows += [[btn(t(lang, "verify_btn_ss"), "ver:ss")], nav(lang, "ver:menu")]
    await render(cb, text, markup(rows))


@router.message(Flow.screenshot, F.photo)
async def got_screenshot(m: Message, state: FSMContext, bot: Bot):
    photo = m.photo[-1]
    async with SessionLocal() as db:
        u = await upsert_user(db, m.from_user)
        lang = u.language or "en"
        if photo.file_size and photo.file_size > 10 * 1024 * 1024:
            return await m.answer("⚠️ Image too large (max 10 MB).")
        dup = (await db.execute(select(Verification).where(
            Verification.screenshot_unique_id == photo.file_unique_id, Verification.user_id != u.id,
            Verification.result == "pass"))).first()
        if dup:
            await m.answer("🚫 This screenshot was already used by another account. Please upload your own.")
            return
        wait = await m.answer(t(lang, "analyzing"))
        buf = BytesIO()
        await bot.download(photo, destination=buf)
        overrides = {k: await get_setting(db, k) for k in ("ai_provider", "ai_model", "ai_vision_model", "ai_base_url")}
        ai = AIService(overrides)
        rec = Verification(user_id=u.id, method="screenshot", result="review", screenshot_file_id=photo.file_id,
                           screenshot_unique_id=photo.file_unique_id)
        msg = ""
        if not ai.enabled:
            rec.result, rec.reasons = "unavailable", "AI not configured; queued for manual admin review."
            msg = "📨 Your screenshot was sent to our admins for manual review. You'll be notified."
        else:
            try:
                r = await ai.analyze_screenshot(buf.getvalue(), "RUK MODERS GANG", "image/jpeg")
                conf = float(r.get("confidence", 0))
                ok = all([r.get("is_youtube_screenshot"), r.get("channel_matches"), r.get("shows_subscribed_state")])
                rec.confidence, rec.reasons = conf, str(r.get("reasons", ""))[:1000]
                if r.get("manipulation_suspected"):
                    rec.result = "fail"
                    msg = "🚫 The screenshot looks edited. Please send an unedited screenshot."
                elif ok and conf >= 0.75:
                    rec.result = "pass"
                    if u.verification_status == "none":
                        u.verification_status = "visual"
                    msg = ("✅ Screenshot accepted (visual check). You can download now!"
                           if await verified_ok(db, u) else
                           "🟡 Screenshot accepted, but this store also requires confirmation via Google. Tap 🔍 Verify Subscription.")
                elif ok:
                    rec.result = "review"
                    msg = "🕵️ We couldn't be fully sure, so an admin will review it shortly."
                else:
                    rec.result = "fail"
                    msg = "❌ We couldn't see the subscribed state of our channel. Send a clearer screenshot of the channel page."
            except (AIError, ValueError, KeyError) as e:
                log.warning("screenshot analysis failed: %s", e)
                rec.result, rec.reasons = "unavailable", "AI error; manual review."
                msg = "📨 Automatic analysis is unavailable; an admin will review your screenshot."
        db.add(rec)
        await db.commit()
    await state.set_state(None)
    await wait.edit_text(msg, reply_markup=markup([[btn("🔍 " + t(lang, "verify_btn_check"), "ver:check")], nav(lang)]))


@router.message(Flow.screenshot)
async def not_photo(m: Message):
    await m.answer("📸 Please send the screenshot as a photo (not a file).")

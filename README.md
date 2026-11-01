# 🚀 RUK MODERS GANG — Telegram File Store Bot

Aiogram 3 bot + FastAPI admin dashboard in **one process**, SQLAlchemy 2 (SQLite dev / PostgreSQL prod), replaceable AI layer.

## 1. Where to paste your secrets
Copy `.env.example` → `.env` (local) **or** add the same names in Render → *Environment* / your VPS secret store. Never commit `.env`.

| Variable | What to put |
|---|---|
| `BOT_TOKEN` | New token from @BotFather (revoke any token you've ever pasted in public) |
| `ADMIN_ID` | Your numeric Telegram ID (ask @userinfobot) — becomes Super Admin |
| `DATABASE_URL` | Blank/default = SQLite `data/bot.db`. Production: your Postgres URL (`postgres://…` is auto-converted) |
| `SECRET_KEY` | Long random string: `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `ADMIN_PANEL_PASSWORD` | Your dashboard password (login = your Telegram ID + this password) |
| `AI_API_KEY` (+ `AI_PROVIDER`, `AI_MODEL`, `AI_BASE_URL`) | Any OpenAI-compatible API or Anthropic. Vision-capable model needed for screenshots |
| `PUBLIC_BASE_URL` | Public https URL of your deployment (needed for Google sign-in) |
| `STORAGE_CHAT_ID` | Optional private channel/group (bot must be admin) used to store uploads; default = your DM with the bot |

**First step:** open your bot in Telegram and press **Start** once (otherwise the bot can't message you to store uploads).

## 2. Run
**Local / Termux (Android):** `pkg install python` → `pip install -r requirements.txt` (if `asyncpg` fails to build, delete that line; SQLite doesn't need it) → `python -m app.main` → dashboard at `http://localhost:8000/admin`.

**Docker / VPS:** set `POSTGRES_PASSWORD` + the vars above in `.env` → `docker compose up -d --build`. Put Caddy/Nginx in front for HTTPS. Logs: `docker compose logs -f app`. Restart: `docker compose restart app`. Health: `GET /healthz`.

**Render:** push to GitHub → *New → Blueprint* (uses `render.yaml`) → fill the `sync:false` secrets. Use a paid always-on instance (polling bots stop when a free instance sleeps). Add an uptime monitor on `/healthz`.

## 3. Database & backups
`alembic upgrade head` runs automatically in Docker/Procfile. Schema changes: edit `app/db/models.py` → `alembic revision --autogenerate -m "msg"` → `alembic upgrade head`.
Backup: `./scripts/backup.sh` (pg_dump or SQLite `.backup`, keeps 14). Schedule with cron: `0 3 * * * cd /srv && ./scripts/backup.sh`.

## 4. Using it
1. `/admin` in the bot (admins only) or open the dashboard → **Upload**: pick category, attach apk/zip/mcpack files (several per version), thumbnail, tick *Published*. Files are stored as Telegram `file_id`s; users get them instantly.
2. **Categories** page: unlimited categories/subcategories. **Broadcast**: text/image/video + buttons (`Label | https://…`). Ticking *Notify* on first publish announces the file.
3. Roles: **Super** (everything, AI, admins) · **Admin** (files, categories, users, broadcast, stats, settings) · **Moderator** (view files/users, review verifications).

## 5. Honest limitations
- **Subscription verification.** A screenshot is *visual evidence only* and can be faked; AI can't prove a live subscription. The bot stores status separately: `visual` (screenshot/manual approval) vs `api` (Google sign-in + YouTube Data API `subscriptions.list`, read-only, no tokens stored). Enable *Require API-confirmed* in Bot Settings for real enforcement. Google may require OAuth app verification for the `youtube.readonly` scope before public use. Without an AI key, screenshots go to manual review — nothing is auto-approved.
- **File size.** Cloud Bot API: uploads ≤ 50 MB (bots send ≤ 50 MB). For up to 2 GB run a [Local Bot API Server](https://github.com/tdlib/telegram-bot-api) and set `LOCAL_BOT_API_URL`. Larger files: use *External download link*.
- **Languages.** Menus/navigation are translated in all 14 languages; longer messages are English until you add strings in `app/i18n.py`. "More Languages" (8 extra) show the English UI; the AI assistant replies in the user's language.
- **Dashboard login** uses Telegram ID + password (not Telegram Login). Login attempts are rate-limited per IP; all POSTs are CSRF-protected.

## 6. Tests
`python -m unittest discover -s tests -v` (pure logic + template rendering). Manual QA checklist: /start → language → every category → upload a file → download → search → verification (screenshot + Google) → broadcast → restart bot (data persists).

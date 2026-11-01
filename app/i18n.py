"""Translations. Menu labels + navigation are translated for all 14 core languages.
Every other string falls back to English (see t()). Add more keys to EN and WORDS to extend."""

LANGS = {
    "en": "🇬🇧 English", "bn": "🇮🇳 বাংলা", "hi": "🇮🇳 हिंदी", "ru": "🇷🇺 Русский",
    "es": "🇪🇸 Español", "fr": "🇫🇷 Français", "de": "🇩🇪 Deutsch", "pt": "🇵🇹 Português",
    "ar": "🇸🇦 العربية", "id": "🇮🇩 Indonesian", "tr": "🇹🇷 Türkçe", "zh": "🇨🇳 中文",
    "ja": "🇯🇵 日本語", "ko": "🇰🇷 한국어",
}
MORE_LANGS = {  # shown under "More Languages" (UI falls back to English; AI replies in this language)
    "it": "🇮🇹 Italiano", "uk": "🇺🇦 Українська", "pl": "🇵🇱 Polski", "vi": "🇻🇳 Tiếng Việt",
    "th": "🇹🇭 ไทย", "ur": "🇵🇰 اردو", "fa": "🇮🇷 فارسی", "nl": "🇳🇱 Nederlands",
}
ALL_LANGS = {**LANGS, **MORE_LANGS}

KEYS = ["m_clients", "m_patches", "m_textures", "m_fps", "m_apk", "m_tools", "m_search",
        "m_support", "m_account", "m_settings", "back", "home", "download", "welcome"]

WORDS = {
    "en": "Minecraft Clients|Minecraft Patches|Texture Packs|FPS Boosters|APK & Applications|Tools & Utilities|Search Files|Support & Community|My Account|Settings|Back|Home|Download|Welcome",
    "bn": "মাইনক্রাফট ক্লায়েন্ট|মাইনক্রাফট প্যাচ|টেক্সচার প্যাক|FPS বুস্টার|APK ও অ্যাপ|টুলস|ফাইল খুঁজুন|সাপোর্ট ও কমিউনিটি|আমার অ্যাকাউন্ট|সেটিংস|ফিরে যান|হোম|ডাউনলোড|স্বাগতম",
    "hi": "माइनक्राफ्ट क्लाइंट|माइनक्राफ्ट पैच|टेक्सचर पैक|FPS बूस्टर|APK और ऐप्स|टूल्स|फ़ाइल खोजें|सहायता और कम्युनिटी|मेरा खाता|सेटिंग्स|वापस|होम|डाउनलोड|स्वागत है",
    "ru": "Клиенты Minecraft|Патчи Minecraft|Текстур-паки|FPS-бустеры|APK и приложения|Инструменты|Поиск файлов|Поддержка и сообщество|Мой аккаунт|Настройки|Назад|Главная|Скачать|Добро пожаловать",
    "es": "Clientes de Minecraft|Parches de Minecraft|Paquetes de texturas|Potenciadores de FPS|APK y aplicaciones|Herramientas|Buscar archivos|Soporte y comunidad|Mi cuenta|Ajustes|Atrás|Inicio|Descargar|Bienvenido",
    "fr": "Clients Minecraft|Patchs Minecraft|Packs de textures|Boosters de FPS|APK et applications|Outils|Rechercher|Support et communauté|Mon compte|Paramètres|Retour|Accueil|Télécharger|Bienvenue",
    "de": "Minecraft-Clients|Minecraft-Patches|Texturpakete|FPS-Booster|APK & Apps|Werkzeuge|Dateien suchen|Support & Community|Mein Konto|Einstellungen|Zurück|Start|Herunterladen|Willkommen",
    "pt": "Clientes de Minecraft|Patches de Minecraft|Pacotes de texturas|Boosters de FPS|APK e aplicativos|Ferramentas|Buscar arquivos|Suporte e comunidade|Minha conta|Configurações|Voltar|Início|Baixar|Bem-vindo",
    "ar": "عملاء ماينكرافت|تصحيحات ماينكرافت|حزم الإكساء|معززات FPS|APK والتطبيقات|الأدوات|بحث عن الملفات|الدعم والمجتمع|حسابي|الإعدادات|رجوع|الرئيسية|تحميل|أهلاً بك",
    "id": "Klien Minecraft|Patch Minecraft|Paket Tekstur|Penguat FPS|APK & Aplikasi|Alat|Cari File|Dukungan & Komunitas|Akun Saya|Pengaturan|Kembali|Beranda|Unduh|Selamat datang",
    "tr": "Minecraft İstemcileri|Minecraft Yamaları|Doku Paketleri|FPS Arttırıcılar|APK ve Uygulamalar|Araçlar|Dosya Ara|Destek ve Topluluk|Hesabım|Ayarlar|Geri|Ana Sayfa|İndir|Hoş geldin",
    "zh": "Minecraft 客户端|Minecraft 补丁|材质包|FPS 加速器|APK 与应用|工具|搜索文件|支持与社区|我的账户|设置|返回|主页|下载|欢迎",
    "ja": "Minecraft クライアント|Minecraft パッチ|テクスチャパック|FPS ブースター|APK とアプリ|ツール|ファイル検索|サポートとコミュニティ|マイアカウント|設定|戻る|ホーム|ダウンロード|ようこそ",
    "ko": "마인크래프트 클라이언트|마인크래프트 패치|텍스처 팩|FPS 부스터|APK 및 앱|도구|파일 검색|지원 및 커뮤니티|내 계정|설정|뒤로|홈|다운로드|환영합니다",
}
TABLE = {lang: dict(zip(KEYS, v.split("|"))) for lang, v in WORDS.items()}

# Longer messages (English; extend with per-language dicts as needed)
EN = {
    "pick_lang": "🌍 <b>Please Select Your Language</b>",
    "welcome_msg": "👋 <b>{welcome}, {name}!</b>\n\n🔥 <b>RUK MODERS GANG</b>\n🎮 Minecraft clients, patches, packs, APKs and tools — all in one place.\n\n👇 Choose a category below.",
    "search_prompt": "🔍 <b>Search Files</b>\n\nSend a name, version or keyword.\nExamples: <i>Apollon Client</i>, <i>1.26.60</i>, <i>64-bit APK</i>",
    "no_results": "😕 No files found. Try a shorter or different keyword.",
    "empty": "📭 Nothing here yet. Check back soon!",
    "not_found": "⚠️ This file is no longer available.",
    "support_title": "❤️ <b>Support & Community</b>\n\nJoin us and never miss an update!",
    "settings_title": "⚙️ <b>Settings</b>",
    "change_lang": "🌍 Change Language",
    "lang_saved": "✅ Language saved.",
    "more_langs": "➕ More Languages",
    "ask_ai": "🤖 Ask AI Assistant",
    "ask_ai_prompt": "🤖 Ask me anything about downloads, installation or the bot. Send your question:",
    "ai_unavailable": "🤖 The AI assistant isn't configured right now. Try 🔍 Search instead.",
    "verify_title": "❤️ <b>SUPPORT OUR COMMUNITY</b>\n\nPlease subscribe to our YouTube channel before downloading!",
    "verify_btn_sub": "▶️ Subscribe to YouTube",
    "verify_btn_ss": "📸 Upload Subscription Screenshot",
    "verify_btn_check": "🔍 Verify Subscription",
    "send_ss": "📸 Send a clear screenshot of the channel page showing the <b>Subscribed</b> button (bell icon visible).",
    "analyzing": "⏳ Analyzing your screenshot…",
    "too_fast": "⏱ Slow down a little, please.",
    "banned": "🚫 Your access has been restricted.",
    "error": "⚠️ Something went wrong. Please try again.",
    "page": "Page {p}/{n}",
}


def t(lang: str | None, key: str, **kw) -> str:
    lang = lang or "en"
    val = TABLE.get(lang, {}).get(key) or TABLE["en"].get(key) or EN.get(key) or key
    return val.format(**kw) if kw else val

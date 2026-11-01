"""Run: python -m unittest discover -s tests -v   (pure-logic tests; no network or token needed)."""
import os
import importlib.util
import unittest
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PANEL_PASSWORD", "pw")


class Core(unittest.TestCase):
    def test_i18n_all_core_languages_complete(self):
        from app.i18n import KEYS, LANGS, TABLE, t
        for code in LANGS:
            self.assertEqual(set(TABLE[code]), set(KEYS), code)
        self.assertEqual(t("hi", "back"), "वापस")
        self.assertEqual(t("xx", "back"), "Back")        # unknown language -> English
        self.assertIn("Search", t("ur", "m_search"))      # extra language -> English fallback

    def test_security(self):
        from app.services.security import hash_password, looks_spammy, safe_filename, verify_password
        h = hash_password("secret-pass-1")
        self.assertTrue(verify_password("secret-pass-1", h))
        self.assertFalse(verify_password("wrong", h))
        self.assertEqual(safe_filename("../../etc/pa ss<wd>.apk"), "pa ss_wd_.apk")
        self.assertTrue(looks_spammy("http://a.com http://b.com t.me/x"))
        self.assertFalse(looks_spammy("apollon client 1.26.60"))

    @unittest.skipUnless(importlib.util.find_spec("sqlalchemy"), "needs sqlalchemy")
    def test_search_terms(self):
        from app.services.search import terms_of
        self.assertEqual(terms_of("  64-bit  APK "), ["64-bit", "apk"])

    @unittest.skipUnless(importlib.util.find_spec("pydantic_settings"), "needs pydantic-settings")
    def test_db_url(self):
        from app.config import Settings
        s = Settings(database_url="postgres://u:p@h/db")
        self.assertTrue(s.db_url.startswith("postgresql+asyncpg://"))

    def test_templates_render(self):
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(Path("app/web/templates")), autoescape=True)
        class A: role = "super"; telegram_id = 1
        for p in Path("app/web/templates").glob("*.html"):
            env.get_template(p.name).render(admin=A, nav=[("/x", "X")], flash=None, csrf="c", d={}, files=[], users=[],
                                            rows=[], cats=[], series=[], mx=1, top=[], langs={}, enabled=[""],
                                            translated=set(), v={}, s=type("S", (), {})(), o={}, key_set=False,
                                            result=None, f=None, q="", p=0, flt="", max_mb=50, oauth=False, root=1)


if __name__ == "__main__":
    unittest.main()

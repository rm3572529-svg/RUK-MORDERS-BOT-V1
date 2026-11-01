import hashlib
import hmac
import os
import re

ALLOWED_EXT = {".apk", ".zip", ".mcpack", ".mcaddon", ".mcworld", ".mctemplate", ".rar", ".7z",
               ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".json", ".txt"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".mp4"}


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + h.hex()


def verify_password(pw: str, stored: str) -> bool:
    try:
        salt_hex, h_hex = stored.split("$")
        h = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


def safe_filename(name: str) -> str:
    name = os.path.basename(name or "file")
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .") or "file"
    return name[:120]


def ext_of(name: str) -> str:
    return os.path.splitext(name.lower())[1]


def clean(text: str | None, limit: int = 2000) -> str:
    """Trim + strip control characters from user/admin supplied text."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text or "").strip()
    return text[:limit]


def is_http_url(u: str) -> bool:
    return bool(re.fullmatch(r"https?://[^\s<>\"']+", u or ""))


URL_RE = re.compile(r"(https?://|t\.me/|www\.)", re.I)


def looks_spammy(text: str) -> bool:
    """Cheap heuristic pre-filter (AI check runs on top when configured)."""
    if len(URL_RE.findall(text)) >= 3:
        return True
    if re.search(r"(.)\1{15,}", text):
        return True
    return False

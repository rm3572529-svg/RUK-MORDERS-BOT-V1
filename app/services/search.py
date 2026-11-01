import re
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import File


def terms_of(q: str) -> list[str]:
    return [x for x in re.split(r"[\s,]+", q.lower().strip()) if len(x) >= 2][:6]


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def search_files(db: AsyncSession, terms: list[str]) -> list[File]:
    """Partial + alias matching. Ranks by number of terms matched."""
    if not terms:
        return []
    cols = (File.name, File.version, File.architecture, File.aliases, File.description)
    conds = [c.ilike(f"%{_esc(t)}%", escape="\\") for t in terms for c in cols]
    rows = (await db.execute(select(File).where(File.published.is_(True), or_(*conds)).limit(200))).scalars().all()

    def score(f: File) -> int:
        blob = " ".join([f.name, f.version, f.architecture, f.aliases, f.description]).lower()
        name_blob = f"{f.name} {f.version} {f.aliases}".lower()
        return sum((2 if t in name_blob else 1) for t in terms if t in blob)

    return sorted(rows, key=score, reverse=True)

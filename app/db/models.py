from datetime import datetime, timezone
from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user id
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str | None] = mapped_column(String(8))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    total_downloads: Mapped[int] = mapped_column(Integer, default=0)
    # none | visual | api   (visual = screenshot only / manual approval, api = confirmed via YouTube API)
    verification_status: Mapped[str] = mapped_column(String(16), default="none")
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_bot: Mapped[bool] = mapped_column(Boolean, default=False)


class Category(Base):
    """Categories and subcategories (parent_id is NULL for top-level)."""
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    key: Mapped[str | None] = mapped_column(String(32))  # menu key for translated top-level items
    name: Mapped[str] = mapped_column(String(100))
    emoji: Mapped[str] = mapped_column(String(8), default="📁")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    children = relationship("Category", cascade="all, delete-orphan", lazy="selectin")
    __table_args__ = (Index("ix_categories_parent", "parent_id"),)


class File(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(50), default="")
    architecture: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    changelog: Mapped[str] = mapped_column(Text, default="")
    aliases: Mapped[str] = mapped_column(Text, default="")  # comma separated search aliases (any language)
    youtube_url: Mapped[str] = mapped_column(String(300), default="")
    external_url: Mapped[str] = mapped_column(String(500), default="")
    thumbnail_file_id: Mapped[str | None] = mapped_column(String(300))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    restricted: Mapped[bool] = mapped_column(Boolean, default=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    assets = relationship("FileAsset", cascade="all, delete-orphan", lazy="selectin")
    category = relationship("Category", lazy="joined")

    @property
    def size_bytes(self) -> int:
        return sum(a.size or 0 for a in self.assets)

    __table_args__ = (Index("ix_files_category_pub", "category_id", "published"),
                      Index("ix_files_name", "name"))


class FileAsset(Base):
    """One Telegram file; a File version may have several."""
    __tablename__ = "file_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    tg_file_id: Mapped[str] = mapped_column(String(300))
    file_name: Mapped[str] = mapped_column(String(200), default="")
    size: Mapped[int] = mapped_column(BigInteger, default=0)


class Admin(Base):
    __tablename__ = "admins"
    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(16), default="moderator")  # super | admin | moderator
    password_hash: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Verification(Base):
    __tablename__ = "verifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    method: Mapped[str] = mapped_column(String(16))  # screenshot | oauth | manual
    result: Mapped[str] = mapped_column(String(16))  # pass | fail | review | unavailable
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reasons: Mapped[str] = mapped_column(Text, default="")
    screenshot_file_id: Mapped[str | None] = mapped_column(String(300))
    screenshot_unique_id: Mapped[str | None] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Download(Base):
    __tablename__ = "downloads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (Index("ix_downloads_user", "user_id"), Index("ix_downloads_created", "created_at"))


class BotSetting(Base):
    __tablename__ = "bot_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Broadcast(Base):
    __tablename__ = "broadcasts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, default="")
    media_kind: Mapped[str] = mapped_column(String(10), default="")
    media_file_id: Mapped[str] = mapped_column(String(300), default="")
    buttons: Mapped[str] = mapped_column(Text, default="")
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    created_by: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

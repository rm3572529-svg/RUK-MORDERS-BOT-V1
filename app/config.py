from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_id: int
    secret_key: str
    admin_panel_password: str
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"

    ai_provider: str = "openai"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_vision_model: str = ""

    public_base_url: str = "http://localhost:8000"
    port: int = 8000
    storage_chat_id: int | None = None
    local_bot_api_url: str = ""

    youtube_channel_id: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""

    youtube_url: str = "https://youtube.com/@rukmodersgang?si=ZCTlu8OwnppFzjC5"
    whatsapp_url: str = "https://whatsapp.com/channel/0029Vb6ZkXmJ3jv1PQ6CZs33"

    @property
    def db_url(self) -> str:
        u = self.database_url.strip()
        if u.startswith("postgres://"):
            u = "postgresql+asyncpg://" + u[len("postgres://"):]
        elif u.startswith("postgresql://"):
            u = "postgresql+asyncpg://" + u[len("postgresql://"):]
        return u

    @property
    def storage_chat(self) -> int:
        return self.storage_chat_id or self.admin_id

    @property
    def max_upload_mb(self) -> int:
        return 2000 if self.local_bot_api_url else 50

    @property
    def oauth_ready(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret and self.youtube_channel_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

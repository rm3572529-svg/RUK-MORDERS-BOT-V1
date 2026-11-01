import logging
import re
from app.config import get_settings


class SecretFilter(logging.Filter):
    """Masks secrets so they never reach the logs."""

    def __init__(self):
        super().__init__()
        s = get_settings()
        self.secrets = [x for x in (s.bot_token, s.ai_api_key, s.secret_key,
                                    s.admin_panel_password, s.google_client_secret) if x]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for sec in self.secrets:
            msg = msg.replace(sec, "***")
        msg = re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot***", msg)
        record.msg, record.args = msg, ()
        return True


def setup_logging():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    f = SecretFilter()
    for h in logging.getLogger().handlers:
        h.addFilter(f)
    logging.getLogger("httpx").setLevel(logging.WARNING)

from slowapi import Limiter
from slowapi.util import get_remote_address

from src.app.settings import settings

REDIS_PASSWORD = settings.REDIS_PASSWORD
REDIS_HOST = settings.REDIS_HOST
REDIS_PORT = settings.REDIS_PORT

limiter = Limiter(
    key_func=get_remote_address,
    key_style="endpoint",
    strategy="moving-window",
    headers_enabled=True,
    storage_uri=f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0",
)

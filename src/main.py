from contextlib import asynccontextmanager

import geoip2.database
import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.app.db import AsyncSessionLocal, engine
from src.app.repositories.user_repository import create_first_admin_if_not_exists
from src.app.routes import register_routes
from src.app.settings import settings
from src.app.utils import limiter
from src.app.utils.exception_handlers import register_exception_handlers
from src.app.utils.logger import startup_logger

startup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as session:
        await create_first_admin_if_not_exists(session)

    app.state.redis = aioredis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
        retry_on_timeout=False,
        retry=None,
    )

    try:
        app.state.geoip_reader = geoip2.database.Reader("GeoLite2-City.mmdb")
    except (FileNotFoundError, OSError) as error:
        logger.warning(f"GeoIP database unavailable: {error}")
        app.state.geoip_reader = None

    try:
        yield
    finally:
        try:
            if app.state.geoip_reader is not None:
                app.state.geoip_reader.close()
        finally:
            try:
                await app.state.redis.aclose()
            finally:
                await engine.dispose()


app = FastAPI(lifespan=lifespan, title="FastAPI IAM")

app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_routes(app)

logger.info("Server successfully started")

register_exception_handlers(app)

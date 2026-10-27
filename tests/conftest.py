import os

os.environ["ENV_FILE"] = ".env.test"

from pathlib import Path

import pytest_asyncio
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from src.app.db import AsyncSessionLocal
from src.main import app
from tests.factories import *  # noqa: F403
from tests.fixtures import *  # noqa: F403

BASE_DIR = Path(__file__).resolve().parent.parent / "src"


@pytest_asyncio.fixture(scope="session", autouse=True)
def migrations():
    config = Config()
    config.set_main_option(
        "script_location",
        str(BASE_DIR / "migrations"),
    )

    command.upgrade(config, "head")


@pytest_asyncio.fixture
async def app_lifespan():
    async with LifespanManager(app):
        yield


@pytest_asyncio.fixture
async def client(app_lifespan):
    transport = ASGITransport(app)

    async with AsyncClient(
        transport=transport, base_url="http://test/api/v1"
    ) as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def clear_db(app_lifespan):
    yield

    await app.state.redis.flushdb()
    async with AsyncSessionLocal() as session:
        await session.execute(text("""
            TRUNCATE TABLE
                users
            RESTART IDENTITY
            CASCADE
        """))
        await session.commit()

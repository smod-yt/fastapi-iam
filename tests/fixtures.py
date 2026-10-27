import pytest_asyncio
from faker import Faker
from httpx import AsyncClient

faker = Faker()


@pytest_asyncio.fixture
async def access_token(client: AsyncClient):
    name = faker.name()[:32]
    user_name = faker.user_name().lower().replace(".", "_")[:16]
    if len(user_name) < 3:
        user_name = f"user_{user_name}"

    response = await client.post(
        "/auth/register",
        json={"name": name, "user_name": user_name, "password": "password"},
    )
    content = response.json()

    assert response.status_code == 201

    return content["access_token"]


@pytest_asyncio.fixture
async def refresh_token(client: AsyncClient):
    name = faker.name()[:32]
    user_name = faker.user_name().lower().replace(".", "_")[:16]
    if len(user_name) < 3:
        user_name = f"user_{user_name}"

    response = await client.post(
        "/auth/register",
        json={"name": name, "user_name": user_name, "password": "password"},
    )

    assert response.status_code == 201

    return response.cookies.get("refresh_token")


@pytest_asyncio.fixture
async def other_user_session_uuid(refresh_token: str):
    from src.app.repositories import token_repository
    from src.main import app

    return await token_repository.get_session_uuid_from_refresh(
        app.state.redis, refresh_token
    )

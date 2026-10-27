import pytest_asyncio
from faker import Faker
from httpx import AsyncClient, Response
from pydantic import BaseModel

from src.app.schemas.auth_schema import AuthResponse
from tests.utils import validate_response

faker = Faker()


@pytest_asyncio.fixture
async def user_factory(client: AsyncClient):
    async def factory(
        name: str | None = None,
        user_name: str | None = None,
        password: str | None = "password",
    ) -> tuple[BaseModel, Response]:
        name = (name or faker.name())[:32]
        user_name = (user_name or faker.user_name().lower().replace(".", "_"))[:16]
        if len(user_name) < 3:
            user_name = f"user_{user_name}"

        payload = {"name": name, "user_name": user_name, "password": password}

        response = await client.post(
            "/auth/register",
            json=payload,
        )

        assert response.status_code == 201
        data = validate_response(response, AuthResponse)

        assert data.access_token is not None
        assert response.cookies.get("refresh_token") is not None
        assert data.user.name == payload["name"]
        assert data.user.user_name == payload["user_name"]
        assert "password" not in response.json()["user"]
        assert data.user.id > 0

        return data, response

    return factory


@pytest_asyncio.fixture
async def admin_factory(client: AsyncClient, user_factory):
    async def factory(
        name: str | None = None,
        user_name: str | None = None,
        password: str | None = "adminpassword",
    ) -> tuple[BaseModel, Response]:
        from src.app.db import AsyncSessionLocal
        from src.app.models import User
        from src.app.models.user_model import UserRoles

        data, response = await user_factory(
            name=name, user_name=user_name, password=password
        )
        async with AsyncSessionLocal() as session:
            user = await session.get(User, data.user.id)
            user.role = UserRoles.ADMIN
            session.add(user)
            await session.commit()

        return data, response

    return factory


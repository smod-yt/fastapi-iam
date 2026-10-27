from datetime import timedelta

import pytest
from httpx import AsyncClient

from src.app.schemas.auth_schema import (
    AccessTokenSchema,
    AuthResponse,
)
from tests.utils import validate_response


async def test_register_success(client: AsyncClient):
    payload = {
        "name": "Test User",
        "user_name": "test_user",
        "password": "validpassword123",
    }

    response = await client.post("/auth/register", json=payload)

    assert response.status_code == 201
    auth_data = validate_response(response, AuthResponse)

    assert auth_data.access_token != ""
    assert auth_data.user.id > 0
    assert auth_data.user.name == payload["name"]
    assert auth_data.user.user_name == payload["user_name"]
    assert "password" not in response.json()["user"]

    refresh_token = response.cookies.get("refresh_token")
    assert refresh_token is not None
    assert refresh_token != ""


async def test_register_duplicate_user_conflict(client: AsyncClient, user_factory):
    user_data, _ = await user_factory(user_name="conflict_user")

    payload = {
        "name": user_data.user.name,
        "user_name": user_data.user.user_name,
        "password": "somepassword",
    }
    response = await client.post("/auth/register", json=payload)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert response.json()["error"]["message"] == "This user name is already taken"


async def test_register_duplicate_admin_conflict(client: AsyncClient):
    payload = {
        "name": "Admin",
        "user_name": "admin",
        "password": "somepassword",
    }

    response = await client.post("/auth/register", json=payload)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert response.json()["error"]["message"] == "This user name is already taken"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"user_name": "validname", "password": "pass123"},
        {"name": "Test", "password": "pass123"},
        {"name": "Test", "user_name": "validname"},
        {"name": "", "user_name": "validname", "password": "pass123"},
        {"name": "a" * 33, "user_name": "validname", "password": "pass123"},
        {"name": "Test", "user_name": "ab", "password": "pass123"},
        {"name": "Test", "user_name": "a" * 17, "password": "pass123"},
        {"name": "Test", "user_name": "Invalid_Caps", "password": "pass123"},
        {"name": "Test", "user_name": "user@name!", "password": "pass123"},
        {"name": "Test", "user_name": "validname", "password": "short7"},
        {"name": "Test", "user_name": "юзернейм", "password": "pass123"},
        {"name": "Test", "user_name": "validname", "password": "a" * 61},
    ],
)
async def test_register_invalid_payload(client: AsyncClient, payload: dict):
    response = await client.post("/auth/register", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"password": "pass123"},
        {"user_name": "validname"},
        {"user_name": "ab", "password": "pass123"},
        {"user_name": "a" * 17, "password": "pass123"},
        {"user_name": "Invalid_Caps", "password": "pass123"},
        {"user_name": "validname", "password": "a" * 61},
    ],
)
async def test_login_invalid_payload(client: AsyncClient, payload: dict):
    response = await client.post("/auth/login", json=payload)

    assert response.status_code == 422


async def test_login_success(client: AsyncClient, user_factory):
    user_pass = "somepassword"
    user_data, register_response = await user_factory(password=user_pass)

    login_response = await client.post(
        "/auth/login",
        json={
            "user_name": user_data.user.user_name,
            "password": user_pass,
        },
    )

    assert login_response.status_code == 200
    auth_data = validate_response(login_response, AuthResponse)

    assert auth_data.access_token != ""
    assert auth_data.user.id == user_data.user.id
    assert auth_data.user.user_name == user_data.user.user_name

    register_refresh_token = register_response.cookies.get("refresh_token")
    login_refresh_token = login_response.cookies.get("refresh_token")

    assert login_refresh_token is not None
    assert login_refresh_token != ""
    assert login_refresh_token != register_refresh_token


async def test_login_invalid_password(client: AsyncClient, user_factory):
    user_data, _ = await user_factory(password="correct_password")

    response = await client.post(
        "/auth/login",
        json={
            "user_name": user_data.user.user_name,
            "password": "wrong_password",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert response.json()["error"]["message"] == "Invalid credentials"


async def test_login_invalid_user_name(client: AsyncClient, user_factory):
    user_pass = "correct_password"
    await user_factory(user_name="existing_user", password=user_pass)

    response = await client.post(
        "/auth/login",
        json={
            "user_name": "non_exists_user",
            "password": user_pass,
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert response.json()["error"]["message"] == "Invalid credentials"


async def test_refresh_success(client: AsyncClient, freezer, user_factory):
    user_data, register_response = await user_factory()
    old_refresh_token = register_response.cookies.get("refresh_token")
    old_access_token = user_data.access_token

    freezer.tick(timedelta(seconds=1))
    response = await client.post("/auth/refresh")

    assert response.status_code == 200
    token_data = validate_response(response, AccessTokenSchema)

    assert token_data.access_token != ""
    assert token_data.access_token != old_access_token

    new_refresh_token = response.cookies.get("refresh_token")
    assert new_refresh_token is not None
    assert new_refresh_token != ""
    assert new_refresh_token != old_refresh_token


@pytest.mark.parametrize(
    "refresh_token_value, expected_status, expected_error_code",
    [
        (None, 401, "REFRESH_TOKEN_NOT_GRANTED"),
        ("invalid_refresh_token", 401, "SESSION_EXPIRED"),
    ],
)
async def test_refresh_unauthorized(
    client: AsyncClient,
    refresh_token_value: str | None,
    expected_status: int,
    expected_error_code: str,
):
    if refresh_token_value is None:
        client.cookies.delete("refresh_token")
    else:
        client.cookies.set("refresh_token", refresh_token_value)

    response = await client.post("/auth/refresh")

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_error_code

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from pydantic import RootModel

from src.app.schemas.auth_schema import (
    AccessTokenSchema,
    AuthResponse,
    SessionReadSchema,
)
from tests.utils import auth_header, validate_response

SessionsResponse = RootModel[dict[uuid.UUID, SessionReadSchema]]


async def test_get_sessions_success(client: AsyncClient, user_factory):
    user_data, _ = await user_factory()
    access_token = user_data.access_token

    response = await client.get(
        "/sessions/",
        headers=auth_header(access_token),
    )

    assert response.status_code == 200
    sessions = validate_response(response, SessionsResponse).root
    assert len(sessions) == 1

    session_uuid, session = next(iter(sessions.items()))

    assert session.is_current is True
    assert session.created_at > 0
    assert session.last_activity > 0
    assert session.ip != ""
    assert session.client != ""
    assert session.location != ""


async def test_get_sessions_multiple_sessions(client: AsyncClient, user_factory):
    user_pass = "somepassword"
    user_data, _ = await user_factory(password=user_pass)
    user_name = user_data.user.user_name

    login_response = await client.post(
        "/auth/login",
        json={"user_name": user_name, "password": user_pass},
    )
    assert login_response.status_code == 200
    auth_data = validate_response(login_response, AuthResponse)
    login_access_token = auth_data.access_token

    sessions_response = await client.get(
        "/sessions/",
        headers=auth_header(login_access_token),
    )

    assert sessions_response.status_code == 200
    sessions = validate_response(sessions_response, SessionsResponse).root
    assert len(sessions) == 2

    current_sessions = [info for info in sessions.values() if info.is_current]
    other_sessions = [info for info in sessions.values() if not info.is_current]

    assert len(current_sessions) == 1
    assert len(other_sessions) == 1


async def test_get_sessions_user_isolation(client: AsyncClient, user_factory):
    user1_data, user1_resp = await user_factory()
    user2_data, _ = await user_factory()

    u2_sessions_resp = await client.get(
        "/sessions/",
        headers=auth_header(user2_data.access_token),
    )
    assert u2_sessions_resp.status_code == 200
    u2_sessions = validate_response(u2_sessions_resp, SessionsResponse).root
    u2_session_uuid = next(iter(u2_sessions.keys()))

    user1_refresh = user1_resp.cookies.get("refresh_token")
    client.cookies.set("refresh_token", user1_refresh)

    u1_sessions_resp = await client.get(
        "/sessions/",
        headers=auth_header(user1_data.access_token),
    )
    assert u1_sessions_resp.status_code == 200
    u1_sessions = validate_response(u1_sessions_resp, SessionsResponse).root

    assert u2_session_uuid not in u1_sessions


@pytest.mark.parametrize(
    "token, cookie_present, expected_status",
    [
        (None, True, 401),
        ("invalid_token", True, 401),
        ("valid", False, 401),
    ],
)
async def test_get_sessions_unauthorized(
    client: AsyncClient,
    user_factory,
    token: str | None,
    cookie_present: bool,
    expected_status: int,
):
    user_data, _ = await user_factory()

    headers = {}
    if token == "valid":
        headers = auth_header(user_data.access_token)
    elif token:
        headers = auth_header(token)

    if not cookie_present:
        client.cookies.delete("refresh_token")

    response = await client.get("/sessions/", headers=headers)
    assert response.status_code == expected_status


async def test_logout_success(client: AsyncClient, user_factory):
    user_data, register_response = await user_factory()
    access_token = user_data.access_token

    logout_response = await client.post(
        "/sessions/logout",
        headers=auth_header(access_token),
    )

    assert logout_response.status_code == 204
    assert logout_response.text == ""

    set_cookie_header = logout_response.headers.get("set-cookie", "")
    assert (
        'refresh_token=""' in set_cookie_header
        or "max-age=0" in set_cookie_header.lower()
    )
    assert (
        client.cookies.get("refresh_token") is None
        or client.cookies.get("refresh_token") == ""
    )

    old_refresh_token = register_response.cookies.get("refresh_token")
    client.cookies.set("refresh_token", old_refresh_token)
    subsequent_response = await client.get(
        "/sessions/",
        headers=auth_header(access_token),
    )
    assert subsequent_response.status_code == 401


async def test_logout_unauthorized(client: AsyncClient, user_factory):
    user_data, _ = await user_factory()
    access_token = user_data.access_token

    resp_no_auth = await client.post("/sessions/logout")
    assert resp_no_auth.status_code == 401

    client.cookies.delete("refresh_token")
    resp_no_cookie = await client.post(
        "/sessions/logout",
        headers=auth_header(access_token),
    )
    assert resp_no_cookie.status_code == 401


async def test_logout_other_user_session_forbidden(
    client: AsyncClient, user_factory, refresh_token: str
):
    user2_refresh_token = refresh_token

    user1_data, _ = await user_factory()

    client.cookies.set("refresh_token", user2_refresh_token)

    response = await client.post(
        "/sessions/logout",
        headers=auth_header(user1_data.access_token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_logout_all_within_24h_forbidden(
    client: AsyncClient, user_factory, freezer
):
    user_data, _ = await user_factory()
    access_token = user_data.access_token

    resp_immediate = await client.post(
        "/sessions/logout-all",
        headers=auth_header(access_token),
    )
    assert resp_immediate.status_code == 403
    assert resp_immediate.json()["error"]["code"] == "SESSION_TOO_EARLY"

    freezer.tick(timedelta(hours=23))
    refresh_response = await client.post("/auth/refresh")
    assert refresh_response.status_code == 200
    access_token = validate_response(refresh_response, AccessTokenSchema).access_token

    resp_23h = await client.post(
        "/sessions/logout-all",
        headers=auth_header(access_token),
    )
    assert resp_23h.status_code == 403
    assert resp_23h.json()["error"]["code"] == "SESSION_TOO_EARLY"

    sessions_response = await client.get(
        "/sessions/",
        headers=auth_header(access_token),
    )
    assert sessions_response.status_code == 200
    sessions = validate_response(sessions_response, SessionsResponse).root
    assert len(sessions) > 0


async def test_logout_all_after_24h_success(client: AsyncClient, user_factory, freezer):
    user_pass = "somepassword"
    user_data, _ = await user_factory(password=user_pass)

    login_response = await client.post(
        "/auth/login",
        json={"user_name": user_data.user.user_name, "password": user_pass},
    )
    assert login_response.status_code == 200
    validate_response(login_response, AuthResponse)

    freezer.tick(timedelta(hours=25))

    refresh_response = await client.post("/auth/refresh")
    assert refresh_response.status_code == 200
    access_token = validate_response(refresh_response, AccessTokenSchema).access_token

    response = await client.post(
        "/sessions/logout-all",
        headers=auth_header(access_token),
    )

    assert response.status_code == 204
    assert response.text == ""

    set_cookie_header = response.headers.get("set-cookie", "")
    assert (
        'refresh_token=""' in set_cookie_header
        or "max-age=0" in set_cookie_header.lower()
    )
    assert (
        client.cookies.get("refresh_token") is None
        or client.cookies.get("refresh_token") == ""
    )

    sessions_response = await client.get(
        "/sessions/",
        headers=auth_header(access_token),
    )
    assert sessions_response.status_code == 401


async def test_revoke_session_within_24h_forbidden(
    client: AsyncClient, user_factory, freezer
):
    user_pass = "somepassword"
    user_data, _ = await user_factory(password=user_pass)
    session1_access = user_data.access_token

    async with AsyncClient(
        transport=client._transport, base_url=str(client.base_url)
    ) as client_device2:
        login_response = await client_device2.post(
            "/auth/login",
            json={"user_name": user_data.user.user_name, "password": user_pass},
        )
        assert login_response.status_code == 200
        validate_response(login_response, AuthResponse)

    sessions_resp = await client.get(
        "/sessions/",
        headers=auth_header(session1_access),
    )
    assert sessions_resp.status_code == 200
    sessions = validate_response(sessions_resp, SessionsResponse).root
    assert len(sessions) == 2
    session2_uuid = next(uuid for uuid, info in sessions.items() if not info.is_current)

    resp_immediate = await client.delete(
        f"/sessions/revoke/{session2_uuid}",
        headers=auth_header(session1_access),
    )
    assert resp_immediate.status_code == 403
    assert resp_immediate.json()["error"]["code"] == "SESSION_TOO_EARLY"

    freezer.tick(timedelta(hours=23))
    refresh_response = await client.post("/auth/refresh")
    assert refresh_response.status_code == 200
    access_token = validate_response(refresh_response, AccessTokenSchema).access_token

    resp_23h = await client.delete(
        f"/sessions/revoke/{session2_uuid}",
        headers=auth_header(access_token),
    )
    assert resp_23h.status_code == 403
    assert resp_23h.json()["error"]["code"] == "SESSION_TOO_EARLY"

    sessions_check = await client.get(
        "/sessions/",
        headers=auth_header(access_token),
    )
    assert sessions_check.status_code == 200
    sessions_check_data = validate_response(sessions_check, SessionsResponse).root
    assert session2_uuid in sessions_check_data


async def test_revoke_session_after_24h_success(
    client: AsyncClient, user_factory, freezer
):
    user_pass = "somepassword"
    user_data, _ = await user_factory(password=user_pass)
    session1_access = user_data.access_token

    async with AsyncClient(
        transport=client._transport, base_url=str(client.base_url)
    ) as client_device2:
        login_response = await client_device2.post(
            "/auth/login",
            json={"user_name": user_data.user.user_name, "password": user_pass},
        )
        assert login_response.status_code == 200
        validate_response(login_response, AuthResponse)

    sessions_resp = await client.get(
        "/sessions/",
        headers=auth_header(session1_access),
    )
    assert sessions_resp.status_code == 200
    sessions = validate_response(sessions_resp, SessionsResponse).root
    session2_uuid = next(uuid for uuid, info in sessions.items() if not info.is_current)

    freezer.tick(timedelta(hours=25))

    refresh_response = await client.post("/auth/refresh")
    assert refresh_response.status_code == 200
    access_token = validate_response(refresh_response, AccessTokenSchema).access_token

    revoke_response = await client.delete(
        f"/sessions/revoke/{session2_uuid}",
        headers=auth_header(access_token),
    )
    assert revoke_response.status_code == 204
    assert revoke_response.text == ""

    sessions_after = await client.get(
        "/sessions/",
        headers=auth_header(access_token),
    )
    assert sessions_after.status_code == 200
    sessions_after_data = validate_response(sessions_after, SessionsResponse).root
    assert session2_uuid not in sessions_after_data
    assert len(sessions_after_data) == 1


async def test_revoke_non_existent_session(client: AsyncClient, user_factory):
    user_data, _ = await user_factory()
    access_token = user_data.access_token

    random_uuid = uuid.uuid4()
    response = await client.delete(
        f"/sessions/revoke/{random_uuid}",
        headers=auth_header(access_token),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"


async def test_revoke_expired_session(client: AsyncClient, user_factory):
    user_pass = "somepassword"
    user_data, _ = await user_factory(password=user_pass)
    session1_access = user_data.access_token

    async with AsyncClient(
        transport=client._transport, base_url=str(client.base_url)
    ) as client_device2:
        login_response = await client_device2.post(
            "/auth/login",
            json={"user_name": user_data.user.user_name, "password": user_pass},
        )
        assert login_response.status_code == 200
        auth_data = validate_response(login_response, AuthResponse)
        session2_access = auth_data.access_token

        sessions_resp = await client.get(
            "/sessions/",
            headers=auth_header(session1_access),
        )
        assert sessions_resp.status_code == 200
        sessions = validate_response(sessions_resp, SessionsResponse).root
        session2_uuid = next(
            uuid for uuid, info in sessions.items() if not info.is_current
        )

        logout_resp = await client_device2.post(
            "/sessions/logout",
            headers=auth_header(session2_access),
        )
        assert logout_resp.status_code == 204

    revoke_response = await client.delete(
        f"/sessions/revoke/{session2_uuid}",
        headers=auth_header(session1_access),
    )

    assert revoke_response.status_code == 401
    assert revoke_response.json()["error"]["code"] == "SESSION_EXPIRED"


async def test_revoke_other_user_session_forbidden(
    client: AsyncClient, user_factory, other_user_session_uuid: str
):
    user1_data, _ = await user_factory()
    user1_access = user1_data.access_token

    response = await client.delete(
        f"/sessions/revoke/{other_user_session_uuid}",
        headers=auth_header(user1_access),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert (
        response.json()["error"]["message"]
        == "You cannot revoke someone else's session"
    )

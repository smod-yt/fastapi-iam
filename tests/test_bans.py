from datetime import datetime, timedelta, timezone

from httpx import AsyncClient

from src.app.schemas.auth_schema import AuthResponse
from src.app.schemas.ban_schema import (
    PaginatedBanHistoryResponse,
    UserBanResponse,
)
from tests.utils import auth_header, validate_response


async def test_user_cannot_access_bans_endpoints(client: AsyncClient, user_factory):
    user, _ = await user_factory()

    resp_post = await client.post(
        "/bans/users",
        json={"user_id": user.user.id, "reason": "Test ban"},
        headers=auth_header(user.access_token),
    )
    assert resp_post.status_code == 403
    assert resp_post.json()["error"]["code"] == "FORBIDDEN"

    resp_get = await client.get(
        f"/bans/users/{user.user.id}",
        headers=auth_header(user.access_token),
    )
    assert resp_get.status_code == 403
    assert resp_get.json()["error"]["code"] == "FORBIDDEN"

    resp_delete = await client.delete(
        f"/bans/users/{user.user.id}",
        headers=auth_header(user.access_token),
    )
    assert resp_delete.status_code == 403
    assert resp_delete.json()["error"]["code"] == "FORBIDDEN"

    assert (
        await client.post("/bans/users", json={"user_id": user.user.id})
    ).status_code == 401
    assert (await client.get(f"/bans/users/{user.user.id}")).status_code == 401
    assert (await client.delete(f"/bans/users/{user.user.id}")).status_code == 401


async def test_admin_cannot_ban_admin(client: AsyncClient, admin_factory):
    admin1, _ = await admin_factory()
    admin2, _ = await admin_factory()

    response = await client.post(
        "/bans/users",
        json={"user_id": admin2.user.id, "reason": "Admin fight"},
        headers=auth_header(admin1.access_token),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"

    response_self = await client.post(
        "/bans/users",
        json={"user_id": admin1.user.id, "reason": "Self ban"},
        headers=auth_header(admin1.access_token),
    )
    assert response_self.status_code == 403
    assert response_self.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_can_ban_user_success(
    client: AsyncClient, admin_factory, user_factory
):
    admin, _ = await admin_factory()
    user, _ = await user_factory()

    response = await client.post(
        "/bans/users",
        json={"user_id": user.user.id, "reason": "Spam and abuse"},
        headers=auth_header(admin.access_token),
    )
    assert response.status_code == 201
    data = validate_response(response, UserBanResponse)
    assert data.user_id == user.user.id
    assert data.admin_id == admin.user.id
    assert data.is_banned is True
    assert data.reason == "Spam and abuse"
    assert data.revoked_at is None
    assert data.expires_at is None


async def test_ban_invalidates_sessions_and_blocks_active_jwt(
    client: AsyncClient, admin_factory, user_factory
):
    admin, _ = await admin_factory()
    user, user_register_resp = await user_factory()

    resp_before = await client.get(
        f"/users/{user.user.id}",
        headers=auth_header(user.access_token),
    )
    assert resp_before.status_code == 200

    resp_ban = await client.post(
        "/bans/users",
        json={"user_id": user.user.id, "reason": "Terms violation"},
        headers=auth_header(admin.access_token),
    )
    assert resp_ban.status_code == 201

    resp_after = await client.get(
        f"/users/{user.user.id}",
        headers=auth_header(user.access_token),
    )
    assert resp_after.status_code == 403
    assert resp_after.json()["error"]["code"] == "USER_BANNED"

    refresh_token = user_register_resp.cookies.get("refresh_token")
    client.cookies.set("refresh_token", refresh_token)
    resp_refresh = await client.post("/auth/refresh")
    assert resp_refresh.status_code in (401, 403)


async def test_cannot_ban_already_banned_user(
    client: AsyncClient, admin_factory, user_factory
):
    admin, _ = await admin_factory()
    user, _ = await user_factory()

    resp1 = await client.post(
        "/bans/users",
        json={"user_id": user.user.id, "reason": "First offense"},
        headers=auth_header(admin.access_token),
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/bans/users",
        json={"user_id": user.user.id, "reason": "Second offense"},
        headers=auth_header(admin.access_token),
    )
    assert resp2.status_code == 409
    error_data = resp2.json()["error"]
    assert error_data["code"] == "USER_ALREADY_BANNED"
    assert "details" in error_data
    assert error_data["details"]["user_id"] == user.user.id
    assert error_data["details"]["is_banned"] is True
    assert error_data["details"]["reason"] == "First offense"


async def test_revoke_ban_success(client: AsyncClient, admin_factory, user_factory):
    admin, _ = await admin_factory()
    user, _ = await user_factory(password="securepass123")

    resp_ban = await client.post(
        "/bans/users",
        json={"user_id": user.user.id, "reason": "Temporary ban"},
        headers=auth_header(admin.access_token),
    )
    assert resp_ban.status_code == 201

    resp_banned = await client.get(
        f"/users/{user.user.id}",
        headers=auth_header(user.access_token),
    )
    assert resp_banned.status_code == 403
    assert resp_banned.json()["error"]["code"] == "USER_BANNED"

    resp_revoke = await client.delete(
        f"/bans/users/{user.user.id}",
        headers=auth_header(admin.access_token),
    )
    assert resp_revoke.status_code == 204

    resp_revoke_again = await client.delete(
        f"/bans/users/{user.user.id}",
        headers=auth_header(admin.access_token),
    )
    assert resp_revoke_again.status_code == 204

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": user.user.user_name, "password": "securepass123"},
    )
    assert login_resp.status_code == 200
    new_auth = validate_response(login_resp, AuthResponse)

    resp_after = await client.get(
        f"/users/{user.user.id}",
        headers=auth_header(new_auth.access_token),
    )
    assert resp_after.status_code == 200
    assert resp_after.json()["id"] == user.user.id


async def test_ban_expires_successfully(
    client: AsyncClient, admin_factory, user_factory, freezer
):
    admin, _ = await admin_factory()
    user, _ = await user_factory(password="mypassword1")

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    resp_ban = await client.post(
        "/bans/users",
        json={
            "user_id": user.user.id,
            "reason": "Short timeout",
            "expires_at": expires_at.isoformat(),
        },
        headers=auth_header(admin.access_token),
    )
    assert resp_ban.status_code == 201

    resp_banned = await client.get(
        f"/users/{user.user.id}",
        headers=auth_header(user.access_token),
    )
    assert resp_banned.status_code == 403
    assert resp_banned.json()["error"]["code"] == "USER_BANNED"

    freezer.tick(timedelta(minutes=6))

    resp_active_jwt = await client.get(
        f"/users/{user.user.id}",
        headers=auth_header(user.access_token),
    )
    assert resp_active_jwt.status_code == 200
    assert resp_active_jwt.json()["id"] == user.user.id

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": user.user.user_name, "password": "mypassword1"},
    )
    assert login_resp.status_code == 200


async def test_multiple_bans_displayed_in_history(
    client: AsyncClient, admin_factory, user_factory
):
    admin, _ = await admin_factory()
    user, _ = await user_factory()

    resp_ban1 = await client.post(
        "/bans/users",
        json={"user_id": user.user.id, "reason": "First warning ban"},
        headers=auth_header(admin.access_token),
    )
    assert resp_ban1.status_code == 201

    resp_revoke1 = await client.delete(
        f"/bans/users/{user.user.id}",
        headers=auth_header(admin.access_token),
    )
    assert resp_revoke1.status_code == 204

    resp_ban2 = await client.post(
        "/bans/users",
        json={"user_id": user.user.id, "reason": "Second permanent ban"},
        headers=auth_header(admin.access_token),
    )
    assert resp_ban2.status_code == 201

    history_resp = await client.get(
        f"/bans/users/{user.user.id}",
        headers=auth_header(admin.access_token),
    )
    assert history_resp.status_code == 200
    history = validate_response(history_resp, PaginatedBanHistoryResponse)
    assert history.total == 2
    assert len(history.items) == 2
    assert history.page == 1
    assert history.limit == 10

    reasons = [ban.reason for ban in history.items]
    assert "First warning ban" in reasons
    assert "Second permanent ban" in reasons


async def test_ban_endpoints_user_not_found(client: AsyncClient, admin_factory):
    admin, _ = await admin_factory()
    non_existent_id = 999999

    resp_post = await client.post(
        "/bans/users",
        json={"user_id": non_existent_id, "reason": "Non-existent"},
        headers=auth_header(admin.access_token),
    )
    assert resp_post.status_code == 404
    assert resp_post.json()["error"]["code"] == "USER_NOT_FOUND"

    resp_get = await client.get(
        f"/bans/users/{non_existent_id}",
        headers=auth_header(admin.access_token),
    )
    assert resp_get.status_code == 404
    assert resp_get.json()["error"]["code"] == "USER_NOT_FOUND"

    resp_delete = await client.delete(
        f"/bans/users/{non_existent_id}",
        headers=auth_header(admin.access_token),
    )
    assert resp_delete.status_code == 404
    assert resp_delete.json()["error"]["code"] == "USER_NOT_FOUND"


async def test_ban_history_pagination(
    client: AsyncClient, admin_factory, user_factory
):
    admin, _ = await admin_factory()
    user, _ = await user_factory()

    for reason in ("First", "Second", "Third"):
        resp_ban = await client.post(
            "/bans/users",
            json={"user_id": user.user.id, "reason": reason},
            headers=auth_header(admin.access_token),
        )
        assert resp_ban.status_code == 201

        if reason != "Third":
            resp_revoke = await client.delete(
                f"/bans/users/{user.user.id}",
                headers=auth_header(admin.access_token),
            )
            assert resp_revoke.status_code == 204

    first_page_resp = await client.get(
        f"/bans/users/{user.user.id}",
        params={"page": 1, "limit": 2},
        headers=auth_header(admin.access_token),
    )
    assert first_page_resp.status_code == 200
    first_page = validate_response(first_page_resp, PaginatedBanHistoryResponse)
    assert first_page.total == 3
    assert first_page.page == 1
    assert first_page.limit == 2
    assert len(first_page.items) == 2
    assert [ban.reason for ban in first_page.items] == ["Third", "Second"]

    second_page_resp = await client.get(
        f"/bans/users/{user.user.id}",
        params={"page": 2, "limit": 2},
        headers=auth_header(admin.access_token),
    )
    assert second_page_resp.status_code == 200
    second_page = validate_response(second_page_resp, PaginatedBanHistoryResponse)
    assert second_page.total == 3
    assert second_page.page == 2
    assert second_page.limit == 2
    assert len(second_page.items) == 1
    assert second_page.items[0].reason == "First"


async def test_ban_history_pagination_query_validation(
    client: AsyncClient, admin_factory, user_factory
):
    admin, _ = await admin_factory()
    user, _ = await user_factory()

    invalid_params = (
        {"page": 0},
        {"limit": 0},
        {"limit": 101},
    )
    for params in invalid_params:
        response = await client.get(
            f"/bans/users/{user.user.id}",
            params=params,
            headers=auth_header(admin.access_token),
        )
        assert response.status_code == 422

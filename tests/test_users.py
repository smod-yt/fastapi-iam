from datetime import timedelta

from httpx import AsyncClient

from src.app.schemas.auth_schema import AccessTokenSchema, AuthResponse
from src.app.schemas.user_schema import PaginatedUsersResponse, UserResponse
from tests.utils import auth_header, validate_response


async def test_get_users_unauthorized(client: AsyncClient):
    response = await client.get("/users/")
    assert response.status_code == 401


async def test_get_users_success(client: AsyncClient, user_factory):
    user1, _ = await user_factory(name="Alice", user_name="alice_1")
    user2, _ = await user_factory(name="Bob", user_name="bob_1")

    response = await client.get(
        "/users/",
        headers=auth_header(user1.access_token),
    )
    assert response.status_code == 200
    data = validate_response(response, PaginatedUsersResponse)
    assert data.total >= 2
    assert data.page == 1
    assert data.limit == 10
    assert any(u.id == user1.user.id for u in data.items)
    assert any(u.id == user2.user.id for u in data.items)
    for u in data.items:
        assert "password" not in u.model_dump()


async def test_get_users_filtering_and_pagination(client: AsyncClient, user_factory):
    u1, _ = await user_factory(name="Charlie Chaplin", user_name="charlie_c")
    u2, _ = await user_factory(name="Charlie Brown", user_name="charlie_b")
    u3, _ = await user_factory(name="David Miller", user_name="david_m")

    resp_name = await client.get(
        "/users/?name=Charlie",
        headers=auth_header(u1.access_token),
    )
    assert resp_name.status_code == 200
    data_name = validate_response(resp_name, PaginatedUsersResponse)
    assert data_name.total == 2
    assert all("Charlie" in u.name for u in data_name.items)

    resp_uname = await client.get(
        "/users/?user_name=david",
        headers=auth_header(u1.access_token),
    )
    assert resp_uname.status_code == 200
    data_uname = validate_response(resp_uname, PaginatedUsersResponse)
    assert data_uname.total == 1
    assert data_uname.items[0].user_name == "david_m"

    resp_page = await client.get(
        "/users/?limit=1&page=2",
        headers=auth_header(u1.access_token),
    )
    assert resp_page.status_code == 200
    data_page = validate_response(resp_page, PaginatedUsersResponse)
    assert len(data_page.items) == 1
    assert data_page.page == 2
    assert data_page.limit == 1


async def test_get_user_by_id_success(client: AsyncClient, user_factory):
    user1, _ = await user_factory()
    user2, _ = await user_factory()

    response = await client.get(
        f"/users/{user2.user.id}",
        headers=auth_header(user1.access_token),
    )
    assert response.status_code == 200
    data = validate_response(response, UserResponse)
    assert data.id == user2.user.id
    assert data.name == user2.user.name
    assert data.user_name == user2.user.user_name


async def test_get_user_by_id_not_found(client: AsyncClient, user_factory):
    user1, _ = await user_factory()

    response = await client.get(
        "/users/999999",
        headers=auth_header(user1.access_token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "USER_NOT_FOUND"


async def test_get_me_success(client: AsyncClient, user_factory):
    user, _ = await user_factory()

    response = await client.get(
        "/users/me",
        headers=auth_header(user.access_token),
    )
    assert response.status_code == 200
    data = validate_response(response, UserResponse)
    assert data.id == user.user.id
    assert data.name == user.user.name
    assert data.user_name == user.user.user_name
    assert "password" not in response.json()


async def test_get_me_unauthorized(client: AsyncClient):
    response = await client.get("/users/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "JWT_NOT_GRANTED"


async def test_get_me_banned(client: AsyncClient, admin_factory, user_factory):
    admin, _ = await admin_factory()
    user, _ = await user_factory()

    ban_resp = await client.post(
        "/bans/users",
        json={"user_id": user.user.id, "reason": "Terms violation"},
        headers=auth_header(admin.access_token),
    )
    assert ban_resp.status_code == 201

    response = await client.get(
        "/users/me",
        headers=auth_header(user.access_token),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER_BANNED"


async def test_update_user_within_24h_forbidden(client: AsyncClient, user_factory):
    user1, _ = await user_factory()

    response = await client.patch(
        f"/users/{user1.user.id}",
        headers=auth_header(user1.access_token),
        json={"name": "New Name"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SESSION_TOO_EARLY"


async def test_update_user_after_24h_success(
    client: AsyncClient, user_factory, freezer
):
    user_pass = "somepass123"
    user_data, _ = await user_factory(password=user_pass)

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": user_data.user.user_name, "password": user_pass},
    )
    assert login_resp.status_code == 200

    freezer.tick(timedelta(hours=25))
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    access_token = validate_response(refresh_resp, AccessTokenSchema).access_token

    response = await client.patch(
        f"/users/{user_data.user.id}",
        headers=auth_header(access_token),
        json={"name": "Updated Name", "user_name": "updated_uname"},
    )
    assert response.status_code == 200
    data = validate_response(response, UserResponse)
    assert data.name == "Updated Name"
    assert data.user_name == "updated_uname"


async def test_update_user_duplicate_username_conflict(
    client: AsyncClient, user_factory, freezer
):
    u1_pass = "pass12345"
    u1, _ = await user_factory(password=u1_pass)
    u2, _ = await user_factory()

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": u1.user.user_name, "password": u1_pass},
    )
    assert login_resp.status_code == 200

    freezer.tick(timedelta(hours=25))
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    access_token = validate_response(refresh_resp, AccessTokenSchema).access_token

    response = await client.patch(
        f"/users/{u1.user.id}",
        headers=auth_header(access_token),
        json={"user_name": u2.user.user_name},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


async def test_update_user_other_user_forbidden(
    client: AsyncClient, user_factory, freezer
):
    u1_pass = "pass12345"
    u1, _ = await user_factory(password=u1_pass)
    u2, _ = await user_factory()

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": u1.user.user_name, "password": u1_pass},
    )
    assert login_resp.status_code == 200

    freezer.tick(timedelta(hours=25))
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    access_token = validate_response(refresh_resp, AccessTokenSchema).access_token

    response = await client.patch(
        f"/users/{u2.user.id}",
        headers=auth_header(access_token),
        json={"name": "Hacked Name"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_update_user_by_admin_success(
    client: AsyncClient, user_factory, admin_factory, freezer
):
    admin_pass = "adminpass123"
    admin_data, _ = await admin_factory(password=admin_pass)
    u2, _ = await user_factory()

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": admin_data.user.user_name, "password": admin_pass},
    )
    assert login_resp.status_code == 200

    freezer.tick(timedelta(hours=25))
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    access_token = validate_response(refresh_resp, AccessTokenSchema).access_token

    response = await client.patch(
        f"/users/{u2.user.id}",
        headers=auth_header(access_token),
        json={"name": "Admin Changed Name"},
    )
    assert response.status_code == 200
    data = validate_response(response, UserResponse)
    assert data.name == "Admin Changed Name"


async def test_update_user_validation_errors(
    client: AsyncClient, user_factory, freezer
):
    u_pass = "pass12345"
    u, _ = await user_factory(password=u_pass)

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": u.user.user_name, "password": u_pass},
    )
    assert login_resp.status_code == 200

    freezer.tick(timedelta(hours=25))
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    access_token = validate_response(refresh_resp, AccessTokenSchema).access_token

    empty_resp = await client.patch(
        f"/users/{u.user.id}",
        headers=auth_header(access_token),
        json={},
    )
    assert empty_resp.status_code == 422

    ws_resp = await client.patch(
        f"/users/{u.user.id}",
        headers=auth_header(access_token),
        json={"name": "   "},
    )
    assert ws_resp.status_code == 422


async def test_update_password_within_24h_forbidden(client: AsyncClient, user_factory):
    u, _ = await user_factory(password="oldpass123")

    response = await client.patch(
        f"/users/{u.user.id}/password",
        headers=auth_header(u.access_token),
        json={"old_password": "oldpass123", "new_password": "newpass123"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SESSION_TOO_EARLY"


async def test_update_password_incorrect_old_password(
    client: AsyncClient, user_factory, freezer
):
    old_pass = "oldpass123"
    u, _ = await user_factory(password=old_pass)

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": u.user.user_name, "password": old_pass},
    )
    assert login_resp.status_code == 200

    freezer.tick(timedelta(hours=25))
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    access_token = validate_response(refresh_resp, AccessTokenSchema).access_token

    response = await client.patch(
        f"/users/{u.user.id}/password",
        headers=auth_header(access_token),
        json={"old_password": "wrongpassword", "new_password": "newpass123"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_update_password_other_user_forbidden(
    client: AsyncClient, user_factory, freezer
):
    u1_pass = "pass12345"
    u1, _ = await user_factory(password=u1_pass)
    u2, _ = await user_factory(password="pass98765")

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": u1.user.user_name, "password": u1_pass},
    )
    assert login_resp.status_code == 200

    freezer.tick(timedelta(hours=25))
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    access_token = validate_response(refresh_resp, AccessTokenSchema).access_token

    response = await client.patch(
        f"/users/{u2.user.id}/password",
        headers=auth_header(access_token),
        json={"old_password": "pass98765", "new_password": "hackedpass123"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_update_password_success(client: AsyncClient, user_factory, freezer):
    old_pass = "originalpass123"
    new_pass = "brandnewpass123"
    u, _ = await user_factory(password=old_pass)

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": u.user.user_name, "password": old_pass},
    )
    assert login_resp.status_code == 200

    freezer.tick(timedelta(hours=25))
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    access_token = validate_response(refresh_resp, AccessTokenSchema).access_token

    response = await client.patch(
        f"/users/{u.user.id}/password",
        headers=auth_header(access_token),
        json={"old_password": old_pass, "new_password": new_pass},
    )
    assert response.status_code == 204
    assert response.text == ""

    old_login = await client.post(
        "/auth/login",
        json={"user_name": u.user.user_name, "password": old_pass},
    )
    assert old_login.status_code == 401
    assert old_login.json()["error"]["code"] == "INVALID_CREDENTIALS"

    new_login = await client.post(
        "/auth/login",
        json={"user_name": u.user.user_name, "password": new_pass},
    )
    assert new_login.status_code == 200
    validate_response(new_login, AuthResponse)


async def test_delete_user_within_24h_forbidden(client: AsyncClient, user_factory):
    u, _ = await user_factory()

    response = await client.delete(
        f"/users/{u.user.id}",
        headers=auth_header(u.access_token),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SESSION_TOO_EARLY"


async def test_delete_user_other_user_forbidden(
    client: AsyncClient, user_factory, freezer
):
    u1_pass = "pass12345"
    u1, _ = await user_factory(password=u1_pass)
    u2, _ = await user_factory()

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": u1.user.user_name, "password": u1_pass},
    )
    assert login_resp.status_code == 200

    freezer.tick(timedelta(hours=25))
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    access_token = validate_response(refresh_resp, AccessTokenSchema).access_token

    response = await client.delete(
        f"/users/{u2.user.id}",
        headers=auth_header(access_token),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_delete_user_self_success(client: AsyncClient, user_factory, freezer):
    u_pass = "pass12345"
    u, _ = await user_factory(password=u_pass)

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": u.user.user_name, "password": u_pass},
    )
    assert login_resp.status_code == 200

    freezer.tick(timedelta(hours=25))
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    access_token = validate_response(refresh_resp, AccessTokenSchema).access_token

    response = await client.delete(
        f"/users/{u.user.id}",
        headers=auth_header(access_token),
    )
    assert response.status_code == 204
    assert response.text == ""

    set_cookie_header = response.headers.get("set-cookie", "")
    assert 'refresh_token=""' in set_cookie_header

    admin_login = await client.post(
        "/auth/login",
        json={"user_name": "admin", "password": "admin"},
    )
    if admin_login.status_code == 200:
        admin_token = admin_login.json()["access_token"]
        get_user = await client.get(
            f"/users/{u.user.id}",
            headers=auth_header(admin_token),
        )
        assert get_user.status_code == 404


async def test_delete_user_by_admin_success(
    client: AsyncClient, user_factory, admin_factory, freezer
):
    admin_pass = "adminpass123"
    admin_data, _ = await admin_factory(password=admin_pass)
    target_user, _ = await user_factory()

    login_resp = await client.post(
        "/auth/login",
        json={"user_name": admin_data.user.user_name, "password": admin_pass},
    )
    assert login_resp.status_code == 200

    freezer.tick(timedelta(hours=25))
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    access_token = validate_response(refresh_resp, AccessTokenSchema).access_token

    response = await client.delete(
        f"/users/{target_user.user.id}",
        headers=auth_header(access_token),
    )
    assert response.status_code == 204

    set_cookie_header = response.headers.get("set-cookie", "")
    assert 'refresh_token=""' not in set_cookie_header

    get_user = await client.get(
        f"/users/{target_user.user.id}",
        headers=auth_header(access_token),
    )
    assert get_user.status_code == 404


async def test_admin_can_assign_user_role(client: AsyncClient, admin_factory, user_factory):
    admin, _ = await admin_factory()
    user, _ = await user_factory()

    response = await client.patch(
        f"/users/{user.user.id}/role",
        headers=auth_header(admin.access_token),
        json={"role": "moderator"},
    )

    assert response.status_code == 200
    assert response.json() == {"id": user.user.id, "role": "moderator"}


async def test_non_admin_cannot_assign_user_role(client: AsyncClient, user_factory):
    actor, _ = await user_factory()
    target, _ = await user_factory()

    response = await client.patch(
        f"/users/{target.user.id}/role",
        headers=auth_header(actor.access_token),
        json={"role": "admin"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_cannot_change_another_admin_role(
    client: AsyncClient, admin_factory
):
    admin1, _ = await admin_factory()
    admin2, _ = await admin_factory()

    response = await client.patch(
        f"/users/{admin2.user.id}/role",
        headers=auth_header(admin1.access_token),
        json={"role": "user"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "You cannot modify another administrator"


async def test_admin_cannot_update_or_delete_another_admin(
    client: AsyncClient, admin_factory, freezer
):
    admin1, _ = await admin_factory(password="adminpass123")
    admin2, _ = await admin_factory()
    login = await client.post(
        "/auth/login",
        json={"user_name": admin1.user.user_name, "password": "adminpass123"},
    )
    assert login.status_code == 200

    freezer.tick(timedelta(hours=25))
    refreshed = await client.post("/auth/refresh")
    access_token = validate_response(refreshed, AccessTokenSchema).access_token

    profile_response = await client.patch(
        f"/users/{admin2.user.id}",
        headers=auth_header(access_token),
        json={"name": "Changed Admin"},
    )
    assert profile_response.status_code == 403
    assert profile_response.json()["error"]["message"] == "You cannot modify another administrator"

    delete_response = await client.delete(
        f"/users/{admin2.user.id}", headers=auth_header(access_token)
    )
    assert delete_response.status_code == 403

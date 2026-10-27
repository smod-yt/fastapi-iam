from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from src.app.db import AsyncSessionDep
from src.app.models import User
from src.app.models.user_model import UserRoles
from src.app.repositories import token_repository
from src.app.services import ban_service, session_service, user_service
from src.app.utils import hash
from src.app.utils.exceptions import (
    Forbidden,
    JWTNotGranted,
    RefreshTokenNotGranted,
    UserBanned,
    UserNotFound,
)

security_scheme = HTTPBearer(auto_error=False)


async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


RedisSessionDep = Annotated[aioredis.Redis, Depends(get_redis)]


async def get_refresh_token(request: Request) -> str:
    refresh_token = request.cookies.get("refresh_token")

    if refresh_token is None:
        raise RefreshTokenNotGranted

    return refresh_token


async def get_user_id_from_jwt(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> int:
    if credentials is None:
        raise JWTNotGranted
    access_token = credentials.credentials

    return hash.get_user_id_from_jwt(access_token)


async def get_current_user(
    session: AsyncSessionDep,
    redis: RedisSessionDep,
    user_id: int = Depends(get_user_id_from_jwt),
) -> User:
    user = await session.get(User, user_id)

    if user is None:
        raise UserNotFound("Current user not found")

    active_ban = await ban_service.get_active_ban_cached(session, redis, user.id)
    if active_ban is not None:
        logger.warning(
            f"Banned user {user.id} ('{user.user_name}') attempted to access API (ban reason: '{active_ban['reason']}')"
        )
        raise UserBanned(
            message="User is banned",
            details={
                "reason": active_ban["reason"],
                "expires_at": active_ban["expires_at"],
            },
        )

    return user


def require_role(require_role: UserRoles) -> User:
    def role_check(user: User = Depends(get_current_user)):
        if user.role.weight < require_role.weight:
            logger.warning(
                f"Access denied: user {user.id} ('{user.user_name}', role={user.role.value}) lacks required role {require_role.value}"
            )
            raise Forbidden("You don't have permissions for this action")
        return user

    return role_check


async def check_user_access(
    user_id: int,
    current_user: User = Depends(get_current_user),
) -> User:
    user_service.check_user_access(current_user, user_id)
    return current_user


async def check_session_age(
    redis: RedisSessionDep,
    refresh_token: str = Depends(get_refresh_token),
) -> None:
    session_uuid = await token_repository.get_session_uuid_from_refresh(
        redis, refresh_token
    )
    await session_service.check_session_age(redis, session_uuid)

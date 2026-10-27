from fastapi import Request
from loguru import logger
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.repositories import auth_repository, token_repository
from src.app.schemas.auth_schema import LoginSchema, RegisterSchema
from src.app.services import token_service
from src.app.utils import hash
from src.app.utils.exceptions import InvalidCredentials


async def register(
    session: AsyncSession, data: RegisterSchema, request: Request, redis: Redis
):
    name = data.name.strip()
    user_name = data.user_name.strip()

    password = data.password
    hashed_password = await hash.hash_password(password)

    new_user = await auth_repository.register(session, name, user_name, hashed_password)

    raw_token, access_token = await token_service.create_and_save_tokens(
        redis, request, new_user.id
    )

    return new_user, raw_token, access_token


async def login(
    session: AsyncSession, data: LoginSchema, request: Request, redis: Redis
):
    user_name = data.user_name.strip()
    password = data.password

    user = await auth_repository.login(session, user_name)

    if not await hash.check_password(password, user.password):
        logger.warning(f'Failed login attempt for user "{user.user_name}"')
        raise InvalidCredentials

    raw_token, access_token = await token_service.create_and_save_tokens(
        redis, request, user.id
    )
    await token_repository.delete_expired_sessions(redis, user.id)

    return user, raw_token, access_token


async def refresh(request: Request, redis: Redis, refresh_token: str):
    session_uuid = await token_repository.get_session_uuid_from_refresh(
        redis, refresh_token
    )
    session_data = await token_service.get_session_data(redis, session_uuid)
    user_id = session_data["user_id"]
    created_at = session_data["created_at"]

    await token_service.delete_session(redis, session_uuid, user_id)
    raw_token, access = await token_service.create_and_save_tokens(
        redis, request, user_id, session_uuid, created_at
    )

    return raw_token, access

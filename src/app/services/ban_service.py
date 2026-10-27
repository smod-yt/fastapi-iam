import json
from datetime import datetime, timezone

from loguru import logger
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models import User
from src.app.models.user_ban_model import UserBan
from src.app.models.user_model import UserRoles
from src.app.repositories import ban_repository, token_repository, user_repository
from src.app.schemas.ban_schema import BanUserSchema, UserBanResponse
from src.app.utils.exceptions import Forbidden, UserAlreadyBanned, UserNotFound

BAN_CACHE_PREFIX = "user_ban:"
NEGATIVE_BAN_CACHE_TTL = 30
MAX_BAN_CACHE_TTL = 300


def _ban_cache_key(user_id: int) -> str:
    return f"{BAN_CACHE_PREFIX}{user_id}"


async def get_active_ban_cached(
    session: AsyncSession, redis: Redis, user_id: int
) -> dict | None:
    key = _ban_cache_key(user_id)
    try:
        cached = await redis.get(key)
        if cached is not None:
            value = json.loads(cached)
            if not value.get("banned"):
                return None
            expires_at = value.get("expires_at")
            if expires_at is None or datetime.fromisoformat(expires_at) > datetime.now(
                timezone.utc
            ):
                return value
            await redis.delete(key)
    except (RedisError, ValueError, AttributeError) as error:
        logger.warning(f"Ban cache read failed for user {user_id}: {error}")

    active_ban = await ban_repository.get_active_ban(session, user_id)
    if active_ban is None:
        payload = {"banned": False}
        ttl = NEGATIVE_BAN_CACHE_TTL
        result = None
    else:
        result = {
            "banned": True,
            "reason": active_ban.reason,
            "expires_at": active_ban.expires_at.isoformat()
            if active_ban.expires_at
            else None,
        }
        payload = result
        if active_ban.expires_at is None:
            ttl = MAX_BAN_CACHE_TTL
        else:
            remaining = (active_ban.expires_at - datetime.now(timezone.utc)).total_seconds()
            ttl = max(1, min(MAX_BAN_CACHE_TTL, int(remaining)))
    try:
        await redis.set(key, json.dumps(payload), ex=ttl)
    except RedisError as error:
        logger.warning(f"Ban cache write failed for user {user_id}: {error}")
    return result


async def _cache_active_ban(redis: Redis, ban: UserBan) -> None:
    payload = {
        "banned": True,
        "reason": ban.reason,
        "expires_at": ban.expires_at.isoformat() if ban.expires_at else None,
    }
    if ban.expires_at is None:
        ttl = MAX_BAN_CACHE_TTL
    else:
        remaining = (ban.expires_at - datetime.now(timezone.utc)).total_seconds()
        ttl = max(1, min(MAX_BAN_CACHE_TTL, int(remaining)))
    try:
        await redis.set(_ban_cache_key(ban.user_id), json.dumps(payload), ex=ttl)
    except RedisError as error:
        logger.warning(f"Ban cache update failed for user {ban.user_id}: {error}")


async def ban_user(
    session: AsyncSession,
    redis: Redis,
    admin: User,
    data: BanUserSchema,
) -> UserBan:
    target_user = await user_repository.get_user_by_id(session, data.user_id)
    if target_user is None:
        logger.warning(
            f"Admin {admin.id} ('{admin.user_name}') failed to ban user {data.user_id}: user not found"
        )
        raise UserNotFound("User not found")

    if target_user.role == UserRoles.ADMIN:
        logger.warning(
            f"Admin {admin.id} ('{admin.user_name}') attempted to ban admin {target_user.id} ('{target_user.user_name}')"
        )
        raise Forbidden("Admins cannot be banned")

    active_ban = await ban_repository.get_active_ban(session, data.user_id)
    if active_ban is not None:
        logger.warning(
            f"Admin {admin.id} ('{admin.user_name}') attempted to ban user {target_user.id} ('{target_user.user_name}'), but user is already banned (ban_id={active_ban.id})"
        )
        raise UserAlreadyBanned(
            message="User is already banned",
            details=UserBanResponse.model_validate(active_ban).model_dump(mode="json"),
        )

    target_user_id = target_user.id
    target_user_name = target_user.user_name
    admin_id = admin.id
    admin_user_name = admin.user_name

    ban = await ban_repository.create_ban(
        session=session,
        admin_id=admin_id,
        user_id=data.user_id,
        reason=data.reason,
        expires_at=data.expires_at,
    )

    await _cache_active_ban(redis, ban)

    await token_repository.delete_all_user_sessions(redis, data.user_id)
    logger.info(
        f"User {target_user_id} ('{target_user_name}') was banned by admin {admin_id} ('{admin_user_name}'). "
        f"Ban ID: {ban.id}, reason: '{ban.reason}', expires_at: {ban.expires_at}"
    )

    return ban


async def get_ban_history(
    session: AsyncSession,
    user_id: int,
    page: int = 1,
    limit: int = 10,
) -> tuple[list[UserBan], int]:
    target_user = await user_repository.get_user_by_id(session, user_id)
    if target_user is None:
        logger.warning(f"Failed to get ban history: user {user_id} not found")
        raise UserNotFound("User not found")

    bans, total = await ban_repository.get_user_bans(
        session, user_id, page=page, limit=limit
    )
    logger.debug(
        f"Retrieved {len(bans)} of {total} ban record(s) for user {user_id}"
    )
    return bans, total


async def unban_user(
    session: AsyncSession,
    user_id: int,
    redis: Redis,
    admin: User | None = None,
) -> None:
    target_user = await user_repository.get_user_by_id(session, user_id)
    if target_user is None:
        admin_info = f" by admin {admin.id} ('{admin.user_name}')" if admin else ""
        logger.warning(f"Failed to unban user {user_id}{admin_info}: user not found")
        raise UserNotFound("User not found")

    if target_user.role == UserRoles.ADMIN and target_user.id != (admin.id if admin else None):
        logger.warning(f"Attempt to change ban status of admin {target_user.id}")
        raise Forbidden("Admins cannot change another admin's status")

    target_user_name = target_user.user_name
    admin_info = (
        f" by admin {admin.id} ('{admin.user_name}')" if admin is not None else ""
    )

    revoked_ban = await ban_repository.revoke_active_ban(session, user_id)
    try:
        await redis.delete(_ban_cache_key(user_id))
    except RedisError as error:
        logger.warning(f"Ban cache invalidation failed for user {user_id}: {error}")
    if revoked_ban:
        logger.info(
            f"Active ban (ban_id={revoked_ban.id}) revoked for user {user_id} ('{target_user_name}'){admin_info}"
        )
    else:
        logger.info(
            f"No active ban to revoke for user {user_id} ('{target_user_name}'){admin_info}"
        )

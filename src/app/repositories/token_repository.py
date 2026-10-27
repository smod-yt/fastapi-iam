import json
from datetime import datetime, timezone

from loguru import logger
from redis.asyncio import Redis

from src.app.utils import hash
from src.app.utils.exceptions import SessionExpired


async def save_session(
    redis: Redis,
    refresh_token: str,
    session_uuid: str,
    user_id: int,
    ttl: int,
    session_data: str,
) -> None:
    await redis.set(f"session:{session_uuid}", session_data, ttl)
    await redis.set(f"refresh:{refresh_token}", session_uuid, ttl)
    logger.debug(f"Refresh token for user with id: {user_id} successflly created")

    current_time = int(datetime.now(timezone.utc).timestamp())
    expires_time = current_time + ttl

    await redis.zadd(f"user:{user_id}:sessions", {session_uuid: expires_time})
    logger.debug(
        f"Session successfully added to user sessons list (user id: {user_id})"
    )


async def get_session_uuid_from_refresh(redis: Redis, refresh_token: str) -> str:
    token_hash = hash.hash_refresh_token(refresh_token)
    session_uuid = await redis.get(f"refresh:{token_hash}")

    if session_uuid is None:
        raise SessionExpired

    return session_uuid


async def get_user_sessions(redis: Redis, user_id: int) -> dict:
    await delete_expired_sessions(redis, user_id)

    sessions_uuids = await redis.zrange(f"user:{user_id}:sessions", 0, -1)

    async with redis.pipeline() as pipe:
        for session in sessions_uuids:
            await pipe.get(f"session:{session}")

        sessions = await pipe.execute()

    return dict(zip(sessions_uuids, sessions))


async def get_session_data(redis: Redis, session_uuid: str) -> str:
    session_data = await redis.get(f"session:{session_uuid}")

    if session_data is None:
        raise SessionExpired

    return json.loads(session_data)


async def delete_expired_sessions(redis: Redis, user_id: int) -> None:
    current_time = int(datetime.now(timezone.utc).timestamp())

    deleted_sessions = await redis.zremrangebyscore(
        f"user:{user_id}:sessions", -1, current_time
    )

    if deleted_sessions > 0:
        logger.debug(
            f"Successfully deleted {deleted_sessions} expired sessions of user with id: {user_id}"
        )


async def delete_session(redis: Redis, session_uuid: str, user_id: int) -> None:
    session_data = await get_session_data(redis, session_uuid)
    token_hash = session_data["token_hash"]

    if await redis.delete(f"session:{session_uuid}") > 0:
        await redis.zrem(f"user:{user_id}:sessions", f"{session_uuid}")
        await redis.delete(f"refresh:{token_hash}")
        logger.debug(f"Session of user with id: {user_id} deleted")


async def delete_all_user_sessions(redis: Redis, user_id: int) -> None:
    sessions_uuids = await redis.zrange(f"user:{user_id}:sessions", 0, -1)

    async with redis.pipeline() as pipe:
        for session in sessions_uuids:
            pipe.get(f"session:{session}")

        sessions = await pipe.execute()

    async with redis.pipeline() as pipe:
        for session_uuid, session in zip(sessions_uuids, sessions):
            if session is None:
                continue

            token_hash = json.loads(session)["token_hash"]

            pipe.delete(f"refresh:{token_hash}")
            pipe.delete(f"session:{session_uuid}")

        pipe.delete(f"user:{user_id}:sessions")

        await pipe.execute()

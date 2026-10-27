import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from redis.asyncio import Redis

from src.app.models import User
from src.app.repositories import token_repository
from src.app.schemas.auth_schema import SessionReadSchema
from src.app.services import token_service, user_service
from src.app.utils.exceptions import SessionTooEarly


async def check_session_age(
    redis: Redis, current_session_uuid: UUID | str, min_age_hours: int = 24
) -> None:
    time_now = datetime.now(timezone.utc)
    session_data = await token_repository.get_session_data(
        redis, str(current_session_uuid)
    )
    target_time = datetime.fromtimestamp(
        int(session_data["created_at"]), tz=timezone.utc
    ) + timedelta(hours=min_age_hours)

    if time_now < target_time:
        raise SessionTooEarly


async def check_revoke_access(redis: Redis, current_session_uuid: UUID | str) -> None:
    await check_session_age(redis, current_session_uuid)


async def get_user_sessions(
    redis: Redis, current_user: User, current_session_uuid: UUID
) -> dict:
    raw_sessions = await token_repository.get_user_sessions(redis, current_user.id)

    sessions = {}

    for session_uuid, raw_data in raw_sessions.items():
        if not raw_data:
            continue

        data = json.loads(raw_data)
        data["is_current"] = current_session_uuid == str(session_uuid)

        sessions[session_uuid] = SessionReadSchema.model_validate(data)

    return sessions


async def logout(redis: Redis, current_user: User, refresh_token: str) -> None:
    session_uuid = await token_repository.get_session_uuid_from_refresh(
        redis, refresh_token
    )
    session_data = await token_service.get_session_data(redis, session_uuid)
    target_user_id = session_data["user_id"]

    user_service.check_user_access(
        current_user, target_user_id, "You can't log out from someone else's session"
    )

    await token_service.delete_session(redis, session_uuid, target_user_id)


async def revoke_session(
    redis: Redis, current_user: User, refresh_token: str, session_uuid: UUID
) -> None:
    session_data = await token_service.get_session_data(redis, str(session_uuid))
    target_user_id = session_data["user_id"]

    current_session_uuid = await token_repository.get_session_uuid_from_refresh(
        redis, refresh_token
    )

    user_service.check_user_access(
        current_user, target_user_id, "You cannot revoke someone else's session"
    )

    await check_session_age(redis, current_session_uuid)

    await token_repository.delete_session(redis, session_uuid, current_user.id)


async def logout_all(redis: Redis, refresh_token: str, current_user: User) -> None:
    current_session_uuid = await token_repository.get_session_uuid_from_refresh(
        redis, refresh_token
    )

    await check_session_age(redis, current_session_uuid)

    await token_repository.delete_all_user_sessions(redis, current_user.id)

from loguru import logger
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models import User
from src.app.models.user_model import UserRoles
from src.app.repositories import token_repository, user_repository
from src.app.schemas.user_schema import (
    UserUpdatePasswordSchema,
    UserUpdateSchema,
)
from src.app.utils import hash
from src.app.utils.exceptions import Conflict, Forbidden, InvalidCredentials, UserNotFound


def ensure_not_other_admin(actor: User, target: User) -> None:
    if target.role == UserRoles.ADMIN and target.id != actor.id:
        logger.warning(
            f"Admin {actor.id} attempted to change protected admin {target.id}"
        )
        raise Forbidden("You cannot modify another administrator")


def check_user_access(
    current_user: User, target_user_id: int, error_msg: str | None = None
) -> bool:
    if current_user.role.weight >= UserRoles.ADMIN.weight or current_user.id == target_user_id:
        return True
    else:
        logger.warning(
            f"Access denied: user {current_user.id} ('{current_user.user_name}') "
            f"attempted to access user {target_user_id}"
        )
        raise Forbidden(message=error_msg)


async def get_users(
    session: AsyncSession,
    page: int = 1,
    limit: int = 10,
    name: str | None = None,
    user_name: str | None = None,
) -> tuple[list[User], int]:
    return await user_repository.get_users(
        session, page=page, limit=limit, name=name, user_name=user_name
    )


async def get_user_by_id(session: AsyncSession, user_id: int) -> User:
    user = await user_repository.get_user_by_id(session, user_id)
    if user is None:
        logger.debug(f"User with id {user_id} not found")
        raise UserNotFound
    return user


async def get_user_by_user_name(session: AsyncSession, user_name: str) -> User | None:
    return await user_repository.get_user_by_user_name(session, user_name)


async def update_user_role(
    session: AsyncSession, user: User, role: UserRoles, actor: User
) -> User:
    ensure_not_other_admin(actor, user)
    actor_id = actor.id
    user = await user_repository.update_user_role(session, user, role)
    logger.info(
        f"User {user.id} ('{user.user_name}') role changed to {role.value} by admin {actor_id}"
    )
    return user


async def update_user(
    session: AsyncSession,
    user: User,
    data: UserUpdateSchema,
    actor: User,
) -> User:
    ensure_not_other_admin(actor, user)
    name = data.name.strip() if data.name is not None else None
    user_name = data.user_name.strip() if data.user_name is not None else None

    if user_name is not None and user_name != user.user_name:
        existing = await user_repository.get_user_by_user_name(session, user_name)
        if existing is not None and existing.id != user.id:
            logger.warning(
                f"Failed to update user {user.id}: username '{user_name}' is already taken"
            )
            raise Conflict(message="This user name is already taken")

    updated_user = await user_repository.update_user(
        session, user, name=name, user_name=user_name
    )
    logger.info(
        f"User {user.id} profile updated: name='{updated_user.name}', user_name='{updated_user.user_name}'"
    )
    return updated_user


async def update_user_password(
    session: AsyncSession,
    user: User,
    data: UserUpdatePasswordSchema,
    actor: User,
) -> None:
    ensure_not_other_admin(actor, user)
    if not await hash.check_password(data.old_password, user.password):
        logger.warning(
            f"Password update failed for user {user.id} ('{user.user_name}'): invalid old password"
        )
        raise InvalidCredentials(message="Incorrect old password")

    user_id = user.id
    user_name = user.user_name
    hashed_password = await hash.hash_password(data.new_password)
    await user_repository.update_user_password(session, user, hashed_password)
    logger.info(f"Password successfully updated for user {user_id} ('{user_name}')")


async def delete_user(
    session: AsyncSession,
    redis: Redis,
    user: User,
    actor: User,
) -> None:
    ensure_not_other_admin(actor, user)
    user_id = user.id
    user_name = user.user_name
    await token_repository.delete_all_user_sessions(redis, user_id)
    await user_repository.delete_user(session, user)
    logger.info(f"User {user_id} ('{user_name}') deleted and all sessions invalidated")


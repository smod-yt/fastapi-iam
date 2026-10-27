from loguru import logger
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.app.models import User
from src.app.models.user_model import UserRoles
from src.app.settings import settings
from src.app.utils.exceptions import Conflict
from src.app.utils.hash import hash_password



async def create_first_admin_if_not_exists(session: AsyncSession):
    query = await session.execute(select(User).where(User.role == UserRoles.ADMIN))
    admin = query.scalar_one_or_none()

    if admin is not None:
        logger.debug("The admin already exists")
        return

    logger.info("No admins found, creating the first admin...")

    admin_name = settings.FIRST_ADMIN_DEFAULT_NAME
    admin_user_name = settings.FIRST_ADMIN_DEFAULT_USER_NAME
    admin_hashed_password = await hash_password(settings.FIRST_ADMIN_DEFAULT_PASSWORD)

    try:
        first_admin = User(
            name=admin_name,
            user_name=admin_user_name,
            role=UserRoles.ADMIN,
            password=admin_hashed_password,
        )

        session.add(first_admin)
        await session.commit()
        logger.info(f"The first admin ({admin_user_name}) successfully created")
    except IntegrityError:
        await session.rollback()
        logger.warning(
            "Failed to create first admin, user with the same user_name already exists"
        )
    except Exception as e:
        await session.rollback()
        logger.exception(
            f"An unexpected error occurred while creating the first admin: {e}"
        )


async def get_users(
    session: AsyncSession,
    page: int = 1,
    limit: int = 10,
    name: str | None = None,
    user_name: str | None = None,
) -> tuple[list[User], int]:
    conditions = []
    if name:
        conditions.append(User.name.ilike(f"%{name.strip()}%"))
    if user_name:
        conditions.append(User.user_name.ilike(f"%{user_name.strip()}%"))

    count_stmt = select(func.count(User.id))
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = select(User)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(User.id).offset((page - 1) * limit).limit(limit)
    result = await session.execute(stmt)
    users = list(result.scalars().all())

    return users, total


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_user_name(session: AsyncSession, user_name: str) -> User | None:
    query = await session.execute(select(User).where(User.user_name == user_name))
    return query.scalar_one_or_none()


async def update_user(
    session: AsyncSession,
    user: User,
    name: str | None = None,
    user_name: str | None = None,
) -> User:
    if name is not None:
        user.name = name
    if user_name is not None:
        user.user_name = user_name

    session.add(user)
    try:
        await session.commit()
        await session.refresh(user)
        return user
    except IntegrityError:
        await session.rollback()
        logger.warning(
            f"IntegrityError while updating user {user.id}: username '{user_name}' already taken"
        )
        raise Conflict(message="This user name is already taken")


async def update_user_password(
    session: AsyncSession,
    user: User,
    hashed_password: str,
) -> User:
    user.password = hashed_password
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user_role(
    session: AsyncSession, user: User, role: UserRoles
) -> User:
    user.role = role
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user: User) -> None:
    await session.delete(user)
    await session.commit()
    logger.debug(f"User {user.id} deleted from database")


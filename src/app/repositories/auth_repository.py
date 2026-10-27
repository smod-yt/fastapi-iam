from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models import User
from src.app.utils.exceptions import Conflict, InvalidCredentials


async def register(
    session: AsyncSession, name: str, user_name: str, hashed_password: str
) -> User:
    new_user = User(name=name, user_name=user_name, password=hashed_password)

    try:
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        logger.info(
            f'User with user_name "{new_user.user_name}" (id: {new_user.id}) succesfully registered'
        )
        return new_user
    except IntegrityError:
        await session.rollback()
        logger.warning(
            f'Failed registration attempt, user_name "{user_name}" is already taken'
        )
        raise Conflict(message="This user name is already taken")


async def login(session: AsyncSession, user_name: str) -> User:
    query = await session.execute(select(User).where(User.user_name == user_name))
    user = query.scalar_one_or_none()

    if user is None:
        logger.debug(f'User "{user_name}" not found')
        raise InvalidCredentials

    return user

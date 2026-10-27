from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import or_, select

from src.app.models.user_ban_model import UserBan


async def get_active_ban(session: AsyncSession, user_id: int) -> UserBan | None:
    now = datetime.now(timezone.utc)
    statement = (
        select(UserBan)
        .where(
            UserBan.user_id == user_id,
            UserBan.is_banned == True,  # noqa: E712
            UserBan.revoked_at.is_(None),
            or_(UserBan.expires_at.is_(None), UserBan.expires_at > now),
        )
        .order_by(UserBan.created_at.desc(), UserBan.id.desc())
        .limit(1)
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def create_ban(
    session: AsyncSession,
    admin_id: int,
    user_id: int,
    reason: str,
    expires_at: datetime | None = None,
) -> UserBan:
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    ban = UserBan(
        user_id=user_id,
        admin_id=admin_id,
        is_banned=True,
        reason=reason,
        created_at=datetime.now(timezone.utc),
        expires_at=expires_at,
        revoked_at=None,
    )
    session.add(ban)
    await session.commit()
    await session.refresh(ban)
    logger.debug(
        f"Ban record #{ban.id} created in DB for user {user_id} by admin {admin_id}"
    )
    return ban


async def get_user_bans(
    session: AsyncSession,
    user_id: int,
    page: int = 1,
    limit: int = 10,
) -> tuple[list[UserBan], int]:
    count_statement = select(func.count(UserBan.id)).where(UserBan.user_id == user_id)
    total = (await session.execute(count_statement)).scalar_one()

    statement = (
        select(UserBan)
        .where(UserBan.user_id == user_id)
        .order_by(UserBan.created_at.desc(), UserBan.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await session.execute(statement)
    return list(result.scalars().all()), total


async def revoke_active_ban(session: AsyncSession, user_id: int) -> UserBan | None:
    now = datetime.now(timezone.utc)
    statement = (
        select(UserBan)
        .where(
            UserBan.user_id == user_id,
            UserBan.is_banned == True,  # noqa: E712
            UserBan.revoked_at.is_(None),
            or_(UserBan.expires_at.is_(None), UserBan.expires_at > now),
        )
        .order_by(UserBan.created_at.desc(), UserBan.id.desc())
    )
    result = await session.execute(statement)
    active_bans = list(result.scalars().all())
    if not active_bans:
        logger.debug(f"No active bans found in DB to revoke for user {user_id}")
        return None

    for ban in active_bans:
        ban.is_banned = False
        ban.revoked_at = now
        session.add(ban)

    await session.commit()
    for ban in active_bans:
        await session.refresh(ban)

    logger.debug(
        f"Revoked {len(active_bans)} active ban record(s) in DB for user {user_id}"
    )
    return active_bans[0]

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.settings import settings

engine = create_async_engine(settings.POSTGRES_URL, pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(engine)


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session


AsyncSessionDep = Annotated[AsyncSession, Depends(get_session)]

from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql
from sqlmodel import Column, Field, SQLModel


class UserBan(SQLModel, table=True):
    __tablename__ = "user_bans"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        foreign_key="users.id", nullable=False, ondelete="CASCADE", index=True
    )
    admin_id: int = Field(foreign_key="users.id", nullable=False, ondelete="CASCADE")
    is_banned: bool = Field(default=True, nullable=False)
    reason: str = Field(nullable=False, min_length=1, max_length=255)
    created_at: datetime = Field(
        sa_column=Column(
            postgresql.TIMESTAMP(timezone=True),
            default=lambda: datetime.now(timezone.utc),
            nullable=False,
        )
    )
    expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

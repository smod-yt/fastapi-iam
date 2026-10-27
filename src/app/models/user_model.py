from datetime import datetime, timezone
from enum import Enum

from sqlalchemy.dialects import postgresql
from sqlmodel import Column, Field, SQLModel


class UserRoles(str, Enum):
    USER = ("user", 10)
    MODERATOR = ("moderator", 30)
    ADMIN = ("admin", 50)

    weight: int

    def __new__(cls, value: str, weight: int):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.weight = weight
        return obj


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)

    name: str = Field(min_length=1, max_length=32)
    user_name: str = Field(
        unique=True, min_length=3, max_length=16, regex=r"^[a-z0-9_-]+$"
    )

    created_at: datetime = Field(
        sa_column=Column(
            postgresql.TIMESTAMP(timezone=True),
            default=lambda: datetime.now(timezone.utc),
        )
    )
    role: UserRoles = Field(
        sa_column=Column(
            postgresql.ENUM(UserRoles, name="userroles", create_type=False),
            default=UserRoles.USER,
            nullable=False,
        )
    )

    password: str = Field(max_length=60)

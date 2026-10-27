from datetime import datetime

from pydantic import BaseModel, Field


class BanUserSchema(BaseModel):
    user_id: int
    reason: str = Field(default="Violation of rules", min_length=1, max_length=255)
    expires_at: datetime | None = None


class UserBanResponse(BaseModel):
    id: int
    user_id: int
    admin_id: int
    is_banned: bool
    reason: str
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}


class PaginatedBanHistoryResponse(BaseModel):
    items: list[UserBanResponse]
    total: int
    page: int
    limit: int

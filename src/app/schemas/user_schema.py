from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.app.models.user_model import UserRoles


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    user_name: str


class PaginatedUsersResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    limit: int


class UserUpdateSchema(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=32)
    user_name: str | None = Field(
        default=None, min_length=3, max_length=16, pattern=r"^[a-z0-9_-]+$"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Name cannot be empty or whitespace only")
        return v

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "UserUpdateSchema":
        if self.name is None and self.user_name is None:
            raise ValueError("At least one field must be provided for update")
        return self


class UserUpdatePasswordSchema(BaseModel):
    old_password: str = Field(min_length=8, max_length=60)
    new_password: str = Field(min_length=8, max_length=60)


class UserRoleUpdateSchema(BaseModel):
    role: UserRoles


class UserRoleResponse(BaseModel):
    id: int
    role: UserRoles

    model_config = ConfigDict(from_attributes=True)

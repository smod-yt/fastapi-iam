from pydantic import BaseModel, Field

from .user_schema import UserResponse


class RegisterSchema(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    user_name: str = Field(min_length=3, max_length=16, pattern=r"^[a-z0-9_-]+$")
    password: str = Field(min_length=8, max_length=60)


class LoginSchema(BaseModel):
    user_name: str = Field(min_length=3, max_length=16, pattern=r"^[a-z0-9_-]+$")
    password: str = Field(max_length=60)


class AuthResponse(BaseModel):
    user: UserResponse
    access_token: str


class SessionDataSchema(BaseModel):
    token_hash: str
    user_id: int
    created_at: int
    last_activity: int
    ip: str
    client: str
    location: str


class SessionReadSchema(BaseModel):
    created_at: int
    last_activity: int
    ip: str
    client: str
    location: str
    is_current: bool


class AccessTokenSchema(BaseModel):
    access_token: str

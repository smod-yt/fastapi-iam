import asyncio
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from jwt import (
    DecodeError,
    ExpiredSignatureError,
    InvalidSignatureError,
    InvalidTokenError,
)

from src.app.settings import settings
from src.app.utils.exceptions import (
    InvalidJWT,
    InvalidJWTSignature,
    JWTDecodeError,
    JWTExpired,
)

JWT_TOKEN_KEY = settings.JWT_TOKEN_KEY
JWT_EXPIRES_TIME = settings.JWT_EXPIRES_TIME
JWT_ALGORITHM = settings.JWT_ALGORITHM

REFRESH_TOKEN_KEY = settings.REFRESH_TOKEN_KEY


async def hash_password(password: str) -> str:
    salt = await asyncio.to_thread(bcrypt.gensalt)
    hashed_password = await asyncio.to_thread(
        bcrypt.hashpw, password.encode("utf-8"), salt
    )

    return hashed_password.decode("utf-8")


async def check_password(password: str, hashed_password: str) -> bool:
    return await asyncio.to_thread(
        bcrypt.checkpw, password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def generate_refresh_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(48)

    hashed_token = hash_refresh_token(raw_token)

    return raw_token, hashed_token


def hash_refresh_token(raw_token: str) -> str:
    return hmac.new(
        key=REFRESH_TOKEN_KEY.encode("utf-8"),
        msg=raw_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def generate_jwt_token(user_id: int) -> str:
    expires_time = datetime.now(timezone.utc) + timedelta(seconds=JWT_EXPIRES_TIME)

    return jwt.encode(
        payload={"sub": str(user_id), "exp": expires_time},
        key=JWT_TOKEN_KEY,
        algorithm=JWT_ALGORITHM,
    )


def get_user_id_from_jwt(token: str) -> int:
    try:
        payload = jwt.decode(jwt=token, key=JWT_TOKEN_KEY, algorithms=[JWT_ALGORITHM])
    except ExpiredSignatureError:
        raise JWTExpired
    except InvalidSignatureError:
        raise InvalidJWTSignature
    except InvalidTokenError:
        raise InvalidJWT
    except DecodeError:
        raise JWTDecodeError

    return int(payload["sub"])

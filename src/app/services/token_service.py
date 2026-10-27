import json
from datetime import datetime, timezone
from uuid import uuid4

import geoip2.database
from fastapi import Request
from geoip2.errors import AddressNotFoundError, GeoIP2Error
from loguru import logger
from redis.asyncio import Redis
from user_agents import parse

from src.app.repositories import token_repository
from src.app.schemas.auth_schema import SessionDataSchema
from src.app.settings import settings
from src.app.utils import hash


async def create_and_save_tokens(
    redis: Redis,
    request: Request,
    user_id: int,
    session_uuid: str | None = None,
    created_at: int | None = None,
) -> tuple[str, str]:
    raw_token, refresh_token = hash.generate_refresh_token()
    access_token = hash.generate_jwt_token(user_id)
    token_uuid = session_uuid or str(uuid4())

    ip = request.client.host
    raw_user_agent = request.headers.get("User-Agent")
    user_agent = parse(raw_user_agent)

    location = "Unknown"
    reader: geoip2.database.Reader | None = getattr(
        request.app.state, "geoip_reader", None
    )
    if reader is not None:
        try:
            geoip_response = reader.city(ip)
            location = f"{geoip_response.country.name}, {geoip_response.city.name}"
        except AddressNotFoundError:
            logger.warning(f"Address {ip} not found in the GeoIP database")
        except GeoIP2Error as e:
            logger.error(f"GeoIP library error: {e}")

    session_data = {
        "user_id": user_id,
        "token_hash": refresh_token,
        "created_at": created_at or int(datetime.now(timezone.utc).timestamp()),
        "last_activity": int(datetime.now(timezone.utc).timestamp()),
        "ip": ip,
        "client": str(user_agent),
        "location": location,
    }

    validated_data = json.dumps(SessionDataSchema.model_validate(session_data).__dict__)

    await token_repository.save_session(
        redis,
        refresh_token,
        token_uuid,
        user_id,
        settings.REFRESH_EXPIRES_TIME,
        validated_data,
    )

    return raw_token, access_token


async def get_session_data(redis: Redis, session_uuid: str) -> dict:
    data = await token_repository.get_session_data(redis, session_uuid)

    return data


async def delete_session(redis: Redis, session_uuid: str, user_id: int) -> None:
    await token_repository.delete_session(redis, session_uuid, user_id)

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from src.app.models import User
from src.app.repositories import token_repository
from src.app.schemas.auth_schema import SessionReadSchema
from src.app.services import session_service
from src.app.settings import settings
from src.app.utils import limiter
from src.app.utils.dependencies import (
    RedisSessionDep,
    get_current_user,
    get_refresh_token,
)
from src.app.utils.errors import (
    JWT_ERRORS,
    RATE_LIMIT_ERROR,
    REQUEST_ERRORS,
    SESSION_ERRORS,
    error_example,
    error_response,
    errors_list,
)
from src.app.utils.exceptions import Forbidden, SessionExpired, UserNotFound

router = APIRouter(prefix="/sessions", tags=["Sessions"])


def delete_refresh_cookie(response: Response):
    response.delete_cookie(
        "refresh_token",
        httponly=True,
        secure=settings.HTTPS,
        samesite="lax",
    )



@router.get(
    "/",
    status_code=status.HTTP_200_OK,
    response_model=dict[UUID, SessionReadSchema],
    responses={
        **REQUEST_ERRORS,
        **errors_list(
            status.HTTP_401_UNAUTHORIZED,
            "Auth Errors",
            {**JWT_ERRORS, **SESSION_ERRORS},
        ),
        **RATE_LIMIT_ERROR,
    },
)
@limiter.limit("60/minute")
async def get_sessions(
    request: Request,
    response: Response,
    redis: RedisSessionDep,
    user: User = Depends(get_current_user),
    refresh_token: str = Depends(get_refresh_token),
):
    """
    Returns all user sessions
    """

    session_uuid = await token_repository.get_session_uuid_from_refresh(
        redis, refresh_token
    )

    user_sessions = await session_service.get_user_sessions(redis, user, session_uuid)

    return user_sessions


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        **REQUEST_ERRORS,
        **errors_list(
            status.HTTP_401_UNAUTHORIZED,
            "Auth Errors",
            {**JWT_ERRORS, **SESSION_ERRORS},
        ),
        **RATE_LIMIT_ERROR,
        **error_response(UserNotFound, "Current User Not Found Error"),
        **error_response(Forbidden, "Forbidden Error"),
    },
)
@limiter.limit("5/minute")
async def logout(
    request: Request,
    response: Response,
    redis: RedisSessionDep,
    user: User = Depends(get_current_user),
    refresh_token: str = Depends(get_refresh_token),
):
    """
    Invalidates the current session
    """

    await session_service.logout(redis, user, refresh_token)
    delete_refresh_cookie(response)

    return


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        **REQUEST_ERRORS,
        **errors_list(status.HTTP_401_UNAUTHORIZED, "Auth Errors", {**JWT_ERRORS}),
        **RATE_LIMIT_ERROR,
        **error_response(UserNotFound, "Current User Not Found Error"),
    },
)
@limiter.limit("3/minute")
async def logout_all(
    request: Request,
    response: Response,
    redis: RedisSessionDep,
    refresh_token: str = Depends(get_refresh_token),
    user: User = Depends(get_current_user),
):
    """
    Invalidates all user sessions
    """

    await session_service.logout_all(redis, refresh_token, user)
    delete_refresh_cookie(response)

    return


@router.delete(
    "/revoke/{session_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        **REQUEST_ERRORS,
        **errors_list(
            status.HTTP_401_UNAUTHORIZED,
            "Auth Errors",
            {
                **JWT_ERRORS,
                **error_example(SessionExpired, "Session Not Found Or Expired Error"),
            },
        ),
        **RATE_LIMIT_ERROR,
        **error_response(UserNotFound, "Current User Not Found Error"),
        **error_response(Forbidden, "Forbidden Error"),
    },
)
@limiter.limit("10/minute")
async def revoke_session_by_uuid(
    request: Request,
    response: Response,
    redis: RedisSessionDep,
    session_uuid: UUID,
    refresh_token: str = Depends(get_refresh_token),
    user: User = Depends(get_current_user),
):
    """
    Invalidates a user session by UUID
    """

    await session_service.revoke_session(redis, user, refresh_token, session_uuid)

    return

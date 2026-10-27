from fastapi import APIRouter, Depends, Query, Request, Response, status

from src.app.db import AsyncSessionDep
from src.app.models import User
from src.app.models.user_model import UserRoles
from src.app.schemas.user_schema import (
    PaginatedUsersResponse,
    UserResponse,
    UserRoleResponse,
    UserRoleUpdateSchema,
    UserUpdatePasswordSchema,
    UserUpdateSchema,
)
from src.app.services import user_service
from src.app.settings import settings
from src.app.utils import limiter
from src.app.utils.dependencies import (
    RedisSessionDep,
    check_session_age,
    check_user_access,
    get_current_user,
    require_role,
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
from src.app.utils.exceptions import (
    Conflict,
    Forbidden,
    InvalidCredentials,
    SessionTooEarly,
    UserBanned,
    UserNotFound,
)

router = APIRouter(prefix="/users", tags=["Users"])


def delete_refresh_cookie(response: Response):
    response.delete_cookie(
        "refresh_token",
        httponly=True,
        secure=settings.HTTPS,
        samesite="lax",
    )


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=UserResponse,
    responses={
        **REQUEST_ERRORS,
        **errors_list(
            status.HTTP_401_UNAUTHORIZED,
            "Auth Errors",
            {**JWT_ERRORS},
        ),
        **RATE_LIMIT_ERROR,
        **error_response(UserBanned, "User Banned Error"),
        **error_response(UserNotFound, "Current User Not Found Error"),
    },
)
@limiter.limit("60/minute")
async def get_me(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
):
    """
    Returns the currently authenticated user's profile
    """
    return current_user


@router.get(
    "/",
    status_code=status.HTTP_200_OK,
    response_model=PaginatedUsersResponse,
    responses={
        **REQUEST_ERRORS,
        **errors_list(
            status.HTTP_401_UNAUTHORIZED,
            "Auth Errors",
            {**JWT_ERRORS},
        ),
        **RATE_LIMIT_ERROR,
    },
)
@limiter.limit("60/minute")
async def get_users(
    request: Request,
    response: Response,
    session: AsyncSessionDep,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    name: str | None = Query(default=None),
    user_name: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    """
    Returns a paginated list of users with optional filtering by name or user_name
    """
    items, total = await user_service.get_users(
        session, page=page, limit=limit, name=name, user_name=user_name
    )
    return PaginatedUsersResponse(
        items=[u for u in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=UserResponse,
    responses={
        **REQUEST_ERRORS,
        **errors_list(
            status.HTTP_401_UNAUTHORIZED,
            "Auth Errors",
            {**JWT_ERRORS},
        ),
        **RATE_LIMIT_ERROR,
        **error_response(UserNotFound, "User Not Found Error"),
    },
)
@limiter.limit("60/minute")
async def get_user_by_id(
    request: Request,
    response: Response,
    session: AsyncSessionDep,
    user_id: int,
    current_user: User = Depends(get_current_user),
):
    """
    Returns user details by ID
    """
    user = await user_service.get_user_by_id(session, user_id)
    return user


@router.patch(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=UserResponse,
    responses={
        **REQUEST_ERRORS,
        **errors_list(
            status.HTTP_401_UNAUTHORIZED,
            "Auth Errors",
            {**JWT_ERRORS, **SESSION_ERRORS},
        ),
        **RATE_LIMIT_ERROR,
        **error_response(Forbidden, "Forbidden Error"),
        **error_response(Conflict, "Conflict Error"),
        **error_response(UserNotFound, "User Not Found Error"),
        **error_response(SessionTooEarly, "Session Age Error"),
    },
)
@limiter.limit("10/minute")
async def update_user(
    request: Request,
    response: Response,
    session: AsyncSessionDep,
    user_id: int,
    data: UserUpdateSchema,
    current_user: User = Depends(check_user_access),
    _age_check: None = Depends(check_session_age),
):
    """
    Updates user profile (name and/or user_name)
    """
    user = await user_service.get_user_by_id(session, user_id)
    updated_user = await user_service.update_user(session, user, data, current_user)
    return updated_user


@router.patch(
    "/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        **REQUEST_ERRORS,
        **errors_list(
            status.HTTP_401_UNAUTHORIZED,
            "Auth Errors",
            {
                **JWT_ERRORS,
                **SESSION_ERRORS,
                **error_example(InvalidCredentials, "Invalid Credentials Error"),
            },
        ),
        **RATE_LIMIT_ERROR,
        **error_response(Forbidden, "Forbidden Error"),
        **error_response(UserNotFound, "User Not Found Error"),
        **error_response(SessionTooEarly, "Session Age Error"),
    },
)
@limiter.limit("5/minute")
async def update_user_password(
    request: Request,
    response: Response,
    session: AsyncSessionDep,
    user_id: int,
    data: UserUpdatePasswordSchema,
    current_user: User = Depends(check_user_access),
    _age_check: None = Depends(check_session_age),
):
    """
    Updates user password
    """
    user = await user_service.get_user_by_id(session, user_id)
    await user_service.update_user_password(session, user, data, current_user)
    return


@router.patch(
    "/{user_id}/role",
    status_code=status.HTTP_200_OK,
    response_model=UserRoleResponse,
    responses={
        **REQUEST_ERRORS,
        **errors_list(status.HTTP_401_UNAUTHORIZED, "Auth Errors", {**JWT_ERRORS}),
        **RATE_LIMIT_ERROR,
        **error_response(Forbidden, "Forbidden Error"),
        **error_response(UserNotFound, "User Not Found Error"),
    },
)
@limiter.limit("10/minute")
async def update_user_role(
    request: Request,
    response: Response,
    session: AsyncSessionDep,
    user_id: int,
    data: UserRoleUpdateSchema,
    current_user: User = Depends(require_role(UserRoles.ADMIN)),
):
    """
    Updates the user role (available roles: user, moderator, admin)
    """

    user = await user_service.get_user_by_id(session, user_id)
    return await user_service.update_user_role(session, user, data.role, current_user)


@router.delete(
    "/{user_id}",
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
        **error_response(Forbidden, "Forbidden Error"),
        **error_response(UserNotFound, "User Not Found Error"),
        **error_response(SessionTooEarly, "Session Age Error"),
    },
)
@limiter.limit("5/minute")
async def delete_user(
    request: Request,
    response: Response,
    session: AsyncSessionDep,
    redis: RedisSessionDep,
    user_id: int,
    current_user: User = Depends(check_user_access),
    _age_check: None = Depends(check_session_age),
):
    """
    Deletes user account and invalidates their sessions
    """
    current_user_id = current_user.id
    user = await user_service.get_user_by_id(session, user_id)
    await user_service.delete_user(session, redis, user, current_user)

    if current_user_id == user_id:
        delete_refresh_cookie(response)

    return

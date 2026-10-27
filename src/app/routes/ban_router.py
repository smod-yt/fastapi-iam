from fastapi import APIRouter, Depends, Query, Request, Response, status

from src.app.db import AsyncSessionDep
from src.app.models import User
from src.app.models.user_model import UserRoles
from src.app.schemas.ban_schema import (
    BanUserSchema,
    PaginatedBanHistoryResponse,
    UserBanResponse,
)
from src.app.services import ban_service
from src.app.utils import limiter
from src.app.utils.dependencies import RedisSessionDep, require_role
from src.app.utils.errors import (
    JWT_ERRORS,
    RATE_LIMIT_ERROR,
    REQUEST_ERRORS,
    error_response,
    errors_list,
)
from src.app.utils.exceptions import (
    Forbidden,
    UserAlreadyBanned,
    UserNotFound,
)

router = APIRouter(
    prefix="/bans",
    tags=["Bans"],
    dependencies=[Depends(require_role(UserRoles.ADMIN))],
)


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    response_model=UserBanResponse,
    responses={
        **REQUEST_ERRORS,
        **errors_list(
            status.HTTP_401_UNAUTHORIZED,
            "Auth Errors",
            {**JWT_ERRORS},
        ),
        **RATE_LIMIT_ERROR,
        **error_response(Forbidden, "Forbidden Error"),
        **error_response(UserNotFound, "User Not Found Error"),
        **error_response(UserAlreadyBanned, "User Already Banned Error"),
    },
)
@limiter.limit("60/minute")
async def ban_user(
    request: Request,
    response: Response,
    data: BanUserSchema,
    session: AsyncSessionDep,
    redis: RedisSessionDep,
    admin: User = Depends(require_role(UserRoles.ADMIN)),
):
    """
    Bans a user and invalidates all their active sessions
    """
    ban = await ban_service.ban_user(
        session=session,
        redis=redis,
        admin=admin,
        data=data,
    )
    return ban


@router.get(
    "/users/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=PaginatedBanHistoryResponse,
    responses={
        **REQUEST_ERRORS,
        **errors_list(
            status.HTTP_401_UNAUTHORIZED,
            "Auth Errors",
            {**JWT_ERRORS},
        ),
        **RATE_LIMIT_ERROR,
        **error_response(Forbidden, "Forbidden Error"),
        **error_response(UserNotFound, "User Not Found Error"),
    },
)
@limiter.limit("60/minute")
async def get_ban_history(
    request: Request,
    response: Response,
    user_id: int,
    session: AsyncSessionDep,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    admin: User = Depends(require_role(UserRoles.ADMIN)),
):
    """
    Returns paginated ban history for a user
    """
    bans, total = await ban_service.get_ban_history(
        session, user_id, page=page, limit=limit
    )
    return PaginatedBanHistoryResponse(
        items=bans,
        total=total,
        page=page,
        limit=limit,
    )


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        **REQUEST_ERRORS,
        **errors_list(
            status.HTTP_401_UNAUTHORIZED,
            "Auth Errors",
            {**JWT_ERRORS},
        ),
        **RATE_LIMIT_ERROR,
        **error_response(Forbidden, "Forbidden Error"),
        **error_response(UserNotFound, "User Not Found Error"),
    },
)
@limiter.limit("60/minute")
async def unban_user(
    request: Request,
    response: Response,
    user_id: int,
    redis: RedisSessionDep,
    session: AsyncSessionDep,
    admin: User = Depends(require_role(UserRoles.ADMIN)),
):
    """
    Revokes an active ban for a user
    """
    await ban_service.unban_user(session, user_id, redis=redis, admin=admin)
    return

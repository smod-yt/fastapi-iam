from typing import Any

from fastapi import status


class BaseAppException(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code: str = "BAD_REQUEST"
    default_message: str = "An error occurred while processing your request"

    def __init__(
        self, message: str | None = None, details: dict[str, Any] | None = None
    ):
        self.message = message or self.default_message
        self.details = details or {}


class Conflict(BaseAppException):
    status_code = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"
    default_message = "Conflict"


class Forbidden(BaseAppException):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "FORBIDDEN"
    default_message = "You don't have permission to perform this action"


class JWTNotGranted(BaseAppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "JWT_NOT_GRANTED"
    default_message = "JWT not granted"


class InvalidCredentials(BaseAppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "INVALID_CREDENTIALS"
    default_message = "Invalid credentials"


class UserNotFound(BaseAppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "USER_NOT_FOUND"
    default_message = "User not found"


class JWTExpired(BaseAppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "JWT_EXPIRED"
    default_message = "JWT has expired"


class InvalidJWTSignature(BaseAppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "INVALID_JWT_SIGNATURE"
    default_message = "JWT signature is invalid"


class InvalidJWT(BaseAppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "INVALID_JWT"
    default_message = "JWT is invalid"


class JWTDecodeError(BaseAppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "JWT_DECODE_ERROR"
    default_message = "An error occurred while decoding the JWT"


class RefreshTokenNotGranted(BaseAppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "REFRESH_TOKEN_NOT_GRANTED"
    default_message = "Refresh token not granted"


class SessionExpired(BaseAppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "SESSION_EXPIRED"
    default_message = "Session not found or expired"


class SessionTooEarly(BaseAppException):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "SESSION_TOO_EARLY"
    default_message = "This action requires a session that is at least 24 hours old"


class UserAlreadyBanned(Conflict):
    status_code = status.HTTP_409_CONFLICT
    error_code = "USER_ALREADY_BANNED"
    default_message = "User is already banned"


class UserBanned(Forbidden):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "USER_BANNED"
    default_message = "User is banned"


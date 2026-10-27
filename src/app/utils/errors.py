from typing import Any

from fastapi import status

from src.app.utils.exceptions import (
    BaseAppException,
    InvalidJWT,
    InvalidJWTSignature,
    JWTDecodeError,
    JWTExpired,
    RefreshTokenNotGranted,
    SessionExpired,
)


def error_response(
    exception: type[BaseAppException], description: str | None = None
) -> dict:
    return {
        exception.status_code: {
            "description": description,
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": exception.error_code,
                            "message": exception.default_message or "string",
                            "details": {},
                        }
                    }
                }
            },
        }
    }


def custom_error_response(
    status_code: status,
    error_code: str,
    description: str | None = None,
    message: str | None = None,
    details: Any = None,
):
    return {
        status_code: {
            "description": description,
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": error_code,
                            "message": message,
                            "details": details or {},
                        }
                    }
                }
            },
        }
    }


def errors_list(status_code: status, description: str, examples: dict) -> dict:
    return {
        status_code: {
            "description": description,
            "content": {"application/json": {"examples": examples}},
        }
    }


def error_example(
    exception: type[BaseAppException], description: str | None = None
) -> dict:
    return {
        description: {
            "summary": description,
            "value": {
                "error": {
                    "code": exception.error_code,
                    "message": exception.default_message or "string",
                    "details": {},
                }
            },
        }
    }


RATE_LIMIT_ERROR = custom_error_response(
    status.HTTP_429_TOO_MANY_REQUESTS,
    description="Rate Limit Error",
    error_code="RATE_LIMIT_EXCEEDED",
    message="Too many requests",
    details={
        "limit": "string",
        "retry_after": 0,
    },
)

BAD_REQUEST_ERROR = custom_error_response(
    status.HTTP_400_BAD_REQUEST,
    error_code="BAD_REQUEST",
    description="Bad Request Error",
    message="Invalid JSON format",
    details="string",
)

VALIDATION_ERROR = custom_error_response(
    status.HTTP_422_UNPROCESSABLE_ENTITY,
    error_code="VALIDATION_ERROR",
    description="Request Validation Error",
    message="Request validation failed",
    details=[
        {
            "field": "string",
            "type": "string",
            "message": "string",
            "context": {},
            "input": "any",
        }
    ],
)

REQUEST_ERRORS = {**BAD_REQUEST_ERROR, **VALIDATION_ERROR}

JWT_ERRORS = {
    **error_example(JWTExpired, "JWT Expired Error"),
    **error_example(InvalidJWTSignature, "Invalid JWT Signature Error"),
    **error_example(InvalidJWT, "Invalid JWT Error"),
    **error_example(JWTDecodeError, "JWT Decode Error"),
}

SESSION_ERRORS = {
    **error_example(RefreshTokenNotGranted, "Refresh Token Not Granted Error"),
    **error_example(SessionExpired, "Session Not Found Or Expired Error"),
}

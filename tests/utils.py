from httpx import Response
from pydantic import BaseModel


def validate_response(
    response: Response,
    response_model: type[BaseModel],
) -> BaseModel:
    return response_model.model_validate(response.json())


def auth_header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}

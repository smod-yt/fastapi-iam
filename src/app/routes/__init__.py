from fastapi import APIRouter, FastAPI
from loguru import logger

from src.app.routes.auth_router import router as auth_router
from src.app.routes.ban_router import router as ban_router
from src.app.routes.session_router import router as session_router
from src.app.routes.user_router import router as user_router

all_routes = [auth_router, session_router, user_router, ban_router]

api_v1_router = APIRouter(prefix="/api/v1")


def register_routes(app: FastAPI):
    for route in all_routes:
        api_v1_router.include_router(route)
    app.include_router(api_v1_router)

    routes_count = sum(len(route.routes) for route in all_routes)
    logger.info(f"Successfully registred {routes_count} API routes")

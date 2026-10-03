from fastapi import APIRouter

from app.api.routes import auth, chat, health, projects, repositories

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(repositories.router)
api_router.include_router(chat.router)

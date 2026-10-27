from bot.handlers.admin import router as admin_router
from bot.handlers.routes import router as routes_router
from bot.handlers.analytics import router as analytics_router
from bot.handlers.privacy import router as privacy_router
from bot.handlers.forward import router as forward_router

__all__ = [
    "admin_router",
    "routes_router",
    "analytics_router",
    "privacy_router",
    "forward_router",
]

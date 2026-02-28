from aiogram import Router

from .automod import router as automod_router
from .commands import router as commands_router
from .menu import router as menu_router

router = Router(name="group_manager")
router.include_router(menu_router)
router.include_router(commands_router)
router.include_router(automod_router)

__all__ = ["router"]

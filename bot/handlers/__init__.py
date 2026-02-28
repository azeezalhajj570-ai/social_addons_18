from aiogram import Router

from . import export_users, group_manager, info, menu, start, support


def get_handlers_router() -> Router:
    router = Router()
    router.include_router(group_manager.router)
    router.include_router(start.router)
    router.include_router(info.router)
    router.include_router(support.router)
    router.include_router(menu.router)
    router.include_router(export_users.router)

    return router

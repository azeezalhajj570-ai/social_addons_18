from __future__ import annotations
import asyncio
import contextlib

import sentry_sdk
import uvloop
from loguru import logger
from sentry_sdk.integrations.loguru import LoggingLevels, LoguruIntegration

from bot.core.config import settings
from bot.core.loader import app, bot, dp
from bot.handlers import get_handlers_router
from bot.handlers.metrics import MetricsView
from bot.keyboards.default_commands import remove_default_commands, set_default_commands
from bot.middlewares import register_middlewares
from bot.middlewares.prometheus import prometheus_middleware_factory
from bot.services.scheduler import scheduler_loop

scheduler_task: asyncio.Task[None] | None = None


async def on_startup() -> None:
    global scheduler_task
    logger.info("bot starting...")

    register_middlewares(dp)

    dp.include_router(get_handlers_router())

    if settings.USE_WEBHOOK:
        app.middlewares.append(prometheus_middleware_factory())
        app.router.add_route("GET", "/metrics", MetricsView)

    await set_default_commands(bot)

    bot_info = await bot.get_me()

    logger.info(f"Name     - {bot_info.full_name}")
    logger.info(f"Username - @{bot_info.username}")
    logger.info(f"ID       - {bot_info.id}")

    states: dict[bool | None, str] = {
        True: "Enabled",
        False: "Disabled",
        None: "Unknown (This's not a bot)",
    }

    logger.info(f"Groups Mode  - {states[bot_info.can_join_groups]}")
    logger.info(f"Privacy Mode - {states[not bot_info.can_read_all_group_messages]}")
    logger.info(f"Inline Mode  - {states[bot_info.supports_inline_queries]}")

    scheduler_task = asyncio.create_task(scheduler_loop(bot))
    logger.info("scheduler started")

    logger.info("bot started")


async def on_shutdown() -> None:
    global scheduler_task
    logger.info("bot stopping...")

    await remove_default_commands(bot)

    if scheduler_task is not None:
        scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler_task
        scheduler_task = None

    await dp.storage.close()
    await dp.fsm.storage.close()

    await bot.delete_webhook()
    await bot.session.close()

    logger.info("bot stopped")


async def setup_webhook() -> None:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application  # noqa: PLC0415
    from aiohttp.web import AppRunner, TCPSite  # noqa: PLC0415

    await bot.set_webhook(
        settings.webhook_url,
        allowed_updates=dp.resolve_used_update_types(),
        secret_token=settings.WEBHOOK_SECRET,
    )

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.WEBHOOK_SECRET,
    )
    webhook_requests_handler.register(app, path=settings.WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    runner = AppRunner(app)
    await runner.setup()
    site = TCPSite(runner, host=settings.WEBHOOK_HOST, port=settings.WEBHOOK_PORT)
    await site.start()

    await asyncio.Event().wait()


async def main() -> None:
    if settings.SENTRY_DSN:
        sentry_loguru = LoguruIntegration(
            level=LoggingLevels.INFO.value,
            event_level=LoggingLevels.INFO.value,
        )
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            enable_tracing=True,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
            integrations=[sentry_loguru],
        )

    logger.add(
        "logs/telegram_bot.log",
        level="DEBUG",
        format="{time} | {level} | {module}:{function}:{line} | {message}",
        rotation="100 KB",
        compression="zip",
    )

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if settings.USE_WEBHOOK:
        await setup_webhook()
    else:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    uvloop.run(main())

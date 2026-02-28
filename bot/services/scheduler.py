from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from loguru import logger

from bot.database.database import sessionmaker
from bot.services import moderation


async def scheduler_loop(bot: Bot) -> None:
    while True:
        try:
            async with sessionmaker() as session:
                now = datetime.now(timezone.utc)
                due = await moderation.get_due_scheduled_messages(session, now)

                for item in due:
                    try:
                        target_chat_id = item.target_chat_id if item.target_chat_id is not None else item.chat_id
                        await bot.send_message(chat_id=target_chat_id, text=item.text, disable_web_page_preview=True)
                        next_run_at = now + timedelta(seconds=max(60, item.interval_seconds))
                        await moderation.mark_scheduled_message_sent(session, item.id, next_run_at)
                    except Exception as exc:
                        logger.warning(
                            "scheduled message send failed schedule_id={} source_chat={} target_chat={} err={}",
                            item.id,
                            item.chat_id,
                            item.target_chat_id,
                            exc,
                        )
        except Exception as exc:
            logger.warning("scheduler loop iteration failed: {}", exc)

        await asyncio.sleep(30)

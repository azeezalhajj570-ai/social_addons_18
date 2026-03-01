from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events


def _setup_logging() -> logging.Logger:
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("user-client-telethon")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = logging.FileHandler(log_dir / "user_client_groups.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    return logger


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


async def main() -> None:
    load_dotenv(".env.user")
    log = _setup_logging()

    api_id = int(_require_env("API_ID"))
    api_hash = _require_env("API_HASH")
    session_name = os.getenv("SESSION_NAME", "user_client")
    phone_number = os.getenv("PHONE_NUMBER", "").strip()

    async with TelegramClient(session_name, api_id, api_hash) as client:
        @client.on(events.NewMessage(incoming=True))
        async def _on_new_message(event: events.NewMessage.Event) -> None:
            if not event.is_group:
                return
            text = event.raw_text or ""
            sender_id = event.sender_id
            log.info(
                "group=%s sender=%s msg=%s text=%r",
                event.chat_id,
                sender_id,
                event.id,
                text[:500],
            )

        if not await client.is_user_authorized():
            await client.send_code_request(phone_number)
            code = input("Enter Telegram login code: ").strip()
            try:
                await client.sign_in(phone_number, code)
            except Exception:
                password = input("Enter 2FA password: ").strip()
                await client.sign_in(password=password)

        me = await client.get_me()
        print(f"Logged in as: {me.first_name} (@{me.username}) id={me.id}")
        print("User client is running and logging group messages. Press Ctrl+C to stop.")
        await client.run_until_disconnected()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

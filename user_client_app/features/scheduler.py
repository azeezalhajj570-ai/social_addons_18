from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from pyrogram import Client

from user_client_app.storage import Repository


def parse_datetime_utc(raw: str) -> datetime:
    value = raw.strip()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Use datetime like 2026-02-27 14:30 or 2026-02-27T14:30") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class ScheduledOutboxRunner:
    def __init__(self, client: Client, repo: Repository, log: logging.Logger, poll_seconds: int) -> None:
        self.client = client
        self.repo = repo
        self.log = log
        self.poll_seconds = poll_seconds

    async def run_forever(self) -> None:
        while True:
            try:
                due = self.repo.get_due_scheduled(datetime.now(tz=timezone.utc), limit=20)
                for row in due:
                    job_id = int(row["id"])
                    target = row["target"]
                    text = row["text"]
                    try:
                        sent = await self.client.send_message(target, text)
                        self.repo.mark_sent(job_id, getattr(sent, "id", None))
                        self.log.info("scheduled message sent job_id=%s target=%s", job_id, target)
                    except Exception as exc:
                        self.repo.mark_failed(job_id, str(exc))
                        self.log.error("scheduled message failed job_id=%s target=%s error=%s", job_id, target, exc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.log.exception("scheduler loop error: %s", exc)
            await asyncio.sleep(self.poll_seconds)


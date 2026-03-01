from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from pyrogram import Client, filters, idle

from user_client_app.config import Config
from user_client_app.features.link_collector import collect_group_links
from user_client_app.features.odoo_sync import OdooAutoReplySyncRunner
from user_client_app.features.scheduler import ScheduledOutboxRunner, parse_datetime_utc
from user_client_app.storage import Repository


class UserClientApp:
    def __init__(self, cfg: Config, repo: Repository, log: logging.Logger) -> None:
        self.cfg = cfg
        self.repo = repo
        self.log = log
        self.client = Client(
            cfg.session_name,
            api_id=cfg.api_id,
            api_hash=cfg.api_hash,
            session_string=cfg.session_string,
        )
        self.last_reply_at: dict[tuple[int, int], float] = {}
        self._scheduler_task: asyncio.Task[None] | None = None
        self._odoo_sync_task: asyncio.Task[None] | None = None
        self._scheduler = ScheduledOutboxRunner(
            client=self.client,
            repo=self.repo,
            log=self.log,
            poll_seconds=self.cfg.scheduler_poll_seconds,
        )
        self._odoo_sync = OdooAutoReplySyncRunner(cfg=self.cfg, repo=self.repo, log=self.log) if self.cfg.odoo_enabled else None
        self._bind_handlers()

    def _bind_handlers(self) -> None:
        @self.client.on_message(filters.group & filters.incoming)
        async def _on_group_message(client: Client, message) -> None:
            await self._handle_group_message(client, message)

        @self.client.on_message(filters.me & filters.private & filters.text)
        async def _on_private_self_text(client: Client, message) -> None:
            await self._handle_private_command(message)

    async def _handle_group_message(self, client: Client, message) -> None:
        now = time.time()
        text = message.text or message.caption or ""
        text_lower = text.strip().lower()
        sender_id = message.from_user.id if message.from_user else None
        self.log.info(
            "group=%s sender=%s msg=%s text=%r",
            message.chat.id,
            sender_id,
            message.id,
            text[:500],
        )

        if text_lower and not text_lower.startswith("/"):
            routes = self.repo.list_auto_reply_routes(message.chat.id)
            for route in routes:
                keyword = (route["keyword"] or "").strip().lower()
                if not keyword or int(route["enabled"] or 0) != 1:
                    continue
                if keyword in text_lower:
                    try:
                        await message.reply_text(route["response"])
                        self.log.info(
                            "dynamic route hit chat=%s keyword=%r msg=%s",
                            message.chat.id,
                            keyword,
                            message.id,
                        )
                    except Exception as exc:
                        self.log.error(
                            "dynamic route failed chat=%s keyword=%r msg=%s err=%s",
                            message.chat.id,
                            keyword,
                            message.id,
                            exc,
                        )
                    return

        if self.cfg.auto_reply_user_id <= 0 or sender_id != self.cfg.auto_reply_user_id:
            return

        key = (sender_id, sender_id)
        prev = self.last_reply_at.get(key, 0.0)
        if self.cfg.auto_reply_cooldown_seconds > 0 and (now - prev) < self.cfg.auto_reply_cooldown_seconds:
            return

        try:
            await client.send_message(sender_id, self.cfg.auto_reply_text)
            self.last_reply_at[key] = now
            self.log.info(
                "auto-dm sent target=%s text=%r source_chat=%s",
                sender_id,
                self.cfg.auto_reply_text,
                message.chat.id,
            )
        except Exception as exc:
            self.log.error("auto-dm failed target=%s source_chat=%s error=%s", sender_id, message.chat.id, exc)

    async def _handle_private_command(self, message) -> None:
        # In some Pyrogram builds Chat has no `is_self`; use sender self-flag instead.
        if not message.chat or not message.from_user or not getattr(message.from_user, "is_self", False):
            return
        text = (message.text or "").strip()
        if not text.startswith("."):
            return

        cmd, _, payload = text.partition(" ")
        cmd = cmd.lower()
        payload = payload.strip()

        if cmd == ".help":
            await message.reply_text(
                "\n".join(
                    [
                        "User Client Commands:",
                        ".help",
                        ".addroute <chat_id> | <keyword> | <response>",
                        ".delroute <chat_id> | <keyword>",
                        ".listroutes <chat_id>",
                        ".schedule <chat> | <YYYY-MM-DD HH:MM> | <text>",
                        ".schedule_in <chat> | <minutes> | <text>",
                        ".schedules",
                        ".cancel_schedule <id>",
                        ".collect_links",
                    ]
                )
            )
            return

        if cmd == ".schedule":
            await self._cmd_schedule(message, payload)
            return

        if cmd == ".addroute":
            if self.cfg.odoo_enabled:
                await message.reply_text("Routes are managed by Odoo (source of truth). Local addroute is disabled.")
                return
            await self._cmd_addroute(message, payload)
            return

        if cmd == ".delroute":
            if self.cfg.odoo_enabled:
                await message.reply_text("Routes are managed by Odoo (source of truth). Local delroute is disabled.")
                return
            await self._cmd_delroute(message, payload)
            return

        if cmd == ".listroutes":
            await self._cmd_listroutes(message, payload)
            return

        if cmd == ".schedule_in":
            await self._cmd_schedule_in(message, payload)
            return

        if cmd == ".schedules":
            await self._cmd_schedules(message)
            return

        if cmd == ".cancel_schedule":
            await self._cmd_cancel_schedule(message, payload)
            return

        if cmd == ".collect_links":
            await self._cmd_collect_links(message)
            return

        await message.reply_text("Unknown command. Use .help")

    async def _cmd_addroute(self, message, payload: str) -> None:
        parts = [p.strip() for p in payload.split("|", 2)]
        if len(parts) != 3 or not all(parts):
            await message.reply_text("Format: .addroute <chat_id> | <keyword> | <response>")
            return
        raw_chat_id, keyword, response = parts
        try:
            chat_id = int(raw_chat_id)
        except ValueError:
            await message.reply_text("chat_id must be an integer.")
            return
        self.repo.upsert_auto_reply_route(chat_id=chat_id, keyword=keyword, response=response)
        await message.reply_text(f"Route saved for {chat_id}: `{keyword}` -> {response}")

    async def _cmd_delroute(self, message, payload: str) -> None:
        parts = [p.strip() for p in payload.split("|", 1)]
        if len(parts) != 2 or not all(parts):
            await message.reply_text("Format: .delroute <chat_id> | <keyword>")
            return
        raw_chat_id, keyword = parts
        try:
            chat_id = int(raw_chat_id)
        except ValueError:
            await message.reply_text("chat_id must be an integer.")
            return
        deleted = self.repo.delete_auto_reply_route(chat_id=chat_id, keyword=keyword)
        if deleted:
            await message.reply_text(f"Route deleted for {chat_id}: `{keyword}`")
        else:
            await message.reply_text("Route not found.")

    async def _cmd_listroutes(self, message, payload: str) -> None:
        raw_chat_id = payload.strip()
        if not raw_chat_id:
            await message.reply_text("Format: .listroutes <chat_id>")
            return
        try:
            chat_id = int(raw_chat_id)
        except ValueError:
            await message.reply_text("chat_id must be an integer.")
            return
        rows = self.repo.list_auto_reply_routes(chat_id=chat_id)
        if not rows:
            await message.reply_text("No routes configured for this chat.")
            return
        lines = []
        for row in rows[:30]:
            preview = (row["response"] or "").replace("\n", " ")[:60]
            source = row["source"] if "source" in row.keys() else "local"
            lines.append(f"- [{source}] {row['keyword']} -> {preview}")
        if len(rows) > 30:
            lines.append(f"...and {len(rows) - 30} more")
        await message.reply_text("Routes:\n" + "\n".join(lines))

    async def _cmd_schedule(self, message, payload: str) -> None:
        parts = [p.strip() for p in payload.split("|", 2)]
        if len(parts) != 3 or not all(parts):
            await message.reply_text("Format: .schedule <chat> | <YYYY-MM-DD HH:MM> | <text>")
            return

        target, raw_date, text = parts
        try:
            send_at_utc = parse_datetime_utc(raw_date.replace(" ", "T", 1))
        except ValueError as exc:
            await message.reply_text(str(exc))
            return

        if send_at_utc <= datetime.now(tz=timezone.utc):
            await message.reply_text("send_at must be in the future (UTC).")
            return

        job_id = self.repo.add_scheduled_message(target=target, text=text, send_at_utc=send_at_utc)
        await message.reply_text(
            f"Scheduled job #{job_id}\nTarget: {target}\nUTC: {send_at_utc.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    async def _cmd_schedule_in(self, message, payload: str) -> None:
        parts = [p.strip() for p in payload.split("|", 2)]
        if len(parts) != 3 or not all(parts):
            await message.reply_text("Format: .schedule_in <chat> | <minutes> | <text>")
            return

        target, raw_minutes, text = parts
        try:
            minutes = int(raw_minutes)
        except ValueError:
            await message.reply_text("minutes must be an integer.")
            return
        if minutes <= 0:
            await message.reply_text("minutes must be > 0.")
            return

        send_at_utc = datetime.now(tz=timezone.utc) + timedelta(minutes=minutes)
        job_id = self.repo.add_scheduled_message(target=target, text=text, send_at_utc=send_at_utc)
        await message.reply_text(
            f"Scheduled job #{job_id}\nTarget: {target}\nUTC: {send_at_utc.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    async def _cmd_schedules(self, message) -> None:
        rows = self.repo.list_pending_scheduled()
        if not rows:
            await message.reply_text("No pending scheduled messages.")
            return
        lines = []
        for row in rows[:20]:
            text_preview = (row["text"] or "").replace("\n", " ")[:50]
            lines.append(f"#{row['id']} -> {row['target']} @ {row['send_at_utc']} | {text_preview}")
        tail = ""
        if len(rows) > 20:
            tail = f"\n...and {len(rows) - 20} more"
        await message.reply_text("Pending schedules:\n" + "\n".join(lines) + tail)

    async def _cmd_cancel_schedule(self, message, payload: str) -> None:
        raw = payload.strip()
        if not raw:
            await message.reply_text("Format: .cancel_schedule <id>")
            return
        try:
            job_id = int(raw)
        except ValueError:
            await message.reply_text("id must be an integer.")
            return
        cancelled = self.repo.cancel_pending(job_id)
        if cancelled:
            await message.reply_text(f"Cancelled schedule #{job_id}.")
        else:
            await message.reply_text(f"Schedule #{job_id} not found or already processed.")

    async def _cmd_collect_links(self, message) -> None:
        await message.reply_text("Collecting group links...")
        resolved_links, total_groups, out_path = await collect_group_links(self.client, self.repo)
        await message.reply_text(
            f"Collected {resolved_links}/{total_groups} group links.\nSaved: {out_path.as_posix()}"
        )

    async def run(self) -> None:
        await self.client.start()
        try:
            me = await self.client.get_me()
            self.log.info("Logged in as: %s (@%s) id=%s", me.first_name, me.username, me.id)

            try:
                count = 0
                async for _ in self.client.get_dialogs():
                    count += 1
                self.log.info("Dialog peer cache synced. dialogs=%s", count)
            except Exception as exc:
                self.log.warning("Dialog sync failed: %s", exc)

            self._scheduler_task = asyncio.create_task(self._scheduler.run_forever())
            if self._odoo_sync is not None:
                self._odoo_sync_task = asyncio.create_task(self._odoo_sync.run_forever())
            print(f"Logged in as: {me.first_name} (@{me.username}) id={me.id}")
            print("User client is running. Use '.help' in Saved Messages. Press Ctrl+C to stop.")
            await idle()
        finally:
            if self._scheduler_task:
                self._scheduler_task.cancel()
                try:
                    await self._scheduler_task
                except asyncio.CancelledError:
                    pass
            if self._odoo_sync_task:
                self._odoo_sync_task.cancel()
                try:
                    await self._odoo_sync_task
                except asyncio.CancelledError:
                    pass
            await self.client.stop()

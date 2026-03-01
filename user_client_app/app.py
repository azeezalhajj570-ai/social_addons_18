from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from user_client_app.config import Config
from user_client_app.features.link_collector import collect_group_links
from user_client_app.features.odoo_sync import OdooAutoReplySyncRunner
from user_client_app.features.scheduler import ScheduledOutboxRunner, parse_datetime_utc
from user_client_app.integrations.odoo_api_client import OdooApiClient
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
        self._setup_state: dict[str, str | int] | None = None
        self._self_user_id: int | None = None
        self._bind_handlers()

    async def _send_route_dm_after_delay(self, user_id: int, text: str, delay_seconds: int, chat_id: int, keyword: str, msg_id: int) -> None:
        try:
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            await self.client.send_message(user_id, text)
            self.log.info(
                "dynamic route dm sent user=%s delay=%ss chat=%s keyword=%r msg=%s",
                user_id,
                delay_seconds,
                chat_id,
                keyword,
                msg_id,
            )
        except Exception as exc:
            self.log.error(
                "dynamic route dm failed user=%s delay=%ss chat=%s keyword=%r msg=%s err=%s",
                user_id,
                delay_seconds,
                chat_id,
                keyword,
                msg_id,
                exc,
            )

    @staticmethod
    def _format_when(send_at_utc: datetime) -> str:
        local_dt = send_at_utc.astimezone()
        return (
            f"UTC: {send_at_utc.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Local: {local_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )

    async def _respond(self, message, text: str, reply_markup=None) -> None:
        try:
            await message.reply_text(text, reply_markup=reply_markup)
            return
        except Exception as exc:
            self.log.warning("reply_text failed, fallback to send_message. err=%s", exc)
        await self.client.send_message("me", text, reply_markup=reply_markup)

    def _bind_handlers(self) -> None:
        @self.client.on_message(filters.group & filters.incoming)
        async def _on_group_message(client: Client, message) -> None:
            await self._handle_group_message(client, message)

        @self.client.on_message(filters.private & filters.text)
        async def _on_private_self_text(client: Client, message) -> None:
            await self._handle_private_command(message)

        @self.client.on_callback_query(filters.regex(r"^menu:"))
        async def _on_menu_callback(client: Client, callback_query) -> None:
            await self._handle_menu_callback(callback_query)

    def _menu_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Help", callback_data="menu:help"),
                    InlineKeyboardButton("My Groups", callback_data="menu:mygroups"),
                ],
                [
                    InlineKeyboardButton("Setup Wizard", callback_data="menu:setup"),
                    InlineKeyboardButton("Schedules", callback_data="menu:schedules"),
                ],
                [
                    InlineKeyboardButton("Collect Links", callback_data="menu:collect_links"),
                    InlineKeyboardButton("Odoo Ping", callback_data="menu:odoo_ping"),
                ],
                [
                    InlineKeyboardButton("Close", callback_data="menu:close"),
                ],
            ]
        )

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
                        if not sender_id:
                            self.log.info(
                                "dynamic route skipped missing-sender chat=%s keyword=%r msg=%s",
                                message.chat.id,
                                keyword,
                                message.id,
                            )
                            return
                        delay = self.cfg.route_dm_delay_seconds
                        asyncio.create_task(
                            self._send_route_dm_after_delay(
                                user_id=sender_id,
                                text=route["response"],
                                delay_seconds=delay,
                                chat_id=message.chat.id,
                                keyword=keyword,
                                msg_id=message.id,
                            )
                        )
                        self.log.info(
                            "dynamic route queued dm user=%s delay=%ss chat=%s keyword=%r msg=%s",
                            sender_id,
                            delay,
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
        if not message.chat:
            return
        chat_id = getattr(message.chat, "id", None)
        from_user_id = getattr(getattr(message, "from_user", None), "id", None)
        is_outgoing = bool(getattr(message, "outgoing", False))
        is_saved_messages = self._self_user_id is not None and chat_id == self._self_user_id
        if not (is_outgoing or is_saved_messages or (self._self_user_id is not None and from_user_id == self._self_user_id)):
            return
        text = (message.text or "").strip()
        self.log.info("private command candidate chat=%s from=%s outgoing=%s text=%r", chat_id, from_user_id, is_outgoing, text[:120])
        if self._setup_state and not text.startswith("."):
            consumed = await self._handle_setup_wizard(message)
            if consumed:
                return
        if not text.startswith("."):
            return

        cmd, _, payload = text.partition(" ")
        cmd = cmd.lower()
        payload = payload.strip()

        if cmd == ".help":
            await self._respond(
                message,
                "\n".join(
                    [
                        "User Client Commands:",
                        ".help",
                        ".menu",
                        ".addroute <chat_id> | <keyword> | <response>",
                        ".delroute <chat_id> | <keyword>",
                        ".listroutes <chat_id>",
                        ".mygroups",
                        ".setup",
                        ".setup_cancel",
                        ".odoo_ping",
                        ".schedule <chat> | <YYYY-MM-DD HH:MM> | <text>",
                        ".schedule_in <chat> | <minutes> | <text>",
                        ".schedules",
                        ".cancel_schedule <id>",
                        ".collect_links",
                    ]
                ),
            )
            return

        if cmd == ".schedule":
            await self._cmd_schedule(message, payload)
            return

        if cmd == ".menu":
            self.log.info("menu command received chat=%s", chat_id)
            await self._respond(
                message,
                "\n".join(
                    [
                        "User client menu",
                        "",
                        "Quick Start",
                        "1) .mygroups",
                        "2) .setup",
                        "3) Send chat_id, then 'keyword: response' lines",
                        "",
                        "Auto Reply",
                        "- .addroute <chat_id> | <keyword> | <response>",
                        "- .delroute <chat_id> | <keyword>",
                        "- .listroutes <chat_id>",
                        "",
                        "Scheduler",
                        "- .schedule <chat> | <YYYY-MM-DD HH:MM> | <text>",
                        "- .schedule_in <chat> | <minutes> | <text>",
                        "- .schedules",
                        "- .cancel_schedule <id>",
                        "",
                        "Tools",
                        "- .collect_links",
                        "- .odoo_ping",
                        "- .help",
                    ]
                ),
                reply_markup=self._menu_keyboard(),
            )
            return

        if cmd == ".addroute":
            await self._cmd_addroute(message, payload)
            return

        if cmd == ".delroute":
            await self._cmd_delroute(message, payload)
            return

        if cmd == ".listroutes":
            await self._cmd_listroutes(message, payload)
            return

        if cmd == ".mygroups":
            await self._cmd_mygroups(message)
            return

        if cmd == ".setup":
            await self._cmd_setup(message)
            return

        if cmd == ".setup_cancel":
            self._setup_state = None
            await self._respond(message, "Setup cancelled.")
            return

        if cmd == ".odoo_ping":
            await self._cmd_odoo_ping(message)
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

        await self._respond(message, "Unknown command. Use .help")

    async def _handle_menu_callback(self, callback_query) -> None:
        data = callback_query.data or ""
        await callback_query.answer()
        msg = callback_query.message
        if not msg:
            return

        if data == "menu:help":
            await msg.reply_text("Use `.help` for full command list.")
            return
        if data == "menu:mygroups":
            await self._cmd_mygroups(msg)
            return
        if data == "menu:setup":
            await self._cmd_setup(msg)
            return
        if data == "menu:schedules":
            await self._cmd_schedules(msg)
            return
        if data == "menu:collect_links":
            await self._cmd_collect_links(msg)
            return
        if data == "menu:odoo_ping":
            await self._cmd_odoo_ping(msg)
            return
        if data == "menu:close":
            try:
                await msg.edit_text("Menu closed.")
            except Exception:
                pass

    async def _cmd_mygroups(self, message) -> None:
        groups: list[str] = []
        async for dialog in self.client.get_dialogs():
            chat = dialog.chat
            if not chat:
                continue
            if str(chat.type).lower() not in {"chattype.group", "chattype.supergroup"}:
                continue
            title = chat.title or str(chat.id)
            groups.append(f"- {title} | {chat.id}")
        if not groups:
            await self._respond(message, "No groups found in this account.")
            return
        await self._respond(message, "Your groups:\n" + "\n".join(groups[:100]))

    async def _cmd_setup(self, message) -> None:
        self._setup_state = {"step": "chat_id"}
        await self._respond(
            message,
            "Setup wizard started.\n"
            "Step 1/2: send target `chat_id`.\n"
            "Then step 2/2: send routes lines in format:\n"
            "`keyword: response`\n"
            "Use `.setup_cancel` to stop."
        )

    async def _handle_setup_wizard(self, message) -> bool:
        if not self._setup_state:
            return False
        text = (message.text or "").strip()
        if not text:
            return True
        step = self._setup_state.get("step")
        if step == "chat_id":
            try:
                chat_id = int(text)
            except ValueError:
                await self._respond(message, "Invalid chat_id. Send an integer like -1001234567890.")
                return True
            self._setup_state = {"step": "routes", "chat_id": chat_id}
            await self._respond(
                message,
                "Step 2/2: send one or multiple lines:\n"
                "`keyword: response`\n"
                "Example:\n"
                "hello: Hi there\n"
                "price: Contact admin"
            )
            return True

        if step == "routes":
            chat_id = int(self._setup_state["chat_id"])
            saved = 0
            invalid: list[str] = []
            for line in text.splitlines():
                raw = line.strip()
                if not raw:
                    continue
                if ":" not in raw:
                    invalid.append(raw)
                    continue
                keyword, response = raw.split(":", 1)
                keyword = keyword.strip()
                response = response.strip()
                if not keyword or not response:
                    invalid.append(raw)
                    continue
                self.repo.upsert_auto_reply_route(chat_id=chat_id, keyword=keyword, response=response)
                saved += 1

            if saved == 0:
                await self._respond(message, "No valid routes found. Use `keyword: response` format.")
                return True
            self._setup_state = None
            tail = f"\nInvalid lines: {len(invalid)}" if invalid else ""
            if self.cfg.odoo_enabled:
                tail += "\nWarning: Odoo sync is enabled and may overwrite local routes."
            await self._respond(message, f"Setup complete. Saved {saved} routes for {chat_id}.{tail}")
            return True
        return False

    async def _cmd_addroute(self, message, payload: str) -> None:
        normalized = payload.replace(" ", "")
        if normalized in {"||", "| |".replace(" ", "")}:
            await self._cmd_setup(message)
            return

        parts = [p.strip() for p in payload.split("|", 2)]
        if len(parts) != 3 or not all(parts):
            await self._respond(
                message,
                "Format: `.addroute chat_id | keyword | response`\n"
                "Shortcut: `.addroute | |` (starts setup wizard)"
            )
            return
        raw_chat_id, keyword, response = parts
        try:
            chat_id = int(raw_chat_id)
        except ValueError:
            await self._respond(message, "chat_id must be an integer.")
            return
        self.repo.upsert_auto_reply_route(chat_id=chat_id, keyword=keyword, response=response)
        tail = "\nWarning: Odoo sync may overwrite this route." if self.cfg.odoo_enabled else ""
        await self._respond(message, f"Route saved for {chat_id}: `{keyword}` -> {response}{tail}")

    async def _cmd_delroute(self, message, payload: str) -> None:
        parts = [p.strip() for p in payload.split("|", 1)]
        if len(parts) != 2 or not all(parts):
            await self._respond(message, "Format: .delroute chat_id | keyword")
            return
        raw_chat_id, keyword = parts
        try:
            chat_id = int(raw_chat_id)
        except ValueError:
            await self._respond(message, "chat_id must be an integer.")
            return
        deleted = self.repo.delete_auto_reply_route(chat_id=chat_id, keyword=keyword)
        if deleted:
            tail = "\nWarning: Odoo sync may recreate routes from Odoo source." if self.cfg.odoo_enabled else ""
            await self._respond(message, f"Route deleted for {chat_id}: `{keyword}`{tail}")
        else:
            await self._respond(message, "Route not found.")

    async def _cmd_listroutes(self, message, payload: str) -> None:
        raw_chat_id = payload.strip()
        if not raw_chat_id:
            await self._respond(message, "Format: .listroutes chat_id")
            return
        try:
            chat_id = int(raw_chat_id)
        except ValueError:
            await self._respond(message, "chat_id must be an integer.")
            return
        rows = self.repo.list_auto_reply_routes(chat_id=chat_id)
        if not rows:
            await self._respond(message, "No routes configured for this chat.")
            return
        lines = []
        for row in rows[:30]:
            preview = (row["response"] or "").replace("\n", " ")[:60]
            source = row["source"] if "source" in row.keys() else "local"
            lines.append(f"- [{source}] {row['keyword']} -> {preview}")
        if len(rows) > 30:
            lines.append(f"...and {len(rows) - 30} more")
        await self._respond(message, "Routes:\n" + "\n".join(lines))

    async def _cmd_odoo_ping(self, message) -> None:
        if not self.cfg.odoo_enabled:
            await self._respond(message, "Odoo mode is disabled. Set ODOO_ENABLED=1 in .env.user.")
            return
        if not (self.cfg.odoo_url and self.cfg.odoo_db and self.cfg.odoo_username and self.cfg.odoo_password):
            await self._respond(message, "Missing Odoo config. Check ODOO_URL/ODOO_DB/ODOO_USERNAME/ODOO_PASSWORD.")
            return

        try:
            client = OdooApiClient(
                url=self.cfg.odoo_url,
                db=self.cfg.odoo_db,
                username=self.cfg.odoo_username,
                password=self.cfg.odoo_password,
            )
            uid = client.authenticate()
            session_exists = client.fetch_account_session_string(
                account_model=self.cfg.odoo_account_model,
                account_ref=self.cfg.odoo_account_ref,
                phone_number=self.cfg.odoo_phone_number,
            )
            routes = client.fetch_auto_reply_routes(
                model=self.cfg.odoo_auto_reply_model,
                account_ref=self.cfg.odoo_account_ref,
                phone_number=self.cfg.odoo_phone_number,
            )
            await self._respond(
                message,
                "\n".join(
                    [
                        "Odoo ping: OK",
                        f"uid: {uid}",
                        f"account_ref: {self.cfg.odoo_account_ref}",
                        f"phone: {self.cfg.odoo_phone_number}",
                        f"session_string_found: {'yes' if session_exists else 'no'}",
                        f"routes_found: {len(routes)}",
                    ]
                )
            )
        except Exception as exc:
            await self._respond(message, f"Odoo ping failed: {type(exc).__name__}: {exc}")

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
            f"Scheduled job #{job_id}\nTarget: {target}\nMessage: {text}\n{self._format_when(send_at_utc)}"
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
            f"Scheduled job #{job_id}\nTarget: {target}\nMessage: {text}\n{self._format_when(send_at_utc)}"
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
            self._self_user_id = me.id
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

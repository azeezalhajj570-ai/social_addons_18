from __future__ import annotations

import asyncio
import logging

from user_client_app.config import Config
from user_client_app.integrations.odoo_api_client import OdooApiClient
from user_client_app.storage import Repository


class OdooAutoReplySyncRunner:
    def __init__(self, cfg: Config, repo: Repository, log: logging.Logger) -> None:
        self.cfg = cfg
        self.repo = repo
        self.log = log
        self.client = OdooApiClient(
            url=cfg.odoo_url,
            db=cfg.odoo_db,
            username=cfg.odoo_username,
            password=cfg.odoo_password,
        )

    def validate_config(self) -> None:
        missing = []
        if not self.cfg.odoo_url:
            missing.append("ODOO_URL")
        if not self.cfg.odoo_db:
            missing.append("ODOO_DB")
        if not self.cfg.odoo_username:
            missing.append("ODOO_USERNAME")
        if not self.cfg.odoo_password:
            missing.append("ODOO_PASSWORD")
        if not self.cfg.odoo_phone_number:
            missing.append("ODOO_PHONE_NUMBER (or PHONE_NUMBER)")
        if missing:
            raise RuntimeError(f"Odoo enabled but missing config: {', '.join(missing)}")

    async def _sync_once(self) -> None:
        routes = await asyncio.to_thread(
            self.client.fetch_auto_reply_routes,
            self.cfg.odoo_auto_reply_model,
            self.cfg.odoo_account_ref,
            self.cfg.odoo_phone_number,
        )
        await asyncio.to_thread(self.repo.replace_auto_reply_routes_from_odoo, routes)
        self.log.info(
            "odoo auto-reply sync ok account_ref=%s phone=%s routes=%s model=%s",
            self.cfg.odoo_account_ref,
            self.cfg.odoo_phone_number,
            len(routes),
            self.cfg.odoo_auto_reply_model,
        )

    async def run_forever(self) -> None:
        self.validate_config()
        while True:
            try:
                await self._sync_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.log.error("odoo auto-reply sync failed: %s", exc)
            await asyncio.sleep(self.cfg.odoo_sync_seconds)

from __future__ import annotations

import asyncio
from dataclasses import replace

from dotenv import load_dotenv

from user_client_app.app import UserClientApp
from user_client_app.config import load_config
from user_client_app.integrations.odoo_api_client import OdooApiClient
from user_client_app.logging_config import setup_logging
from user_client_app.storage import Repository


def _resolve_session_from_odoo(cfg, log):
    if not cfg.odoo_enabled:
        return cfg
    if cfg.session_string:
        return cfg
    try:
        client = OdooApiClient(
            url=cfg.odoo_url,
            db=cfg.odoo_db,
            username=cfg.odoo_username,
            password=cfg.odoo_password,
        )
        session = client.fetch_account_session_string(
            account_model=cfg.odoo_account_model,
            account_ref=cfg.odoo_account_ref,
            phone_number=cfg.odoo_phone_number,
        )
        if not session:
            log.warning(
                "No authorized session_string found in Odoo for ref=%s phone=%s",
                cfg.odoo_account_ref,
                cfg.odoo_phone_number,
            )
            return cfg
        log.info("Loaded session_string from Odoo for ref=%s phone=%s", cfg.odoo_account_ref, cfg.odoo_phone_number)
        return replace(cfg, session_string=session)
    except Exception as exc:
        log.error("Failed loading session_string from Odoo: %s", exc)
        return cfg


async def amain() -> None:
    load_dotenv(".env.user")
    log = setup_logging()
    cfg = load_config()
    cfg = _resolve_session_from_odoo(cfg, log)
    repo = Repository(cfg.db_path, cfg.db_url)
    app = UserClientApp(cfg, repo, log)
    await app.run()


def main() -> None:
    asyncio.run(amain())

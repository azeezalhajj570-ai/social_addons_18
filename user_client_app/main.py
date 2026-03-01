from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

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


def _has_local_session_file(session_name: str) -> bool:
    base = Path(f"{session_name}.session")
    return base.exists()


async def amain() -> None:
    load_dotenv(".env.user")
    log = setup_logging()
    cfg = load_config()
    cfg = _resolve_session_from_odoo(cfg, log)
    if not cfg.session_string and not _has_local_session_file(cfg.session_name):
        raise SystemExit(
            "No Telegram session found. Run CLI auth first: "
            "docker compose -f docker-compose-prod.yml run --rm user-client "
            "python -m user_client_app.auth_cli"
        )
    repo = Repository(cfg.db_path, cfg.db_url)
    app = UserClientApp(cfg, repo, log)
    await app.run()


def main() -> None:
    try:
        asyncio.run(amain())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"user-client startup failed: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()

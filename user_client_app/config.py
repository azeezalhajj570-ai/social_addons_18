from __future__ import annotations

import os
from dataclasses import dataclass


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


def as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    session_name: str
    session_string: str | None
    db_path: str
    db_url: str | None
    auto_reply_user_id: int
    auto_reply_text: str
    auto_reply_cooldown_seconds: int
    route_dm_delay_seconds: int
    scheduler_poll_seconds: int
    odoo_enabled: bool
    odoo_url: str
    odoo_db: str
    odoo_username: str
    odoo_password: str
    odoo_auto_reply_model: str
    odoo_account_model: str
    odoo_account_ref: str
    odoo_phone_number: str
    odoo_sync_seconds: int


def load_config() -> Config:
    session_name = os.getenv("SESSION_NAME", "user_client")
    return Config(
        api_id=int(require_env("API_ID")),
        api_hash=require_env("API_HASH"),
        session_name=session_name,
        session_string=os.getenv("SESSION_STRING", "").strip() or None,
        db_path=os.getenv("USER_CLIENT_DB_PATH", "user_client_app/user_client.db"),
        db_url=os.getenv("USER_CLIENT_DB_URL", "").strip() or None,
        auto_reply_user_id=int(os.getenv("AUTO_REPLY_USER_ID", "0")),
        auto_reply_text=os.getenv("AUTO_REPLY_TEXT", "Hello"),
        auto_reply_cooldown_seconds=int(os.getenv("AUTO_REPLY_COOLDOWN_SECONDS", "8")),
        route_dm_delay_seconds=max(0, int(os.getenv("ROUTE_DM_DELAY_SECONDS", "30"))),
        scheduler_poll_seconds=max(1, int(os.getenv("SCHEDULER_POLL_SECONDS", "2"))),
        odoo_enabled=as_bool(os.getenv("ODOO_ENABLED", "0")),
        odoo_url=os.getenv("ODOO_URL", "").strip(),
        odoo_db=os.getenv("ODOO_DB", "").strip(),
        odoo_username=os.getenv("ODOO_USERNAME", "").strip(),
        odoo_password=os.getenv("ODOO_PASSWORD", "").strip(),
        odoo_auto_reply_model=os.getenv("ODOO_AUTO_REPLY_MODEL", "telegram.auto.reply.route").strip(),
        odoo_account_model=os.getenv("ODOO_ACCOUNT_MODEL", "telegram.user.account").strip(),
        odoo_account_ref=os.getenv("ODOO_ACCOUNT_REF", session_name).strip() or session_name,
        odoo_phone_number=os.getenv("ODOO_PHONE_NUMBER", os.getenv("PHONE_NUMBER", "").strip()).strip(),
        odoo_sync_seconds=max(5, int(os.getenv("ODOO_SYNC_SECONDS", "30"))),
    )

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.errors import PhoneCodeExpired, PhoneCodeInvalid, SessionPasswordNeeded

from user_client_app.config import load_config


def _require_phone(phone_number: str) -> str:
    value = phone_number.strip()
    if not value:
        value = input("Enter Telegram phone number (international format, e.g. +15551234567): ").strip()
    if not value:
        raise SystemExit("Phone number is required for CLI login")
    return value


def _is_auth_key_unregistered(exc: Exception) -> bool:
    return "AUTH_KEY_UNREGISTERED" in str(exc).upper()


def _clear_local_session(session_name: str) -> None:
    base = Path(f"{session_name}.session")
    for path in (
        base,
        Path(f"{session_name}.session-journal"),
        Path(f"{session_name}.session-shm"),
        Path(f"{session_name}.session-wal"),
    ):
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass


def main() -> None:
    load_dotenv(".env.user")
    cfg = load_config()
    phone = _require_phone(cfg.odoo_phone_number or "")

    client = Client(
        cfg.session_name,
        api_id=cfg.api_id,
        api_hash=cfg.api_hash,
        session_string=cfg.session_string,
    )

    client.connect()
    try:
        needs_login = False
        try:
            me = client.get_me()
            needs_login = me is None
        except Exception as exc:
            if not _is_auth_key_unregistered(exc):
                raise

            if cfg.session_string:
                raise SystemExit(
                    "SESSION_STRING is invalid/unregistered. Remove SESSION_STRING from .env.user and run login again."
                ) from exc

            print("Found invalid local session, resetting and starting fresh login...")
            client.disconnect()
            _clear_local_session(cfg.session_name)
            client.connect()
            needs_login = True

        if needs_login:
            sent = client.send_code(phone)
            code = input("Enter Telegram login code: ").strip()
            try:
                client.sign_in(phone_number=phone, phone_code_hash=sent.phone_code_hash, phone_code=code)
            except SessionPasswordNeeded:
                password = input("Enter Telegram 2FA password: ").strip()
                client.check_password(password)
            except PhoneCodeInvalid:
                raise SystemExit("Invalid login code")
            except PhoneCodeExpired:
                raise SystemExit("Login code expired")

        me = client.get_me()
        session_string = client.export_session_string()

        print(f"Logged in as: {me.first_name} (@{me.username or ''}) id={me.id}")
        print("Save this to .env.user:")
        print(f"SESSION_STRING={session_string}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()

from __future__ import annotations

from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.errors import PhoneCodeExpired, PhoneCodeInvalid, SessionPasswordNeeded

from user_client_app.config import load_config


def _require_phone(phone_number: str) -> str:
    value = phone_number.strip()
    if not value:
        raise SystemExit("Missing PHONE_NUMBER in .env.user for CLI login")
    return value


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
        if client.get_me() is None:
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

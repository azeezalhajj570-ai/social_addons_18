# Telegram User Client (Separate App)

This is a separate app from your bot.  
It logs in as a **real Telegram user account** using MTProto (`API_ID` + `API_HASH`).

## Choose library

- `Telethon`: more low-level control/flexibility
- `Pyrogram`: cleaner high-level API

## Setup

1. Install deps:

```bash
pip install -r requirements-user-client.txt
```

2. Create `.env.user` from `.env.user.example`:

```env
API_ID=123456
API_HASH=YOUR_API_HASH
PHONE_NUMBER=+15551234567
SESSION_NAME=user_client
```

Get `API_ID` and `API_HASH` from: https://my.telegram.org

## Run (Telethon)

```bash
python user_client_app/telethon_user_client.py
```

- First run asks for login code.
- If 2FA is enabled, it asks for password.
- Creates a local session file (`SESSION_NAME.session`).

## Run (Pyrogram)

```bash
python user_client_app/pyrogram_user_client.py
```

- First run performs login flow in terminal.
- Also creates local session file.

Use commands in your Saved Messages chat:

```text
.help
.addroute <chat_id> | <keyword> | <response>
.delroute <chat_id> | <keyword>
.listroutes <chat_id>
.schedule <chat> | <YYYY-MM-DD HH:MM> | <text>
.schedule_in <chat> | <minutes> | <text>
.schedules
.cancel_schedule <id>
.collect_links
```

## Odoo Source Of Truth (Recommended)

You can manage auto-reply routes from Odoo and let the user client sync from Odoo.

Environment in `.env.user`:

```env
ODOO_ENABLED=1
ODOO_URL=https://your-odoo-host
ODOO_DB=your_db
ODOO_USERNAME=your_user
ODOO_PASSWORD=your_password
ODOO_ACCOUNT_MODEL=telegram.user.account
ODOO_AUTO_REPLY_MODEL=telegram.auto.reply.route
ODOO_ACCOUNT_REF=user_client
ODOO_PHONE_NUMBER=+15551234567
ODOO_SYNC_SECONDS=30
```

- Install Odoo addon from `odoo_addons/telegram_user_client_sync`
- In Odoo, create record in `telegram.user.account`
  - set `account_ref`, `phone_number`, `api_id`, `api_hash`
  - keep `manual_session_only = True`
  - paste `session_string` from Flask in the account form
  - click **Fetch Chats** to import your Telegram groups into Odoo
- User client loads `session_string` from Odoo automatically
- Then create routes in `telegram.auto.reply.route` linked to that account

When Odoo mode is enabled:

- route source of truth is Odoo
- local `.addroute` and `.delroute` commands are disabled

## Notes

- Keep your `API_HASH` and session file private.
- Do not use user-account automation in ways that violate Telegram Terms.
- On Python 3.13 (Windows), `tgcrypto` may fail to compile without MSVC Build Tools.
  - App still works without it (slower crypto path).
  - If you need max speed, install Microsoft C++ Build Tools then install `tgcrypto`.

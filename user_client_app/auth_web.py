from __future__ import annotations

import secrets
import sys
import time
import asyncio
from dataclasses import dataclass
from html import escape
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.errors import PhoneCodeExpired, PhoneCodeInvalid, SessionPasswordNeeded

# Allow running as: python user_client_app/auth_web.py
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from user_client_app.config import load_config
from user_client_app.storage import Repository

AUTH_TTL_SECONDS = 10 * 60


@dataclass
class PendingAuth:
    token: str
    phone_number: str
    phone_code_hash: str
    client: Client
    created_at: float
    awaiting_password: bool = False


load_dotenv(".env.user")
cfg = load_config()
app = Flask(__name__)
_pending: dict[str, PendingAuth] = {}
repo = Repository(cfg.db_path, cfg.db_url)


def _render_page(content: str) -> str:
    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>User Client Auth</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; background: #f7f7f8; }}
    .card {{ background: #fff; border: 1px solid #ddd; border-radius: 10px; padding: 1rem; margin-bottom: 1rem; }}
    input {{ width: 100%; padding: .65rem; margin: .4rem 0 1rem; border: 1px solid #bbb; border-radius: 8px; }}
    button {{ padding: .6rem 1rem; border: none; border-radius: 8px; background: #1565c0; color: #fff; cursor: pointer; }}
    .warn {{ color: #a15c00; }}
    .ok {{ color: #0a7a35; }}
    .err {{ color: #b00020; }}
    code {{ background: #f1f1f1; padding: .15rem .3rem; border-radius: 4px; }}
  </style>
</head>
<body>
  <h2>User Client Login</h2>
  <p><a href="/">Login</a> | <a href="/routes">Manage Auto Replies</a></p>
  <p class="warn">Stop any running user client before login, so the session is not locked.</p>
  {content}
</body>
</html>
"""


def _disconnect_safely(client: Client) -> None:
    try:
        client.disconnect()
    except Exception:
        pass


def _ensure_event_loop() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _cleanup_token(token: str) -> None:
    item = _pending.pop(token, None)
    if item:
        _disconnect_safely(item.client)


def _get_pending(token: str) -> PendingAuth | None:
    item = _pending.get(token)
    if not item:
        return None
    if (time.time() - item.created_at) > AUTH_TTL_SECONDS:
        _cleanup_token(token)
        return None
    return item


def _phone_form(note: str = "") -> str:
    msg = f'<p class="err">{escape(note)}</p>' if note else ""
    return f"""
<div class="card">
  <h3>1) Enter Phone Number</h3>
  {msg}
  <form method="post" action="/auth/send-code">
    <label>Phone number (international format)</label>
    <input name="phone_number" placeholder="+15551234567" required />
    <button type="submit">Send Login Code</button>
  </form>
</div>
"""


def _code_form(token: str, note: str = "") -> str:
    msg = f'<p class="err">{escape(note)}</p>' if note else "<p>Code sent. Enter the code from Telegram.</p>"
    return f"""
<div class="card">
  <h3>2) Enter SMS/Login Code</h3>
  {msg}
  <form method="post" action="/auth/verify-code">
    <input type="hidden" name="token" value="{escape(token)}" />
    <label>Code</label>
    <input name="code" placeholder="12345" required />
    <button type="submit">Verify Code</button>
  </form>
</div>
"""


def _password_form(token: str, note: str = "") -> str:
    msg = f'<p class="err">{escape(note)}</p>' if note else "<p>2FA is enabled. Enter your password.</p>"
    return f"""
<div class="card">
  <h3>3) Enter 2FA Password</h3>
  {msg}
  <form method="post" action="/auth/verify-password">
    <input type="hidden" name="token" value="{escape(token)}" />
    <label>Password</label>
    <input type="password" name="password" required />
    <button type="submit">Verify Password</button>
  </form>
</div>
"""


def _build_account_client() -> Client:
    return Client(
        cfg.session_name,
        api_id=cfg.api_id,
        api_hash=cfg.api_hash,
        session_string=cfg.session_string,
    )


def _routes_page(note: str = "", selected_chat_id: int | None = None) -> str:
    _ensure_event_loop()
    groups: list[tuple[int, str]] = []
    routes = []
    error: str | None = None
    me_display = "Unknown"
    client = _build_account_client()
    try:
        client.connect()
        me = client.get_me()
        me_display = f"{me.first_name or 'User'} (@{me.username or ''}) id={me.id}"
        for dialog in client.get_dialogs():
            chat = dialog.chat
            if not chat:
                continue
            if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
                continue
            title = chat.title or f"Chat {chat.id}"
            groups.append((chat.id, title))
    except Exception as exc:
        error = str(exc)
    finally:
        _disconnect_safely(client)

    if selected_chat_id is None and groups:
        selected_chat_id = groups[0][0]

    if selected_chat_id is not None:
        routes = repo.list_auto_reply_routes(selected_chat_id)

    note_html = f'<p class="ok">{escape(note)}</p>' if note else ""
    err_html = f'<p class="err">{escape(error)}</p>' if error else ""

    group_options = []
    for chat_id, title in groups:
        selected = " selected" if selected_chat_id == chat_id else ""
        group_options.append(f'<option value="{chat_id}"{selected}>{escape(title)} ({chat_id})</option>')
    options_html = "\n".join(group_options) if group_options else '<option value="">No groups found</option>'

    route_rows = []
    for row in routes:
        keyword = row["keyword"]
        response = row["response"]
        route_rows.append(
            f"""
<tr>
  <td><code>{escape(keyword)}</code></td>
  <td>{escape(response)}</td>
  <td>
    <form method="post" action="/routes/delete">
      <input type="hidden" name="chat_id" value="{selected_chat_id or ''}">
      <input type="hidden" name="keyword" value="{escape(keyword)}">
      <button type="submit">Delete</button>
    </form>
  </td>
</tr>
"""
        )
    routes_table = (
        """
<table style="width:100%;border-collapse:collapse">
  <thead><tr><th align="left">Keyword</th><th align="left">Response</th><th align="left">Action</th></tr></thead>
  <tbody>
"""
        + ("\n".join(route_rows) if route_rows else '<tr><td colspan="3">No routes for this group yet.</td></tr>')
        + """
  </tbody>
</table>
"""
    )

    return f"""
<div class="card">
  <h3>Auto Reply Routes</h3>
  <p>Account: <code>{escape(me_display)}</code></p>
  {note_html}
  {err_html}
  <form method="get" action="/routes">
    <label>Select group</label>
    <select name="chat_id" style="width:100%; padding:.6rem; margin:.4rem 0 1rem; border:1px solid #bbb; border-radius:8px;">
      {options_html}
    </select>
    <button type="submit">Load Routes</button>
  </form>
</div>

<div class="card">
  <h3>Add/Update Route</h3>
  <form method="post" action="/routes/save">
    <label>Chat ID</label>
    <input name="chat_id" value="{selected_chat_id or ''}" placeholder="-1001234567890" required />
    <label>Keyword</label>
    <input name="keyword" placeholder="hello" required />
    <label>Response</label>
    <input name="response" placeholder="Hi there!" required />
    <button type="submit">Save Route</button>
  </form>
</div>

<div class="card">
  <h3>Current Routes</h3>
  {routes_table}
</div>
"""


@app.get("/")
def index() -> str:
    return _render_page(_phone_form())


@app.get("/routes")
def routes_page() -> str:
    raw_chat_id = (request.args.get("chat_id") or "").strip()
    chat_id: int | None = None
    if raw_chat_id:
        try:
            chat_id = int(raw_chat_id)
        except ValueError:
            return _render_page(_routes_page("Invalid chat_id."))
    return _render_page(_routes_page(selected_chat_id=chat_id))


@app.post("/routes/save")
def routes_save() -> str:
    raw_chat_id = (request.form.get("chat_id") or "").strip()
    keyword = (request.form.get("keyword") or "").strip()
    response = (request.form.get("response") or "").strip()
    try:
        chat_id = int(raw_chat_id)
    except ValueError:
        return _render_page(_routes_page("chat_id must be an integer."))
    if not keyword or not response:
        return _render_page(_routes_page("keyword and response are required.", selected_chat_id=chat_id))
    repo.upsert_auto_reply_route(chat_id=chat_id, keyword=keyword, response=response)
    return _render_page(_routes_page(f"Route saved for {chat_id}.", selected_chat_id=chat_id))


@app.post("/routes/delete")
def routes_delete() -> str:
    raw_chat_id = (request.form.get("chat_id") or "").strip()
    keyword = (request.form.get("keyword") or "").strip()
    try:
        chat_id = int(raw_chat_id)
    except ValueError:
        return _render_page(_routes_page("Invalid chat_id."))
    if not keyword:
        return _render_page(_routes_page("keyword is required.", selected_chat_id=chat_id))
    deleted = repo.delete_auto_reply_route(chat_id=chat_id, keyword=keyword)
    msg = "Route deleted." if deleted else "Route not found."
    return _render_page(_routes_page(msg, selected_chat_id=chat_id))


@app.post("/auth/send-code")
def send_code() -> str:
    _ensure_event_loop()
    phone = (request.form.get("phone_number") or "").strip()
    if not phone:
        return _render_page(_phone_form("Phone number is required."))

    token = secrets.token_urlsafe(24)
    client = Client(
        name=f"{cfg.session_name}_web_{token[:8]}",
        api_id=cfg.api_id,
        api_hash=cfg.api_hash,
        in_memory=True,
    )

    try:
        client.connect()
        sent = client.send_code(phone)
    except Exception as exc:
        _disconnect_safely(client)
        return _render_page(_phone_form(f"Failed to send code: {exc}"))

    _pending[token] = PendingAuth(
        token=token,
        phone_number=phone,
        phone_code_hash=sent.phone_code_hash,
        client=client,
        created_at=time.time(),
    )
    return _render_page(_code_form(token))


@app.post("/auth/verify-code")
def verify_code() -> str:
    token = (request.form.get("token") or "").strip()
    code = (request.form.get("code") or "").strip()
    pending = _get_pending(token)
    if not pending:
        return _render_page(_phone_form("Session expired. Start again."))

    try:
        pending.client.sign_in(
            phone_number=pending.phone_number,
            phone_code_hash=pending.phone_code_hash,
            phone_code=code,
        )
    except SessionPasswordNeeded:
        pending.awaiting_password = True
        return _render_page(_password_form(token))
    except PhoneCodeInvalid:
        return _render_page(_code_form(token, "Invalid code."))
    except PhoneCodeExpired:
        _cleanup_token(token)
        return _render_page(_phone_form("Code expired. Start again."))
    except Exception as exc:
        return _render_page(_code_form(token, f"Verification failed: {exc}"))

    try:
        me = pending.client.get_me()
        session_string = pending.client.export_session_string()
    except Exception as exc:
        _cleanup_token(token)
        return _render_page(_phone_form(f"Authorized but failed to export session: {exc}"))

    _cleanup_token(token)
    return _render_page(
        f"""
<div class="card">
  <h3 class="ok">Login Successful</h3>
  <p>Connected as <b>{escape(me.first_name or "User")}</b> (@{escape(me.username or "")}).</p>
  <p>Put this in <code>.env.user</code>:</p>
  <p><code>SESSION_STRING={escape(session_string)}</code></p>
</div>
"""
    )


@app.post("/auth/verify-password")
def verify_password() -> str:
    token = (request.form.get("token") or "").strip()
    password = (request.form.get("password") or "").strip()
    pending = _get_pending(token)
    if not pending:
        return _render_page(_phone_form("Session expired. Start again."))
    if not pending.awaiting_password:
        return _render_page(_code_form(token, "Password step not active. Verify code first."))

    try:
        pending.client.check_password(password)
    except Exception as exc:
        return _render_page(_password_form(token, f"Invalid password: {exc}"))

    try:
        me = pending.client.get_me()
        session_string = pending.client.export_session_string()
    except Exception as exc:
        _cleanup_token(token)
        return _render_page(_phone_form(f"Authorized but failed to export session: {exc}"))

    _cleanup_token(token)
    return _render_page(
        f"""
<div class="card">
  <h3 class="ok">Login Successful</h3>
  <p>Connected as <b>{escape(me.first_name or "User")}</b> (@{escape(me.username or "")}).</p>
  <p>Put this in <code>.env.user</code>:</p>
  <p><code>SESSION_STRING={escape(session_string)}</code></p>
</div>
"""
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False, threaded=False)

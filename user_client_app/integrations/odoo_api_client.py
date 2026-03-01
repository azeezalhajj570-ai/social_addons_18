from __future__ import annotations

import xmlrpc.client


class OdooApiClient:
    def __init__(self, url: str, db: str, username: str, password: str) -> None:
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self._uid: int | None = None
        self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def authenticate(self) -> int:
        uid = self._common.authenticate(self.db, self.username, self.password, {})
        if not uid:
            raise RuntimeError("Odoo authentication failed.")
        self._uid = int(uid)
        return self._uid

    @property
    def uid(self) -> int:
        if self._uid is None:
            return self.authenticate()
        return self._uid

    def fetch_auto_reply_routes(
        self, model: str, account_ref: str, phone_number: str | None = None
    ) -> list[dict[str, str | int | bool]]:
        domain = [("account_ref", "=", account_ref), ("enabled", "=", True)]
        if phone_number:
            domain.append(("phone_number", "=", phone_number))
        fields = ["chat_id", "keyword", "response", "enabled", "phone_number"]
        rows = self._models.execute_kw(
            self.db,
            self.uid,
            self.password,
            model,
            "search_read",
            [domain],
            {"fields": fields, "limit": 10000, "order": "id asc"},
        )
        parsed: list[dict[str, str | int | bool]] = []
        for row in rows:
            chat_id_raw = row.get("chat_id")
            keyword = str(row.get("keyword") or "").strip().lower()
            response = str(row.get("response") or "").strip()
            enabled = bool(row.get("enabled", True))
            if not keyword or not response:
                continue
            try:
                chat_id = int(chat_id_raw)
            except Exception:
                continue
            parsed.append(
                {
                    "chat_id": chat_id,
                    "keyword": keyword,
                    "response": response,
                    "enabled": enabled,
                }
            )
        return parsed

    def fetch_account_session_string(self, account_model: str, account_ref: str, phone_number: str) -> str | None:
        domain = [
            ("account_ref", "=", account_ref),
            ("phone_number", "=", phone_number),
            ("enabled", "=", True),
            ("session_string", "!=", False),
        ]
        fields = ["session_string"]
        rows = self._models.execute_kw(
            self.db,
            self.uid,
            self.password,
            account_model,
            "search_read",
            [domain],
            {"fields": fields, "limit": 1, "order": "id desc"},
        )
        if not rows:
            return None
        value = str(rows[0].get("session_string") or "").strip()
        return value or None

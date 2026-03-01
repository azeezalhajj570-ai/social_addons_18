from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - optional dependency at runtime
    psycopg = None
    dict_row = None


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class Repository:
    def __init__(self, db_path: str, db_url: str | None = None) -> None:
        self.db_path = db_path
        self.db_url = (db_url or "").strip() or None
        self.is_postgres = bool(self.db_url and self.db_url.startswith(("postgres://", "postgresql://")))

        if self.is_postgres and psycopg is None:
            raise RuntimeError("PostgreSQL URL provided but psycopg is not installed")

        if not self.is_postgres:
            parent = Path(db_path).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    @contextmanager
    def _conn(self):
        if self.is_postgres:
            conn = psycopg.connect(self.db_url, row_factory=dict_row)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _as_dict_rows(rows: list[Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                output.append(row)
            else:
                output.append(dict(row))
        return output

    def _init_db(self) -> None:
        with self._conn() as conn:
            cur = conn.cursor()
            if self.is_postgres:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scheduled_outbox (
                        id BIGSERIAL PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        target TEXT NOT NULL,
                        text TEXT NOT NULL,
                        send_at_utc TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        sent_at_utc TEXT,
                        sent_message_id BIGINT,
                        error TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS group_link_snapshots (
                        id BIGSERIAL PRIMARY KEY,
                        collected_at TEXT NOT NULL,
                        chat_id BIGINT NOT NULL,
                        title TEXT,
                        username TEXT,
                        invite_link TEXT,
                        error TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS auto_reply_routes (
                        id BIGSERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        keyword TEXT NOT NULL,
                        response TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        source TEXT NOT NULL DEFAULT 'local',
                        created_at TEXT NOT NULL,
                        UNIQUE(chat_id, keyword)
                    )
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE auto_reply_routes
                    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'local'
                    """
                )
            else:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scheduled_outbox (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        target TEXT NOT NULL,
                        text TEXT NOT NULL,
                        send_at_utc TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        sent_at_utc TEXT,
                        sent_message_id INTEGER,
                        error TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS group_link_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        collected_at TEXT NOT NULL,
                        chat_id INTEGER NOT NULL,
                        title TEXT,
                        username TEXT,
                        invite_link TEXT,
                        error TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS auto_reply_routes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER NOT NULL,
                        keyword TEXT NOT NULL,
                        response TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        source TEXT NOT NULL DEFAULT 'local',
                        created_at TEXT NOT NULL,
                        UNIQUE(chat_id, keyword)
                    )
                    """
                )
                columns = {row["name"] for row in conn.execute("PRAGMA table_info(auto_reply_routes)").fetchall()}
                if "source" not in columns:
                    cur.execute("ALTER TABLE auto_reply_routes ADD COLUMN source TEXT NOT NULL DEFAULT 'local'")

    def add_scheduled_message(self, target: str, text: str, send_at_utc: datetime) -> int:
        with self._conn() as conn:
            cur = conn.cursor()
            if self.is_postgres:
                cur.execute(
                    """
                    INSERT INTO scheduled_outbox(created_at, target, text, send_at_utc, status)
                    VALUES (%s, %s, %s, %s, 'pending')
                    RETURNING id
                    """,
                    (utc_now_iso(), target, text, send_at_utc.isoformat()),
                )
                return int(cur.fetchone()["id"])
            cur.execute(
                """
                INSERT INTO scheduled_outbox(created_at, target, text, send_at_utc, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (utc_now_iso(), target, text, send_at_utc.isoformat()),
            )
            return int(cur.lastrowid)

    def list_pending_scheduled(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.cursor()
            if self.is_postgres:
                cur.execute(
                    """
                    SELECT id, target, text, send_at_utc, created_at
                    FROM scheduled_outbox
                    WHERE status = 'pending'
                    ORDER BY send_at_utc ASC
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT id, target, text, send_at_utc, created_at
                    FROM scheduled_outbox
                    WHERE status = 'pending'
                    ORDER BY send_at_utc ASC
                    """
                )
            return self._as_dict_rows(list(cur.fetchall()))

    def get_due_scheduled(self, now_utc: datetime, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.cursor()
            if self.is_postgres:
                cur.execute(
                    """
                    SELECT id, target, text, send_at_utc
                    FROM scheduled_outbox
                    WHERE status = 'pending' AND send_at_utc <= %s
                    ORDER BY send_at_utc ASC
                    LIMIT %s
                    """,
                    (now_utc.isoformat(), limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, target, text, send_at_utc
                    FROM scheduled_outbox
                    WHERE status = 'pending' AND send_at_utc <= ?
                    ORDER BY send_at_utc ASC
                    LIMIT ?
                    """,
                    (now_utc.isoformat(), limit),
                )
            return self._as_dict_rows(list(cur.fetchall()))

    def mark_sent(self, job_id: int, message_id: int | None) -> None:
        with self._conn() as conn:
            cur = conn.cursor()
            if self.is_postgres:
                cur.execute(
                    """
                    UPDATE scheduled_outbox
                    SET status='sent', sent_at_utc=%s, sent_message_id=%s, error=NULL
                    WHERE id=%s
                    """,
                    (utc_now_iso(), message_id, job_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE scheduled_outbox
                    SET status='sent', sent_at_utc=?, sent_message_id=?, error=NULL
                    WHERE id=?
                    """,
                    (utc_now_iso(), message_id, job_id),
                )

    def mark_failed(self, job_id: int, error: str) -> None:
        with self._conn() as conn:
            cur = conn.cursor()
            if self.is_postgres:
                cur.execute(
                    """
                    UPDATE scheduled_outbox
                    SET status='failed', error=%s
                    WHERE id=%s
                    """,
                    (error[:600], job_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE scheduled_outbox
                    SET status='failed', error=?
                    WHERE id=?
                    """,
                    (error[:600], job_id),
                )

    def cancel_pending(self, job_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.cursor()
            if self.is_postgres:
                cur.execute(
                    """
                    UPDATE scheduled_outbox
                    SET status='cancelled'
                    WHERE id=%s AND status='pending'
                    """,
                    (job_id,),
                )
            else:
                cur.execute(
                    """
                    UPDATE scheduled_outbox
                    SET status='cancelled'
                    WHERE id=? AND status='pending'
                    """,
                    (job_id,),
                )
            return cur.rowcount > 0

    def save_link_snapshot(
        self,
        chat_id: int,
        title: str | None,
        username: str | None,
        invite_link: str | None,
        error: str | None = None,
    ) -> None:
        with self._conn() as conn:
            cur = conn.cursor()
            if self.is_postgres:
                cur.execute(
                    """
                    INSERT INTO group_link_snapshots(collected_at, chat_id, title, username, invite_link, error)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (utc_now_iso(), chat_id, title, username, invite_link, error),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO group_link_snapshots(collected_at, chat_id, title, username, invite_link, error)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (utc_now_iso(), chat_id, title, username, invite_link, error),
                )

    def upsert_auto_reply_route(self, chat_id: int, keyword: str, response: str) -> None:
        with self._conn() as conn:
            cur = conn.cursor()
            if self.is_postgres:
                cur.execute(
                    """
                    INSERT INTO auto_reply_routes(chat_id, keyword, response, enabled, source, created_at)
                    VALUES (%s, %s, %s, 1, 'local', %s)
                    ON CONFLICT(chat_id, keyword) DO UPDATE SET
                        response=excluded.response,
                        enabled=1,
                        source='local'
                    """,
                    (chat_id, keyword.strip().lower(), response.strip(), utc_now_iso()),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO auto_reply_routes(chat_id, keyword, response, enabled, source, created_at)
                    VALUES (?, ?, ?, 1, 'local', ?)
                    ON CONFLICT(chat_id, keyword) DO UPDATE SET
                        response=excluded.response,
                        enabled=1,
                        source='local'
                    """,
                    (chat_id, keyword.strip().lower(), response.strip(), utc_now_iso()),
                )

    def delete_auto_reply_route(self, chat_id: int, keyword: str) -> bool:
        with self._conn() as conn:
            cur = conn.cursor()
            if self.is_postgres:
                cur.execute(
                    """
                    DELETE FROM auto_reply_routes
                    WHERE chat_id=%s AND keyword=%s
                    """,
                    (chat_id, keyword.strip().lower()),
                )
            else:
                cur.execute(
                    """
                    DELETE FROM auto_reply_routes
                    WHERE chat_id=? AND keyword=?
                    """,
                    (chat_id, keyword.strip().lower()),
                )
            return cur.rowcount > 0

    def list_auto_reply_routes(self, chat_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.cursor()
            if self.is_postgres:
                cur.execute(
                    """
                    SELECT keyword, response, enabled, source
                    FROM auto_reply_routes
                    WHERE chat_id=%s
                    ORDER BY keyword ASC
                    """,
                    (chat_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT keyword, response, enabled, source
                    FROM auto_reply_routes
                    WHERE chat_id=?
                    ORDER BY keyword ASC
                    """,
                    (chat_id,),
                )
            return self._as_dict_rows(list(cur.fetchall()))

    def replace_auto_reply_routes_from_odoo(self, routes: list[dict[str, str | int | bool]]) -> int:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM auto_reply_routes")
            now = utc_now_iso()
            for row in routes:
                if self.is_postgres:
                    cur.execute(
                        """
                        INSERT INTO auto_reply_routes(chat_id, keyword, response, enabled, source, created_at)
                        VALUES (%s, %s, %s, %s, 'odoo', %s)
                        """,
                        (
                            int(row["chat_id"]),
                            str(row["keyword"]).strip().lower(),
                            str(row["response"]).strip(),
                            1 if bool(row.get("enabled", True)) else 0,
                            now,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO auto_reply_routes(chat_id, keyword, response, enabled, source, created_at)
                        VALUES (?, ?, ?, ?, 'odoo', ?)
                        """,
                        (
                            int(row["chat_id"]),
                            str(row["keyword"]).strip().lower(),
                            str(row["response"]).strip(),
                            1 if bool(row.get("enabled", True)) else 0,
                            now,
                        ),
                    )
            return len(routes)

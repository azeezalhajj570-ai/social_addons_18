from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pyrogram import Client
from pyrogram.enums import ChatType

from user_client_app.storage import Repository


async def collect_group_links(client: Client, repo: Repository) -> tuple[int, int, Path]:
    results: list[dict[str, Any]] = []
    total_groups = 0
    resolved_links = 0

    async for dialog in client.get_dialogs():
        chat = dialog.chat
        if not chat:
            continue
        if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            continue

        total_groups += 1
        username = chat.username
        invite_link: str | None = None
        error: str | None = None
        if username:
            invite_link = f"https://t.me/{username}"
        else:
            try:
                invite_link = await client.export_chat_invite_link(chat.id)
            except Exception as exc:
                error = str(exc)

        if invite_link:
            resolved_links += 1
        repo.save_link_snapshot(
            chat_id=chat.id,
            title=chat.title,
            username=username,
            invite_link=invite_link,
            error=error,
        )
        results.append(
            {
                "chat_id": chat.id,
                "title": chat.title,
                "username": username,
                "invite_link": invite_link,
                "error": error,
            }
        )

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path("logs") / f"group_join_links_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return resolved_links, total_groups, out_path


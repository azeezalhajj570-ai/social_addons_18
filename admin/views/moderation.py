# ruff: noqa: RUF012
from __future__ import annotations

from typing import TYPE_CHECKING

from flask import abort, redirect, request, url_for
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user

if TYPE_CHECKING:
    from werkzeug.wrappers.response import Response


class ModerationBaseView(ModelView):
    can_view_details = True
    details_modal = True
    can_export = True
    export_types = ["csv", "xlsx", "json", "yaml"]

    def is_accessible(self) -> bool:
        if not current_user.is_active or not current_user.is_authenticated:
            return False
        return bool(current_user.has_role("superuser"))

    def _handle_view(self, _name: str, **_kwargs: dict) -> Response | None:
        if not self.is_accessible():
            if current_user.is_authenticated:
                abort(403)
            return redirect(url_for("security.login", next=request.url))
        return None


class GroupSettingsView(ModerationBaseView):
    column_list = [
        "chat_id",
        "anti_links",
        "anti_bots",
        "hide_system",
        "warn_in_dm",
        "warn_in_group",
        "temp_ban_before_remove",
        "temp_ban_seconds",
        "created_at",
    ]
    column_searchable_list = ["chat_id"]
    column_filters = column_list
    column_default_sort = ("created_at", True)


class GroupMetaView(ModerationBaseView):
    column_list = [
        "chat_id",
        "rules_text",
        "welcome_message",
        "goodbye_message",
        "antispam_limit",
        "antispam_window",
        "antiflood_limit",
        "antiflood_window",
        "created_at",
    ]
    column_searchable_list = ["chat_id"]
    column_filters = ["chat_id", "created_at"]
    column_default_sort = ("created_at", True)


class WarningsView(ModerationBaseView):
    column_list = ["id", "chat_id", "user_id", "warns"]
    column_searchable_list = ["chat_id", "user_id"]
    column_filters = ["chat_id", "user_id", "warns"]
    column_default_sort = ("id", True)


class DynamicRulesView(ModerationBaseView):
    column_list = ["id", "chat_id", "pattern", "enabled", "created_at"]
    column_searchable_list = ["chat_id", "pattern"]
    column_filters = ["chat_id", "enabled", "created_at"]
    column_default_sort = ("created_at", True)


class LinkRoutesView(ModerationBaseView):
    column_list = ["id", "chat_id", "keyword", "destination", "gate_group_id", "enabled", "created_at"]
    column_searchable_list = ["chat_id", "keyword", "destination"]
    column_filters = ["chat_id", "enabled", "gate_group_id", "created_at"]
    column_default_sort = ("created_at", True)


class ParticipationGatesView(ModerationBaseView):
    column_list = ["id", "chat_id", "gate_group_id", "gate_title", "join_url", "enabled", "created_at"]
    column_searchable_list = ["chat_id", "gate_group_id", "gate_title", "join_url"]
    column_filters = ["chat_id", "enabled", "created_at"]
    column_default_sort = ("created_at", True)


class FiltersView(ModerationBaseView):
    column_list = ["id", "chat_id", "keyword", "text", "caption", "created_at"]
    column_searchable_list = ["chat_id", "keyword", "text", "caption"]
    column_filters = ["chat_id", "keyword", "created_at"]
    column_default_sort = ("created_at", True)


class ScheduledMessagesView(ModerationBaseView):
    column_list = ["id", "chat_id", "target_chat_id", "text", "interval_seconds", "next_run_at", "enabled", "created_at"]
    column_searchable_list = ["chat_id", "target_chat_id", "text"]
    column_filters = ["chat_id", "target_chat_id", "enabled", "next_run_at", "created_at"]
    column_default_sort = ("next_run_at", False)


class BotCommandsView(ModerationBaseView):
    column_list = ["id", "language_code", "command", "description", "enabled", "sort_order", "created_at"]
    column_searchable_list = ["language_code", "command", "description"]
    column_filters = ["language_code", "command", "enabled", "sort_order", "created_at"]
    column_default_sort = ("sort_order", False)

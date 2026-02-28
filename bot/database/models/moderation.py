from __future__ import annotations
import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bot.database.models.base import Base, created_at, int_pk


class GroupSettingsModel(Base):
    __tablename__ = "group_settings"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, unique=True, autoincrement=False)
    created_at: Mapped[created_at]

    anti_links: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    anti_bots: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    hide_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    warn_in_dm: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    warn_in_group: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    temp_ban_before_remove: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    temp_ban_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)


class WarningModel(Base):
    __tablename__ = "warnings"
    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_warnings_chat_user"),
        Index("ix_warnings_chat_user", "chat_id", "user_id"),
    )

    id: Mapped[int_pk]
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("group_settings.chat_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    warns: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class DynamicRuleModel(Base):
    __tablename__ = "dynamic_remove_rules"
    __table_args__ = (Index("ix_dynamic_rules_chat", "chat_id"),)

    id: Mapped[int_pk]
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("group_settings.chat_id", ondelete="CASCADE"),
        nullable=False,
    )
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[created_at]


class LinkRouteModel(Base):
    __tablename__ = "link_routes"
    __table_args__ = (
        UniqueConstraint("chat_id", "keyword", name="uq_link_routes_chat_keyword"),
        Index("ix_link_routes_chat", "chat_id"),
    )

    id: Mapped[int_pk]
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("group_settings.chat_id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    gate_group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[created_at]


class ParticipationGateModel(Base):
    __tablename__ = "participation_gates"
    __table_args__ = (
        UniqueConstraint("chat_id", "gate_group_id", name="uq_participation_gates_chat_gate"),
        Index("ix_participation_gates_chat", "chat_id"),
    )

    id: Mapped[int_pk]
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("group_settings.chat_id", ondelete="CASCADE"),
        nullable=False,
    )
    gate_group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gate_title: Mapped[str] = mapped_column(String(255), nullable=False)
    join_url: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[created_at]


class GroupMetaModel(Base):
    __tablename__ = "group_meta"

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("group_settings.chat_id", ondelete="CASCADE"),
        primary_key=True,
        unique=True,
        autoincrement=False,
    )
    created_at: Mapped[created_at]
    rules_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    goodbye_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    antispam_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    antispam_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    antiflood_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    antiflood_window: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FilterModel(Base):
    __tablename__ = "filters"
    __table_args__ = (
        UniqueConstraint("chat_id", "keyword", name="uq_filters_chat_keyword"),
        Index("ix_filters_chat", "chat_id"),
    )

    id: Mapped[int_pk]
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("group_settings.chat_id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sticker: Mapped[str | None] = mapped_column(String(255), nullable=True)
    animation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    video: Mapped[str | None] = mapped_column(String(255), nullable=True)
    voice: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audio: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[created_at]


class ScheduledMessageModel(Base):
    __tablename__ = "scheduled_messages"
    __table_args__ = (Index("ix_scheduled_messages_chat", "chat_id"), Index("ix_scheduled_messages_next_run_at", "next_run_at"))

    id: Mapped[int_pk]
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("group_settings.chat_id", ondelete="CASCADE"),
        nullable=False,
    )
    target_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    next_run_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[created_at]


class BotCommandModel(Base):
    __tablename__ = "bot_commands"
    __table_args__ = (
        UniqueConstraint("language_code", "command", name="uq_bot_commands_lang_command"),
        Index("ix_bot_commands_language", "language_code"),
        Index("ix_bot_commands_enabled", "enabled"),
    )

    id: Mapped[int_pk]
    language_code: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    command: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[created_at]

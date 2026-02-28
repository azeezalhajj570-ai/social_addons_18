from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    DynamicRuleModel,
    FilterModel,
    GroupMetaModel,
    GroupSettingsModel,
    LinkRouteModel,
    ParticipationGateModel,
    ScheduledMessageModel,
    WarningModel,
)

BOOL_SETTINGS = {
    "anti_links",
    "anti_bots",
    "hide_system",
    "warn_in_dm",
    "warn_in_group",
    "temp_ban_before_remove",
}
INT_SETTINGS = {"temp_ban_seconds"}


@dataclass(frozen=True)
class DynamicRule:
    id: int
    chat_id: int
    pattern: str
    enabled: bool


@dataclass(frozen=True)
class LinkRoute:
    chat_id: int
    keyword: str
    destination: str
    gate_group_id: int | None
    enabled: bool


@dataclass(frozen=True)
class ParticipationGate:
    chat_id: int
    gate_group_id: int
    gate_title: str
    join_url: str
    enabled: bool


@dataclass(frozen=True)
class GroupMeta:
    chat_id: int
    rules_text: str | None
    welcome_message: str | None
    goodbye_message: str | None
    antispam_limit: int | None
    antispam_window: int | None
    antiflood_limit: int | None
    antiflood_window: int | None


@dataclass(frozen=True)
class SavedFilter:
    keyword: str
    text: str | None
    caption: str | None
    photo: str | None
    document: str | None
    sticker: str | None
    animation: str | None
    video: str | None
    voice: str | None
    audio: str | None


@dataclass(frozen=True)
class ScheduledMessage:
    id: int
    chat_id: int
    target_chat_id: int | None
    text: str
    interval_seconds: int
    next_run_at: datetime
    enabled: bool


async def ensure_group(session: AsyncSession, chat_id: int) -> None:
    stmt = insert(GroupSettingsModel).values(chat_id=chat_id).on_conflict_do_nothing(index_elements=["chat_id"])
    await session.execute(stmt)
    await session.commit()


async def list_groups(session: AsyncSession) -> list[int]:
    result = await session.execute(select(GroupSettingsModel.chat_id).order_by(GroupSettingsModel.chat_id.asc()))
    return [int(chat_id) for chat_id in result.scalars().all()]


async def get_setting(session: AsyncSession, chat_id: int, key: str) -> bool:
    if key not in BOOL_SETTINGS:
        raise ValueError(f"Unknown boolean setting: {key}")
    await ensure_group(session, chat_id)
    result = await session.execute(select(getattr(GroupSettingsModel, key)).where(GroupSettingsModel.chat_id == chat_id))
    value = result.scalar_one()
    return bool(value)


async def get_int_setting(session: AsyncSession, chat_id: int, key: str, default: int = 0) -> int:
    if key not in INT_SETTINGS:
        raise ValueError(f"Unknown integer setting: {key}")
    await ensure_group(session, chat_id)
    result = await session.execute(select(getattr(GroupSettingsModel, key)).where(GroupSettingsModel.chat_id == chat_id))
    value = result.scalar_one()
    return int(value) if value is not None else default


async def set_int_setting(session: AsyncSession, chat_id: int, key: str, value: int) -> None:
    if key not in INT_SETTINGS:
        raise ValueError(f"Unknown integer setting: {key}")
    await ensure_group(session, chat_id)
    await session.execute(
        update(GroupSettingsModel).where(GroupSettingsModel.chat_id == chat_id).values({key: int(value)}),
    )
    await session.commit()


async def toggle_setting(session: AsyncSession, chat_id: int, key: str) -> bool:
    if key not in BOOL_SETTINGS:
        raise ValueError(f"Unknown boolean setting: {key}")
    current = await get_setting(session, chat_id, key)
    new_value = not current
    await session.execute(
        update(GroupSettingsModel).where(GroupSettingsModel.chat_id == chat_id).values({key: new_value}),
    )
    await session.commit()
    return new_value


async def add_warn(session: AsyncSession, chat_id: int, user_id: int) -> int:
    await ensure_group(session, chat_id)
    stmt = (
        insert(WarningModel)
        .values(chat_id=chat_id, user_id=user_id, warns=1)
        .on_conflict_do_update(
            constraint="uq_warnings_chat_user",
            set_={"warns": WarningModel.warns + 1},
        )
        .returning(WarningModel.warns)
    )
    result = await session.execute(stmt)
    await session.commit()
    return int(result.scalar_one())


async def get_warns(session: AsyncSession, chat_id: int, user_id: int) -> int:
    result = await session.execute(
        select(WarningModel.warns).where(WarningModel.chat_id == chat_id, WarningModel.user_id == user_id),
    )
    warns = result.scalar_one_or_none()
    return int(warns or 0)


async def set_warns(session: AsyncSession, chat_id: int, user_id: int, warns: int) -> None:
    await ensure_group(session, chat_id)
    stmt = (
        insert(WarningModel)
        .values(chat_id=chat_id, user_id=user_id, warns=max(0, warns))
        .on_conflict_do_update(
            constraint="uq_warnings_chat_user",
            set_={"warns": max(0, warns)},
        )
    )
    await session.execute(stmt)
    await session.commit()


async def reset_warns(session: AsyncSession, chat_id: int, user_id: int) -> None:
    await session.execute(delete(WarningModel).where(WarningModel.chat_id == chat_id, WarningModel.user_id == user_id))
    await session.commit()


async def add_dynamic_rule(session: AsyncSession, chat_id: int, pattern: str) -> int:
    await ensure_group(session, chat_id)
    model = DynamicRuleModel(chat_id=chat_id, pattern=pattern, enabled=True)
    session.add(model)
    await session.commit()
    return int(model.id)


async def list_dynamic_rules(session: AsyncSession, chat_id: int) -> list[DynamicRule]:
    result = await session.execute(
        select(DynamicRuleModel).where(DynamicRuleModel.chat_id == chat_id).order_by(DynamicRuleModel.id.asc()),
    )
    rows = result.scalars().all()
    return [DynamicRule(id=row.id, chat_id=row.chat_id, pattern=row.pattern, enabled=row.enabled) for row in rows]


async def delete_dynamic_rule(session: AsyncSession, chat_id: int, rule_id: int) -> bool:
    result = await session.execute(
        delete(DynamicRuleModel).where(DynamicRuleModel.chat_id == chat_id, DynamicRuleModel.id == rule_id),
    )
    await session.commit()
    return bool(result.rowcount)


async def upsert_link_route(
    session: AsyncSession,
    chat_id: int,
    keyword: str,
    destination: str,
    gate_group_id: int | None = None,
) -> None:
    await ensure_group(session, chat_id)
    stmt = (
        insert(LinkRouteModel)
        .values(
            chat_id=chat_id,
            keyword=keyword.lower().strip(),
            destination=destination.strip(),
            gate_group_id=gate_group_id,
            enabled=True,
        )
        .on_conflict_do_update(
            constraint="uq_link_routes_chat_keyword",
            set_={
                "destination": destination.strip(),
                "gate_group_id": gate_group_id,
                "enabled": True,
            },
        )
    )
    await session.execute(stmt)
    await session.commit()


async def list_link_routes(session: AsyncSession, chat_id: int) -> list[LinkRoute]:
    result = await session.execute(
        select(LinkRouteModel).where(LinkRouteModel.chat_id == chat_id).order_by(LinkRouteModel.keyword.asc()),
    )
    rows = result.scalars().all()
    return [
        LinkRoute(
            chat_id=row.chat_id,
            keyword=row.keyword,
            destination=row.destination,
            gate_group_id=row.gate_group_id,
            enabled=row.enabled,
        )
        for row in rows
    ]


async def delete_link_route(session: AsyncSession, chat_id: int, keyword: str) -> bool:
    result = await session.execute(
        delete(LinkRouteModel).where(
            LinkRouteModel.chat_id == chat_id,
            LinkRouteModel.keyword == keyword.lower().strip(),
        ),
    )
    await session.commit()
    return bool(result.rowcount)


async def upsert_participation_gate(
    session: AsyncSession,
    chat_id: int,
    gate_group_id: int,
    gate_title: str,
    join_url: str,
) -> None:
    await ensure_group(session, chat_id)
    stmt = (
        insert(ParticipationGateModel)
        .values(
            chat_id=chat_id,
            gate_group_id=gate_group_id,
            gate_title=gate_title,
            join_url=join_url,
            enabled=True,
        )
        .on_conflict_do_update(
            constraint="uq_participation_gates_chat_gate",
            set_={
                "gate_title": gate_title,
                "join_url": join_url,
                "enabled": True,
            },
        )
    )
    await session.execute(stmt)
    await session.commit()


async def list_participation_gates(session: AsyncSession, chat_id: int) -> list[ParticipationGate]:
    result = await session.execute(
        select(ParticipationGateModel)
        .where(ParticipationGateModel.chat_id == chat_id)
        .order_by(ParticipationGateModel.gate_title.asc()),
    )
    rows = result.scalars().all()
    return [
        ParticipationGate(
            chat_id=row.chat_id,
            gate_group_id=row.gate_group_id,
            gate_title=row.gate_title,
            join_url=row.join_url,
            enabled=row.enabled,
        )
        for row in rows
    ]


async def delete_participation_gate(session: AsyncSession, chat_id: int, gate_group_id: int) -> bool:
    result = await session.execute(
        delete(ParticipationGateModel).where(
            ParticipationGateModel.chat_id == chat_id,
            ParticipationGateModel.gate_group_id == gate_group_id,
        ),
    )
    await session.commit()
    return bool(result.rowcount)


async def ensure_group_meta(session: AsyncSession, chat_id: int) -> None:
    await ensure_group(session, chat_id)
    stmt = insert(GroupMetaModel).values(chat_id=chat_id).on_conflict_do_nothing(index_elements=["chat_id"])
    await session.execute(stmt)
    await session.commit()


async def get_group_meta(session: AsyncSession, chat_id: int) -> GroupMeta:
    await ensure_group_meta(session, chat_id)
    result = await session.execute(select(GroupMetaModel).where(GroupMetaModel.chat_id == chat_id))
    row = result.scalar_one()
    return GroupMeta(
        chat_id=row.chat_id,
        rules_text=row.rules_text,
        welcome_message=row.welcome_message,
        goodbye_message=row.goodbye_message,
        antispam_limit=row.antispam_limit,
        antispam_window=row.antispam_window,
        antiflood_limit=row.antiflood_limit,
        antiflood_window=row.antiflood_window,
    )


async def set_rules_text(session: AsyncSession, chat_id: int, rules_text: str) -> None:
    await ensure_group_meta(session, chat_id)
    await session.execute(update(GroupMetaModel).where(GroupMetaModel.chat_id == chat_id).values(rules_text=rules_text))
    await session.commit()


async def set_welcome_message(session: AsyncSession, chat_id: int, welcome_message: str) -> None:
    await ensure_group_meta(session, chat_id)
    await session.execute(
        update(GroupMetaModel).where(GroupMetaModel.chat_id == chat_id).values(welcome_message=welcome_message),
    )
    await session.commit()


async def set_goodbye_message(session: AsyncSession, chat_id: int, goodbye_message: str) -> None:
    await ensure_group_meta(session, chat_id)
    await session.execute(
        update(GroupMetaModel).where(GroupMetaModel.chat_id == chat_id).values(goodbye_message=goodbye_message),
    )
    await session.commit()


async def set_antispam(session: AsyncSession, chat_id: int, limit: int, window: int) -> None:
    await ensure_group_meta(session, chat_id)
    await session.execute(
        update(GroupMetaModel)
        .where(GroupMetaModel.chat_id == chat_id)
        .values(antispam_limit=max(1, limit), antispam_window=max(1, window)),
    )
    await session.commit()


async def set_antiflood(session: AsyncSession, chat_id: int, limit: int, window: int) -> None:
    await ensure_group_meta(session, chat_id)
    await session.execute(
        update(GroupMetaModel)
        .where(GroupMetaModel.chat_id == chat_id)
        .values(antiflood_limit=max(1, limit), antiflood_window=max(1, window)),
    )
    await session.commit()


async def upsert_filter(
    session: AsyncSession,
    chat_id: int,
    keyword: str,
    *,
    text: str | None,
    caption: str | None,
    photo: str | None,
    document: str | None,
    sticker: str | None,
    animation: str | None,
    video: str | None,
    voice: str | None,
    audio: str | None,
) -> None:
    await ensure_group(session, chat_id)
    stmt = (
        insert(FilterModel)
        .values(
            chat_id=chat_id,
            keyword=keyword.lower().strip(),
            text=text,
            caption=caption,
            photo=photo,
            document=document,
            sticker=sticker,
            animation=animation,
            video=video,
            voice=voice,
            audio=audio,
        )
        .on_conflict_do_update(
            constraint="uq_filters_chat_keyword",
            set_={
                "text": text,
                "caption": caption,
                "photo": photo,
                "document": document,
                "sticker": sticker,
                "animation": animation,
                "video": video,
                "voice": voice,
                "audio": audio,
            },
        )
    )
    await session.execute(stmt)
    await session.commit()


async def delete_filter(session: AsyncSession, chat_id: int, keyword: str) -> bool:
    result = await session.execute(
        delete(FilterModel).where(FilterModel.chat_id == chat_id, FilterModel.keyword == keyword.lower().strip()),
    )
    await session.commit()
    return bool(result.rowcount)


async def list_filters(session: AsyncSession, chat_id: int) -> list[SavedFilter]:
    result = await session.execute(select(FilterModel).where(FilterModel.chat_id == chat_id).order_by(FilterModel.keyword.asc()))
    rows = result.scalars().all()
    return [
        SavedFilter(
            keyword=row.keyword,
            text=row.text,
            caption=row.caption,
            photo=row.photo,
            document=row.document,
            sticker=row.sticker,
            animation=row.animation,
            video=row.video,
            voice=row.voice,
            audio=row.audio,
        )
        for row in rows
    ]


async def add_scheduled_message(
    session: AsyncSession,
    chat_id: int,
    target_chat_id: int | None,
    text: str,
    interval_minutes: int,
) -> int:
    await ensure_group(session, chat_id)
    now = datetime.now(timezone.utc)
    model = ScheduledMessageModel(
        chat_id=chat_id,
        target_chat_id=target_chat_id,
        text=text.strip(),
        interval_seconds=max(60, interval_minutes * 60),
        next_run_at=now + timedelta(minutes=max(1, interval_minutes)),
        enabled=True,
    )
    session.add(model)
    await session.commit()
    return int(model.id)


async def list_scheduled_messages(session: AsyncSession, chat_id: int) -> list[ScheduledMessage]:
    result = await session.execute(
        select(ScheduledMessageModel)
        .where(ScheduledMessageModel.chat_id == chat_id)
        .order_by(ScheduledMessageModel.id.asc()),
    )
    rows = result.scalars().all()
    return [
        ScheduledMessage(
            id=row.id,
            chat_id=row.chat_id,
            target_chat_id=row.target_chat_id,
            text=row.text,
            interval_seconds=row.interval_seconds,
            next_run_at=row.next_run_at,
            enabled=row.enabled,
        )
        for row in rows
    ]


async def delete_scheduled_message(session: AsyncSession, chat_id: int, schedule_id: int) -> bool:
    result = await session.execute(
        delete(ScheduledMessageModel).where(
            ScheduledMessageModel.chat_id == chat_id,
            ScheduledMessageModel.id == schedule_id,
        ),
    )
    await session.commit()
    return bool(result.rowcount)


async def toggle_scheduled_message(session: AsyncSession, chat_id: int, schedule_id: int) -> bool | None:
    result = await session.execute(
        select(ScheduledMessageModel).where(
            ScheduledMessageModel.chat_id == chat_id,
            ScheduledMessageModel.id == schedule_id,
        ),
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.enabled = not row.enabled
    await session.commit()
    return bool(row.enabled)


async def get_due_scheduled_messages(session: AsyncSession, now: datetime) -> list[ScheduledMessageModel]:
    result = await session.execute(
        select(ScheduledMessageModel).where(
            ScheduledMessageModel.enabled.is_(True),
            ScheduledMessageModel.next_run_at <= now,
        ),
    )
    return list(result.scalars().all())


async def mark_scheduled_message_sent(session: AsyncSession, schedule_id: int, next_run_at: datetime) -> None:
    await session.execute(
        update(ScheduledMessageModel).where(ScheduledMessageModel.id == schedule_id).values(next_run_at=next_run_at),
    )
    await session.commit()

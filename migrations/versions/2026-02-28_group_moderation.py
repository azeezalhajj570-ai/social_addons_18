"""group moderation tables

Revision ID: 7f3d19ab2d80
Revises: e4b7e8c165c1
Create Date: 2026-02-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f3d19ab2d80"
down_revision: Union[str, None] = "e4b7e8c165c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "group_settings",
        sa.Column("chat_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("TIMEZONE('utc', now())"), nullable=False),
        sa.Column("anti_links", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("anti_bots", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("hide_system", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("warn_in_dm", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("warn_in_group", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("temp_ban_before_remove", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("temp_ban_seconds", sa.Integer(), server_default="600", nullable=False),
        sa.PrimaryKeyConstraint("chat_id"),
        sa.UniqueConstraint("chat_id"),
    )

    op.create_table(
        "warnings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("warns", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["group_settings.chat_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "user_id", name="uq_warnings_chat_user"),
    )
    op.create_index("ix_warnings_chat_user", "warnings", ["chat_id", "user_id"], unique=False)

    op.create_table(
        "dynamic_remove_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("TIMEZONE('utc', now())"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["group_settings.chat_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dynamic_rules_chat", "dynamic_remove_rules", ["chat_id"], unique=False)

    op.create_table(
        "link_routes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("gate_group_id", sa.BigInteger(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("TIMEZONE('utc', now())"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["group_settings.chat_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "keyword", name="uq_link_routes_chat_keyword"),
    )
    op.create_index("ix_link_routes_chat", "link_routes", ["chat_id"], unique=False)

    op.create_table(
        "participation_gates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("gate_group_id", sa.BigInteger(), nullable=False),
        sa.Column("gate_title", sa.String(length=255), nullable=False),
        sa.Column("join_url", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("TIMEZONE('utc', now())"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["group_settings.chat_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "gate_group_id", name="uq_participation_gates_chat_gate"),
    )
    op.create_index("ix_participation_gates_chat", "participation_gates", ["chat_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_participation_gates_chat", table_name="participation_gates")
    op.drop_table("participation_gates")
    op.drop_index("ix_link_routes_chat", table_name="link_routes")
    op.drop_table("link_routes")
    op.drop_index("ix_dynamic_rules_chat", table_name="dynamic_remove_rules")
    op.drop_table("dynamic_remove_rules")
    op.drop_index("ix_warnings_chat_user", table_name="warnings")
    op.drop_table("warnings")
    op.drop_table("group_settings")

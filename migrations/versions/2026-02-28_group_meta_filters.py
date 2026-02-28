"""group meta and filters

Revision ID: b6b21640f01f
Revises: 7f3d19ab2d80
Create Date: 2026-02-28 00:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6b21640f01f"
down_revision: Union[str, None] = "7f3d19ab2d80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "group_meta",
        sa.Column("chat_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("TIMEZONE('utc', now())"), nullable=False),
        sa.Column("rules_text", sa.Text(), nullable=True),
        sa.Column("welcome_message", sa.Text(), nullable=True),
        sa.Column("goodbye_message", sa.Text(), nullable=True),
        sa.Column("antispam_limit", sa.Integer(), nullable=True),
        sa.Column("antispam_window", sa.Integer(), nullable=True),
        sa.Column("antiflood_limit", sa.Integer(), nullable=True),
        sa.Column("antiflood_window", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["chat_id"], ["group_settings.chat_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id"),
        sa.UniqueConstraint("chat_id"),
    )

    op.create_table(
        "filters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("photo", sa.String(length=255), nullable=True),
        sa.Column("document", sa.String(length=255), nullable=True),
        sa.Column("sticker", sa.String(length=255), nullable=True),
        sa.Column("animation", sa.String(length=255), nullable=True),
        sa.Column("video", sa.String(length=255), nullable=True),
        sa.Column("voice", sa.String(length=255), nullable=True),
        sa.Column("audio", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("TIMEZONE('utc', now())"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["group_settings.chat_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "keyword", name="uq_filters_chat_keyword"),
    )
    op.create_index("ix_filters_chat", "filters", ["chat_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_filters_chat", table_name="filters")
    op.drop_table("filters")
    op.drop_table("group_meta")

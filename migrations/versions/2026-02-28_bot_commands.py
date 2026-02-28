"""bot commands table

Revision ID: c7a1e2d3f4a5
Revises: f1a2b3c4d5e6
Create Date: 2026-02-28 02:05:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7a1e2d3f4a5"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_commands",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("language_code", sa.String(length=8), nullable=False),
        sa.Column("command", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=256), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="100", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("TIMEZONE('utc', now())"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("language_code", "command", name="uq_bot_commands_lang_command"),
    )
    op.create_index("ix_bot_commands_language", "bot_commands", ["language_code"], unique=False)
    op.create_index("ix_bot_commands_enabled", "bot_commands", ["enabled"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bot_commands_enabled", table_name="bot_commands")
    op.drop_index("ix_bot_commands_language", table_name="bot_commands")
    op.drop_table("bot_commands")

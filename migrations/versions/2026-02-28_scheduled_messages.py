"""scheduled messages

Revision ID: 8df4a3f9be21
Revises: b6b21640f01f
Create Date: 2026-02-28 01:25:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8df4a3f9be21"
down_revision: Union[str, None] = "b6b21640f01f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("TIMEZONE('utc', now())"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["group_settings.chat_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduled_messages_chat", "scheduled_messages", ["chat_id"], unique=False)
    op.create_index("ix_scheduled_messages_next_run_at", "scheduled_messages", ["next_run_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scheduled_messages_next_run_at", table_name="scheduled_messages")
    op.drop_index("ix_scheduled_messages_chat", table_name="scheduled_messages")
    op.drop_table("scheduled_messages")

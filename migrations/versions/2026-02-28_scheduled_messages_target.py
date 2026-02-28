"""scheduled messages target

Revision ID: f1a2b3c4d5e6
Revises: 8df4a3f9be21
Create Date: 2026-02-28 01:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "8df4a3f9be21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scheduled_messages", sa.Column("target_chat_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("scheduled_messages", "target_chat_id")

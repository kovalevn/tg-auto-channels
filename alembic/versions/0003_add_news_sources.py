"""add news source lists to channels

Revision ID: 0003
Revises: 0002
Create Date: 2024-10-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("news_source_lists", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("channels", "news_source_lists")

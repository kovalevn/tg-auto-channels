"""initial tables

Revision ID: 0001
Revises: 
Create Date: 2024-05-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("internal_name", sa.String(length=255), nullable=False),
        sa.Column("telegram_channel_id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=True),
        sa.Column("posting_frequency_per_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("posting_window_start", sa.Time(timezone=True), nullable=True),
        sa.Column("posting_window_end", sa.Time(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("auto_post_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("content_strategy", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("internal_name"),
    )
    op.create_table(
        "posts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Enum("queued", "sent", "failed", name="post_status"), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("posts")
    op.drop_table("channels")
    op.execute("DROP TYPE IF EXISTS post_status")

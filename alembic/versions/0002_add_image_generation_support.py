"""add image generation support

Revision ID: 0002
Revises: 0001
Create Date: 2024-08-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("generate_images", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("posts", sa.Column("image_url", sa.Text(), nullable=True))
    op.alter_column("channels", "generate_images", server_default=None)


def downgrade() -> None:
    op.drop_column("posts", "image_url")
    op.drop_column("channels", "generate_images")

"""Add media ownership, private shows, and season details.

Revision ID: 7b28d1a4c6f0
Revises: 1d596fd7a30b
Create Date: 2026-10-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7b28d1a4c6f0"
down_revision: Union[str, Sequence[str], None] = "1d596fd7a30b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shows",
        sa.Column(
            "is_private",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    for table_name in ("shows", "seasons", "episodes"):
        op.add_column(
            table_name,
            sa.Column("created_by_id", sa.UUID(), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table_name}_created_by_id_users",
            table_name,
            "users",
            ["created_by_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.add_column(
        "seasons",
        sa.Column(
            "name",
            sa.String(length=255),
            server_default="Season",
            nullable=False,
        ),
    )
    op.add_column(
        "seasons",
        sa.Column(
            "description",
            sa.Text(),
            server_default="No description provided",
            nullable=False,
        ),
    )
    op.add_column(
        "seasons",
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
    )
    op.execute("UPDATE seasons SET name = 'Season ' || season_number::text")
    op.create_unique_constraint(
        "uq_seasons_show_season_number",
        "seasons",
        ["show_id", "season_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_seasons_show_season_number",
        "seasons",
        type_="unique",
    )
    op.drop_column("seasons", "thumbnail_url")
    op.drop_column("seasons", "description")
    op.drop_column("seasons", "name")
    for table_name in ("episodes", "seasons", "shows"):
        op.drop_constraint(
            f"fk_{table_name}_created_by_id_users",
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, "created_by_id")
    op.drop_column("shows", "is_private")

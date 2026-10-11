"""added genres to the show table

Revision ID: a2aa790afbed
Revises: 1103bd0e0458
Create Date: 2026-10-10 20:01:23.487984

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2aa790afbed'
down_revision: Union[str, Sequence[str], None] = '1103bd0e0458'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Explicitly create the enum type in PostgreSQL first
    genre_enum = sa.Enum('anime', 'drama', 'action', 'comedy', 'sci-fi', name='genre_enum')
    genre_enum.create(op.get_bind(), checkfirst=True)
    
    # 2. Now add the column using that enum
    op.add_column('shows', sa.Column('genre', genre_enum, server_default='drama', nullable=False))


def downgrade() -> None:
    # 1. Drop the column first
    op.drop_column('shows', 'genre')
    
    # 2. Then drop the enum type from the database
    genre_enum = sa.Enum('anime', 'drama', 'action', 'comedy', 'sci-fi', name='genre_enum')
    genre_enum.drop(op.get_bind(), checkfirst=True)

"""add activity and message columns back to activity_log

Revision ID: 4f5a76cc1953
Revises: 42ebb0d26634
Create Date: 2025-10-28 10:36:26.850251

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f5a76cc1953'
down_revision: Union[str, Sequence[str], None] = '42ebb0d26634'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('activity_log', sa.Column('activity', sa.String(), nullable=True))
    op.add_column('activity_log', sa.Column('message', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('activity_log', 'message')
    op.drop_column('activity_log', 'activity')

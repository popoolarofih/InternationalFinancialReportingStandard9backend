"""alter pd_file id to serial

Revision ID: 333630fc4072
Revises: e0913da6fe43
Create Date: 2025-10-03 21:07:02.992039

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '333630fc4072'
down_revision: Union[str, Sequence[str], None] = 'e0913da6fe43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create sequence for pd_file id
    op.execute("CREATE SEQUENCE IF NOT EXISTS pd_file_id_seq")
    # Set default for id column
    op.execute("ALTER TABLE pd_file ALTER COLUMN id SET DEFAULT nextval('pd_file_id_seq')")
    # Update existing rows if any
    op.execute("SELECT setval('pd_file_id_seq', GREATEST((SELECT COALESCE(MAX(id), 0) FROM pd_file), 1))")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove default from id column
    op.execute("ALTER TABLE pd_file ALTER COLUMN id DROP DEFAULT")
    # Drop the sequence
    op.execute("DROP SEQUENCE IF EXISTS pd_file_id_seq")

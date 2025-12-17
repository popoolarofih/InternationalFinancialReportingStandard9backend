"""alter fli_file id to serial

Revision ID: e0913da6fe43
Revises: 7a076475db3f
Create Date: 2025-10-03 13:30:54.074162

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0913da6fe43'
down_revision: Union[str, Sequence[str], None] = '7a076475db3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create sequence for fli_file id
    op.execute("CREATE SEQUENCE IF NOT EXISTS fli_file_id_seq")
    # Set default for id column
    op.execute("ALTER TABLE fli_file ALTER COLUMN id SET DEFAULT nextval('fli_file_id_seq')")
    # Update existing rows if any
    op.execute("SELECT setval('fli_file_id_seq', GREATEST((SELECT COALESCE(MAX(id), 0) FROM fli_file), 1))")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove default from id column
    op.execute("ALTER TABLE fli_file ALTER COLUMN id DROP DEFAULT")
    # Drop the sequence
    op.execute("DROP SEQUENCE IF EXISTS fli_file_id_seq")

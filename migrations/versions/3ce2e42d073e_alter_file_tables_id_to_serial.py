"""alter_file_tables_id_to_serial

Revision ID: 3ce2e42d073e
Revises: 333630fc4072
Create Date: 2025-10-03 22:46:16.631907

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ce2e42d073e'
down_revision: Union[str, Sequence[str], None] = '333630fc4072'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create sequences and alter id columns for remaining file tables
    tables = ['lgd_file', 'ead_file', 'ecl_file', 'ccf_file', 'staging_file']

    for table in tables:
        seq_name = f"{table}_id_seq"
        # Create sequence
        op.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}")
        # Set default for id column
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT nextval('{seq_name}')")
        # Update existing rows if any
        op.execute(f"SELECT setval('{seq_name}', GREATEST((SELECT COALESCE(MAX(id), 0) FROM {table}), 1))")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove defaults and drop sequences for file tables
    tables = ['lgd_file', 'ead_file', 'ecl_file', 'ccf_file', 'staging_file']

    for table in tables:
        seq_name = f"{table}_id_seq"
        # Remove default from id column
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id DROP DEFAULT")
        # Drop the sequence
        op.execute(f"DROP SEQUENCE IF EXISTS {seq_name}")

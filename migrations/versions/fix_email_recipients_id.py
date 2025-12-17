"""Fix email_recipients id auto increment

Revision ID: fix_email_recipients_id
Revises: a350357de0c8
Create Date: 2025-10-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'fix_email_recipients_id'
down_revision: Union[str, Sequence[str], None] = 'a350357de0c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create sequence if not exists
    op.execute("CREATE SEQUENCE IF NOT EXISTS email_recipients_id_seq")
    # Set the sequence owned by the column
    op.execute("ALTER SEQUENCE email_recipients_id_seq OWNED BY email_recipients.id")
    # Set default
    op.execute("ALTER TABLE email_recipients ALTER COLUMN id SET DEFAULT nextval('email_recipients_id_seq')")
    # Update any existing rows with null id
    op.execute("UPDATE email_recipients SET id = nextval('email_recipients_id_seq') WHERE id IS NULL")
    # Make sure the sequence is at the right place
    op.execute("SELECT setval('email_recipients_id_seq', (SELECT GREATEST(COALESCE(MAX(id), 0), 1) FROM email_recipients))")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove default
    op.execute("ALTER TABLE email_recipients ALTER COLUMN id DROP DEFAULT")
    # Drop sequence
    op.execute("DROP SEQUENCE IF EXISTS email_recipients_id_seq")

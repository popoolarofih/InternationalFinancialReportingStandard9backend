"""fix_model_execution_log_id_auto_increment

Revision ID: 7a076475db3f
Revises: df2433381319
Create Date: 2025-10-03 11:45:31.770067

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a076475db3f'
down_revision: Union[str, Sequence[str], None] = 'df2433381319'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create sequence for model_execution_log id
    op.execute("CREATE SEQUENCE IF NOT EXISTS model_execution_log_id_seq")
    # Set default for id column
    op.execute("ALTER TABLE model_execution_log ALTER COLUMN id SET DEFAULT nextval('model_execution_log_id_seq')")
    # Update existing rows with null id
    op.execute("UPDATE model_execution_log SET id = nextval('model_execution_log_id_seq') WHERE id IS NULL")
    # Make id NOT NULL
    op.execute("ALTER TABLE model_execution_log ALTER COLUMN id SET NOT NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE model_execution_log ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS model_execution_log_id_seq")

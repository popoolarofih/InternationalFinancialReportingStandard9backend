"""initial schema

Revision ID: df2433381319
Revises:
Create Date: 2025-09-27 08:50:05.884696
"""
from typing import Sequence, Union
import sqlmodel
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "df2433381319"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def enum_exists(enum_name: str) -> bool:
    """Check if an enum type exists in the PostgreSQL database."""
    result = op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = :name)"),
        {"name": enum_name}
    )
    return result.scalar()


def upgrade() -> None:
    """Upgrade schema."""

    # 1️⃣ Create ENUMs with explicit existence check
    if not enum_exists("roletypeenum"):
        op.execute(
            "CREATE TYPE roletypeenum AS ENUM ('USER', 'SUPER_USER', 'ADMIN', 'SUPER_ADMIN')"
        )

    if not enum_exists("modelexecutionstatus"):
        op.execute(
            "CREATE TYPE modelexecutionstatus AS ENUM ('COMPLETED', 'FAILED', 'RUNNING', 'CANCELLED', 'REJECTED', 'PENDING_APPROVAL')"
        )

    if not enum_exists("executionmodeltype"):
        op.execute(
            "CREATE TYPE executionmodeltype AS ENUM ('PD', 'EAD', 'CCF', 'ECL', 'LGD', 'FLI', 'STAGING')"
        )

    # Update existing role values to match enum
    op.execute("UPDATE users SET role = UPPER(role)")

    # 2️⃣ Alter users table using raw SQL
    op.execute("ALTER TABLE users ALTER COLUMN email SET NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN full_name SET NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE roletypeenum USING role::roletypeenum")
    op.execute("ALTER TABLE users ALTER COLUMN status SET NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN is_temporary_password SET NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN hashed_password SET NOT NULL")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.execute("ALTER TABLE users DROP COLUMN department")

    # 3️⃣ Create independent tables
    op.execute("""
        CREATE TABLE email_recipients (
            id SERIAL PRIMARY KEY,
            email VARCHAR NOT NULL,
            name VARCHAR NOT NULL
        )
    """)
    op.create_index(op.f("ix_email_recipients_id"), "email_recipients", ["id"], unique=False)

    op.execute("""
        CREATE TABLE model_execution_log (
            id SERIAL PRIMARY KEY,
            data_name VARCHAR NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            report_exported BOOLEAN NOT NULL,
            executed_model_type executionmodeltype NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            execution_status modelexecutionstatus NOT NULL,
            celery_task_id VARCHAR,
            celery_task_name VARCHAR
        )
    """)

    # 4️⃣ Alter activity_log
    op.execute("ALTER TABLE activity_log ADD COLUMN execution_model_id INTEGER")
    op.execute("ALTER TABLE activity_log ALTER COLUMN timestamp SET NOT NULL")
    op.drop_index(op.f("ix_activity_log_id"), table_name="activity_log")
    op.drop_constraint(op.f("activity_log_user_id_fkey"), "activity_log", type_="foreignkey")
    op.execute("ALTER TABLE activity_log ADD CONSTRAINT activity_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE activity_log ADD CONSTRAINT activity_log_execution_model_id_fkey FOREIGN KEY (execution_model_id) REFERENCES model_execution_log(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE activity_log DROP COLUMN activity")
    op.execute("ALTER TABLE activity_log DROP COLUMN message")

    # 5️⃣ Create the rest of the tables
    op.execute("""
        CREATE TABLE ccf_file (
            id SERIAL PRIMARY KEY,
            data_name VARCHAR NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            data JSON,
            minio_file_key VARCHAR,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            execution_model_id INTEGER REFERENCES model_execution_log(id) ON DELETE SET NULL
        )
    """)

    op.execute("""
        CREATE TABLE dashboard_summary (
            id SERIAL PRIMARY KEY,
            total_customers INTEGER,
            total_ead FLOAT,
            total_ecl FLOAT,
            non_performing_loan_percentage FLOAT,
            performing_loan_percentage FLOAT,
            sector_by_ecl_df JSON,
            top_obligors JSON,
            timestamp TIMESTAMP NOT NULL,
            ecl_summary JSON,
            execution_model_id INTEGER REFERENCES model_execution_log(id) ON DELETE SET NULL
        )
    """)

    op.execute("""
        CREATE TABLE ead_file (
            id SERIAL PRIMARY KEY,
            account_number VARCHAR NOT NULL,
            account_name VARCHAR NOT NULL,
            date_of_origination TIMESTAMP NOT NULL,
            date_of_maturity TIMESTAMP NOT NULL,
            loan_type VARCHAR NOT NULL,
            repayment_type VARCHAR NOT NULL,
            eir FLOAT NOT NULL,
            payment_eir FLOAT NOT NULL,
            monthly_eir FLOAT NOT NULL,
            maturity_check VARCHAR NOT NULL,
            total_ead FLOAT NOT NULL,
            month_year_data JSON,
            minio_file_key VARCHAR,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            execution_model_id INTEGER REFERENCES model_execution_log(id) ON DELETE SET NULL
        )
    """)

    op.execute("""
        CREATE TABLE ecl_file (
            id SERIAL PRIMARY KEY,
            account_number VARCHAR NOT NULL,
            account_name VARCHAR NOT NULL,
            loan_balance FLOAT NOT NULL,
            stage VARCHAR NOT NULL,
            final_ecl FLOAT NOT NULL,
            data JSON,
            minio_file_key VARCHAR,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            execution_model_id INTEGER REFERENCES model_execution_log(id) ON DELETE SET NULL
        )
    """)

    op.execute("""
        CREATE TABLE ecl_model_report_summary (
            id SERIAL PRIMARY KEY,
            total_ecl FLOAT,
            ecl_stage1 FLOAT,
            ecl_stage2 FLOAT,
            ecl_stage3 FLOAT,
            execution_log_id_model INTEGER REFERENCES model_execution_log(id)
        )
    """)
    op.create_index(op.f("ix_ecl_model_report_summary_id"), "ecl_model_report_summary", ["id"], unique=False)

    op.execute("""
        CREATE TABLE fli_file (
            id SERIAL PRIMARY KEY,
            overall_verdict VARCHAR NOT NULL,
            message VARCHAR NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            fli_table JSON,
            forecast_scalars JSON,
            summary_scenario_weights JSON,
            fli_scalar_weight JSON,
            fli_scalar_weights_per_qrt JSON,
            minio_file_key VARCHAR,
            execution_model_id INTEGER REFERENCES model_execution_log(id) ON DELETE SET NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
        )
    """)

    op.execute("""
        CREATE TABLE lgd_file (
            id SERIAL PRIMARY KEY,
            segments VARCHAR NOT NULL,
            final_lgd FLOAT NOT NULL,
            data JSON,
            minio_file_key VARCHAR,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            execution_model_id INTEGER REFERENCES model_execution_log(id) ON DELETE SET NULL
        )
    """)

    op.execute("""
        CREATE TABLE pd_file (
            id SERIAL PRIMARY KEY,
            segments VARCHAR NOT NULL,
            reporting_date VARCHAR,
            data_type VARCHAR NOT NULL,
            data JSON,
            minio_file_key VARCHAR,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            execution_model_id INTEGER REFERENCES model_execution_log(id) ON DELETE SET NULL
        )
    """)

    op.execute("""
        CREATE TABLE staging_file (
            id SERIAL PRIMARY KEY,
            account_number VARCHAR NOT NULL,
            account_name VARCHAR NOT NULL,
            performance_status VARCHAR NOT NULL,
            dpd FLOAT NOT NULL,
            final_stage FLOAT NOT NULL,
            data JSON,
            minio_file_key VARCHAR,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            execution_model_id INTEGER REFERENCES model_execution_log(id) ON DELETE SET NULL
        )
    """)


def downgrade() -> None:
    """Downgrade schema."""

    # Drop dependent tables first
    op.execute("DROP TABLE IF EXISTS staging_file")
    op.execute("DROP TABLE IF EXISTS pd_file")
    op.execute("DROP TABLE IF EXISTS lgd_file")
    op.execute("DROP TABLE IF EXISTS fli_file")
    op.execute("DROP INDEX IF EXISTS ix_ecl_model_report_summary_id")
    op.execute("DROP TABLE IF EXISTS ecl_model_report_summary")
    op.execute("DROP TABLE IF EXISTS ecl_file")
    op.execute("DROP TABLE IF EXISTS ead_file")
    op.execute("DROP TABLE IF EXISTS dashboard_summary")
    op.execute("DROP TABLE IF EXISTS ccf_file")
    op.execute("DROP TABLE IF EXISTS model_execution_log")
    op.execute("DROP INDEX IF EXISTS ix_email_recipients_id")
    op.execute("DROP TABLE IF EXISTS email_recipients")

    # Restore users table
    op.execute("ALTER TABLE users ADD COLUMN department VARCHAR")
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.execute("ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN is_temporary_password DROP NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN status DROP NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR USING role::VARCHAR")
    op.execute("ALTER TABLE users ALTER COLUMN full_name DROP NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN email DROP NOT NULL")

    # Restore activity_log
    op.execute("ALTER TABLE activity_log ADD COLUMN message VARCHAR")
    op.execute("ALTER TABLE activity_log ADD COLUMN activity VARCHAR")
    op.drop_constraint(None, "activity_log", type_="foreignkey")
    op.drop_constraint(None, "activity_log", type_="foreignkey")
    op.execute("ALTER TABLE activity_log ADD CONSTRAINT activity_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id)")
    op.create_index(op.f("ix_activity_log_id"), "activity_log", ["id"], unique=False)
    op.execute("ALTER TABLE activity_log ALTER COLUMN timestamp DROP NOT NULL")
    op.execute("ALTER TABLE activity_log DROP COLUMN execution_model_id")

    # Drop enums last
    op.execute("DROP TYPE IF EXISTS roletypeenum")
    op.execute("DROP TYPE IF EXISTS modelexecutionstatus")
    op.execute("DROP TYPE IF EXISTS executionmodeltype")
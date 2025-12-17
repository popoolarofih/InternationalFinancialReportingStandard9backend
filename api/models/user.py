from datetime import datetime
from enum import StrEnum
from typing import List, Optional
from sqlmodel import (
    Field,
    Relationship,
    JSON,
    SQLModel,  # noqa: F401
    Column,
)

from api.schema.models_schema import (
    ActivityLogBase,
    DashboardSummarySchema,
    FLILog,
    ModelExecutionBase,
    CCFLog,
    StagingLog,
    EADLog,
    LGDLog,
    PDLog,
    ECLLog,
)
from api.schema.user import UserBase, EmailRecipientBase


class ModelExecutionStatus(StrEnum):
    COMPLETED = "Completed"
    FAILED = "Failed"
    RUNNING = "Running"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"
    PENDING_APPROVAL = "Pending_Approval"


class ExecutionModelType(StrEnum):
    PD = "pd"
    EAD = "ead"
    CCF = "ccf"
    ECL = "ecl"
    LGD = "lgd"
    FLI = "fli"
    STAGING = "staging"


class User(UserBase, table=True):
    __tablename__ = "users"

    hashed_password: str
    verification_code: Optional[str] = Field(default=None)
    temp_password_set_at: Optional[datetime] = Field(default=None)
    refresh_token: Optional[str] = Field(default=None)
    refresh_token_expires_at: Optional[datetime] = Field(default=None)
    pd_files: List["PDFile"] = Relationship(back_populates="user")
    ccf_files: List["CCFFile"] = Relationship(back_populates="user")
    staging_files: List["StagingFile"] = Relationship(back_populates="user")
    ead_files: List["EADFile"] = Relationship(back_populates="user")
    lgd_files: List["LGDFile"] = Relationship(back_populates="user")
    ecl_files: List["ECLFile"] = Relationship(back_populates="user")
    fli_files: List["FLIFile"] = Relationship(back_populates="user")
    model_execution_logs: List["ModelExecutionLog"] = Relationship(
        back_populates="user"
    )
    activities: List["ActivityLog"] = Relationship(back_populates="user")


class EmailRecipient(EmailRecipientBase, table=True):
    __tablename__ = "email_recipients"
    pass


class PDFile(SQLModel, table=True):
    __tablename__ = "pd_file"

    id: Optional[int] = Field(default=None, primary_key=True)
    segments: str
    data_type: str  # marginal, cumm, conditional, conditional_w_fli
    reporting_date: Optional[str] = Field(default=None, description="Reporting date in YYYY-MM-DD format")
    data: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    minio_file_key: Optional[str] = Field(default=None)  # MinIO file reference

    user_id: Optional[int] = Field(foreign_key="users.id", ondelete="SET NULL")
    execution_model_id: Optional[int] = Field(
        foreign_key="model_execution_log.id", ondelete="SET NULL"
    )

    user: User = Relationship(back_populates="pd_files")
    model_execution_log: "ModelExecutionLog" = Relationship(back_populates="pd_files")


class CCFFile(CCFLog, table=True):
    __tablename__ = "ccf_file"

    minio_file_key: Optional[str] = Field(default=None)  # MinIO file reference

    user_id: Optional[int] = Field(foreign_key="users.id", ondelete="SET NULL")
    execution_model_id: Optional[int] = Field(
        foreign_key="model_execution_log.id", ondelete="SET NULL"
    )

    user: User = Relationship(back_populates="ccf_files")
    model_execution_log: "ModelExecutionLog" = Relationship(back_populates="ccf_files")


class StagingFile(StagingLog, table=True):
    __tablename__ = "staging_file"

    minio_file_key: Optional[str] = Field(default=None)  # MinIO file reference

    user_id: Optional[int] = Field(foreign_key="users.id", ondelete="SET NULL")
    execution_model_id: Optional[int] = Field(
        foreign_key="model_execution_log.id", ondelete="SET NULL"
    )

    user: User = Relationship(back_populates="staging_files")
    model_execution_log: "ModelExecutionLog" = Relationship(
        back_populates="staging_files"
    )


class EADFile(EADLog, table=True):
    __tablename__ = "ead_file"

    month_year_data: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    minio_file_key: Optional[str] = Field(default=None)  # MinIO file reference

    user_id: Optional[int] = Field(foreign_key="users.id", ondelete="SET NULL")
    execution_model_id: Optional[int] = Field(
        foreign_key="model_execution_log.id", ondelete="SET NULL"
    )

    user: User = Relationship(back_populates="ead_files")
    model_execution_log: "ModelExecutionLog" = Relationship(back_populates="ead_files")


class LGDFile(LGDLog, table=True):
    __tablename__ = "lgd_file"

    minio_file_key: Optional[str] = Field(default=None)  # MinIO file reference

    user_id: Optional[int] = Field(foreign_key="users.id", ondelete="SET NULL")
    execution_model_id: Optional[int] = Field(
        foreign_key="model_execution_log.id", ondelete="SET NULL"
    )

    user: User = Relationship(back_populates="lgd_files")
    model_execution_log: "ModelExecutionLog" = Relationship(back_populates="lgd_files")


class ECLFile(ECLLog, table=True):
    __tablename__ = "ecl_file"

    minio_file_key: Optional[str] = Field(default=None)  # MinIO file reference

    user_id: Optional[int] = Field(foreign_key="users.id", ondelete="SET NULL")
    execution_model_id: Optional[int] = Field(
        foreign_key="model_execution_log.id", ondelete="SET NULL"
    )

    user: User = Relationship(back_populates="ecl_files")
    model_execution_log: "ModelExecutionLog" = Relationship(back_populates="ecl_files")


class ModelExecutionLog(ModelExecutionBase, table=True):
    __tablename__ = "model_execution_log"

    executed_model_type: ExecutionModelType = Field(
        description="The type of model executed"
    )
    user_id: Optional[int] = Field(foreign_key="users.id", ondelete="SET NULL")
    execution_status: ModelExecutionStatus = Field(default=ModelExecutionStatus.RUNNING)
    celery_task_id: Optional[str] = Field(default=None)
    celery_task_name: Optional[str] = Field(default=None)

    user: User = Relationship(back_populates="model_execution_logs")
    ccf_files: CCFFile = Relationship(back_populates="model_execution_log")
    staging_files: StagingFile = Relationship(back_populates="model_execution_log")
    ead_files: EADFile = Relationship(back_populates="model_execution_log")
    lgd_files: LGDFile = Relationship(back_populates="model_execution_log")
    ecl_files: ECLFile = Relationship(back_populates="model_execution_log")
    pd_files: PDFile = Relationship(back_populates="model_execution_log")
    activities: List["ActivityLog"] = Relationship(back_populates="model_execution_log")
    fli_files: "FLIFile" = Relationship(back_populates="model_execution_log")
    dashboard_summary: "DashboardSummary" = Relationship(
        back_populates="model_execution_log"
    )
    ecl_model_report_summary: "ECLModelReportSummary" = Relationship(
        back_populates="execution_log_model"
    )


class ActivityLog(ActivityLogBase, table=True):
    __tablename__ = "activity_log"

    execution_model_id: Optional[int] = Field(
        foreign_key="model_execution_log.id", ondelete="SET NULL"
    )
    user_id: Optional[int] = Field(foreign_key="users.id", ondelete="SET NULL")


    user: User = Relationship(back_populates="activities")
    model_execution_log: ModelExecutionLog = Relationship(back_populates="activities")


class DashboardSummary(DashboardSummarySchema, table=True):
    __tablename__ = "dashboard_summary"

    sector_by_ecl_df: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    top_obligors: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    ecl_summary: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    execution_model_id: Optional[int] = Field(
        foreign_key="model_execution_log.id", ondelete="SET NULL"
    )

    model_execution_log: ModelExecutionLog = Relationship(
        back_populates="dashboard_summary"
    )


class FLIFile(FLILog, table=True):
    __tablename__ = "fli_file"

    id: Optional[int] = Field(default=None, primary_key=True)
    fli_table: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    forecast_scalars: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    summary_scenario_weights: Optional[List[dict]] = Field(
        default=None, sa_column=Column(JSON)
    )
    fli_scalar_weight: Optional[dict] = Field(
        default=None, sa_column=Column(JSON)
    )
    fli_scalar_weights_per_qrt: Optional[dict] = Field(
        default=None, sa_column=Column(JSON)
    )
    minio_file_key: Optional[str] = Field(default=None)  # MinIO file reference

    execution_model_id: Optional[int] = Field(
        foreign_key="model_execution_log.id", ondelete="SET NULL"
    )
    user_id: Optional[int] = Field(foreign_key="users.id", ondelete="SET NULL")

    user: User = Relationship(back_populates="fli_files")
    model_execution_log: ModelExecutionLog = Relationship(back_populates="fli_files")


class ECLModelReportSummary(SQLModel, table=True):
    __tablename__ = "ecl_model_report_summary"
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    total_ecl: Optional[float] = Field(default=None)
    ecl_stage1: Optional[float] = Field(default=None)
    ecl_stage2: Optional[float] = Field(default=None)
    ecl_stage3: Optional[float] = Field(default=None)
    execution_log_id_model: Optional[int] = Field(
        default=None, foreign_key="model_execution_log.id"
    )

    execution_log_model: Optional[ModelExecutionLog] = Relationship(
        back_populates="ecl_model_report_summary"
    )

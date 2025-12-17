# api/schema/models_schema.py
from typing import Optional, List, TypeVar, Generic
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pydantic import ConfigDict, field_validator
from sqlmodel import Field, SQLModel, JSON
from sqlalchemy import Column
from enum import Enum

T = TypeVar('T')

class ApprovalStatusEnum(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"

class ModelTypeEnum(str, Enum):
    STAGING = "staging_model"
    CCF = "ccf_model"
    EAD = "ead_model"
    LGD = "lgd_model"
    ECL = "ecl_model"
    PD = "pd_model"
    FLI = "fli_model"

class ModelExecutionStatus(str, Enum):
    COMPLETED = "Completed"
    FAILED = "Failed"
    RUNNING = "Running"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"
    PENDING_APPROVAL = "Pending_Approval"

class ExecutionModelType(str, Enum):
    PD = "pd"
    EAD = "ead"
    CCF = "ccf"
    ECL = "ecl"
    LGD = "lgd"
    FLI = "fli"
    STAGING = "staging"

class ModelExecutionBase(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    data_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    report_exported: bool = Field(default_factory=lambda: False)

class ModelExecutionLogPublic(ModelExecutionBase):
    execution_status: str
    user_name: str | None
    user_email: str | None
    execution_model_type: str
    report_exported: bool

    @field_validator("timestamp", mode="before")
    def convert_to_wat(cls, value: datetime) -> datetime:
        wat_timezone = ZoneInfo("Africa/Lagos")
        return value.astimezone(wat_timezone)

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

class ModelExecutionResponse(ModelExecutionBase):
    log_id: int
    status: str
    model_type: str
    message: Optional[str] = None
    data: Optional[dict] = None

    model_config = ConfigDict(protected_namespaces=())

class CCFLog(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    data_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))

    @field_validator("timestamp", mode="before")
    def convert_to_wat(cls, value: datetime) -> datetime:
        wat_timezone = ZoneInfo("Africa/Lagos")
        return value.astimezone(wat_timezone)

class StagingLog(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_number: str
    account_name: str
    performance_status: str
    dpd: float
    final_stage: float
    data: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))

class EADLog(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_number: str
    account_name: str
    date_of_origination: datetime
    date_of_maturity: datetime
    loan_type: str
    repayment_type: str
    eir: float
    payment_eir: float
    monthly_eir: float
    maturity_check: str
    total_ead: float
    month_year_data: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))

class LGDLog(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    segments: str
    final_lgd: float
    data: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))

class ECLLog(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_number: str
    account_name: str
    loan_balance: float
    stage: str
    final_ecl: float
    data: Optional[dict] = Field(default=None, sa_column=Column(JSON))

class PDLog(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    segments: str
    data_type: str
    reporting_date: Optional[str] = Field(default=None, description="Reporting date in YYYY-MM-DD format")
    data: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))

class FLILog(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    overall_verdict: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fli_table: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    forecast_scalars: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    summary_scenario_weights: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    fli_scalar_weight: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    fli_scalar_weights_per_qrt: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    @field_validator("timestamp", mode="before")
    def convert_to_wat(cls, value: datetime) -> datetime:
        wat_timezone = ZoneInfo("Africa/Lagos")
        return value.astimezone(wat_timezone)

class FLILogPublic(FLILog):
    execution_model_id: uuid.UUID
    user_name: str | None
    user_email: str | None

class DashboardSummarySchema(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    total_customers: Optional[int] = Field(default=None)
    total_ead: Optional[float] = Field(default=None)
    total_ecl: Optional[float] = Field(default=None)
    non_performing_loan_percentage: Optional[float] = Field(default=None)
    performing_loan_percentage: Optional[float] = Field(default=None)
    sector_by_ecl_df: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    top_obligors: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("timestamp", mode="before")
    def convert_to_wat(cls, value: datetime) -> datetime:
        wat_timezone = ZoneInfo("Africa/Lagos")
        return value.astimezone(wat_timezone)

class ObligorsListItem(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    obligor_name: Optional[str] = Field(default=None)
    obligor_account_number: Optional[str] = Field(default=None)
    obligor_ead: Optional[float] = Field(default=None)
    obligor_ecl: Optional[float] = Field(default=None)

class ActivityLogBase(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ActivityLogPublic(ActivityLogBase):
    user_name: str | None
    user_email: str | None
    execution_model_type: str | None
    execution_status: str | None

    @field_validator("timestamp", mode="before")
    def convert_to_wat(cls, value: datetime) -> datetime:
        wat_timezone = ZoneInfo("Africa/Lagos")
        return value.astimezone(wat_timezone)

class ECLModelReportSummarySchema(SQLModel):
    id: Optional[int] = Field(default=None)
    total_ecl: Optional[float] = Field(default=None)
    ecl_stage1: Optional[float] = Field(default=None)
    ecl_stage2: Optional[float] = Field(default=None)
    ecl_stage3: Optional[float] = Field(default=None)
    execution_log_id_model: Optional[int] = Field(default=None)

class ModelExecutionLogSchema(ModelExecutionBase):
    execution_status: str
    user_name: str | None = None            # made optional
    user_email: str | None = None           # made optional
    execution_model_type: str | None = None # made optional
    report_exported: bool

    @field_validator("timestamp", mode="before")
    def convert_to_wat(cls, value: datetime) -> datetime:
        wat_timezone = ZoneInfo("Africa/Lagos")
        return value.astimezone(wat_timezone)

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

class ModelSummaryByFacilityTypeSchema(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    facility_types: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("timestamp", mode="before")
    def convert_to_wat(cls, value: datetime) -> datetime:
        wat_timezone = ZoneInfo("Africa/Lagos")
        return value.astimezone(wat_timezone)

class SuccessMessage(SQLModel):
    message: str

class PaginatedResponse(SQLModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int

class PDModelReportScenarioSchema(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    industry_sector_code: str
    internal_rating: str
    scenario: str
    quarter_pd_values: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    execution_log_id_model: Optional[int] = Field(default=None)

class ECLModelReportScenarioSchema(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    account_number: str
    account_name: str
    facility_type: str
    sector: str
    stage: str
    rating_at_reporting_date: str
    expiry_date: str
    interest_rate: float
    balance: float
    ead: float
    pd: float
    lgd: float
    total_ecl: float
    scenario: str
    next_12_month_ecl: float
    quarter_ecl_values: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    execution_log_id_model: Optional[int] = Field(default=None)

class ECLModelReportDetailSchema(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    account_number: str
    account_name: str
    facility_type: str
    sector: str
    stage: str
    rating_at_reporting_date: str
    expiry_date: str
    interest_rate: float
    balance: float
    ead: float
    pd: float
    lgd: float
    total_ecl: float
    next_12_month_ecl: float
    quarter_ecl_values: Optional[List[dict]] = Field(default=None, sa_column=Column(JSON))
    execution_log_id_model: Optional[int] = Field(default=None)
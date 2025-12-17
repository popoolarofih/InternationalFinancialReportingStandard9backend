from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone

Base = declarative_base()

class ModelExecutionLog(Base):
    __tablename__ = "model_execution_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_name = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    report_exported = Column(Boolean, default=False, nullable=False)
    executed_model_type = Column(Enum(
        "PD", "EAD", "CCF", "ECL", "LGD", "FLI", "STAGING",
        name="executionmodeltype"
    ), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    execution_status = Column(Enum(
        "COMPLETED", "FAILED", "RUNNING", "CANCELLED", "REJECTED", "PENDING_APPROVAL",
        name="modelexecutionstatus"
    ), nullable=False)
    celery_task_id = Column(String, nullable=True)
    celery_task_name = Column(String, nullable=True)
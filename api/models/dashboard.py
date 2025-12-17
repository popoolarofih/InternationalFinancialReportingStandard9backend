from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel

class TopObligor(SQLModel, table=True):
    __tablename__ = "top_obligors"

    id: Optional[int] = Field(default=None, primary_key=True)
    account_name: Optional[str] = Field(default=None)
    ead: Optional[float] = Field(default=None)
    pd: Optional[float] = Field(default=None)
    lgd: Optional[float] = Field(default=None)
    ecl: Optional[float] = Field(default=None)
    identifier: Optional[str] = Field(default=None)  # EAD, ECL, PD, LGD
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
#stag3= ead*slgd*lgd 

class ECLSummary(SQLModel, table=True):
    __tablename__ = "ecl_summaries"

    id: Optional[int] = Field(default=None, primary_key=True)
    total_ecl: Optional[float] = Field(default=None)
    stage_1: Optional[float] = Field(default=None)
    stage_2: Optional[float] = Field(default=None)
    stage_3: Optional[float] = Field(default=None)
    ead_stage_1: Optional[float] = Field(default=None)
    ead_stage_2: Optional[float] = Field(default=None)
    ead_stage_3: Optional[float] = Field(default=None)
    total_customers: Optional[int] = Field(default=None)
    total_ead: Optional[float] = Field(default=None)
    performing_loan_percentage: Optional[float] = Field(default=None)
    non_performing_loan_percentage: Optional[float] = Field(default=None)
    npl: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SectorECL(SQLModel, table=True):
    __tablename__ = "sector_ecls"

    id: Optional[int] = Field(default=None, primary_key=True)
    sector: Optional[str] = Field(default=None)
    customers: Optional[int] = Field(default=None)
    ecl: Optional[float] = Field(default=None)
    percent_ecl: Optional[float] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

from typing import Optional
from sqlmodel import SQLModel, Field

class RepaymentFrequency(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    repayment_frequency: str = Field(index=True, nullable=False)
    times_per_year: int = Field(nullable=False)

class CollateralAssumption(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    collateral_description: str = Field(index=True, nullable=False)
    cbn_accepted_collateral_type: str = Field(nullable=False)
    haircut: float = Field(nullable=False)
    time_to_recovery_years: float = Field(nullable=False)
    direct_recovery_cost: float = Field(nullable=False)

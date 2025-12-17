from typing import Optional
from pydantic import BaseModel

class RepaymentFrequencyBase(BaseModel):
    repayment_frequency: str
    times_per_year: int

class RepaymentFrequencyCreate(RepaymentFrequencyBase):
    pass

class RepaymentFrequencyUpdate(RepaymentFrequencyBase):
    pass

class RepaymentFrequencyRead(RepaymentFrequencyBase):
    id: int

    class Config:
        orm_mode = True

RepaymentFrequencyResponse = RepaymentFrequencyRead

class CollateralAssumptionBase(BaseModel):
    collateral_description: str
    cbn_accepted_collateral_type: str
    haircut: float
    time_to_recovery_years: float
    direct_recovery_cost: float

class CollateralAssumptionCreate(CollateralAssumptionBase):
    pass

class CollateralAssumptionUpdate(CollateralAssumptionBase):
    pass

class CollateralAssumptionRead(CollateralAssumptionBase):
    id: int

    class Config:
        orm_mode = True

CollateralAssumptionResponse = CollateralAssumptionRead

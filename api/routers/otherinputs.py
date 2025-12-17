from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from api.database.database import get_db
from api.models.otherinputs import RepaymentFrequency, CollateralAssumption
from api.schema.otherinputs import (
    RepaymentFrequencyCreate,
    RepaymentFrequencyUpdate,
    RepaymentFrequencyResponse,
    CollateralAssumptionCreate,
    CollateralAssumptionUpdate,
    CollateralAssumptionResponse,
)

# import current_user and require authentication on the router
from api.utils.deps import current_user

router = APIRouter(prefix="/otherinputs", tags=["Mapping"], dependencies=[Depends(current_user)])

# RepaymentFrequency CRUD endpoints
@router.get("/repaymentfrequencies", response_model=List[RepaymentFrequencyResponse])
async def get_repayment_frequencies(db: Session = Depends(get_db)):
    """Get all repayment frequencies"""
    frequencies = db.query(RepaymentFrequency).all()
    return frequencies

@router.post("/repaymentfrequencies", response_model=RepaymentFrequencyResponse)
async def create_repayment_frequency(
    frequency: RepaymentFrequencyCreate,
    db: Session = Depends(get_db)
):
    """Create a new repayment frequency"""
    db_frequency = RepaymentFrequency(**frequency.dict())
    db.add(db_frequency)
    db.commit()
    db.refresh(db_frequency)
    return db_frequency

@router.get("/repaymentfrequencies/{frequency_id}", response_model=RepaymentFrequencyResponse)
async def get_repayment_frequency(
    frequency_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific repayment frequency by ID"""
    frequency = db.get(RepaymentFrequency, frequency_id)
    if not frequency:
        raise HTTPException(status_code=404, detail="Repayment frequency not found")
    return frequency

@router.put("/repaymentfrequencies/{frequency_id}", response_model=RepaymentFrequencyResponse)
async def update_repayment_frequency(
    frequency_id: int,
    frequency_update: RepaymentFrequencyUpdate,
    db: Session = Depends(get_db)
):
    """Update a repayment frequency"""
    frequency = db.get(RepaymentFrequency, frequency_id)
    if not frequency:
        raise HTTPException(status_code=404, detail="Repayment frequency not found")

    for key, value in frequency_update.dict(exclude_unset=True).items():
        setattr(frequency, key, value)

    db.commit()
    db.refresh(frequency)
    return frequency

@router.delete("/repaymentfrequencies/{frequency_id}")
async def delete_repayment_frequency(
    frequency_id: int,
    db: Session = Depends(get_db)
):
    """Delete a repayment frequency"""
    frequency = db.get(RepaymentFrequency, frequency_id)
    if not frequency:
        raise HTTPException(status_code=404, detail="Repayment frequency not found")

    db.delete(frequency)
    db.commit()
    return {"message": "Repayment frequency deleted successfully"}

# CollateralAssumption CRUD endpoints

@router.get("/collateralassumptions", response_model=List[CollateralAssumptionResponse])
async def get_collateral_assumptions(db: Session = Depends(get_db)):
    """Get all collateral assumptions"""
    assumptions = db.query(CollateralAssumption).all()
    return assumptions

@router.post("/collateralassumptions", response_model=CollateralAssumptionResponse)
async def create_collateral_assumption(
    assumption: CollateralAssumptionCreate,
    db: Session = Depends(get_db)
):
    """Create a new collateral assumption"""
    db_assumption = CollateralAssumption(**assumption.dict())
    db.add(db_assumption)
    db.commit()
    db.refresh(db_assumption)
    return db_assumption

@router.get("/collateralassumptions/{assumption_id}", response_model=CollateralAssumptionResponse)
async def get_collateral_assumption(
    assumption_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific collateral assumption by ID"""
    assumption = db.get(CollateralAssumption, assumption_id)
    if not assumption:
        raise HTTPException(status_code=404, detail="Collateral assumption not found")
    return assumption

@router.put("/collateralassumptions/{assumption_id}", response_model=CollateralAssumptionResponse)
async def update_collateral_assumption(
    assumption_id: int,
    assumption_update: CollateralAssumptionUpdate,
    db: Session = Depends(get_db)
):
    """Update a collateral assumption"""
    assumption = db.get(CollateralAssumption, assumption_id)
    if not assumption:
        raise HTTPException(status_code=404, detail="Collateral assumption not found")

    for key, value in assumption_update.dict(exclude_unset=True).items():
        setattr(assumption, key, value)

    db.commit()
    db.refresh(assumption)
    return assumption

@router.delete("/collateralassumptions/{assumption_id}")
async def delete_collateral_assumption(
    assumption_id: int,
    db: Session = Depends(get_db)
):
    """Delete a collateral assumption"""
    assumption = db.get(CollateralAssumption, assumption_id)
    if not assumption:
        raise HTTPException(status_code=404, detail="Collateral assumption not found")

    db.delete(assumption)
    db.commit()
    return {"message": "Collateral assumption deleted successfully"}

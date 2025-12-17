from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from api.database.database import get_db
from api.models.dashboard import TopObligor, ECLSummary, SectorECL
from api.utils.deps import current_user
from api.services.dashboard_service import DashboardService

router = APIRouter(tags=["Dashboard"], dependencies=[Depends(current_user)])

@router.get("/dashboard/top-obligors")
async def get_top_obligors(
    identifier: Optional[str] = Query("EAD", description="Identifier: EAD, ECL, PD, LGD"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    size: int = Query(20, ge=1, le=100, description="Page size (max 100)"),
    db: Session = Depends(get_db),
):
    # normalize identifier and ensure it's not None
    identifier = (identifier or "EAD").upper()
    offset = (page - 1) * size

    async with DashboardService(db) as service:
        # call the existing service signature (no limit/offset params)
        all_items = await service.fetch_top_obligors(identifier=identifier)

    # paginate in the router (service returned a list)
    total = len(all_items) if isinstance(all_items, list) else 0
    start = offset
    end = offset + size
    items = all_items[start:end] if isinstance(all_items, list) else []

    return {"page": page, "size": size, "total": total, "items": items}

@router.get("/dashboard/ecl-summary")
async def get_ecl_summary(db: Session = Depends(get_db)):
    async with DashboardService(db) as service:
        data = await service.fetch_ecl_summary()
        # Store the ECL summary data for future differences calculation
        if data.get("success"):
            summary_data = data["data"]["data"]
            mapped_summary = {
                "total_ecl": summary_data["Total ECL"],
                "stage_1": summary_data["ECL Stage 1"],
                "stage_2": summary_data["ECL Stage 2"],
                "stage_3": summary_data["ECL Stage 3"],
                "ead_stage_1": summary_data["EAD Balance Stage 1"],
                "ead_stage_2": summary_data["EAD Balance Stage 2"],
                "ead_stage_3": summary_data["EAD Balance Stage 3"],
                "total_customers": summary_data["total_customers"],
                "total_ead": summary_data["total_ead"],
                "performing_loan_percentage": summary_data["performing_loan_percentage"],
                "non_performing_loan_percentage": summary_data["non_performing_loan_percentage"]
            }
            await service.update_ecl_summary(mapped_summary)
    return data

@router.get("/dashboard/sector-by-ecl")
async def get_sector_by_ecl(db: Session = Depends(get_db)):
    async with DashboardService(db) as service:
        data = await service.fetch_sector_by_ecl()
    return data

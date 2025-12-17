import asyncio
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from api.database.database import get_db
from api.models.dashboard import TopObligor, ECLSummary, SectorECL
from api.core.logging import get_logger
from ifrsmodel.ECL.ECLmodel import ECLModel

logger = get_logger(__name__)

# Assuming the base URL is configurable, add to config if needed
BASE_URL = "http://localhost:8000"  # Replace with actual base URL

class DashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ConnectError))
    )
    async def fetch_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{BASE_URL}{endpoint}"
        logger.info(f"Fetching data from {url} with params {params}")
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Successfully fetched data from {endpoint}")
            return data
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching {endpoint}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching {endpoint}: {e}")
            raise

    async def fetch_top_obligors(self, identifier: str = "EAD", page: int = 1, page_size: int = 20) -> List[Dict[str, Any]]:
        def calculate():
            try:
                model = ECLModel()
                model.load_all_data()
                model.calculate_per_account_ecl()
                # Sort by identifier
                if identifier.upper() == "EAD":
                    sort_col = "Outstanding Balance (₦)"
                elif identifier.upper() == "ECL":
                    sort_col = "Scenario Weighted ECL"
                elif identifier.upper() == "PD":
                    sort_col = "Average PD"
                elif identifier.upper() == "LGD":
                    sort_col = "LGD"
                else:
                    sort_col = "Outstanding Balance (₦)"
                df = model.ecl_df.sort_values(by=sort_col, ascending=False)
                start = (page - 1) * page_size
                end = start + page_size
                top = df.iloc[start:end]
                data = []
                for _, row in top.iterrows():
                    data.append({
                        "account_name": row.get("Account Names", ""),
                        "ead": float(row.get("Outstanding Balance (₦)", 0)),
                        "pd": float(row.get("Average PD", 0)),
                        "lgd": float(row.get("LGD", 0)),
                        "ecl": float(row.get("Scenario Weighted ECL", 0))
                    })
                return data
            except Exception as e:
                logger.error(f"Error calculating top obligors: {e}")
                return []
        return await asyncio.to_thread(calculate)

    async def fetch_ecl_summary(self) -> Dict[str, Any]:
        def calculate():
            try:
                model = ECLModel()
                model.load_all_data()
                model.calculate_per_account_ecl()
                model.calculate_aggregations()
                # From ecl_by_stage
                stage_data = model.ecl_by_stage.set_index("IFRS 9 STAGE")["ECL"].to_dict()
                ead_stage_data = model.ecl_by_stage.set_index("IFRS 9 STAGE")["EAD"].to_dict()
                total_ecl = sum(stage_data.values())
                total_ead = sum(ead_stage_data.values())
                total_customers = len(model.ecl_df)
                performing_loans = len(model.ecl_df[model.ecl_df["IFRS 9 STAGE"] == 1])
                non_performing_loans = total_customers - performing_loans
                performing_loan_percentage = performing_loans / total_customers if total_customers > 0 else 0
                non_performing_loan_percentage = non_performing_loans / total_customers if total_customers > 0 else 0

                data = {
                    "Total ECL": float(total_ecl),
                    "ECL Stage 1": float(stage_data.get(1, 0)),
                    "EAD Balance Stage 1": float(ead_stage_data.get(1, 0)),
                    "ECL Stage 2": float(stage_data.get(2, 0)),
                    "EAD Balance Stage 2": float(ead_stage_data.get(2, 0)),
                    "ECL Stage 3": float(stage_data.get(3, 0)),
                    "EAD Balance Stage 3": float(ead_stage_data.get(3, 0)),
                    "total_customers": int(total_customers),
                    "total_ecl": float(total_ecl),
                    "performing_loan_percentage": float(performing_loan_percentage),
                    "total_ead": float(total_ead),
                    "non_performing_loan_percentage": float(non_performing_loan_percentage),
                    "npl": int(non_performing_loans)
                }

                # Fetch previous data for differences
                previous_summary = self.db.query(ECLSummary).order_by(ECLSummary.created_at.desc()).first()
                differences = {}
                if previous_summary:
                    for key in ["total_customers", "total_ead", "total_ecl", "non_performing_loan_percentage", "npl"]:
                        current_val = data.get(key, 0)
                        prev_val = getattr(previous_summary, key, 0) or 0
                        value_difference = current_val - prev_val
                        percent_difference = (value_difference / prev_val * 100) if prev_val != 0 else 0
                        differences[key] = {
                            "value_difference": float(value_difference),
                            "percent_difference": float(percent_difference)
                        }

                data["differences"] = differences

                return {
                    "success": True,
                    "status_code": 200,
                    "message": "ECL Summary retrieved successfully",
                    "error": "",
                    "data": {
                        "data": data
                    }
                }
            except Exception as e:
                logger.error(f"Error calculating ecl summary: {e}")
                return {
                    "success": False,
                    "status_code": 500,
                    "message": "Error retrieving ECL Summary",
                    "error": str(e),
                    "data": {}
                }
        return await asyncio.to_thread(calculate)

    async def fetch_sector_by_ecl(self) -> List[Dict[str, Any]]:
        def calculate():
            try:
                model = ECLModel()
                model.load_all_data()
                model.calculate_per_account_ecl()
                model.calculate_aggregations()
                # Get sector counts
                sector_counts = model.ecl_df.groupby("Business Sector").size().to_dict()
                # Prepare data
                import pandas as pd
                data = []
                for _, row in model.ecl_by_segment.iterrows():
                    sector = row["Business Sector"]
                    customers = sector_counts.get(sector, 0)
                    ecl_val = row["Total ECL"]
                    ecl = 0.0 if pd.isna(ecl_val) else float(ecl_val)
                    percent_val = row["% to ECL"]
                    percent_ecl = 0.0 if pd.isna(percent_val) else float(percent_val)
                    data.append({
                        "sector": sector,
                        "customers": int(customers),
                        "ecl": ecl,
                        "percent_ecl": percent_ecl
                    })
                return data
            except Exception as e:
                logger.error(f"Error calculating sector ECL: {e}")
                return []
        return await asyncio.to_thread(calculate)

    def validate_top_obligor(self, item: Dict[str, Any]) -> bool:
        required = ["account_name", "ead", "pd", "lgd", "ecl"]
        return all(key in item for key in required)

    def validate_ecl_summary(self, data: Dict[str, Any]) -> bool:
        required = ["total_ecl", "stage_1", "stage_2", "stage_3", "ead_stage_1", "ead_stage_2", "ead_stage_3", "total_customers", "total_ead", "performing_loan_percentage", "non_performing_loan_percentage", "npl"]
        return all(key in data for key in required)

    def validate_sector_ecl(self, item: Dict[str, Any]) -> bool:
        required = ["sector", "customers", "ecl", "percent_ecl"]
        return all(key in item for key in required)

    async def update_top_obligors(self, data: List[Dict[str, Any]], identifier: str):
        # Clear existing for this identifier
        self.db.query(TopObligor).filter(TopObligor.identifier == identifier).delete()
        for item in data:
            if not self.validate_top_obligor(item):
                logger.warning(f"Invalid top_obligor data: {item}")
                continue
            obligor = TopObligor(
                account_name=item.get("account_name"),
                ead=item.get("ead"),
                pd=item.get("pd"),
                lgd=item.get("lgd"),
                ecl=item.get("ecl"),
                identifier=identifier
            )
            self.db.add(obligor)
        self.db.commit()
        logger.info(f"Updated {len(data)} top obligors for identifier {identifier}")

    async def update_ecl_summary(self, data: Dict[str, Any]):
        # Clear existing
        self.db.query(ECLSummary).delete()
        if not self.validate_ecl_summary(data):
            logger.warning(f"Invalid ecl_summary data: {data}")
            return
        summary = ECLSummary(
            total_ecl=data.get("total_ecl"),
            stage_1=data.get("stage_1"),
            stage_2=data.get("stage_2"),
            stage_3=data.get("stage_3"),
            ead_stage_1=data.get("ead_stage_1"),
            ead_stage_2=data.get("ead_stage_2"),
            ead_stage_3=data.get("ead_stage_3"),
            total_customers=data.get("total_customers"),
            total_ead=data.get("total_ead"),
            performing_loan_percentage=data.get("performing_loan_percentage"),
            non_performing_loan_percentage=data.get("non_performing_loan_percentage"),
            npl=data.get("npl")
        )
        self.db.add(summary)
        self.db.commit()
        logger.info("Updated ECL summary")

    async def update_sector_ecls(self, data: List[Dict[str, Any]]):
        # Clear existing
        self.db.query(SectorECL).delete()
        for item in data:
            if not self.validate_sector_ecl(item):
                logger.warning(f"Invalid sector_ecl data: {item}")
                continue
            sector_ecl = SectorECL(
                sector=item.get("sector"),
                customers=item.get("customers"),
                ecl=item.get("ecl"),
                percent_ecl=item.get("percent_ecl")
            )
            self.db.add(sector_ecl)
        self.db.commit()
        logger.info(f"Updated {len(data)} sector ECLs")

    async def fetch_and_store_all(self):
        try:
            # Fetch all data concurrently
            tasks = [
                self.fetch_top_obligors(),
                self.fetch_ecl_summary(),
                self.fetch_sector_by_ecl()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            top_obligors_data = results[0] if not isinstance(results[0], Exception) else []
            ecl_summary_data = results[1] if not isinstance(results[1], Exception) else {}
            sector_ecl_data = results[2] if not isinstance(results[2], Exception) else []

            # Update DB
            await self.update_top_obligors(top_obligors_data, "EAD")  # Default identifier
            await self.update_ecl_summary(ecl_summary_data)
            await self.update_sector_ecls(sector_ecl_data)

            logger.info("Successfully fetched and stored all dashboard data")
        except Exception as e:
            logger.error(f"Error in fetch_and_store_all: {e}")
            raise


async def fetch_and_store_dashboard_data():
    db = next(get_db())
    async with DashboardService(db) as service:
        await service.fetch_and_store_all()

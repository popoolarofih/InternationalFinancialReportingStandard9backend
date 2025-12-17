from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
from datetime import datetime as dt

from api.database import get_db
from api.utils.deps import current_user
from api.models.user import (
    StagingFile,
    CCFFile,
    EADFile,
    LGDFile,
    ECLFile,
    PDFile,
    FLIFile,
    User,  # added: ensure we can lookup user by id if relationship isn't populated
)
from api.schema.models_schema import PaginatedResponse

router = APIRouter(prefix="/report", tags=["reports"])

def paginate_data(data: List[Dict[str, Any]], page: int, page_size: int) -> PaginatedResponse[Dict[str, Any]]:
    total = len(data)
    start = (page - 1) * page_size
    end = start + page_size
    items = data[start:end]
    pages = (total + page_size - 1) // page_size
    return PaginatedResponse(items=items, total=total, page=page, size=page_size, pages=pages)

# --- New helper functions ---
def fetch_file_record(model_cls, model_execution_id: Optional[int], db: Session, current_user: Any):
    """
    Try to fetch a file record for the current_user. If none found, fall back to latest overall record.
    If model_execution_id is provided, try to fetch that execution first (user-scoped then global).
    """
    try:
        if model_execution_id:
            # try user-scoped with execution id
            rec = (
                db.query(model_cls)
                .filter(model_cls.execution_model_id == model_execution_id, model_cls.user_id == current_user.id)
                .first()
            )
            if rec:
                return rec
            # fallback to any record with that execution id
            rec = db.query(model_cls).filter(model_cls.execution_model_id == model_execution_id).first()
            return rec
        # no execution id: latest for user
        rec = db.query(model_cls).filter(model_cls.user_id == current_user.id).order_by(model_cls.id.desc()).first()
        if rec:
            return rec
        # fallback to latest overall
        return db.query(model_cls).order_by(model_cls.id.desc()).first()
    except Exception:
        # On any unexpected error, return None so endpoints can handle it gracefully
        return None

def _normalize_value(v):
    """Normalize single cell value for JSON output: pandas NaN -> None, timestamps -> ISO strings, numpy -> native."""
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass

    # pandas Timestamp or datetime
    try:
        if isinstance(v, (pd.Timestamp, dt)):
            return v.isoformat()
    except Exception:
        pass

    # numpy integer/float/bool -> native python
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_ , bool)):
        return bool(v)

    # Decimal-like (keep as float if possible)
    try:
        # float conversion for numpy scalar types not caught above
        if isinstance(v, (int, float)):
            return v
    except Exception:
        pass

    return v

def _normalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Apply normalization to all values in a record (dict)."""
    if not isinstance(rec, dict):
        return rec
    return {k: _normalize_value(v) for k, v in rec.items()}

def extract_records_from_file_record(file_record, attr_name: str = "data"):
    """
    Normalize file_record attr to a list of records.
    - If attr is a list -> return (with normalization).
    - If attr is a dict (e.g., sheets) -> try to return first sheet's list or flatten all lists.
    - Else -> return [].
    """
    if not file_record:
        return []
    data = getattr(file_record, attr_name, None)
    if not data:
        return []
    # If data is already a list of records
    if isinstance(data, list):
        return [_normalize_record(r) for r in data]
    # If data is a dict (sheet_name -> list of records)
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list) and v]
        if not lists:
            return []
        # If one sheet, return it; otherwise flatten all sheets (keeps ordering per sheet)
        if len(lists) == 1:
            return [_normalize_record(r) for r in lists[0]]
        flattened = [item for lst in lists for item in lst]
        return [_normalize_record(r) for r in flattened]
    # Unknown format
    return []

@router.get("/staging")
async def get_staging_report(
    model_execution_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    file_record = fetch_file_record(StagingFile, model_execution_id, db, current_user)
    data = extract_records_from_file_record(file_record, "data")
    return paginate_data(data, page, page_size)

@router.get("/ccf")
async def get_ccf_report(
    model_execution_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    file_record = fetch_file_record(CCFFile, model_execution_id, db, current_user)
    data = extract_records_from_file_record(file_record, "data")
    return paginate_data(data, page, page_size)

@router.get("/ead")
async def get_ead_report(
    model_execution_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    file_record = fetch_file_record(EADFile, model_execution_id, db, current_user)
    # EAD stores month_year_data for the projection; fallback to 'data' too
    data = extract_records_from_file_record(file_record, "month_year_data") or extract_records_from_file_record(file_record, "data")
    return paginate_data(data, page, page_size)

@router.get("/lgd")
async def get_lgd_report(
    model_execution_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 100,  # kept for compatibility but not used in response
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    """
    Return combined LGD and SLGD output data for the current user (or latest overall).
    This endpoint returns flattened records with Business Sector and computed final_lgd.
    """
    try:
        # fetch recent LGDFile records: prefer user-scoped then fallback to overall latest
        records = (
            db.query(LGDFile)
            .filter(LGDFile.user_id == current_user.id)
            .order_by(LGDFile.id.desc())
            .limit(50)
            .all()
        )
        if not records:
            records = db.query(LGDFile).order_by(LGDFile.id.desc()).limit(50).all()

        combined: List[Dict[str, Any]] = []

        def _parse_num(x):
            """Robust numeric parser: handles lists, percent strings, comma thousands, numpy, None."""
            import numpy as _np
            if x is None:
                return None
            # unwrap single-element containers
            if isinstance(x, (list, tuple, _np.ndarray)):
                if len(x) == 0:
                    return None
                x = x[0]
            # pandas/numpy NaN
            try:
                if pd.isna(x):
                    return None
            except Exception:
                pass
            # string handling
            if isinstance(x, str):
                s = x.strip().replace(",", "")
                if s == "":
                    return None
                if s.endswith("%"):
                    try:
                        return float(s.rstrip("%")) / 100.0
                    except:
                        return None
                try:
                    return float(s)
                except:
                    return None
            # numeric
            try:
                return float(x)
            except:
                return None

        # normalize and flatten all rows from each LGDFile record
        for rec in records:
            data = getattr(rec, "data", None)
            if not data:
                continue
            rows: List[Dict[str, Any]] = []

            # If data stored as list of records already
            if isinstance(data, list):
                rows.extend(data)
            # If data stored as dict of sheets -> collect lists
            elif isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        rows.extend(v)
                    elif isinstance(v, dict):
                        # single row mapping
                        rows.append(v)
            else:
                # unknown format: skip
                continue

            for row in rows:
                if not isinstance(row, dict):
                    continue

                # detect sector value: check common keys
                sector = None
                for candidate in ["Business Sector", "Business sector", "SEGMENT", "segments", "segment"]:
                    if candidate in row and pd.notna(row.get(candidate)):
                        sector = row.get(candidate)
                        break
                # fallback: search keys case-insensitively
                if sector is None:
                    for k, v in row.items():
                        if "sector" in str(k).lower() or "segment" in str(k).lower():
                            if pd.notna(v):
                                sector = v
                                break

                if sector is None:
                    # skip rows with no sector info
                    continue

                # find unsecured LGD and secured LGD columns (case-insensitive search)
                unsecured_val = None
                secured_val = None
                for k, v in row.items():
                    kn = str(k).lower()
                    if "unsecured" in kn and "lgd" in kn:
                        unsecured_val = _parse_num(v)
                    elif "secured" in kn and "lgd" in kn:
                        secured_val = _parse_num(v)
                    elif kn == "lgd" and unsecured_val is None:
                        unsecured_val = _parse_num(v)
                    # sometimes secured is called 'discounted collateral' / 'secured recovery' -> try heuristics
                    elif ("secured" in kn or "collateral" in kn or "secured recovery" in kn) and secured_val is None:
                        maybe = _parse_num(v)
                        if maybe is not None:
                            secured_val = maybe

                # if both not found, try to find any numeric column that might be the LGD (last numeric)
                if unsecured_val is None:
                    numeric_candidates = []
                    for k, v in row.items():
                        if isinstance(v, (int, float)) or (isinstance(v, str) and any(ch.isdigit() for ch in v)):
                            parsed = _parse_num(v)
                            if parsed is not None:
                                numeric_candidates.append((k, parsed))
                    if numeric_candidates:
                        # pick last numeric candidate as a fallback (mimic earlier behavior)
                        unsecured_val = numeric_candidates[-1][1]

                # final_lgd computation:
                # - if both available -> product (unsecured * secured)
                # - if only one -> use that
                # - else fallback to rec.final_lgd (if present) or None
                final_lgd = None
                if unsecured_val is not None and secured_val is not None:
                    final_lgd = float(unsecured_val) * float(secured_val)
                elif unsecured_val is not None:
                    final_lgd = float(unsecured_val)
                elif secured_val is not None:
                    final_lgd = float(secured_val)
                else:
                    # try using top-level final_lgd field on the LGDFile record
                    top_final = getattr(rec, "final_lgd", None)
                    if top_final is not None:
                        try:
                            final_lgd = float(top_final)
                        except:
                            final_lgd = None

                # Ensure final_lgd is numeric and in reasonable bounds (0..1). If not, set None.
                if final_lgd is not None:
                    try:
                        if not (0.0 <= final_lgd <= 1.0):
                            # if value seems like percent >1 (e.g., 62 -> 0.62)
                            if final_lgd > 1 and final_lgd <= 100:
                                final_lgd = float(final_lgd) / 100.0
                            else:
                                # invalid -> clamp to None
                                final_lgd = None
                    except:
                        final_lgd = None

                combined.append({
                    "execution_model_id": str(getattr(rec, "execution_model_id", None)) if getattr(rec, "execution_model_id", None) else None,
                    "id": str(getattr(rec, "id", None)) if getattr(rec, "id", None) else None,
                    "Business sector": str(sector).strip() if sector is not None else None,
                    "final_lgd": final_lgd
                })

        # pagination over combined list
        total = len(combined)
        pages = (total + page_size - 1) // page_size if page_size and page_size > 0 else 1
        start = (page - 1) * page_size
        end = start + page_size
        page_items = combined[start:end]

        response = {
            "success": True,
            "status_code": 200,
            "message": "LGD model output retrieved",
            "data": {
                "data": page_items,
                "exports": None,
                "total_logs": total,
                "total_pages": pages,
                "current_page": page,
                "page_size": page_size
            }
        }
        return response

    except Exception as e:
        # Avoid throwing an unhandled 500 for malformed DB contents; return empty structured response
        return {
            "success": False,
            "status_code": 500,
            "message": f"Error retrieving LGD model output: {str(e)}",
            "data": {
                "data": [],
                "exports": None,
                "total_logs": 0,
                "total_pages": 0,
                "current_page": page,
                "page_size": page_size
            }
        }
#100*80
@router.get("/ecl")
async def get_ecl_report(
    data_type: Optional[str] = Query(None, description="Type of ECL data to retrieve", enum=["ECL Summary", "ECL by Segment", "ECL by Stage"]),
    model_execution_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    file_record = fetch_file_record(ECLFile, model_execution_id, db, current_user)
    if not file_record:
        raise HTTPException(status_code=404, detail="ECL file record not found")

    # ECL data is stored as a dict of sheets
    all_data = getattr(file_record, "data", {})
    if not isinstance(all_data, dict):
        raise HTTPException(status_code=500, detail="ECL data format is invalid")

    # Define the expected sheets
    expected_sheets = ["ECL Summary", "ECL by Segment", "ECL by Stage"]

    if data_type:
        if data_type not in expected_sheets:
            raise HTTPException(status_code=400, detail=f"Invalid data_type: {data_type}")
        sheet_data = all_data.get(data_type, [])
        if not isinstance(sheet_data, list):
            sheet_data = []
        return paginate_data(sheet_data, page, page_size)
    else:
        # Return all sheets if no data_type specified
        response = {}
        for sheet_name in expected_sheets:
            sheet_data = all_data.get(sheet_name, [])
            if not isinstance(sheet_data, list):
                sheet_data = []
            response[sheet_name] = paginate_data(sheet_data, page, page_size)
        return response

@router.get("/pd")
async def get_pd_report(
    data_type: str = Query(..., description="Type of PD data to retrieve", enum=["Cumulative PDs", "Conditional PDs", "Scaled Conditional PDs", "Monthly Conditional PDs", "Scaled Marginal PDs", "Best Marginal PDs", "Worse Marginal PDs", "Base Marginal PDs", "Scenario Weighted PDs"]),
    model_execution_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    file_record = fetch_file_record(PDFile, model_execution_id, db, current_user)
    if not file_record:
        raise HTTPException(status_code=404, detail="PD file record not found")

    # PD data is stored as a dict of sheets
    all_data = getattr(file_record, "data", {})
    if not isinstance(all_data, dict):
        raise HTTPException(status_code=500, detail="PD data format is invalid")

    # Map data_type to sheet names
    sheet_mapping = {
        "Cumulative PDs": "Cumulative PDs",
        "Conditional PDs": "Conditional PDs",
        "Scaled Conditional PDs": "Scaled Conditional Monthly",  # Note: this might be "Scaled Conditional PDs" but sheet is "Scaled Conditional Monthly"
        "Monthly Conditional PDs": "Conditional Monthly PDs",
        "Scaled Marginal PDs": "Scaled Marginal PDs",
        "Best Marginal PDs": "Best_Marginal",
        "Worse Marginal PDs": "Worst_Marginal",
        "Base Marginal PDs": "Base_Marginal",
        "Scenario Weighted PDs": "Scenario_Weighted",
    }

    sheet_name = sheet_mapping.get(data_type)
    if not sheet_name:
        raise HTTPException(status_code=400, detail=f"Invalid data_type: {data_type}")

    # Extract data for the specific sheet
    data = all_data.get(sheet_name, [])
    if not isinstance(data, list):
        data = []

    return paginate_data(data, page, page_size)

@router.get("/fli_response")
async def get_fli_response_report(
    model_execution_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    file_record = fetch_file_record(FLIFile, model_execution_id, db, current_user)
    data = extract_records_from_file_record(file_record, "fli_table") or extract_records_from_file_record(file_record, "forecast_scalars") or extract_records_from_file_record(file_record, "data")
    return paginate_data(data, page, page_size)

@router.get("/fli")
async def get_fli_report(
    model_execution_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    file_record = fetch_file_record(FLIFile, model_execution_id, db, current_user)
    if not file_record:
        return {
            "success": False,
            "status_code": 404,
            "message": "FLI model output not found",
            "error": "No FLI file record found for the given parameters",
            "data": None
        }

    # Try to get user from relationship; if missing, fetch by user_id
    user_obj = None
    if getattr(file_record, "user", None):
        user_obj = file_record.user
    elif getattr(file_record, "user_id", None):
        user_obj = db.query(User).filter(User.id == file_record.user_id).first()

    # Construct the FLI data object (NOTE: removed 'fli_table' per request)
    fli_data = {
        "id": str(file_record.id) if file_record.id else None,
        "overall_verdict": file_record.overall_verdict,
        "message": file_record.message,
        "timestamp": file_record.timestamp.isoformat() if file_record.timestamp else None,
        "forecast_scalars": file_record.forecast_scalars or [],
        "summary_scenario_weights": file_record.summary_scenario_weights or [],
        "execution_model_id": str(file_record.execution_model_id) if file_record.execution_model_id else None,
    }

    # If DB doesn't have summary_scenario_weights, compute a summary from forecast_scalars
    if not fli_data["summary_scenario_weights"]:
        forecast = fli_data["forecast_scalars"]
        # Mapping friendly scenario names to forecast keys
        key_map = {
            "Base": "Base Scenario",
            "Downturn": "Worst Scenario",
            "Upturn": "Best Scenario",
        }
        # Initialize counts
        counts = {
            "Base": {"Crude Oil Prices ": 0, "GDP ": 0, "Prime Lending Rates ": 0},
            "Downturn": {"Crude Oil Prices ": 0, "GDP ": 0, "Prime Lending Rates ": 0},
            "Upturn": {"Crude Oil Prices ": 0, "GDP ": 0, "Prime Lending Rates ": 0},
        }
        valid_periods = 0

        if isinstance(forecast, list) and forecast:
            for row in forecast:
                if not isinstance(row, dict):
                    continue
                # Try to extract numeric values for each scenario; skip period if any missing or non-numeric
                try:
                    vals = {}
                    for scen_name, key in key_map.items():
                        v = row.get(key, None)
                        # Some values may be strings; try convert
                        if v is None:
                            raise ValueError("missing")
                        vals[scen_name] = float(v)
                except Exception:
                    continue

                # We have numeric values for all three scenarios for this period
                valid_periods += 1
                # Rank scenarios: highest, middle, lowest
                ranked = sorted(vals.items(), key=lambda x: x[1], reverse=True)  # list of (scenario, value)
                # highest -> Crude Oil Prices
                counts[ranked[0][0]]["Crude Oil Prices "] += 1
                # middle -> GDP
                counts[ranked[1][0]]["GDP "] += 1
                # lowest -> Prime Lending Rates
                counts[ranked[2][0]]["Prime Lending Rates "] += 1

        # Build summary list and compute weights
        summary = []
        if valid_periods > 0:
            denom = 3 * valid_periods  # total counted across all scenarios and metrics
            for scen in ["Base", "Downturn", "Upturn"]:
                crude = counts[scen]["Crude Oil Prices "]
                gdp = counts[scen]["GDP "]
                rates = counts[scen]["Prime Lending Rates "]
                total = crude + gdp + rates
                weight = total / denom if denom else 0.0
                summary.append({
                    "Scenarios": scen,
                    "Crude Oil Prices ": crude,
                    "GDP ": gdp,
                    "Prime Lending Rates ": rates,
                    "Weights": weight
                })
        else:
            # No valid periods -> zeroed summary
            for scen in ["Base", "Downturn", "Upturn"]:
                summary.append({
                    "Scenarios": scen,
                    "Crude Oil Prices ": 0,
                    "GDP ": 0,
                    "Prime Lending Rates ": 0,
                    "Weights": 0.0
                })

        fli_data["summary_scenario_weights"] = summary

    return {
        "success": True,
        "status_code": 200,
        "message": "FLI model output retrieved",
        "error": "",
        "data": {
            "data": [fli_data]
        }
    }

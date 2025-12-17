# api/services/model_execution.py
from typing import Dict, Any, List
import pandas as pd
import os
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from api.models.user import (
    PDFile,
    LGDFile,
    EADFile,
    ECLFile,
    FLIFile,
    StagingFile,
    CCFFile,
    ModelExecutionLog,
)
from api.utils.crud import (
    create_pd_file,
    create_lgd_file,
    create_ead_file,
    create_ecl_file,
    create_fli_file,
    create_staging_file,
    create_ccf_file,
)
from api.utils.minio_service import minio_service

def convert_to_serializable(value):
    """
    Recursively convert pandas DataFrames and nested structures to JSON-serializable dicts/lists.
    Handles NaN values by converting them to None.
    """
    if isinstance(value, pd.DataFrame):
        # Convert DataFrame to dict, ensuring dates are strings and NaN becomes None
        df_dict = value.to_dict(orient='records')
        for record in df_dict:
            for k, v in record.items():
                if isinstance(v, pd.Timestamp):
                    record[k] = v.isoformat()
                elif pd.isna(v):  # Handle NaN values
                    record[k] = None
        return df_dict
    elif isinstance(value, dict):
        return {k: convert_to_serializable(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [convert_to_serializable(item) for item in value]
    elif isinstance(value, pd.Timestamp):
        return value.isoformat()
    elif pd.isna(value):  # Handle NaN values
        return None
    else:
        return value

def execute_pd(execution_log_id: int, db: Session, file_paths: Dict[str, str], reporting_date: str = None) -> Dict[str, Any]:
    """
    Execute PD model using provided file paths, reporting date, and FLI scalars from database.

    Args:
        execution_log_id: The execution log ID
        db: Database session
        file_paths: Dictionary containing file paths for PD input
        reporting_date: Reporting date in YYYY-MM-DD format
    """
    try:
        # Override default paths with uploaded ones
        pd_input_path = file_paths.get("pd_input", "worktemplates/pd_input.xlsx")

        # Validate reporting date format
        if reporting_date:
            try:
                datetime.strptime(reporting_date, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Invalid reporting date format: {reporting_date}. Expected YYYY-MM-DD")

        # Get the current execution log to find user
        log = db.query(ModelExecutionLog).filter(ModelExecutionLog.id == execution_log_id).first()
        if not log:
            raise Exception("Execution log not found")

        # Retrieve latest FLI scalars for the user
        from api.models.user import FLIFile
        latest_fli = (
            db.query(FLIFile)
            .join(ModelExecutionLog)
            .filter(ModelExecutionLog.user_id == log.user_id)
            .order_by(ModelExecutionLog.timestamp.desc())
            .first()
        )
        fli_scalars = latest_fli.fli_scalar_weights_per_qrt if latest_fli else {}

        # Run the main PD logic with PD input path and FLI scalars
        from ifrsmodel.PD.PD_run_all import main
        main(reporting_date=reporting_date, pd_input_path=pd_input_path, fli_scalars=fli_scalars)

        # Load output Excel and convert to dicts
        output_path = "worktemplates/PD_results_final.xlsx"
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"PD output not found: {output_path}")

        xls = pd.ExcelFile(output_path)
        data: Dict[str, List[dict]] = {}
        for sheet_name in xls.sheet_names:
            df_out = pd.read_excel(xls, sheet_name=sheet_name)
            data[sheet_name] = df_out.to_dict("records")

        # Upload output file to MinIO
        minio_file_key = minio_service.upload_file(
            output_path,
            "pd",
            execution_log_id,
            f"pd_results_{reporting_date or datetime.now().strftime('%Y%m%d')}.xlsx"
        )

        # Create PDFile entry with MinIO reference
        pd_file = PDFile(
            execution_model_id=execution_log_id,
            segments="all",  # Required field from PDLog
            data_type="marginal_cumulative_conditional",  # Adjust based on sheets
            reporting_date=reporting_date,
            data=convert_to_serializable(data),
            minio_file_key=minio_file_key,  # Add MinIO reference
        )
        create_pd_file(db, pd_file)

        # Clean up temporary files from worktemplates folder
        try:
            if os.path.exists(output_path):
                os.remove(output_path)
            if os.path.exists(pd_input_path):
                os.remove(pd_input_path)
        except Exception as cleanup_error:
            # Log cleanup error but don't fail the execution
            print(f"Warning: Failed to clean up temporary files: {cleanup_error}")

        return {
            "data_types": list(data.keys()),
            "rows": {k: len(v) for k, v in data.items()},
            "minio_file_key": minio_file_key
        }

    except Exception as e:
        raise Exception(f"PD execution error: {str(e)}")


def execute_lgd(execution_log_id: int, db: Session, file_paths: Dict[str, str]) -> Dict[str, Any]:
    """
    Execute LGD model using provided file paths.
    Runs the unsecured LGD pipeline (mirrors ifrsmodel/LGD/LGDinput.py) and saves LGD_Final.xlsx,
    then creates a DB record. Robustly handles list/string/non-numeric LGD cells.
    """
    try:
        lgd_path = file_paths.get("lgd_input", "worktemplates/LGD.xlsx")

        # Import LGD pipeline functions from the LGD module
        from ifrsmodel.LGD.LGDinput import (
            load_lgd_input,
            preprocess_lgd_data,
            compute_lgd_migration_table,
            compute_quarterly_sums,
            compute_average_migration_matrix,
            compute_mmult_quarters,
            compute_final_lgd,
            LGD_FALLBACK,
        )

        import numpy as np  # local import to avoid changing top-level imports

        # Load and preprocess
        df = load_lgd_input(file_path=lgd_path, header_row=1)
        df_pre = preprocess_lgd_data(df)

        # Ensure preprocess output is a DataFrame (preprocess_lgd_data may return list/dict)
        if isinstance(df_pre, list):
            df_pre = pd.DataFrame(df_pre)
        elif isinstance(df_pre, dict):
            # If dict of sheets -> try first list sheet, else coerce to single-row DF
            lists = [v for v in df_pre.values() if isinstance(v, list) and len(v) > 0]
            if lists:
                df_pre = pd.DataFrame(lists[0])
            else:
                # convert mapping to single-row DF
                df_pre = pd.DataFrame([df_pre])
        else:
            # last resort: coerce any other type to DataFrame
            try:
                df_pre = pd.DataFrame(df_pre)
            except Exception:
                df_pre = pd.DataFrame()

        # normalize column names
        if not df_pre.empty:
            df_pre.columns = [str(c).strip() for c in df_pre.columns]

        # Determine sectors / quarters / statuses
        try:
            sectors = df_pre['Business sector'].dropna().unique().tolist()
        except Exception:
            sectors = df_pre['Business sector'].unique().tolist() if 'Business sector' in df_pre.columns else []

        statuses = ['Performing', 'Default', 'Watchlist']
        if 'Reporting Date' in df_pre.columns:
            # parse reporting dates robustly, drop NaT, keep unique values
            parsed = pd.to_datetime(df_pre['Reporting Date'].dropna(), errors='coerce').dropna().unique()
            parsed = [p for p in parsed if pd.notna(p)]
            if len(parsed) >= 4:
                last4 = sorted(parsed)[-4:]
                # format to yyyy-mm-dd strings
                quarters = [pd.to_datetime(d).strftime("%Y-%m-%d") for d in last4]
            else:
                quarters = ['2024-09-30', '2024-12-31', '2025-03-31', '2025-06-30']
        else:
            quarters = ['2024-09-30', '2024-12-31', '2025-03-31', '2025-06-30']

        # Compute tables
        migration_df = compute_lgd_migration_table(df_pre, sectors, statuses, quarters)
        # coerce to DataFrame if necessary
        if not isinstance(migration_df, pd.DataFrame):
            try:
                migration_df = pd.DataFrame(migration_df)
            except Exception:
                migration_df = pd.DataFrame()

        quarterly_sums_df = compute_quarterly_sums(df_pre, sectors)
        if not isinstance(quarterly_sums_df, pd.DataFrame):
            try:
                quarterly_sums_df = pd.DataFrame(quarterly_sums_df)
            except Exception:
                quarterly_sums_df = pd.DataFrame()

        avg_migration_df = compute_average_migration_matrix(quarterly_sums_df)
        if not isinstance(avg_migration_df, pd.DataFrame):
            try:
                avg_migration_df = pd.DataFrame(avg_migration_df)
            except Exception:
                avg_migration_df = pd.DataFrame()

        mmult_results = compute_mmult_quarters(avg_migration_df, quarters=4)
        if not isinstance(mmult_results, pd.DataFrame):
            try:
                mmult_results = pd.DataFrame(mmult_results)
            except Exception:
                mmult_results = pd.DataFrame()

        final_lgd_df = compute_final_lgd(mmult_results, avg_migration_df)

        # Normalize final_lgd_df to DataFrame
        if isinstance(final_lgd_df, list):
            final_lgd_df = pd.DataFrame(final_lgd_df)
        if not isinstance(final_lgd_df, pd.DataFrame):
            final_lgd_df = pd.DataFrame([final_lgd_df])

        # Find a LGD-like column name
        lgd_col = None
        for c in final_lgd_df.columns:
            if 'lgd' in str(c).lower():
                lgd_col = c
                break
        if lgd_col is None:
            # Create a fallback column if none exists
            final_lgd_df['UNSECURED LGD'] = LGD_FALLBACK
            lgd_col = 'UNSECURED LGD'

        # Robust parser for various cell types (list, string with %, commas, numeric)
        def _parse_cell(x):
            # flatten single-element lists/tuples/ndarrays
            if isinstance(x, (list, tuple, np.ndarray)):
                if len(x) == 0:
                    return np.nan
                x = x[0]
            if pd.isna(x):
                return np.nan
            # handle strings
            if isinstance(x, str):
                s = x.strip().replace(",", "")
                if s == "":
                    return np.nan
                if s.endswith('%'):
                    try:
                        return float(s.strip('%')) / 100.0
                    except:
                        return np.nan
                try:
                    return float(s)
                except:
                    return np.nan
            # numeric
            try:
                return float(x)
            except:
                return np.nan

        ser = final_lgd_df[lgd_col].apply(_parse_cell)
        # replace NaNs with fallback before aggregate
        ser_clean = ser.fillna(LGD_FALLBACK)

        try:
            agg_final_lgd = float(ser_clean.mean()) if not ser_clean.empty else float(LGD_FALLBACK)
        except Exception:
            agg_final_lgd = float(LGD_FALLBACK)

        # Ensure there is at least one row
        if final_lgd_df.empty:
            final_lgd_df = pd.DataFrame([{"SEGMENT": "ALL", lgd_col: agg_final_lgd}])

        # Save to LGD_Final.xlsx (used by downstream models)
        out_path = os.path.join("worktemplates", "LGD_Final.xlsx")
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            df_pre.to_excel(writer, sheet_name="Preprocessed Data", index=False)
            migration_df.to_excel(writer, sheet_name="Migration Table", index=False)
            quarterly_sums_df.to_excel(writer, sheet_name="Quarterly Sums", index=False)
            avg_migration_df.to_excel(writer, sheet_name="Avg Migration Matrix", index=False)
            mmult_results.to_excel(writer, sheet_name="MMULT Results", index=False)
            final_lgd_df.to_excel(writer, sheet_name="Final LGD Table", index=False)

        # Upload LGD_Final.xlsx to MinIO
        minio_file_key = minio_service.upload_file(
            out_path,
            "lgd",
            execution_log_id,
            f"LGD_Final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        # Prepare data as dict of sheets
        data = {
            "Preprocessed Data": convert_to_serializable(df_pre),
            "Final LGD Table": convert_to_serializable(final_lgd_df)
        }

        # Create LGDFile DB record
        lgd_file = LGDFile(
            execution_model_id=execution_log_id,
            segments="all",
            final_lgd=agg_final_lgd,
            data=data,
            minio_file_key=minio_file_key,
        )
        create_lgd_file(db, lgd_file)

        # Clean up temporary files
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
            if os.path.exists(lgd_path):
                os.remove(lgd_path)
        except Exception as cleanup_error:
            print(f"Warning: Failed to clean up temporary files: {cleanup_error}")

        return {"rows": len(data), "sheets": ["Preprocessed Data", "Migration Table", "Quarterly Sums", "Avg Migration Matrix", "MMULT Results", "Final LGD Table"], "minio_file_key": minio_file_key}

    except Exception as e:
        raise Exception(f"LGD execution error: {str(e)}")


def execute_slgd(execution_log_id: int, db: Session, file_paths: Dict[str, str]) -> Dict[str, Any]:
    """
    Execute SLGD (Secured) model using provided file paths.
    """
    try:
        slgd_path = file_paths.get("secured_lgd", "worktemplates/SecuredLGD.xlsx")

        # Run SLGD logic (adapted from SLGDinput.py __main__)
        from ifrsmodel.LGD.SLGD.SLGDinput import (
            load_securedlgd_input,
            create_lgd_lookup_tables,
            preprocess_secured_lgd,
        )

        df = load_securedlgd_input(file_path=slgd_path, header_row=1)
        print("Original Columns:")
        print(df.columns)

        # Load other inputs from database
        from ifrsmodel.OtherInputs import load_other_inputs
        repayment_freq_df, collateral_df = load_other_inputs()

        df_p = preprocess_secured_lgd(
            df, current_date="2025-09-09", repayment_freq_lookup=repayment_freq_df, collateral_lookup=collateral_df
        )

        print("\nAfter preprocessing, sample of new columns:")
        sample_cols = ["Tenor (Days)", "Tenor (Months)", "Repayment Frequency in a Year", "Discounted Collateral", "Secured Recovery", "Secured LGD"]
        if all(col in df_p.columns for col in sample_cols):
            sample_df = df_p[sample_cols].head()
            print(sample_df)

        # Save to Excel
        out_path = os.path.join("worktemplates", "SecuredLGD_Output.xlsx")
        df_p.to_excel(out_path, index=False)

        # Upload output file to MinIO
        minio_file_key = minio_service.upload_file(
            out_path,
            "slgd",
            execution_log_id,
            f"secured_lgd_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        # Store processed data
        data = df_p.to_dict("records")

        # Reuse LGDFile for SLGD
        lgd_file = LGDFile(
            execution_model_id=execution_log_id,
            segments="all",  # Required field from LGDLog
            final_lgd=0.0,  # Default value for SLGD, no aggregate available
            data=convert_to_serializable(data),  # Full processed DF
            minio_file_key=minio_file_key,  # Add MinIO reference
        )
        create_lgd_file(db, lgd_file)

        # Clean up temporary files from worktemplates folder
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
            if os.path.exists(slgd_path):
                os.remove(slgd_path)
        except Exception as cleanup_error:
            # Log cleanup error but don't fail the execution
            print(f"Warning: Failed to clean up temporary files: {cleanup_error}")

        return {"rows": len(data), "columns": list(df_p.columns), "minio_file_key": minio_file_key}

    except Exception as e:
        raise Exception(f"SLGD execution error: {str(e)}")


def execute_ead(execution_log_id: int, db: Session, file_paths: Dict[str, str]) -> Dict[str, Any]:
    """
    Execute EAD model using provided file paths.
    """
    try:
        rawdata_path = file_paths.get("rawdata", "worktemplates/Rawdata.xlsx")
        
        # Run EAD logic (adapted from EADmodel.py __main__)
        from ifrsmodel.EAD.EADmodel import calculate_ead_term_structure

        out_path = os.path.join("worktemplates", "EAD_Term_Structure_Output.xlsx")

        if not os.path.exists(rawdata_path):
            raise FileNotFoundError(f"Input file not found: {rawdata_path}")

        raw_df = pd.read_excel(rawdata_path, header=1)
        print("✅ Loaded data:", raw_df.shape)
        print("Columns:", raw_df.columns.tolist())

        enriched = calculate_ead_term_structure(raw_df, months_forward=13)

        # Save as per script (simplified)
        enriched.to_excel(out_path, sheet_name="EAD_Term_Structure", index=False)

        # Upload output file to MinIO
        minio_file_key = minio_service.upload_file(
            out_path,
            "ead",
            execution_log_id,
            f"ead_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        # Load and store
        enriched_df = pd.read_excel(out_path, sheet_name="EAD_Term_Structure")
        data = enriched_df.to_dict("records")

        # Extract required fields from the first row or provide defaults
        first_row = data[0] if data else {}
        ead_file = EADFile(
            execution_model_id=execution_log_id,
            account_number=str(first_row.get('Account Number', 'N/A')),
            account_name=str(first_row.get('Account Name', 'N/A')),
            date_of_origination=datetime.now(timezone.utc),  # Default
            date_of_maturity=datetime.now(timezone.utc),  # Default
            loan_type=str(first_row.get('Loan Type', 'N/A')),
            repayment_type=str(first_row.get('Repayment Type', 'N/A')),
            eir=float(first_row.get('EIR', 0.0)),
            payment_eir=float(first_row.get('Payment EIR', 0.0)),
            monthly_eir=float(first_row.get('Monthly EIR', 0.0)),
            maturity_check=str(first_row.get('Maturity Check', 'N/A')),
            total_ead=float(first_row.get('Total EAD', 0.0)),
            month_year_data=convert_to_serializable(data),
            minio_file_key=minio_file_key,  # Add MinIO reference
        )
        create_ead_file(db, ead_file)

        # Clean up temporary files from worktemplates folder
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
            if os.path.exists(rawdata_path):
                os.remove(rawdata_path)
        except Exception as cleanup_error:
            # Log cleanup error but don't fail the execution
            print(f"Warning: Failed to clean up temporary files: {cleanup_error}")

        return {"rows": len(data), "projection_months": 13, "minio_file_key": minio_file_key}

    except Exception as e:
        raise Exception(f"EAD execution error: {str(e)}")


def execute_ecl(execution_log_id: int, db: Session, file_paths: Dict[str, str], reporting_date: str = None) -> Dict[str, Any]:
    """
    Execute ECL model using provided file paths (if any).
    """
    try:
        rawdata_path = file_paths.get("rawdata", "worktemplates/Rawdata.xlsx")

        # Get the current execution log to find user
        log = db.query(ModelExecutionLog).filter(ModelExecutionLog.id == execution_log_id).first()
        if not log:
            raise Exception("Execution log not found")

        # Fetch latest LGD data from database and save to file
        latest_lgd = (
            db.query(LGDFile)
            .join(ModelExecutionLog)
            .filter(ModelExecutionLog.user_id == log.user_id)
            .order_by(ModelExecutionLog.timestamp.desc())
            .first()
        )
        if latest_lgd and latest_lgd.data:
            lgd_df = pd.DataFrame(latest_lgd.data.get("Final LGD Table", []))
            lgd_df.to_excel(os.path.join("worktemplates", "LGD_Final.xlsx"), sheet_name="Final LGD Table", index=False)

        # Fetch latest PD data from database and save to file
        latest_pd = (
            db.query(PDFile)
            .join(ModelExecutionLog)
            .filter(ModelExecutionLog.user_id == log.user_id)
            .order_by(ModelExecutionLog.timestamp.desc())
            .first()
        )
        if latest_pd and latest_pd.data:
            with pd.ExcelWriter(os.path.join("worktemplates", "PD_results_final.xlsx")) as writer:
                for sheet_name, records in latest_pd.data.items():
                    df = pd.DataFrame(records)
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

        # Fetch latest EAD data from database and save to file
        latest_ead = (
            db.query(EADFile)
            .join(ModelExecutionLog)
            .filter(ModelExecutionLog.user_id == log.user_id)
            .order_by(ModelExecutionLog.timestamp.desc())
            .first()
        )
        if latest_ead and latest_ead.month_year_data:
            ead_df = pd.DataFrame(latest_ead.month_year_data)
            ead_df.to_excel(os.path.join("worktemplates", "EAD_Term_Structure_Output.xlsx"), index=False)

        # Fetch latest Staging data from database and save to file
        latest_staging = (
            db.query(StagingFile)
            .join(ModelExecutionLog)
            .filter(ModelExecutionLog.user_id == log.user_id)
            .order_by(ModelExecutionLog.timestamp.desc())
            .first()
        )
        if latest_staging and latest_staging.data:
            staging_df = pd.DataFrame(latest_staging.data)
            staging_df.to_excel(os.path.join("worktemplates", "Staging.xlsx"), index=False)

        # Ensure rawdata is in the expected location
        expected_rawdata_path = os.path.join("worktemplates", "Rawdata.xlsx")
        if rawdata_path and rawdata_path != expected_rawdata_path:
            import shutil
            shutil.copy(rawdata_path, expected_rawdata_path)

        # Run ECL logic (from ECLmodel.py)
        from ifrsmodel.ECL.ECLmodel import ECLModel

        model = ECLModel(base_path="worktemplates")
        model.load_all_data()  # Assumes outputs from previous models; rawdata if provided
        model.calculate_per_account_ecl()
        model.calculate_aggregations()
        model.export_to_excel()  # Saves to ECLFinalSummary_Rewrite.xlsx

        out_path = os.path.join("worktemplates", "ECLFinalSummary_Rewrite.xlsx")

        # Upload output file to MinIO
        minio_file_key = minio_service.upload_file(
            out_path,
            "ecl",
            execution_log_id,
            f"ecl_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        # Load sheets and store
        xls = pd.ExcelFile(out_path)
        data: Dict[str, List[dict]] = {}
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            data[sheet_name] = df.to_dict("records")

        # Extract required fields from ECL Summary sheet if available
        ecl_summary = data.get("ECL Summary", [])
        first_row = ecl_summary[0] if ecl_summary else {}
        ecl_file = ECLFile(
            execution_model_id=execution_log_id,
            account_number=str(first_row.get('Account Number', 'N/A')),
            account_name=str(first_row.get('Account Name', 'N/A')),
            loan_balance=float(first_row.get('Loan Balance', 0.0)),
            stage=str(first_row.get('Stage', 'N/A')),
            final_ecl=float(first_row.get('Final ECL', 0.0)),
            data=convert_to_serializable(data),
            minio_file_key=minio_file_key,  # Add MinIO reference
        )
        create_ecl_file(db, ecl_file)

        # Clean up temporary files from worktemplates folder
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
            if rawdata_path and os.path.exists(rawdata_path):
                os.remove(rawdata_path)
        except Exception as cleanup_error:
            # Log cleanup error but don't fail the execution
            print(f"Warning: Failed to clean up temporary files: {cleanup_error}")

        return {"sheets": list(data.keys()), "summary_rows": len(data.get("ECL Summary", [])), "minio_file_key": minio_file_key}

    except Exception as e:
        raise Exception(f"ECL execution error: {str(e)}")


def execute_fli(execution_log_id: int, db: Session, file_paths: Dict[str, str]) -> Dict[str, Any]:
    """
    Execute FLI model using provided file paths.
    """
    try:
        fli_path = file_paths.get("fli_input")
        if not fli_path:
            raise Exception("FLI input file path not provided")
        
        # Run FLI model: first get scenario weights, then get FLI model
        from ifrsmodel.FLI_model.scenario_weights import get_scenario_weights
        from ifrsmodel.FLI_model.fli_model import get_fli_model

        scenario_output_dict = get_scenario_weights(fli_path, "Scenario Weight Historical Data")
        if scenario_output_dict is None:
            raise Exception("Failed to get scenario weights for FLI model")

        result = get_fli_model(fli_file_path=fli_path, scenario_output_dict=scenario_output_dict)
        if result is None:
            raise Exception("Failed to run FLI model")

        # Create output Excel file for FLI results
        fli_output_path = os.path.join("worktemplates", f"FLI_Output_{execution_log_id}.xlsx")

        # Create a summary Excel file with FLI results
        with pd.ExcelWriter(fli_output_path, engine="openpyxl") as writer:
            # Save MEV forecast quarterly if available
            if result.get("mev_forecast_quarterly") is not None:
                fli_forecast_df = result["mev_forecast_quarterly"]
                fli_forecast_df.to_excel(writer, sheet_name="MEV_Forecast_Quarterly", index=False)

            # Save historical input df if available
            if result.get("historical_input_df") is not None:
                hist_input_df = result["historical_input_df"]
                hist_input_df.to_excel(writer, sheet_name="Historical_Input", index=False)

            # Save correlation analysis if available
            if result.get("correlation_analysis") is not None:
                corr_analysis_df = result["correlation_analysis"]
                corr_analysis_df.to_excel(writer, sheet_name="Correlation_Analysis")

            # Save regression results if available
            if result.get("regression_result_to_excel_sheet") is not None:
                for sheet_name, dfs in result["regression_result_to_excel_sheet"].items():
                    for df_name, df in dfs.items():
                        df.to_excel(writer, sheet_name=f"{sheet_name}_{df_name}")

            # Save FLI run validation table if available
            if result.get("fli_run_validation") is not None:
                validation_df = result["fli_run_validation"]["Table"]
                validation_df.to_excel(writer, sheet_name="FLI_Run_Validation", index=False)

            # Save forecast scalars if available
            if result.get("forecast_scalars") is not None:
                forecast_scalars_df = result["forecast_scalars"]
                forecast_scalars_df.to_excel(writer, sheet_name="Forecast_Scalars", index=False)

            # Save summary scenario weights if available
            if result.get("summary_scenario_weights") is not None:
                summary_weights_df = result["summary_scenario_weights"]
                summary_weights_df.to_excel(writer, sheet_name="Scenario_Weights", index=False)

        # Upload output file to MinIO (using FLI bucket)
        minio_file_key = minio_service.upload_file(
            fli_output_path,
            "fli",
            execution_log_id,
            f"fli_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        fli_file = FLIFile(
            execution_model_id=execution_log_id,
            overall_verdict="success",
            message="FLI model executed successfully",
            timestamp=datetime.now(timezone.utc),
            fli_table=convert_to_serializable(result.get("fli_table", [])),
            forecast_scalars=convert_to_serializable(result.get("forecast_scalars", [])),
            summary_scenario_weights=convert_to_serializable(result.get("summary_scenario_weights", [])),
            fli_scalar_weight=convert_to_serializable(result.get("fli_scalar_weight", {})),
            fli_scalar_weights_per_qrt=convert_to_serializable(result.get("fli_scalar_weights_per_qrt", {})),
            minio_file_key=minio_file_key,  # Add MinIO reference
        )
        create_fli_file(db, fli_file)

        # Clean up temporary files from worktemplates folder
        try:
            if os.path.exists(fli_output_path):
                os.remove(fli_output_path)
            if os.path.exists(fli_path):
                os.remove(fli_path)
        except Exception as cleanup_error:
            # Log cleanup error but don't fail the execution
            print(f"Warning: Failed to clean up temporary files: {cleanup_error}")

        return {"components": list(result.keys()), "minio_file_key": minio_file_key}

    except Exception as e:
        raise Exception(f"FLI execution error: {str(e)}")


def execute_staging(execution_log_id: int, db: Session, file_paths: Dict[str, str]) -> Dict[str, Any]:
    """
    Execute Staging model using provided file paths.
    """
    try:
        rawdata_path = file_paths.get("rawdata", "worktemplates/Rawdata.xlsx")
        
        # The staging.py does not have a main function, so we need to call the create_staging_table function directly
        import pandas as pd
        from ifrsmodel.staging import create_staging_table
        
        # Load raw data
        raw_df = pd.read_excel(rawdata_path, header=1)
        
        # Create staging table
        staging_df = create_staging_table(raw_df)
        
        # Save staging output
        out_path = "worktemplates/Staging.xlsx"
        staging_df.to_excel(out_path, index=False)

        # Load output Staging.xlsx
        df = pd.read_excel(out_path)
        data = df.to_dict("records")

        # Upload output file to MinIO
        minio_file_key = minio_service.upload_file(
            out_path,
            "staging",
            execution_log_id,
            f"staging_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        # Extract required fields from the first row or provide defaults
        first_row = data[0] if data else {}
        staging_file = StagingFile(
            execution_model_id=execution_log_id,
            account_number=str(first_row.get('Account ID', 'N/A')),
            account_name=str(first_row.get('Account Names', 'N/A')),
            performance_status=str(first_row.get('PERFORMANCE CLASS (31-Mar-25)', 'N/A')),
            dpd=float(first_row.get('DPD (31-Mar-25)', 0.0)),
            final_stage=float(first_row.get('FINAL QTR STAGE (31-Mar-25)', 0.0)),
            data=convert_to_serializable(data),
            minio_file_key=minio_file_key,  # Add MinIO reference
        )
        create_staging_file(db, staging_file)

        # Clean up temporary files from worktemplates folder
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
            if os.path.exists(rawdata_path):
                os.remove(rawdata_path)
        except Exception as cleanup_error:
            # Log cleanup error but don't fail the execution
            print(f"Warning: Failed to clean up temporary files: {cleanup_error}")

        return {"rows": len(data), "minio_file_key": minio_file_key}

    except Exception as e:
        raise Exception(f"Staging execution error: {str(e)}")


def execute_ccf(execution_log_id: int, db: Session, file_paths: Dict[str, str]) -> Dict[str, Any]:
    """
    Execute CCF model using provided file paths.
    """
    try:
        rawdata_path = file_paths.get("rawdata", "worktemplates/Rawdata.xlsx")
        
        # Assume ccf.py main accepts path
        from ifrsmodel.CCF.ccf import main as run_ccf
        
        run_ccf(rawdata_path=rawdata_path)  # Hypothetical

        # Assume outputs to CCF_Output.xlsx
        out_path = "worktemplates/CCF_Output.xlsx"
        df = pd.read_excel(out_path)
        data = df.to_dict("records")

        # Upload output file to MinIO
        minio_file_key = minio_service.upload_file(
            out_path,
            "ccf",
            execution_log_id,
            f"ccf_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        ccf_file = CCFFile(
            execution_model_id=execution_log_id,
            data_name="CCF Results",  # Required field from CCFLog
            timestamp=datetime.now(timezone.utc),  # Required field from CCFLog
            data=convert_to_serializable(data),
            minio_file_key=minio_file_key,  # Add MinIO reference
        )
        create_ccf_file(db, ccf_file)

        # Clean up temporary files from worktemplates folder
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
            if os.path.exists(rawdata_path):
                os.remove(rawdata_path)
        except Exception as cleanup_error:
            # Log cleanup error but don't fail the execution
            print(f"Warning: Failed to clean up temporary files: {cleanup_error}")

        return {"rows": len(data), "minio_file_key": minio_file_key}

    except Exception as e:
        raise Exception(f"CCF execution error: {str(e)}")


def cancel_execution(celery_task_id: str):
    """Cancel a running Celery task"""
    from celery import Celery
    from api.core.config import settings
    
    celery_app = Celery(
        'ifrs9_tasks',
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND
    )
    celery_app.control.revoke(celery_task_id, terminate=True)

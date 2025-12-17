"""
Validation service for IFRS model input files.
Integrates file_validator.py into the model execution workflow.
"""

import tempfile
from typing import Dict, List, Optional

from api.core.logging import get_logger
from api.schema.validation_schema import (
    FileValidationResult,
    ValidationError,
    ValidationResult,
    ValidationSummary,
    MODEL_VALIDATION_CONFIGS
)

# Import validation classes from file_validator
from file_validator import (
    ValidateCCF,
    ValidateCollateral,
    ValidateEAD,
    ValidateFLIForecast,
    ValidateFLIHistorical,
    ValidatePD,
    ValidateScenarioWeight,
    ValidateStagingMultiSheet,
    ValidateWRITEOFF,
    ccf_columns,
    collateral_columns,
    ead_columns,
    EAD_COLUMN_ALIASES,
    fli_forecast_columns,
    fli_historical_columns,
    pd_columns,
    pd_write_off_columns,
    WRITEOFF_COLUMN_ALIASES,
    read_excel_with_auto_header,
    scenario_weight_columns,
)

logger = get_logger(__name__)


import json
import os

class ValidationService:
    """Service class for validating IFRS model input files"""

    def __init__(self):
        self.validation_results: List[FileValidationResult] = []
        # Load allowed sectors from JSON file
        sectors_path = os.path.join(os.path.dirname(__file__), '..', 'sectors.json')
        try:
            with open(sectors_path, 'r') as f:
                data = json.load(f)
                self.allowed_sectors = set(data.get("allowed_sectors", []))
        except Exception as e:
            logger.error(f"Failed to load sectors.json: {str(e)}")
            self.allowed_sectors = set()

    def validate_ead_file(
        self,
        file_content: bytes,
        filename: str = "EAD_Input"
    ) -> FileValidationResult:
        """Validate EAD input file"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                tmp_file.write(file_content)
                tmp_file.flush()

                df = read_excel_with_auto_header(
                    tmp_file.name,
                    expected_cols=ead_columns,
                    column_aliases=EAD_COLUMN_ALIASES,
                )

                validator = ValidateEAD(df, ead_columns)
                validator.validate()

                return FileValidationResult(
                    file_name=filename,
                    file_type="EAD",
                    is_valid=len(validator.error_list) == 0,
                    errors=[ValidationError(message=error) for error in validator.error_list],
                    total_errors=len(validator.error_list),
                    total_rows=len(df)
                )

        except Exception as e:
            logger.error(f"Error validating EAD file {filename}: {str(e)}")
            return FileValidationResult(
                file_name=filename,
                file_type="EAD",
                is_valid=False,
                errors=[ValidationError(message=f"File processing error: {str(e)}")],
                total_errors=1,
                total_rows=0
            )

    def validate_pd_file(
        self,
        file_content: bytes,
        filename: str = "PD_Input"
    ) -> FileValidationResult:
        """Validate PD input file"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                tmp_file.write(file_content)
                tmp_file.flush()

                # Try reading with header row 1 (second row) to skip first row with large number
                import pandas as pd
                try:
                    df = pd.read_excel(tmp_file.name, header=1)
                except Exception:
                    df = read_excel_with_auto_header(
                        tmp_file.name,
                        expected_cols=pd_columns
                    )

                # Validate 'Business sector' column values against allowed sectors
                invalid_sectors = []
                if 'Business sector' in df.columns:
                    sectors_in_file = set(df['Business sector'].dropna().unique())
                    invalid_sectors = [s for s in sectors_in_file if s not in self.allowed_sectors]
                else:
                    invalid_sectors = ["Missing 'Business sector' column"]

                validator = ValidatePD(df, pd_columns)
                validator.validate()

                # Combine errors from ValidatePD and sector validation
                combined_errors = validator.error_list.copy()
                if invalid_sectors:
                    combined_errors.append(f"Invalid sectors found: {', '.join(invalid_sectors)}")

                return FileValidationResult(
                    file_name=filename,
                    file_type="PD",
                    is_valid=len(combined_errors) == 0,
                    errors=[ValidationError(message=error) for error in combined_errors],
                    total_errors=len(combined_errors),
                    total_rows=len(df)
                )

        except Exception as e:
            logger.error(f"Error validating PD file {filename}: {str(e)}")
            return FileValidationResult(
                file_name=filename,
                file_type="PD",
                is_valid=False,
                errors=[ValidationError(message=f"File processing error: {str(e)}")],
                total_errors=1,
                total_rows=0
            )

    def validate_ccf_file(
        self,
        file_content: bytes,
        filename: str = "CCF_Input"
    ) -> FileValidationResult:
        """Validate CCF input file"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                tmp_file.write(file_content)
                tmp_file.flush()

                df = read_excel_with_auto_header(
                    tmp_file.name,
                    expected_cols=ccf_columns
                )

                validator = ValidateCCF(df, ccf_columns)
                validator.validate()

                return FileValidationResult(
                    file_name=filename,
                    file_type="CCF",
                    is_valid=len(validator.error_list) == 0,
                    errors=[ValidationError(message=error) for error in validator.error_list],
                    total_errors=len(validator.error_list),
                    total_rows=len(df)
                )

        except Exception as e:
            logger.error(f"Error validating CCF file {filename}: {str(e)}")
            return FileValidationResult(
                file_name=filename,
                file_type="CCF",
                is_valid=False,
                errors=[ValidationError(message=f"File processing error: {str(e)}")],
                total_errors=1,
                total_rows=0
            )

    def validate_staging_file(
        self,
        file_content: bytes,
        filename: str = "Staging_Input"
    ) -> FileValidationResult:
        """Validate Staging input file (multi-sheet M1-M6)"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                tmp_file.write(file_content)
                tmp_file.flush()

                multi_validator = ValidateStagingMultiSheet(tmp_file.name)
                all_errors = multi_validator.validate_all_sheets()

                return FileValidationResult(
                    file_name=filename,
                    file_type="STAGING",
                    is_valid=len(all_errors) == 0,
                    errors=[ValidationError(message=error) for error in all_errors],
                    total_errors=len(all_errors),
                    total_rows=0
                )

        except Exception as e:
            logger.error(f"Error validating Staging file {filename}: {str(e)}")
            return FileValidationResult(
                file_name=filename,
                file_type="STAGING",
                is_valid=False,
                errors=[ValidationError(message=f"File processing error: {str(e)}")],
                total_errors=1,
                total_rows=0
            )

    def validate_collateral_file(
        self,
        file_content: bytes,
        filename: str = "Collateral_Input"
    ) -> FileValidationResult:
        """Validate Collateral input file"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                tmp_file.write(file_content)
                tmp_file.flush()

                df = read_excel_with_auto_header(
                    tmp_file.name,
                    expected_cols=collateral_columns
                )

                validator = ValidateCollateral(df, collateral_columns)
                validator.validate()

                return FileValidationResult(
                    file_name=filename,
                    file_type="COLLATERAL",
                    is_valid=len(validator.error_list) == 0,
                    errors=[ValidationError(message=error) for error in validator.error_list],
                    total_errors=len(validator.error_list),
                    total_rows=len(df)
                )

        except Exception as e:
            logger.error(f"Error validating Collateral file {filename}: {str(e)}")
            return FileValidationResult(
                file_name=filename,
                file_type="COLLATERAL",
                is_valid=False,
                errors=[ValidationError(message=f"File processing error: {str(e)}")],
                total_errors=1,
                total_rows=0
            )



    def validate_write_off_file(
        self,
        file_content: bytes,
        filename: str = "WriteOff_Input"
    ) -> FileValidationResult:
        """Validate Write-off input file"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                tmp_file.write(file_content)
                tmp_file.flush()

                df = read_excel_with_auto_header(
                    tmp_file.name,
                    expected_cols=pd_write_off_columns,
                    column_aliases=WRITEOFF_COLUMN_ALIASES
                )

                validator = ValidateWRITEOFF(df, pd_write_off_columns)
                validator.validate()

                return FileValidationResult(
                    file_name=filename,
                    file_type="WRITE_OFF",
                    is_valid=len(validator.error_list) == 0,
                    errors=[ValidationError(message=error) for error in validator.error_list],
                    total_errors=len(validator.error_list),
                    total_rows=len(df)
                )

        except Exception as e:
            logger.error(f"Error validating Write-off file {filename}: {str(e)}")
            return FileValidationResult(
                file_name=filename,
                file_type="WRITE_OFF",
                is_valid=False,
                errors=[ValidationError(message=f"File processing error: {str(e)}")],
                total_errors=1,
                total_rows=0
            )

    def validate_fli_file(
        self,
        file_content: bytes,
        filename: str = "FLI_Input"
    ) -> FileValidationResult:
        """Validate FLI input file (multiple sheets)"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
                tmp_file.write(file_content)
                tmp_file.flush()

                all_errors = []

                # Validate FLI Historical Data
                try:
                    df_hist = read_excel_with_auto_header(
                        tmp_file.name,
                        sheet_name="FLI Historical Data",
                        expected_cols=fli_historical_columns
                    )
                    validator_hist = ValidateFLIHistorical(df_hist, fli_historical_columns)
                    validator_hist.validate()
                    all_errors.extend([f"Historical Data: {error}" for error in validator_hist.error_list])
                except Exception as e:
                    all_errors.append(f"Historical Data sheet error: {str(e)}")

                # Validate FLI Forecast Data
                try:
                    df_forecast = read_excel_with_auto_header(
                        tmp_file.name,
                        sheet_name="FLI Forecast Data",
                        expected_cols=fli_forecast_columns
                    )
                    validator_forecast = ValidateFLIForecast(df_forecast, fli_forecast_columns)
                    validator_forecast.validate()
                    all_errors.extend([f"Forecast Data: {error}" for error in validator_forecast.error_list])
                except Exception as e:
                    all_errors.append(f"Forecast Data sheet error: {str(e)}")

                # Validate Scenario Weight Data
                # FIXME: To be revisited
                # try:
                #     df_scenario = read_excel_with_auto_header(
                #         tmp_file.name,
                #         sheet_name="Scenario Weight Historical Data",
                #         expected_cols=scenario_weight_columns
                #     )
                #     validator_scenario = ValidateScenarioWeight(df_scenario, scenario_weight_columns)
                #     validator_scenario.validate()
                #     all_errors.extend([f"Scenario Weight: {error}" for error in validator_scenario.error_list])
                # except Exception as e:
                #     all_errors.append(f"Scenario Weight sheet error: {str(e)}")

                return FileValidationResult(
                    file_name=filename,
                    file_type="FLI",
                    is_valid=len(all_errors) == 0,
                    errors=[ValidationError(message=error) for error in all_errors],
                    total_errors=len(all_errors),
                    total_rows=0
                )

        except Exception as e:
            logger.error(f"Error validating FLI file {filename}: {str(e)}")
            return FileValidationResult(
                file_name=filename,
                file_type="FLI",
                is_valid=False,
                errors=[ValidationError(message=f"File processing error: {str(e)}")],
                total_errors=1,
                total_rows=0
            )

    def validate_model_files(
        self,
        model_type: str,
        files: Dict[str, bytes],
        filenames: Optional[Dict[str, str]] = None
    ) -> ValidationResult:
        """
        Validate all files for a specific model type

        Args:
            model_type: Type of model (e.g., 'ead_model', 'ccf_model')
            files: Dictionary mapping file types to file content
            filenames: Optional dictionary mapping file types to filenames

        Returns:
            ValidationResult with summary and individual file results
        """

        if model_type not in MODEL_VALIDATION_CONFIGS:
            raise ValueError(f"Unknown model type: {model_type}")

        config = MODEL_VALIDATION_CONFIGS[model_type]
        file_results = []

        # Validate each required file
        for file_type in config.required_files:
            if file_type not in files:
                # Missing required file
                file_results.append(FileValidationResult(
                    file_name=filenames.get(file_type, f"{file_type}_missing") if filenames else f"{file_type}_missing",
                    file_type=file_type,
                    is_valid=False,
                    errors=[ValidationError(message=f"Required file {file_type} is missing")],
                    total_errors=1,
                    total_rows=0
                ))
                continue

            # Validate the file based on its type
            filename = filenames.get(file_type, f"{file_type}_input") if filenames else f"{file_type}_input"

            if file_type == "EAD":
                result = self.validate_ead_file(files[file_type], filename)
            elif file_type == "CCF":
                result = self.validate_ccf_file(files[file_type], filename)
            elif file_type == "STAGING":
                result = self.validate_staging_file(files[file_type], filename)
            elif file_type == "COLLATERAL":
                result = self.validate_collateral_file(files[file_type], filename)
            elif file_type == "PD":
                result = self.validate_pd_file(files[file_type], filename)
            elif file_type == "WRITE_OFF":
                result = self.validate_write_off_file(files[file_type], filename)
            elif file_type == "FLI":
                result = self.validate_fli_file(files[file_type], filename)
            else:
                result = FileValidationResult(
                    file_name=filename,
                    file_type=file_type,
                    is_valid=False,
                    errors=[ValidationError(message=f"Unknown file type: {file_type}")],
                    total_errors=1,
                    total_rows=0
                )

            file_results.append(result)

        # Calculate summary
        total_files = len(file_results)
        valid_files = sum(1 for result in file_results if result.is_valid)
        invalid_files = total_files - valid_files
        total_errors = sum(result.total_errors for result in file_results)
        total_warnings = sum(result.total_warnings for result in file_results)
        validation_passed = invalid_files == 0 and total_errors == 0

        summary = ValidationSummary(
            total_files=total_files,
            valid_files=valid_files,
            invalid_files=invalid_files,
            total_errors=total_errors,
            total_warnings=total_warnings,
            validation_passed=validation_passed
        )

        return ValidationResult(
            summary=summary,
            file_results=file_results,
            model_type=model_type
        )


# Singleton instance
validation_service = ValidationService()

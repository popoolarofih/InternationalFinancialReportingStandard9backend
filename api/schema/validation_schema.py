"""
Schema definitions for validation responses and error reporting.
"""

from typing import List, Optional, Dict
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class ValidationSeverity(str, Enum):
    """Severity levels for validation errors"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationError(BaseModel):
    """Individual validation error"""
    message: str = Field(..., description="Error message")
    severity: ValidationSeverity = Field(default=ValidationSeverity.ERROR, description="Error severity")
    column: Optional[str] = Field(None, description="Column name if applicable")
    sheet: Optional[str] = Field(None, description="Sheet name if applicable")
    excel_rows: Optional[List[int]] = Field(None, description="Excel row numbers with errors")
    error_count: Optional[int] = Field(None, description="Number of rows with this error")


class FileValidationResult(BaseModel):
    """Validation result for a single file"""
    file_name: str = Field(..., description="Name of the validated file")
    file_type: str = Field(..., description="Type of file (EAD, CCF, STAGING, etc.)")
    is_valid: bool = Field(..., description="Whether the file passed validation")
    errors: List[ValidationError] = Field(default_factory=list, description="List of validation errors")
    warnings: List[ValidationError] = Field(default_factory=list, description="List of validation warnings")
    total_errors: int = Field(default=0, description="Total number of errors")
    total_warnings: int = Field(default=0, description="Total number of warnings")
    total_rows: int = Field(default=0, description="Total number of data rows processed")
    validation_timestamp: datetime = Field(default_factory=datetime.now, description="When validation was performed")


class ValidationSummary(BaseModel):
    """Summary of validation results across multiple files"""
    total_files: int = Field(..., description="Total number of files validated")
    valid_files: int = Field(..., description="Number of files that passed validation")
    invalid_files: int = Field(..., description="Number of files that failed validation")
    total_errors: int = Field(..., description="Total errors across all files")
    total_warnings: int = Field(..., description="Total warnings across all files")
    validation_passed: bool = Field(..., description="Whether overall validation passed")
    validation_timestamp: datetime = Field(default_factory=datetime.now, description="When validation was performed")


class ValidationResult(BaseModel):
    """Complete validation result for model execution"""
    summary: ValidationSummary = Field(..., description="Validation summary")
    file_results: List[FileValidationResult] = Field(..., description="Individual file validation results")
    model_type: str = Field(..., description="Type of model being validated")
    # execution_id: Optional[str] = Field(None, description="Model execution ID if available")

    @property
    def can_proceed(self) -> bool:
        """Whether model execution can proceed based on validation results"""
        return self.summary.validation_passed

    @property
    def error_summary(self) -> Dict[str, int]:
        """Summary of errors by file type"""
        error_summary = {}
        for file_result in self.file_results:
            error_summary[file_result.file_type] = file_result.total_errors
        return error_summary

    model_config = ConfigDict(protected_namespaces=())


class ModelValidationConfig(BaseModel):
    """Configuration for model validation"""
    model_type: str = Field(..., description="Type of model")
    required_files: List[str] = Field(..., description="List of required file types")
    optional_files: List[str] = Field(default_factory=list, description="List of optional file types")
    strict_validation: bool = Field(default=True, description="Whether to use strict validation")
    allow_warnings: bool = Field(default=True, description="Whether to allow warnings")

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


# Model-specific validation configurations
MODEL_VALIDATION_CONFIGS = {
    "ead_model": ModelValidationConfig(
        model_type="ead_model",
        required_files=["EAD", "STAGING", "CCF"],
        strict_validation=True
    ),
    "ccf_model": ModelValidationConfig(
        model_type="ccf_model",
        required_files=["CCF"],
        strict_validation=True
    ),
    "staging_model": ModelValidationConfig(
        model_type="staging_model",
        required_files=["STAGING"],
        strict_validation=True
    ),
    "pd_model": ModelValidationConfig(
        model_type="pd_model",
        required_files=["PD", "WRITE_OFF"],
        strict_validation=True
    ),
    "ecl_model": ModelValidationConfig(
        model_type="ecl_model",
        required_files=["EAD", "WRITE_OFF", "PD", "COLLATERAL", "STAGING"],
        strict_validation=True
    ),
    "lgd_model": ModelValidationConfig(
        model_type="lgd_model",
        required_files=["EAD", "WRITE_OFF", "PD", "COLLATERAL", "STAGING", "CCF"],
        strict_validation=True
    ),
    "fli_model": ModelValidationConfig(
        model_type="fli_model",
        required_files=["FLI"],
        strict_validation=True
    )
}


class ValidationException(Exception):
    """Custom exception for validation errors"""

    def __init__(self, validation_result: ValidationResult, message: str = None):
        self.validation_result = validation_result
        self.message = message or f"Validation failed for {validation_result.model_type}"
        super().__init__(self.message)


class ValidationResponse(BaseModel):
    """API response for validation endpoints"""
    success: bool = Field(..., description="Whether the validation was successful")
    message: str = Field(..., description="Response message")
    validation_result: Optional[ValidationResult] = Field(None, description="Detailed validation results")
    can_proceed: bool = Field(..., description="Whether model execution can proceed")

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

"""
Integration helpers for validation service with existing model execution workflow.
"""

from typing import Dict, Optional
from fastapi import HTTPException, status
from api.core.logging import get_logger
from api.services.validation_service import validation_service
from api.schema.validation_schema import ValidationResult

logger = get_logger(__name__)


def validate_ead_model_files(
    ead_file: bytes,
    staging_file: bytes,
    ccf_file: bytes,
    filenames: Optional[Dict[str, str]] = None
) -> ValidationResult:
    """Validate files for EAD model execution"""
    files = {
        "EAD": ead_file,
        "STAGING": staging_file,
        "CCF": ccf_file
    }

    return validation_service.validate_model_files(
        model_type="ead_model",
        files=files,
        filenames=filenames
    )


def validate_ccf_model_files(
    ccf_file: bytes,
    filenames: Optional[Dict[str, str]] = None
) -> ValidationResult:
    """Validate files for CCF model execution"""
    files = {
        "CCF": ccf_file
    }

    return validation_service.validate_model_files(
        model_type="ccf_model",
        files=files,
        filenames=filenames
    )


def validate_staging_model_files(
    staging_file: bytes,
    filenames: Optional[Dict[str, str]] = None
) -> ValidationResult:
    """Validate files for Staging model execution"""
    files = {
        "STAGING": staging_file
    }

    return validation_service.validate_model_files(
        model_type="staging_model",
        files=files,
        filenames=filenames
    )


def validate_pd_model_files(
    pd_file: bytes,
    write_off_file: bytes,
    filenames: Optional[Dict[str, str]] = None
) -> ValidationResult:
    """Validate files for PD model execution"""
    files = {
        "PD": pd_file,
        "WRITE_OFF": write_off_file
    }

    return validation_service.validate_model_files(
        model_type="pd_model",
        files=files,
        filenames=filenames
    )


def validate_ecl_model_files(
    ead_file: bytes,
    write_off_file: bytes,
    pd_file: bytes,
    collateral_file: bytes,
    staging_file: bytes,
    filenames: Optional[Dict[str, str]] = None
) -> ValidationResult:
    """Validate files for ECL model execution"""
    files = {
        "EAD": ead_file,
        "WRITE_OFF": write_off_file,
        "PD": pd_file,
        "COLLATERAL": collateral_file,
        "STAGING": staging_file
    }

    return validation_service.validate_model_files(
        model_type="ecl_model",
        files=files,
        filenames=filenames
    )


def validate_lgd_model_files(
    ead_file: bytes,
    write_off_file: bytes,
    pd_file: bytes,
    collateral_file: bytes,
    staging_file: bytes,
    ccf_file: bytes,
    filenames: Optional[Dict[str, str]] = None
) -> ValidationResult:
    """Validate files for LGD model execution"""
    files = {
        "EAD": ead_file,
        "WRITE_OFF": write_off_file,
        "PD": pd_file,
        "COLLATERAL": collateral_file,
        "STAGING": staging_file,
        "CCF": ccf_file
    }

    return validation_service.validate_model_files(
        model_type="lgd_model",
        files=files,
        filenames=filenames
    )


def validate_fli_model_files(
    fli_file: bytes,
    filenames: Optional[Dict[str, str]] = None
) -> ValidationResult:
    """Validate files for FLI model execution"""
    files = {
        "FLI": fli_file
    }

    return validation_service.validate_model_files(
        model_type="fli_model",
        files=files,
        filenames=filenames
    )


def validate_and_proceed(validation_result: ValidationResult) -> None:
    """
    Check validation result and raise HTTPException if validation failed

    Args:
        validation_result: Result from validation

    Raises:
        HTTPException: If validation failed with detailed error information
    """
    if not validation_result.can_proceed:
        error_details = []

        for file_result in validation_result.file_results:
            if not file_result.is_valid:
                file_errors = [error.message for error in file_result.errors]
                error_details.append(f"{file_result.file_type}: {', '.join(file_errors[:3])}")
                if len(file_result.errors) > 3:
                    error_details.append(f"... and {len(file_result.errors) - 3} more errors")

        error_message = f"File validation failed for {validation_result.model_type}. " + \
                       f"Errors: {'; '.join(error_details[:5])}"

        if len(error_details) > 5:
            error_message += f" ... and {len(error_details) - 5} more file errors"

        logger.error(f"Validation failed: {error_message}")

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "File validation failed",
                "validation_summary": {
                    "total_files": validation_result.summary.total_files,
                    "valid_files": validation_result.summary.valid_files,
                    "invalid_files": validation_result.summary.invalid_files,
                    "total_errors": validation_result.summary.total_errors,
                    "error_summary": validation_result.error_summary
                },
                "errors": error_details[:10]
            }
        )

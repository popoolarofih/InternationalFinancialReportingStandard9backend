# api/routers/model.py
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime
import os
import uuid
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo

from api.database import get_db
from api.core.config import settings
from api.utils.deps import current_user
from api.models.user import (
    ModelExecutionLog,
    ExecutionModelType,
    ModelExecutionStatus,
    PDFile,
    LGDFile,
    EADFile,
    ECLFile,
    FLIFile,
    StagingFile,
    CCFFile,
    ActivityLog,
    User,  # <-- added User import
)
from api.services.model_execution import (
    execute_pd,
    execute_lgd,
    execute_slgd,
    execute_ead,
    execute_ecl,
    execute_fli,
    execute_staging,
    execute_ccf,
)
from api.schema.models_schema import ModelExecutionResponse
from api.utils.minio_service import minio_service
from api.services.validation_service import validation_service
from fastapi.responses import StreamingResponse
import io

router = APIRouter(prefix="/models", tags=["models"])

# Helper function to save uploaded file
def save_uploaded_file(upload: UploadFile, base_path: str, prefix: str = "") -> str:
    file_id = str(uuid.uuid4())
    file_extension = Path(upload.filename).suffix
    filename = f"{prefix}{file_id}{file_extension}" if prefix else f"{file_id}{file_extension}"
    filepath = os.path.join(base_path, filename)
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
    return filepath

@router.post(
    "/pd",
    response_model=ModelExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute PD Model"
)
async def trigger_pd_execution(
    pd_input: UploadFile = File(..., description="PD Input Excel file (pd_input.xlsx)"),
    reporting_date: str = Form(..., description="Reporting date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
) -> Dict[str, Any]:
    # Validate PD file before saving and executing
    content = await pd_input.read()
    validation_result = validation_service.validate_pd_file(content, pd_input.filename)
    if not validation_result.is_valid:
        error_messages = [error.message for error in validation_result.errors]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "PD file validation failed", "errors": error_messages}
        )
    # Reset file pointer after reading
    await pd_input.seek(0)

    log = ModelExecutionLog(
        data_name=f"PD Model Execution - {reporting_date}",
        user_id=current_user.id,
        executed_model_type=ExecutionModelType.PD,
        execution_status=ModelExecutionStatus.RUNNING,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # Create activity log
    activity = ActivityLog(execution_model_id=log.id, user_id=current_user.id)
    db.add(activity)
    db.commit()

    try:
        # Save uploaded file
        work_dir = settings.WORKTEMPLATES_PATH
        pd_input_path = save_uploaded_file(pd_input, work_dir, "pd_input_")

        result = execute_pd(log.id, db, {"pd_input": pd_input_path}, reporting_date)
        log.execution_status = ModelExecutionStatus.COMPLETED
        db.commit()
        return {
            "log_id": log.id,
            "status": "completed",
            "model_type": "pd",
            "data_name": log.data_name,
            "message": "PD model executed successfully",
            **result,
        }
    except Exception as e:
        db.rollback()
        log.execution_status = ModelExecutionStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PD model execution failed: {str(e)}",
        )

@router.post(
    "/lgd",
    response_model=ModelExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute LGD Models"
)
async def trigger_lgd_execution(
    lgd_input: UploadFile = File(..., description="LGD Input Excel file (LGD.xlsx)"),
    secured_lgd_input: UploadFile = File(..., description="Secured LGD Input Excel file (SecuredLGD.xlsx)"),
    reporting_date: str = Form(..., description="Reporting date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
) -> Dict[str, Any]:
    log = ModelExecutionLog(
        data_name="LGD and SLGD Model Execution",
        user_id=current_user.id,
        executed_model_type=ExecutionModelType.LGD,
        execution_status=ModelExecutionStatus.RUNNING,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # Create activity log
    activity = ActivityLog(execution_model_id=log.id, user_id=current_user.id)
    db.add(activity)
    db.commit()

    try:
        # Save uploaded files
        work_dir = settings.WORKTEMPLATES_PATH
        lgd_path = save_uploaded_file(lgd_input, work_dir, "lgd_input_")
        slgd_path = save_uploaded_file(secured_lgd_input, work_dir, "secured_lgd_")

        # Execute LGD
        lgd_result = execute_lgd(log.id, db, {"lgd_input": lgd_path})

        # Execute SLGD
        slgd_result = execute_slgd(log.id, db, {"secured_lgd": slgd_path})

        log.execution_status = ModelExecutionStatus.COMPLETED
        db.commit()
        return {
            "log_id": log.id,
            "status": "completed",
            "model_type": "lgd",
            "data_name": log.data_name,
            "message": "LGD modelexecuted successfully",
            "lgd_result": lgd_result,
            "slgd_result": slgd_result,
        }
    except Exception as e:
        db.rollback()
        log.execution_status = ModelExecutionStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LGD and SLGD model execution failed: {str(e)}",
        )

@router.post(
    "/ead",
    response_model=ModelExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute EAD Model"
)
async def trigger_ead_execution(
    rawdata: UploadFile = File(..., description="Raw Data Excel file (Rawdata.xlsx)"),
    reporting_date: str = Form(..., description="Reporting date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
) -> Dict[str, Any]:
    log = ModelExecutionLog(
        data_name="EAD Model Execution",
        user_id=current_user.id,
        executed_model_type=ExecutionModelType.EAD,
        execution_status=ModelExecutionStatus.RUNNING,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # Create activity log
    activity = ActivityLog(execution_model_id=log.id, user_id=current_user.id)
    db.add(activity)
    db.commit()

    try:
        # Save uploaded file
        work_dir = settings.WORKTEMPLATES_PATH
        rawdata_path = save_uploaded_file(rawdata, work_dir, "rawdata_")
        
        result = execute_ead(log.id, db, {"rawdata": rawdata_path})
        log.execution_status = ModelExecutionStatus.COMPLETED
        db.commit()
        return {
            "log_id": log.id,
            "status": "completed",
            "model_type": "ead",
            "data_name": log.data_name,
            "message": "EAD model executed successfully",
            **result,
        }
    except Exception as e:
        log.execution_status = ModelExecutionStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"EAD model execution failed: {str(e)}",
        )

@router.post(
    "/ecl",
    response_model=ModelExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute ECL Model"
)
async def trigger_ecl_execution(
    # ECL typically uses outputs from previous models, but allow Rawdata if needed
    rawdata: Optional[UploadFile] = File(None, description="Raw Data Excel file (Rawdata.xlsx) - optional if already available"),
    reporting_date: str = Form(..., description="Reporting date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
) -> Dict[str, Any]:
    log = ModelExecutionLog(
        data_name="ECL Model Execution",
        user_id=current_user.id,
        executed_model_type=ExecutionModelType.ECL,
        execution_status=ModelExecutionStatus.RUNNING,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # Create activity log
    activity = ActivityLog(execution_model_id=log.id, user_id=current_user.id)
    db.add(activity)
    db.commit()

    try:
        file_paths = {}
        if rawdata:
            work_dir = settings.WORKTEMPLATES_PATH
            rawdata_path = save_uploaded_file(rawdata, work_dir, "rawdata_ecl_")
            file_paths["rawdata"] = rawdata_path
        
        result = execute_ecl(log.id, db, file_paths, reporting_date)
        log.execution_status = ModelExecutionStatus.COMPLETED
        db.commit()
        return {
            "log_id": log.id,
            "status": "completed",
            "model_type": "ecl",
            "data_name": log.data_name,
            "message": "ECL model executed successfully",
            **result,
        }
    except Exception as e:
        log.execution_status = ModelExecutionStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ECL model execution failed: {str(e)}",
        )

@router.post(
    "/fli",
    response_model=ModelExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute FLI Model"
)
async def trigger_fli_execution(
    fli_input: UploadFile = File(..., description="FLI Input Excel file with required sheets: 'FLI Historical Data', 'FLI Forecast Data', 'Scenario Weight Historical Data'"),
    execution_data: Optional[str] = Form(None, description="The date of execution YYYY-MM-DD 2020-03-31"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
) -> Dict[str, Any]:
    log = ModelExecutionLog(
        data_name="FLI Model Execution",
        user_id=current_user.id,
        executed_model_type=ExecutionModelType.FLI,
        execution_status=ModelExecutionStatus.RUNNING,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # Create activity log
    activity = ActivityLog(execution_model_id=log.id, user_id=current_user.id)
    db.add(activity)
    db.commit()

    try:
        file_paths = {}
        work_dir = settings.WORKTEMPLATES_PATH
        fli_path = save_uploaded_file(fli_input, work_dir, "fli_input_")
        file_paths["fli_input"] = fli_path
        
        result = execute_fli(log.id, db, file_paths)
        log.execution_status = ModelExecutionStatus.COMPLETED
        db.commit()
        return {
            "log_id": log.id,
            "status": "completed",
            "model_type": "fli",
            "data_name": log.data_name,
            "message": "FLI model executed successfully",
            **result,
        }
    except Exception as e:
        log.execution_status = ModelExecutionStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"FLI model execution failed: {str(e)}",
        )

@router.post(
    "/staging",
    response_model=ModelExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute Staging Model"
)
async def trigger_staging_execution(
    rawdata: UploadFile = File(..., description="Raw Data Excel file for Staging"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
) -> Dict[str, Any]:
    log = ModelExecutionLog(
        data_name="Staging Model Execution",
        user_id=current_user.id,
        executed_model_type=ExecutionModelType.STAGING,
        execution_status=ModelExecutionStatus.RUNNING,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # Create activity log
    activity = ActivityLog(execution_model_id=log.id, user_id=current_user.id)
    db.add(activity)
    db.commit()

    try:
        # Save uploaded file
        work_dir = settings.WORKTEMPLATES_PATH
        rawdata_path = save_uploaded_file(rawdata, work_dir, "rawdata_staging_")
        
        result = execute_staging(log.id, db, {"rawdata": rawdata_path})
        log.execution_status = ModelExecutionStatus.COMPLETED
        db.commit()
        return {
            "log_id": log.id,
            "status": "completed",
            "model_type": "staging",
            "data_name": log.data_name,
            "message": "Staging model executed successfully",
            **result,
        }
    except Exception as e:
        log.execution_status = ModelExecutionStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Staging model execution failed: {str(e)}",
        )

@router.post(
    "/ccf",
    response_model=ModelExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute CCF Model"
)
async def trigger_ccf_execution(
    rawdata: UploadFile = File(..., description="Raw Data Excel file for CCF"),
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
) -> Dict[str, Any]:
    log = ModelExecutionLog(
        data_name="CCF Model Execution",
        user_id=current_user.id,
        executed_model_type=ExecutionModelType.CCF,
        execution_status=ModelExecutionStatus.RUNNING,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # Create activity log
    activity = ActivityLog(execution_model_id=log.id, user_id=current_user.id)
    db.add(activity)
    db.commit()

    try:
        # Save uploaded file
        work_dir = settings.WORKTEMPLATES_PATH
        rawdata_path = save_uploaded_file(rawdata, work_dir, "rawdata_ccf_")
        
        result = execute_ccf(log.id, db, {"rawdata": rawdata_path})
        log.execution_status = ModelExecutionStatus.COMPLETED
        db.commit()
        return {
            "log_id": log.id,
            "status": "completed",
            "model_type": "ccf",
            "data_name": log.data_name,
            "message": "CCF model executed successfully",
            **result,
        }
    except Exception as e:
        log.execution_status = ModelExecutionStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"CCF model execution failed: {str(e)}",
        )

@router.get(
    "/{model_execution_id}",
    summary="Get Response - Download report of an executed model"
)
async def get_model_response(
    model_execution_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    """Download report of an executed model. If no model_execution_id provided, returns Latest model executed"""
    if model_execution_id:
        log = (
            db.query(ModelExecutionLog)
            .filter(ModelExecutionLog.id == model_execution_id, ModelExecutionLog.user_id == current_user.id)
            .first()
        )
    else:
        # Get latest
        log = (
            db.query(ModelExecutionLog)
            .filter(ModelExecutionLog.user_id == current_user.id)
            .order_by(ModelExecutionLog.timestamp.desc())
            .first()
        )
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Execution log not found"
        )

    # Find the associated file based on model type
    file_record = None
    if log.executed_model_type.value == "pd":
        file_record = db.query(PDFile).filter(PDFile.execution_model_id == log.id).first()
    elif log.executed_model_type.value == "lgd":
        file_record = db.query(LGDFile).filter(LGDFile.execution_model_id == log.id).first()
    elif log.executed_model_type.value == "ead":
        file_record = db.query(EADFile).filter(EADFile.execution_model_id == log.id).first()
    elif log.executed_model_type.value == "ecl":
        file_record = db.query(ECLFile).filter(ECLFile.execution_model_id == log.id).first()
    elif log.executed_model_type.value == "fli":
        file_record = db.query(FLIFile).filter(FLIFile.execution_model_id == log.id).first()
    elif log.executed_model_type.value == "staging":
        file_record = db.query(StagingFile).filter(StagingFile.execution_model_id == log.id).first()
    elif log.executed_model_type.value == "ccf":
        file_record = db.query(CCFFile).filter(CCFFile.execution_model_id == log.id).first()

    if not file_record or not file_record.minio_file_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output file not found or not stored in MinIO"
        )

    try:
        # Use main bucket for all model types
        bucket_name = settings.MINIO_BUCKET

        # Always download and stream the file directly
        work_dir = settings.WORKTEMPLATES_PATH
        os.makedirs(work_dir, exist_ok=True)
        temp_path = os.path.join(work_dir, f"temp_download_{log.id}.xlsx")
        if minio_service.download_file(file_record.minio_file_key, temp_path, bucket_name=bucket_name):
            return StreamingResponse(
                io.FileIO(temp_path, 'rb'),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={file_record.minio_file_key.split('/')[-1]}"}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to download file from storage"
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving file: {str(e)}"
        )


@router.delete(
    "/{model_execution_id}/cancel",
    summary="Cancel Model Execution"
)
async def cancel_model_execution(
    model_execution_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    """Cancel/terminate a running model execution. This uses Celery revoke under the hood."""
    log = (
        db.query(ModelExecutionLog)
        .filter(ModelExecutionLog.id == model_execution_id, ModelExecutionLog.user_id == current_user.id)
        .first()
    )
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Execution log not found"
        )
    if log.execution_status != ModelExecutionStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Execution is not running"
        )
    # Cancel using Celery
    from api.services.model_execution import cancel_execution
    cancel_execution(log.celery_task_id)
    log.execution_status = ModelExecutionStatus.CANCELLED
    db.commit()
    return {"message": "Execution cancelled"}

@router.get(
    "/{model_execution_id}/email",
    summary="Send Model Output Via Email"
)
async def send_model_output_email(
    model_execution_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    """Send to email report of an executed model. If no model_execution_id provided, returns Latest model executed"""
    if model_execution_id:
        log = (
            db.query(ModelExecutionLog)
            .filter(ModelExecutionLog.id == model_execution_id, ModelExecutionLog.user_id == current_user.id)
            .first()
        )
    else:
        log = (
            db.query(ModelExecutionLog)
            .filter(ModelExecutionLog.user_id == current_user.id)
            .order_by(ModelExecutionLog.timestamp.desc())
            .first()
        )
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Execution log not found"
        )
    # Send email
    from api.services.email import send_model_report_email
    try:
        await send_model_report_email(current_user.email, log.id, db)
        return {"message": "Email sent"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {str(e)}"
        )

@router.get(
    "/",
    summary="Get Responses - Returns a paginated response of model execution logs"
)
async def get_model_executions(
    page: int = 1,
    page_size: int = 10,
    model_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    """Returns a paginated response of model execution logs"""
    from api.schema.models_schema import PaginatedResponse, ModelExecutionLogSchema
    query = db.query(ModelExecutionLog).filter(ModelExecutionLog.user_id == current_user.id)
    if model_type:
        # Normalize model_type to lowercase and handle SLGD as LGD
        normalized_model_type = model_type.lower()
        if normalized_model_type == "slgd":
            normalized_model_type = "lgd"
        query = query.filter(ModelExecutionLog.executed_model_type == normalized_model_type)
    logs = (
        query
        .order_by(ModelExecutionLog.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    total_query = db.query(ModelExecutionLog).filter(ModelExecutionLog.user_id == current_user.id)
    if model_type:
        # Normalize model_type to lowercase and handle SLGD as LGD
        normalized_model_type = model_type.lower()
        if normalized_model_type == "slgd":
            normalized_model_type = "lgd"
        total_query = total_query.filter(ModelExecutionLog.executed_model_type == normalized_model_type)
    total = total_query.count()

    # Build items manually to include user_name, user_email and execution_model_type properly
    items = []
    for log in logs:
        # fetch user record (may be None)
        user = db.query(User).filter(User.id == log.user_id).first()
        user_name = None
        if user:
            # prefer a combined name if first/last exist, fall back to username or email
            name_parts = []
            if getattr(user, "first_name", None):
                name_parts.append(user.first_name)
            if getattr(user, "last_name", None):
                name_parts.append(user.last_name)
            if name_parts:
                user_name = " ".join(name_parts)
            else:
                user_name = getattr(user, "username", None) or getattr(user, "email", None)

        user_email = getattr(user, "email", None) if user else None

        # execution status and model type may be Enum; handle safely
        execution_status = getattr(log.execution_status, "value", log.execution_status)
        execution_model_type = getattr(log.executed_model_type, "value", log.executed_model_type)

        # Convert timestamp to WAT
        wat_timezone = ZoneInfo("Africa/Lagos")
        timestamp_wat = log.timestamp.astimezone(wat_timezone)

        # Determine download_status
        download_status = "pending"
        if execution_status == "Completed":
            # Check if associated file exists in MinIO
            file_record = None
            if execution_model_type == "pd":
                file_record = db.query(PDFile).filter(PDFile.execution_model_id == log.id).first()
            elif execution_model_type == "lgd":
                file_record = db.query(LGDFile).filter(LGDFile.execution_model_id == log.id).first()
            elif execution_model_type == "ead":
                file_record = db.query(EADFile).filter(EADFile.execution_model_id == log.id).first()
            elif execution_model_type == "ecl":
                file_record = db.query(ECLFile).filter(ECLFile.execution_model_id == log.id).first()
            elif execution_model_type == "fli":
                file_record = db.query(FLIFile).filter(FLIFile.execution_model_id == log.id).first()
            elif execution_model_type == "staging":
                file_record = db.query(StagingFile).filter(StagingFile.execution_model_id == log.id).first()
            elif execution_model_type == "ccf":
                file_record = db.query(CCFFile).filter(CCFFile.execution_model_id == log.id).first()

            if file_record and file_record.minio_file_key:
                download_status = "Ready"
            else:
                download_status = "pending"
        elif execution_status in ["Failed", "Cancelled"]:
            download_status = "failed"

        items.append({
            "id": log.id,
            "data_name": log.data_name,
            "timestamp": timestamp_wat.isoformat(),
            "report_exported": getattr(log, "report_exported", False),
            "execution_status": execution_status,
            "user_name": user_name,
            "user_email": user_email,
            "execution_model_type": execution_model_type,
            "download_status": download_status,
        })

    return PaginatedResponse(items=items, total=total, page=page, size=page_size, pages=(total + page_size - 1) // page_size)


@router.get(
    "/{execution_id}/status",
    summary="Get Model Execution Status"
)
async def get_model_execution_status(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    """Get the status of a specific model execution."""
    log = (
        db.query(ModelExecutionLog)
        .filter(ModelExecutionLog.id == execution_id, ModelExecutionLog.user_id == current_user.id)
        .first()
    )
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Execution log not found"
        )

    # Convert timestamp to WAT
    wat_timezone = ZoneInfo("Africa/Lagos")
    timestamp_wat = log.timestamp.astimezone(wat_timezone)

    # Check if model is ready for download
    download_ready = False
    if log.execution_status.value == "Completed":
        # Find the associated file based on model type
        file_record = None
        if log.executed_model_type.value == "pd":
            file_record = db.query(PDFile).filter(PDFile.execution_model_id == log.id).first()
        elif log.executed_model_type.value == "lgd":
            file_record = db.query(LGDFile).filter(LGDFile.execution_model_id == log.id).first()
        elif log.executed_model_type.value == "ead":
            file_record = db.query(EADFile).filter(EADFile.execution_model_id == log.id).first()
        elif log.executed_model_type.value == "ecl":
            file_record = db.query(ECLFile).filter(ECLFile.execution_model_id == log.id).first()
        elif log.executed_model_type.value == "fli":
            file_record = db.query(FLIFile).filter(FLIFile.execution_model_id == log.id).first()
        elif log.executed_model_type.value == "staging":
            file_record = db.query(StagingFile).filter(StagingFile.execution_model_id == log.id).first()
        elif log.executed_model_type.value == "ccf":
            file_record = db.query(CCFFile).filter(CCFFile.execution_model_id == log.id).first()

        if file_record and file_record.minio_file_key:
            download_ready = True

    return {
        "execution_id": log.id,
        "model_type": log.executed_model_type.value,
        "status": log.execution_status.value,
        "data_name": log.data_name,
        "timestamp": timestamp_wat.isoformat(),
        "download_ready": download_ready,
        "celery_task_id": log.celery_task_id,
        "celery_task_name": log.celery_task_name,
    }


@router.get(
    "/files/{log_id}",
    summary="List Files for Model Execution"
)
async def list_model_files(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    """List all files associated with a model execution."""
    # Get the execution log
    log = (
        db.query(ModelExecutionLog)
        .filter(ModelExecutionLog.id == log_id, ModelExecutionLog.user_id == current_user.id)
        .first()
    )
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Execution log not found"
        )

    try:
        # Use main bucket for all model types
        bucket_name = settings.MINIO_BUCKET

        # List files in MinIO for this execution
        files = minio_service.list_files(log.executed_model_type.value, log_id, bucket_name=bucket_name)

        return {
            "execution_id": log_id,
            "model_type": log.executed_model_type.value,
            "files": files
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing files: {str(e)}"
        )





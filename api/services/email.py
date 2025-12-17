from typing import Optional
from fastapi import HTTPException, status
from jinja2 import Template
from sqlalchemy.orm import Session
from datetime import datetime
from api.models import EmailRecipient, User
from api.utils.send_mail import send_email
from api.core.logging import get_logger
from api.core.config import settings

logger = get_logger(__name__)


async def send_report_to_email_recipients(
    dashboard_summary,
    execution_date,
    db: Session,  # = Depends(get_db),
    file_bytes: Optional[bytes] = None,
    filename: Optional[str] = None,
    current_user_id: str = None,
):
    # Retrieve all email recipients
    recipients = db.query(EmailRecipient).all() or []
    current_user = db.query(User).filter_by(id=current_user_id).first()
    recipients.append(EmailRecipient(email=current_user.email, name=current_user.name))

    if not recipients:
        raise HTTPException(status_code=404, detail="No email recipients found")

    if not dashboard_summary:
        raise HTTPException(status_code=404, detail="No dashboard summary found")

    execution_date_dt = datetime.strptime(execution_date, "%Y-%m-%d")
    report_data = dashboard_summary
    report_data.update(
        {
            "execution_date": execution_date_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "total_ead": f"{dashboard_summary['total_ead'] / 1_000_000_000:.2f}",
            "total_ecl": f"{dashboard_summary['total_ecl'] / 1_000_000_000:.2f}",
            "performing_loan_percentage": f"{dashboard_summary['performing_loan_perc'] * 100:.2f}",
        }
    )

    try:
        # Load HTML template
        with open("./api/templates/report.html") as f:
            template_content = f.read()
    except FileNotFoundError:
        logger.error("Report template file not found.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Report template file not found.",
        )
    for recipient in recipients:
        # Personalize the email for each recipient
        personalized_data = report_data.copy()
        personalized_data["user_name"] = (
            recipient.name if recipient.name else recipient.email.split("@")[0]
        )
        personalized_data["dashboard_url"] = f"{settings.FRONTEND_DASHBOARD_URL}"
        personalized_data['year'] = datetime.now().year

        template = Template(template_content)
        html_content = template.render(**personalized_data)
        subject = f"ECL Model Execution Report - {execution_date_dt.strftime('%Y-%m-%d %H:%M:%S')}"

        added_attachments = []
        if file_bytes and filename:
            added_attachments.append({"filename": filename, "file": file_bytes})

        await send_email(
            recipient_emails=[recipient.email],
            subject=subject,
            body=html_content,
            attachments=added_attachments if added_attachments else [],
            subtype="html",
        )

    return {
        "message": "Emails with the attached is being sent to all recipients in the background."
    }


async def send_report_via_email(
    recipients: list,
    attachments: list
):
    try:
        # Load HTML template
        with open("./api/templates/email_report.html") as f:
            template_content = f.read()
    except FileNotFoundError:
        logger.error("Report template file not found.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Report template file not found.",
        )
    for recipient in recipients:
        # Personalize the email for each recipient
        personalized_data = {}
        personalized_data["dashboard_url"] = f"{settings.FRONTEND_DASHBOARD_URL}"
        personalized_data['year'] = datetime.now().year

        personalized_data["user_name"] = (
            recipient.name if recipient.name else recipient.email.split("@")[0]
        )
        template = Template(template_content)
        html_content = template.render(**personalized_data)
        subject = "Model Execution Report"

        await send_email(
            recipient_emails=[recipient.email],
            subject=subject,
            body=html_content,
            attachments=attachments if attachments else [],
            subtype="html",
        )

    return {
        "message": "Model Execution Report is being sent to all recipients in the background."
    }


async def send_onboarding_message(
    user_data: dict
):
    try:
        # Load HTML template
        with open("./api/templates/onboarding.html") as f:
            template_content = f.read()
    except FileNotFoundError:
        logger.error("Onboarding template file not found.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Onboarding template file not found.",
        )

    template = Template(template_content)
    html_content = template.render(**user_data)
    subject = "IFRS9 Onboarding Email"

    await send_email(
        recipient_emails=[user_data.get("email")],
        subject=subject,
        body=html_content,
        subtype="html",
    )

    return {"message": "welcome email sent"}


async def send_reset_passwd_message(
    data,
):
    try:
        # Load HTML template
        with open("./api/templates/reset_password.html") as f:
            template_content = f.read()
    except FileNotFoundError:
        logger.error("Reset password template file not found.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reset password template file not found.",
        )

    template = Template(template_content)
    html_content = template.render(**data)
    subject = "IFRS9 Password Reset Request"

    await send_email(
        recipient_emails=[data.get("email")],
        subject=subject,
        body=html_content,
        subtype="html",
    )

    return {"message": "reset password email sent"}


async def send_model_report_email(user_email: str, execution_id: int, db: Session):
    """Send model report email to user"""
    from api.utils.minio_service import minio_service
    from api.models.user import ModelExecutionLog, PDFile, LGDFile, EADFile, ECLFile, FLIFile, StagingFile, CCFFile
    import tempfile
    import os

    # Get the execution log to determine model type
    log = db.query(ModelExecutionLog).filter(ModelExecutionLog.id == execution_id).first()
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution log not found"
        )

    # Find the associated file based on model type
    file_record = None
    if log.executed_model_type.value == "pd":
        file_record = db.query(PDFile).filter(PDFile.execution_model_id == execution_id).first()
    elif log.executed_model_type.value == "lgd":
        file_record = db.query(LGDFile).filter(LGDFile.execution_model_id == execution_id).first()
    elif log.executed_model_type.value == "ead":
        file_record = db.query(EADFile).filter(EADFile.execution_model_id == execution_id).first()
    elif log.executed_model_type.value == "ecl":
        file_record = db.query(ECLFile).filter(ECLFile.execution_model_id == execution_id).first()
    elif log.executed_model_type.value == "fli":
        file_record = db.query(FLIFile).filter(FLIFile.execution_model_id == execution_id).first()
    elif log.executed_model_type.value == "staging":
        file_record = db.query(StagingFile).filter(StagingFile.execution_model_id == execution_id).first()
    elif log.executed_model_type.value == "ccf":
        file_record = db.query(CCFFile).filter(CCFFile.execution_model_id == execution_id).first()

    if not file_record or not file_record.minio_file_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output file not found or not stored in MinIO"
        )

    file_key = file_record.minio_file_key
    temp_path = None
    file_bytes = None

    try:
        # Use main bucket for all model types
        bucket_name = settings.MINIO_BUCKET

        temp_path = tempfile.mktemp(suffix=".xlsx")
        if minio_service.download_file(file_key, temp_path, bucket_name=bucket_name):
            with open(temp_path, "rb") as f:
                file_bytes = f.read()
        os.unlink(temp_path) if temp_path else None
    except Exception as e:
        if temp_path:
            os.unlink(temp_path)
        file_bytes = None

    success = False
    if file_bytes:
        success = await send_email(
            recipient_emails=[user_email],
            subject=f"Model Execution Report - {execution_id}",
            body="Attached is your model execution report.",
            attachments=[{"filename": f"model_report_{execution_id}.xlsx", "file": file_bytes}],
            subtype="html",
        )
    else:
        success = await send_email(
            recipient_emails=[user_email],
            subject=f"Model Execution Report - {execution_id}",
            body="Your model execution report is ready but attachment could not be retrieved. Please download from the dashboard.",
            subtype="html",
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send email. Please check email configuration and try again.",
        )

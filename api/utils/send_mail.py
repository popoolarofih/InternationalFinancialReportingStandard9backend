from io import BytesIO
from typing import Dict, List
from fastapi import UploadFile

# from jinja2 import Template
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema
from api.core.config import settings
from api.core.logging import get_logger

logger = get_logger(__name__)

# Email Configuration
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=False,
)


async def send_email(
    recipient_emails: List[str],
    subject: str,
    body: str,
    attachments: List[Dict[str, bytes]] = [],
    subtype: str = "plain",
):
    try:
        attachments = [
            UploadFile(filename=file["filename"], file=BytesIO(file["file"]))
            for file in attachments
        ]
        fm = FastMail(conf)
        message = MessageSchema(
            subject=subject,
            recipients=recipient_emails,
            body=body,
            subtype=subtype,
            attachments=attachments,
        )

        await fm.send_message(message)
        logger.info(f"Email sent to {recipient_emails}")
        return True

    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return False

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid


from typing import List
from api.core.logging import get_logger
from api.database.database import get_db
from api.schema.common import MessagePublic
from api.schema.user import EmailRecipientCreate, EmailRecipientPublic
from api.services import auth
from api.utils.deps import current_user
from api.models import User
from api.utils.validators import require_settings_access

logger = get_logger(__name__)

router = APIRouter(tags=["Settings"])


@router.get(
    "/email-recipients", response_model=MessagePublic[List[EmailRecipientPublic]]
)
async def get_email_recipients(
    user: User = Depends(current_user),
    _=Depends(require_settings_access),
    db_session: Session = Depends(get_db),
):
    """Returns all email_recipients"""
    try:
        response = await auth.get_all_email_recipients(db_session=db_session)
        return MessagePublic(
            success=True,
            message="Users retrieved successfully",
            data=[EmailRecipientPublic.model_validate(email) for email in response],
        )
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception as e:
        logger.error(f"an unexpected error occurred: {str(e)}")
        return MessagePublic(
            success=False, error="An unexpected error occurred", status_code=500
        )


# add an email recipient
@router.post("/email-recipients", response_model=MessagePublic[EmailRecipientPublic])
async def add_email_recipient(
    email_recipient: EmailRecipientCreate,
    _=Depends(require_settings_access),
    db_session: Session = Depends(get_db),
):
    """Adds a new email recipient"""
    try:
        response = await auth.add_email_recipient(
            db_session=db_session, user_details=email_recipient
        )
        return MessagePublic(
            success=True,
            message="Email recipient added successfully",
            data=EmailRecipientPublic.model_validate(response),
        )
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception as e:
        logger.error(f"an unexpected error occurred: {str(e)}")
        return MessagePublic(
            success=False, error="An unexpected error occurred", status_code=500
        )


# remove an email recipient
@router.delete(
    "/email-recipients/{recipient_id}",
    response_model=MessagePublic[EmailRecipientPublic],
)
async def delete_email_recipient(
    recipient_id: int,
    _=Depends(require_settings_access),
    db_session: Session = Depends(get_db),
):
    """Removes a email recipient"""
    try:
        response = await auth.delete_email_recipient(
            db_session=db_session, recipient_id=recipient_id
        )
        return MessagePublic().model_validate(response)
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception as e:
        logger.error(f"an unexpected error occurred: {str(e)}")
        return MessagePublic(
            success=False, error="An unexpected error occurred", status_code=500
        )

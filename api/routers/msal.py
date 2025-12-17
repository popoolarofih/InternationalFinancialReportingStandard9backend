from api.schema.common import MessagePublic
from api.services.msal import login, microsoft_token_verification
from api.utils.validators import fail_response
from api.core.config import settings
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api.database.database import get_db
from api.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["MSAL"])


@router.get('/auth/msal')
async def microsoft_login():
    '''authenticates the microsoft token and generate custom token'''
    try:
        logger.info('call to the msal verification made')
        response = await login()
        return MessagePublic(
            success=True,
            message="Microsoft login link generated successfully",
            data=response,
            )
    except HTTPException as e:
        logger.error("An exception occurred: %s", str(e))
        return fail_response(e.status_code, e.detail)
    except Exception as e:
        logger.error("An unexpected error occurred: %s", str(e))
        return fail_response(500, "An unexpected error occurred")


@router.get("/auth/callback", response_model=MessagePublic)
async def microsoft_callback(code: str, db_session: Session = Depends(get_db)):
    '''authenticates the microsoft token and generate custom token: the callback'''
    try:
        logger.info('call to the msal callback verification url made')
        if not code:
            raise HTTPException(
                status_code=400,
                detail="authentication unverified"
            )
        response = await microsoft_token_verification(code, db_session)
        # Construct frontend URL with token as query parameter
        frontend_url = f"{settings.MSAL_FRONTEND_REDIRECT_URL}/auth?access_token={response.access_token}&refresh_token={response.refresh_token}"
        return RedirectResponse(url=frontend_url)

    except HTTPException as e:
        logger.error("An exception occurred: %s", str(e))
        error_url = f"{settings.MSAL_FRONTEND_REDIRECT_URL}/error?error={e.detail}"
        return RedirectResponse(url=error_url)

    except Exception as e:
        logger.error("An unexpected error occurred: %s", str(e))
        error_url = f"{settings.MSAL_FRONTEND_REDIRECT_URL}/error?error=An unexpected error occurred"
        return RedirectResponse(url=error_url)
        return RedirectResponse(url=error_url)

import json
from fastapi import Depends, HTTPException
from jose import jwt, JWTError
import httpx
from api.database.database import get_db
from api.schema.user import UserSignin, UserCreate
from api.core.config import settings
from api.models.user import User
from api.services.auth import login_user, create_msal_user
from sqlalchemy.orm import Session
from sqlalchemy import func
from api.core.logging import get_logger

logger = get_logger(__name__)

MSAL_SCOPE = ["openid", "profile", "email"]


# helper function to fetch Microsoft public keys
async def fetch_microsoft_public_keys():
    jwks_uri = f"{settings.MSAL_AUTHORITY}/discovery/keys"
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_uri)
        return response.json()


# validate the microsoft ID token
async def validate_microsoft_token(token: str):
    keys = await fetch_microsoft_public_keys()
    try:
        logger.info('Fetching the microsoft public keys')
        unverified_header = jwt.get_unverified_header(token)
        key = next(key for key in keys["keys"] if key["kid"] == unverified_header["kid"])

        logger.info('Decoding the microsoft token')
        payload = jwt.decode(token, key, algorithms=["RS256"], audience=settings.MSAL_CLIENT_ID, issuer=f"{settings.MSAL_AUTHORITY}/v2.0")

        logger.info('microsoft token verified')
        return payload
    except (JWTError, StopIteration) as e:
        logger.error(f'an error occurred: {str(e)}')
        raise HTTPException(status_code=401, detail="Invalid token")


async def check_user(db_session: Session, user_email: str):
    '''check if user is already registered'''
    db_user = db_session.query(User).filter(func.lower(User.email) == user_email.lower()).first()
    if not db_user:
        return False
    return True


async def login():
    auth_url = (
        f"{settings.MSAL_AUTHORITY}/oauth2/v2.0/authorize?"
        f"client_id={settings.MSAL_CLIENT_ID}&"
        f"response_type=code&"
        f"redirect_url={settings.MSAL_REDIRECT_URI}&"
        f"scope={' '.join(MSAL_SCOPE)}"
    )
    return auth_url


async def microsoft_token_verification(code: str, db_session: Session):
    try:
        logger.info('starting the microsoft token validation')
        token_url = f"{settings.MSAL_AUTHORITY}/oauth2/v2.0/token"

        data = {
            "client_id": settings.MSAL_CLIENT_ID,
            "client_secret": settings.MSAL_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.MSAL_REDIRECT_URI,
            "grant_type": "authorization_code"
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(token_url, data=data)
            response.raise_for_status()
            token_data = response.json()
            logger.info(f'this  is the token data response: {token_data}')
            id_token = token_data.get('id_token')
            if not id_token:
                raise HTTPException(status_code=400, detail='No ID token received')
            payload = await validate_microsoft_token(id_token)

            # generate new custom token
            email = payload['preferred_username'] or payload['unique_name']

            # check if the user is already registered on the system
            logger.info('checking if user is registered')
            _is_user = await check_user(db_session, email)
            if not _is_user:
                # user is not registered, raise an error instead of auto-creating
                logger.warning(f'user {email} not registered, denying access')
                raise HTTPException(status_code=403, detail="User not registered in the system")

            # log user in and return custom token
            logger.info(f'user {email} is registered, generating login details')
            login_details = UserSignin(
                email=email)
            login_response = await login_user(login_details, db_session)
            return login_response
    except HTTPException as e:
        logger.error(f'an error occurred: {str(e)}')
        raise e
    except Exception as e:
        logger.error(f'An unexpected error occurred: {str(e)}')
        raise HTTPException(status_code=500, detail='An unexpected error occurred')
    except Exception as e:
        logger.error(f'An unexpected error occurred: {str(e)}')
        raise HTTPException(status_code=500, detail='An unexpected error occurred')

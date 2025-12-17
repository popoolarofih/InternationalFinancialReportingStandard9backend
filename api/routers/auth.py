from api.models import User
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import EmailStr
from sqlalchemy.orm import Session
from typing import List, Optional
from api.database.database import get_db
from api.schema.auth import ChangePassword
from api.schema.common import MessagePublic
from api.schema.user import (
    PasswordReset,
    RoleTypeEnum,
    UserCreate,
    UserPublic,
    UserSignin,
    UserSigninPublic,
)
from api.services import auth
from api.utils.validators import (
    fail_response,
    require_admin_management_access,
    require_profile_management_access,
)
from api.core.logging import get_logger

logger = get_logger(__name__)
oauth2_bearer_scheme = HTTPBearer()

router = APIRouter(tags=["Authentication"])


@router.post("/signup", response_model=MessagePublic[UserPublic])
async def create_user(
    background_tasks: BackgroundTasks,
    user_create: UserCreate,
    current_user: User = Depends(require_admin_management_access),
    db_session: Session = Depends(get_db),
):
    """
    User Registration: email, name, password
    """
    try:
        response = await auth.create_user(
            current_user=current_user,
            background_task=background_tasks,
            user_details=user_create,
            db_session=db_session,
        )
        return MessagePublic(
            success=True,
            message="New user created",
            data=UserPublic.model_validate(response),
        )
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception:
        return MessagePublic(
            success=False, error="An unexpected error occurred", status_code=500
        )


@router.post("/login", response_model=MessagePublic[UserSigninPublic])
async def login_user(
    user_detail: UserSignin,
    db_session: Session = Depends(get_db),
):
    """User Login"""
    try:
        response = await auth.login_user(
            user_details=user_detail, db_session=db_session
        )
        return MessagePublic(
            success=True,
            message="Verification successfull",
            data=UserSigninPublic.model_validate(response),
        )
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception:
        return MessagePublic(
            success=False, error="An unexpected error occurred", status_code=500
        )


@router.put("/change_password", response_model=MessagePublic[UserPublic])
async def change_password(
    user_create: ChangePassword,
    current_user=Depends(require_profile_management_access),
    db_session: Session = Depends(get_db),
):
    """
    change user password
    """
    try:
        response = await auth.change_password(
            password_details=user_create,
            current_user_id=current_user.id,
            db_session=db_session,
        )
        return MessagePublic.model_validate(response)
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception:
        return MessagePublic(
            success=False, error="An unexpected error occurred", status_code=500
        )


@router.post("/forgot_password", response_model=MessagePublic)
async def forgot_password(
    background_tasks: BackgroundTasks,
    user_email: str,
    db_session: Session = Depends(get_db),
):
    """
    Forgotten Password
    """
    try:
        response = await auth.forgotPassword(
            background_tasks=background_tasks,
            user_email=user_email,
            db_session=db_session,
        )
        return MessagePublic().model_validate(response)
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception:
        return MessagePublic(
            success=False, error="An unexpected error occurred", status_code=500
        )


@router.post("/resend_code", response_model=MessagePublic)
async def resend_code(
    background_tasks: BackgroundTasks,
    user_email: EmailStr,
    db_session: Session = Depends(get_db),
):
    """
    Resend code for forgotten password
    """
    try:
        response = await auth.resend_code(
            background_tasks=background_tasks,
            user_email=user_email,
            db_session=db_session,
        )
        return MessagePublic().model_validate(response)
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception as e:
        return MessagePublic(
            success=False,
            error="An unexpected error occurred",
            status_code=e.status_code,
        )


@router.post("/reset_password", response_model=MessagePublic)
async def reset_password(
    password_details: PasswordReset,
    db_session: Session = Depends(get_db),
):
    """
    User Registration: email, name, password
    """
    try:
        response = await auth.resetPassword(
            password_details=password_details, db_session=db_session
        )
        return MessagePublic().model_validate(response)
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception:
        return MessagePublic(
            success=False, error="An unexpected error occurred", status_code=500
        )


@router.post("/refresh", response_model=MessagePublic)
async def refresh_token(
    token: HTTPAuthorizationCredentials = Depends(oauth2_bearer_scheme),
):
    try:
        response = await auth.refreshToken(token)
        return MessagePublic(data=response)
    except HTTPException as e:
        return fail_response(e.status_code, e.detail)
    except Exception:
        return fail_response(500, "An unexpected error occurred")


@router.get("/users", response_model=MessagePublic[List[UserPublic]])
async def get_users(
    user_id: Optional[int] = None,
    _=Depends(require_admin_management_access),
    db_session: Session = Depends(get_db),
):
    """Returns all users or a specific user if user_id is provided"""
    try:
        response = await auth.get_users(db_session=db_session, user_id=user_id)
        if user_id:
            return MessagePublic(
                success=True,
                message="Users retrieved successfully",
                data=[UserPublic.model_validate(response)],
            )
        return MessagePublic(
            success=True,
            message="Users retrieved successfully",
            data=[UserPublic.model_validate(user) for user in response],
        )
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception as e:
        logger.error(f"an unexpected error occurred: {str(e)}")
        return MessagePublic(
            success=False, error="An unexpected error occurred", status_code=500
        )


@router.put("/users/{user_id}", response_model=MessagePublic)
async def update_users(
    user_id: int,
    new_role: RoleTypeEnum,
    current_user: User = Depends(require_admin_management_access),
    db_session: Session = Depends(get_db),
):
    """updates a user role in the application"""
    try:
        response = await auth.update_user(
            current_user=current_user,
            db_session=db_session,
            user_id=user_id, new_role=new_role
        )

        return MessagePublic.model_validate(response)
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception as e:
        logger.error(f"an unexpected error occurred: {str(e)}")
        return MessagePublic(
            success=False, error="An unexpected error occurred", status_code=500
        )


@router.delete("/users/{user_id}", response_model=MessagePublic)
async def delete_users(
    user_id: int,
    current_user: User = Depends(require_admin_management_access),
    db_session: Session = Depends(get_db),
):
    """Removes a user from the application"""
    try:
        response = await auth.remove_user(
            current_user=current_user,
            db_session=db_session,
            user_id=user_id
        )

        return MessagePublic.model_validate(response)
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception as e:
        logger.error(f"an unexpected error occurred: {str(e)}")
        return MessagePublic(
            success=False, error="An unexpected error occurred", status_code=500
        )


@router.get("/me", response_model=MessagePublic[List[UserPublic]])
async def get_me(
    db_session: Session = Depends(get_db),
    user: User = Depends(require_profile_management_access),
):
    """returns the details of a specific logged in user"""
    try:
        response = await auth.profile(db_session=db_session, user_id=user.id)

        return MessagePublic(
            success=True,
            message="Users retrieved successfully",
            data=[UserPublic.model_validate(response)],
        )
    except HTTPException as e:
        return MessagePublic(success=False, error=e.detail, status_code=e.status_code)
    except Exception as e:
        logger.error(f"an unexpected error occurred: {str(e)}")
        return MessagePublic(
            success=False, error="An unexpected error occurred", status_code=500
        )

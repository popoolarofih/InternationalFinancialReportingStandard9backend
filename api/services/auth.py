from datetime import datetime
from sqlite3 import OperationalError
from typing import Union

from api.services.email import send_onboarding_message, send_reset_passwd_message
from fastapi import BackgroundTasks, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import func

from api.core.config import settings
from api.core.logging import get_logger
from api.database.database import get_db
from api.models import User, EmailRecipient
from api.schema.auth import ChangePassword
from api.schema.user import (
    PasswordReset,
    TokenTypeEnum,
    UserCreate,
    UserSignin,
    UserSigninPublic,
    EmailRecipientCreate,
    RoleTypeEnum,
)
from api.utils import deps
from api.utils.deps import (
    create_jwt,
    generate_random_access_code,
    generate_random_password,
    get_password_hash,
    verify_password,
)

logger = get_logger(__name__)


async def create_user(
    current_user: User,
    user_details: UserCreate, db_session: Session, background_task: BackgroundTasks
):
    """Creates a new user and assign the required role to the user"""
    try:
        db_user = db_session.query(User).filter(func.lower(User.email) == user_details.email.lower()).first()
        if db_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with email already exists",
            )
        random_password = generate_random_password()
        default_password = get_password_hash(random_password)
        new_user = User(
            full_name=user_details.full_name,
            email=user_details.email,
            hashed_password=default_password,
            role=user_details.role,
            status="active",
            is_temporary_password=True,
            last_logged_in=None,
        )
        db_session.add(new_user)
        db_session.commit()
        db_session.refresh(new_user)
        user_data = {
            "first_name": user_details.full_name,
            "email": user_details.email,
            "link_to_IFRS": settings.FRONTEND_URL,
            "year": datetime.now().year
        }
        background_task.add_task(
            send_onboarding_message,
            user_data,
        )
        return new_user
    except HTTPException as e:
        raise e
    except OperationalError:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="A database error occurred"
        )
    except Exception as e:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e.args[0])}",
        )


async def create_msal_user(
    user_details: UserCreate, db_session: Session
):
    """Creates a new user for MSAL authentication without requiring current_user"""
    try:
        db_user = db_session.query(User).filter(func.lower(User.email) == user_details.email.lower()).first()
        if db_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with email already exists",
            )
        # For MSAL users, set a dummy password since they authenticate via MSAL
        dummy_password = get_password_hash("msal_user_dummy_password")
        new_user = User(
            full_name=user_details.full_name,
            email=user_details.email,
            hashed_password=dummy_password,
            role=RoleTypeEnum.USER,  # Default role for MSAL users
            status="active",
            is_temporary_password=False,  # MSAL users don't need password reset
            last_logged_in=None,
        )
        db_session.add(new_user)
        db_session.commit()
        db_session.refresh(new_user)
        logger.info(f"MSAL user {user_details.email} created successfully")
        return new_user
    except HTTPException as e:
        raise e
    except OperationalError:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="A database error occurred"
        )
    except Exception as e:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e.args[0])}",
        )


async def login_user(user_details: UserSignin, db_session: Session):
    """Log a user in"""
    try:
        # confirm user is registered
        db_user = (
            db_session.query(User).filter(func.lower(User.email) == user_details.email.lower()).first()
        )
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Invalid email provided"
            )

        # confirm the password matches
        # if password is supplied, verify that they match.
        if user_details.password:
            if not verify_password(user_details.password, db_user.hashed_password):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Password do not match"
                )

        # generate access and refresh token for user

        access_token = create_jwt(db_user)
        refresh_token = create_jwt(db_user, TokenTypeEnum.REFRESH)
        db_user.last_logged_in = datetime.utcnow()
        db_session.commit()

        # return the details to the client
        return UserSigninPublic(
            access_token=access_token, refresh_token=refresh_token, user=db_user
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}",
        )


async def resend_code(
    background_tasks: Union[BackgroundTasks, None],
    user_email: EmailStr,
    db_session: Session,
):
    # check if the user exists
    db_user = db_session.query(User).filter(func.lower(User.email) == user_email.lower()).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Email not registered"
        )

    # generate a valid verification token
    verification_token = generate_random_access_code()

    # generate the password reset link
    password_reset_link = f"{settings.FRONTEND_PWD_LINK}?email={db_user.email}&verification={verification_token}"

    # save to the database
    db_user.verification_code = verification_token

    user_data = {
        "first_name": db_user.full_name,
        "email": db_user.email,
        "reset_link": password_reset_link,
    }
    background_tasks.add_task(send_reset_passwd_message, user_data)
    db_session.commit()
    return {"message": "Password reset link set to mail"}


async def forgotPassword(
    user_email: str, db_session: Session, background_tasks: BackgroundTasks
):
    """Procedures to recover a password"""
    try:
        response = await resend_code(
            background_tasks=background_tasks,
            user_email=user_email,
            db_session=db_session,
        )

        return response
    except HTTPException as e:
        raise e
    except Exception as e:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}",
        )


async def change_password(
    password_details: ChangePassword, db_session: Session, current_user_id: int
):
    """Changes a user password"""
    try:
        user_id = current_user_id

        # Fetch the user from the database
        db_user = db_session.query(User).filter(User.id == user_id).first()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Verify the old password
        if not verify_password(password_details.old_password, db_user.password):
            raise HTTPException(status_code=401, detail="Incorrect old password")

        # Hash the new password and update the user's record
        hashed_new_password = get_password_hash(password_details.new_password)
        db_user.hashed_password = hashed_new_password
        db_user.is_temporary_password = False
        db_session.commit()
        db_session.refresh(db_user)
        return {"message": "Password changed successfully"}
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        db_session.rollback()
        logger.error(f"An unexpected error occurred: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password",
        )


async def resetPassword(password_details: PasswordReset, db_session: Session):
    """Reset a user's password"""
    try:
        # get the user
        db_user = (
            db_session.query(User)
            .filter(
                func.lower(User.email) == password_details.email.lower(),
                User.verification_code == password_details.verification_code,
            )
            .first()
        )
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid parameters provided",
            )

        # set the user new password
        db_user.password = get_password_hash(password=password_details.password)
        db_user.verification_code = None
        db_session.commit()

        # can optionally send an email informing user of reset password
        return {"message": "Password reset successful"}
    except HTTPException as e:
        raise e
    except OperationalError:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_504_BAD_GATEWAY,
            detail="A operational error has occurred",
        )
    except Exception as e:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}",
        )


async def refreshToken(token: HTTPAuthorizationCredentials):
    db_session: Session = next(get_db())
    try:
        # verify it's the refresh token that's sent
        token_data = await deps.decodeToken(token)
        if token_data["data"]["token_type"] != "refresh":
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail="Refresh token is required",
            )

        # get the user data
        db_user = (
            db_session.query(User)
            .filter(func.lower(User.email) == token_data["data"]["user_email"].lower())
            .first()
        )
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        token = create_jwt(db_user)
        return token
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error has occurred: {str(e)}",
        )


async def get_users(
    db_session: Session,
    user_id: int = None,
):
    """Returns all users in the db or a specific user if user_id provided"""
    try:
        # get the users
        db_query = db_session.query(User)
        if user_id:
            db_users = db_query.filter_by(id=user_id).first()
        else:
            db_users = db_query.all()
        if not db_users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Users not found"
            )

        return db_users
    except HTTPException as e:
        raise e
    except OperationalError:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_504_BAD_GATEWAY,
            detail="A operational error has occurred",
        )
    except Exception as e:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e.args[0])}",
        )


async def profile(
    db_session: Session,
    user_id: int,
):
    """Returns details of a specific user"""
    try:
        # get the user
        logger.info("getting the details of a user")
        db_user = db_session.query(User).filter_by(id=user_id).first()

        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        return db_user
    except HTTPException as e:
        raise e
    except OperationalError:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_504_BAD_GATEWAY,
            detail="A operational error has occurred",
        )
    except Exception as e:
        db_session.rollback()
        logger.error(f"An unexpected error occurred: {str(e.args[0])}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        )


async def update_user(
    current_user: User,
    db_session: Session,
    user_id: int,
    new_role: str,
):
    """Updates a specific user's role in the application"""
    try:
        # get the users
        db_user = db_session.query(User).filter_by(id=user_id).first()

        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        allowed_roles = [role.value for role in RoleTypeEnum]
        if new_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"New role is not recognized, use one of {allowed_roles}",
            )
        # Normalize new role to RoleTypeEnum
        try:
            role_enum = (
                new_role
                if isinstance(new_role, RoleTypeEnum)
                else RoleTypeEnum(new_role)
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"New role is not recognized, use one of {[role.value for role in RoleTypeEnum]}",
            )

        if (
            current_user.id == user_id
            and role_enum.value == RoleTypeEnum.SUPER_ADMIN
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to assign this role",
            )

        db_user.role = role_enum
        db_session.commit()
        db_session.refresh(db_user)
        return {"message": "User role updated successfully"}

    except HTTPException as e:
        raise e
    except OperationalError:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_504_BAD_GATEWAY,
            detail="A operational error has occurred",
        )
    except Exception as e:
        logger.error(f"an exception occurred: : {str(e)}")
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        )


async def remove_user(
    current_user: User,
    db_session: Session,
    user_id: int,
):
    """Removes a specific user from the application"""
    try:
        # get the users
        db_user = db_session.query(User).filter_by(id=user_id).first()

        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        db_session.delete(db_user)
        db_session.commit()
        return {"message": "User deleted successfully"}

    except HTTPException as e:
        raise e
    except OperationalError:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_504_BAD_GATEWAY,
            detail="A operational error has occurred",
        )
    except Exception as e:
        db_session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e.args[0])}",
        )


# SETTINGS


async def add_email_recipient(
    db_session: Session,
    user_details: EmailRecipientCreate,
):
    try:
        # check if the recipient hasn't been added before
        db_reci = (
            db_session.query(EmailRecipient)
            .filter(
                func.lower(EmailRecipient.email) == user_details.email.lower()
            )
            .first()
        )
        if db_reci:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A recipient with this email already exists",
            )
        recipient = EmailRecipient(
            email=user_details.email,
            name=user_details.name or ""
        )
        db_session.add(recipient)
        db_session.commit()
        db_session.refresh(recipient)
        return recipient
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"an unexpected error occurred: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="an unexpected error occurred",
        )


async def get_all_email_recipients(db_session: Session):
    return db_session.query(EmailRecipient).all()


async def delete_email_recipient(recipient_id: int, db_session: Session):
    try:
        # fetch the recipient
        db_reci = (
            db_session.query(EmailRecipient)
            .filter_by(id=recipient_id)
            .first()
        )
        if not db_reci:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="requested recipient not found",
            )

        db_session.delete(db_reci)
        db_session.commit()
        return {"message": "recipient deleted successfully"}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"an unexpected error occurred: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="an unexpected error occurred",
        )
    except Exception as e:
        logger.error(f"an unexpected error occurred: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="an unexpected error occurred",
        )

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from api.models.user import User
from api.schema.user import RoleTypeEnum
from api.utils.deps import current_user


def fail_response(status_code: int, message: str, data: Optional[dict] = None):
    """Returns a JSON response for failed responses"""

    response_data = {"status_code": status_code, "success": False, "message": message}

    if data is not None:
        response_data["data"] = data

    return JSONResponse(
        status_code=status_code, content=jsonable_encoder(response_data)
    )

# DEFINE BASE ROLES


async def require_user(current_user: User = Depends(current_user)):
    """
    This method checks if the current user has the 'User' role.
    """
    if current_user.role != RoleTypeEnum.USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User role required"
        )
    return current_user


async def require_superuser(current_user: User = Depends(current_user)):
    """
    This method checks if the current user has the 'Super User' role.
    It grants access to full dashboard, reporting, and model execution, but not admin management.
    """
    if current_user.role != RoleTypeEnum.SUPER_USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Superuser role required"
        )
    return current_user


async def require_admin(current_user: User = Depends(current_user)):
    """
    This method checks if the current user has the 'Admin' role.
    Admins have access to Admin Management (user and admin management) but not model execution or dashboard.
    """
    if current_user.role != RoleTypeEnum.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required"
        )
    return current_user


async def require_superadmin(current_user: User = Depends(current_user)):
    """
    This method checks if the current user has the 'Super Admin' role.
    Super Admins have full access to all system functionality, including Admin Management, Dashboard, Reporting, and Model Execution.
    """
    if current_user.role != RoleTypeEnum.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin role required"
        )
    return current_user


async def require_reporting_access(current_user: User = Depends(current_user)):
    """
    Users, Super Users, and Super Admins can access the Reporting and Dashboard modules.
    """
    if current_user.role not in (
        RoleTypeEnum.USER,
        RoleTypeEnum.SUPER_USER,
        RoleTypeEnum.SUPER_ADMIN,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Report Access required"
        )
    return current_user


async def require_dashboard_access(current_user: User = Depends(current_user)):
    """
    Users, Super Users, and Super Admins can access the Dashboard module.
    """
    if current_user.role not in (
        RoleTypeEnum.USER,
        RoleTypeEnum.SUPER_USER,
        RoleTypeEnum.SUPER_ADMIN,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Dashboard access required"
        )
    return current_user


async def require_model_execution_access(current_user: User = Depends(current_user)):
    """
    Super Users and Super Admins have access to model execution.
    """
    if current_user.role not in (RoleTypeEnum.SUPER_USER, RoleTypeEnum.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Model execution access required",
        )
    return current_user


async def require_admin_management_access(current_user: User = Depends(current_user)):
    """
    Admins and Super Admins can manage Admin functionalities (add/remove users).
    """
    if current_user.role not in (RoleTypeEnum.ADMIN, RoleTypeEnum.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin management access required",
        )
    return current_user


async def require_settings_access(current_user: User = Depends(current_user)):
    """
    Super Users and Super Admins have access to settings.
    """
    if current_user.role not in (RoleTypeEnum.SUPER_USER, RoleTypeEnum.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Settings access required"
        )
    return current_user


async def require_profile_management_access(current_user: User = Depends(current_user)):
    """
    All users can change their password, so no role-based restriction here.
    """
    return current_user


async def require_full_system_access(current_user: User = Depends(current_user)):
    """
    Super Admins have full access to the system (Dashboard, Model Execution, Reporting, Admin Management, Settings, Email Notification).
    """
    if current_user.role != RoleTypeEnum.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Super Admin access required"
        )
    return current_user

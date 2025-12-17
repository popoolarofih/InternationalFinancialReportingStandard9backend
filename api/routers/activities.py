from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from typing import Any
from math import ceil

from api.database import get_db
from api.utils.deps import current_user
from api.models.user import ActivityLog
from api.schema.models_schema import ActivityLogPublic, PaginatedResponse

router = APIRouter(prefix="/activities", tags=["activities"])

@router.get(
    "/",
    summary="Get Activity Logs - Returns a paginated response of activity logs",
    response_model=PaginatedResponse
)
async def get_activity_logs(
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: Any = Depends(current_user),
):
    """Returns a paginated response of activity logs"""

    # Get total record count
    total_records = db.query(ActivityLog).filter(
        ActivityLog.user_id == current_user.id
    ).count()

    # Fetch paginated activity logs
    activities = (
        db.query(ActivityLog)
        .options(joinedload(ActivityLog.user), joinedload(ActivityLog.model_execution_log))
        .filter(ActivityLog.user_id == current_user.id)
        .order_by(ActivityLog.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Serialize results
    activity_logs = [
        ActivityLogPublic(
            id=activity.id,
            timestamp=activity.timestamp,
            user_name=activity.user.full_name if activity.user else None,
            user_email=activity.user.email if activity.user else None,
            execution_model_type=activity.model_execution_log.executed_model_type.value if activity.model_execution_log else None,
            execution_status=activity.model_execution_log.execution_status.value if activity.model_execution_log else None,
        )
        for activity in activities
    ]

    total_pages = ceil(total_records / page_size)

    # Return paginated response
    return PaginatedResponse(
        items=activity_logs,
        total=total_records,
        page=page,
        size=page_size,
        pages=total_pages,
    )

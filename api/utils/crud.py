from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timezone
from ..data_model import User, ActivityLog, ActivityTag
from ..schema.user import UpdateMeUser
from ..models.user import (
    PDFile,
    LGDFile,
    EADFile,
    ECLFile,
    FLIFile,
    StagingFile,
    CCFFile,
)
from typing import List

async def get_all_users(db: Session) -> List[User]:
    """
    Retrieve all users from the database.
    """
    return db.query(User).all()

async def update_user_info(db: Session, user_id: int, update_data: UpdateMeUser) -> User:
    """
    Update user information (full_name, department).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for key, value in update_data.dict(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user

async def add_activity(db: Session, user: User, activity: str, message: str = None) -> None:
    """
    Add an activity log entry for a user.
    """
    activity_log = ActivityLog(
        user_id=user.id,
        activity=activity,
        message=message,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(activity_log)
    db.commit()

def create_pd_file(db: Session, pd_file: PDFile) -> PDFile:
    """
    Create a PD file entry in the database.
    """
    db.add(pd_file)
    db.commit()
    db.refresh(pd_file)
    return pd_file

def create_lgd_file(db: Session, lgd_file: LGDFile) -> LGDFile:
    """
    Create an LGD file entry in the database.
    """
    db.add(lgd_file)
    db.commit()
    db.refresh(lgd_file)
    return lgd_file

def create_ead_file(db: Session, ead_file: EADFile) -> EADFile:
    """
    Create an EAD file entry in the database.
    """
    db.add(ead_file)
    db.commit()
    db.refresh(ead_file)
    return ead_file

def create_ecl_file(db: Session, ecl_file: ECLFile) -> ECLFile:
    """
    Create an ECL file entry in the database.
    """
    db.add(ecl_file)
    db.commit()
    db.refresh(ecl_file)
    return ecl_file

def create_fli_file(db: Session, fli_file: FLIFile) -> FLIFile:
    """
    Create an FLI file entry in the database.
    """
    db.add(fli_file)
    db.commit()
    db.refresh(fli_file)
    return fli_file

def create_staging_file(db: Session, staging_file: StagingFile) -> StagingFile:
    """
    Create a Staging file entry in the database.
    """
    db.add(staging_file)
    db.commit()
    db.refresh(staging_file)
    return staging_file

def create_ccf_file(db: Session, ccf_file: CCFFile) -> CCFFile:
    """
    Create a CCF file entry in the database.
    """
    db.add(ccf_file)
    db.commit()
    db.refresh(ccf_file)
    return ccf_file
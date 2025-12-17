from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone

Base = declarative_base()

class ActivityTag:
    LOGGED_IN = "logged_in"
    CHANGE_PASSWORD = "change_password"
    RESET_PASSWORD = "reset_password"
    UPDATE_PROFILE = "update_profile"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String, nullable=True)
    role = Column(String, nullable=True)
    status = Column(String, nullable=True)
    hashed_password = Column(String)
    is_temporary_password = Column(Boolean, default=False)
    temp_password_set_at = Column(DateTime, nullable=True)
    last_logged_in = Column(DateTime, nullable=True)
    refresh_token = Column(String, nullable=True)
    refresh_token_expires_at = Column(DateTime, nullable=True)

class ActivityLog(Base):
    __tablename__ = "activity_log"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    activity = Column(String)
    message = Column(String, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
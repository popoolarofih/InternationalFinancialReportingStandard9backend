from sqlmodel import SQLModel
from pydantic import field_validator


class ChangePassword(SQLModel):
    old_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    def validate_password(cls, value):
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return value

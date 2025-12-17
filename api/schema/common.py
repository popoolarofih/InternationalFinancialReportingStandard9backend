from typing import Generic, Optional, TypeVar, List
from pydantic import BaseModel

T = TypeVar("T")


class MessagePublic(BaseModel, Generic[T]):
    success: bool = True
    message: Optional[str] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    data: Optional[T] = None


class ValidationError(BaseModel):
    loc: List[str]
    msg: str
    type: str


class HTTPValidationError(BaseModel):
    detail: Optional[List[ValidationError]] = None

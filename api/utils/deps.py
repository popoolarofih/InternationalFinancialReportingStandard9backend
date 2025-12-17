import json
import os
import random
import pandas as pd
from pathlib import Path
import secrets
from datetime import datetime, timedelta, timezone, date
from io import BytesIO
from typing import Optional

import bcrypt
from dotenv import load_dotenv
from fastapi import Depends, File, Form, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import desc
from sqlalchemy.orm import Session
from minio.error import S3Error

from api.core.config import settings
from api.core.logging import get_logger
from api.core.miniosetup import minio_client
from api.database.database import get_db
from api.models.user import (
    ExecutionModelType,
    ModelExecutionLog,
    ModelExecutionStatus,
    User,
)
from api.schema.user import TokenTypeEnum, UserPublic
from api.schema.models_schema import ModelTypeEnum

########### CONFIGURATION ###############

basepath = os.path.dirname(__file__)
LOCAL_OUTPUT_DIR = f"{basepath}"
os.makedirs(LOCAL_OUTPUT_DIR, exist_ok=True)
MODEL_RUN_OUTPUT_BUCKET = settings.MINIO_BUCKET


MODEL_REQUIREMENTS = {
    "ecl_model": 5,
    "lgd_model": 6,
    "pd_model": 2,
    "ead_model": 3, #ccf and staging files are required
    "ccf_model": 1,
    "staging_model": 1,
    "fli_model": 1,
}

logger = get_logger(__name__)
load_dotenv()

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM

# Define password expiration time (24 hours)
PASSWORD_EXPIRY_TIME = timedelta(hours=24)

oauth2_bearer_scheme = HTTPBearer()


def create_jwt(user: User, token_type: TokenTypeEnum = TokenTypeEnum.BEARER):
    expiry_minutes = (
        settings.ACCESS_TOKEN_EXPIRES_MINUTES
        if token_type == TokenTypeEnum.BEARER
        else settings.REFRESH_TOKEN_EXPIRY_TIME
    )

    subject = {
        "token_type": token_type,
        "user_email": user.email,
        "user_id": str(user.id),
    }

    expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
    ).timestamp()
    return jwt.encode(
        {
            "sub": json.dumps(subject),
            "exp": expires_at,
            "iat": datetime.now(timezone.utc).timestamp(),
            "user_data": UserPublic.model_validate(user).model_dump_json(),
            "token_type": token_type,
        },
        SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_password_hash(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# generate random temporary password after signup
def generate_random_password(length=10):
    return secrets.token_urlsafe(length)


def is_password_expired(user: User):
    # Get the current time in UTC
    current_time = datetime.now()

    # Check if password was set more than 24 hours ago
    if current_time - user.temp_password_set_at > PASSWORD_EXPIRY_TIME:
        return True  # Password is expired

    return False  # Password is still valid


async def get_user(email: str, db: Session = None):
    return db.query(User).filter(User.email == email).first()


async def current_user(
    token: HTTPAuthorizationCredentials = Depends(oauth2_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        data = json.loads(payload.get("sub"))
        if not isinstance(data, dict) or "user_email" not in data:
            raise HTTPException(status_code=401, detail="Invalid token")
        email: str = data["user_email"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await get_user(email, db)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def decodeToken(token):
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        data = json.loads(payload.get("sub"))
        user_data = json.loads(payload.get("user_data"))
        if not isinstance(data, dict) or "user_email" not in data:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"data": data, "user_data": user_data}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def generate_random_access_code(length=6):
    return "".join(map(str, random.sample(range(10), length)))


def process_file(file: UploadFile) -> BytesIO:
    """Reads and returns the file content as BytesIO, with optional file size limit.

    Args:
        file: The uploaded file.

    Raises:
        HTTPException: 400 Bad Request if the file is missing, empty, or exceeds the size limit.

    Returns:
        BytesIO: The file content as BytesIO.
    """
    logger.info(f"Processing file: {file.filename}")

    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No file uploaded."
        )
    try:
        content = file.file.read()
        if not content:
            raise ValueError("File is empty")

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        logger.exception(f"Error reading file: {file.filename}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error reading file.",
        )
    return BytesIO(content)


def upload_to_minio(
    output_file: str | Path | BytesIO, db_model, bucket_name=MODEL_RUN_OUTPUT_BUCKET
):
    """Upload file to MinIO."""
    try:
        # NOTE: Each model execution type has it's own folder
        minio_path = (
            f"{db_model.executed_model_type}/{db_model.id}_{db_model.data_name}.xlsx"
        )
        if isinstance(output_file, (Path, str)):
            assert Path(output_file).exists(), "File does not exist"
            minio_client.fput_object(
                bucket_name=bucket_name, object_name=minio_path, file_path=output_file
            )
        elif isinstance(output_file, BytesIO):
            # This branch is not needed but I left if just in case we want to use it to upload
            # files that can be read from memory
            output_file.seek(0)
            minio_client.put_object(
                bucket_name=bucket_name, object_name=minio_path, data=output_file
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type",
            )
        logger.info(f"File uploaded to MinIO: {minio_path}")
        db_model.report_exported = True
    except Exception as e:
        logger.error(f"Error uploading to MinIO for model ID {db_model.id}: : {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload to MinIO",
        )


async def remove_from_minio(
    object_name, bucket_name=MODEL_RUN_OUTPUT_BUCKET, db_model=None
):
    """Removes a file from MinIO storage."""
    try:
        minio_client.remove_object(
            bucket_name, object_name
        )  # Removes the file from the minio storage
        logger.info(f"Successfully removed {object_name} from {bucket_name}")
        db_model.report_exported = False
        return True

    except Exception as e:
        logger.error(f"Error removing {object_name} from {bucket_name}: {e}")
        return False


def get_file_from_minio(
    file_path: str, bucket_name=MODEL_RUN_OUTPUT_BUCKET, minio_client=None
):
    """Retrieves a file from MinIO.

    Args:
        bucket_name: The name of the MinIO bucket.
        file_path: The path to the file within the bucket.
        minio_client: Optional. A custom MinIO client instance.
            If not provided, a default client will be used (assuming it's defined globally).

    Returns:
        bytes: The content of the file.

    Raises:
        HTTPException: 404 if the file is not found or if the content is empty.
        HTTPException: 500 if there's an error during file retrieval.
    """
    try:
        client = minio_client or minio_client
        response = client.get_object(bucket_name, file_path)
        file_content = response.read()

        if not file_content:
            raise HTTPException(status_code=404, detail="File content is empty")

        return file_content
    except S3Error as e:
        if e.code == "NoSuchKey":
            logger.error(f"No such key error: {e.message}")
            raise HTTPException(
                status_code=404,
                detail="The requested file does not exist in the storage.",
            )
        else:
            logger.error(f"MinIO error occurred: {str(e)}")
            raise HTTPException(
                status_code=500, detail="Error retrieving files from storage"
            )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error retrieving file from storage: {str(e)}")
        raise HTTPException(
            status_code=400, detail="Error retrieving file from storage"
        )


async def upload_file(
    execution_model_type: ModelTypeEnum = Form(
        ..., description="The model type to run"
    ),
    execution_date: date = Form(..., description="The date for the execution"),
    file1: UploadFile = File(..., description="The files to upload"),
    file2: Optional[UploadFile] = File(None, description="The files to upload"),
    file3: Optional[UploadFile] = File(None, description="The files to upload"),
    file4: Optional[UploadFile] = File(None, description="The files to upload"),
    file5: Optional[UploadFile] = File(None, description="The files to upload"),
    file6: Optional[UploadFile] = File(None, description="The files to upload"),
):
    """The upload endpoint for the files"""
    logger.info(
        "Starting upload_file with execution_model_type: %s, execution_date: %s",
        execution_model_type,
        execution_date,
    )

    try:
        # 1. Validate Model Type and File Count
        if execution_model_type not in MODEL_REQUIREMENTS:  # might be redundant now
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid model name"
            )

        # filter out the empty files
        files_list = [file1, file2, file3, file4, file5, file6]
        files = [file for file in files_list if file is not None]
        required_files = MODEL_REQUIREMENTS[execution_model_type]
        if len(files) != required_files:
            logger.error(
                "File requirement not met for model: %s. Expected %d files, got %d.",
                execution_model_type,
                required_files,
                len(files),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"This model requires {required_files} files, but {len(files)} were provided.",
            )

        # 2. Process Files
        processed_files = {}
        filenames = []
        for i, file in enumerate(files):
            try:
                processed_files[f"file{i+1}"] = process_file(file)
                filenames.append(file.filename)
            except HTTPException as e:
                raise e
            except Exception as e:
                logger.error(f"Error processing file {file.filename}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error processing file {file.filename}",
                )

        # 3. Construct Response
        processed_files["execution_date"] = execution_date
        processed_files["filenames"] = datetime.now().strftime("%Y%m%d_%H%M%S")
        # (
        #     ", ".join(filenames)
        #     if len(filenames) > 1
        #     else filenames[0]
        #     if filenames
        #     else None
        # )

        return processed_files

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception("An unexpected error occurred during file upload: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during file upload",
        )


##########################
#   FLI DEPENDENCY
##########################
async def check_fli_model_executed(db_session: Session = Depends(get_db)):
    logger.info("Entering check_fli_model_executed dependency")

    current_date = datetime.now()
    current_quarter = (current_date.month - 1) // 3
    current_year = current_date.year

    try:
        # query the latest FLI execution model
        db_fli = (
            db_session.query(ModelExecutionLog)
            .filter_by(
                executed_model_type=ExecutionModelType.FLI,
                execution_status=ModelExecutionStatus.COMPLETED,
            )
            .order_by(desc(ModelExecutionLog.timestamp))
            .first()
        )

        if not db_fli:
            logger.error("No successful FLI model execution found in the database.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="FLI model must be executed before running other models",
            )

        # check the execution dates
        execution_date = db_fli.timestamp
        execution_quarter = (execution_date.month - 1) // 3
        execution_year = execution_date.year

        if execution_year != current_year or execution_quarter != current_quarter:
            logger.error(
                f"FLI model is outdated. Last execution was in Q{execution_quarter + 1} {execution_year}, "
                f"but current quarter is Q{current_quarter + 1} {current_year}."
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="FLI must be updated for the current quarter before running other models",
            )

        logger.info("FLI model execution check passed.")
        return

    except HTTPException as e:
        logger.error(f"HTTPException in check_fli_model_executed: {e.detail}")
        raise
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred in check_fli_model_executed: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during FLI model check",
        )


def df_to_dict(df_output):
    """converts dataframes into dictionaries"""
    try:
        logger.info("converting df to dictionary")
        return {
            key: value.to_dict(orient="records")
            if isinstance(value, pd.DataFrame)
            else value
            for key, value in df_output.items()
        }
    except Exception as e:
        logger.error(f"Error converting dataframe to dictionary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during dataframe conversion",
        )


def revoke_task(task_id: str, terminate: bool = True, signal: str | None = "SIGTERM"):
    """
    Revoke a celery task by its ID.
    """
    from api.main import celery as celery_app

    return celery_app.control.revoke(
        task_id,
        terminate=terminate,
        signal=signal,
    )

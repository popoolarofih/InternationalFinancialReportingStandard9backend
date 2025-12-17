import os
import uuid
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from io import BytesIO
import pandas as pd
from minio import Minio
from minio.error import S3Error

from api.core.config import settings
from api.core.miniosetup import minio_client


class MinIOService:
    """Robust service for handling MinIO operations for model outputs with retry logic and enhanced logging."""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.client = minio_client
        self.main_bucket = settings.MINIO_BUCKET
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logging.getLogger(__name__)

    def _retry_operation(self, operation_func, *args, **kwargs):
        """Generic retry wrapper for MinIO operations."""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                return operation_func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    self.logger.warning(f"Operation failed (attempt {attempt + 1}/{self.max_retries}): {str(e)}. Retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    self.logger.error(f"Operation failed after {self.max_retries} attempts: {str(e)}")
        raise last_exception

    def ensure_bucket_exists(self, bucket_name: str) -> bool:
        """Ensure bucket exists, create if it doesn't with retry logic."""
        def _create_bucket():
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                self.logger.info(f"Created bucket: {bucket_name}")
            return True

        try:
            return self._retry_operation(_create_bucket)
        except S3Error as e:
            self.logger.error(f"Failed to create bucket {bucket_name} after retries: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error creating bucket {bucket_name}: {e}")
            return False

    def generate_file_key(self, model_type: str, execution_id: int, filename: str) -> str:
        """Generate a unique file key for MinIO storage."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_id = str(uuid.uuid4())[:8]
        return f"{model_type}/execution_{execution_id}/{timestamp}_{file_id}_{filename}"

    def upload_file(self, file_path: str, model_type: str, execution_id: int,
                   custom_filename: Optional[str] = None) -> Optional[str]:
        """Upload a file to MinIO with retry logic and return the file key."""
        try:
            # Always use the single main bucket for all model types
            bucket_name = self.main_bucket

            # Ensure bucket exists with retries
            if not self.ensure_bucket_exists(bucket_name):
                raise Exception(f"Failed to ensure bucket {bucket_name} exists")

            # Generate filename if not provided
            if not custom_filename:
                filename = os.path.basename(file_path)
            else:
                filename = custom_filename

            # Generate unique file key
            file_key = self.generate_file_key(model_type, execution_id, filename)

            # Verify file exists before upload
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File to upload does not exist: {file_path}")

            # Upload file with retry logic
            def _upload():
                self.client.fput_object(bucket_name, file_key, file_path)
                return file_key

            result = self._retry_operation(_upload)
            self.logger.info(f"Successfully uploaded {file_path} to MinIO bucket '{bucket_name}' as {file_key}")
            return result

        except FileNotFoundError as e:
            self.logger.error(f"File not found error: {e}")
            raise e
        except S3Error as e:
            self.logger.error(f"S3 error uploading file {file_path}: {e}")
            raise Exception(f"MinIO upload failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error uploading file {file_path}: {e}")
            raise Exception(f"File upload failed: {str(e)}")

    def upload_dataframe(self, df: pd.DataFrame, model_type: str, execution_id: int,
                        filename: str, sheet_name: str = "Sheet1") -> Optional[str]:
        """Upload a pandas DataFrame as Excel to MinIO with retry logic."""
        try:
            # Always use the single main bucket for all model types
            bucket_name = self.main_bucket

            # Ensure bucket exists with retries
            if not self.ensure_bucket_exists(bucket_name):
                raise Exception(f"Failed to ensure bucket {bucket_name} exists")

            # Generate unique file key
            file_key = self.generate_file_key(model_type, execution_id, filename)

            # Create Excel file in memory
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            excel_buffer.seek(0)

            # Upload to MinIO with retry logic
            def _upload_df():
                self.client.put_object(
                    bucket_name,
                    file_key,
                    excel_buffer,
                    length=len(excel_buffer.getvalue())
                )
                return file_key

            result = self._retry_operation(_upload_df)
            self.logger.info(f"Successfully uploaded DataFrame to MinIO bucket '{bucket_name}' as {file_key}")
            return result

        except S3Error as e:
            self.logger.error(f"S3 error uploading DataFrame: {e}")
            raise Exception(f"MinIO DataFrame upload failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error uploading DataFrame: {e}")
            raise Exception(f"DataFrame upload failed: {str(e)}")

    def download_file(self, file_key: str, download_path: str,
                     bucket_name: Optional[str] = None) -> bool:
        """Download a file from MinIO to local path with retry logic."""
        try:
            # Always use the single main bucket if not specified
            if not bucket_name:
                bucket_name = self.main_bucket

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(download_path), exist_ok=True)

            # Download file with retry logic
            def _download():
                self.client.fget_object(bucket_name, file_key, download_path)
                return True

            result = self._retry_operation(_download)
            self.logger.info(f"Successfully downloaded {file_key} from bucket '{bucket_name}' to {download_path}")
            return result

        except S3Error as e:
            self.logger.error(f"S3 error downloading file {file_key}: {e}")
            raise Exception(f"MinIO download failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error downloading file {file_key}: {e}")
            raise Exception(f"File download failed: {str(e)}")

    def get_file_url(self, file_key: str, bucket_name: Optional[str] = None) -> str:
        """Generate a presigned URL for file download with retry logic."""
        try:
            # Always use the single main bucket if not specified
            if not bucket_name:
                bucket_name = self.main_bucket

            # Generate presigned URL with retry logic
            def _get_url():
                url = self.client.presigned_get_object(bucket_name, file_key, expires=timedelta(hours=24))
                return url

            url = self._retry_operation(_get_url)

            # For local development, replace 'minio' with 'localhost' in the URL
            if 'minio' in url:
                url = url.replace('minio', 'localhost')

            self.logger.info(f"Generated presigned URL for {file_key}")
            return url

        except S3Error as e:
            self.logger.error(f"S3 error generating URL for {file_key}: {e}")
            raise Exception(f"URL generation failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error generating URL for {file_key}: {e}")
            raise Exception(f"URL generation failed: {str(e)}")

    def list_files(self, model_type: str, execution_id: Optional[int] = None,
                  bucket_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List files for a specific model type and execution with retry logic."""
        try:
            # Always use the single main bucket if not specified
            if not bucket_name:
                bucket_name = self.main_bucket

            # List objects with prefix and retry logic
            prefix = f"{model_type}/"
            if execution_id:
                prefix += f"execution_{execution_id}/"

            def _list_objects():
                objects = self.client.list_objects(bucket_name, prefix=prefix, recursive=True)
                files = []
                for obj in objects:
                    files.append({
                        "key": obj.object_name,
                        "size": obj.size,
                        "last_modified": obj.last_modified,
                        "etag": obj.etag
                    })
                return files

            files = self._retry_operation(_list_objects)
            self.logger.info(f"Listed {len(files)} files for model_type='{model_type}', execution_id={execution_id}")
            return files

        except S3Error as e:
            self.logger.error(f"S3 error listing files: {e}")
            raise Exception(f"File listing failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error listing files: {e}")
            raise Exception(f"File listing failed: {str(e)}")

    def delete_file(self, file_key: str, bucket_name: Optional[str] = None) -> bool:
        """Delete a file from MinIO with retry logic."""
        try:
            # Always use the single main bucket if not specified
            if not bucket_name:
                bucket_name = self.main_bucket

            # Delete file with retry logic
            def _delete():
                self.client.remove_object(bucket_name, file_key)
                return True

            result = self._retry_operation(_delete)
            self.logger.info(f"Successfully deleted {file_key} from bucket '{bucket_name}'")
            return result

        except S3Error as e:
            self.logger.error(f"S3 error deleting file {file_key}: {e}")
            raise Exception(f"File deletion failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error deleting file {file_key}: {e}")
            raise Exception(f"File deletion failed: {str(e)}")


# Global instance
minio_service = MinIOService()

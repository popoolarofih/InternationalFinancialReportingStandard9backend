from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Class to hold application's config values."""

    SECRET_KEY: str = "my-ranD0m-s3cr3t-k3y"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRES_MINUTES: int = 10
    REFRESH_TOKEN_EXPIRY_TIME: int = 120

    # Database
    PROD_DB_URI: str
    LOCAL_DB_URI: str
    TESTING_DB_URI: str

    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    PGDATA: str

    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_PORT: int
    MAIL_SERVER: str
    MAIL_FROM_NAME: str
    MAIL_USE_TLS: str = "true"
    MAIL_USE_SSL: str = "false"

    ENV: str
    FRONTEND_URL: str
    FRONTEND_PWD_LINK: str
    FRONTEND_DASHBOARD_URL: str

    # ADMIN SETUP
    ADMIN_NAME: str
    ADMIN_EMAIL: str
    ADMIN_PASSWORD: str

    # REGULAR USERS SETUP
    REGULAR_USER_EMAILS: List[str] = []

    # MINIO SETUP
    MINIO_ENDPOINT: str
    MINIO_ROOT_USER: str
    MINIO_ROOT_PASSWORD: str
    MINIO_SECURE: str = False
    MINIO_BUCKET: str
    FLI_BUCKET: str

    # Model execution values
    STAGING_ROWS_TO_SAVE: int
    EAD_ROWS_TO_SAVE: int
    ECL_ROWS_TO_SAVE: int
    PD_ROWS_TO_SAVE: int
    LGD_ROWS_TO_SAVE: int

    # MSAL CONFIG
    MSAL_AUTHORITY: str
    MSAL_CLIENT_ID: str
    MSAL_CLIENT_SECRET: str
    MSAL_REDIRECT_URI: str
    MSAL_FRONTEND_REDIRECT_URL: str
    MSAL_TENANT_ID: str = ""
    MSAL_SCOPE: str = ""

    # CELERY CONFIGURATIONS
    CELERY_RESULT_BACKEND: str
    CELERY_BROKER_URL: str

    # Add these fields to match .env
    database_url: str = ""
    NEXT_PUBLIC_API_BASE_URL: str = ""

    WORKTEMPLATES_PATH: str = "worktemplates"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

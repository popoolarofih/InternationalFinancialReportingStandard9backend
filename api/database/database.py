from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from api.core.config import settings
from api.core.logging import get_logger

logger = get_logger(__name__)

if settings.ENV == "TESTING":
    DATABASE_URI = settings.TESTING_DB_URI
    logger.info(f"This is testing mode and this is the db uri {DATABASE_URI}")

elif settings.ENV == "DEVELOPMENT":
    DATABASE_URI = settings.LOCAL_DB_URI
    logger.info(f"This is development mode and this is the db uri {DATABASE_URI}")

elif settings.ENV == "PRODUCTION":
    DATABASE_URI = settings.PROD_DB_URI

# logger.info(f'The database engine: {DATABASE_URI}')

engine = create_engine(
    DATABASE_URI,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_timeout=30,
    pool_size=10,
    max_overflow=20,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
logger.debug(f"server is running well: {engine}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

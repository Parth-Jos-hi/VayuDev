
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


# Get database URL from the environment configuration
database_url = settings.database_url.get_secret_value()

# Configure PostgreSQL to use Psycopg 3
url = make_url(database_url).set(
    drivername="postgresql+psycopg"
)

# Create database engine
engine = create_engine(
    url,
    pool_pre_ping=True
)

# Create session factory
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False
)

# Provide and close database sessions
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

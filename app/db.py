from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings


# Base class for all models
Base = declarative_base()

# create engine
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
)

SessionLocal = sessionmaker(
    autocommit = False,
    autoflush = False,
    bind = engine,
)

# helper function to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
"""
Database configuration for Best Buy Scanner.
Uses PostgreSQL (shared with customer platform).
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Use environment variable or default to platform database
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://bde_customer_platform_user:4G1wDPxs8WaZaXhefACIdsQiS8bNSfTC@dpg-d5ilsqlactks73e60fi0-a.oregon-postgres.render.com/bde_customer_platform"
)

# Handle Render's postgres:// vs postgresql:// issue
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables."""
    from . import models  # noqa - import to register models
    Base.metadata.create_all(bind=engine)
    print(f"Database initialized")

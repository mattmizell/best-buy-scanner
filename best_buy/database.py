"""
Database configuration for Best Buy Scanner.
Uses PostgreSQL on Render, SQLite for local dev.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path

# Use DATABASE_URL env var for PostgreSQL, fallback to SQLite for local dev
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # Render uses postgres:// but SQLAlchemy needs postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
    print(f"Using PostgreSQL database")
else:
    # Local development - use SQLite
    DB_DIR = Path(__file__).parent.parent / "data"
    DB_DIR.mkdir(exist_ok=True)
    DB_PATH = DB_DIR / "best_buy.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    print(f"Using SQLite at {DB_PATH}")

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
    """Create all tables if they don't exist."""
    from . import models  # noqa - import to register models
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    print(f"Existing tables: {existing_tables}")

    # Create each table individually to handle partial states
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            try:
                table.create(engine, checkfirst=True)
                print(f"Created table: {table.name}")
            except Exception as e:
                print(f"Error creating {table.name}: {e}")
        else:
            print(f"Table exists: {table.name}")

    # Create indexes separately, ignoring if they exist
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                try:
                    index.create(engine, checkfirst=True)
                except Exception:
                    pass  # Index already exists
        conn.commit()

    print("Database initialization complete")

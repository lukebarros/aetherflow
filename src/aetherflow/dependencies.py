"""FastAPI dependencies."""

from sqlalchemy.orm import Session, sessionmaker

# This will be set by main.py
SessionLocal: sessionmaker = None


def get_db():
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

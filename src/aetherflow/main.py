"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from aetherflow.config import settings
from aetherflow.logging import get_logger, configure_logging
from aetherflow.models import Base
from aetherflow import dependencies

# Initialize logging
configure_logging()
logger = get_logger(__name__)

# Database setup
engine = create_engine(
    settings.database_url,
    echo=settings.env == "development",
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Initialize dependencies with SessionLocal
dependencies.SessionLocal = SessionLocal

# Import router after dependencies are set
from aetherflow.api import router as workflows_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("app_starting", env=settings.env, log_level=settings.log_level)
    
    # Verify database connection
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info("database_connected", tables_count=len(tables), tables=tables)
    except Exception as e:
        logger.error("database_connection_failed", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("app_shutting_down")
    engine.dispose()


# FastAPI application
app = FastAPI(
    title="AetherFlow",
    description="AI-enabled workflow orchestration platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(workflows_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    
    Returns service status and database connectivity.
    """
    try:
        # Verify DB connection
        with engine.connect() as conn:
            pass
        
        return {
            "status": "healthy",
            "service": "aetherflow",
            "environment": settings.env,
        }
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail="Service unavailable: database connection failed"
        )


@app.get("/", tags=["Info"])
async def root():
    """Root endpoint."""
    return {
        "service": "AetherFlow",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


# Future endpoints will be added here
# from aetherflow.api import workflows, executions, tasks
# app.include_router(workflows.router)
# app.include_router(executions.router)
# app.include_router(tasks.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "aetherflow.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.env == "development",
    )

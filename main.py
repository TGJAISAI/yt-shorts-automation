"""Main FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_config
from app.core.logger import setup_logging
from app.api import routes
import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    config = get_config()

    # Setup logging
    setup_logging(
        log_level=config.settings.log_level,
        log_format=config.logging.format,
        max_bytes=10 * 1024 * 1024,
        backup_count=config.logging.backup_count
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Starting {config.app.name} v{config.app.version}")
    logger.info(f"Environment: {config.settings.environment}")

    # Start scheduler if enabled
    if config.settings.schedule_enabled:
        try:
            scheduler.start_scheduler()
            logger.info("Automated scheduler enabled and started")
        except Exception as e:
            logger.error(f"Failed to start scheduler: {str(e)}")

    yield

    # Shutdown
    logger.info("Shutting down application")

    # Stop scheduler
    if scheduler.is_running():
        try:
            scheduler.stop_scheduler()
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {str(e)}")


# Create FastAPI application
app = FastAPI(
    title="YouTube Shorts Automation",
    description="Automated video generation and upload pipeline for YouTube Shorts using AI",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(routes.router, prefix="/api/v1", tags=["api"])


@app.get("/")
async def root():
    """Root endpoint."""
    config = get_config()
    return {
        "name": config.app.name,
        "version": config.app.version,
        "description": config.app.description,
        "docs": "/docs",
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn

    # Get configuration
    config = get_config()

    # Run the application
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=config.settings.environment == "development",
        log_level=config.settings.log_level.lower()
    )

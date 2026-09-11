"""FastAPI application for Job Copilot."""

from contextlib import asynccontextmanager
from typing import Dict
from fastapi import FastAPI
import uvicorn

from job_copilot import __version__
from job_copilot.api.routes.analytics import router as analytics_router
from job_copilot.api.routes.application_prep import router as application_prep_router
from job_copilot.api.routes.browser import router as browser_router
from job_copilot.api.routes.copilot import router as copilot_router
from job_copilot.api.routes.discovery import router as discovery_router
from job_copilot.api.routes.job_intelligence import router as job_intelligence_router
from job_copilot.api.routes.resume import router as resume_router
from job_copilot.api.routes.tracking import router as tracking_router
from job_copilot.config import settings
from job_copilot.db.database import check_db_connection, init_db
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for startup and shutdown events."""
    logger.info("Starting Job Copilot API...")
    init_db()
    yield
    logger.info("Shutting down Job Copilot API...")


app = FastAPI(
    title="Job Copilot API",
    description="Personal Job Application Automation and Copilot System",
    version=__version__,
    lifespan=lifespan,
)

app.include_router(analytics_router)
app.include_router(application_prep_router)
app.include_router(browser_router)
app.include_router(copilot_router)
app.include_router(discovery_router)
app.include_router(job_intelligence_router)
app.include_router(resume_router)
app.include_router(tracking_router)


@app.get("/health", summary="Health Check")
def health_check() -> Dict[str, str]:
    """Health status endpoint (lightweight for liveness probes)."""
    return {"status": "ok"}


@app.get("/ready", summary="Readiness Check")
def readiness_check() -> Dict[str, str]:
    """Readiness probe checking database connectivity without leaking credentials."""
    from fastapi import HTTPException, status

    db_healthy = check_db_connection()
    if not db_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connectivity unavailable",
        )
    return {
        "status": "ready",
        "database": "connected",
    }


@app.get("/", summary="Root Status")
def root() -> Dict[str, str]:
    """Basic service identifier."""
    return {
        "service": "Job Copilot API",
        "version": __version__,
        "status": "online",
    }


def start_api():
    """CLI runner for starting FastAPI server."""
    uvicorn.run(
        "job_copilot.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    start_api()

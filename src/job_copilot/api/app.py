"""FastAPI application for Job Copilot."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import uvicorn

from job_copilot import __version__
from job_copilot.api.auth import require_dashboard_auth
from job_copilot.api.routes.agent_protocol import router as agent_protocol_router
from job_copilot.api.routes.analytics import router as analytics_router
from job_copilot.api.routes.application_prep import router as application_prep_router
from job_copilot.api.routes.browser import router as browser_router
from job_copilot.api.routes.browser_sessions import router as browser_sessions_router
from job_copilot.api.routes.browser_tasks import router as browser_tasks_router
from job_copilot.api.routes.copilot import router as copilot_router
from job_copilot.api.routes.dashboard import router as dashboard_router
from job_copilot.api.routes.discovery import router as discovery_router
from job_copilot.api.routes.job_intelligence import router as job_intelligence_router
from job_copilot.api.routes.resume import router as resume_router
from job_copilot.api.routes.tracking import router as tracking_router
from job_copilot.config import settings
from job_copilot.db.database import check_db_connection, init_db
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Attach standard defensive HTTP security headers to all HTTP responses.
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: blob:; "
            "frame-src 'self' blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self';"
        )
        # Apply HSTS on HTTPS requests or in production
        is_https = (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto", "").lower() == "https"
        )
        if is_https or settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for startup and shutdown events."""
    import asyncio
    import os
    logger.info("Starting Job Copilot API...")
    init_db()

    # Start zero-cost supervised background BrowserWorker loop in server mode
    worker = None
    worker_task = None
    enable_worker = os.environ.get("ENABLE_BACKGROUND_WORKER", "true").lower() in ("true", "1", "yes")
    if enable_worker:
        try:
            from job_copilot.browser_worker.worker import BrowserWorker
            worker = BrowserWorker(poll_interval_seconds=3.0)
            worker_task = asyncio.create_task(worker.run_loop())
            logger.info(f"Initialized background BrowserWorker '{worker.worker_id}' in API process.")
        except Exception as e:
            logger.warning(f"Could not start background BrowserWorker in lifespan: {e}")

    yield

    logger.info("Shutting down Job Copilot API...")
    if worker:
        worker.stop()
    if worker_task:
        worker_task.cancel()
        try:
            await asyncio.wait_for(worker_task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass



app = FastAPI(
    title="Job Copilot API",
    description="Personal Job Application Automation and Human Review Control Center",
    version=__version__,
    lifespan=lifespan,
)

# 1. Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# 2. CORS Middleware with safe origin parsing and production protection
cors_origins = settings.parsed_cors_origins
if settings.is_production:
    if "*" in cors_origins:
        logger.warning(
            "Wildcard origin '*' is unsafe for production with credentials. Removing '*' from allowed origins."
        )
        cors_origins = [o for o in cors_origins if o != "*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins else ["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


# 3. Global exception handler to mask internal stack traces in production
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    logger.error(
        f"Unhandled exception during {request.method} {request.url.path}: {exc}",
        exc_info=True,
    )
    if settings.is_production or not settings.debug:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred."},
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc)},
    )


# 4. Include feature routers with require_dashboard_auth protection
app.include_router(dashboard_router)
app.include_router(agent_protocol_router)
app.include_router(analytics_router, dependencies=[Depends(require_dashboard_auth)])
app.include_router(application_prep_router, dependencies=[Depends(require_dashboard_auth)])
app.include_router(browser_sessions_router, dependencies=[Depends(require_dashboard_auth)])
app.include_router(browser_tasks_router, dependencies=[Depends(require_dashboard_auth)])
app.include_router(browser_router, dependencies=[Depends(require_dashboard_auth)])
app.include_router(copilot_router, dependencies=[Depends(require_dashboard_auth)])
app.include_router(discovery_router, dependencies=[Depends(require_dashboard_auth)])
app.include_router(job_intelligence_router, dependencies=[Depends(require_dashboard_auth)])
app.include_router(resume_router, dependencies=[Depends(require_dashboard_auth)])
app.include_router(tracking_router, dependencies=[Depends(require_dashboard_auth)])


@app.get("/health", summary="Health Check")
def health_check() -> Dict[str, str]:
    """Health status endpoint (lightweight for liveness probes)."""
    return {"status": "ok"}


@app.get("/ready", summary="Readiness Check")
def readiness_check() -> Dict[str, str]:
    """Readiness probe checking database connectivity and storage readiness without leaking credentials."""
    db_healthy = check_db_connection()
    if not db_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connectivity unavailable",
        )

    # In production with S3 storage, verify configuration is present
    if settings.is_production and settings.artifact_storage_provider.lower() == "s3":
        s3_valid, s3_msg = settings.validate_s3_config()
        if not s3_valid:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Storage configuration unavailable: {s3_msg}",
            )

    return {
        "status": "ready",
        "database": "connected",
        "storage": settings.artifact_storage_provider,
    }


# Static and UI routes
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        app.mount("/dashboard/assets", StaticFiles(directory=str(assets_dir)), name="dashboard_assets")

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/dashboard", summary="Dashboard Control Center UI")
    @app.get("/dashboard/", summary="Dashboard Control Center UI")
    @app.get("/dashboard/{full_path:path}", summary="Dashboard Single Page App")
    def serve_dashboard(full_path: str = ""):
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"status": "Dashboard frontend asset building in progress"}


@app.get("/", summary="Root Status")
def root() -> Dict[str, str]:
    """Basic service identifier."""
    return {
        "service": "Job Copilot API",
        "version": __version__,
        "status": "online",
        "dashboard": "/dashboard",
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


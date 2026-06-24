from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import AsyncSession, get_db
from app.core.exceptions import AppError
from app.core.logging import setup_logging
from app.core.rate_limit import limiter
from app.db.session import check_db_connection
from app.websocket.manager import websocket_endpoint
from app.workers.notification_worker import notification_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await notification_worker.start()
    yield
    await notification_worker.stop()


app = FastAPI(
    title=settings.app_name,
    description="YouHoo Alert — emergency coordination API for SOS alerts, live location, and trusted groups",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_cors_origins = settings.cors_origin_list
_allow_all_origins = _cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all_origins else _cors_origins,
    allow_credentials=not _allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)

if settings.enable_legacy_api:
    from app.routers.legacy_api import legacy_api_router

    app.include_router(legacy_api_router, prefix="/api")


@app.websocket("/ws/alerts/{alert_id}")
async def alert_websocket(
    websocket: WebSocket,
    alert_id: str,
    token: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> None:
    await websocket_endpoint(websocket, alert_id, token, db)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.get("/health/db")
async def health_db() -> dict[str, str]:
    if not settings.uses_database:
        return {"status": "skipped", "message": "DATABASE_URL not set"}
    ok = await check_db_connection()
    return {"status": "ok" if ok else "error", "storage": "postgres"}


@app.get("/health/notifications")
async def health_notifications() -> JSONResponse:
    """Diagnostic report for SOS push delivery (Redis, worker, tokens, queue)."""
    from app.services.notification_health import collect_notification_health

    report = await collect_notification_health()
    status_code = 503 if report["status"] == "error" else 200
    return JSONResponse(status_code=status_code, content=report)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "code": exc.code, "details": exc.details},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "Validation failed", "code": "validation_error", "details": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    import logging

    logging.getLogger(__name__).exception("Unhandled API error")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Something went wrong. Please try again in a moment.",
            "code": "internal_error",
        },
    )

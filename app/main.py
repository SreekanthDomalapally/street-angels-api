from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
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
    description="Emergency coordination API — SOS alerts, live location, trusted groups",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.websocket("/ws/alerts/{alert_id}")
async def alert_websocket(websocket: WebSocket, alert_id: str, token: str | None = None) -> None:
    await websocket_endpoint(websocket, alert_id, token)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


@app.get("/health/db")
async def health_db() -> dict[str, str]:
    if not settings.uses_database:
        return {"status": "skipped", "message": "DATABASE_URL not set"}
    ok = await check_db_connection()
    return {"status": "ok" if ok else "error", "storage": "postgres"}


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

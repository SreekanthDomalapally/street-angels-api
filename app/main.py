from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db.database import check_db_connection, init_db
from app.routers import auth, contacts, emergencies, users
from app.services import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.uses_database:
        init_db()
    yield


app = FastAPI(
    title="Street Angels API",
    description="Backend API for the Street Angels safety app",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(contacts.router, prefix="/api")
app.include_router(emergencies.router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "storage": store.storage_mode()}


@app.get("/health/db")
def health_db() -> dict:
    if not settings.uses_database:
        return {"status": "skipped", "message": "Set POSTGRES_URL or DATABASE_URL in .env"}
    try:
        ok = check_db_connection()
        return {"status": "ok" if ok else "error", "storage": "postgres"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "Validation failed", "details": exc.errors()},
    )

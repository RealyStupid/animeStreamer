"""
    API main entrance point allowing the setup and deployment of the API
"""
from contextlib import asynccontextmanager
import logging
from time import perf_counter


from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from fastapi.encoders import jsonable_encoder

from fastapi.responses import JSONResponse

from starlette.exceptions import HTTPException as StarletteHTTPException


from core.config import get_settings

from core.logging import LoggingConfig, configure_logging, get_logger

from core.database import engine, Base

from sqlalchemy import text
# Settings
settings = get_settings()

# Logging configuration
configure_logging(
    LoggingConfig(
        name=               "PiraTube",
        directory=          ".logs",
        filename=           "piratube.log",
        level=              "DEBUG" if settings.DEBUG == True else "INFO",
        file_level=         "DEBUG" if settings.DEBUG == True else "INFO",
        console_level=      "DEBUG" if settings.DEBUG == True else "INFO",
        file=True,
        console=True if settings.ENVIRONMENT == "development" else False,
        rotation_type="time",
        rotation_when="midnight",
        rotation_interval=1,
        backup_count=3,
        log_format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        capture_root=True,
    )
)

logging.getLogger("sqlalchemy.engine").setLevel(
    logging.INFO if settings.DEBUG else logging.WARNING
)

# Uvicorn's default handlers bypass the root logger. Forward its server logs
# through the configured handlers; request lines are logged by the middleware.
for logger_name in ("uvicorn", "uvicorn.error"):
    server_logger = logging.getLogger(logger_name)

    for handler in server_logger.handlers[:]:
        server_logger.removeHandler(handler)
        handler.close()

    server_logger.setLevel(logging.WARNING)
    server_logger.propagate = True
    server_logger.disabled = False

access_logger = logging.getLogger("uvicorn.access")

for handler in access_logger.handlers[:]:
    access_logger.removeHandler(handler)
    handler.close()

access_logger.disabled = True

logger = get_logger(__name__)


# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("----- %s Started -----", app.title)

    if settings.DEBUG:
        # listing routes
        routes = [
            f"  {', '.join(r.methods or []): <10} {r.path}"
            for r in app.routes
            if hasattr(r, "methods")
        ]
        logger.debug("Registered routes:\n" + "\n".join(sorted(routes)))

        # get settings info
        if settings.ENVIRONMENT == "development":
            logger.debug(
                "Configuration Settings:\n" +
                f"                                  App Name:                   '{settings.APP_NAME}'\n" +
                f"                                  App Version:                '{settings.APP_VERSION}'\n"
                f"                                  Enviroment:                 '{settings.ENVIRONMENT}'\n" +
                f"                                  Debug:                      '{str(settings.DEBUG)}'\n" +
                f"                                  Allowed Hosts:              '{settings.allowed_origins_list}'\n" +
                f"                                  Secret Key:                 '{settings.SECRET_KEY}'\n" +
                f"                                  Algorithm:                  '{settings.ALGORITHM}'\n" +
                f"                                  Access Token Expire Min:    '{settings.ACCESS_TOKEN_EXPIRE_MINUTES}'\n" +
                f"                                  Refresh Token Expire Days:  '{settings.REFRESH_TOKEN_EXPIRE_DAYS}'\n" +
                f"                                  Database URL:               '{settings.DATABASE_URL}'\n"
            )
        else:
            logger.info("Enviroment is detected as production and so configuration is hidden")

    # begin database
    logger.info("Begining Database\n")

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Error While begining database '{settings.DATABASE_URL}': {e}")

    logger.info("Database Beginned!")
    yield

    logger.info("Stopping/dispossing Database")
    await engine.dispose()

    logger.info("----- %s Stopped -----", app.title)

# app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API for PiraTube",
    docs_url="/api/docs"                if settings.DEBUG or settings.ENVIRONMENT == "development" else None,
    redoc_url="/api/redocs"             if settings.DEBUG or settings.ENVIRONMENT == "development" else None,
    openapi_url="/api/openapi.json"     if settings.DEBUG or settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (perf_counter() - start_time) * 1000
        logger.error(
            "%s %s failed after %.2f ms",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (perf_counter() - start_time) * 1000
    if response.status_code >= 500:
        level = logging.ERROR
    elif response.status_code >= 400:
        level = logging.WARNING
    else:
        level = logging.INFO
    logger.log(
        level,
        "%s %s -> %d (%.2f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

# Exception Handlers
@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error(
            "HTTP %d while handling %s %s",
            exc.status_code,
            request.method,
            request.url.path,
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.debug(
        "Request validation failed for %s %s",
        request.method,
        request.url.path,
    )
    errors = [
        {
            "loc": [str(x) for x in error["loc"]],
            "msg": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors())})


@app.exception_handler(Exception)
async def handle_unexpected_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "Unhandled %s while handling %s %s",
        type(exc).__name__,
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )


# Routes
API_PREFIX = "/api/v1"

# add routers here

# Health & Meta
@app.get("/api/health", tags=["Meta"])
async def health_check():
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }
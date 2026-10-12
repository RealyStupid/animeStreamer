"""
    API main entrance point allowing the setup and deployment of the API
"""
from contextlib import asynccontextmanager
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
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
from core.database import engine
from core.storage import StorageManager


from sqlalchemy import text


from routes.auth import auth
from routes.users import users
from routes.media import media

# Settings
settings = get_settings()

# Logging configuration
configure_logging(
    LoggingConfig(
        name=               settings.APP_NAME,
        directory=          ".logs",
        filename=           f"{settings.APP_NAME}.log",
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

# Keep storage diagnostics out of the API log and console.
storage_logger = logging.getLogger(f"{settings.APP_NAME}.storage")
storage_logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
storage_logger.propagate = False

for handler in storage_logger.handlers[:]:
    if getattr(handler, "_anime_streamer_storage_handler", False):
        storage_logger.removeHandler(handler)
        handler.close()

storage_log_directory = Path(".logs")
storage_log_directory.mkdir(parents=True, exist_ok=True)
storage_file_handler = TimedRotatingFileHandler(
    storage_log_directory / "storage.log",
    when="midnight",
    interval=1,
    backupCount=3,
    encoding="utf-8",
)
storage_file_handler.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
storage_file_handler.setFormatter(
    logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
    )
)
setattr(storage_file_handler, "_anime_streamer_storage_handler", True)
storage_logger.addHandler(storage_file_handler)

logging.getLogger("sqlalchemy.engine").setLevel(
    logging.INFO if settings.DEBUG else logging.WARNING
)

# storage manager initialzation
storage: StorageManager = StorageManager(
    default_path=".localDevStorage" if settings.ENVIRONMENT == "development" else ".localStorage",
    default_allocation="10 GiB",
    debug=settings.DEBUG,
    print_debug=False,
    logger=storage_logger,
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
    try:
        app.state.storage = storage
        logger.info("Local storage manager initialized at path: %s", storage.default_storage_id)
    except Exception as e:
        logger.error("error occured when trying to initialize local storage manager: %s", e)
        
    if settings.DEBUG:
        # listing routes
        route_lines = []
        for route in app.routes:
            get_included_routes = getattr(route, "effective_route_contexts", None)
            routes = get_included_routes() if callable(get_included_routes) else [route]
            for included_route in routes:
                methods = (
                    ", ".join(
                        sorted(getattr(included_route, "methods", None) or [])
                    )
                    or "N/A"
                )
                path = (
                    getattr(included_route, "path_format", None)
                    or getattr(included_route, "path", None)
                    or "N/A"
                )
                route_lines.append(f"  {methods:<10} {path}")
        logger.debug("Registered routes:\n%s", "\n".join(route_lines))

        storageInfo = storage.get_storage(storage_id=storage.default_storage_id)
        logger.debug(
            f"Main Storage Information: \n" +
            f"  Storage ID:             {storageInfo.storage_id}\n" +
            f"  Path:                   {storageInfo.path}\n" +
            f"  Alocated bytes:         {storageInfo.allocation_bytes}\n" +
            f"  Bytes used:             {storageInfo.used_bytes}\n" +
            f"  Available bytes:        {storageInfo.available_bytes}\n" +
            f"  Filesystem free bytes:  {storageInfo.filesystem_free_bytes}\n"
        )
        
        # get settings info
        if settings.ENVIRONMENT == "development":
            logger.debug(
                "Configuration Settings:\n" +
                f"  App Name:                   '{settings.APP_NAME}'\n" +
                f"  App Version:                '{settings.APP_VERSION}'\n"
                f"  Enviroment:                 '{settings.ENVIRONMENT}'\n" +
                f"  Debug:                      '{str(settings.DEBUG)}'\n" +
                f"  Allowed Hosts:              '{settings.allowed_origins_list}'\n" +
                f"  Secret Key:                 '{settings.SECRET_KEY}'\n" +
                f"  Algorithm:                  '{settings.ALGORITHM}'\n" +
                f"  Access Token Expire Min:    '{settings.ACCESS_TOKEN_EXPIRE_MINUTES}'\n" +
                f"  Refresh Token Expire Days:  '{settings.REFRESH_TOKEN_EXPIRE_DAYS}'\n" +
                f"  Database URL:               '{settings.DATABASE_URL}'\n"
            )
        else:
            logger.info("Enviroment is detected as production and so configuration is hidden")

    # begin database
    logger.info("Begining Database\n")

    try:
        async with engine.begin() as conn:
            # Alembic replaced this:
            # await conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext;"))
            # await conn.run_sync(Base.metadata.create_all)

            await conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Error While begining database '{settings.DATABASE_URL}': {e}")

    logger.info("Backend API Initialized!\n")
    yield

    logger.info("Stopping storage manager")
    await storage.async_close()

    logger.info("Stopping/dispossing Database")
    await engine.dispose()

    logger.info("----- %s Stopped -----", app.title)

# app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=f"Backend API for {settings.APP_NAME}",
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

app.include_router(auth,        prefix=API_PREFIX)
app.include_router(users,       prefix=API_PREFIX)
app.include_router(media,       prefix=API_PREFIX)

# Health & Meta
@app.get("/api/health", tags=["Meta"])
async def health_check():
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }
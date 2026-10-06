"""
Configurable application logging.

Quick start
```
    from core.logging import LoggingConfig, configure_logging

    logger = configure_logging(
        LoggingConfig(
            name="Unified Logger",
            directory=".logs",
            filename="api.log",
            level="DEBUG",
            file_level="DEBUG",
            console_level="INFO",
            console=True,
            file=True,
            rotate=True,
            max_bytes=10_000_000,
            backup_count=3,
            encoding="utf-8",
            log_format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            date_format="%Y-%m-%d %H:%M:%S",
            console_stream="stderr",
            propagate=False,
            capture_root=True,
        )
    )
    logger.info("API started")
    logger.warning("A warning with context: %s", "details")
    try:
        1 / 0
    except ZeroDivisionError:
        logger.exception("An operation failed")

Configure once during application startup, before importing modules that create
their loggers. In any other module, get a child logger like this::

    from core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("This message uses the application's configured handlers")

``get_logger()`` without a name returns the configured application logger.
With a module name, it returns a child logger that propagates messages to the
configured application logger. Do not call ``configure_logging()`` in every
module. ``capture_root=True`` also routes otherwise-propagating third-party
library logs through these handlers.
```
Configuration options
---------------------
* ``name`` (default ``"Unified Logger"``) selects the named Python logger.

* ``directory`` (default ``".logs"``) and ``filename`` (default ``"app.log"``)
  choose the file location. Missing parent directories are created
  automatically, and ``filename`` may itself include subdirectories.

* ``level`` (default ``logging.INFO``) is the logger-wide minimum severity.
  ``file_level`` and ``console_level`` are independent minimum severities for
  the file and console handlers. For example, ``file_level="DEBUG"`` and
  ``console_level="INFO"`` write debug messages to the file while keeping them
  off the terminal. A record must pass both the logger-wide level and its
  handler's level to be emitted. Either handler level may be ``None`` (the
  default) to use ``level``. Levels can be standard names such as
  ``"DEBUG"``, ``"INFO"``, ``"WARNING"``, ``"ERROR"``, ``"CRITICAL"``, or
  their integer values.

* ``file`` and ``console`` (both default ``True``) independently enable file
  and terminal output.

* ``rotate`` (default ``True``) enables size-based rotation. 

* ``max_bytes`` (default ``10_000_000``) is the maximum file size before rotation, and
  ``backup_count`` (default ``5``) is the number of rotated backups to retain.
  Set ``rotate=False`` to use a regular file handler.

* ``encoding`` (default ``"utf-8"``) selects the file encoding.

* ``log_format`` and ``date_format`` control the message and timestamp
  formatting. Their defaults are ``"%(asctime)s | %(levelname)s | %(name)s |
  %(message)s"`` and ``"%Y-%m-%d %H:%M:%S"``.

* ``console_stream`` (default ``"stderr"``) chooses ``"stderr"`` or
  ``"stdout"`` for terminal output.
  
* ``propagate`` (default ``False``) controls whether records are also passed
  to the root logger.
* ``capture_root`` (default ``False``) attaches these handlers to the root
  logger too, so records from other libraries can use the same destinations.
  The configured application logger does not propagate, preventing its own
  records from being handled twice.

Calling ``configure_logging`` again with the same logger name replaces only
handlers created by this module, so repeated setup does not duplicate output
and handlers owned by other code are left untouched.
"""

from dataclasses import dataclass
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
from typing import Literal


_MANAGED_HANDLER_ATTRIBUTE = "_anime_streamer_managed"
_DEFAULT_LOGGER_NAME = "Unified Logger"
_DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_configured_logger_name = _DEFAULT_LOGGER_NAME
_root_original_level: int | None = None


@dataclass
class LoggingConfig:
    """Options for :func:`configure_logging`."""

    name: str = _DEFAULT_LOGGER_NAME
    directory: str | Path = ".logs"
    filename: str = "app.log"
    level: int | str = logging.INFO
    file_level: int | str | None = None
    console_level: int | str | None = None
    file: bool = True
    console: bool = True
    rotate: bool = True
    max_bytes: int = 10_000_000
    backup_count: int = 5
    encoding: str = "utf-8"
    log_format: str = _DEFAULT_FORMAT
    date_format: str = _DEFAULT_DATE_FORMAT
    console_stream: Literal["stdout", "stderr"] = "stderr"
    propagate: bool = False
    capture_root: bool = False


def _resolve_level(level: int | str) -> int:
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        resolved = logging.getLevelNamesMapping().get(level.upper())
        if isinstance(resolved, int):
            return resolved
    raise ValueError(f"Invalid logging level: {level!r}")


def configure_logging(config: LoggingConfig | None = None) -> logging.Logger:
    """Create or configure a logger and return it for application use."""
    global _configured_logger_name, _root_original_level

    if config is None:
        config = LoggingConfig()

    if not config.name:
        raise ValueError("Logger name must not be empty")
    if config.max_bytes < 0:
        raise ValueError("max_bytes must be zero or greater")
    if config.backup_count < 0:
        raise ValueError("backup_count must be zero or greater")
    if config.file and not config.filename:
        raise ValueError("filename must not be empty when file logging is enabled")
    if config.console_stream not in ("stdout", "stderr"):
        raise ValueError("console_stream must be either 'stdout' or 'stderr'")

    logger_level = _resolve_level(config.level)
    file_level = _resolve_level(
        config.level if config.file_level is None else config.file_level
    )
    console_level = _resolve_level(
        config.level if config.console_level is None else config.console_level
    )
    formatter = logging.Formatter(config.log_format, datefmt=config.date_format)
    new_handlers: list[logging.Handler] = []

    try:
        if config.file:
            log_path = Path(config.directory) / config.filename
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if config.rotate:
                file_handler: logging.Handler = RotatingFileHandler(
                    log_path,
                    maxBytes=config.max_bytes,
                    backupCount=config.backup_count,
                    encoding=config.encoding,
                )
            else:
                file_handler = logging.FileHandler(log_path, encoding=config.encoding)
            file_handler.setLevel(file_level)
            file_handler.setFormatter(formatter)
            setattr(file_handler, _MANAGED_HANDLER_ATTRIBUTE, True)
            new_handlers.append(file_handler)

        if config.console:
            stream = sys.stdout if config.console_stream == "stdout" else sys.stderr
            console_handler = logging.StreamHandler(stream)
            console_handler.setLevel(console_level)
            console_handler.setFormatter(formatter)
            setattr(console_handler, _MANAGED_HANDLER_ATTRIBUTE, True)
            new_handlers.append(console_handler)
    except Exception:
        for handler in new_handlers:
            handler.close()
        raise

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if getattr(handler, _MANAGED_HANDLER_ATTRIBUTE, False):
            root_logger.removeHandler(handler)

    logger = logging.getLogger(config.name)
    for handler in logger.handlers[:]:
        if getattr(handler, _MANAGED_HANDLER_ATTRIBUTE, False):
            logger.removeHandler(handler)
            handler.close()

    logger.setLevel(logger_level)
    logger.propagate = config.propagate
    for handler in new_handlers:
        logger.addHandler(handler)

    if config.capture_root:
        if _root_original_level is None:
            _root_original_level = root_logger.level
        root_logger.setLevel(logger_level)
        for handler in new_handlers:
            root_logger.addHandler(handler)
    elif _root_original_level is not None:
        root_logger.setLevel(_root_original_level)
        _root_original_level = None

    _configured_logger_name = config.name
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return the configured application logger or one of its child loggers.

    Call :func:`configure_logging` once during application startup before
    obtaining module loggers with this function.
    """
    if not name:
        return logging.getLogger(_configured_logger_name)
    if name == _configured_logger_name or name.startswith(
        f"{_configured_logger_name}."
    ):
        return logging.getLogger(name)
    return logging.getLogger(f"{_configured_logger_name}.{name}")
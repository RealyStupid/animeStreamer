# `core/logging.py` — Configurable Application Logging

This module configures named Python loggers and their file/console handlers.
The FastAPI application calls `configure_logging` during startup module import
and obtains module loggers with `get_logger`. Storage diagnostics use a
separate named logger configured in `api/main.py`; see
[`storage.md`](./storage.md).

## Quick start

```python
from core.logging import LoggingConfig, configure_logging, get_logger

configure_logging(
    LoggingConfig(
        name="AnimeWatcher API",
        directory=".logs",
        filename="api.log",
        level="INFO",
        file=True,
        console=True,
        rotation_type="time",
        rotation_when="midnight",
        backup_count=3,
    )
)

logger = get_logger(__name__)
logger.info("Service ready")
```

Configure once, before obtaining module loggers. Reconfiguring the same
application logger replaces handlers managed by this module; configuring in
every module is unnecessary and can make lifecycle/ownership harder to
understand.

## `LoggingConfig`

`LoggingConfig` is a dataclass. Its options and defaults are:

| Option | Default | Description |
|---|---|---|
| `name` | `"Unified Logger"` | Logger name. Must not be empty. |
| `directory` | `".logs"` | Base log directory. |
| `filename` | `"app.log"` | File name, optionally including subdirectories. Required when `file=True`. |
| `level` | `logging.INFO` | Logger-wide severity threshold. |
| `file_level` | `None` | File handler threshold; defaults to `level`. |
| `console_level` | `None` | Console handler threshold; defaults to `level`. |
| `file` | `True` | Enable file output. |
| `console` | `True` | Enable console output. |
| `rotate` | `True` | Backward-compatible rotation selector if `rotation_type` is omitted (`True` means size, `False` means none). |
| `rotation_type` | `None` | One of `"size"`, `"time"`, `"watched"`, `"none"`; if omitted, derived from `rotate`. |
| `max_bytes` | `10_000_000` | Size limit for size-based rotation; must be non-negative. |
| `backup_count` | `5` | Number of old rotated logs to retain; must be non-negative. |
| `rotation_when` | `"midnight"` | Time schedule for timed rotation. |
| `rotation_interval` | `1` | Positive multiplier for the timed-rotation unit. |
| `rotation_utc` | `False` | Use UTC for timed rotation. |
| `rotation_at_time` | `None` | Optional `datetime.time` for midnight/weekly rotation. |
| `delay` | `False` | Delay opening a file until first use. |
| `encoding` | `"utf-8"` | File text encoding. |
| `errors` | `None` | Encoding error policy passed to the handler. |
| `log_format` | timestamp/level/name/message | `logging.Formatter` format string. |
| `date_format` | `"%Y-%m-%d %H:%M:%S"` | Timestamp format. |
| `console_stream` | `"stderr"` | `"stdout"` or `"stderr"`. |
| `propagate` | `False` | Whether the configured logger also propagates to ancestors. |
| `capture_root` | `False` | Attach configured handlers to Python's root logger to capture propagating third-party logs. |

### Severity filtering

A record must pass the logger level and the selected handler's level. For
example, a logger at `DEBUG` with a file handler at `DEBUG` and console handler
at `INFO` writes debug messages to the file while omitting them from the
console.

Levels can be standard names (`"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`,
`"CRITICAL"`) or integer logging levels. Invalid strings raise `ValueError`;
they are not treated as `INFO`.

### Rotation modes

- `"size"` uses `RotatingFileHandler` with `max_bytes` and `backup_count`.
- `"time"` uses `TimedRotatingFileHandler`. Supported `rotation_when` values
  are `"S"`, `"M"`, `"H"`, `"D"`, `"midnight"`, and weekdays `"W0"` through
  `"W6"` (case-insensitive check). `rotation_interval` must be at least `1`.
- `"watched"` uses `WatchedFileHandler` for external rotation such as logrotate.
  This mode is intended for Unix-like platforms and does not itself rotate or
  retain backups.
- `"none"` uses a normal `FileHandler`.

The handler implementation determines the exact rotation timing semantics.
`backup_count=0` is permitted and means no rotated backups are retained. The
configuration validates `rotation_when` even if a non-time mode is selected.

## `configure_logging(config=None)`

If `config` is omitted, uses the `LoggingConfig` defaults. It validates the
configuration, creates enabled handlers, formats records, and then:

1. removes and closes module-managed handlers previously attached to the
   process root logger;
2. removes and closes module-managed handlers from the named logger;
3. sets its level and propagation setting;
4. attaches the newly created handlers to that named logger; and
5. if `capture_root=True`, attaches the same handler objects to the root logger
   and changes root level to the configured logger level.

Only handlers carrying this module's private managed-handler marker are
replaced. Handlers installed by other code are deliberately left alone on the
named logger. Root logger managed handlers are removed during reconfiguration.

When root capture is disabled after a prior capture, the original root level is
restored. Root capture does not make the configured application logger
propagate: `propagate` remains controlled by the explicit config option.

Errors creating parent directories, opening files, or constructing handlers
are not silently ignored. Any handlers created before a setup failure are
closed, and the exception is raised.

### Root capture and duplicate output

`capture_root=True` adds the configured handlers to the root logger so
third-party records that propagate to root can use them. If another logger
also owns/uses the same handlers or propagates unexpectedly, duplicate output
may occur. Named child loggers returned by `get_logger(__name__)` propagate to
the configured app logger; that app logger defaults to `propagate=False`, which
prevents its own records from also reaching root.

The API's separate storage logger has its own file handler and
`propagate=False`, deliberately preventing storage messages from appearing in
the main API log or console.

## `get_logger(name=None)`

- `get_logger()` or `get_logger("")` returns the currently configured
  application logger.
- If `name` equals the configured logger name or already starts with
  `<configured-name>.`, it returns that exact named logger.
- Otherwise the function prefixes the configured logger name and a dot. For
  example, with configured name `"AnimeWatcher API"`,
  `get_logger("core.database")` resolves to
  `"AnimeWatcher API.core.database"`.

The configured root name is module-global and is updated by the most recent
`configure_logging` call. A logger retrieved before a later reconfiguration is
still a Python logger object, but handler/propagation behavior can change as
that named logger is configured.

## API integration and log paths

`api/main.py` configures the app logger with a daily log file in `.logs` and
sets `capture_root=True`. It separately creates a storage logger named
`<APP_NAME>.storage`, sets its own level and `propagate=False`, then attaches a
daily rotating `.logs/storage.log` handler retaining three backups. That
separate handler is managed directly in `main.py`, not through
`configure_logging`.

Changing the API logger's handlers does not automatically change the custom
storage logger's handler. Conversely, changing storage logger configuration
does not replace the API logger's handlers.


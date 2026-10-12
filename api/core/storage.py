"""Indexed, quota-aware local storage for untrusted show uploads.

Quick start
===========

1. Create one manager when the API starts and reuse it for requests. A relative
   storage path is resolved from the process working directory; an absolute
   path can point to another mounted drive. Adding a location creates the
   directory, a small SQLite index at its root, and a lock file used to
   coordinate concurrent writers:
       from core.storage import StorageManager

       storage = StorageManager(
           default_path=".localstorage",
           default_allocation="500 GiB",
           reconciliation_interval_seconds=5,
           debug=True,
           print_debug=False,
           logger=my_storage_logger,
       )

   For FastAPI, keep one manager on ``app.state`` and stop its monitor during
   application shutdown:

       from contextlib import asynccontextmanager
       from fastapi import FastAPI
       from core.storage import StorageManager

       @asynccontextmanager
       async def lifespan(app: FastAPI):
           storage_logger = get_logger("core.storage")
           app.state.storage = StorageManager(
               ".localstorage",
               "500 GiB",
               reconciliation_interval_seconds=5,
               debug=settings.DEBUG,
               logger=storage_logger,
           )
           try:
               yield
           finally:
               await app.state.storage.async_close()

       app = FastAPI(lifespan=lifespan)

   The first time a location is registered, every existing entry not already
   recorded in its SQLite index is deleted. Back up or move anything you want
   to keep before registering an existing directory. The index database,
   SQLite sidecars, and lock file are internal metadata and are not storage
   entries. A background monitor then reconciles every registered root on a
   timer; by default, unindexed files/folders created outside this manager are
   removed within about five seconds. Set
   ``reconciliation_interval_seconds=None`` to disable the monitor (manual
   reconciliation still works). Always call ``storage.close()`` during API
   shutdown so the monitor thread exits.

   ``debug=True`` enables detailed operation traces. ``print_debug=True`` also
   prints those DEBUG messages to stdout (leave it false for normal servers).
   Pass any logger implementing the standard ``debug/info/warning/error/
   exception`` methods to route storage logs through your application's
   handlers. The same logger and flags are shared with every added storage
   root. You can toggle ``storage.debug`` or ``storage.print_debug`` later;
   changes apply to already-registered roots and the background monitor.

2. Optionally register more locations, for example a directory on a separate
   disk. Each storage location has its own index and quota:

       archive_id = await storage.async_add_storage(
           "/mnt/archive/.storage",
           allocation="2 TiB",
           storage_id="archive",
       )

   Allocations accept integer byte counts or decimal/binary size strings such
   as ``"20 GB"``, ``"20 GiB"``, or ``"500 MB"``. Omitting ``allocation``
   disables the per-location quota, but available physical filesystem space is
   still checked. The manager keeps a 64 MiB free-space reserve by default.
   Set ``minimum_free_bytes=0`` only when that reserve is not wanted.

3. Make folders through the manager so they are recorded in the index. Paths
   are relative to the selected storage root; parent folders are created and
   indexed as needed:

       await storage.async_add_directory(
           "shows/space-opera", storage_id=archive_id
       )

4. Pass FastAPI's ``UploadFile`` (or another async object with ``read(size)``)
   directly to ``save_upload``. Without ``storage_id``, the manager automatically
   picks the registered root with the most available space that can fit the
   complete upload. FastAPI's ``UploadFile.size`` is used to make that decision
   before the request body is written. If no root can fit it, the call raises
   ``InsufficientStorageError``; it never silently falls back to a partially
   written file. If an async upload stream has no ``size`` attribute (or its
   value is ``None``), placement uses the root with the most currently
   available bytes and capacity is still checked as chunks arrive. You can
   still pass ``storage_id`` to pin an upload to one specific root. You can
   also select an existing indexed destination
   directory. The original client filename is used only to select an allowed
   extension; the stored filename is random and cannot contain client path
   components:

       stored = await storage.save_upload(
           upload=upload_file,
           filename=upload_file.filename or "",
           # Omit storage_id for automatic placement, or supply archive_id
           # to pin this upload to that storage.
           directory="shows/space-opera",
       )

   ``stored.storage_id`` tells you which root was selected. ``stored.filename``
   is the generated basename. ``stored.path`` is the absolute local path, and
   ``stored.media_type``, ``stored.size_bytes``, and ``stored.sha256`` describe
   the accepted content. Persist the storage ID and generated filename (or a
   relative path) in the application's SQL database; do not treat the local
   absolute path as a portable URL. The manager's SQLite database is only its
   filesystem index and does not replace the application's SQL database.

5. Inspect indexed contents, quota, and reconciliation results:

       entries = await storage.async_list_entries(storage_id=archive_id)
       info = await storage.async_get_storage(archive_id)
       print(info.used_bytes, info.available_bytes)
       report = await storage.async_reconcile_storage(archive_id)
       print(report.removed_count, report.indexed_count)

   Every listed entry is a ``StorageEntry`` with a root-relative POSIX path,
   kind, byte size, and modification time. The root directory itself has the
   empty relative path. ``list_entries`` reconciles before returning, so
   external/unindexed additions are purged first. Reconciliation also removes
   stale index rows for files that were externally deleted.

   The background monitor runs separately from API requests. It logs
   reconciliation errors and retries on the next interval; errors in explicit
   reconciliation calls are raised to the caller.

   Storage diagnostics use one shared logger for every registered location.
   The logger is independent of the API logger, so storage messages do not
   clutter the main API log. Configure detailed traces or console printing:

       import logging
       from core.logging import get_logger

       from logging.handlers import TimedRotatingFileHandler

       storage_logger = logging.getLogger("api.storage")
       storage_logger.setLevel(logging.DEBUG)
       storage_logger.propagate = False
       file_handler = TimedRotatingFileHandler(
           ".logs/storage.log",
           when="midnight",
           backupCount=3,
           encoding="utf-8",
       )
       file_handler.setFormatter(logging.Formatter(
           "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
       ))
       storage_logger.addHandler(file_handler)
       storage.debug = True          # detailed DEBUG messages via logger
       storage.print_debug = True    # also print DEBUG messages to stdout
       storage.logger = storage_logger

   Alternatively, pass ``debug=True``, ``print_debug=True``, and/or
   ``logger=storage_logger`` to ``StorageManager`` at construction. Logger
   messages include manager startup/shutdown, roots and quotas, SQLite index
   setup, upload stages and size/hash, capacity checks, directory and entry
   operations, reconciliation counts/removals, and monitor errors. Upload
   contents are never logged. ``print_debug`` is off by default; normal
   INFO/WARNING/ERROR messages always go only to the configured logger. To
   store them in a separate file, attach a file handler to this named logger
   and set ``propagate=False``; the API application configures
   ``.logs/storage.log`` with daily rotation and three backups.

6. Delete entries with ``remove``. Directories are recursively removed by
   default; set ``recursive=False`` to reject a non-empty directory:

       await storage.async_remove(
           "shows/space-opera/episode-01.mp4", storage_id=archive_id
       )
       await storage.async_remove("shows/space-opera", storage_id=archive_id)

   Removing the storage root itself is prohibited. Add and delete operations
   update disk and SQLite index under the storage lock. Keep the manager's
   internal database and lock files in place while the location is registered.
   The synchronous methods are useful in scripts and tests. API handlers should
   use the corresponding ``async_*`` methods so lock waits and filesystem work
   do not block the server's event loop.

Storage exceptions
==================

``InsufficientStorageError`` means the configured allocation or available
filesystem space (including its reserve) would be exceeded. ``InvalidUploadError``
means the upload is empty, malformed, or invalid UTF-8 text.
``UnsupportedFileTypeError`` means the extension is not allowed or its content
signature does not match. ``StorageError`` reports general storage/index
problems. Catch these at the API boundary and return an appropriate response;
do not convert an exception into a success response.

Tests and safety
================

From the repository root, run the focused tests with:

    cd api
    source ../.venv/bin/activate
    python -m unittest discover -s tests -p 'test_storage.py' -v

Tests use temporary directories and streams, so they exercise real SQLite,
file, folder, upload, quota, removal, and reconciliation behavior without
touching a production storage path. They do not connect to or verify the SQL
database used by the API.

The allowlist covers common image/video containers and UTF-8 ``.txt``, ``.srt``,
and ``.vtt``. Extension/signature and basic boundary checks are not a full media
decoder or malware scanner. Keep uploads private and serve them as attachments
unless a trusted media pipeline has processed them.
"""

from __future__ import annotations

import asyncio
import codecs
import errno
import hashlib
import importlib
import logging
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import threading
import time
import unicodedata
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import AsyncGenerator, Generator, Protocol


_CHUNK_SIZE = 1024 * 1024
_DEFAULT_MINIMUM_FREE_BYTES = 64 * 1024 * 1024
_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}
_VIDEO_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
}
_TEXT_TYPES = {
    ".txt": "text/plain",
    ".srt": "text/plain",
    ".vtt": "text/plain",
}
_STORAGE_ID_RE = re.compile(r"^(?!\.{1,2}$)[A-Za-z0-9._-]{1,64}$")
_SIZE_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(b|kb|mb|gb|tb|kib|mib|gib|tib)?\s*$",
    re.IGNORECASE,
)
_DECIMAL_MULTIPLIERS = {
    "b": 1,
    "kb": 1_000,
    "mb": 1_000_000,
    "gb": 1_000_000_000,
    "tb": 1_000_000_000_000,
}
_BINARY_MULTIPLIERS = {
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}
_INDEX_FILENAME = ".storage-index.sqlite3"
_LOCK_FILENAME = ".storage.lock"
_INDEX_METADATA_NAMES = {
    _INDEX_FILENAME,
    f"{_INDEX_FILENAME}-journal",
    f"{_INDEX_FILENAME}-wal",
    f"{_INDEX_FILENAME}-shm",
    _LOCK_FILENAME,
}


@contextmanager
def _exclusive_storage_lock_sync(path: Path) -> Generator[None, None, None]:
    lock_path = path / _LOCK_FILENAME
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    file_descriptor = os.open(lock_path, flags, 0o600)
    locked = False
    is_windows = os.name == "nt"
    lock_module = importlib.import_module("msvcrt" if is_windows else "fcntl")

    try:
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            raise StorageError(f"Storage lock is not a regular file: {lock_path}")
        if is_windows and os.fstat(file_descriptor).st_size == 0:
            os.write(file_descriptor, b"\0")

        while not locked:
            try:
                if is_windows:
                    os.lseek(file_descriptor, 0, os.SEEK_SET)
                    lock_module.locking(file_descriptor, lock_module.LK_NBLCK, 1)
                else:
                    lock_module.flock(
                        file_descriptor,
                        lock_module.LOCK_EX | lock_module.LOCK_NB,
                    )
                locked = True
            except BlockingIOError:
                time.sleep(0.05)
            except OSError as exc:
                if not is_windows or exc.errno not in {
                    errno.EACCES,
                    errno.EDEADLK,
                }:
                    raise
                time.sleep(0.05)
        yield
    finally:
        if locked:
            if is_windows:
                os.lseek(file_descriptor, 0, os.SEEK_SET)
                lock_module.locking(file_descriptor, lock_module.LK_UNLCK, 1)
            else:
                lock_module.flock(file_descriptor, lock_module.LOCK_UN)
        os.close(file_descriptor)


@asynccontextmanager
async def _exclusive_storage_lock(path: Path) -> AsyncGenerator[None, None]:
    lock_path = path / ".storage.lock"
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    file_descriptor = os.open(lock_path, flags, 0o600)
    locked = False
    is_windows = os.name == "nt"
    lock_module = importlib.import_module("msvcrt" if is_windows else "fcntl")

    try:
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            raise StorageError(f"Storage lock is not a regular file: {lock_path}")

        if is_windows and os.fstat(file_descriptor).st_size == 0:
            os.write(file_descriptor, b"\0")

        while not locked:
            try:
                if is_windows:
                    os.lseek(file_descriptor, 0, os.SEEK_SET)
                    lock_module.locking(file_descriptor, lock_module.LK_NBLCK, 1)
                else:
                    lock_module.flock(
                        file_descriptor,
                        lock_module.LOCK_EX | lock_module.LOCK_NB,
                    )
                locked = True
            except BlockingIOError:
                await asyncio.sleep(0.05)
            except OSError as exc:
                if not is_windows or exc.errno not in {
                    errno.EACCES,
                    errno.EDEADLK,
                }:
                    raise
                await asyncio.sleep(0.05)

        yield
    finally:
        if locked:
            if is_windows:
                os.lseek(file_descriptor, 0, os.SEEK_SET)
                lock_module.locking(
                    file_descriptor, lock_module.LK_UNLCK, 1
                )
            else:
                lock_module.flock(file_descriptor, lock_module.LOCK_UN)
        os.close(file_descriptor)


class StorageError(Exception):
    """Base error for storage configuration and upload failures."""


class InvalidUploadError(StorageError):
    """The upload is empty, malformed, or invalid for its declared type."""


class UnsupportedFileTypeError(InvalidUploadError):
    """The file extension or detected content type is not allowed."""


class InsufficientStorageError(StorageError):
    """A quota, filesystem reserve, or physical disk limit was reached."""


class AsyncReadable(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class SizedAsyncReadable(AsyncReadable, Protocol):
    size: int | None


class StorageLogger(Protocol):
    """Logger interface accepted by ``StorageManager``."""

    def debug(self, message: str, *args: object, **kwargs: object) -> None: ...

    def info(self, message: str, *args: object, **kwargs: object) -> None: ...

    def warning(self, message: str, *args: object, **kwargs: object) -> None: ...

    def error(self, message: str, *args: object, **kwargs: object) -> None: ...

    def exception(self, message: str, *args: object, **kwargs: object) -> None: ...


@dataclass
class _StorageLogging:
    logger: StorageLogger
    debug: bool
    print_debug: bool

    def debug_message(self, message: str, *args: object) -> None:
        if not (self.debug or self.print_debug):
            return
        self.logger.debug(message, *args)
        if self.print_debug:
            print("[storage DEBUG] " + (message % args if args else message))

    def info(self, message: str, *args: object) -> None:
        self.logger.info(message, *args)

    def warning(self, message: str, *args: object) -> None:
        self.logger.warning(message, *args)

    def error(self, message: str, *args: object) -> None:
        self.logger.error(message, *args)

    def exception(self, message: str, *args: object) -> None:
        self.logger.exception(message, *args)


@dataclass(frozen=True)
class StorageInfo:
    storage_id: str
    path: Path
    allocation_bytes: int | None
    used_bytes: int
    available_bytes: int
    filesystem_free_bytes: int


@dataclass(frozen=True)
class StorageEntry:
    storage_id: str
    relative_path: str
    is_directory: bool
    size_bytes: int
    modified_ns: int


@dataclass(frozen=True)
class ReconcileReport:
    storage_id: str
    indexed_count: int
    removed_count: int


@dataclass(frozen=True)
class StoredObject:
    storage_id: str
    path: Path
    filename: str
    media_type: str
    size_bytes: int
    sha256: str


@dataclass
class _StorageLocation:
    storage_id: str
    path: Path
    allocation_bytes: int | None
    lock: asyncio.Lock
    logging: _StorageLogging


def parse_size(value: int | str) -> int:
    """Convert a byte count or a human-readable size (for example, ``2 GiB``)."""
    if isinstance(value, bool):
        raise ValueError("A storage allocation must be a byte count or size string.")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("A storage allocation cannot be negative.")
        return value
    if not isinstance(value, str):
        raise ValueError("A storage allocation must be a byte count or size string.")

    match = _SIZE_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"Invalid storage size: {value!r}")

    amount, unit = match.groups()
    normalized_unit = (unit or "b").lower()
    multiplier = _DECIMAL_MULTIPLIERS.get(
        normalized_unit, _BINARY_MULTIPLIERS.get(normalized_unit)
    )
    try:
        return int(Decimal(amount) * multiplier)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid storage size: {value!r}") from exc


class _UploadValidator:
    def __init__(self, extension: str, header: bytes) -> None:
        self.extension = extension
        self.header = header[:32]
        self.tail = b""
        self.total_bytes = 0
        self.media_type = self._detect_type(header)
        self._text_decoder = (
            codecs.getincrementaldecoder("utf-8")("strict")
            if self.media_type == "text/plain"
            else None
        )

    def _detect_type(self, header: bytes) -> str:
        if self.extension in _TEXT_TYPES:
            return _TEXT_TYPES[self.extension]

        if self.extension in _IMAGE_TYPES:
            signatures = {
                ".jpg": header.startswith(b"\xff\xd8\xff"),
                ".jpeg": header.startswith(b"\xff\xd8\xff"),
                ".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
                ".gif": header.startswith((b"GIF87a", b"GIF89a")),
                ".webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
                ".bmp": header.startswith(b"BM"),
                ".tif": header.startswith((b"II*\x00", b"MM\x00*")),
                ".tiff": header.startswith((b"II*\x00", b"MM\x00*")),
            }
            if signatures[self.extension]:
                return _IMAGE_TYPES[self.extension]
            raise UnsupportedFileTypeError(
                "The file content does not match its image extension."
            )

        if self.extension in _VIDEO_TYPES:
            is_mp4 = (
                self.extension in {".mp4", ".m4v", ".mov"}
                and len(header) >= 12
                and header[4:8] == b"ftyp"
            )
            is_ebml = (
                self.extension in {".mkv", ".webm"}
                and header.startswith(b"\x1a\x45\xdf\xa3")
            )
            is_avi = (
                self.extension == ".avi"
                and len(header) >= 12
                and header[:4] == b"RIFF"
                and header[8:12] == b"AVI "
            )
            if is_mp4 or is_ebml or is_avi:
                return _VIDEO_TYPES[self.extension]
            raise UnsupportedFileTypeError(
                "The file content does not match its video extension."
            )

        raise UnsupportedFileTypeError(
            "Only common image/video formats and UTF-8 text or subtitle files are allowed."
        )

    def feed(self, chunk: bytes) -> None:
        if self._text_decoder is not None:
            try:
                text = self._text_decoder.decode(chunk)
            except UnicodeDecodeError as exc:
                raise InvalidUploadError(
                    "Text uploads must contain valid UTF-8."
                ) from exc
            for character in text:
                if (
                    unicodedata.category(character) == "Cc"
                    and character not in "\t\n\r\f"
                ):
                    raise InvalidUploadError(
                        "Text uploads cannot contain control characters."
                    )
        self.total_bytes += len(chunk)
        self.tail = (self.tail + chunk)[-16:]

    def finish(self) -> None:
        if self.total_bytes == 0:
            raise InvalidUploadError("Empty uploads are not allowed.")

        if self._text_decoder is not None:
            try:
                self._text_decoder.decode(b"", final=True)
            except UnicodeDecodeError as exc:
                raise InvalidUploadError(
                    "Text uploads must contain valid UTF-8."
                ) from exc
            return

        if self.extension in {".jpg", ".jpeg"}:
            valid = self.tail.endswith(b"\xff\xd9")
        elif self.extension == ".png":
            valid = self.tail.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")
        elif self.extension == ".gif":
            valid = self.tail.endswith(b";")
        elif self.extension == ".webp":
            valid = (
                self.header[:4] == b"RIFF"
                and int.from_bytes(self.header[4:8], "little")
                == self.total_bytes - 8
            )
        elif self.extension == ".bmp":
            valid = int.from_bytes(self.header[2:6], "little") == self.total_bytes
        elif self.extension in {".tif", ".tiff"}:
            valid = len(self.header) >= 4
        elif self.extension in {".mp4", ".m4v", ".mov"}:
            box_size = int.from_bytes(self.header[:4], "big")
            valid = box_size == 0 or box_size <= self.total_bytes
            if box_size == 1:
                valid = (
                    len(self.header) >= 16
                    and int.from_bytes(self.header[8:16], "big")
                    <= self.total_bytes
                )
        elif self.extension in {".mkv", ".webm"}:
            valid = self.header.startswith(b"\x1a\x45\xdf\xa3")
        else:
            valid = (
                int.from_bytes(self.header[4:8], "little")
                == self.total_bytes - 8
            )

        if not valid:
            raise InvalidUploadError(
                "The file content is truncated or malformed for its declared type."
            )


class StorageManager:
    """Manage multiple local storage roots and stream uploads within their limits."""

    def __init__(
        self,
        default_path: str | Path = ".localstorage",
        default_allocation: int | str | None = None,
        *,
        minimum_free_bytes: int | str = _DEFAULT_MINIMUM_FREE_BYTES,
        reconciliation_interval_seconds: float | None = 5.0,
        debug: bool = False,
        print_debug: bool = False,
        logger: StorageLogger | None = None,
    ) -> None:
        if reconciliation_interval_seconds is not None and (
            not isinstance(reconciliation_interval_seconds, (int, float))
            or isinstance(reconciliation_interval_seconds, bool)
            or not 0 < reconciliation_interval_seconds < float("inf")
        ):
            raise ValueError(
                "Reconciliation interval must be a positive finite number or None."
            )
        if not isinstance(debug, bool) or not isinstance(print_debug, bool):
            raise ValueError("debug and print_debug must be boolean values.")
        if logger is not None and not all(
            callable(getattr(logger, method, None))
            for method in ("debug", "info", "warning", "error", "exception")
        ):
            raise TypeError(
                "logger must provide debug, info, warning, error, and exception methods."
            )
        self.minimum_free_bytes = parse_size(minimum_free_bytes)
        self._logging = _StorageLogging(
            logger=(
                logger
                if logger is not None
                else logging.getLogger("core.storage")
            ),
            debug=debug,
            print_debug=print_debug,
        )
        self._locations: dict[str, _StorageLocation] = {}
        self._paths: set[Path] = set()
        self._registry_lock = threading.RLock()
        self._reconciliation_interval_seconds = reconciliation_interval_seconds
        self._stop_monitor = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._log_debug(
            "Creating storage manager (default_path=%s, allocation_bytes=%s, "
            "reconciliation_interval_seconds=%s, debug=%s, print_debug=%s).",
            default_path,
            None if default_allocation is None else parse_size(default_allocation),
            reconciliation_interval_seconds,
            debug,
            print_debug,
        )
        self.default_storage_id = self.add_storage(
            default_path, default_allocation
        )
        if reconciliation_interval_seconds is not None:
            self._monitor_thread = threading.Thread(
                target=self._monitor_storage_roots,
                name="local-storage-reconciler",
                daemon=True,
            )
            self._monitor_thread.start()
            self._log_debug(
                "Started reconciliation monitor thread '%s'.",
                self._monitor_thread.name,
            )
        self._logging.info(
            "Storage manager ready (default_storage_id='%s', debug=%s, "
            "print_debug=%s, reconciliation_interval_seconds=%s).",
            self.default_storage_id,
            self.debug,
            self.print_debug,
            reconciliation_interval_seconds,
        )

    @property
    def logger(self) -> StorageLogger:
        """Logger shared by the manager, all registered roots, and its monitor."""
        return self._logging.logger

    @logger.setter
    def logger(self, value: StorageLogger) -> None:
        if not all(
            callable(getattr(value, method, None))
            for method in ("debug", "info", "warning", "error", "exception")
        ):
            raise TypeError(
                "logger must provide debug, info, warning, error, and exception methods."
            )
        self._logging.logger = value

    @property
    def debug(self) -> bool:
        """Whether to emit detailed storage operations at DEBUG level."""
        return self._logging.debug

    @debug.setter
    def debug(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise ValueError("debug must be a boolean value.")
        self._logging.debug = value

    @property
    def print_debug(self) -> bool:
        """Whether to print detailed DEBUG messages to stdout as well as log."""
        return self._logging.print_debug

    @print_debug.setter
    def print_debug(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise ValueError("print_debug must be a boolean value.")
        self._logging.print_debug = value

    def _log_debug(self, message: str, *args: object) -> None:
        self._logging.debug_message(message, *args)

    def add_storage(
        self,
        path: str | Path,
        allocation: int | str | None = None,
        *,
        storage_id: str | None = None,
    ) -> str:
        """Create and register a writable storage directory, returning its ID."""
        configured_path = Path(path).expanduser()
        configured_path.mkdir(parents=True, exist_ok=True)
        resolved_path = configured_path.resolve(strict=True)
        if not resolved_path.is_dir():
            raise StorageError(f"Storage path is not a directory: {resolved_path}")

        identifier = storage_id or resolved_path.name or "storage"
        self._log_debug(
            "Registering storage '%s' at %s (allocation=%s).",
            identifier,
            resolved_path,
            "unlimited" if allocation is None else parse_size(allocation),
        )
        if not _STORAGE_ID_RE.fullmatch(identifier):
            raise ValueError(
                "Storage IDs must contain only letters, digits, '.', '_' or '-'."
            )
        with self._registry_lock:
            if identifier in self._locations:
                raise ValueError(f"Storage ID already exists: {identifier}")
            if resolved_path in self._paths:
                raise ValueError(
                    f"Storage path is already registered: {resolved_path}"
                )

        allocation_bytes = (
            None if allocation is None else parse_size(allocation)
        )
        probe_fd, probe_name = tempfile.mkstemp(
            prefix=".storage-check-", dir=resolved_path
        )
        os.close(probe_fd)
        Path(probe_name).unlink()

        location = _StorageLocation(
            identifier,
            resolved_path,
            allocation_bytes,
            asyncio.Lock(),
            self._logging,
        )
        with _exclusive_storage_lock_sync(resolved_path):
            self._initialize_index(location)
            report = self._reconcile_locked(location)

        with self._registry_lock:
            self._locations[identifier] = location
            self._paths.add(resolved_path)
        self._logging.info(
            "Registered storage '%s' at %s (allocation=%s bytes, indexed=%s, "
            "removed_unindexed=%s).",
            identifier,
            resolved_path,
            allocation_bytes,
            report.indexed_count,
            report.removed_count,
        )
        return identifier

    def close(self) -> None:
        """Stop the periodic reconciliation monitor and wait for its current pass."""
        self._log_debug("Stopping storage manager reconciliation monitor.")
        self._stop_monitor.set()
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=10)
            if self._monitor_thread.is_alive():
                raise StorageError(
                    "The storage reconciliation monitor did not stop within 10 seconds."
                )
            self._monitor_thread = None
        self._logging.info("Storage manager closed.")

    async def async_close(self) -> None:
        """Async-friendly version of ``close`` for API shutdown hooks."""
        await asyncio.to_thread(self.close)

    def __enter__(self) -> StorageManager:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    async def __aenter__(self) -> StorageManager:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.async_close()

    def _monitor_storage_roots(self) -> None:
        interval = self._reconciliation_interval_seconds
        if interval is None:
            return
        while not self._stop_monitor.wait(interval):
            with self._registry_lock:
                locations = tuple(self._locations.values())
            self._log_debug(
                "Automatic reconciliation cycle started for %d storage root(s).",
                len(locations),
            )
            for location in locations:
                if self._stop_monitor.is_set():
                    return
                try:
                    with _exclusive_storage_lock_sync(location.path):
                        report = self._reconcile_locked(location)
                    location.logging.debug_message(
                        "Automatic reconciliation completed for '%s': "
                        "indexed=%d, removed=%d.",
                        location.storage_id,
                        report.indexed_count,
                        report.removed_count,
                    )
                except Exception:
                    location.logging.exception(
                        "Automatic storage reconciliation failed for '%s' at %s; "
                        "it will be retried after %.3g seconds.",
                        location.storage_id,
                        location.path,
                        interval,
                    )

    async def async_add_storage(
        self,
        path: str | Path,
        allocation: int | str | None = None,
        *,
        storage_id: str | None = None,
    ) -> str:
        """Async-friendly version of ``add_storage`` for API handlers."""
        return await asyncio.to_thread(
            self.add_storage,
            path,
            allocation,
            storage_id=storage_id,
        )

    def list_storages(self) -> list[StorageInfo]:
        with self._registry_lock:
            storage_ids = tuple(self._locations)
        return [
            self.get_storage(storage_id)
            for storage_id in storage_ids
        ]

    async def async_list_storages(self) -> list[StorageInfo]:
        """Async-friendly version of ``list_storages`` for API handlers."""
        return await asyncio.to_thread(self.list_storages)

    def get_storage(self, storage_id: str) -> StorageInfo:
        location = self._get_location(storage_id)
        with _exclusive_storage_lock_sync(location.path):
            report = self._reconcile_locked(location)
            info = self._storage_info(location)
        location.logging.debug_message(
            "Storage status for '%s': used=%d bytes, available=%d bytes, "
            "allocation=%s, filesystem_free=%d bytes; reconciliation removed=%d.",
            location.storage_id,
            info.used_bytes,
            info.available_bytes,
            info.allocation_bytes,
            info.filesystem_free_bytes,
            report.removed_count,
        )
        return info

    async def async_get_storage(self, storage_id: str) -> StorageInfo:
        """Async-friendly version of ``get_storage`` for API handlers."""
        return await asyncio.to_thread(self.get_storage, storage_id)

    def add_directory(
        self,
        relative_path: str,
        *,
        storage_id: str | None = None,
    ) -> StorageEntry:
        """Create and index a directory and any missing parent directories."""
        location = self._get_location(storage_id or self.default_storage_id)
        parts = self._parse_relative_path(relative_path)
        self._log_debug(
            "Creating indexed directory '%s' in storage '%s'.",
            relative_path,
            location.storage_id,
        )

        with _exclusive_storage_lock_sync(location.path):
            self._reconcile_locked(location)
            current = location.path
            entries: list[tuple[str, Path]] = []
            for part in parts:
                current = current / part
                relative = current.relative_to(location.path).as_posix()
                if current.exists():
                    if current.is_symlink() or not current.is_dir():
                        raise StorageError(
                            f"Cannot create directory over an existing entry: {relative}"
                        )
                else:
                    current.mkdir()
                    entries.append((relative, current))

            if entries:
                try:
                    with self._connection(location) as connection:
                        for relative, path in entries:
                            info = path.stat(follow_symlinks=False)
                            connection.execute(
                                """
                                INSERT INTO entries
                                    (relative_path, kind, size_bytes, modified_ns)
                                VALUES (?, 'directory', 0, ?)
                                """,
                                (relative, info.st_mtime_ns),
                            )
                except Exception:
                    for _, path in reversed(entries):
                        path.rmdir()
                    raise
                location.logging.info(
                    "Created and indexed %d directory path(s) under storage '%s'.",
                    len(entries),
                    location.storage_id,
                )

            return self._entry_for_path(location, current)

    async def async_add_directory(
        self,
        relative_path: str,
        *,
        storage_id: str | None = None,
    ) -> StorageEntry:
        """Async-friendly version of ``add_directory`` for API handlers."""
        return await asyncio.to_thread(
            self.add_directory, relative_path, storage_id=storage_id
        )

    def _select_upload_storage(
        self,
        storage_id: str | None,
        expected_size: int | None,
    ) -> _StorageLocation:
        """Choose the best-fit registered location, or honor an explicit pin."""
        if storage_id is not None:
            return self._get_location(storage_id)

        with self._registry_lock:
            locations = tuple(self._locations.values())
        if not locations:
            raise InsufficientStorageError("No storage locations are registered.")

        required_bytes = 1 if expected_size is None else expected_size
        capacities = [
            (location, self.get_storage(location.storage_id).available_bytes)
            for location in locations
        ]
        capacities.sort(key=lambda item: item[1], reverse=True)

        for location, available_bytes in capacities:
            if available_bytes >= required_bytes:
                location.logging.info(
                    "Automatic upload placement selected storage '%s' "
                    "(available=%d bytes, upload_size=%s).",
                    location.storage_id,
                    available_bytes,
                    "unknown" if expected_size is None else expected_size,
                )
                return location

        self._logging.warning(
            "No registered storage can fit the upload (size=%s bytes). "
            "Capacities: %s.",
            "unknown" if expected_size is None else expected_size,
            ", ".join(
                f"{location.storage_id}={available} bytes"
                for location, available in capacities
            ),
        )
        raise InsufficientStorageError(
            "No registered storage has enough available space for this upload."
        )

    async def save_upload(
        self,
        upload: AsyncReadable,
        filename: str,
        *,
        storage_id: str | None = None,
        directory: str | None = None,
    ) -> StoredObject:
        """Validate, stream, and index an upload without trusting its name."""
        expected_size = getattr(upload, "size", None)
        if expected_size is not None and (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
        ):
            raise InvalidUploadError("Upload size must be a non-negative byte count.")
        location = self._select_upload_storage(storage_id, expected_size)
        self._log_debug(
            "Starting upload validation for storage '%s' (destination=%s).",
            location.storage_id,
            directory or ".",
        )
        try:
            extension = self._get_extension(filename)
        except UnsupportedFileTypeError:
            location.logging.warning(
                "Rejected upload for storage '%s': unsupported or mismatched file type.",
                location.storage_id,
            )
            raise
        relative_directory = ""
        if directory is not None:
            relative_directory = "/".join(self._parse_relative_path(directory))

        async with location.lock, _exclusive_storage_lock(location.path):
            reconcile_report = self._reconcile_locked(location)
            used_bytes = self._used_bytes(location)
            self._log_debug(
                "Upload preflight for '%s': used=%d bytes, incoming_minimum=1, "
                "removed_unindexed=%d.",
                location.storage_id,
                used_bytes,
                reconcile_report.removed_count,
            )
            self._check_capacity(location, used_bytes, 1)

            destination_directory = location.path / relative_directory
            if not destination_directory.is_dir() or destination_directory.is_symlink():
                raise StorageError(
                    f"Upload destination is not an indexed directory: {relative_directory}"
                )

            first_chunk_parts: list[bytes] = []
            first_chunk_size = 0
            while first_chunk_size < 32:
                part = await upload.read(32 - first_chunk_size)
                if not part:
                    break
                if not isinstance(part, bytes):
                    raise InvalidUploadError("Upload streams must return bytes.")
                first_chunk_parts.append(part)
                first_chunk_size += len(part)
            first_chunk = b"".join(first_chunk_parts)
            if not first_chunk:
                location.logging.warning(
                    "Rejected empty upload for storage '%s'.",
                    location.storage_id,
                )
                raise InvalidUploadError("Empty uploads are not allowed.")
            try:
                validator = _UploadValidator(extension, first_chunk)
                validator.feed(first_chunk)
            except InvalidUploadError:
                location.logging.warning(
                    "Rejected upload for storage '%s': content validation failed.",
                    location.storage_id,
                )
                raise

            stored_filename = f"{uuid.uuid4().hex}{extension}"
            destination = destination_directory / stored_filename
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=".upload-", suffix=".tmp", dir=destination_directory
            )
            temporary_path = Path(temporary_name)
            digest = hashlib.sha256()
            total_bytes = 0

            try:
                with os.fdopen(file_descriptor, "wb") as output:
                    chunk = first_chunk
                    while chunk:
                        if not isinstance(chunk, bytes):
                            raise InvalidUploadError(
                                "Upload streams must return bytes."
                            )
                        self._check_capacity(
                            location, used_bytes, total_bytes + len(chunk)
                        )
                        next_total = total_bytes + len(chunk)
                        if total_bytes == 0 or (
                            next_total // (16 * _CHUNK_SIZE)
                            > total_bytes // (16 * _CHUNK_SIZE)
                        ):
                            self._log_debug(
                                "Upload progress in storage '%s': %d bytes written.",
                                location.storage_id,
                                next_total,
                            )
                        if total_bytes:
                            validator.feed(chunk)
                        output.write(chunk)
                        digest.update(chunk)
                        total_bytes += len(chunk)
                        chunk = await upload.read(_CHUNK_SIZE)
                    validator.finish()
                    output.flush()
                    os.fsync(output.fileno())

                os.replace(temporary_path, destination)
                relative_path = destination.relative_to(location.path).as_posix()
                try:
                    info = destination.stat(follow_symlinks=False)
                    with self._connection(location) as connection:
                        connection.execute(
                            """
                            INSERT INTO entries
                                (relative_path, kind, size_bytes, modified_ns)
                            VALUES (?, 'file', ?, ?)
                            """,
                            (relative_path, total_bytes, info.st_mtime_ns),
                        )
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
            except InsufficientStorageError:
                raise
            except InvalidUploadError:
                location.logging.warning(
                    "Rejected upload for storage '%s': content validation failed.",
                    location.storage_id,
                )
                raise
            except OSError as exc:
                if exc.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)}:
                    location.logging.error(
                        "Filesystem ran out of usable space while writing an upload "
                        "to storage '%s'.",
                        location.storage_id,
                    )
                    raise InsufficientStorageError(
                        "Not enough usable storage is available for this upload."
                    ) from exc
                location.logging.exception(
                    "Filesystem error while writing an upload to storage '%s'.",
                    location.storage_id,
                )
                raise
            except Exception:
                location.logging.exception(
                    "Upload failed before it could be committed to storage '%s'.",
                    location.storage_id,
                )
                raise
            finally:
                temporary_path.unlink(missing_ok=True)

            result = StoredObject(
                storage_id=location.storage_id,
                path=destination,
                filename=stored_filename,
                media_type=validator.media_type,
                size_bytes=total_bytes,
                sha256=digest.hexdigest(),
            )
            location.logging.info(
                "Stored and indexed upload in storage '%s': path=%s, "
                "media_type=%s, size=%d bytes, sha256=%s.",
                location.storage_id,
                relative_path,
                validator.media_type,
                total_bytes,
                result.sha256,
            )
            return result

    def list_entries(
        self,
        *,
        storage_id: str | None = None,
        recursive: bool = True,
        include_root: bool = True,
    ) -> list[StorageEntry]:
        """List indexed files and directories, reconciling unindexed content first."""
        location = self._get_location(storage_id or self.default_storage_id)
        with _exclusive_storage_lock_sync(location.path):
            report = self._reconcile_locked(location)
            query = """
                SELECT relative_path, kind, size_bytes, modified_ns
                FROM entries
            """
            conditions: list[str] = []
            if not include_root:
                conditions.append("relative_path != ''")
            if not recursive:
                conditions.append("instr(relative_path, '/') = 0")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY relative_path"
            with self._connection(location) as connection:
                rows = connection.execute(query).fetchall()
            location.logging.debug_message(
                "Listed %d indexed entry/entries from storage '%s' "
                "(recursive=%s, include_root=%s, reconciliation_removed=%d).",
                len(rows),
                location.storage_id,
                recursive,
                include_root,
                report.removed_count,
            )
            return [
                StorageEntry(
                    storage_id=location.storage_id,
                    relative_path=row["relative_path"],
                    is_directory=row["kind"] == "directory",
                    size_bytes=row["size_bytes"],
                    modified_ns=row["modified_ns"],
                )
                for row in rows
            ]

    async def async_list_entries(
        self,
        *,
        storage_id: str | None = None,
        recursive: bool = True,
        include_root: bool = True,
    ) -> list[StorageEntry]:
        """Async-friendly version of ``list_entries`` for API handlers."""
        return await asyncio.to_thread(
            self.list_entries,
            storage_id=storage_id,
            recursive=recursive,
            include_root=include_root,
        )

    def remove(
        self,
        relative_path: str,
        *,
        storage_id: str | None = None,
        recursive: bool = True,
    ) -> None:
        """Remove an indexed file or directory and its corresponding index rows."""
        location = self._get_location(storage_id or self.default_storage_id)
        parts = self._parse_relative_path(relative_path)
        normalized = "/".join(parts)
        target = location.path.joinpath(*parts)

        location.logging.debug_message(
            "Removing indexed entry '%s' from storage '%s' (recursive=%s).",
            normalized,
            location.storage_id,
            recursive,
        )
        with _exclusive_storage_lock_sync(location.path):
            self._reconcile_locked(location)
            with self._connection(location) as connection:
                row = connection.execute(
                    "SELECT kind FROM entries WHERE relative_path = ?",
                    (normalized,),
                ).fetchone()
                if row is None:
                    raise StorageError(f"Storage entry does not exist: {normalized}")
                if row["kind"] == "directory":
                    children = connection.execute(
                        "SELECT relative_path FROM entries"
                    ).fetchall()
                    has_children = any(
                        child["relative_path"].startswith(normalized + "/")
                        for child in children
                    )
                    if has_children and not recursive:
                        raise StorageError(
                            f"Directory is not empty: {normalized}"
                        )

            if target.is_symlink():
                target.unlink()
            elif target.is_dir():
                if recursive:
                    shutil.rmtree(target)
                else:
                    target.rmdir()
            else:
                target.unlink()

            with self._connection(location) as connection:
                paths = connection.execute(
                    "SELECT relative_path FROM entries"
                ).fetchall()
                for row in paths:
                    indexed_path = row["relative_path"]
                    if (
                        indexed_path == normalized
                        or indexed_path.startswith(normalized + "/")
                    ):
                        connection.execute(
                            "DELETE FROM entries WHERE relative_path = ?",
                            (indexed_path,),
                        )
        location.logging.info(
            "Removed indexed entry '%s' from storage '%s'.",
            normalized,
            location.storage_id,
        )

    async def async_remove(
        self,
        relative_path: str,
        *,
        storage_id: str | None = None,
        recursive: bool = True,
    ) -> None:
        """Async-friendly version of ``remove`` for API handlers."""
        await asyncio.to_thread(
            self.remove,
            relative_path,
            storage_id=storage_id,
            recursive=recursive,
        )

    def reconcile_storage(
        self, storage_id: str | None = None
    ) -> ReconcileReport:
        """Delete unindexed filesystem entries and prune stale rows in the index."""
        location = self._get_location(storage_id or self.default_storage_id)
        location.logging.debug_message(
            "Starting explicit reconciliation for storage '%s' at %s.",
            location.storage_id,
            location.path,
        )
        with _exclusive_storage_lock_sync(location.path):
            report = self._reconcile_locked(location)
        location.logging.info(
            "Reconciled storage '%s': indexed=%d, removed=%d.",
            location.storage_id,
            report.indexed_count,
            report.removed_count,
        )
        return report

    async def async_reconcile_storage(
        self, storage_id: str | None = None
    ) -> ReconcileReport:
        """Async-friendly version of ``reconcile_storage`` for API handlers."""
        return await asyncio.to_thread(self.reconcile_storage, storage_id)

    def _get_location(self, storage_id: str) -> _StorageLocation:
        with self._registry_lock:
            try:
                return self._locations[storage_id]
            except KeyError as exc:
                raise StorageError(f"Unknown storage ID: {storage_id}") from exc

    @staticmethod
    def _parse_relative_path(relative_path: str) -> tuple[str, ...]:
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or "\x00" in relative_path
            or "\\" in relative_path
        ):
            raise ValueError("Storage paths must be non-empty relative POSIX paths.")
        path = Path(relative_path)
        if path.is_absolute():
            raise ValueError("Storage paths must be relative to their storage root.")
        parts = tuple(relative_path.split("/"))
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("Storage paths cannot contain empty or traversal segments.")
        if parts[0] in _INDEX_METADATA_NAMES or parts[0].startswith(".upload-"):
            raise ValueError("Storage path is reserved for internal storage metadata.")
        return parts

    @staticmethod
    def _connect_index(location: _StorageLocation) -> sqlite3.Connection:
        index_path = location.path / _INDEX_FILENAME
        if index_path.is_symlink():
            raise StorageError(f"Storage index cannot be a symlink: {index_path}")
        connection = sqlite3.connect(index_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    @contextmanager
    def _connection(
        location: _StorageLocation,
    ) -> Generator[sqlite3.Connection, None, None]:
        try:
            connection = StorageManager._connect_index(location)
        except sqlite3.DatabaseError as exc:
            raise StorageError(f"Could not open storage index: {exc}") from exc
        try:
            with connection:
                yield connection
        except sqlite3.DatabaseError as exc:
            raise StorageError(f"Could not use storage index: {exc}") from exc
        finally:
            connection.close()

    def _initialize_index(self, location: _StorageLocation) -> None:
        index_path = location.path / _INDEX_FILENAME
        location.logging.debug_message(
            "Opening SQLite storage index at %s.", index_path
        )
        if index_path.is_symlink():
            raise StorageError(f"Storage index cannot be a symlink: {index_path}")
        try:
            with self._connection(location) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in {0, 1}:
                    raise StorageError(
                        f"Unsupported storage index version {version}: {index_path}"
                    )
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise StorageError(
                        f"Storage index integrity check failed: {integrity}"
                    )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS entries (
                        relative_path TEXT PRIMARY KEY,
                        kind TEXT NOT NULL CHECK (kind IN ('file', 'directory')),
                        size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                        modified_ns INTEGER NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entries_kind ON entries(kind)"
                )
                connection.execute(
                    "INSERT OR IGNORE INTO entries "
                    "(relative_path, kind, size_bytes, modified_ns) "
                    "VALUES ('', 'directory', 0, ?)",
                    (location.path.stat().st_mtime_ns,),
                )
                connection.execute("PRAGMA user_version = 1")
            location.logging.debug_message(
                "SQLite storage index initialized and verified for '%s'.",
                location.storage_id,
            )
        except sqlite3.DatabaseError as exc:
            location.logging.exception(
                "Failed to initialize SQLite storage index for '%s'.",
                location.storage_id,
            )
            raise StorageError(
                f"Could not read or initialize storage index {index_path}: {exc}"
            ) from exc

    def _reconcile_locked(self, location: _StorageLocation) -> ReconcileReport:
        location.logging.debug_message(
            "Scanning storage root '%s' for filesystem/index differences.",
            location.path,
        )
        with self._connection(location) as connection:
            indexed = {
                row["relative_path"]: row["kind"]
                for row in connection.execute(
                    "SELECT relative_path, kind FROM entries"
                ).fetchall()
            }

        actual: dict[str, tuple[str, int, int]] = {}
        special_paths: set[str] = set()
        pending = [(location.path, "")]
        while pending:
            directory, parent = pending.pop()
            with os.scandir(directory) as children:
                for child in children:
                    if not parent and child.name in _INDEX_METADATA_NAMES:
                        continue
                    relative_path = (
                        f"{parent}/{child.name}" if parent else child.name
                    )
                    if child.is_symlink():
                        special_paths.add(relative_path)
                        actual[relative_path] = ("symlink", 0, 0)
                    elif child.is_dir(follow_symlinks=False):
                        info = child.stat(follow_symlinks=False)
                        actual[relative_path] = (
                            "directory",
                            0,
                            info.st_mtime_ns,
                        )
                        pending.append((Path(child.path), relative_path))
                    elif child.is_file(follow_symlinks=False):
                        info = child.stat(follow_symlinks=False)
                        actual[relative_path] = (
                            "file",
                            info.st_size,
                            info.st_mtime_ns,
                        )
                    else:
                        special_paths.add(relative_path)
                        actual[relative_path] = ("special", 0, 0)

        purge_paths = {
            relative_path
            for relative_path, (kind, _, _) in actual.items()
            if relative_path in special_paths
            or relative_path not in indexed
            or indexed[relative_path] != kind
        }
        for relative_path in actual:
            parts = relative_path.split("/")
            if any(
                "/".join(parts[:index]) in purge_paths
                for index in range(1, len(parts))
            ):
                purge_paths.add(relative_path)

        for relative_path in sorted(
            purge_paths, key=lambda item: (item.count("/"), item), reverse=True
        ):
            location.logging.debug_message(
                "Deleting filesystem entry absent from or inconsistent with index: "
                "%s/%s.",
                location.path,
                relative_path,
            )
            path = location.path.joinpath(*relative_path.split("/"))
            try:
                if path.is_symlink() or not path.is_dir():
                    path.unlink(missing_ok=True)
                else:
                    path.rmdir()
            except OSError as exc:
                raise StorageError(
                    f"Could not remove unindexed storage entry {relative_path}: {exc}"
                ) from exc

        valid_actual = {
            path: record
            for path, record in actual.items()
            if path not in purge_paths
        }
        root_modified_ns = location.path.stat().st_mtime_ns
        with self._connection(location) as connection:
            current_paths = {
                row["relative_path"]
                for row in connection.execute(
                    "SELECT relative_path FROM entries"
                ).fetchall()
            }
            valid_paths = set(valid_actual) | {""}
            stale_paths = current_paths - valid_paths
            for stale_path in stale_paths:
                location.logging.debug_message(
                    "Removing stale index row for missing path '%s'.",
                    stale_path or ".",
                )
                connection.execute(
                    "DELETE FROM entries WHERE relative_path = ?",
                    (stale_path,),
                )
            connection.execute(
                """
                INSERT INTO entries
                    (relative_path, kind, size_bytes, modified_ns)
                VALUES ('', 'directory', 0, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    kind = 'directory', size_bytes = 0, modified_ns = excluded.modified_ns
                """,
                (root_modified_ns,),
            )
            for relative_path, (kind, size_bytes, modified_ns) in valid_actual.items():
                connection.execute(
                    """
                    INSERT INTO entries
                        (relative_path, kind, size_bytes, modified_ns)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(relative_path) DO UPDATE SET
                        kind = excluded.kind,
                        size_bytes = excluded.size_bytes,
                        modified_ns = excluded.modified_ns
                    """,
                    (relative_path, kind, size_bytes, modified_ns),
                )
            indexed_count = connection.execute(
                "SELECT COUNT(*) FROM entries"
            ).fetchone()[0]

        report = ReconcileReport(
            storage_id=location.storage_id,
            indexed_count=indexed_count,
            removed_count=len(purge_paths | stale_paths),
        )
        location.logging.debug_message(
            "Storage scan complete for '%s': indexed=%d, filesystem entries "
            "removed=%d, stale index rows removed=%d.",
            location.storage_id,
            report.indexed_count,
            len(purge_paths),
            len(stale_paths),
        )
        return report

    @staticmethod
    def _entry_for_path(
        location: _StorageLocation, path: Path
    ) -> StorageEntry:
        relative_path = (
            "" if path == location.path else path.relative_to(location.path).as_posix()
        )
        with StorageManager._connection(location) as connection:
            row = connection.execute(
                "SELECT kind, size_bytes, modified_ns FROM entries "
                "WHERE relative_path = ?",
                (relative_path,),
            ).fetchone()
        if row is None:
            raise StorageError(f"Storage entry was not indexed: {relative_path}")
        return StorageEntry(
            storage_id=location.storage_id,
            relative_path=relative_path,
            is_directory=row["kind"] == "directory",
            size_bytes=row["size_bytes"],
            modified_ns=row["modified_ns"],
        )

    @staticmethod
    def _get_extension(filename: str) -> str:
        if not isinstance(filename, str) or "\x00" in filename:
            raise InvalidUploadError("A valid upload filename is required.")
        basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        if basename in {"", ".", ".."}:
            raise InvalidUploadError("A valid upload filename is required.")
        extension = Path(basename).suffix.lower()
        if extension not in _IMAGE_TYPES | _VIDEO_TYPES | _TEXT_TYPES:
            raise UnsupportedFileTypeError(
                "Only common image/video formats and UTF-8 text or subtitle files are allowed."
            )
        return extension

    def _check_capacity(
        self,
        location: _StorageLocation,
        used_bytes: int,
        incoming_bytes: int,
    ) -> None:
        if (
            location.allocation_bytes is not None
            and used_bytes + incoming_bytes > location.allocation_bytes
        ):
            location.logging.warning(
                "Storage quota would be exceeded for '%s': used=%d, incoming=%d, "
                "allocation=%d bytes.",
                location.storage_id,
                used_bytes,
                incoming_bytes,
                location.allocation_bytes,
            )
            raise InsufficientStorageError(
                f"Storage allocation reached for '{location.storage_id}'."
            )
        free_bytes = shutil.disk_usage(location.path).free
        if free_bytes - self.minimum_free_bytes < incoming_bytes:
            location.logging.warning(
                "Filesystem space check failed for '%s': free=%d, reserve=%d, "
                "incoming=%d bytes.",
                location.storage_id,
                free_bytes,
                self.minimum_free_bytes,
                incoming_bytes,
            )
            raise InsufficientStorageError(
                "Not enough usable filesystem space is available for this upload."
            )

    def _storage_info(self, location: _StorageLocation) -> StorageInfo:
        used_bytes = self._used_bytes(location)
        filesystem_free_bytes = shutil.disk_usage(location.path).free
        quota_free_bytes = (
            filesystem_free_bytes
            if location.allocation_bytes is None
            else max(location.allocation_bytes - used_bytes, 0)
        )
        available_bytes = max(
            min(quota_free_bytes, filesystem_free_bytes - self.minimum_free_bytes),
            0,
        )
        return StorageInfo(
            storage_id=location.storage_id,
            path=location.path,
            allocation_bytes=location.allocation_bytes,
            used_bytes=used_bytes,
            available_bytes=available_bytes,
            filesystem_free_bytes=filesystem_free_bytes,
        )

    @staticmethod
    def _used_bytes(location: _StorageLocation) -> int:
        with StorageManager._connection(location) as connection:
            return connection.execute(
                "SELECT COALESCE(SUM(size_bytes), 0) FROM entries WHERE kind = 'file'"
            ).fetchone()[0]

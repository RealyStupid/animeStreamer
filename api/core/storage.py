"""Local, quota-aware storage for untrusted show uploads.

Quick start
===========

Create one manager at application startup and reuse it. The default storage
directory is ``.localstorage`` relative to the process working directory:

    from core.storage import StorageManager

    storage = StorageManager(
        default_path=".localstorage",
        default_allocation="500 GiB",
    )

Add another directory on a different mounted drive with ``add_storage``.
Allocations support bytes and decimal or binary units (for example, ``"20 GB"``
or ``"20 GiB"``); omit an allocation for no per-location quota:

    archive_id = storage.add_storage(
        "/mnt/archive/.storage",
        allocation="2 TiB",
        storage_id="archive",
    )

Pass a FastAPI ``UploadFile`` directly to ``save_upload``. Use the returned
generated filename/path for your database record; the client-supplied filename
is used only to select the allowed extension, never as the stored path:

    stored = await storage.save_upload(
        upload_file,
        upload_file.filename or "",
        storage_id=archive_id,
    )
    # Save stored.path (or a storage ID plus stored.filename) in your database.
    # stored.media_type, stored.size_bytes, and stored.sha256 are also available.

``get_storage(storage_id)`` and ``list_storages()`` report used, allocated,
available, and filesystem-free bytes. ``save_upload`` raises
``InsufficientStorageError`` when a quota or usable filesystem limit would be
exceeded, ``UnsupportedFileTypeError`` for a disallowed or mismatched type, and
``InvalidUploadError`` for empty, malformed, or invalid text input.

Run the storage tests from the repository root with:

    cd api
    source ../.venv/bin/activate
    python -m unittest discover -s tests -p 'test_storage.py' -v

The tests use temporary directories and simulated upload streams, so they
exercise real file creation and quota checks without filling a real drive.
This manager stores files on the filesystem; it does not connect to or test the
SQL database.

Safety notes
============

Uploads are limited to recognized image/video containers and UTF-8 subtitle or
plain-text files. This module does not decode media or scan for malware; keep
stored files private and serve them as attachments unless a trusted media
pipeline has processed them. Signature and boundary checks reject common
extension/content mismatches and truncated uploads, but are not a full media
decoder or malware scanner.
"""

from __future__ import annotations

import asyncio
import codecs
import errno
import hashlib
import importlib
import os
import re
import shutil
import stat
import tempfile
import unicodedata
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import AsyncGenerator, Protocol


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
_STORAGE_LOCKS: dict[Path, asyncio.Lock] = {}


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


@dataclass(frozen=True)
class StorageInfo:
    storage_id: str
    path: Path
    allocation_bytes: int | None
    used_bytes: int
    available_bytes: int
    filesystem_free_bytes: int


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
    ) -> None:
        self.minimum_free_bytes = parse_size(minimum_free_bytes)
        self._locations: dict[str, _StorageLocation] = {}
        self._paths: set[Path] = set()
        self.default_storage_id = self.add_storage(
            default_path, default_allocation
        )

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
        if not _STORAGE_ID_RE.fullmatch(identifier):
            raise ValueError(
                "Storage IDs must contain only letters, digits, '.', '_' or '-'."
            )
        if identifier in self._locations:
            raise ValueError(f"Storage ID already exists: {identifier}")
        if resolved_path in self._paths:
            raise ValueError(f"Storage path is already registered: {resolved_path}")

        allocation_bytes = (
            None if allocation is None else parse_size(allocation)
        )
        probe_fd, probe_name = tempfile.mkstemp(
            prefix=".storage-check-", dir=resolved_path
        )
        os.close(probe_fd)
        Path(probe_name).unlink()

        self._locations[identifier] = _StorageLocation(
            identifier,
            resolved_path,
            allocation_bytes,
            _STORAGE_LOCKS.setdefault(resolved_path, asyncio.Lock()),
        )
        self._paths.add(resolved_path)
        return identifier

    def list_storages(self) -> list[StorageInfo]:
        return [
            self._storage_info(location)
            for location in self._locations.values()
        ]

    def get_storage(self, storage_id: str) -> StorageInfo:
        return self._storage_info(self._get_location(storage_id))

    async def save_upload(
        self,
        upload: AsyncReadable,
        filename: str,
        *,
        storage_id: str | None = None,
    ) -> StoredObject:
        """Validate and stream an upload into a storage location without trusting its name."""
        location = self._get_location(storage_id or self.default_storage_id)
        extension = self._get_extension(filename)

        async with location.lock, _exclusive_storage_lock(location.path):
            used_bytes = self._used_bytes(location.path)
            self._check_capacity(location, used_bytes, 1)

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
                raise InvalidUploadError("Empty uploads are not allowed.")
            validator = _UploadValidator(extension, first_chunk)
            validator.feed(first_chunk)

            stored_filename = f"{uuid.uuid4().hex}{extension}"
            destination = location.path / stored_filename
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=".upload-", suffix=".tmp", dir=location.path
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
            except OSError as exc:
                if exc.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)}:
                    raise InsufficientStorageError(
                        "Not enough usable storage is available for this upload."
                    ) from exc
                raise
            finally:
                temporary_path.unlink(missing_ok=True)

            return StoredObject(
                storage_id=location.storage_id,
                path=destination,
                filename=stored_filename,
                media_type=validator.media_type,
                size_bytes=total_bytes,
                sha256=digest.hexdigest(),
            )

    def _get_location(self, storage_id: str) -> _StorageLocation:
        try:
            return self._locations[storage_id]
        except KeyError as exc:
            raise StorageError(f"Unknown storage ID: {storage_id}") from exc

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
            raise InsufficientStorageError(
                f"Storage allocation reached for '{location.storage_id}'."
            )
        free_bytes = shutil.disk_usage(location.path).free
        if free_bytes - self.minimum_free_bytes < incoming_bytes:
            raise InsufficientStorageError(
                "Not enough usable filesystem space is available for this upload."
            )

    def _storage_info(self, location: _StorageLocation) -> StorageInfo:
        used_bytes = self._used_bytes(location.path)
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
    def _used_bytes(root: Path) -> int:
        total = 0
        pending = [root]
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.name == ".storage.lock":
                        continue
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
        return total

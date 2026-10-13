# `core/storage.py` — Indexed Local Storage Manager

`StorageManager` manages one or more local directories for uploaded content. It
provides per-root SQLite indexes, size quotas, physical-free-space checks,
streamed content validation, automatic placement, removal/listing APIs, and
periodic reconciliation. The manager is independent from the API's relational
database in [`database.md`](./database.md); an application should store the
returned storage ID and relative filename in its own SQL records.

## Important: destructive behavior

**A registered storage directory is managed exclusively by this module.** On
registration, the manager opens/creates the root's SQLite index, checks it, and
reconciles the directory. Any filesystem entry that is not already represented
by a compatible row in that index is deleted. This is also true of existing
files found the first time an empty index is created. Do not register a folder
whose contents must be preserved unless those contents have first been added
through the manager/index.

Use dedicated empty directories, for example `.localstorage/` or
`/mnt/media/.storage/`. **Never point a root at `/`, a home directory, a drive
root, the repository, or another directory containing unrelated files.** The
manager does not infer which existing files are valuable or ask for
confirmation before reconciliation.

The SQLite index is authoritative: files written outside the manager are not
automatically added to the index; they are removed by a later reconciliation.
The background monitor defaults to a five-second interval. Manual operations
such as listing, getting storage information, and upload preflight also
reconcile first, so unindexed files may be deleted before those operations
return.

## Quick start

Create one manager for the application lifecycle. An absolute path can locate
another mounted drive; a relative path is resolved from the process working
directory:

```python
from core.storage import StorageManager

storage = StorageManager(
    default_path=".localstorage",
    default_allocation="500 GiB",
)
```

Register another root and make an indexed directory:

```python
archive_id = await storage.async_add_storage(
    "/mnt/archive/.storage",
    allocation="2 TiB",
    storage_id="archive",
)
await storage.async_add_directory("shows/space-opera", storage_id=archive_id)
```

Pass a FastAPI `UploadFile` (or an object with `async read(size) -> bytes`) to
`save_upload`:

```python
stored = await storage.save_upload(
    upload=upload_file,
    filename=upload_file.filename or "",
    directory="shows/space-opera",
)
```

With no explicit `storage_id`, the manager selects the root with the greatest
available capacity that can fit the complete upload size when `upload.size` is
known. Use `stored.storage_id` and `stored.filename` (or a root-relative path)
for app metadata. Do not expose the absolute local `stored.path` as a portable
URL.

Always close the manager on shutdown:

```python
await storage.async_close()
```

Synchronous context manager support (`with StorageManager(...) as storage`)
and async context manager support (`async with ...`) are also available.

## Size parsing and allocations

### `parse_size(value)`

Returns an integer byte count from a non-negative integer or size string.
Accepted units are bytes (`B`, or omitted), decimal `KB`/`MB`/`GB`/`TB`
(powers of 1,000), and binary `KiB`/`MiB`/`GiB`/`TiB` (powers of 1,024).
Matching is case-insensitive and permits spaces and fractional amounts:

```python
parse_size(123)       # 123
parse_size("1.5 MB")  # 1_500_000
parse_size("2 GiB")   # 2 * 1024**3
```

Negative values, booleans, unsupported units, malformed strings, and other
input types raise `ValueError`. Fractional values are converted to an integer
byte count by truncating the fractional part after multiplication. A valid
zero-byte allocation is accepted; it means no file bytes fit.

### Per-root and physical capacity

`default_allocation` and each `add_storage(..., allocation=...)` value set a
per-root quota. `None` means no per-root quota. The manager separately checks
physical free space through `shutil.disk_usage` and reserves
`minimum_free_bytes`, which defaults to 64 MiB.

For a root, `available_bytes` is the non-negative minimum of:

- allocation minus indexed file bytes (or physical free bytes if allocation is
  unlimited); and
- physical filesystem free bytes minus the reserve.

Directories have size zero and do not consume quota. Used bytes are summed from
indexed file rows after reconciliation. A full quota on one location does not
prevent using another eligible registered location.

Roots on the same physical filesystem share the same physical free-space pool.
Registering multiple directories on one disk does not create additional disk
capacity. The manager does not reserve bytes with the operating system while
choosing a root, so unrelated processes can consume space after a capacity
check; every write is checked again and filesystem `ENOSPC`/`EDQUOT` errors are
translated to `InsufficientStorageError`.

## Public data types and exceptions

- `StorageInfo`: `storage_id`, canonical `path`, `allocation_bytes`,
  `used_bytes`, `available_bytes`, and `filesystem_free_bytes`.
- `StorageEntry`: `storage_id`, root-relative POSIX `relative_path`,
  `is_directory`, `size_bytes`, and `modified_ns`. The storage root itself is
  represented by an empty relative path.
- `ReconcileReport`: `storage_id`, current `indexed_count`, and
  `removed_count`. The removal count includes filesystem entries purged and
  stale index rows pruned; it may exceed the number of top-level objects.
- `StoredObject`: chosen `storage_id`, absolute `path`, generated `filename`,
  detected `media_type`, actual `size_bytes`, and computed `sha256`.
- `StorageError`: base class for storage/index failures.
- `InvalidUploadError`: empty, malformed, invalid UTF-8, or otherwise invalid
  upload.
- `UnsupportedFileTypeError`: subclass of `InvalidUploadError` for unsupported
  extension or mismatched signature.
- `InsufficientStorageError`: no eligible root, per-root quota limit,
  filesystem free-space reserve, or actual disk/quota exhaustion.

Invalid configuration/path arguments can also raise `ValueError` or
`TypeError`; SQLite/filesystem failures are surfaced as storage errors or the
original OS error where the implementation does not translate that particular
operation. Do not turn these into a success response at the API boundary.

## Manager configuration and logging

```python
StorageManager(
    default_path=".localstorage",
    default_allocation=None,
    *,
    minimum_free_bytes="64 MiB",
    reconciliation_interval_seconds=5.0,
    debug=False,
    print_debug=False,
    logger=None,
)
```

- `default_path` is created if missing. Its canonical resolved directory name
  is the default storage ID unless another ID is specified during registration.
- `default_allocation=None` leaves only physical free-space limits in effect.
- `minimum_free_bytes` uses `parse_size`.
- `reconciliation_interval_seconds` must be a positive finite number or
  `None`. `None` disables the monitor, but manual reconciliation and
  operation-triggered reconciliation remain active.
- `debug` must be `bool`; when true, detailed DEBUG messages are emitted through
  the selected logger.
- `print_debug` must be `bool`; when true, detailed DEBUG messages are also
  printed to stdout. It does not print ordinary INFO/WARNING/ERROR messages.
- `logger` must implement callable `debug`, `info`, `warning`, `error`, and
  `exception` methods. With no custom logger, the module uses
  `logging.getLogger("core.storage")`.

`manager.logger`, `manager.debug`, and `manager.print_debug` can be changed
after initialization. They are shared by all registered locations and the
monitor. Assigning an invalid logger or a non-boolean flag raises an error.
Messages report operations and metadata (including stored path, size, detected
type, and SHA-256); upload bytes/content are not logged.

The API configures a dedicated `.logs/storage.log` with daily rotation and
three backups in `api/main.py`. Its propagation is disabled so storage messages
do not clutter the API logger. See [`logging.md`](./logging.md).

## Managing storage roots

### `add_storage(path, allocation=None, *, storage_id=None)`

Creates the path (including parents), resolves it to a canonical directory,
checks that the directory can be written, registers it, initializes/verifies
the SQLite index, and reconciles it. Returns the storage ID.

- An explicit ID must be 1–64 characters containing only letters, digits,
  period, underscore, or hyphen; `"."` and `".."` are not accepted.
- Without an explicit ID, the resolved directory's basename is used (fallback
  `"storage"` for a path with no name).
- Duplicate IDs and duplicate canonical paths raise `ValueError`.
- A path that resolves to a non-directory or cannot be written cannot be
  registered.
- A symlink supplied as the root path is resolved to its target before it is
  registered; the manager then owns/manages that resolved target directory.
- Existing unindexed content is purged as described above.
- There is no public unregister/remove-root method. Do not delete, rename, or
  move a root while the manager is using it.

`async_add_storage` calls the synchronous operation in a worker thread.

### `list_storages()` / `async_list_storages()`

Returns `StorageInfo` for each registered root. Each info query reconciles that
root first and can therefore purge unindexed content. Results are snapshots;
available bytes can change immediately due to other processes or uploads.

### `get_storage(storage_id)` / `async_get_storage(storage_id)`

Returns a refreshed `StorageInfo`, after reconciliation. An unknown ID raises
`StorageError`. Treat the returned capacity as an estimate, not a disk
reservation.

## Indexed directories and paths

### `add_directory(relative_path, *, storage_id=None)`

Creates the requested directory and any missing parent directories, indexing
each one, and returns the requested `StorageEntry`. If existing components are
already real directories, they are reused; a file or symlink at a component
causes `StorageError`. If index insertion fails, newly created empty
directories are removed before the exception propagates.

Use `async_add_directory` from async handlers to avoid blocking the event loop.

### Path rules

Paths passed to directory/upload destination/removal methods are root-relative
POSIX paths, using `/` separators. Empty paths, absolute paths, NUL bytes,
backslashes, empty segments, `"."`, and `".."` segments are rejected. The
manager protects internal metadata names and root-level `.upload-*` names.
These checks prevent ordinary traversal/absolute-path escapes; do not bypass
them by concatenating client-controlled paths elsewhere in application code.

The root itself cannot be passed to `remove`; callers may only remove a named
indexed entry beneath it.

## Uploads and content checks

### Episode video conversion

Episode creation and replacement use the system `ffmpeg` executable to
normalize uploaded video before it is added to indexed storage. Install FFmpeg
on every API host and ensure it is available on `PATH`. The output is MP4 with
H.264 video, AAC audio when an audio track exists, 8-bit `yuv420p`, and a
maximum dimension of 1920x1080; MP4 metadata is moved to the beginning for
progressive playback. The original upload is not retained.

Conversion runs with a one-hour timeout and rejects input larger than the
storage manager's currently available capacity. If FFmpeg is unavailable, the
API returns `503`; unsupported, malformed, or failed conversions return `422`.
Transcoding requires temporary disk space for both the incoming source and
converted output, in addition to the final storage quota.

### `save_upload(upload, filename, *, storage_id=None, directory=None)`

This is async and accepts an async reader returning `bytes` from
`read(size)`. FastAPI's `UploadFile` is supported. The `filename` argument is
used only to determine an allowlisted extension; the client-supplied basename
is never used as a destination name.

#### Supported extensions and returned media types

Images:

| Extensions | Media type |
|---|---|
| `.jpg`, `.jpeg` | `image/jpeg` |
| `.png` | `image/png` |
| `.gif` | `image/gif` |
| `.webp` | `image/webp` |
| `.bmp` | `image/bmp` |
| `.tif`, `.tiff` | `image/tiff` |

Video:

| Extensions | Media type |
|---|---|
| `.mp4`, `.m4v` | `video/mp4` |
| `.mov` | `video/quicktime` |
| `.mkv` | `video/x-matroska` |
| `.webm` | `video/webm` |
| `.avi` | `video/x-msvideo` |

Text/subtitles: `.txt`, `.srt`, and `.vtt`, all reported as `text/plain`.
Other extensions (including archives, executables, HTML, and JSON) are
rejected. Extension matching is case-insensitive. The filename may include
client path separators; only its final basename is considered.

#### Validation steps

1. If `upload.size` exists, require a non-boolean, non-negative integer.
   `None` means size is unknown.
2. Choose a root (automatic placement or explicit `storage_id`).
3. Check the filename extension.
4. Parse/validate `directory` if provided. It must be an existing indexed
   directory; upload does not implicitly create it.
5. Acquire the per-root async lock and cross-process OS file lock, reconcile
   the root, check at least one byte can be written, and verify the destination
   is a real directory rather than a symlink.
6. Read an initial prefix (up to 32 bytes), reject empty streams, and compare
   file signatures with the declared extension.
7. Stream the content in chunks up to 1 MiB. Enforce quota and physical
   free-space reserve as each chunk is written, incrementally validate UTF-8
   text/control characters or retain container boundary information, and
   compute SHA-256.
8. Validate end-of-file/closing structure where the format check supports it.
9. Flush and `fsync` the temporary file, atomically rename it to a UUID-based
   filename with the allowed extension, and add the file row to SQLite. If
   index insertion fails after the rename, delete the destination and raise.
10. Return `StoredObject` with actual byte count/hash and detected media type.

Temporary uploads are created in the destination directory with a
`.upload-...tmp` name. On an ordinary exception, cleanup removes the temporary
file. The final filename uses a random UUID hex string, not the client's
basename, so path components in the uploaded name do not control where it is
stored.

#### Automatic placement and multiple roots

- With an explicit `storage_id`, the upload is pinned to that root; it does not
  spill into another root if that root cannot fit it.
- With no `storage_id`, every registered root is refreshed/reconciled, and
  eligible roots are sorted by currently available bytes, greatest first.
- If `upload.size` is known, a root must have at least that many available
  bytes to be selected. If none fit, `InsufficientStorageError` is raised
  before the upload is streamed.
- If size is unknown, the root with the most available bytes is selected if it
  has at least one byte; the manager continues enforcing limits while reading.
- The complete file is stored on one root. Files are never split across roots.
- Selection and streaming are not one global reservation transaction. Another
  process may change free space after selection; the writer rechecks capacity
  under the chosen root's lock and cleans up on failure.

#### Content validation limits

The checks include recognizable signatures and some simple structural checks:
image magic bytes; RIFF/container markers for applicable formats; selected
file-end markers/declared sizes; and strict UTF-8 decoding for text. Text control
characters are rejected except tab, line feed, carriage return, and form feed.
The video checks are limited to container signatures/basic headers; they do
not decode tracks or verify every internal box/segment.

These checks are useful against accidental extension spoofing, but **are not a
malware scanner, a sandbox, or complete format validation**. Polyglot files,
crafted parser exploits, resource exhaustion, or malformed structures not
covered by the lightweight checks may remain possible. Do not serve untrusted
uploads inline from the application origin without an appropriate trusted
processing and delivery policy. Consider size/request limits at the API or
reverse-proxy layer as well; the storage quota is not a substitute for
request-body limits.

#### Failure/cleanup behavior

- Unsupported extension or mismatched signature:
  `UnsupportedFileTypeError`.
- Empty file, invalid UTF-8/control characters, invalid reader return type, or
  malformed/truncated content detected by implemented checks:
  `InvalidUploadError`.
- No eligible root, quota limit, insufficient free space, `ENOSPC`, or
  `EDQUOT`: `InsufficientStorageError`.
- Invalid/unknown storage ID, missing destination, corrupt index, or ordinary
  filesystem/index failure: `StorageError` or the surfaced underlying error.
- A failed stream does not return a `StoredObject`. Temporary data is removed;
  after the final rename, an index failure attempts to remove the unindexed
  destination before raising.

## Listing and removing entries

### `list_entries(*, storage_id=None, recursive=True, include_root=True)`

Reconciles before querying the index. `recursive=False` returns only entries
whose relative path has no `/` (plus the root if `include_root=True`).
`include_root=False` omits the root's empty path. Results are sorted by
relative path. External additions will be deleted before they can be listed;
external deletions cause stale index rows to be removed.

`async_list_entries` runs this filesystem/index work in a worker thread.

### `remove(relative_path, *, storage_id=None, recursive=True)`

Reconciles first, requires the target to be indexed, then removes the target
filesystem object and its index row(s). Files and symlinks are unlinked;
directories are recursively removed by default. With `recursive=False`, a
non-empty indexed directory raises `StorageError`; an empty directory is
removed. The target root is not removable through this API.

Directly deleting or renaming files outside this method is detected on the
next reconciliation, which prunes stale rows. `async_remove` is the
worker-thread wrapper for async handlers.

The media API's owner-only `DELETE /media/my/shows/{show_id}`,
`DELETE /media/my/seasons/{season_id}`, and
`DELETE /media/my/episodes/{episode_id}` routes use recursive indexed removal
before deleting their database records. Deleting a show also removes all
season and episode files; deleting a season also removes its episode files.

## Reconciliation and active cleanup

### `reconcile_storage(storage_id=None)`

Takes the storage lock and compares the tree on disk with the index:

- Any filesystem entry absent from the index, with a mismatching file/directory
  kind, or identified as a symlink/special file is purged.
- Descendants of a purged directory are purged too.
- Index rows for paths no longer present are deleted.
- Valid entries' kind, size, and modification time are refreshed in SQLite.
- The root directory's own empty-path index row is maintained.
- The root's internal index, SQLite journal/WAL/SHM sidecars, and lock file are
  skipped at the root level; other objects are treated as managed content.

The SQLite index is checked for supported schema version and integrity during
initialization. If the index is corrupt or unsupported, registration fails
rather than treating the contents as safe to erase or silently rebuilding an
empty index. Subsequent index/filesystem errors surface as failures. A root
with a valid index but lost/removed rows is different: all unindexed content is
considered unauthorized and purged.

### Background monitor

By default, a daemon thread waits for the configured interval (five seconds),
then reconciles each registered root. If one root's reconciliation fails, the
error is logged and that root is retried on a later cycle; the monitor proceeds
to the other roots. It is a periodic scan, not an operating-system filesystem
watcher. Unindexed content may exist until a monitor/explicit operation next
scans the root.

Set `reconciliation_interval_seconds=None` to disable this thread. Operations
that explicitly refresh/list or modify storage still reconcile as described.
Call `close()` or `async_close()` when the manager is shut down. `close()` waits
up to 10 seconds for an in-progress monitor pass; if it cannot stop in time, it
raises `StorageError`.

## Internal files and concurrency

Every root contains:

- `.storage-index.sqlite3`: the SQLite index of files/directories;
- SQLite journal/WAL/SHM files when SQLite uses them; and
- `.storage.lock`: a persistent regular file used as an OS-level locking point.

The lock file existing on disk does **not** mean a lock is currently held. The
process holds an OS lock on its open file descriptor only while operating on a
root. Do not delete, replace, or symlink `.storage.lock` while managers or
processes use that root; different processes must coordinate through the same
file. The manager also uses an in-process async lock per root and a registry
lock for its root collection.

The lock is advisory/cooperative: software that ignores it can still modify
the directory concurrently. Directory contents should not be manipulated by
other code while registered. Symlinks and special files discovered during
reconciliation are deleted rather than followed.

## Synchronous and asynchronous method pairs

The asynchronous wrappers below generally use `asyncio.to_thread` for
synchronous filesystem/database work:

| Synchronous | Async wrapper |
|---|---|
| `add_storage` | `async_add_storage` |
| `list_storages` | `async_list_storages` |
| `get_storage` | `async_get_storage` |
| `add_directory` | `async_add_directory` |
| `list_entries` | `async_list_entries` |
| `remove` | `async_remove` |
| `reconcile_storage` | `async_reconcile_storage` |
| `close` | `async_close` |

`save_upload` is itself asynchronous because it reads from an async upload
stream. Prefer these async entry points in FastAPI handlers; synchronous
filesystem scans can otherwise block the event loop.

## Tests

From `api/`, run the focused storage test module:

```bash
python -m unittest discover -s tests -p 'test_storage.py' -v
```

In this repository's development setup, the virtual environment is at
`../.venv`; either activate it first or run
`../.venv/bin/python -m unittest discover -s tests -p 'test_storage.py' -v`.
The tests create temporary roots and use in-memory async readers. They exercise
the actual SQLite/filesystem behavior without touching the API's configured
storage root or connecting to the API SQL database.

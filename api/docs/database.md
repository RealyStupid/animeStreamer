# `core/database.py` — Async SQLAlchemy Database

This module owns the API's SQLAlchemy async engine, session factory, declarative
model base, and FastAPI database dependency. It is separate from
[`storage.py`](./storage.md): storage uses a small SQLite database to index
files, while this module connects the application to the configured SQL
database (currently intended to be PostgreSQL).

## Initialization

At import time the module:

1. Calls `get_settings()` and stores the returned cached settings.
2. Creates a SQLAlchemy async engine using `settings.DATABASE_URL`.
3. Creates `AsyncSessionLocal`, an `async_sessionmaker` bound to that engine.
4. Declares the shared SQLAlchemy `Base`.

Engine options:

- `echo=False`: SQL statements are not automatically echoed by the engine.
- `pool_size=10`: base pool size.
- `max_overflow=20`: permits overflow connections above the base pool under
  load.
- `pool_pre_ping=True`: checks a pooled connection before use to help detect
  stale connections.

The configured URL must be compatible with SQLAlchemy's async engine and the
installed async driver. A syntactically valid URL does not prove that a server
is reachable, credentials are correct, the database exists, or migrations have
run; those failures happen when connecting or executing SQL.

## Public objects

### `engine`

The application-wide `AsyncEngine`. The application lifespan uses it for a
startup connectivity probe and disposes it at shutdown. Alembic also creates
its migration engine from settings independently.

Do not create another engine for each request. Engines own connection pools and
should have application/process lifetime.

### `AsyncSessionLocal`

An `async_sessionmaker` configured with:

- `class_=AsyncSession`;
- `expire_on_commit=False`;
- `autocommit=False`; and
- `autoflush=False`.

`expire_on_commit=False` means ORM-loaded/committed values are not automatically
expired after a commit. `autoflush=False` means pending changes are not
automatically flushed before every query; routes should commit or explicitly
flush when needed. Database constraints and SQL errors can still arise at
flush/commit time.

### `Base`

The project-wide SQLAlchemy `DeclarativeBase`. ORM models subclass this class
so that their tables appear in `Base.metadata`. Alembic uses this metadata for
migration comparison. A model module must be imported before Alembic reads
metadata, or its tables may not be registered yet.

### `get_db()`

An async generator intended for use as a FastAPI dependency:

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db

async def route(db: AsyncSession = Depends(get_db)):
    ...
```

The dependency opens a session with `async with AsyncSessionLocal()`, yields it
to the route, and then:

- commits if execution returns normally after the yield; or
- rolls back and re-raises if an exception passes through the dependency.

The session context then closes the session. The generator catches `Exception`
around the yielded work, not `BaseException` subclasses such as process-level
interrupts.

## Transaction behavior and edge cases

- The dependency gives each request that uses it a session. It does not share a
  single session globally.
- A route may explicitly call `commit()` (as the registration route currently
  does). A later commit by the dependency is generally a no-op for an already
  committed transaction, but route-level explicit transaction management can
  make ownership less obvious. Prefer a consistent convention across routes.
- If an exception occurs after a route commits, the dependency cannot undo that
  already committed transaction.
- If a route catches and suppresses a database exception internally, the
  dependency may see normal completion; callers should not suppress failed
  writes and report success.
- `get_db()` does not translate database errors into HTTP responses, retry
  failed transactions, or guarantee rollback after an error the route catches
  and does not re-raise.
- A session is not safe to use concurrently from multiple async tasks.
- This module does not run Alembic migrations or call `create_all`.
- The API lifespan's connection probe is a separate concern: it executes
  `SELECT 1`; it does not verify that every expected table exists.

## Lifecycle

The FastAPI application owns engine shutdown and calls `await engine.dispose()`
after serving requests. If `engine` is used by another process entry point,
that entry point should likewise dispose it when its application lifecycle
ends.

## Troubleshooting

1. Check the effective `DATABASE_URL` source; do not print credentials in
   logs.
2. Confirm the URL uses the async dialect/driver expected by the installed
   dependencies.
3. Confirm the DB host, port, credentials, and database are reachable from the
   API process.
4. Confirm Alembic migrations have run. A successful `SELECT 1` alone does
   not prove the schema is current.
5. Inspect exceptions from query/flush/commit; this module intentionally lets
   them propagate so the request or startup logic can handle/report failure.


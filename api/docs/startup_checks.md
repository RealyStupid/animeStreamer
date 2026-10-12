# `core/startup_checks.py` — Development Startup Test Gate

This module runs the API's `unittest` suite before the application starts in
development mode. The FastAPI lifespan calls `run_development_tests()` directly
after logging the startup banner and before creating the shared
`StorageManager`, assigning it to `app.state`, or running the normal database
startup probe.

## `run_development_tests()`

The runner starts a separate Python process using the same interpreter as the
API (`sys.executable`) and runs:

```bash
python -m unittest discover -s tests -v
```

The working directory is resolved from this module's file location, so the
test discovery path is `api/tests` regardless of the server's current working
directory. Standard output and error are captured and returned together on
success. The lifespan logs that output so developers can see the individual
test results.

If unittest returns a non-zero status, the runner raises `RuntimeError` with
the captured test output. The lifespan logs the exception and re-raises it;
FastAPI startup therefore fails and Uvicorn cannot begin serving requests.
Tests are invoked only when `settings.ENVIRONMENT == "development"`.

## Isolation contract

The startup suite must not use or mutate the configured application database or
the configured persistent storage directory. Database-dependent route tests
use fake sessions; storage tests use temporary directories. The test process is
separate to keep test-only setup isolated from the API process.

This is a unittest-based gate, not a database migration check or live-service
health check. It verifies the behaviors covered by unit tests; it does not
prove connectivity to PostgreSQL, correctness against production data, or
successful deployment in every environment.

Run the same suite manually from `api/`:

```bash
python -m unittest discover -s tests -v
```


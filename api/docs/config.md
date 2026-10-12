# `core/config.py` — Application Settings

This module defines the API's Pydantic settings model and a cached function for
obtaining it. The settings object is used by database setup, authentication,
logging, CORS, and application startup. See [database.md](./database.md),
[security.md](./security.md), and [logging.md](./logging.md) for those
consumers.

## Public API

### `Settings`

`Settings` subclasses `pydantic_settings.BaseSettings`. Creating a `Settings`
instance reads recognized values from the process environment and the `.env`
file, then validates/converts them according to their declared Pydantic types.
The model configuration is:

- `env_file=".env"`: searches for `.env` according to the process's working
  directory/configuration context; it is not anchored by this module to the
  directory containing `config.py`.
- `extra="ignore"`: unknown `.env` settings are ignored rather than rejected.
- Declared defaults are used when no override is provided.

Current fields and defaults:

| Field | Default | Intended role |
|---|---|---|
| `DATABASE_URL` | `******localhost:5432/animewatcher` | SQLAlchemy async database URL. The actual example in `api/.env.example` is the configuration reference for local development. |
| `SECRET_KEY` | `insecure-dev-secret-change-me` | Signs and verifies JWT access tokens. Replace with a strong secret outside local development. |
| `ALGORITHM` | `HS256` | JWT signing algorithm supplied to `python-jose`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Default access-token lifetime. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Reserved configuration value; the current security module does not implement refresh-token creation or validation. |
| `ENVIRONMENT` | `development` | Application environment label; startup uses it to choose development/production behavior. |
| `DEBUG` | `True` | Enables diagnostic behavior and debug-level logging in the application. |
| `APP_NAME` | `AnimeWatcher API` | Application/logger name and API title. |
| `APP_VERSION` | `0.0.1` | API version metadata. |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS origins, as comma-separated text or intended JSON-array text. |

The production secret and database URL must be supplied through environment
configuration. Do not commit real credentials in `.env.example` or source
defaults. The development defaults are convenient for local use, not a secure
deployment profile.

**Current startup logging caveat:** in development with `DEBUG=True`,
`api/main.py` currently includes `SECRET_KEY` and `DATABASE_URL` in a debug
configuration dump; its database connection error log also includes the
configured URL. Do not run that mode with real production credentials or
expose those logs. This is application logging behavior, not a feature of
`Settings`, and should be changed in the startup code if sensitive credentials
may be present.

### `Settings.allowed_origins_list`

This property converts the single `ALLOWED_ORIGINS` string into a list:

1. It strips surrounding whitespace.
2. An empty value returns `["http://localhost:3000"]`.
3. A string beginning with `[` is passed to `json.loads`.
4. If that JSON parsing raises `JSONDecodeError`, the original text is treated
   as a comma-separated list.
5. Each comma-separated value is stripped and empty items are omitted.

Examples:

```dotenv
ALLOWED_ORIGINS=http://localhost:3000,https://anime.example
```

or:

```dotenv
ALLOWED_ORIGINS=["http://localhost:3000","https://anime.example"]
```

Edge cases:

- A malformed bracket-prefixed value falls back to comma splitting rather than
  raising a settings-validation error.
- The JSON branch returns `json.loads`'s result directly. This property does
  not itself verify that the JSON value is a list of strings. Supply a JSON
  array of origins, not an object, scalar, or mixed-type array.
- Empty comma-separated entries are discarded.
- Setting the value to blank does not result in an empty allowlist; it restores
  the localhost default.
- CORS validation/normalization beyond this conversion belongs to FastAPI's
  middleware, not this property.

### `get_settings()`

`get_settings` is decorated with `functools.lru_cache` and returns
`Settings()`. In ordinary use, the first call loads and validates settings;
later calls reuse that same object, avoiding repeated `.env` reads and
validation.

Operational implications:

- Environment changes made after the first call are not automatically picked
  up in the running process.
- Tests that need different environment values should clear the cache with
  `get_settings.cache_clear()` before constructing a new settings object, and
  restore test environment state afterward.
- Modules that assign `settings = get_settings()` at import time retain their
  reference; clearing the function cache does not replace those already
  imported module globals.
- Invalid declared values can raise Pydantic validation errors on first
  construction. They are not silently replaced with defaults.

## How to configure

Use environment variables or copy `api/.env.example` to a local `.env`. Keep
secrets in an ignored local `.env` or a deployment secret store. `Settings`
does not create the `.env` file, read alternate files, or expose a reload
operation.

The application currently calls `get_settings()` during imports and uses the
result to configure API routes, CORS, database initialization, logging, and
storage. Therefore, set environment values before starting/importing the API.

## Boundaries

This module only defines and loads settings. It does not:

- open or test a database connection;
- configure log handlers;
- generate JWT keys;
- ensure an `ENVIRONMENT` label is one of a fixed set;
- implement refresh tokens; or
- guarantee that example defaults are suitable for production.

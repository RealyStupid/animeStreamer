# API Core Documentation Guidance

These documents explain the modules in `api/core/`. Keep them aligned with the
implementation, not with intended or planned behavior.

## Updating the documentation

- When a `core/*.py` module changes, update the matching `core/*.md` document in
  this folder in the same change.
- Describe public functions, configuration, lifecycle, error behavior, and
  relevant edge cases. Link related core documents rather than duplicating
  their explanations.
- Be explicit about destructive or security-sensitive behavior. In particular,
  `StorageManager` treats its SQLite index as authoritative and can delete
  unindexed files from registered storage roots.
- Distinguish the API's SQL database from the storage manager's per-root SQLite
  filesystem index. They are separate systems with different responsibilities.
- Do not claim stronger guarantees than the code provides. Storage signature
  checks are not full media decoding or malware scanning; periodic
  reconciliation is interval-based, not instantaneous.
- Never include real credentials, tokens, or secret values in examples. Use
  clearly fake placeholders and explain the required configuration.

## Documentation layout

- `config.md` documents environment-backed application settings.
- `database.md` documents SQLAlchemy engine/session setup.
- `logging.md` documents the configurable application logger and the separate
  storage log integration.
- `security.md` documents password hashing and bearer-token authentication.
- `storage.md` documents local storage, indexing, quotas, placement, cleanup,
  and lifecycle.
- `startup_checks.md` documents the development-only startup test gate.

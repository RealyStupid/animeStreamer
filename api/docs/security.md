# `core/security.py` — Passwords and Bearer Authentication

This module supplies password hashing/verification, JWT access-token creation,
and the FastAPI dependency that resolves a bearer token to a database user.
Authentication routes call these helpers; see `api/routes/auth.py` for
registration and login request handling.

## Import-time objects and dependencies

When imported, the module:

- constructs `pwd_context` with `PasswordHash.recommended()` from `pwdlib`;
- constructs `oauth2_scheme` with
  `OAuth2PasswordBearer(tokenUrl="token")`; and
- calls `get_settings()` and stores the resulting cached settings object.

The OAuth dependency extracts a bearer token from the request's Authorization
header. Missing/malformed bearer credentials are rejected by the dependency
before `get_current_user` can look up a user.

**OpenAPI URL detail:** this module declares `tokenUrl="token"`, while the
actual login route is `/auth/token` because its router has an `/auth` prefix.
Check the API's generated OAuth/OpenAPI configuration if the docs UI's
Authorize flow is used; the declaration and route prefix are separate facts.

## `hash_password(password)`

Passes the plaintext password to `pwd_context.hash` and returns the encoded
password hash string for storage in `Users.password_hashed`.

- The route should store the returned hash, never the original password.
- The helper has no application-specific password policy or input validation;
  length/complexity requirements belong in the request schema or route.
- The exact recommended hash algorithm is selected by the installed `pwdlib`
  implementation.
- Hashing is intentionally more expensive than a fast general-purpose digest.
  Do not replace it with plain SHA/MD5 or log the password.

## `verify_password(plain_password, hashed_password)`

Delegates verification to the same `pwd_context` and returns its boolean
result. The login route uses this to compare a submitted password with the
stored encoded hash.

The helper does not look up the account and does not return user information.
Unexpected hasher errors are not converted here to a false result; callers
should not suppress them and claim a successful login.

## `create_access_token(data, expires_delta=None)`

Creates an access token as follows:

1. Copies the input mapping; the caller's dictionary is not directly mutated.
2. Uses the supplied `expires_delta`, or defaults to
   `ACCESS_TOKEN_EXPIRE_MINUTES`.
3. Computes expiration from the current UTC time and adds/overwrites the `exp`
   claim.
4. Encodes the claims with `SECRET_KEY` and `ALGORITHM`.

In the login route, `data={"sub": user.email}` makes the user's email the token
subject. Existing `exp` supplied by the caller is replaced with the computed
expiration. Other claims are preserved.

Edge cases and responsibilities:

- An explicitly supplied zero `timedelta` is falsey, so the current
  `expires_delta or default` expression uses the default instead of producing
  an immediately expiring token.
- This helper does not automatically add `sub`, `iat`, issuer, audience, role,
  or refresh-token claims. The caller must provide any required non-expiration
  claims.
- It does not persist or revoke tokens.
- Configuration mistakes in the secret or algorithm can cause encode/decode to
  fail; they are not silently repaired.
- `REFRESH_TOKEN_EXPIRE_DAYS` exists in settings but this module currently
  creates only access tokens.

## `get_current_user(token, db)`

This async FastAPI dependency:

1. Receives the bearer token through `oauth2_scheme`.
2. Decodes the token using the configured secret and a one-element allowed
   algorithm list.
3. Reads the `sub` claim as an email. Missing `sub` produces a standard
   `401 Unauthorized` response.
4. Queries `Users.email` through the provided async SQLAlchemy session.
5. Returns the matching `Users` ORM object or raises the same `401` response if
   no account exists.

The unauthorized response has `WWW-Authenticate: Bearer` and a generic
`"Could not validate credentials"` detail. `JWTError` from decoding is
translated to that response. Database errors are not caught here; they
propagate through the route/session dependency.

### Input and identity edge cases

- Tokens with no subject are rejected.
- Tokens whose subject is not a current user's email are rejected, even if the
  token signature and expiration are otherwise valid.
- The token does not embed a user ID, so changing a user's email can make
  previously issued tokens stop resolving.
- The type annotation says `email: str`, but the code obtains the value from an
  untrusted JWT payload; runtime validation beyond the missing-value check is
  not explicitly performed here.
- Authorization decisions based on user role are not made by this dependency.
  Routes must add their own role/permission checks.
- A valid JWT does not imply the user remains enabled or authorized; this
  dependency currently checks only that an email-matched row exists.

## Data-flow summary

```text
POST /auth/register -> hash_password -> Users.password_hashed
POST /auth/token    -> verify_password -> create_access_token(sub=email)
protected route     -> oauth2_scheme -> get_current_user -> Users row
```

The database session lifecycle is documented in
[`database.md`](./database.md). General app secrets and environment loading are
documented in [`config.md`](./config.md).


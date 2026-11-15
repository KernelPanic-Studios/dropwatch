# ADR-0007: One page password, hashed session tokens, and a Host check instead of user accounts

**Status:** Accepted (recorded retroactively, 2026-11-15)

## Context

The dashboard is opened on a home network, usually by IP address or the server's name, over plain HTTP.
Anyone who can open it could pause mining or change the lists. A web page elsewhere can point its own
domain at a LAN address (DNS rebinding) and talk to the server as same-origin.

## Decision

- **One password for the page,** chosen on the first visit (`setup` in `src/dropwatch/api/auth.py`),
  stored as an argon2 hash, at least 8 characters. No users, no roles.
- **Sessions:** a random token in the `dm_session` cookie (`HttpOnly`, `SameSite=Strict`, 30 days); only
  its sha256 is stored. Settings lists the signed-in browsers by a 16-character prefix of the hash.
- **Login limiter:** 5 wrong passwords per client address in 15 minutes, then 429 with `Retry-After`; in
  memory; one password check at a time so parallel guesses all count (commit `a334e4b`).
- **`HostCheck`** (`src/dropwatch/api/app.py`): answer only to IP addresses, bare names, private suffixes
  and names in `DROPWATCH_HOSTS`. A rebinding page's domain is a public one, so it is refused.
- `require_session` guards every route but the five public ones; `tests/test_auth_api.py` keeps the
  list exact. The OpenAPI schema is not served.

## Consequences

- Nothing to manage but one password; it is separate from the Twitch account.
- **Everyone signed in can do everything,** including signing Dropwatch out of Twitch and exporting
  notification secrets in a backup.
- **The limiter counts the proxy as one address** unless `FORWARDED_ALLOW_IPS` names it, so five wrong
  guesses through a proxy lock everyone out (documented in `docs/docker.md`).
- `SameSite=Strict` does not stop same-site requests from other ports on the same host (finding F1).
- The cookie is never `Secure` (finding F8).

## Evidence

`src/dropwatch/api/auth.py`, `src/dropwatch/api/app.py` (`HostCheck`, `LOCAL_SUFFIXES`, `create_app`),
`src/dropwatch/store.py` (web sessions), `tests/test_auth_api.py`, `tests/test_lan_hardening.py`.

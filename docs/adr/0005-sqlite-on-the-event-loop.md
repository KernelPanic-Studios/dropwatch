# ADR-0005: Keep everything in one SQLite file, read and written synchronously on the event loop

**Status:** Accepted (recorded retroactively, 2026-11-15)

## Context

One account, one process, a few browsers. The data is small: lists, settings, a week of events, a year of
claims and campaign records. The original spec (§5) planned `asyncio.to_thread` for store calls; the code
calls `sqlite3` directly, and its docstring says why: "Every call is a few milliseconds, so the runner
calls it directly."

## Decision

`Store` (`src/dropwatch/store.py`) opens one `sqlite3` connection to `/data/drops.db` and every caller, API
handlers and the runner alike, uses it from the event loop thread. Writes commit at once (`with self._db:`).
The schema is `CREATE TABLE IF NOT EXISTS` plus additive migrations in `Store.__init__` (`ALTER TABLE ... ADD
COLUMN` when `PRAGMA table_info` lacks a column). Older rows read back with `NULL` details. Retention is
enforced on write: events 7 days, campaign and points logs 400 days, seen channels 30 days, expired page
sessions on each new one. The file is created `0600`.

The one slow operation, argon2 password verification, reads the hash on the loop and verifies in
`asyncio.to_thread` (`login` in `api/auth.py`), because the connection belongs to the loop thread.

## Consequences

- No database server; a backup is a copy of one file (Dropwatch makes one before each upgrade,
  [ADR-0011](0011-restart-instead-of-repair.md)).
- No migration framework: a column can be added, never renamed or dropped, without new code.
- **A slow disk stalls mining and every request together.** Settings are read one row per key (20
  queries per `get_settings`), which is cheap on SQLite but all on the loop (finding F7).
- **Store calls cannot move to a thread** without opening a connection per thread.

## Evidence

`src/dropwatch/store.py` (`SCHEMA`, `Store.__init__`, the retention constants), `src/dropwatch/api/auth.py`
(`login`).

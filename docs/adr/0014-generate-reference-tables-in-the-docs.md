# ADR-0014: Generate the docs' reference tables from the code, and fail the tests when they drift

**Status:** Proposed

## Context

Three things in the operator docs are copies of tables in the code: the settings catalogue
(`SETTINGS`, `SETTING_DEFAULTS` and the bounds in `SettingsIn`), the notification services and their
fields (`CHANNELS`), and the runtime dependencies and their licences (`uv.lock`, `web/package-lock.json`).
Typed by hand they drift the first time someone adds a setting.

## Decision

Hand-written pages carry marker pairs, `<!-- generated:<kind> <id> -->` and `<!-- /generated:<kind> -->`.
`scripts/gen_docs.py` imports the tables from source and rewrites only the marked blocks, and writes
`docs/third-party-packages.md` whole. `--check` exits non-zero when anything is stale.
`tests/test_docs_generated.py` runs in the normal `pytest` run: it fails when a block is stale, when a
marker names an id the code does not have, when a service has no block, or when a licence is not on the
allowed list; and it first proves it can find the pages and catch a stale block and an unknown id.

## Consequences

- Adding a setting or a notification service fails the tests until `uv run python scripts/gen_docs.py`
  is run and the result committed.
- A dependency with a new licence fails the tests until the licence is added to `ALLOWED_LICENCES` in
  the script, which makes the choice visible in review.
- The Python licences are read from the installed packages, so the check needs `uv sync` first (CI does
  it).

## Evidence

`scripts/gen_docs.py`, `tests/test_docs_generated.py`, `docs/guides/configuration.md`,
`docs/guides/notifications.md`, `docs/third-party-packages.md`.

# ADR-0009: The page's API types are generated from the server's OpenAPI schema, and both are checked

**Status:** Accepted (recorded retroactively, 2026-11-15)

## Context

The API and the page change together, often in one commit. Hand-written TypeScript types for 42
operations would drift.

## Decision

FastAPI builds the schema from the pydantic models in `src/dropwatch/api/models.py`. `dropwatch openapi`
writes it to `docs/api/openapi.json`, and `npm run gen:api` turns that into `web/src/api/types.ts`
(`openapi-typescript`). `tests/test_openapi.py` fails when the committed schema differs from a fresh
build; `web/src/api/types.freshness.test.ts` fails when `types.ts` differs from a fresh generation. The
schema is not served by the running app (`openapi_url=None`). Request bodies forbid unknown fields
(`StrictIn`, `SettingsIn`), so a misspelt field is a 422, not a silent no-op.

## Consequences

- A change to a response model shows up as a type error in the page.
- Every API change needs two commands before the tests pass; `docs/development.md` lists them, and the
  version bump is one of the changes (the schema carries the version).
- `/api/img/{name}` and the page catch-all are left out of the schema (`include_in_schema=False`).

## Evidence

`src/dropwatch/cli.py` (`openapi`, `build_app_for_schema`), `tests/test_openapi.py`,
`web/src/api/types.freshness.test.ts`, `web/package.json` (`gen:api`).

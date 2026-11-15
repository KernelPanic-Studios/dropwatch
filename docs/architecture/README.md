# Architecture

These pages were written by reading the code on `main` at `687d794` (commit of 2026-11-10, read
2026-11-15): `src/dropwatch/`, `web/src/`, `tests/`, the `Dockerfile`, `docker/entrypoint.sh`,
`unraid/dropwatch.xml` and `.github/workflows/docker.yml`. Every box and row names the file behind it.
They are kept current in the pull request that changes the system; the rule is in
[development.md](../development.md#keeping-the-docs-current).

| Page | What it covers |
|---|---|
| [../architecture.md](../architecture.md) | The codebase map: directories, boot order, subsystems, sources of truth |
| [c4.md](c4.md) | System context, containers, and the components of the one process |
| [data-flows.md](data-flows.md) | DFD level 0, the mining cycle, the page and live updates, notifications, settings and backups, Twitch sign-in, and every key data structure |
| [user-flows.md](user-flows.md) | Eleven journeys with their decision points and literal error texts |
| [reference-architecture.md](reference-architecture.md) | Which well-known patterns it follows, where it departs, and what that costs |
| [../adr/](../adr/README.md) | The decisions behind the shape |

## Shape in one line

A single-process, single-container modular monolith: an asyncio mining loop around a pure planner, and a
FastAPI backend-for-frontend over the same memory and one SQLite file, with an in-process event bus that
tells the page when to re-read.

## Findings

Ordered by how much they matter. None of them is fixed in this change.

**F1. Body-less POSTs can be sent from another site on the same host.** The `dm_session` cookie is
`SameSite=Strict` (`_set_cookie` in `src/dropwatch/api/auth.py`), but "same site" ignores the port, so a
page served by any other web app on the same server or LAN name (common on an Unraid box) is same-site and
the browser sends the cookie. A plain cross-origin `fetch(..., {method: "POST", mode: "no-cors",
credentials: "include"})` needs no CORS preflight when it has no body. Nine routes take no body:
`/api/twitch/signout`, `/api/twitch/signin`, `/api/logout`, `/api/sessions/sign-out-others`,
`/api/resume`, `/api/refresh`, `/api/streak/end`, `/api/notify/test` and `POST
/api/needs/ignored/{campaign_id}` (counted from `docs/api/openapi.json`). Checked 2026-11-15 with an
`httpx` ASGI client against `create_app`: `POST /api/twitch/signout` with only the cookie answered 204 and
stopped the miner; `POST /api/pause` with a `text/plain` body answered 422, so routes with a JSON body are
safe. `/api/restore` already checks the content type for this reason. **Impact:** a page elsewhere on the
same host can sign Dropwatch out of Twitch, sign out other browsers, or spam the notification test. It
cannot read anything. **Fix, cheapest first:** in `HostCheck`, refuse `POST`/`PUT`/`DELETE` whose `Origin`
header is present and does not match `Host`; or have `call` in `web/src/api/client.ts` send a custom
header on every request and require it on unsafe methods (a custom header forces a preflight, which fails
without CORS).

**F2. A locked-out login says the miner is unreachable.** After 5 wrong passwords `/api/login` answers
`429 Too many wrong passwords. Try again in N min.` (`login` in `src/dropwatch/api/auth.py`), but
`LoginScreen` in `web/src/screens/PagePassword.tsx` shows "Couldn't reach the miner. Try again." for every
status except 401. No web test covers a 429. **Impact:** the person is told to check that Dropwatch is
running while it is deliberately making them wait 15 minutes. **Fix:** show `err.message` for any
`ApiError` other than 401, as `SetupScreen` already does.

**F3. A manual run of the release workflow moves `:latest`.** `.github/workflows/docker.yml` also runs on
`workflow_dispatch`, and the `image` job takes the version from `GITHUB_REF_NAME` with a leading `v`
removed. Started by hand on `main`, it pushes `ghcr.io/kernelpanic-studios/dropwatch:main` and `:latest`,
so every Unraid server on `:latest` is offered an untagged build as an update. Read from the workflow; not
run. **Fix:** tag `:latest` only when `startsWith(github.ref, 'refs/tags/v')`, or let manual runs run the
`test` job only.

**F4. The settings catalogue is written four times with nothing comparing the copies.** `SETTINGS` and
`SETTING_DEFAULTS` (`src/dropwatch/store.py`), `SettingsIn` and `SettingsOut`
(`src/dropwatch/api/models.py`) each list the 20 keys. They match today (checked with a one-line script
comparing the four key sets). A key added to the store but not to `SettingsIn` cannot be saved from the
page; one missing from `SettingsOut` is dropped from the API without an error. The same is true, smaller,
for `ACTIVITY_FIELDS` against the 14 event kinds the code logs, and `EVENT_KINDS` in
`web/src/api/live.ts` against the 8 the bus carries. **Fix:** one test that compares the key sets; or
build `SettingsOut` from `SETTINGS`.

**F5. Lint is not run in CI.** `.github/workflows/docker.yml` runs `pytest`, `tsc --noEmit` and
`vitest`, but not `ruff check src tests`, which [development.md](../development.md#tests-and-checks) lists
as a check. It passes today. **Fix:** add `uv run ruff check src tests` to the `test` job.

**F6. The runner probes the store with `getattr`.** `Runner` calls store methods through
`getattr(self._store, "<name>", None)` or `hasattr` in 13 places (`grep -cE "getattr\(self\._store|hasattr\(self\._store" src/dropwatch/runner.py`)
so test fakes can leave methods out. A renamed `Store` method turns the feature off silently: for
example, renaming `add_claim` would stop History from recording claims with no error. **Fix:** a `Protocol`
for the store, implemented in full by the fakes ([reference-architecture.md](reference-architecture.md#d3-the-runner-reaches-into-the-store-with-getattr)).

**F7. Settings are read one row at a time.** `Store.get_settings` runs one `SELECT` per key: 20 queries,
and `get_prefs` 25 (measured with `sqlite3.Connection.set_trace_callback`). The runner calls them from
`_points_on`, `_streak_on`, `_campaigns_every` and `get_prefs` on every plan, and the notifier on every
event and every 30 s. SQLite on a local disk makes this cheap, but it is all on the event loop
([ADR-0005](../adr/0005-sqlite-on-the-event-loop.md)). **Fix:** one `SELECT key, value FROM settings`.

**F8. The cookie is never marked `Secure`.** `_set_cookie` passes `secure=False` always, which is right on
plain-HTTP LAN access, but behind an HTTPS reverse proxy the cookie could be `Secure`. **Impact:** low;
the proxy case is the only one where it matters, and it then depends on nothing else serving the same name
over HTTP. **Fix:** `secure=request.url.scheme == "https"` (uvicorn sets the scheme from
`X-Forwarded-Proto` when `FORWARDED_ALLOW_IPS` trusts the proxy).

**F9. The image's health check assumes port 5800.** `HEALTHCHECK` in the `Dockerfile` calls
`http://127.0.0.1:5800/api/health/miner`, while the port comes from `CMD`. Someone who overrides the
command with another `--port` gets a container that always reports unhealthy. The in-app watchdog does
not depend on it. **Fix:** document it next to the `CMD`, or read the port from an environment variable in
both places.

## Where the docs diverged from the code

| Where | Said | Code | Status |
|---|---|---|---|
| `docs/docker.md`, `--log-opt` row | The miner writes its log to standard output | `logging.StreamHandler()` in `setup_logging` (`src/dropwatch/cli.py`) writes to standard error; Docker keeps both | Fixed |
| `docs/docker.md`, `DROPWATCH_HOSTS` row | Private suffixes `.local`, `.lan`, `.home`, `.home.arpa`, `.internal`, `.localdomain` | `LOCAL_SUFFIXES` in `src/dropwatch/api/app.py` also has `.localhost` | Fixed |
| Original spec §5 (`docs/superpowers/specs/`) | `store` runs `sqlite3` via `asyncio.to_thread` | Synchronous on the event loop (`src/dropwatch/store.py`) | Noted: the spec is a historical record |
| Original spec §7 | Tables `campaign_snapshots` and `ended_campaigns`; four missed reasons | `campaign_log`; seven reasons in `Store.missed_between` | Noted |
| Original spec §8 | SSE kinds `state`, `progress`, `claimed`, `switched`, `needs_you`, `signin` | Also `refreshed` and `claim_failed` (`Runner._emit`) | Noted |
| Original spec §12 | Port 5810 in Docker | The image serves 5800 (`Dockerfile` `CMD`); 5810 is the CLI default for a PC | Noted |
| Original spec §15 | "Mining several channels at once" is not in v1 | Up to three streams: one for drops, two for the Channel points list (`POINTS_SLOTS`) | Noted |
| `src/dropwatch/store.py` docstring | "phase-1 subset: session, lists, settings, events" | 12 tables | Noted (code comment, left for a code change) |
| `src/dropwatch/cli.py`, `run` command | "added in Task 11" | A leftover plan reference | Noted (code comment) |

## Where these diagrams simplify on purpose

- The api router's 36 operations are one box in [c4.md](c4.md#level-3-components-of-the-process);
  `docs/api/openapi.json` lists them.
- The three `Watcher`s are drawn as one process in the data flows.
- PubSub reconnects, `PING`/`PONG` and topic batching (20 per `LISTEN`) are left out of the diagrams;
  they are in `src/dropwatch/twitch/pubsub.py`.
- Watch-streak visits, link probing and claim catch-up are described in prose, not drawn; they are
  branches inside `Runner._plan` and `Runner.tick`.
- The PC-only browser sign-in (`twitch/auth_browser.py`, `dropwatch signin --browser`) and the `capture`
  and `lists` CLI commands are left out of the flows; the Docker image cannot run the first.

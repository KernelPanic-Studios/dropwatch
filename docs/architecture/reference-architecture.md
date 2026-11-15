# Reference architecture

Read against `main` at `687d794` (2026-11-15).

**Dropwatch is a single-process modular monolith with a pure decision core (functional core, imperative
shell), ports-and-adapters edges to Twitch, a backend-for-frontend JSON API, and an in-process
event-notification layer that tells the page when to re-read state.**

## Pattern table

| Canonical pattern | Where it shows up | Fit |
|---|---|---|
| Modular monolith | One package, one process; modules with one job each (`planner`, `runner`, `store`, `alerts`, `notify`, `api/`, `twitch/`) and imports that point inward | **Strong.** The spec's unit table (§5 of the original design) still matches the files |
| Functional core, imperative shell | `planner.plan()` and `models.py` take `now` and data and return values; `Runner` does the I/O and acts on the `Plan` | **Strong.** `planner.py` says "Pure: no I/O and no clock reads"; the planner tests are table-driven |
| Ports and adapters (hexagonal) | `HttpTransport` protocol (`twitch/transport.py`), injected `post` in `notify.py`, injected `get` in `images.py`, injected `clock` everywhere, `build` in `MinerService` | **Partial.** Adapters are injected and faked in tests, but `Runner` calls the store directly and probes it with `getattr(..., None)` instead of a declared port |
| Backend for frontend | `/api/state`, `/api/history`, `/api/points` return screen-shaped snapshots built by `api/views.py`; the page's types are generated from the schema | **Strong.** There is one client, and the API is shaped for it |
| Event notification | `EventBus` publishes "something changed"; the page re-fetches `/api/state` | **Strong.** Events carry hints, not state |
| Event-carried state transfer | The page could apply events instead of re-reading | **No, by choice.** One re-read after a 500 ms debounce is simpler and never drifts |
| Event sourcing | `events` table | **No.** It is a 7-day diagnostic log for Activity; state is not rebuilt from it |
| CQRS | Reads from `views.py` snapshots, writes through commands on `Runner` and setters on `Store` | **Partial, informal.** Same store, same models; the split is by function, not by model |
| Transactional outbox | Notifications | **No.** Alerts are sent straight from memory; a crash between deciding and sending loses that alert. Only the weekly summary records delivery |
| Policy enforcement point | `require_session` on two routers; `HostCheck` before everything | **Strong for what it does.** There is one permission (signed in or not); no policy decision point is needed |
| Configuration as data | `SETTINGS` and `SETTING_DEFAULTS` in `store.py`, edited from the page; `CHANNELS` in `notify.py` | **Strong.** Only deployment facts are environment variables |
| Supervisor / let it crash | `Watchdog` exits the process; Docker's restart policy restarts it | **Strong.** Recovery is a fresh process, not in-process repair |
| Twelve-factor | Config in env for deployment, logs to the console, one process type, port binding, disposable process | **Partial.** State is a local SQLite file on a volume (factor VI expects a backing service), and there is exactly one process by design |

## Deviations

### D1. The store is synchronous and runs on the event loop

**Canonical:** async I/O, or a thread pool for blocking database calls (the original spec planned
`asyncio.to_thread`). **Here:** `Store` uses `sqlite3` directly from handlers and the runner
(`src/dropwatch/store.py`, docstring: "Every call is a few milliseconds"). **Cost:** a slow disk stalls the
mining loop and every request together, and the connection cannot be shared with a thread (the login path
reads the hash on the loop and only verifies in a thread). `get_settings` makes 20 `SELECT`s per call and
`get_prefs` 25, and the runner calls them several times per plan. **Accepted in:**
[ADR-0005](../adr/0005-sqlite-on-the-event-loop.md).

### D2. One process holds all live state

**Canonical:** keep state in a backing service so any replica can serve. **Here:** the plan, campaigns, live
channels, overrides, exclusions, claim ids already used, the login limiter and the notifier's memory are
in `Runner`, `LoginLimiter` and `Notifier` (`src/dropwatch/runner.py`, `api/auth.py`, `alerts.py`).
**Cost:** exactly one replica; a restart forgets which alerts were sent and which channels were set aside.
That is also the product rule: two miners on one account fight over watch progress. **Accepted in:**
[ADR-0002](../adr/0002-one-process-one-miner.md).

### D3. The runner reaches into the store with `getattr`

**Canonical:** a declared port (a `Protocol`) the runner depends on. **Here:** `Runner` calls
`getattr(self._store, "record_seen", None)`, `"log_campaigns"`, `"add_claim"`, `"get_settings"` and
others, so test fakes can leave methods out (`src/dropwatch/runner.py`). **Cost:** a renamed `Store` method
silently turns a feature off in production instead of failing a test; History would stop recording claims
without an error. **Accepted in:** not recorded; it is listed as finding [F6](README.md#findings).

### D4. Alerts are not durable

**Canonical:** write the alert, then deliver it (outbox). **Here:** `Notifier.run` decides and sends in one
step (`src/dropwatch/alerts.py`). **Cost:** an alert decided just before a restart is lost; a recovery
message after a restart is never sent because the process forgot the alert went out. For a home tool with
"it stopped" and "it's back" messages this is mild. **Accepted in:**
[ADR-0010](../adr/0010-notifications-sent-from-memory.md).

### D5. Discovery depends on a third party

**Canonical:** read from the system of record. **Here:** with a TV-code session Twitch hides the campaign
list, so `Catalog` reads a public catalogue run by an anonymous third party and merges Twitch's own
Inventory over it (`src/dropwatch/twitch/catalog.py`, `TwitchClient.campaigns`). **Cost:** new campaigns
are not found while it is down, and its records are trusted for names, games, times and allowed channels.
**Accepted in:** [ADR-0004](../adr/0004-tv-code-sign-in-and-public-catalogue.md).

## Is a different pattern warranted?

No. The workload is one account, a 10-second loop, and a handful of browsers; a single async process with
SQLite fits it and keeps install to one container. Two changes pay off most inside the current pattern:

1. **Give the runner a `Protocol` for the store** and drop the `getattr` probes (D3). Test fakes then have
   to implement the whole port, and a rename fails at type-check or test time.
2. **Read settings in one query and cache them per plan** (D1). `get_settings` could be one
   `SELECT key, value FROM settings`, which removes most of the per-tick queries without moving the store
   off the loop.

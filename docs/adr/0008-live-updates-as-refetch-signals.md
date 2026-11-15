# ADR-0008: Live updates are server-sent "something changed" signals; the page re-reads the state

**Status:** Accepted (recorded retroactively, 2026-11-15)

## Context

The page should follow the miner within a second or so: progress, switches, claims, sign-in steps. The
only client is the dashboard, one-way traffic is enough, and the miner must never wait on a slow browser.

## Decision

`EventBus` (`src/dropwatch/events.py`) gives each subscriber a bounded queue (100) and drops the oldest
event when it is full, so publishing never blocks. `/api/events` streams it as server-sent events with a
ping every 15 s (`src/dropwatch/api/sse.py`) and ends when the page session is gone. The page
(`web/src/api/live.ts`) treats any event as a hint and re-fetches `/api/state` 500 ms after the last one;
it shows "Can't reach the miner" after 15 s without a working stream and reconnects every 5 s. The same
bus feeds the notifier.

## Consequences

- The page never has to merge events into its state, so it cannot drift from the server.
- Dropping events is safe, because the next re-read catches up.
- Each burst of events costs a full `/api/state`, which `state_view` builds from memory and a few store
  reads.
- `X-Accel-Buffering: no` is set for proxies that buffer; a reverse proxy that buffers anyway delays
  updates.

## Evidence

`src/dropwatch/events.py`, `src/dropwatch/api/sse.py`, `events` in `src/dropwatch/api/app.py`,
`web/src/api/live.ts`, `web/src/store.tsx`.

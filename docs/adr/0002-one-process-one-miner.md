# ADR-0002: One process runs the miner and the API, for one Twitch account

**Status:** Accepted (recorded retroactively, 2026-11-15)

## Context

Dropwatch earns drops for one Twitch account. Two miners on the same account fight over watch progress
(the README and `docs/docker.md` both warn about it). The work is almost all waiting on the network: a
10-second playback tick, a 5-minute refresh, a websocket. The dashboard needs the miner's live state: the
current plan, what is being watched, which channels are set aside.

## Decision

`dropwatch serve` (`serve` in `src/dropwatch/cli.py`) runs uvicorn, the FastAPI app, the mining loop, the
PubSub websocket, the notifier and the image keeper as asyncio tasks on one event loop in one process.
`MinerService` (`src/dropwatch/service.py`) holds at most one `Runner`, behind a lock. The API reads the
runner's memory directly (`state_view` in `src/dropwatch/api/views.py`) and steers it with method calls
(`pause`, `resume`, `mine_now`, `use_channel`, `end_streak_visit`, `refresh`, `replan`). One install holds
one Twitch session (`session` table, `CHECK (id = 1)`).

## Consequences

- No broker, no IPC, no cache server: the state the page shows is the state the miner acts on.
- Install is one container with one volume.
- **Only one replica can run, and nothing enforces it.** A second container or a PC copy on the same
  account is not detected; operators are told in the README and `docs/docker.md`.
- **A restart forgets in-memory state:** excluded channels, used claim ids (`Runner._claimed`), "may need
  linking" marks, the login limiter, which alerts were sent. Twitch keeps the drop progress itself, so
  mining resumes where it was.
- A blocking call anywhere stalls everything (see [ADR-0005](0005-sqlite-on-the-event-loop.md)).

## Evidence

`src/dropwatch/cli.py` (`serve`), `src/dropwatch/service.py` (`MinerService`, `build_parts`),
`src/dropwatch/store.py` (`session` table), `docs/docker.md`.

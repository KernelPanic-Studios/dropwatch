# ADR-0011: When mining is stuck, exit and let Docker restart it; copy the database before an upgrade

**Status:** Accepted (recorded retroactively, 2026-11-15)

## Context

A long-running miner can get stuck in ways the code does not foresee: a crashed task, a hung request.
Unraid runs no autoheal container, and Docker's health status on its own restarts nothing. Upgrades
change the database in place (additive migrations), which cannot be undone by running the old image.

## Decision

- `miner_health` (`src/dropwatch/maintenance.py`) is unhealthy when the mining loop crashed or has not
  ticked for 15 minutes (`HEALTH_STALL`, longer than any back-off). Signed out, paused and idle are
  healthy. `/api/health/miner` answers 503 then; the image's `HEALTHCHECK` calls it.
- `Watchdog` checks the same function every 60 s and calls `os._exit(3)` after two bad checks in a row.
  It is on only when `DROPWATCH_EXIT_WHEN_STUCK=1`, which the image sets; on a PC nothing would restart
  it.
- The container must run with a restart policy (`--restart unless-stopped`); the Unraid template sets it.
- Before `Store` opens the database, `backup_on_upgrade` copies `drops.db` to
  `drops.db.before-<version>+<build>` when the recorded `last_build` differs, keeping the newest two. A
  failed copy is logged and never stops the miner. The image refuses to build without `DROPWATCH_COMMIT`
  so every build has a distinct name.

## Consequences

- A stuck miner is back within about two to three minutes of being noticed, with no operator.
- **Without a restart policy the watchdog just stops the container.** `docs/docker.md` marks the policy
  as required.
- Rollback is by hand: stop, copy the file back, run the old image.

## Evidence

`src/dropwatch/maintenance.py`, `src/dropwatch/cli.py` (`watch_health`, `main`), `Dockerfile`
(`HEALTHCHECK`, `DROPWATCH_COMMIT`, `DROPWATCH_EXIT_WHEN_STUCK`), `unraid/dropwatch.xml`,
`tests/test_docker_health.py`; commits `856fc8a`, `f9d0765`.

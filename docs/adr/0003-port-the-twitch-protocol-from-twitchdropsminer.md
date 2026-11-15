# ADR-0003: Port the Twitch protocol from TwitchDropsMiner and keep the sources beside it

**Status:** Accepted (recorded retroactively, 2026-11-15)

## Context

The hard part of a drops miner is Twitch knowledge that is not documented: persisted query hashes, client
ids, the minute-watched event, PubSub topics, the 24-hour claim grace. TwitchDropsMiner (DevilXD) and two
forks have it, under the MIT licence, in Python, but coupled to a desktop GUI. The original spec (§2)
records choosing a port into a new, separated app over wrapping upstream.

## Decision

The Twitch code in `src/dropwatch/twitch/` and the progress rules in `src/dropwatch/models.py` are ported
from those projects, with their notices in `NOTICE`. The upstream sources are kept unmodified in
`reference/` for comparison. Query hashes and client ids live in one module, `twitch/constants.py`, whose
docstring says "Update hashes here only". `reference/` is excluded from lint (`extend-exclude` in
`pyproject.toml`) and from the image (`.dockerignore`).

## Consequences

- When Twitch changes something, the fix can usually be found upstream and compared line by line.
- **Hashes rotate without warning.** A changed hash breaks one feature (discovery, claims) until
  `constants.py` is updated; the "isn't earning" and "stopped" notifications exist so the owner finds out.
- `reference/` adds files to the repository that are never run.

## Evidence

`NOTICE`, `reference/`, `src/dropwatch/twitch/constants.py`, module docstrings in `twitch/watch.py`,
`twitch/pubsub.py`, `twitch/gql.py`, `models.py`.

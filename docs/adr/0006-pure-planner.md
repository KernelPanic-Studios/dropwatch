# ADR-0006: The planner is a pure function

**Status:** Accepted (recorded retroactively, 2026-11-15)

## Context

What to mine, and on which channel, decides everything Dropwatch earns. The rules are many: Never beats
Priority, Priority order, pins, known links before unknown ones, least spare time first, a hold on the
current campaign to stop flapping, favourite then allowed then any channel. The original spec (§13) asks
for table-driven tests and a mutation check on it.

## Decision

`plan()` in `src/dropwatch/planner.py` takes campaigns, live channels, `Prefs`, `now` and the current
choice and overrides, and returns a frozen `Plan`. It does no I/O and reads no clock. The progress
arithmetic it uses (`campaign_ratio`, `campaign_minutes_needed`, `drop_earnable_now`) is in
`src/dropwatch/models.py` under the same rule. `Runner._plan` gathers the inputs and acts on the result.
`_hold_current` keeps a non-priority campaign unless a challenger has 20% less spare time (`HYSTERESIS =
0.8`).

## Consequences

- Every rule is testable with a pinned `now` and no fakes (`tests/test_planner.py`).
- Re-planning is cheap, so the API re-plans at once after a list or setting change (`replan`) without
  calling Twitch.
- Anything that depends on history (link probing, channel exclusions, watch-streak visits) has to live in
  the runner and be passed in or applied after.

## Evidence

`src/dropwatch/planner.py`, `src/dropwatch/models.py`, `Runner._plan` in `src/dropwatch/runner.py`,
`tests/test_planner.py`.

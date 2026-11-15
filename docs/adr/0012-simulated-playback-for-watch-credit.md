# ADR-0012: Earn watch time by simulating HLS playback, with no video downloaded

**Status:** Accepted (recorded retroactively, 2026-11-15)

## Context

The first live run (2026-10-09, `docs/development.md`) showed the minute-watched heartbeat alone answered
204 but earned nothing. Upstream DevilXD#1183 reported that Twitch now credits minutes only while the
account appears to play the stream. JourneyDocker's fork (MIT) had a playback simulation.

## Decision

`Watcher.send` (`src/dropwatch/twitch/watch.py`), every 10 s: get a playback token, read the master
playlist, take the lowest-quality media playlist, and send a `HEAD` for each segment not seen yet, with
per-step time limits. While playback works it posts the spade `minute-watched` event at most once per 59
s, with `"player": "site"` (without it no channel points were credited, 2026-10-11). An ended playlist
(`#EXT-X-ENDLIST`) counts as not watching. Twitch counts two streams at once, so the Channel points list
gets two more `Watcher`s (`POINTS_SLOTS`), one fewer while a drop channel is watched.

## Consequences

- Minutes are credited 1:1 with no video bandwidth (run 3 on 2026-10-09: 22 to 138 minutes in two hours).
- About one playlist GET and a few HEADs per watched stream every 10 s.
- **Twitch can change the rule again,** and mining stops earning until the code is updated; the "isn't
  earning" notification is the early warning.

## Evidence

`src/dropwatch/twitch/watch.py`, `src/dropwatch/runner.py` (`tick`, `_tick_points`, `POINTS_SLOTS`),
`src/dropwatch/service.py` (`build_parts`), `reference/journeydocker/`; commits `327fc68`, `2294067`,
`aef8802`.

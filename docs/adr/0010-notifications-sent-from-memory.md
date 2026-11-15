# ADR-0010: Decide notifications in memory and send them straight away, to seven push services

**Status:** Accepted (recorded retroactively, 2026-11-15)

## Context

The owner is rarely looking at the page. They need to hear when mining stops, isn't earning, can't reach
Twitch, a claim fails, or the sign-in ends, once when it starts and once when it clears. The seven
services and their request shapes were taken from another of the owner's tools ("Clawdmeter",
`notify.py` docstring).

## Decision

`Notifier` (`src/dropwatch/alerts.py`) listens to the bus and runs time-based checks every 30 s. It keeps
what it has said in memory (`_sent`) and only sends a recovery after an alert that went out.
`send_all` (`src/dropwatch/notify.py`) sends one HTTPS POST per configured channel with a 10 s budget.
Channels are one JSON setting, `notify_channels`; the API never returns a secret field's value. Failures
are reported by service name and HTTP status or exception type only. The weekly summary records the week
it was delivered (`notify_weekly_sent`) and retries every 10 minutes for up to 6 hours; "a campaign needs
you" records what it has reported (`notify_needs_you_sent`).

## Consequences

- No queue to run; a broken channel never stops the others or the miner.
- **An alert decided just before a restart is lost, and a restart forgets which alerts were out,** so the
  matching "is working again" is not sent.
- Secrets are plain text in `drops.db` (mode `0600`) and in a backup made with secrets.

## Evidence

`src/dropwatch/alerts.py`, `src/dropwatch/notify.py`, `src/dropwatch/store.py` (`get_channels`,
`put_channel`), `src/dropwatch/backup.py`.

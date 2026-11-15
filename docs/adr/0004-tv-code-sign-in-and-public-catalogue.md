# ADR-0004: Sign in with Twitch's TV device code, and discover campaigns from a public catalogue

**Status:** Accepted (recorded retroactively, 2026-11-15)

## Context

Around 2026-09-18 Twitch stopped the Android app's device-code login (upstream DevilXD#1165). The original
spec (§4) records the spikes of 2026-10-09 and 2026-10-10: the TV client's device-code login (`SMARTBOX`)
works, never expires, earns watch minutes and can claim, but `ViewerDropsDashboard` returns no campaigns
for it. A registered "Login with Twitch" app is refused by the drops GQL. The phase-1 browser sign-in with
Android delegation works but needs a browser, which the image would have to carry.

## Decision

- **Sign-in** is `DeviceCodeSignIn` (`src/dropwatch/twitch/auth_device.py`): the page shows an 8-letter
  code for `twitch.tv/activate`, the server polls at Twitch's interval, and `validate_token` accepts the
  token only if it belongs to the TV client.
- **Every Twitch call goes as the session's own client** (`client_for` in `twitch/constants.py`), because
  a token sent under another client id earns no watch time.
- **Discovery:** when the dashboard returns nothing, `TwitchClient.campaigns` takes the campaign list
  from `Catalog` (`twitch/catalog.py`), a public catalogue of Twitch's own records run by an anonymous
  third party, and merges the account's Inventory over it so the account's own state wins.
- The catalogue gets a plain `GET`, hourly, from its own transport with no Twitch headers or cookies
  (`build_parts` in `service.py`). The last good copy is kept in `/data/catalog.json`. Older than 6 hours
  is "stale"; down is "unreachable"; both show on Overview.
- Campaigns whose link Twitch has not reported are `linked = None`, ranked after known-linked ones outside
  Priority, and tested: 10 minutes of good playback with no minutes marks one "may need linking".
- The browser sign-in stays as a PC-only fallback (`dropwatch signin --browser`, the optional `browser`
  extra). The image does not include it.

## Consequences

- Sign-in works from any device and needs nothing in the container but HTTP.
- **A third party is a runtime dependency.** While the catalogue is down, campaigns already in Inventory
  keep mining and claiming; new ones are not found. Its records are trusted for names, times, games and
  allowed channels.
- An Android session (from the browser fallback) still lists campaigns itself, and then the catalogue is
  never asked (`Catalog.used` stays false).

## Evidence

`src/dropwatch/twitch/auth_device.py`, `auth_browser.py` (`validate_token`), `constants.py`
(`SMARTBOX`, `client_for`), `catalog.py`, `client.py` (`campaigns`), `service.py` (`build_parts`),
`runner.py` (`_probe_link`); commits `8225713`, `bcbfefe`, `d0e3697`, `7d6d19e`.

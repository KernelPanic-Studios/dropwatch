# Configuration

Almost everything is set in the page and saved in the database. Environment variables are only for facts
about the deployment: where the data is, which names to answer to, which proxy to trust. Read against
`main` at `687d794` (2026-11-15).

## The Settings screen

**Settings** has seven sections. Each shows a one-line summary when closed, and the open one is kept in
the address (`#settings/backup`), so a reload returns to it.

| Section | What it is for |
|---|---|
| **Mining** | **Only mine games in Priority** (`priority_only`), **Also mine badge and emote campaigns** (`mine_badges`), and **Check Twitch for campaign changes** every 15, 30, 60, 120 or 240 minutes (`campaigns_every_minutes`). |
| **Channel points** | **Also claim channel points** (`claim_points`: open bonus chests on watched channels and those watched in the last week) and **Collect watch-streak bonuses on favourite channels** (`points_watch_streak`). |
| **Notifications** | Which alerts are on, their wait times, the weekly summary's day, hour and zone, "a reward is claimed", the services they go to, and **Send test notification**. See [notifications.md](notifications.md). |
| **Account & security** | The Twitch account (sign out, or get a sign-in code), the signed-in browsers, and **Sign out of this page**. |
| **Appearance** | System, light or dark theme. Kept in this browser only (`localStorage`), not on the server. |
| **Backup** | **Save a backup** (optionally with notification secrets) and **Restore from a backup**. See [storage-and-backups.md](storage-and-backups.md). |
| **Proxy** | Read-only. Whether this visit came through a reverse proxy and whether Dropwatch trusts it (with the `FORWARDED_ALLOW_IPS` value to set when it doesn't), the current `DROPWATCH_HOSTS` and `FORWARDED_ALLOW_IPS`, and example configs for nginx/SWAG, Nginx Proxy Manager, Caddy and Traefik filled in with this server's name, folder and address. See [reverse-proxy.md](reverse-proxy.md). |
| **About** | Version, build (branch and commit), when Dropwatch started, when campaigns were last read, and the server's time zone. |

Two settings live on other screens: **Arrange myself** on Overview's Up next (`arrange_up_next`: your pins
count only while it is on), and the switch on the **Channel points** tab (`points_watch`: watch the list's
streamers while they are live).

Settings that change what is mined take effect at once, without waiting for the next 5-minute check:
`arrange_up_next`, `mine_badges`, `claim_points`, `points_watch_streak`, `priority_only` and `points_watch`
(`PLANNER_SETTINGS` in `src/dropwatch/api/app.py`).

## Settings saved in the app

Every setting, its type, its default on a new install, and the values the API accepts. A value outside
them is refused with 422; a misspelt key is refused too. This table is generated from `SETTINGS` and
`SETTING_DEFAULTS` in `src/dropwatch/store.py` and `SettingsIn` in `src/dropwatch/api/models.py`.

<!-- generated:settings -->
| Key | Type | Default | Allowed |
|---|---|---|---|
| `mine_badges` | bool | `false` | true, false |
| `claim_points` | bool | `true` | true, false |
| `notify_signin` | bool | `true` | true, false |
| `notify_unreachable` | bool | `true` | true, false |
| `notify_not_earning` | bool | `true` | true, false |
| `notify_claim_failed` | bool | `true` | true, false |
| `notify_stopped` | bool | `true` | true, false |
| `notify_needs_you` | bool | `false` | true, false |
| `notify_unreachable_minutes` | int | `15` | 5 to 240 |
| `notify_not_earning_minutes` | int | `30` | 10 to 240 |
| `arrange_up_next` | bool | `false` | true, false |
| `notify_claimed` | bool | `false` | true, false |
| `notify_weekly` | bool | `false` | true, false |
| `notify_weekly_day` | int | `6` | 0 to 6 |
| `notify_weekly_hour` | int | `18` | 0 to 23 |
| `notify_weekly_tz` | str | `""` | an IANA zone name, or "" for the server's zone |
| `campaigns_every_minutes` | int | `60` | 15, 30, 60, 120, 240 |
| `points_watch_streak` | bool | `true` | true, false |
| `priority_only` | bool | `false` | true, false |
| `points_watch` | bool | `true` | true, false |
<!-- /generated:settings -->

`notify_weekly_day` counts from 0 for Monday, so the default 6 is Sunday; the default hour is 18:00.

Settings are part of a backup. Precedence is simple: there is no environment variable for any of them, so
what is saved in the app is what applies.

## Environment variables

Every variable the code or the image reads (`grep -rhoE "os\.environ(\.get)?\(?\[?['\"][A-Z0-9_]+" src`,
plus `docker/entrypoint.sh`, the `Dockerfile` and uvicorn's own).

### Deployment

| Variable | Required | Default | Notes |
|---|---|---|---|
| `TZ` | No | `UTC` in the image | The server's zone: log times, and the weekly summary's zone when the setting is empty. Read by `server_tz` in `src/dropwatch/version.py`. |
| `PUID` | No | `99` | User the miner runs as. `docker/entrypoint.sh` chowns `/data` to it, then drops root with `setpriv`. |
| `PGID` | No | `100` | Group the miner runs as. |
| `DROPWATCH_HOSTS` | Only behind a public name | empty | Comma-separated names to answer to besides IP addresses and local names, for example `dropwatch.example.com`. `*` turns the Host check off. Read in `serve` (`src/dropwatch/cli.py`). |
| `FORWARDED_ALLOW_IPS` | Only behind a reverse proxy | `127.0.0.1,::1` (uvicorn's default) | The proxy's address, so the login lockout sees each visitor. Read by uvicorn, which trusts `X-Forwarded-For` and `X-Forwarded-Proto` only from these addresses. |

### Set by the image (leave them alone)

| Variable | Value in the image | Notes |
|---|---|---|
| `DROPWATCH_DATA` | `/data` | Where `drops.db`, `catalog.json` and `images/` live. On a PC the default is `./data`. |
| `DROPWATCH_WEB` | `/app/web/dist` | The built page. On a PC the default is the repository's `web/dist`. |
| `DROPWATCH_COMMIT` | `<branch or tag>@<sha>`, from the build argument | The build shown in **About**, used for the copy before upgrades and the "Dropwatch was updated" notice. The build fails without it. On a PC `git` is asked instead. |
| `DROPWATCH_EXIT_WHEN_STUCK` | `1` | Turns on the watchdog that exits a stuck miner so Docker restarts it. Any other value, or unset, turns it off. |
| `PYTHONUNBUFFERED`, `UV_*`, `PATH` | set | Python and uv settings for the image. |

### PC only

| Variable | Default | Notes |
|---|---|---|
| `DROPWATCH_BROWSER` | Chrome or Edge in their usual Windows folders | The browser for `dropwatch signin --browser`. |

## Command line

`dropwatch serve [--host 127.0.0.1] [--port 5810]` is what the image runs (with `--host 0.0.0.0 --port
5800`). The other commands are for a PC: `signin [--browser]`, `run` (mining with no page), `lists
[--priority A,B] [--never C] [--favourites x,y] [--show]`, `capture [--out tests/fixtures]` (records
scrubbed Twitch responses for tests) and `openapi [--out docs/api/openapi.json]`.

## Known limitations

- Settings have no per-browser or per-user values; every signed-in browser sees and changes the same
  ones (the theme is the exception).
- `campaigns_every_minutes` accepts only the five values the page offers.

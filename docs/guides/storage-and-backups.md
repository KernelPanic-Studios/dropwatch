# Storage and backups

Everything Dropwatch keeps is in the data folder: `/data` in the container, mapped to
`/mnt/user/appdata/dropwatch` by the Unraid template.

## What is where

| File | What it holds | Notes |
|---|---|---|
| `drops.db` | The Twitch session, the page password hash, signed-in browsers, Priority, Never, favourites, the Channel points list, pins, settings, notification services, History (claims, campaigns, channel points), the last week of Activity | SQLite, created readable by the miner's user only (`0600`). Holds the Twitch token and notification secrets in plain text. |
| `drops.db.before-<version>+<build>` | A copy of `drops.db` made before a new build first opened it | The newest two are kept. Same permissions and secrets as `drops.db`. |
| `catalog.json` | The last good copy of the public campaign catalogue | Lets a restart while the catalogue is down still know the campaigns. Safe to delete. |
| `images/` | Kept copies of the box art and reward images History shows | Twitch's links can stop working after a campaign ends. Safe to delete; they are fetched again within 10 minutes. |

What is kept, and for how long:

| Data | Kept |
|---|---|
| Activity events | 7 days |
| Claims | No limit |
| Campaign records (History's Missed) and channel points | 400 days |
| Channels seen live (add-box suggestions) | 30 days |
| Signed-in browsers | 30 days from sign-in |

## Backing up

Two ways, for two purposes:

- **The whole install:** back up the data folder with the rest of appdata (Unraid's appdata backup, or a
  copy while the container is stopped). This carries everything, including the Twitch sign-in and History.
  Treat it as a secret.
- **Your choices:** **Settings › Backup › Save a backup** downloads `dropwatch-backup-YYYY-MM-DD.json` with
  your lists, pins, Channel points list, settings and notification services. Tick the option to include
  notification secrets if the file should restore them too.

A backup file does **not** carry the Twitch sign-in, the page password, signed-in browsers, History,
Activity or the Needs you ignore list. Those belong to the install.

## Restoring

**Settings › Backup › Restore from a backup**, pick the file, confirm. Dropwatch checks the whole file
first and changes nothing if any part is unusable:

| Message | Meaning |
|---|---|
| That file isn't a Dropwatch backup. | It is not JSON |
| That isn't a Dropwatch backup, or it's from a newer version. | The format number is not 1 |
| The backup has a value Dropwatch can't use: ... | A setting or list entry is out of range |
| In both Priority and Never: ... | The lists clash |

A restore replaces the lists, pins, settings and services. A Channel points list is replaced only if the
backup has one (backups from before 0.3.0 do not). A secret left out of the backup keeps the value
already set on this install. Anything a newer version wrote that this one does not know is skipped and
listed.

## Moving to another server

Stop the container, copy the data folder, start the new container on the copy. Do not run both: two miners
on one account fight over progress.

## Variables

| Variable | Default | Notes |
|---|---|---|
| `DROPWATCH_DATA` | `/data` in the image, `./data` on a PC | The data folder |
| `PUID` / `PGID` | `99` / `100` | The folder is chowned to them on every start |

## Known limitations

- Secrets are not encrypted at rest; the file permissions are the protection.
- No scheduled backup inside Dropwatch.
- Only one container may use a data folder at a time.

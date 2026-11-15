# How mining works

What Dropwatch mines, in what order, and on which channel. The rules are in `plan()` in
`src/dropwatch/planner.py`; this page says them in the page's words.

## What gets mined first

Every active campaign with something left to earn is a candidate, unless its game is on **Never**. They
are mined in this order:

1. **Priority** games, in your order (Priorities tab). Priority is an order, not a whitelist.
2. **Pinned** campaigns, in your order, while **Up next › Arrange myself** is on.
3. Everything else, **most urgent first**: the least spare time (time left before the drop ends divided by
   the minutes still needed). Outside Priority, campaigns whose game account is known to be linked come
   before ones whose link Twitch has not reported yet, so testing an unknown link only uses time that
   would otherwise be idle.

Dropwatch keeps mining the current campaign unless another one is clearly more urgent (20% less spare
time), so it does not flip between two close ones. Priority and pins always win at once.

**Only mine games in Priority** (Settings › Mining) mines nothing outside Priority. The rest show as
outside on Overview and are not asked about in Needs you.

Badge and emote campaigns need no game account but are off unless **Also mine badge and emote campaigns**
is on.

## Which channel

A campaign can only be mined on a live channel streaming its game with drops on (and on its allowed
channels, if it has a list). Among those: your **favourites** first, in your order, then the campaign's
allowed channels, then any channel, most viewers first. Dropwatch stays on the channel it is watching
unless a favourite is better.

A channel is set aside for 10 minutes when its stream ends or its playback fails for about 90 seconds.
Twitch's directory keeps listing a stream for a few minutes after it ends; the 10 minutes cover that.

You can override both from Overview: **Mine now** on an Up next campaign, or pick another of the listed
channels. An override lasts while the plan can still honour it.

## Needs you

A campaign lands in **Needs you** when its game account is not linked:

- Twitch says it is not linked: **Link account** opens the game's link page. Once Twitch reports the link
  (at the next campaign check), it is mined in its turn.
- Twitch has not said (campaigns not started yet), and 10 minutes of good watching earned nothing: it is
  marked **may need linking** for up to 6 hours. Link it, then press **Mine now** to say you did.

**Ignore** hides one from Needs you, its alert and the weekly summary until the campaign ends; **Undo**
brings it back.

## Claiming

Rewards are claimed as soon as Twitch issues a claim, usually announced over Twitch's live connection. If
that message never comes, Dropwatch re-reads campaigns at every 5-minute check for up to an hour. A
campaign can still be claimed for 24 hours after it ends. A claim on a campaign Twitch says is unlinked is
not attempted (Twitch accepts it and awards nothing).

## Channel points

- **Also claim channel points** opens bonus chests on the channel being watched, on your Channel points
  list, and on channels watched in the last week (up to 30 of them).
- **Collect watch-streak bonuses on favourite channels**: when a favourite starts a new stream, Dropwatch
  watches it for 7 minutes first, once per stream. Overview shows it; **Back to drops now** ends it.
- The **Channel points** tab lists streamers to watch whenever they are live, drops or not. Twitch counts
  two streams at once: one goes to drops while there is a campaign to mine, the rest to your list, top
  first. One already being watched for drops shows as waiting: drops; the rest show waiting: full.

## Timings

| What | How often | Where |
|---|---|---|
| Playback of each watched stream | every 10 s | `PLAY_INTERVAL`, `twitch/constants.py` |
| Minute-watched event | at most every 59 s per stream | `WATCH_INTERVAL` |
| Live channels | every 5 minutes | `REFRESH_EVERY`, `runner.py` |
| Campaigns and links | every 60 minutes by default (Settings › Mining) | `campaigns_every_minutes` |
| Catalogue | hourly; retried after 5 minutes when down | `twitch/catalog.py` |
| Back-off while Twitch fails | 60 s, doubling to 10 minutes | `BACKOFF_START`, `BACKOFF_MAX` |

## Known limitations

- One drop campaign at a time; other campaigns of the same game on the same channel are credited
  alongside and shown as such.
- Twitch's terms of service do not allow automated watching. Use it on your own account at your own risk.

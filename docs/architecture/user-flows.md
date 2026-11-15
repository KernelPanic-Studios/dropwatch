# User flows

Read against `main` at `687d794` (2026-11-15).

The journeys most people take, with the decision points and the success and error paths the code
actually has. Error texts and status codes are copied from the code so they can be searched for. Screen
and button names are the page's own.

## 1. First visit: protect the page

```mermaid
flowchart TD
  a["Open http://server:5800"] --> h{"Host allowed?<br/>HostCheck"}
  h -- "no" --> h400["400 text/plain: Dropwatch doesn't answer to the name ... unless it's listed"]
  h -- "yes" --> me["GET /api/me"]
  me --> setup{"setup_required?"}
  setup -- "yes" --> s1["Protect this page<br/>SetupScreen"]
  s1 --> chk{"8+ characters and both entries match?<br/>checked in the page"}
  chk -- "no" --> s1
  chk -- "yes" --> post["POST /api/setup"]
  post --> r{"answer"}
  r -- "409 A page password is already set." --> err["message on the form"]
  r -- "422 Use at least 8 characters." --> err
  r -- "204 + dm_session cookie" --> conn["#connect: Connect your Twitch account<br/>step 2 of 2"]
  setup -- "no" --> auth{"authenticated?"}
  auth -- "yes" --> tabs["Overview"]
  auth -- "no" --> login["Enter the page password<br/>see flow 2"]
```

Divergence check: `SetupScreen` in `web/src/screens/PagePassword.tsx`, `setup` in
`src/dropwatch/api/auth.py`. `MIN_PASSWORD = 8` and `SESSION_TTL = 30 days` in `src/dropwatch/store.py`.
Setup is open to anyone who reaches the page until a password is set; `HostCheck` keeps a DNS-rebinding web
page from reaching it.

## 2. Later visits: sign in to the page

```mermaid
flowchart TD
  a["Enter the page password"] --> post["POST /api/login"]
  post --> lock{"5 wrong from this address<br/>in 15 min?"}
  lock -- "yes" --> r429["429 Too many wrong passwords. Try again in N min.<br/>Retry-After header"]
  lock -- "no" --> v{"argon2 verify<br/>in a worker thread"}
  v -- "wrong" --> r401["0.5 s pause, then 401 Wrong password."]
  v -- "right" --> ok["204 + dm_session cookie"]
  r401 --> msg1["That isn't the page password. Check it and try again."]
  r429 --> msg2["Couldn't reach the miner. Try again.<br/>(see finding F2)"]
  ok --> tabs["Overview"]
```

Divergence check: `login` and `LoginLimiter` in `src/dropwatch/api/auth.py` (`LOGIN_TRIES = 5`,
`LOGIN_WINDOW = 15 minutes`); `LoginScreen` in `web/src/screens/PagePassword.tsx`, which shows the
"Couldn't reach the miner" text for every status but 401, including the 429 lockout. The limiter counts
by `request.client.host`, which behind a reverse proxy is the proxy unless `FORWARDED_ALLOW_IPS` is set.

## 3. Connect a Twitch account

```mermaid
flowchart TD
  a["Get a sign-in code"] --> post["POST /api/twitch/signin"]
  post --> busy{"a sign-in already waiting?"}
  busy -- "yes" --> r409["409 A sign-in is already waiting for its code.<br/>the page re-reads the status"]
  busy -- "no" --> start{"Twitch gives a code?"}
  start -- "no" --> failed["status failed: Twitch wouldn't start a sign-in (...)"]
  start -- "yes" --> wait["status waiting: 8-letter code, twitch.tv/activate link, QR code, time left<br/>page polls GET /api/twitch/signin every 3 s"]
  wait --> user{"owner enters the code<br/>and clicks Authorize?"}
  user -- "Cancel" --> idle["DELETE /api/twitch/signin: status idle"]
  user -- "code runs out" --> expired["status expired: That code expired. Get a new one."]
  user -- "Authorize" --> val{"token belongs to the TV client?"}
  val -- "no" --> failed2["status failed: Twitch issued a token for ..., not the TV app. It was not saved."]
  val -- "yes" --> done["session saved, miner restarted<br/>status done: Signed in as login."]
  done --> ov["Connected. Mining starts now.<br/>Overview"]
```

Divergence check: `ConnectScreen` in `web/src/screens/Connect.tsx` (`pollMs = 3000`), `SignInManager` in
`src/dropwatch/api/signin.py`, `DeviceCodeSignIn` and `validate_token` in `src/dropwatch/twitch/`. The code
lives as long as Twitch's `expires_in` (1,800 s when Twitch omits it).

## 4. The Overview screen

```mermaid
flowchart TD
  st["GET /api/state"] --> s{"state"}
  s -- "signed_out" --> so["Banner: Twitch signed you out<br/>Get a sign-in code → #connect"]
  s -- "twitch_unreachable" --> tu["Banner: Can't reach Twitch<br/>chip: Retrying Twitch · progress kept"]
  s -- "paused" --> pa["Banner: Paused until ..., Resume now<br/>POST /api/resume"]
  s -- "idle" --> id{"anything waiting for a live channel?"}
  id -- "yes" --> fl["Idle card naming first_in_line, Check now<br/>POST /api/refresh"]
  id -- "no" --> no["Idle: nothing to mine"]
  s -- "mining or switched" --> m["Now mining: campaign, reward track, channel, reason"]
  m --> streak{"streak_visit?"}
  streak -- "yes" --> sv["Watching a favourite for its streak<br/>Back to drops now: POST /api/streak/end"]
  m --> cat{"catalog status stale or unreachable?"}
  cat -- "yes" --> cb["Banner: Can't reach the campaign list since ...<br/>or The campaign list hasn't updated since ..."]
  m --> lists["Needs you, Up next, Done, Never sections"]
```

Divergence check: `OverviewView` in `web/src/views/Overview.tsx`, `state_view` in
`src/dropwatch/api/views.py`, `State` in `src/dropwatch/runner.py`. The top bar pill comes from `pillFor`
in `web/src/App.tsx`; when the event stream has been broken for 15 s it says "Miner unreachable" whatever
the last state was.

## 5. Steer the miner: Mine now, switch channel, pause

```mermaid
flowchart TD
  a["Mine now on an Up next campaign"] --> mn["POST /api/mine-now {campaign_id}"]
  mn --> signed{"miner running and signed in?"}
  signed -- "no" --> e409a["409 Not signed in to Twitch."]
  signed -- "yes" --> known{"campaign known?"}
  known -- "no" --> e404["404 No such campaign."]
  known -- "yes" --> po{"Priority only on and the game not in Priority?"}
  po -- "yes" --> e409b["409 Priority only is on: add game to Priority to mine it."]
  po -- "no" --> rp["replan"] --> took{"plan picked it?"}
  took -- "no" --> e409c["409 Can't mine that campaign right now: it needs a linked account, a live channel, or it's on your Never list."]
  took -- "yes" --> ok["204, the page re-reads state"]
  b["Pick another channel"] --> ch["POST /api/channel {login}"]
  ch --> live{"live with drops?"}
  live -- "no" --> e404b["404 That channel isn't live with drops right now."]
  live -- "yes" --> earn{"can it earn the current campaign?"}
  earn -- "no" --> e409d["409 That channel can't earn the campaign being mined."]
  earn -- "yes" --> ok2["204"]
  c["Pause for N minutes or until resumed"] --> pz["POST /api/pause {minutes}"]
  pz --> ok3["204, state paused; points streams stop too"]
```

Divergence check: `mine_now`, `channel`, `pause` and `_runner` in `src/dropwatch/api/app.py`; overrides last
only while the plan still honours them (`Runner._plan`). A paused miner resumes by itself at `paused_until`
(`Runner.tick`).

## 6. Needs you: link an account, or ignore it

```mermaid
flowchart TD
  a["Campaign in Needs you"] --> why{"why"}
  why -- "Twitch says not linked" --> l1["Link account opens the campaign's link URL"]
  why -- "may need linking<br/>(unknown link, 10 min with no minutes)" --> l2["Link account, then Mine now = I linked it"]
  l1 --> next{"next campaign read<br/>says linked?"}
  next -- "yes" --> leave["leaves Needs you; mined in its turn"]
  next -- "no" --> a
  l2 --> mn["POST /api/mine-now clears the mark"]
  a --> ig["Ignore: POST /api/needs/ignored/id"]
  ig --> hid["moved out of Needs you, its alert and the weekly summary until the campaign ends<br/>Undo: DELETE /api/needs/ignored/id"]
```

Divergence check: `plan()` in `src/dropwatch/planner.py` (`needs_you`, `needs_ignored`), `_probe_link`
and `_settle_link_marks` in `src/dropwatch/runner.py` (`LINK_PROBE_TICKS = 60`, `MAYBE_UNLINKED_FOR = 6
hours`), `ignore_needs` in `src/dropwatch/api/app.py` (keeps the newest 200 ids). Campaign reads follow
`campaigns_every_minutes`, or every 10 minutes while a link is being tested (`LINK_RECHECK`).

## 7. Change Priorities, Never and favourites

```mermaid
flowchart TD
  a["Priorities tab: add, drag, remove"] --> put["PUT /api/lists {priority, never, favourites}"]
  put --> v{"valid?"}
  v -- "unknown field, more than 200 entries, or a name over 200 characters" --> e422["422"]
  v -- "a game in both Priority and Never" --> e422b["422 In both Priority and Never: names"]
  v -- "yes" --> save["saved, replan at once (no Twitch calls)"]
  b["Add a channel by name"] --> lk["GET /api/channels/lookup?login=..."]
  lk --> f{"Twitch reachable?"}
  f -- "no" --> e502["502 Couldn't reach Twitch to check that name."]
  f -- "yes" --> found["found, live, game; or found: false"]
```

Divergence check: `put_lists` and `lookup_channel` in `src/dropwatch/api/app.py`, `ListsIn` in
`src/dropwatch/api/models.py`, `PrioritiesView` in `web/src/views/Priorities.tsx`. Add boxes suggest
nothing until 3 letters are typed (commit `22bae17`).

## 8. Channel points list

```mermaid
flowchart TD
  a["Channel points tab: add a streamer"] --> put["PUT /api/points/channels {channels}"]
  put --> new{"anyone added?"}
  new -- "yes" --> rf["refresh: look up who is live now"]
  new -- "no, only reordered or removed" --> rp["replan"]
  rf --> slots{"free slot?<br/>2, minus 1 while a drop channel is watched"}
  rp --> slots
  slots -- "yes" --> watch["watched for points; shows Watching since"]
  slots -- "no" --> wait["shows waiting: drops (already the drop channel) or full"]
  sw["Points watching switch off"] --> off["PUT /api/settings {points_watch: false}: list kept, nobody watched"]
```

Divergence check: `put_points_channels` and `_points_page` in `src/dropwatch/api/app.py`,
`_choose_points` in `src/dropwatch/runner.py` (`POINTS_SLOTS = 2`).

## 9. Back up and restore settings

```mermaid
flowchart TD
  a["Settings › Backup › Save a backup"] --> sec{"include secrets?"}
  sec -- "no" --> g1["GET /api/backup"]
  sec -- "yes" --> g2["GET /api/backup?secrets=true"]
  g1 --> file["dropwatch-backup-YYYY-MM-DD.json"]
  g2 --> file
  r["Restore from a backup: pick a file, confirm"] --> parse{"the file parses as JSON in the browser?"}
  parse -- "no" --> bad["That file isn't a Dropwatch backup."]
  parse -- "yes" --> post["POST /api/restore (application/json)"]
  post --> chk{"whole file valid?"}
  chk -- "not format 1" --> e1["422 That isn't a Dropwatch backup, or it's from a newer version."]
  chk -- "bad value" --> e2["422 The backup has a value Dropwatch can't use: ..."]
  chk -- "clash" --> e3["422 In both Priority and Never: ..."]
  chk -- "yes" --> done["lists, pins, points list, settings and channels replaced<br/>skipped: what a newer version wrote"]
```

Divergence check: `make_backup` and `restore_backup` in `src/dropwatch/backup.py`, `post_restore` in
`src/dropwatch/api/app.py`, the Backup section of `web/src/views/Settings.tsx`.

## 10. Twitch session ends

```mermaid
flowchart TD
  a["GQL answers 401"] --> so["Runner: state signed_out"]
  so --> clear["MinerService: session row deleted"]
  clear --> ev["bus: signin expired, Twitch session expired. Sign in again."]
  ev --> al{"notify_signin on?"}
  al -- "yes" --> push["Dropwatch: Twitch sign-in stopped working"]
  ev --> page["Overview banner, Get a sign-in code → #connect: Sign in to Twitch again"]
  page --> flow3["flow 3"]
  b["Settings › Account & security › Twitch: Sign out, confirm"] --> po["POST /api/twitch/signout: miner stopped, session deleted"]
```

Divergence check: `MinerService._loop` in `src/dropwatch/service.py`, `signout` in
`src/dropwatch/api/app.py`, `Notifier.handle` in `src/dropwatch/alerts.py`. Drop progress is kept by Twitch,
not by Dropwatch, so it carries on after the next sign-in.

## 11. Updating

```mermaid
flowchart TD
  a["New image pulled, container recreated"] --> b["entrypoint: chown /data, setpriv"]
  b --> c{"build string differs from settings.last_build<br/>and the database has data?"}
  c -- "yes" --> cp["copy drops.db to drops.db.before-version+build<br/>keep the newest 2"]
  c -- "no" --> st["Store opens, adds missing columns"]
  cp --> st
  cp -. "copy fails" .-> warn["warning logged, start anyway"]
  st --> run["mining resumes on the saved session"]
  run --> tab{"a tab still open from before?"}
  tab -- "yes" --> note["Dropwatch was updated: Reload<br/>(build in /api/state changed)"]
```

Divergence check: `backup_on_upgrade` and `safe_backup_on_upgrade` in `src/dropwatch/maintenance.py`
(`BACKUP_KEEP = 2`), `UpdateNotice` in `web/src/App.tsx`, the `build` field set in `get_state`
(`src/dropwatch/api/app.py`). Rolling back is by hand: see [updating.md](../guides/updating.md).

"""SQLite persistence (spec §7, phase-1 subset: session, lists, settings, events).

Synchronous sqlite3. Every call is a few milliseconds, so the runner calls it directly.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from .models import Prefs
from .twitch.session import TwitchSession

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS session (
  id INTEGER PRIMARY KEY CHECK (id = 1), access_token TEXT NOT NULL, user_id INTEGER NOT NULL,
  login TEXT NOT NULL, device_id TEXT NOT NULL, client_id TEXT NOT NULL, session_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS priority (position INTEGER PRIMARY KEY, game_name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS never (game_name TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS favourites (position INTEGER PRIMARY KEY, channel_login TEXT NOT NULL UNIQUE);
-- Channel points (2026-11-08): streamers watched whenever they're live, for their points, apart from drops
CREATE TABLE IF NOT EXISTS points_channels (position INTEGER PRIMARY KEY, channel_login TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS events (at TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS claims (at TEXT NOT NULL, campaign_id TEXT NOT NULL, campaign TEXT NOT NULL,
  game TEXT NOT NULL, rewards TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS web_sessions (token_hash TEXT PRIMARY KEY, expires_at TEXT NOT NULL);
-- channel points gained (2026-10-11), from PubSub points-earned: History and the weekly summary add them up
CREATE TABLE IF NOT EXISTS points_log (at TEXT NOT NULL, channel TEXT, reason TEXT NOT NULL,
  points INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS seen_channels (login TEXT PRIMARY KEY, game TEXT NOT NULL,
  last_seen TEXT NOT NULL);
-- History "Missed" (2026-10-10): the last thing Dropwatch knew about each campaign, kept after it ends
CREATE TABLE IF NOT EXISTS campaign_log (id TEXT PRIMARY KEY, name TEXT NOT NULL, game TEXT NOT NULL,
  box_art_url TEXT NOT NULL, link_url TEXT NOT NULL, ends_at TEXT NOT NULL, rewards TEXT NOT NULL,
  first_seen TEXT NOT NULL, impossible_at_first INTEGER NOT NULL, last_seen TEXT NOT NULL,
  linked INTEGER, badge INTEGER NOT NULL, never INTEGER NOT NULL, priority INTEGER NOT NULL,
  pinned INTEGER NOT NULL, live INTEGER NOT NULL, watched INTEGER NOT NULL,
  outside INTEGER NOT NULL DEFAULT 0);
"""
CAMPAIGN_LOG_KEEP = timedelta(days=400)  # History's longest period is a year
MISSED_OFF_AFTER = timedelta(hours=1)  # no look in the last hour before it ended: Dropwatch was off
CLAIM_DETAIL_COLUMNS = (("minutes", "INTEGER"), ("channel", "TEXT"), ("campaign_rewards", "INTEGER"),
                        ("campaign_ends", "TEXT"), ("box_art_url", "TEXT"))
EVENT_RETENTION = timedelta(days=7)
SESSION_TTL = timedelta(days=30)
SESSION_SEEN_EVERY = timedelta(minutes=5)  # how often a session's "last seen" is written
SESSION_ID_LEN = 16
SEEN_KEEP = timedelta(days=30)  # channels seen live, for the favourites add box
MIN_PASSWORD = 8
SETTINGS: dict[str, type] = {
    "mine_badges": bool, "claim_points": bool,
    # notifications (2026-10-10): failures on by default, "a campaign needs you" off; where they go is
    # the separate notify_channels JSON (get_channels)
    "notify_signin": bool, "notify_unreachable": bool, "notify_not_earning": bool,
    "notify_claim_failed": bool, "notify_stopped": bool, "notify_needs_you": bool,
    "notify_unreachable_minutes": int, "notify_not_earning_minutes": int,
    "arrange_up_next": bool,  # Up next "Arrange myself": pins count only while this is on
    # summaries (2026-10-10), off by default: a push per claim, and a weekly summary on a day (0 = Monday)
    "notify_claimed": bool, "notify_weekly": bool, "notify_weekly_day": int, "notify_weekly_hour": int,
    "notify_weekly_tz": str,  # an IANA zone name; "" = the server's zone (Docker: TZ, often UTC)
    "campaigns_every_minutes": int,  # how often the campaign list (and link status) is re-read from Twitch
    "points_watch_streak": bool,  # watch a favourite's new stream a few minutes first, for its watch streak
    "priority_only": bool,  # mine only games in Priority; everything else waits (2026-10-12)
    "points_watch": bool,  # watch the Channel points list's streamers while they're live (2026-11-08)
}
SETTING_DEFAULTS = {"mine_badges": False, "claim_points": True,
                    "notify_signin": True, "notify_unreachable": True, "notify_not_earning": True,
                    "notify_claim_failed": True, "notify_stopped": True, "notify_needs_you": False,
                    "notify_unreachable_minutes": 15, "notify_not_earning_minutes": 30,
                    "arrange_up_next": False, "notify_claimed": False, "notify_weekly": False,
                    "notify_weekly_day": 6, "notify_weekly_hour": 18, "notify_weekly_tz": "",
                    "campaigns_every_minutes": 60, "points_watch_streak": True, "priority_only": False,
                    "points_watch": True}
_ph = PasswordHasher()


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        self._db = sqlite3.connect(path)
        if new and os.name == "posix":
            os.chmod(path, 0o600)
        self._db.executescript(SCHEMA)
        # 2026-10-10: claim details for History; rows from before read back as NULL (not recorded)
        have = {row[1] for row in self._db.execute("PRAGMA table_info(claims)")}
        for col, kind in CLAIM_DETAIL_COLUMNS:
            if col not in have:
                self._db.execute(f"ALTER TABLE claims ADD COLUMN {col} {kind}")
        # 2026-10-11: Settings lists the signed-in browsers; older rows read back with no details
        have = {row[1] for row in self._db.execute("PRAGMA table_info(web_sessions)")}
        for col in ("created_at", "last_seen_at", "user_agent"):
            if col not in have:
                self._db.execute(f"ALTER TABLE web_sessions ADD COLUMN {col} TEXT")
        # 2026-10-12: Priority only kept it from being mined (History's reason); older rows read back as 0
        if "outside" not in {row[1] for row in self._db.execute("PRAGMA table_info(campaign_log)")}:
            self._db.execute("ALTER TABLE campaign_log ADD COLUMN outside INTEGER NOT NULL DEFAULT 0")
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    # --- session
    def get_session(self) -> TwitchSession | None:
        row = self._db.execute(
            "SELECT access_token, user_id, login, device_id, client_id, session_id FROM session"
        ).fetchone()
        return TwitchSession(*row) if row else None

    def set_session(self, s: TwitchSession) -> None:
        with self._db:
            self._db.execute("DELETE FROM session")
            self._db.execute(
                "INSERT INTO session VALUES (1, ?, ?, ?, ?, ?, ?)",
                (s.access_token, s.user_id, s.login, s.device_id, s.client_id, s.session_id),
            )

    def clear_session(self) -> None:
        with self._db:
            self._db.execute("DELETE FROM session")

    # --- lists and settings
    def get_prefs(self) -> Prefs:
        pr = tuple(r[0] for r in self._db.execute("SELECT game_name FROM priority ORDER BY position"))
        nv = frozenset(r[0] for r in self._db.execute("SELECT game_name FROM never"))
        fv = tuple(
            r[0] for r in self._db.execute("SELECT channel_login FROM favourites ORDER BY position")
        )
        s = self.get_settings()
        return Prefs(pr, nv, fv, s["mine_badges"], tuple(self.get_pins()) if s["arrange_up_next"] else (),
                     frozenset(self.get_ignored()), s["priority_only"],
                     self.get_points_channels() if s["points_watch"] else ())

    # --- Channel points list (ordered logins), kept while points watching is switched off
    def get_points_channels(self) -> tuple[str, ...]:
        return tuple(r[0] for r in self._db.execute(
            "SELECT channel_login FROM points_channels ORDER BY position"))

    def set_points_channels(self, logins: Sequence[str]) -> None:
        pc = list(dict.fromkeys(lg.strip().lower() for lg in logins if lg.strip()))
        with self._db:
            self._db.execute("DELETE FROM points_channels")
            self._db.executemany("INSERT INTO points_channels VALUES (?, ?)", enumerate(pc))

    # --- Up next pins (campaign ids, in order); kept while "Arrange myself" is off
    def get_pins(self) -> list[str]:
        return json.loads(self.get_setting("up_next_pins") or "[]")

    def set_pins(self, ids: Sequence[str]) -> None:
        self.set_setting("up_next_pins", json.dumps(list(dict.fromkeys(ids))))

    # --- Needs you > Ignore (campaign ids); each lasts until its campaign ends (Runner forgets it then)
    def get_ignored(self) -> list[str]:
        return json.loads(self.get_setting("needs_ignored") or "[]")

    def set_ignored(self, ids: Sequence[str]) -> None:
        self.set_setting("needs_ignored", json.dumps(list(dict.fromkeys(ids))))

    def set_lists(
        self, priority: Sequence[str], never: Iterable[str], favourites: Sequence[str]
    ) -> None:
        pr = list(dict.fromkeys(priority))
        fv = list(dict.fromkeys(f.strip().lower() for f in favourites if f.strip()))
        with self._db:
            self._db.execute("DELETE FROM priority")
            self._db.execute("DELETE FROM never")
            self._db.execute("DELETE FROM favourites")
            self._db.executemany("INSERT INTO priority VALUES (?, ?)", enumerate(pr))
            self._db.executemany("INSERT INTO never VALUES (?)", [(g,) for g in dict.fromkeys(never)])
            self._db.executemany("INSERT INTO favourites VALUES (?, ?)", enumerate(fv))

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # --- events
    def log_event(self, kind: str, data: dict) -> None:
        now = datetime.now(UTC)
        with self._db:
            self._db.execute(
                "INSERT INTO events VALUES (?, ?, ?)", (now.isoformat(), kind, json.dumps(data))
            )
            self._db.execute(
                "DELETE FROM events WHERE at < ?", ((now - EVENT_RETENTION).isoformat(),)
            )

    def switched_since(self, since: datetime) -> list[dict]:
        """Channel switches since then, newest first (the chest check's recently watched channels)."""
        rows = self._db.execute("SELECT data FROM events WHERE kind = 'switched' AND at >= ? "
                                "ORDER BY at DESC, rowid DESC", (since.astimezone(UTC).isoformat(),))
        return [json.loads(d) for (d,) in rows]

    def recent_events(self, limit: int | None = 100) -> list[tuple[str, str, dict]]:
        """(kind, at, data), newest first; limit None = everything kept (EVENT_RETENTION bounds it)."""
        rows = self._db.execute(
            "SELECT at, kind, data FROM events ORDER BY at DESC, rowid DESC LIMIT ?",
            (-1 if limit is None else limit,),
        )
        return [(kind, at, json.loads(data)) for at, kind, data in rows]

    # --- typed settings
    def get_settings(self) -> dict:
        out = dict(SETTING_DEFAULTS)
        for key, kind in SETTINGS.items():
            raw = self.get_setting(key)
            if raw is not None:
                out[key] = (raw == "1") if kind is bool else int(raw) if kind is int else raw
        return out

    def put_settings(self, values: dict) -> dict:
        for key, value in values.items():
            kind = SETTINGS.get(key)
            if kind is None:
                raise ValueError(f"unknown setting {key!r}")
            if type(value) is not kind:  # exact type: True is an int too, and must not pass as minutes
                raise ValueError(f"{key} must be {kind.__name__}")
        for key, value in values.items():
            self.set_setting(key, ("1" if value else "0") if SETTINGS[key] is bool else str(value))
        return self.get_settings()

    # --- notification channels: {type: {field: value}} in the order they were added (secrets included:
    # the API never sends them back to the page)
    def get_channels(self) -> dict[str, dict[str, str]]:
        return json.loads(self.get_setting("notify_channels") or "{}")

    def put_channel(self, kind: str, values: dict[str, str]) -> None:
        """Adds the channel if new; sets only the fields given ("" clears one)."""
        channels = self.get_channels()
        channels.setdefault(kind, {}).update(values)
        self.set_setting("notify_channels", json.dumps(channels))

    def set_channels(self, channels: dict[str, dict[str, str]]) -> None:
        """Replaces every channel at once (restoring a backup)."""
        self.set_setting("notify_channels", json.dumps(channels))

    def delete_channel(self, kind: str) -> None:
        channels = self.get_channels()
        channels.pop(kind, None)
        self.set_setting("notify_channels", json.dumps(channels))

    # --- the campaign log behind History's "Missed"
    def log_campaigns(self, now: datetime, rows: list[dict]) -> None:
        """Upsert the latest view of each active campaign. first_seen and impossible_at_first keep the
        values from the first time Dropwatch saw the campaign."""
        at = now.astimezone(UTC).isoformat()
        with self._db:
            self._db.executemany(
                "INSERT INTO campaign_log (id, name, game, box_art_url, link_url, ends_at, rewards,"
                " first_seen, impossible_at_first, last_seen, linked, badge, never, priority, pinned, live,"
                " watched, outside)"
                " VALUES (:id, :name, :game, :box_art_url, :link_url, :ends_at,"
                " :rewards, :at, :impossible, :at, :linked, :badge, :never, :priority, :pinned, :live,"
                " :watched, :outside)"
                " ON CONFLICT(id) DO UPDATE SET name = excluded.name, game = excluded.game,"
                " box_art_url = excluded.box_art_url, link_url = excluded.link_url,"
                " ends_at = excluded.ends_at,"
                " rewards = excluded.rewards, last_seen = excluded.last_seen, linked = excluded.linked,"
                " badge = excluded.badge, never = excluded.never, priority = excluded.priority,"
                " pinned = excluded.pinned, live = excluded.live, watched = excluded.watched,"
                " outside = excluded.outside",
                [{**r, "at": at, "ends_at": r["ends_at"].astimezone(UTC).isoformat(),
                  "rewards": json.dumps(r["rewards"]), "impossible": int(r["impossible"]),
                  "outside": int(r.get("outside", False)),
                  "linked": None if r["linked"] is None else int(r["linked"]),
                  **{k: int(r[k]) for k in ("badge", "never", "priority", "pinned", "live")}} for r in rows])
            self._db.execute("DELETE FROM campaign_log WHERE ends_at < ?",
                             ((now - CAMPAIGN_LOG_KEEP).astimezone(UTC).isoformat(),))

    def first_seen(self) -> tuple[datetime | None, dict[str, datetime]]:
        """(when the log began, {campaign: when Dropwatch first saw it}) for Up next's "New"."""
        rows = self._db.execute("SELECT id, first_seen FROM campaign_log").fetchall()
        seen = {cid: datetime.fromisoformat(at) for cid, at in rows}
        return (min(seen.values()) if seen else None), seen

    def update_log_rewards(self, cid: str, rewards: list[dict]) -> None:
        """A campaign that just ended can still be claimed for 24 h: keep its claimed flags current (not
        last_seen, which says when Dropwatch last saw it running)."""
        with self._db:
            self._db.execute("UPDATE campaign_log SET rewards = ? WHERE id = ?", (json.dumps(rewards), cid))

    def ended_campaign_ids(self, ids: Sequence[str], now: datetime) -> set[str]:
        at = now.astimezone(UTC).isoformat()
        return {i for (i,) in self._db.execute(
            f"SELECT id FROM campaign_log WHERE ends_at <= ? AND id IN ({','.join('?' * len(ids))})",
            (at, *ids))} if ids else set()

    def missed_between(self, since: datetime, now: datetime) -> list[dict]:
        """Campaigns that ended in (since, now] with a reward left unclaimed, newest end first, each with
        the reason read from the last look Dropwatch had before it ended."""
        out = []
        for row in self._db.execute(
                "SELECT id, name, game, box_art_url, link_url, ends_at, rewards, first_seen,"
                " impossible_at_first,"
                " last_seen, linked, badge, never, priority, pinned, live, watched, outside FROM campaign_log"
                " WHERE ends_at > ? AND ends_at <= ? ORDER BY ends_at DESC",
                (since.astimezone(UTC).isoformat(), now.astimezone(UTC).isoformat())):
            (cid, name, game, art, link, ends, rewards, _first, impossible, last, linked, badge, never,
             priority, pinned, live, watched, outside) = row
            rw = json.loads(rewards)
            # a reward History recorded as claimed counts as claimed even if the last look predates it
            have = Counter(r["name"] for (rows,) in self._db.execute(
                "SELECT rewards FROM claims WHERE campaign_id = ?", (cid,)) for r in json.loads(rows))
            for r in rw:
                if not r["claimed"] and have[r["name"]] > 0:
                    r["claimed"], have[r["name"]] = True, have[r["name"]] - 1
            if all(r["claimed"] for r in rw):
                continue
            ends_at, last_seen = datetime.fromisoformat(ends), datetime.fromisoformat(last)
            if never:
                reason = "never_list"
            elif ends_at - last_seen > MISSED_OFF_AFTER:
                reason = "dropwatch_off"
            elif linked == 0 and not badge:
                reason = "not_linked"
            elif impossible:
                reason = "ran_out_of_time"
            elif not live:
                reason = "no_live_channels"
            elif outside:
                reason = "priority_only"
            else:
                reason = "outranked"
            out.append({"campaign_id": cid, "name": name, "game": game, "box_art_url": art, "link_url": link,
                        "ends_at": ends_at, "reason": reason, "rewards": rw, "rewards_total": len(rw),
                        "rewards_claimed": sum(1 for r in rw if r["claimed"]), "minutes_watched": watched,
                        "started": watched > 0, "priority": bool(priority), "pinned": bool(pinned)})
        return out

    def history_image_urls(self, since: datetime) -> list[str]:
        """Every image History can show for claims since then and campaigns that ended since then (box art
        as stored, so the caller sizes it), for the image cache."""
        urls: list[str] = []
        cut = (since.astimezone(UTC).isoformat(),)
        # campaign_log: only campaigns History would show as a full Missed row (not ~140 catalogue ones)
        for sql in ("SELECT rewards, box_art_url FROM claims WHERE at >= ?",
                    "SELECT rewards, box_art_url FROM campaign_log WHERE ends_at >= ? AND never = 0"
                    " AND (watched > 0 OR priority = 1 OR pinned = 1 OR (linked = 0 AND badge = 0))"):
            for rewards, art in self._db.execute(sql, cut):
                urls += [r["image_url"] for r in json.loads(rewards)] + [art or ""]
        return [u for u in dict.fromkeys(urls) if u]

    # --- claims
    def add_claim(self, at: datetime, campaign_id: str, campaign: str, game: str,
                  rewards: list[tuple[str, str]], *, minutes: int | None = None, channel: str | None = None,
                  campaign_rewards: int | None = None, campaign_ends: datetime | None = None,
                  box_art_url: str | None = None) -> None:
        """minutes: the watch time the drop needed; channel: where it was mined (None when not known)."""
        payload = json.dumps([{"name": n, "image_url": u} for n, u in rewards])
        ends = campaign_ends.astimezone(UTC).isoformat() if campaign_ends else None
        with self._db:
            self._db.execute(
                "INSERT INTO claims (at, campaign_id, campaign, game, rewards, minutes, channel,"
                " campaign_rewards, campaign_ends, box_art_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (at.astimezone(UTC).isoformat(), campaign_id, campaign, game, payload, minutes, channel,
                 campaign_rewards, ends, box_art_url or None))

    def claims_since(self, since: datetime) -> list[dict]:
        rows = self._db.execute(
            "SELECT at, campaign_id, campaign, game, rewards, minutes, channel, campaign_rewards,"
            " campaign_ends, box_art_url FROM claims WHERE at >= ? ORDER BY at DESC",
            (since.astimezone(UTC).isoformat(),))
        return [{"at": datetime.fromisoformat(at), "campaign_id": cid, "campaign": camp, "game": game,
                 "rewards": json.loads(rw), "minutes": mins, "channel": ch, "campaign_rewards": total,
                 "campaign_ends": datetime.fromisoformat(ends) if ends else None, "box_art_url": art}
                for at, cid, camp, game, rw, mins, ch, total, ends, art in rows]

    # --- page password (argon2) and web sessions (sha256 of the token only)
    def has_password(self) -> bool:
        return self.get_setting("page_password_hash") is not None

    def set_password(self, plain: str) -> None:
        if len(plain) < MIN_PASSWORD:
            raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
        self.set_setting("page_password_hash", _ph.hash(plain))

    def password_hash(self) -> str | None:
        return self.get_setting("page_password_hash")

    @staticmethod
    def verify_password(h: str, plain: str) -> bool:
        """No database access, so it can run in a worker thread (argon2 is deliberately slow)."""
        try:
            return _ph.verify(h, plain)
        except VerificationError:
            return False

    def check_password(self, plain: str) -> bool:
        h = self.password_hash()
        return h is not None and Store.verify_password(h, plain)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_web_session(self, now: datetime, user_agent: str = "") -> str:
        token = secrets.token_urlsafe(32)
        at = now.astimezone(UTC).isoformat()
        with self._db:
            expires = (now + SESSION_TTL).astimezone(UTC).isoformat()
            self._db.execute("INSERT INTO web_sessions (token_hash, expires_at, created_at, last_seen_at,"
                             " user_agent) VALUES (?, ?, ?, ?, ?)",
                             (self._token_hash(token), expires, at, at, user_agent[:300]))
            self._db.execute("DELETE FROM web_sessions WHERE expires_at < ?",
                             (now.astimezone(UTC).isoformat(),))
        return token

    def valid_web_session(self, token: str | None, now: datetime) -> bool:
        if not token:
            return False
        h = self._token_hash(token)
        row = self._db.execute("SELECT expires_at, last_seen_at FROM web_sessions WHERE token_hash = ?",
                               (h,)).fetchone()
        if not row or datetime.fromisoformat(row[0]) <= now:
            return False
        # not a write per request
        if not row[1] or now - datetime.fromisoformat(row[1]) >= SESSION_SEEN_EVERY:
            with self._db:
                self._db.execute("UPDATE web_sessions SET last_seen_at = ? WHERE token_hash = ?",
                                 (now.astimezone(UTC).isoformat(), h))
        return True

    def web_sessions(self, now: datetime) -> list[dict]:
        """Signed-in browsers, most recently seen first. id is a prefix of the token's hash, never the
        token."""
        rows = self._db.execute("SELECT token_hash, created_at, last_seen_at, user_agent FROM web_sessions "
                                "WHERE expires_at > ? ORDER BY COALESCE(last_seen_at, '') DESC",
                                (now.astimezone(UTC).isoformat(),))
        return [{"hash": h, "id": h[:SESSION_ID_LEN], "created_at": c, "last_seen_at": s,
                 "user_agent": ua or ""} for h, c, s, ua in rows]

    def session_hash(self, token: str) -> str:
        return self._token_hash(token)

    def delete_web_session_by_id(self, session_id: str) -> bool:
        if len(session_id) != SESSION_ID_LEN:
            return False
        with self._db:
            cur = self._db.execute("DELETE FROM web_sessions WHERE substr(token_hash, 1, ?) = ?",
                                   (SESSION_ID_LEN, session_id))
        return cur.rowcount > 0

    def delete_other_web_sessions(self, keep_token: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM web_sessions WHERE token_hash != ?",
                             (self._token_hash(keep_token),))

    # --- channel points gained (History, weekly summary)
    def add_points(self, at: datetime, channel: str | None, reason: str, points: int) -> None:
        with self._db:
            self._db.execute("INSERT INTO points_log VALUES (?, ?, ?, ?)",
                             (at.astimezone(UTC).isoformat(), channel, reason, int(points)))
            self._db.execute("DELETE FROM points_log WHERE at < ?",
                             ((at - CAMPAIGN_LOG_KEEP).astimezone(UTC).isoformat(),))

    def points_since(self, since: datetime) -> dict:
        row = self._db.execute("SELECT COALESCE(SUM(points), 0), COALESCE(SUM(reason = 'CLAIM'), 0) "
                               "FROM points_log WHERE at >= ?",
                               (since.astimezone(UTC).isoformat(),)).fetchone()
        return {"points": int(row[0]), "chests": int(row[1])}

    def points_by_channel(self, since: datetime) -> dict[str, dict]:
        """login -> {"points", "chests"} gained since then (the Channel points page's per-streamer totals)."""
        rows = self._db.execute("SELECT channel, COALESCE(SUM(points), 0), "
                                "COALESCE(SUM(reason = 'CLAIM'), 0) FROM points_log "
                                "WHERE at >= ? AND channel IS NOT NULL GROUP BY channel",
                                (since.astimezone(UTC).isoformat(),))
        return {lg: {"points": int(p), "chests": int(c)} for lg, p, c in rows}

    # --- channels seen live (favourites suggestions; spec §8 /api/suggestions)
    def record_seen(self, channels: list[tuple[str, str]], at: datetime) -> None:
        stamp = at.astimezone(UTC).isoformat()
        with self._db:
            self._db.executemany(
                "INSERT INTO seen_channels VALUES (?, ?, ?) ON CONFLICT(login) DO UPDATE SET "
                "game = excluded.game, last_seen = excluded.last_seen",
                [(lg, g, stamp) for lg, g in channels])
            self._db.execute("DELETE FROM seen_channels WHERE last_seen < ?",
                             ((at - SEEN_KEEP).astimezone(UTC).isoformat(),))

    def seen_channels(self, now: datetime) -> list[dict]:
        since = (now - SEEN_KEEP).astimezone(UTC).isoformat()
        rows = self._db.execute("SELECT login, game, last_seen FROM seen_channels WHERE last_seen >= ? "
                                "ORDER BY last_seen DESC, login", (since,))
        return [{"login": lg, "game": g, "last_seen": datetime.fromisoformat(t)} for lg, g, t in rows]

    def delete_web_session(self, token: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM web_sessions WHERE token_hash = ?", (self._token_hash(token),))

"""Mining loop. Owns state; never touches any UI (spec §5, §9).

Robustness rules (phase-1 final review):
- No exception escapes the loop: safe_tick() and safe_handle() catch, report
  TWITCH_UNREACHABLE and back off.
- refresh() and claims run under one lock, and each claim id is claimed at most once per run.
- Campaigns are re-fetched hourly (and after a claim), live channels every 5 minutes
  (the reference fetches inventory hourly).
- A channel that sends stream-down is excluded until stream-up or 10 minutes pass, even if
  the game directory still lists it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from .models import (
    CLAIM_GRACE,
    Campaign,
    LiveChannel,
    campaign_active,
    campaign_minutes_needed,
    claimable,
    with_drop,
)
from .planner import Plan, plan, qualifies
from .twitch.constants import PLAY_INTERVAL
from .twitch.gql import AuthExpired, GqlError
from .twitch.pubsub import (
    DropClaimable,
    DropProgress,
    PointsClaimable,
    PointsEarned,
    StreamChanged,
    StreamDown,
    StreamUp,
    topic,
)

log = logging.getLogger("dropwatch.runner")
FAILS_BEFORE_SWITCH = 9  # ticks are 10 s apart: ~90 s of failed playback before excluding
STALL_TICKS = 18  # ticks are PLAY_INTERVAL (10 s) apart: resync after ~3 min of silence
EXCLUDE_FOR = timedelta(minutes=10)
REFRESH_EVERY = timedelta(minutes=5)
CAMPAIGNS_EVERY = timedelta(hours=1)  # default; Settings' campaigns_every_minutes overrides it
CHEST_LOOKBACK = timedelta(days=7)  # channels watched this recently are checked for a waiting chest
RECENT_CHEST_CHANNELS = 30  # at most this many of them per refresh (one or two batched requests)
STREAK_VISIT = timedelta(minutes=7)  # a favourite's new stream is watched this long for its watch streak
STREAK_REMEMBER = 200  # visited broadcast ids kept across restarts
# Channel points page (asked for 2026-11-08): Twitch counts watch time on two streams at once, so up to two of
# the list's live streamers are watched for their points, one fewer while a drop channel is being watched
POINTS_SLOTS = 2
CLAIM_WAIT = timedelta(hours=1)  # force campaign re-fetches this long; the hourly fetch covers the rest
BACKOFF_START, BACKOFF_MAX = 60.0, 600.0
HEALTH_STALL = timedelta(minutes=15)  # no tick for this long = stuck (longer than any back-off sleep)
# spec §4 (2026-10-10): an unknown account link that earns nothing for 10 minutes of good playback
LINK_PROBE_TICKS = 60  # ticks are PLAY_INTERVAL (10 s) apart
MAYBE_UNLINKED_FOR = timedelta(hours=6)
# earning doesn't prove the link: Twitch's inventory does, once it lists the campaign (ER ESPORTS DROPS,
# 2026-10-10: an hour of counted minutes, then isAccountConnected false and no reward)
LINK_RECHECK = timedelta(minutes=10)
# GqlError covers TwitchUnreachable; the rest are unexpected response shapes from parsing.
TWITCH_ERRORS = (GqlError, KeyError, TypeError, ValueError)


class State(StrEnum):
    MINING = "mining"
    SWITCHED = "switched"
    PAUSED = "paused"
    IDLE = "idle"
    SIGNED_OUT = "signed_out"
    TWITCH_UNREACHABLE = "twitch_unreachable"


class Runner:
    def __init__(self, client, watcher, pubsub, store, *, user_id: int,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 emit: Callable[[str, dict], None] = lambda k, d: None,
                 points_watchers: Sequence = ()):
        self._client, self._watcher, self._pubsub, self._store = client, watcher, pubsub, store
        # Channel points: one watcher per stream watched for points (each keeps its own playback state)
        self._points_watchers = list(points_watchers)[:POINTS_SLOTS]
        self.points_watching: list[LiveChannel] = []
        self.points_since: dict[str, datetime] = {}  # login -> watched without a break since
        self.points_waiting: dict[str, str] = {}  # live but not watched for points: login -> "drops" | "full"
        self._points_slot: dict[str, object] = {}  # login -> its watcher
        self._points_fails: dict[str, int] = {}
        self._user_id, self._clock, self._emit = user_id, clock, emit
        self.state: State = State.IDLE
        self.plan: Plan | None = None
        self.campaigns: list[Campaign] = []
        self.live: list[LiveChannel] = []
        self.watching: LiveChannel | None = None
        self.paused_until: datetime | None = None
        self._paused = False
        self._fails = 0
        self._ticks_since_progress = 0
        self._excluded: dict[str, datetime] = {}
        self._down_ids: dict[int, str] = {}
        self._override_campaign: str | None = None
        self._override_channel: str | None = None
        self.last_refresh: datetime | None = None
        self._campaigns_at: datetime | None = None
        self._lock = asyncio.Lock()
        self._claimed: set[str] = set()
        self._backoff = 0.0
        self._awaiting_claim: dict[str, datetime] = {}  # drop id -> stop forcing re-fetches at
        self._gave_up_claim: set[str] = set()
        self._refresh_backoff = 0.0
        self._retry_refresh_at: datetime | None = None
        self.last_switch: dict | None = None  # {"from", "to", "at"}
        self._link_probe: dict[str, tuple[int, int]] = {}  # campaign -> (good ticks, minutes at start)
        self._link_recheck: dict[str, datetime] = {}  # unknown-link campaign -> campaigns last re-read for it
        self.maybe_unlinked: dict[str, datetime] = {}  # campaign -> marked at
        self._mined_on: dict[str, str] = {}  # campaign -> channel last watched for it (History details)
        self.last_tick: datetime | None = None
        self._streak: tuple[str, str, datetime] | None = None  # watch-streak visit: (broadcast, login, since)
        # broadcasts already visited (or mined) for their streak; kept across restarts (review fix)
        get = getattr(store, "get_setting", None)
        self._streak_done: set[str] = set(json.loads((get("streak_done") if get else None) or "[]"))

    @property
    def next_check_at(self) -> datetime | None:
        if self.state == State.TWITCH_UNREACHABLE and self._retry_refresh_at is not None:
            return self._retry_refresh_at
        return self.last_refresh + REFRESH_EVERY if self.last_refresh else None

    @property
    def campaigns_at(self) -> datetime | None:
        return self._campaigns_at

    @property
    def catalog_status(self):
        """(ok|stale|unreachable, since) when campaigns come from the catalogue, else None."""
        catalog = getattr(self._client, "catalog", None)
        if catalog is None or not getattr(catalog, "used", True):
            return None
        return catalog.status

    # --- commands
    def pause(self, until: datetime | None) -> None:
        self._paused, self.paused_until = True, until
        self._set_points([], self._clock())  # nothing is watched while paused, points included
        self._set_state(State.PAUSED, {"until": until.isoformat() if until else None})

    def resume(self) -> None:
        self._paused, self.paused_until = False, None
        self._set_state(State.MINING if self.watching else State.IDLE)

    def mine_now(self, campaign_id: str) -> None:
        self._override_campaign = campaign_id
        # "Mine now" on a may-need-linking campaign means "I linked it, try again"
        self.maybe_unlinked.pop(campaign_id, None)
        self._link_probe.pop(campaign_id, None)
        self._end_streak_visit()

    def use_channel(self, login: str) -> None:
        self._override_channel = login
        self._end_streak_visit()  # the user's pick wins over a watch-streak visit

    # --- core
    def _set_state(self, state: State, extra: dict | None = None) -> None:
        if state != self.state or extra:
            self.state = state
            data = {"state": str(state), **(extra or {})}
            self._emit("state", data)
            self._store.log_event("state", data)

    async def refresh(self, *, force_campaigns: bool = False, manual: bool = False) -> None:
        """manual: the page's Check Twitch (logged as clicked in Activity)."""
        async with self._lock:
            await self._refresh(force_campaigns, manual)

    async def _refresh(self, force_campaigns: bool, manual: bool = False) -> None:
        now = self._clock()
        started = time.monotonic()
        prefs = self._store.get_prefs()
        before: dict[str, Campaign] | None = None
        try:
            due = (self._campaigns_at is None or now - self._campaigns_at >= self._campaigns_every()
                   or bool(self._awaiting_claim))
            if force_campaigns or due:
                before = {c.id: c for c in self.campaigns}
                self.campaigns = await self._client.campaigns()
                self._campaigns_at = now
                if await self._catch_up_claims(now):
                    self.campaigns = await self._client.campaigns()
                self._settle_awaiting(now)
            self.live = await self._client.live_channels(self.campaigns, prefs, now)
            if (record := getattr(self._store, "record_seen", None)) is not None:
                record([(c.login, c.game_name) for c in self.live], now)
        except AuthExpired:
            self.watching = None
            self._set_state(State.SIGNED_OUT)
            return
        except TWITCH_ERRORS as exc:
            log.warning("Refresh failed: %s: %s", type(exc).__name__, exc)
            self._refresh_backoff = (min(self._refresh_backoff * 2, BACKOFF_MAX)
                                     if self._refresh_backoff else BACKOFF_START)
            self._retry_refresh_at = now + timedelta(seconds=self._refresh_backoff)
            self._set_state(State.TWITCH_UNREACHABLE, {"error": f"{type(exc).__name__}: {exc}"})
            return
        self.last_refresh = now
        self._refresh_backoff, self._retry_refresh_at = 0.0, None
        if before is not None:
            self._log_check(before, manual, time.monotonic() - started)
        self._bookkeeping(now, prefs)
        self._plan(now, prefs)
        await self._claim_waiting_points()

    def _log_check(self, before: dict[str, Campaign], manual: bool, seconds: float) -> None:
        """Activity: a campaign re-read (Check Twitch, or the Settings interval and other automatic
        ones), with what it found: new campaigns and games whose account now shows as linked."""
        linked = sorted({c.game.name for c in self.campaigns
                         if c.linked is True and c.id in before and before[c.id].linked is not True})
        self._store.log_event("checked", {
            "manual": manual, "campaigns": len(self.campaigns),
            "new": sum(1 for c in self.campaigns if c.id not in before) if before else 0,
            "linked": linked, "seconds": round(seconds, 1)})

    def _bookkeeping(self, now: datetime, prefs) -> None:
        """History's campaign log and pin pruning: a failure is logged, never a reason to stop planning."""
        for step in (self._forget_ended_pins, lambda n: self._log_campaigns(n, prefs)):
            try:
                step(now)
            except Exception as exc:  # noqa: BLE001 - bookkeeping must never stop mining
                log.warning("History bookkeeping failed: %s: %s", type(exc).__name__, exc)

    def _log_campaigns(self, now: datetime, prefs) -> None:
        """Keep History's "Missed" able to say why: the latest view of every active campaign."""
        log = getattr(self._store, "log_campaigns", None)
        if log is None:
            return
        rows = []
        for c in self.campaigns:
            if not campaign_active(c, now):
                if c.ends_at <= now < c.ends_at + CLAIM_GRACE and hasattr(self._store, "update_log_rewards"):
                    self._store.update_log_rewards(c.id, [{"name": r.name, "image_url": r.image_url,
                                                           "claimed": d.claimed}
                                                          for d in c.drops for r in d.rewards])
                continue
            left = (c.ends_at - now).total_seconds() / 60
            rows.append({
                "id": c.id, "name": c.name, "game": c.game.name, "box_art_url": c.game.box_art_url,
                "link_url": c.link_url, "ends_at": c.ends_at, "linked": c.linked,
                "badge": c.has_badge_or_emote,
                "rewards": [{"name": r.name, "image_url": r.image_url, "claimed": d.claimed}
                            for d in c.drops for r in d.rewards],
                "impossible": campaign_minutes_needed(c, now) > left,
                "never": c.game.name in prefs.never, "priority": c.game.name in prefs.priority,
                "pinned": c.id in prefs.pins, "live": any(qualifies(c, ch) for ch in self.live),
                "watched": max((d.current_minutes for d in c.drops), default=0),
                "outside": prefs.priority_only and c.game.name not in prefs.priority,
            })
        log(now, rows)

    def _forget_ended_pins(self, now: datetime) -> None:
        """A pin (or an ignored Needs you campaign) lasts as long as its campaign: drop it once the campaign
        is known to have ended (listed and past its end, or logged as ended). One whose campaign is just
        missing from a short list stays."""
        for get_name, set_name in (("get_pins", "set_pins"), ("get_ignored", "set_ignored")):
            get = getattr(self._store, get_name, None)
            if get is None:
                continue
            ids = get()
            listed = {c.id: c for c in self.campaigns}
            in_log = getattr(self._store, "ended_campaign_ids", lambda ids, at: set())(ids, now)
            kept = [i for i in ids if not (listed[i].ends_at <= now if i in listed else i in in_log)]
            if kept != ids:
                getattr(self._store, set_name)(kept)

    async def replan(self) -> None:
        """Re-decide from what is already known (lists or an override changed): no Twitch calls."""
        async with self._lock:
            self._plan(self._clock(), self._store.get_prefs())

    def _plan(self, now: datetime, prefs) -> None:
        """Lock held. Plan from the cached campaigns and live channels, then act on the result."""
        self._excluded = {k: v for k, v in self._excluded.items() if v > now}
        usable = [c for c in self.live if c.login not in self._excluded]
        previous = self.watching
        self._settle_link_marks(now)
        planned = [replace(c, linked=False) if c.id in self.maybe_unlinked else c for c in self.campaigns]
        self.plan = plan(planned, usable, prefs, now,
                         # during a watch-streak visit, the drop channel is the one to stay on
                         watching=(self.plan.current.channel_login if self._streak and self.plan
                                   and self.plan.current else previous.login if previous else None),
                         override_campaign=self._override_campaign,
                         override_channel=self._override_channel,
                         current_campaign=self.plan.current.campaign_id
                         if self.plan and self.plan.current else None)
        cur = self.plan.current
        # a link test only counts consecutive time on one campaign: restart it after a break
        self._link_probe = {k: v for k, v in self._link_probe.items() if cur and k == cur.campaign_id}
        # spec §6: overrides last only while the plan still honours them
        if self._override_campaign and (cur is None or cur.campaign_id != self._override_campaign):
            self._override_campaign = None
        if self._override_channel and (cur is None or cur.channel_login != self._override_channel):
            self._override_channel = None
        self.watching = next((c for c in usable if cur and c.login == cur.channel_login), None)
        visit = self._streak_visit(now, usable, prefs)
        if visit is not None:
            self.watching = visit  # drops wait a few minutes; the plan itself is unchanged
        elif self.watching and cur:
            for cid in (cur.campaign_id, *self.plan.also_credited):
                self._mined_on[cid] = self.watching.login
        if self._paused:
            self.points_waiting = {}
        self._set_points([] if self._paused else self._choose_points(usable, prefs), now)
        topics = {topic("user_drops", self._user_id), topic("user_notifications", self._user_id)}
        if self._points_on() or self.points_watching:  # points-earned also feeds the page's totals
            topics.add(topic("user_points", self._user_id))
        if self.watching:
            topics |= {topic("stream_state", self.watching.id), topic("stream_update", self.watching.id)}
        topics |= {topic("stream_state", ch.id) for ch in self.points_watching}
        self._pubsub.set_topics(topics)
        if not self._paused:
            if self.watching is None:
                self._set_state(State.IDLE)
            elif previous and previous.login != self.watching.login:
                self._fails = 0
                info = {"from": previous.login, "to": self.watching.login}
                self.last_switch = {**info, "at": now}
                self._emit("switched", info)
                self._store.log_event("switched", {**info, **self._switch_why(previous.login)})
                self._set_state(State.SWITCHED, info)
            else:
                self._set_state(State.MINING)
        self._emit("refreshed", {"at": now.isoformat()})

    def _choose_points(self, usable: list[LiveChannel], prefs) -> list[LiveChannel]:
        """The Channel points list's live streamers to watch, top of the list first. The one the drop miner is
        on already earns there; past the free slots the rest wait (points_waiting says which and why)."""
        self.points_waiting = {}
        live = {c.login: c for c in usable}
        slots = min(len(self._points_watchers), POINTS_SLOTS - (1 if self.watching else 0))
        picks: list[LiveChannel] = []
        for lg in prefs.points_channels:
            ch = live.get(lg)
            if ch is None:
                continue
            if self.watching and lg == self.watching.login:
                self.points_waiting[lg] = "drops"
            elif len(picks) < slots:
                picks.append(ch)
            else:
                self.points_waiting[lg] = "full"
        return picks

    def _set_points(self, picks: list[LiveChannel], now: datetime) -> None:
        """Hand each picked stream a watcher, keeping the one it already has; log who starts and stops."""
        new = {c.login for c in picks}
        for ch in self.points_watching:
            if ch.login not in new:
                self._points_slot.pop(ch.login, None)
                self.points_since.pop(ch.login, None)
                self._points_fails.pop(ch.login, None)
                self._store.log_event("points_watch", {"channel": ch.login, "on": False})
        free = [w for w in self._points_watchers if w not in self._points_slot.values()]
        for ch in picks:
            if ch.login not in self._points_slot:
                self._points_slot[ch.login] = free.pop(0)
                self.points_since[ch.login] = now
                self._store.log_event("points_watch", {"channel": ch.login, "on": True,
                                                       "game": ch.game_name or None})
        self.points_watching = list(picks)

    async def _tick_points(self, now: datetime) -> None:
        """Play each points stream, side by side. One that keeps failing is set aside like a drop channel."""
        chans = list(self.points_watching)
        if not chans:
            return
        results = await asyncio.gather(*(self._points_slot[c.login].send(c, now) for c in chans),
                                       return_exceptions=True)
        dropped = False
        for ch, ok in zip(chans, results, strict=True):
            if ok is True:
                self._points_fails.pop(ch.login, None)
                continue
            n = self._points_fails.get(ch.login, 0) + 1
            if n < FAILS_BEFORE_SWITCH:
                self._points_fails[ch.login] = n
                continue
            self._points_slot[ch.login].forget(ch.login)
            self._excluded[ch.login] = now + EXCLUDE_FOR
            self._store.log_event("points_dropped", {"channel": ch.login})
            dropped = True
        if dropped:
            await self.replan()

    def _settle_link_marks(self, now: datetime) -> None:
        """A "may need linking" mark ends once Twitch reports the link either way, or after 6 h."""
        by_id = {c.id: c for c in self.campaigns}
        for cid, at in list(self.maybe_unlinked.items()):
            c = by_id.get(cid)
            if c is None or c.linked is not None or now - at >= MAYBE_UNLINKED_FOR:
                del self.maybe_unlinked[cid]

    @property
    def streak_visit(self) -> tuple[str, datetime] | None:
        """(channel, ends at) while a watch-streak visit is on, for the page."""
        return (self._streak[1], self._streak[2] + STREAK_VISIT) if self._streak else None

    def _mark_streak_done(self, broadcast: str) -> None:
        self._streak_done.add(broadcast)
        if (put := getattr(self._store, "set_setting", None)) is not None:
            put("streak_done", json.dumps(sorted(self._streak_done)[-STREAK_REMEMBER:]))

    async def end_streak_visit(self) -> None:
        """The page's "Back to drops now"."""
        self._end_streak_visit()
        await self.replan()

    def _end_streak_visit(self) -> None:
        if self._streak:
            self._mark_streak_done(self._streak[0])
            self._streak = None

    def _streak_on(self) -> bool:
        get = getattr(self._store, "get_settings", None)
        return bool(get and get().get("points_watch_streak")) and self._points_on()

    def _streak_visit(self, now: datetime, usable: list[LiveChannel], prefs) -> LiveChannel | None:
        """Watch streaks (asked for 2026-10-11): when a favourite starts a new stream, watch it for
        STREAK_VISIT first. One visit per stream; a favourite already being mined earns it anyway."""
        if not self._streak_on():
            self._streak = None
            return None
        if self._streak:
            b, lg, since = self._streak
            ch = next((c for c in usable if c.login == lg and c.broadcast_id == b), None)
            if ch is not None and now - since < STREAK_VISIT:
                return ch
            self._end_streak_visit()
        drop = self.watching
        for lg in prefs.favourites:
            ch = next((c for c in usable if c.login == lg), None)
            if ch is None or ch.broadcast_id in self._streak_done:
                continue
            # one the Channel points list will watch anyway (a slot is free for it) needs no detour
            watched = {p.login for p in self._choose_points(usable, prefs)}
            if drop is not None:
                watched.add(drop.login)
            if ch.login in watched:
                self._mark_streak_done(ch.broadcast_id)  # earned while mining it, or watching it for points
                continue
            self._streak = (ch.broadcast_id, ch.login, now)
            return ch
        return None

    async def _probe_link(self, now: datetime) -> None:
        """Called after each good playback tick. Unknown link + no new minutes for 10 min -> Needs you."""
        if self._streak:  # a watch-streak visit earns no drop minutes by design
            return
        cur = self.plan.current if self.plan else None
        c = next((x for x in self.campaigns if cur and x.id == cur.campaign_id), None)
        if c is None or c.linked is not None or c.has_badge_or_emote:
            return
        total = sum(d.current_minutes for d in c.drops)
        ticks, start = self._link_probe.get(c.id, (0, total))
        if total > start:
            # it earns, but that doesn't prove the link: re-read Twitch's campaigns now, then every
            # LINK_RECHECK while the link is still unknown, rather than waiting for the hourly fetch
            self._link_probe.pop(c.id, None)
            last = self._link_recheck.get(c.id)
            if last is None or now - last >= LINK_RECHECK:
                self._link_recheck[c.id] = now
                await self.refresh(force_campaigns=True)
            return
        ticks += 1
        if ticks < LINK_PROBE_TICKS:
            self._link_probe[c.id] = (ticks, start)
            return
        self._link_probe.pop(c.id, None)
        self.maybe_unlinked[c.id] = now
        info = {"campaign": c.name, "reason": "may need linking"}
        self._emit("needs_you", info)
        self._store.log_event("needs_you", info)
        await self.refresh()

    def _settle_awaiting(self, now: datetime) -> None:
        """Stop forcing campaign fetches for drops that are claimed, gone, or waited on for 1 h."""
        for drop_id, deadline in list(self._awaiting_claim.items()):
            d = next((d for c in self.campaigns if (d := c.drop(drop_id))), None)
            if d is None or d.claimed:
                del self._awaiting_claim[drop_id]
            elif now >= deadline:
                del self._awaiting_claim[drop_id]
                self._gave_up_claim.add(drop_id)  # never re-armed this run

    async def _catch_up_claims(self, now: datetime) -> bool:
        """Claim anything Twitch has issued a claim id for (reference can_claim). Lock held."""
        claimed = False
        for c in list(self.campaigns):
            for d in c.drops:
                if claimable(c, d, now):
                    claimed |= await self._claim(c, d.id, d.claim_id)
        return claimed

    async def _claim(self, c: Campaign, drop_id: str, claim_id: str | None) -> bool:
        """Lock held by caller. Each claim id is claimed at most once per run."""
        if not claim_id or claim_id in self._claimed:
            return False
        if c.linked is False and not c.has_badge_or_emote:
            # Twitch answers ELIGIBLE_FOR_ALL here but awards nothing (ER ESPORTS DROPS, 2026-10-10);
            # the campaign stays in Needs you, and the claim goes through once Twitch says it's linked
            return False
        d = c.drop(drop_id)
        try:
            ok = await self._client.claim(claim_id)
        except TWITCH_ERRORS as exc:
            log.warning("Claim raised %s", type(exc).__name__)
            ok = False
        if ok:
            self._claimed.add(claim_id)
            info = {"campaign": c.name, "reward": ", ".join(r.name for r in d.rewards) if d else drop_id}
            # game, watch time and channel only for the "a reward is claimed" push
            self._emit("claimed", {**info, "game": c.game.name, "minutes": d.required_minutes if d else None,
                                   "channel": self._mined_on.get(c.id)})
            self._store.log_event("claimed", {**info, "game": c.game.name})
            if hasattr(self._store, "add_claim"):
                self._store.add_claim(self._clock(), c.id, c.name, c.game.name,
                                      [(r.name, r.image_url) for r in (d.rewards if d else ())],
                                      minutes=d.required_minutes if d else None,
                                      channel=self._mined_on.get(c.id),
                                      campaign_rewards=sum(len(x.rewards) for x in c.drops),
                                      campaign_ends=c.ends_at, box_art_url=c.game.box_art_url)
            return True
        self._store.log_event("claim_failed", {"campaign": c.name, "drop": drop_id})
        # for the "a reward couldn't be claimed" notification; same shape as "claimed", so a later
        # success matches it
        self._emit("claim_failed", {"campaign": c.name,
                                    "reward": ", ".join(r.name for r in d.rewards) if d else drop_id})
        return False

    async def tick(self) -> None:
        now = self._clock()
        if self._paused:
            if self.paused_until is None or now < self.paused_until:
                self._set_state(State.PAUSED)
                return
            self.resume()
            await self.replan()  # points watching comes back now, not at the next refresh
        if self._streak and now - self._streak[2] >= STREAK_VISIT:
            await self.replan()  # a visit ends on time, not at the next refresh (review fix)
        if self.state == State.TWITCH_UNREACHABLE and self._retry_refresh_at is not None:
            due = now >= self._retry_refresh_at  # back off while Twitch is failing
        else:
            due = self.last_refresh is None or now - self.last_refresh >= REFRESH_EVERY
        if due:
            await self.refresh()
        await self._tick_points(now)
        if self.watching is None:
            return
        if await self._watcher.send(self.watching, now):
            self._fails = 0
            await self._probe_link(now)
        else:
            self._fails += 1
            if self._fails >= FAILS_BEFORE_SWITCH:
                bad = self.watching.login
                self._watcher.forget(bad)
                self._excluded[bad] = now + EXCLUDE_FOR
                self._store.log_event("channel_dropped", {"channel": bad})
                self._fails = 0
                await self.refresh()
                return
        self._ticks_since_progress += 1
        if self._ticks_since_progress >= STALL_TICKS and self.watching:
            try:
                cur = await self._client.current_drop(self.watching.id)
            except TWITCH_ERRORS as exc:
                log.info("Progress resync failed: %s", type(exc).__name__)
                cur = None
            self._ticks_since_progress = 0  # whatever the outcome, wait STALL_TICKS again
            if cur:
                await self.handle(DropProgress(cur[0], cur[1], -1))

    async def safe_tick(self) -> float:
        """One tick that never raises. Returns how long to sleep before the next one."""
        started = self._clock()
        self.last_tick = started  # the Docker health check reads it
        try:
            await self.tick()
        except Exception as exc:  # noqa: BLE001  the loop must survive anything
            log.exception("Tick failed")
            self._set_state(State.TWITCH_UNREACHABLE, {"error": type(exc).__name__})
            self._backoff = min(self._backoff * 2, BACKOFF_MAX) if self._backoff else BACKOFF_START
            return self._backoff
        self._backoff = 0.0
        elapsed = (self._clock() - started).total_seconds()
        return max(0.0, PLAY_INTERVAL - elapsed)  # keep a steady 10 s period like the reference

    def _switch_why(self, previous: str) -> dict:
        """For Activity: what is mined now and why the channel changed."""
        gone = previous not in self._excluded and any(ch.login == previous for ch in self.live)
        if self._streak and self.watching and self.watching.login == self._streak[1]:
            return {"campaign": None, "game": self.watching.game_name or None, "reason": "watch streak",
                    "channel_reason": None, "from_live": gone}
        choice = self.plan.current if self.plan else None
        c = next((x for x in self.campaigns if choice and x.id == choice.campaign_id), None)
        return {"campaign": c.name if c else None, "game": c.game.name if c else None,
                "reason": choice.reason if choice else None,
                "channel_reason": choice.channel_reason if choice else None,
                # the directory lists a stream for minutes after it ends: an excluded channel is gone
                "from_live": previous not in self._excluded and any(ch.login == previous for ch in self.live)}

    def _campaigns_every(self) -> timedelta:
        """Settings' "Check Twitch for campaign changes every" (campaigns_every_minutes; 1 h by default)."""
        get = getattr(self._store, "get_settings", None)
        minutes = get().get("campaigns_every_minutes") if get else None
        return timedelta(minutes=minutes) if minutes else CAMPAIGNS_EVERY

    def _points_on(self) -> bool:
        """Settings' "Also claim channel points" (claim_points; on by default)."""
        get = getattr(self._store, "get_settings", None)
        return bool(get and get().get("claim_points"))

    async def _claim_points(self, channel_id: int, claim_id: str, login: str | None = None) -> None:
        try:
            ok = await self._client.claim_points(channel_id, claim_id)
        except Exception as exc:  # noqa: BLE001 - points are a bonus: never let them break mining
            log.info("Points claim raised %s", type(exc).__name__)
            ok = False
        login = login or next((ch.login for ch in self.live if ch.id == channel_id), None)
        self._store.log_event("points_claimed" if ok else "points_claim_failed",
                              {"channel_id": channel_id, "channel": login})

    def _recent_channels(self) -> list[str]:
        """Channels watched in the last week, newest first (from Activity's switch events), capped."""
        switched = getattr(self._store, "switched_since", None)
        if switched is None:
            return []
        out: list[str] = []
        for data in switched(self._clock() - CHEST_LOOKBACK):
            for lg in (data.get("to"), data.get("from")):
                if lg and lg not in out:
                    out.append(lg)
            if len(out) >= RECENT_CHEST_CHANNELS:
                break
        return out[:RECENT_CHEST_CHANNELS]

    async def _claim_waiting_points(self) -> None:
        """Bonus chests stay claimable after we stop watching a channel, and one already waiting when we
        start watching never arrives over PubSub: once per refresh, look on the channel being watched and
        on those watched in the last week (asked for 2026-10-11), in one batch."""
        if not self._points_on():
            return
        logins = [self.watching.login] if self.watching else []
        # the Channel points list too: a chest left when its stream stopped being watched still waits there
        for lg in (*(c.login for c in self.points_watching), *self._store.get_prefs().points_channels,
                   *self._recent_channels()):
            if lg not in logins:
                logins.append(lg)
        logins = logins[:RECENT_CHEST_CHANNELS + POINTS_SLOTS + 1]
        if not logins:
            return
        try:
            waiting = await self._client.waiting_points_claims(logins)
        except Exception as exc:  # noqa: BLE001 - points are a bonus: never let them break a refresh
            log.info("Points check raised %s", type(exc).__name__)
            return
        for login, channel_id, claim_id in waiting:
            await self._claim_points(channel_id, claim_id, login)

    async def handle(self, event: object) -> None:
        if isinstance(event, PointsClaimable):
            if self._points_on() and event.channel_id and event.claim_id:
                await self._claim_points(event.channel_id, event.claim_id)
            return
        if isinstance(event, PointsEarned):
            login = next((ch.login for ch in self.live if ch.id == event.channel_id), None)
            if (add := getattr(self._store, "add_points", None)) is not None and event.points:
                add(self._clock(), login, event.reason, event.points)  # History and the weekly summary
            if event.reason not in ("WATCH", "CLAIM"):  # every-5-minute points and chests: not news
                self._store.log_event("points_earned", {"channel": login, "reason": event.reason,
                                                        "points": event.points})
            if event.reason == "WATCH_STREAK" and self._streak and login == self._streak[1]:
                self._end_streak_visit()
                await self.replan()  # back to drops now
            return
        if isinstance(event, DropProgress):
            self._ticks_since_progress = 0
            for i, c in enumerate(self.campaigns):
                d = c.drop(event.drop_id)
                if d is not None:
                    self.campaigns[i] = with_drop(c, replace(d, current_minutes=event.current))
                    if event.current >= d.required_minutes > 0 and not d.claimed:
                        # Twitch may never send drop-claim; fetch the claim id at the next refresh
                        if d.id not in self._gave_up_claim:
                            self._awaiting_claim.setdefault(d.id, self._clock() + CLAIM_WAIT)
            self._emit("progress", {"drop": event.drop_id, "minutes": event.current})
        elif isinstance(event, DropClaimable):
            async with self._lock:
                for c in self.campaigns:
                    if c.drop(event.drop_id) is not None:
                        await self._claim(c, event.drop_id, event.claim_id)
                        break
            await self.refresh(force_campaigns=True)
        elif isinstance(event, StreamUp):
            login = self._down_ids.pop(event.channel_id, None)
            if login:
                self._excluded.pop(login, None)
        elif isinstance(event, StreamDown) and (
                ch := next((c for c in self.points_watching if c.id == event.channel_id), None)):
            # a points stream ended: set it aside like a drop channel, and fill its slot from the list
            self._excluded[ch.login] = self._clock() + EXCLUDE_FOR
            self._down_ids[ch.id] = ch.login
            await self.replan()
        elif isinstance(event, (StreamDown, StreamChanged)):
            if self.watching and event.channel_id == self.watching.id:
                if isinstance(event, StreamDown):
                    # the directory can list a stream for minutes after it ends: exclude it
                    self._excluded[self.watching.login] = self._clock() + EXCLUDE_FOR
                    self._down_ids[self.watching.id] = self.watching.login
                await self.refresh()

    async def safe_handle(self, event: object) -> None:
        try:
            await self.handle(event)
        except Exception as exc:  # noqa: BLE001  one bad event must not stop the rest
            log.exception("Handling %s failed", type(event).__name__)
            self._set_state(State.TWITCH_UNREACHABLE, {"error": type(exc).__name__})


async def run_cli(store) -> int:
    """`dropwatch run`: headless mining until Ctrl+C or the Twitch session expires."""
    from .events import EventBus
    from .service import MinerService

    svc = MinerService(store, EventBus())
    if not await svc.start():
        print("Not signed in. Run: dropwatch signin")
        return 1
    try:
        await svc.wait_stopped()
    finally:
        await svc.stop()
    print("Twitch session expired. Run: dropwatch signin")
    return 1

"""Pure snapshots of runner/store state for the API. No I/O beyond the store reads passed in."""
from __future__ import annotations

from datetime import datetime, timedelta

from ..models import Campaign, campaign_active, campaign_minutes_needed, campaign_ratio, deadline_verdict
from ..planner import qualifies
from .models import (
    CampaignOut,
    CatalogOut,
    ChannelOut,
    ClaimOut,
    CurrentOut,
    DropOut,
    HistoryOut,
    MissedOut,
    PointsWatchOut,
    RewardOut,
    StateOut,
    StreakVisitOut,
    SwitchOut,
)

SWITCH_NOTICE_FOR = timedelta(minutes=10)


NEW_FOR = timedelta(hours=24)  # Up next's "New": first seen within this long
NEW_AFTER_START = timedelta(hours=1)  # ...and not in the log's first hour (the first look sees everything)


def campaign_out(c: Campaign, now: datetime, verdict: str | None,
                 maybe_unlinked: bool = False) -> CampaignOut:
    return CampaignOut(
        id=c.id, name=c.name, game=c.game.name, box_art_url=c.game.box_art_url, ends_at=c.ends_at,
        linked=c.linked, maybe_unlinked=maybe_unlinked, link_url=c.link_url,
        allowed_channels=list(c.allowed_logins),
        minutes_needed=campaign_minutes_needed(c, now), verdict=verdict,
        drops=[DropOut(id=d.id, name=d.name, required_minutes=d.required_minutes,
                       current_minutes=d.current_minutes, claimed=d.claimed, starts_at=d.starts_at,
                       ends_at=d.ends_at, rewards=[RewardOut(name=r.name, image_url=r.image_url)
                                                   for r in d.rewards])
               for d in c.drops],
    )


def state_view(runner, store, now: datetime) -> StateOut:
    session = store.get_session()
    if runner is None:
        return StateOut(state="signed_out" if session is None else "idle", signed_in=session is not None,
                        login=session.login if session else None, paused_until=None, last_refresh=None,
                        current=None, needs_you=[], up_next=[], done=[], catalog=None)
    by_id = {c.id: c for c in runner.campaigns}
    plan = runner.plan
    began, seen = store.first_seen() if hasattr(store, "first_seen") else (None, {})

    def is_new(cid: str) -> bool:
        at = seen.get(cid)
        # the first look logs everything that was already running: none of that is news
        return bool(at and began and at - began > NEW_AFTER_START and now - at < NEW_FOR)
    verdicts = plan.verdicts if plan else {}

    def out(cid: str):
        c = by_id.get(cid)
        if c is None:
            return None
        v = verdicts.get(cid)
        if v is None and campaign_minutes_needed(c, now) > 0:
            v = deadline_verdict(campaign_ratio(c, now))
        o = campaign_out(c, now, v, maybe_unlinked=cid in getattr(runner, "maybe_unlinked", {}))
        o.new = is_new(cid)
        return o

    current = None
    if plan and plan.current and runner.watching and (camp := out(plan.current.campaign_id)):
        favs = store.get_prefs().favourites
        w = runner.watching
        chosen = by_id[plan.current.campaign_id]
        others = sorted((ch for ch in runner.live if ch.login != w.login and qualifies(chosen, ch)),
                        key=lambda ch: (ch.login not in favs, -ch.viewers, ch.login))
        current = CurrentOut(
            campaign=camp, channel=ChannelOut(login=w.login, viewers=w.viewers, favourite=w.login in favs),
            reason=plan.current.reason, channel_reason=plan.current.channel_reason,
            also_credited=list(plan.also_credited),
            channels=[ChannelOut(login=ch.login, viewers=ch.viewers, favourite=ch.login in favs)
                      for ch in others])
    keep = lambda ids: [o for i in ids if (o := out(i)) is not None]  # noqa: E731
    pins = set(store.get_prefs().pins)
    if current and plan.current.campaign_id in pins:
        current.campaign.pinned = True
    # back to back in queue order after what is being mined now: which would end before their turn
    t = now + timedelta(minutes=current.campaign.minutes_needed if current else 0)
    up_next = []
    alongside = set(plan.also_credited) if plan else set()  # earned on the same stream, at the same time
    for o in keep(plan.queue if plan else ()):
        if o.id not in alongside:
            t += timedelta(minutes=o.minutes_needed)
        up_next.append(o.model_copy(update={"pinned": o.id in pins, "ends_before_turn": t > o.ends_at}))
    never_games = store.get_prefs().never
    never = sorted((c for c in runner.campaigns if c.game.name in never_games and campaign_active(c, now)),
                   key=lambda c: (c.ends_at, c.id))
    return StateOut(
        state=str(runner.state), signed_in=session is not None, login=session.login if session else None,
        paused_until=runner.paused_until, last_refresh=runner.last_refresh, current=current,
        needs_you=keep(plan.needs_you if plan else ()), up_next=up_next,
        needs_ignored=keep(plan.needs_ignored if plan else ()),
        priority_only=store.get_prefs().priority_only, outside=keep(plan.outside if plan else ()),
        done=keep(plan.done if plan else ()), catalog=_catalog(runner),
        last_switch=_switch(runner, now), next_check_at=runner.next_check_at,
        never=[campaign_out(c, now, None) for c in never],
        first_in_line=[o.name for o in keep(plan.waiting[:2])] if plan and not plan.current else [],
        streak_visit=(StreakVisitOut(channel=v[0], until=v[1])
                      if (v := getattr(runner, "streak_visit", None)) else None),
        points_watching=[PointsWatchOut(channel=ch.login, game=ch.game_name or None,
                                        since=runner.points_since.get(ch.login, now))
                         for ch in getattr(runner, "points_watching", ())],
    )


def _switch(runner, now: datetime) -> SwitchOut | None:
    sw = getattr(runner, "last_switch", None)
    if not sw or now - sw["at"] >= SWITCH_NOTICE_FOR:
        return None
    return SwitchOut(from_=sw["from"], to=sw["to"], at=sw["at"])


def _catalog(runner) -> CatalogOut | None:
    st = getattr(runner, "catalog_status", None)
    return CatalogOut(status=st[0], since=st[1]) if st else None


def history_view(claims: list[dict], missed: list[dict] = (), images=None) -> HistoryOut:
    """Flat and newest first. Day grouping is the page's job: only the browser knows the viewer's zone.
    Images point at Dropwatch's own copies once they are kept (images.py), else at Twitch."""
    claims, missed = [_kept(c, images) for c in claims], [_kept(m, images) for m in missed]
    out = [ClaimOut(at=row["at"], campaign_id=row["campaign_id"], campaign=row["campaign"], game=row["game"],
                    rewards=[RewardOut(**r) for r in row["rewards"]], minutes=row.get("minutes"),
                    channel=row.get("channel"), campaign_rewards=row.get("campaign_rewards"),
                    campaign_ends=row.get("campaign_ends"), box_art_url=row.get("box_art_url"))
           for row in claims]
    return HistoryOut(total_rewards=sum(len(c.rewards) for c in out), claims=out,
                      missed=[MissedOut(**m) for m in missed])


def _kept(row: dict, images) -> dict:
    """The row with each image URL swapped for the kept copy where there is one."""
    if images is None:
        return row
    from ..images import box_art_144

    art = row.get("box_art_url") or ""
    rewards = [{**r, "image_url": images.local_url(r["image_url"]) or r["image_url"]} for r in row["rewards"]]
    return {**row, "rewards": rewards, "box_art_url": images.local_url(box_art_144(art)) or art}

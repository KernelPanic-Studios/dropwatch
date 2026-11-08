"""Plain data and pure progress arithmetic.

Semantics are ported from reference/fireph-webui/inventory.py (TimedDrop, DropsCampaign):
drop-level time windows, precondition chains, and the 24 h claim grace period.
Nothing here reads the clock; callers pass `now`.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

SPECIAL_GAME_IDS = frozenset({509663, 509672})  # earnable on any channel (reference utils.Game)
BADGE_KINDS = frozenset({"BADGE", "EMOTE"})
CLAIM_GRACE = timedelta(hours=24)  # Twitch help: claimable until 24 h after the campaign ends


def game_slug(name: str) -> str:
    """Game name -> GQL directory slug. Verbatim rule from reference utils.Game.slug."""
    slug = re.sub(r"'", "", name.lower())
    slug = re.sub(r"\W+", "-", slug)
    return re.sub(r"-{2,}", "-", slug.strip("-"))


@dataclass(frozen=True)
class Game:
    id: int
    name: str
    slug: str
    box_art_url: str = ""

    @property
    def special(self) -> bool:
        return self.id in SPECIAL_GAME_IDS


@dataclass(frozen=True)
class Reward:
    id: str
    name: str
    image_url: str
    kind: str


@dataclass(frozen=True)
class Drop:
    id: str
    name: str
    rewards: tuple[Reward, ...]
    starts_at: datetime
    ends_at: datetime
    required_minutes: int
    current_minutes: int
    claimed: bool
    claim_id: str | None
    preconditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Campaign:
    id: str
    name: str
    game: Game
    starts_at: datetime
    ends_at: datetime
    linked: bool | None  # None: unknown (catalogue campaign not started yet; spec §4)
    link_url: str
    allowed_logins: tuple[str, ...]
    drops: tuple[Drop, ...]

    def drop(self, drop_id: str) -> Drop | None:
        return next((d for d in self.drops if d.id == drop_id), None)

    @property
    def has_badge_or_emote(self) -> bool:
        return any(r.kind in BADGE_KINDS for d in self.drops for r in d.rewards)

    def in_chain(self, drop_id: str) -> bool:
        return any(drop_id in d.preconditions for d in self.drops if not d.claimed)


@dataclass(frozen=True)
class LiveChannel:
    id: int
    login: str
    game_id: int | None
    viewers: int
    drops_enabled: bool
    broadcast_id: str
    game_name: str = ""


@dataclass(frozen=True)
class Prefs:
    priority: tuple[str, ...] = ()
    never: frozenset[str] = frozenset()
    favourites: tuple[str, ...] = ()
    mine_badges: bool = False
    pins: tuple[str, ...] = ()  # Up next "Arrange myself": campaign ids mined first after Priority
    ignored: frozenset[str] = frozenset()  # Needs you > Ignore: campaign ids not asked about until they end
    priority_only: bool = False  # Settings > Mining: mine only games in Priority (approved 2026-10-12)
    # Channel points page (2026-11-08): watched while live for their points, whatever drops are doing;
    # empty while points watching is switched off
    points_channels: tuple[str, ...] = ()


def preconditions_met(c: Campaign, d: Drop) -> bool:
    for pid in d.preconditions:
        pre = c.drop(pid)
        if pre is None or not pre.claimed:
            return False
    return True


def _earn_conditions(c: Campaign, d: Drop) -> bool:
    return (
        not d.claimed
        and d.required_minutes > 0
        and (bool(d.rewards) or c.in_chain(d.id))
    )


def drop_open(c: Campaign, d: Drop, now: datetime) -> bool:
    """Can still be earned at some point (window not over), ignoring preconditions."""
    return _earn_conditions(c, d) and now < d.ends_at


def drop_earnable_now(c: Campaign, d: Drop, now: datetime) -> bool:
    # A drop at full minutes but not yet claimed earns nothing more; claiming is the runner's job.
    return (
        _earn_conditions(c, d)
        and d.current_minutes < d.required_minutes
        and preconditions_met(c, d)
        and d.starts_at <= now < d.ends_at
    )


def account_eligible(c: Campaign, prefs: Prefs) -> bool:
    """Badge/emote campaigns need no account link but are opt-in (reference enable_badges_emotes)."""
    return prefs.mine_badges if c.has_badge_or_emote else c.linked is not False  # unknown counts


def total_remaining(c: Campaign, d: Drop) -> int:
    own = max(0, d.required_minutes - d.current_minutes)
    pre = [total_remaining(c, p) for pid in d.preconditions if (p := c.drop(pid)) is not None]
    return own + max(pre, default=0)


def campaign_active(c: Campaign, now: datetime) -> bool:
    return c.starts_at <= now < c.ends_at


def campaign_minutes_needed(c: Campaign, now: datetime) -> int:
    return max((total_remaining(c, d) for d in c.drops if drop_open(c, d, now)), default=0)


def campaign_ratio(c: Campaign, now: datetime) -> float:
    """Spare-time ratio: minutes until the drop ends / minutes still needed (min over open drops).

    Lower is more urgent. inf when nothing is left to earn.
    """
    ratios = []
    for d in c.drops:
        if not drop_open(c, d, now):
            continue
        need = total_remaining(c, d)
        if need <= 0:
            continue
        ratios.append(((d.ends_at - now).total_seconds() / 60) / need)
    return min(ratios, default=math.inf)


def deadline_verdict(ratio: float) -> str:
    if ratio < 1:
        return "wont_finish"
    if ratio < 2:
        return "tight"
    return "plenty"


def claimable(c: Campaign, d: Drop, now: datetime) -> bool:
    return d.claim_id is not None and not d.claimed and now < c.ends_at + CLAIM_GRACE


def with_drop(c: Campaign, drop: Drop) -> Campaign:
    return replace(c, drops=tuple(drop if d.id == drop.id else d for d in c.drops))

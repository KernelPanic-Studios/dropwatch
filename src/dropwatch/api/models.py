"""Request/response models. Field names are the contract phase 3's UI types are generated from."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from ..tz import zone_or_none


class RewardOut(BaseModel):
    name: str
    image_url: str


class DropOut(BaseModel):
    id: str
    name: str
    required_minutes: int
    current_minutes: int
    claimed: bool
    starts_at: datetime
    ends_at: datetime
    rewards: list[RewardOut]


class CampaignOut(BaseModel):
    id: str
    name: str
    game: str
    box_art_url: str
    ends_at: datetime
    linked: bool | None
    maybe_unlinked: bool = False
    link_url: str
    allowed_channels: list[str]
    minutes_needed: int
    verdict: str | None
    drops: list[DropOut]
    pinned: bool = False  # Up next "Arrange myself"
    # Up next only: at the queue's order, mined back to back, it would end before its turn (an estimate)
    ends_before_turn: bool = False
    new: bool = False  # first seen in the last 24 h (and not in Dropwatch's very first look)


class ChannelOut(BaseModel):
    login: str
    viewers: int
    favourite: bool


class CurrentOut(BaseModel):
    campaign: CampaignOut
    channel: ChannelOut
    reason: str
    channel_reason: str
    also_credited: list[str]
    channels: list[ChannelOut] = []  # other live channels that qualify (the "change" picker)


class SwitchOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field(alias="from")
    to: str
    at: datetime


class CatalogOut(BaseModel):
    status: str  # ok | stale | unreachable
    since: datetime | None


class StreakVisitOut(BaseModel):
    channel: str
    until: datetime


class PointsWatchOut(BaseModel):
    channel: str
    game: str | None
    since: datetime  # watched without a break since then


class StateOut(BaseModel):
    state: str
    signed_in: bool
    login: str | None
    paused_until: datetime | None
    last_refresh: datetime | None
    current: CurrentOut | None
    needs_you: list[CampaignOut]
    up_next: list[CampaignOut]
    done: list[CampaignOut]
    catalog: CatalogOut | None = None  # set when campaigns come from the public catalogue (TV login)
    last_switch: SwitchOut | None = None  # for 10 minutes after the channel changed
    next_check_at: datetime | None = None  # the runner's next Twitch refresh (or retry)
    never: list[CampaignOut] = []  # running campaigns of Never games: never mined, listed for their art
    needs_ignored: list[CampaignOut] = []  # Needs you campaigns hidden with Ignore, until they end
    priority_only: bool = False  # Settings > Mining: only Priority games are mined
    outside: list[CampaignOut] = []  # Priority only: what would be mined otherwise, in queue order
    first_in_line: list[str] = []  # idle: names of the next campaigns to mine once a channel goes live
    streak_visit: StreakVisitOut | None = None  # watching a favourite for its watch streak; drops wait
    points_watching: list[PointsWatchOut] = []  # Channel points: streamers watched alongside drops right now
    build: str = ""  # version+commit running; the page offers a reload when it changes


class StrictIn(BaseModel):
    """A request body: a misspelt or unknown field is an error, not silently ignored (polish 2026-10-12)."""
    model_config = ConfigDict(extra="forbid")


def _no_blanks(names: list[str]) -> list[str]:
    # blank entries are dropped; real names are kept exactly as given (Twitch's game names, trailing space
    # and all, are what the lists match on)
    return [n for n in names if n.strip()]


ListName = Annotated[str, Field(max_length=200)]
NameList = Annotated[list[ListName], AfterValidator(_no_blanks)]


class ListsIn(StrictIn):
    priority: NameList = Field(default_factory=list, max_length=200)
    never: NameList = Field(default_factory=list, max_length=200)
    favourites: NameList = Field(default_factory=list, max_length=200)


class PointsChannelsIn(StrictIn):
    channels: NameList = Field(default_factory=list, max_length=200)


class PointsChannelOut(BaseModel):
    login: str
    live: bool  # live now, as of the last refresh
    game: str | None  # what it is (or was last) streaming
    viewers: int | None  # while live
    last_seen: datetime | None  # last seen live; None if never seen
    watching: bool  # being watched for its points right now
    watching_since: datetime | None
    # this one is live but not watched: why ("drops" = the drop miner is on it, so it earns there;
    # "full" = Twitch counts two streams at once and both are taken by channels higher up the list)
    waiting: str | None = None
    points: int = 0  # gained on this channel in the last `days`, from anything Dropwatch watched
    chests: int = 0


class PointsPageOut(BaseModel):
    on: bool  # Settings' points_watch: off keeps the list but watches nothing
    paused: bool  # mining is paused, which pauses points watching too
    days: int  # the period the per-channel totals cover
    channels: list[PointsChannelOut]  # in the list's order
    points: int = 0  # gained on every channel in the period
    chests: int = 0


class Pins(BaseModel):
    pins: list[Annotated[str, Field(max_length=100)]] = Field(default_factory=list, max_length=200)


class IgnoredOut(BaseModel):
    ids: list[str]


class ListsOut(BaseModel):
    priority: list[str]
    never: list[str]
    favourites: list[str]


def _zone(v: str) -> str:
    if v and zone_or_none(v) is None:
        raise ValueError("not a time zone Dropwatch knows")
    return v


class SettingsIn(BaseModel):
    # StrictBool: pydantic's lax mode would turn "yes" or 1 into True
    mine_badges: StrictBool | None = None
    claim_points: StrictBool | None = None
    notify_signin: StrictBool | None = None
    notify_unreachable: StrictBool | None = None
    notify_not_earning: StrictBool | None = None
    notify_claim_failed: StrictBool | None = None
    notify_stopped: StrictBool | None = None
    notify_needs_you: StrictBool | None = None
    notify_unreachable_minutes: StrictInt | None = Field(default=None, ge=5, le=240)
    notify_not_earning_minutes: StrictInt | None = Field(default=None, ge=10, le=240)
    arrange_up_next: StrictBool | None = None
    notify_claimed: StrictBool | None = None
    notify_weekly: StrictBool | None = None
    notify_weekly_day: StrictInt | None = Field(default=None, ge=0, le=6)  # 0 = Monday
    notify_weekly_hour: StrictInt | None = Field(default=None, ge=0, le=23)
    notify_weekly_tz: Annotated[StrictStr, Field(max_length=64), AfterValidator(_zone)] | None = None
    campaigns_every_minutes: Literal[15, 30, 60, 120, 240] | None = None  # the choices Settings offers
    points_watch_streak: StrictBool | None = None
    priority_only: StrictBool | None = None
    points_watch: StrictBool | None = None
    model_config = ConfigDict(extra="forbid")  # a misspelt or retired setting is an error, not a no-op


class SettingsOut(BaseModel):
    mine_badges: bool
    claim_points: bool
    notify_signin: bool
    notify_unreachable: bool
    notify_not_earning: bool
    notify_claim_failed: bool
    notify_stopped: bool
    notify_needs_you: bool
    notify_unreachable_minutes: int
    notify_not_earning_minutes: int
    arrange_up_next: bool
    notify_claimed: bool
    notify_weekly: bool
    notify_weekly_day: int
    notify_weekly_hour: int
    notify_weekly_tz: str
    campaigns_every_minutes: int
    points_watch_streak: bool
    priority_only: bool
    points_watch: bool


class ActivityEvent(BaseModel):
    at: datetime
    kind: str  # started | state | switched | claimed | claim_failed | needs_you | channel_dropped |
    #            points_claimed | points_claim_failed | notified
    data: dict[str, str | bool | int | float | list[str] | None]


class ActivityOut(BaseModel):
    events: list[ActivityEvent]  # newest first
    kept_days: int


class SessionOut(BaseModel):
    id: str
    device: str  # e.g. "Chrome on Windows", from the browser's user agent
    created_at: datetime | None
    last_seen_at: datetime | None
    current: bool  # this browser


class SessionsOut(BaseModel):
    sessions: list[SessionOut]


class RestoreOut(BaseModel):
    skipped: list[str]  # what a newer Dropwatch wrote that this one doesn't know


class AboutOut(BaseModel):
    version: str
    commit: str | None  # "branch@sha", None when unknown
    started_at: datetime
    campaigns_at: datetime | None  # when the campaign list was last read from Twitch
    server_tz: str  # what "" means for the weekly summary's zone


class NotifyFieldOut(BaseModel):
    key: str
    label: str
    secret: bool
    value: str  # always "" for a secret: the page only learns whether it is set
    set: bool


class NotifyChannelOut(BaseModel):
    type: str
    name: str
    configured: bool
    summary: str
    hint: str
    fields: list[NotifyFieldOut]


class NotifyKind(BaseModel):
    type: str
    name: str


class NotifyChannelsOut(BaseModel):
    channels: list[NotifyChannelOut]  # added ones, in the order they were added
    available: list[NotifyKind]  # the "Add a channel" menu: the rest


class NotifyChannelIn(StrictIn):
    values: dict[str, str] = Field(default_factory=dict, max_length=5)  # only the fields given change


class NotifyResult(BaseModel):
    type: str
    name: str
    ok: bool
    message: str


class NotifyTestOut(BaseModel):
    ok: bool
    message: str
    results: list[NotifyResult]


class PasswordIn(StrictIn):
    password: str = Field(max_length=200)


class PauseIn(StrictIn):
    minutes: int | None = Field(default=None, ge=1, le=1440)


class MineNowIn(StrictIn):
    campaign_id: str = Field(min_length=1, max_length=100)


class ChannelIn(StrictIn):
    login: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_]+$")


class ClaimOut(BaseModel):
    at: datetime
    campaign_id: str
    campaign: str
    game: str
    rewards: list[RewardOut]
    # None when not recorded (claims from before 2026-10-10, or a claim made right after a restart)
    minutes: int | None = None  # watch time the drop needed
    channel: str | None = None  # the channel it was mined on
    campaign_rewards: int | None = None  # rewards in the whole campaign
    campaign_ends: datetime | None = None
    box_art_url: str | None = None  # saved with the claim: History keeps it after the campaign ends


class MissedReward(BaseModel):
    name: str
    image_url: str
    claimed: bool


class MissedOut(BaseModel):
    campaign_id: str
    name: str
    game: str
    box_art_url: str
    link_url: str
    ends_at: datetime
    # never_list | dropwatch_off | not_linked | ran_out_of_time | no_live_channels | priority_only | outranked
    reason: str
    rewards: list[MissedReward]
    rewards_total: int
    rewards_claimed: int
    minutes_watched: int
    started: bool  # earned any minutes: shown as a full row; the rest fold away with the Never ones
    priority: bool
    pinned: bool


class PointsOut(BaseModel):
    points: int = 0  # channel points gained in the period (every gain Twitch reported)
    chests: int = 0  # bonus chests opened


class HistoryOut(BaseModel):
    total_rewards: int
    claims: list[ClaimOut]  # newest first; the page groups by the viewer's local day
    missed: list[MissedOut] = []  # campaigns that ended in the period with rewards left, newest first
    points: PointsOut = PointsOut()


class SignInStatus(BaseModel):
    status: str  # idle | waiting | done | expired | failed
    message: str = ""
    code: str | None = None  # the 8 letters to enter at verification_uri
    verification_uri: str | None = None
    expires_at: datetime | None = None


class MeOut(BaseModel):
    authenticated: bool
    setup_required: bool


class ChannelSuggestion(BaseModel):
    login: str
    live: bool  # live now with drops on, as of the last refresh
    game: str | None  # what it is (or was last) streaming
    last_seen: datetime | None  # last seen live; None if never seen (a favourite added by name)


class SuggestionsOut(BaseModel):
    games: list[str]
    channels: list[ChannelSuggestion]  # live first, then most recently seen, then never-seen favourites

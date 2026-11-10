"""FastAPI application: public auth routes plus the session-protected API (spec §8)."""
from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..backup import BadBackup, make_backup, restore_backup
from ..notify import CHANNELS, configured, send_all, summary
from ..runner import TWITCH_ERRORS, State
from ..store import EVENT_RETENTION
from ..version import VERSION, build_info, server_tz
from .auth import COOKIE, LoginLimiter, private_auth, public, require_session
from .models import (
    AboutOut,
    ActivityEvent,
    ActivityOut,
    ChannelIn,
    ChannelLookupOut,
    ChannelSuggestion,
    HistoryOut,
    IgnoredOut,
    ListsIn,
    ListsOut,
    MineNowIn,
    NotifyChannelIn,
    NotifyChannelOut,
    NotifyChannelsOut,
    NotifyFieldOut,
    NotifyKind,
    NotifyResult,
    NotifyTestOut,
    PauseIn,
    Pins,
    PointsChannelOut,
    PointsChannelsIn,
    PointsOut,
    PointsPageOut,
    RestoreOut,
    SessionOut,
    SessionsOut,
    SettingsIn,
    SettingsOut,
    SignInStatus,
    StateOut,
    SuggestionsOut,
)
from .sse import sse_stream
from .views import history_view, state_view

api = APIRouter(prefix="/api", dependencies=[Depends(require_session)])


@dataclass
class AppContext:
    store: object
    bus: object
    service: object
    signin: object
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    post: object = None  # notify's HTTP post; None = a real aiohttp session per send (tests inject a fake)
    images: object = None  # images.ImageCache: History's kept copies (None: Twitch's links only)
    started_at: datetime | None = None  # set by create_app




def _c(request: Request) -> AppContext:
    return request.app.state.ctx


@api.get("/state", response_model=StateOut)
async def get_state(request: Request) -> StateOut:
    ctx = _c(request)
    out = state_view(ctx.service.runner, ctx.store, ctx.clock())
    out.build = f"{VERSION}+{build_info() or 'unknown'}"
    return out


def _lists(ctx) -> ListsOut:
    p = ctx.store.get_prefs()
    return ListsOut(priority=list(p.priority), never=sorted(p.never), favourites=list(p.favourites))


@api.get("/lists", response_model=ListsOut)
async def get_lists(request: Request) -> ListsOut:
    return _lists(_c(request))


@api.put("/lists", response_model=ListsOut)
async def put_lists(body: ListsIn, request: Request) -> ListsOut:
    clash = set(body.priority) & set(body.never)
    if clash:
        raise HTTPException(status_code=422, detail=f"In both Priority and Never: {', '.join(sorted(clash))}")
    ctx = _c(request)
    ctx.store.set_lists(body.priority, set(body.never), body.favourites)
    if ctx.service.runner is not None:
        await ctx.service.runner.replan()  # takes effect now, not at the next 5-minute refresh
    return _lists(ctx)


@api.get("/suggestions", response_model=SuggestionsOut)
async def get_suggestions(request: Request) -> SuggestionsOut:
    ctx = _c(request)
    r = ctx.service.runner
    games = sorted({c.game.name for c in r.campaigns}) if r else []
    live = {ch.login: ch.game_name or None for ch in r.live} if r else {}
    seen = {row["login"]: row for row in ctx.store.seen_channels(ctx.clock())}
    out = [ChannelSuggestion(login=lg, live=True, game=g, last_seen=seen.get(lg, {}).get("last_seen"))
           for lg, g in sorted(live.items())]
    favs = ctx.store.get_prefs().favourites
    named = dict.fromkeys((*favs, *ctx.store.get_points_channels()))  # added by name, maybe never seen
    offline = [lg for lg in seen if lg not in live]  # newest first
    keep = set(offline[:SEEN_SUGGESTIONS]) | set(named)  # a long tail of offline channels isn't useful
    out += [ChannelSuggestion(login=lg, live=False, game=seen[lg]["game"] or None,
                              last_seen=seen[lg]["last_seen"]) for lg in offline if lg in keep]
    known = {c.login for c in out}
    out += [ChannelSuggestion(login=f, live=False, game=None, last_seen=None) for f in named
            if f not in known]
    return SuggestionsOut(games=games, channels=out)


# what Activity shows of each logged event: anything else stays in the database
ACTIVITY_FIELDS = {
    "started": ("version", "commit"),
    "state": ("state", "error"),
    "switched": ("from", "to", "campaign", "game", "reason", "channel_reason", "from_live"),
    "claimed": ("campaign", "reward", "game"),
    "claim_failed": ("campaign",),
    "needs_you": ("campaign", "reason"),
    "channel_dropped": ("channel",),
    "points_claimed": ("channel",),
    "points_claim_failed": ("channel",),
    "notified": ("title", "sent", "failed"),
    "checked": ("manual", "campaigns", "new", "linked", "seconds"),
    "points_earned": ("channel", "reason", "points"),
    "points_watch": ("channel", "on", "game"),
    "points_dropped": ("channel",),
}


@api.get("/activity", response_model=ActivityOut)
async def get_activity(request: Request) -> ActivityOut:
    rows = _c(request).store.recent_events(None)  # the whole kept week: the page says "Kept for 7 days"
    return ActivityOut(kept_days=EVENT_RETENTION.days, events=[
        ActivityEvent(at=at, kind=kind, data={k: data[k] for k in ACTIVITY_FIELDS[kind] if k in data})
        for kind, at, data in rows if kind in ACTIVITY_FIELDS])


@api.get("/backup")
async def get_backup(request: Request, secrets: bool = False) -> JSONResponse:
    """Settings › Backup: a file to keep. Notification secrets only when asked for."""
    ctx = _c(request)
    now = ctx.clock()
    return JSONResponse(make_backup(ctx.store, now, secrets=secrets), headers={
        "Content-Disposition": f'attachment; filename="dropwatch-backup-{now:%Y-%m-%d}.json"',
        "Cache-Control": "no-store"})


@api.post("/restore", response_model=RestoreOut)
async def post_restore(request: Request) -> RestoreOut:
    """Replaces lists, pins, settings and notification channels with a backup's. The whole file is checked
    before anything is written."""
    ctx = _c(request)
    # JSON only: a text/plain POST needs no CORS preflight, so another web app on this host could send one
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Send the backup as application/json.")
    try:
        data = await request.json()
    except ValueError as e:
        raise HTTPException(422, "That file isn't a Dropwatch backup.") from e
    try:
        skipped = restore_backup(ctx.store, data)
    except BadBackup as e:
        raise HTTPException(422, str(e)) from e
    if ctx.service.runner is not None:
        await ctx.service.runner.replan()
    return RestoreOut(skipped=skipped)


def _device(ua: str) -> str:
    """A rough "Browser on OS" from a user agent; good enough to tell your own browsers apart."""
    if not ua:
        return "Older sign-in (no details kept)"  # signed in before the list existed (2026-10-11)
    os_ = next((name for key, name in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                                         ("Windows", "Windows"), ("Mac OS X", "Mac"), ("CrOS", "ChromeOS"),
                                         ("Linux", "Linux")) if key in ua), None)
    browsers = (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"),
                ("Safari/", "Safari"))
    browser = next((name for key, name in browsers if key in ua), None)
    if browser and os_:
        return f"{browser} on {os_}"
    return browser or os_ or "Unknown browser"


@api.get("/sessions", response_model=SessionsOut)
async def get_sessions(request: Request) -> SessionsOut:
    """Settings: the browsers signed in to this page."""
    ctx = _c(request)
    mine = ctx.store.session_hash(request.cookies.get(COOKIE, ""))
    rows = ctx.store.web_sessions(ctx.clock())
    out = [SessionOut(id=r["id"], device=_device(r["user_agent"]), created_at=r["created_at"],
                      last_seen_at=r["last_seen_at"], current=r["hash"] == mine) for r in rows]
    out.sort(key=lambda s: not s.current)  # this browser first
    return SessionsOut(sessions=out)


@api.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request) -> None:
    if not _c(request).store.delete_web_session_by_id(session_id):
        raise HTTPException(404, "No browser like that is signed in.")


@api.post("/sessions/sign-out-others", status_code=204)
async def sign_out_others(request: Request) -> None:
    _c(request).store.delete_other_web_sessions(request.cookies.get(COOKIE, ""))


@api.get("/about", response_model=AboutOut)
async def about(request: Request) -> AboutOut:
    ctx = _c(request)
    runner = ctx.service.runner
    return AboutOut(version=VERSION, commit=build_info(), started_at=ctx.started_at,
                    campaigns_at=runner.campaigns_at if runner else None, server_tz=server_tz())


@api.get("/settings", response_model=SettingsOut)
async def get_settings(request: Request) -> SettingsOut:
    return SettingsOut(**_c(request).store.get_settings())


# settings the planner reads (store.get_prefs): changing one re-plans at once
PLANNER_SETTINGS = {"arrange_up_next", "mine_badges", "claim_points", "points_watch_streak", "priority_only",
                    "points_watch"}


@api.put("/settings", response_model=SettingsOut)
async def put_settings(body: SettingsIn, request: Request) -> SettingsOut:
    values = body.model_dump(exclude_none=True)
    ctx = _c(request)
    out = SettingsOut(**ctx.store.put_settings(values))
    # settings the planner reads take effect now, not at the next 5-minute refresh
    if values.keys() & PLANNER_SETTINGS and ctx.service.runner is not None:
        if values.get("points_watch"):  # the list's streamers weren't looked up while it was off
            await ctx.service.runner.refresh()
        else:
            await ctx.service.runner.replan()
    return out


def _channels(ctx) -> NotifyChannelsOut:
    added = ctx.store.get_channels()
    out = []
    for kind, values in added.items():
        spec = CHANNELS.get(kind)
        if spec is None:
            continue
        out.append(NotifyChannelOut(
            type=kind, name=spec.name, configured=configured(kind, values), summary=summary(kind, values),
            hint=spec.hint,
            fields=[NotifyFieldOut(key=f.key, label=f.label, secret=f.secret,
                                    value="" if f.secret else values.get(f.key, ""),
                                    set=bool((values.get(f.key) or "").strip())) for f in spec.fields]))
    return NotifyChannelsOut(channels=out, available=[NotifyKind(type=k, name=c.name)
                                                for k, c in CHANNELS.items() if k not in added])


@api.get("/notify/channels", response_model=NotifyChannelsOut)
async def get_channels(request: Request) -> NotifyChannelsOut:
    return _channels(_c(request))


@api.put("/notify/channels/{kind}", response_model=NotifyChannelsOut)
async def put_channel(kind: str, body: NotifyChannelIn, request: Request) -> NotifyChannelsOut:
    """Adds the channel if new; changes only the fields given ("" clears one)."""
    spec = CHANNELS.get(kind)
    if spec is None:
        raise HTTPException(404, f"No channel called {kind}.")
    keys = {f.key for f in spec.fields}
    for k, v in body.values.items():
        if k not in keys:
            raise HTTPException(422, f"{spec.name} has no field {k}.")
        if len(v) > 500:
            raise HTTPException(422, "That value is too long.")
    ctx = _c(request)
    ctx.store.put_channel(kind, {k: v.strip() for k, v in body.values.items()})
    return _channels(ctx)


@api.delete("/notify/channels/{kind}", response_model=NotifyChannelsOut)
async def delete_channel(kind: str, request: Request) -> NotifyChannelsOut:
    ctx = _c(request)
    ctx.store.delete_channel(kind)
    return _channels(ctx)


@api.post("/notify/test", response_model=NotifyTestOut)
async def notify_test(request: Request) -> NotifyTestOut:
    """Settings' "Send test notification": every set-up channel, one result each."""
    ctx = _c(request)
    results = await send_all(ctx.store.get_channels(), "Dropwatch: Test notification",
                             "If you can read this, Dropwatch can reach you.", ctx.post)
    if not results:
        return NotifyTestOut(ok=False, message="Add a channel first.", results=[])
    sent = [r["name"] for r in results if r["ok"]]
    failed = [r["message"] for r in results if not r["ok"]]
    parts = []
    if sent:
        names = " and ".join(sent) if len(sent) < 3 else ", ".join(sent[:-1]) + " and " + sent[-1]
        parts.append(f"Sent to {names}.")
    if failed:
        parts.append("Failed: " + "; ".join(failed) + ".")
    return NotifyTestOut(ok=not failed, message=" ".join(parts), results=[NotifyResult(**r) for r in results])


CampaignId = Annotated[str, PathParam(max_length=100)]


@api.post("/needs/ignored/{campaign_id}", response_model=IgnoredOut)
async def ignore_needs(campaign_id: CampaignId, request: Request) -> IgnoredOut:
    """Needs you > Ignore: stop asking about this campaign (page, alert, weekly summary) until it ends.
    One id per call, so Undo reverses only its own change."""
    ctx = _c(request)
    ctx.store.set_ignored([*ctx.store.get_ignored(), campaign_id][-200:])  # ids never seen are never pruned
    if ctx.service.runner is not None:
        await ctx.service.runner.replan()
    return IgnoredOut(ids=ctx.store.get_ignored())


@api.delete("/needs/ignored/{campaign_id}", response_model=IgnoredOut)
async def unignore_needs(campaign_id: CampaignId, request: Request) -> IgnoredOut:
    ctx = _c(request)
    ctx.store.set_ignored([i for i in ctx.store.get_ignored() if i != campaign_id])
    if ctx.service.runner is not None:
        await ctx.service.runner.replan()
    return IgnoredOut(ids=ctx.store.get_ignored())


@api.get("/pins", response_model=Pins)
async def get_pins(request: Request) -> Pins:
    return Pins(pins=_c(request).store.get_pins())


@api.put("/pins", response_model=Pins)
async def put_pins(body: Pins, request: Request) -> Pins:
    """Up next "Arrange myself": the pinned campaigns, in order (they count while the switch is on)."""
    ctx = _c(request)
    ctx.store.set_pins(body.pins)
    if ctx.service.runner is not None:
        await ctx.service.runner.replan()
    return Pins(pins=ctx.store.get_pins())


@api.get("/img/{name}", include_in_schema=False)
async def kept_image(name: str, request: Request):
    """A kept copy of a Twitch image (images.py); named by a hash of its URL, so it never changes."""
    images = _c(request).images
    f = images.file(name) if images is not None else None
    if f is None:
        raise HTTPException(404, "No such image.")
    from ..images import TYPES

    return FileResponse(f, media_type=TYPES[f.suffix],
                        headers={"Cache-Control": "private, max-age=31536000, immutable"})


@api.get("/history", response_model=HistoryOut)
async def get_history(request: Request, days: int = Query(30, ge=1, le=365)) -> HistoryOut:
    ctx = _c(request)
    now = ctx.clock()
    since = now - timedelta(days=days)
    out = history_view(ctx.store.claims_since(since), ctx.store.missed_between(since, now), ctx.images)
    out.points = PointsOut(**ctx.store.points_since(since))
    return out


def _runner(ctx):
    r = ctx.service.runner
    if r is None or r.state == State.SIGNED_OUT:
        raise HTTPException(status_code=409, detail="Not signed in to Twitch.")
    return r


@api.post("/pause", status_code=204)
async def pause(body: PauseIn, request: Request) -> None:
    ctx = _c(request)
    until = ctx.clock() + timedelta(minutes=body.minutes) if body.minutes else None
    _runner(ctx).pause(until)


@api.post("/resume", status_code=204)
async def resume(request: Request) -> None:
    r = _runner(_c(request))
    r.resume()
    await r.replan()  # points watching starts again now, not at the next refresh


def _points_page(ctx, days: int) -> PointsPageOut:
    r = ctx.service.runner
    now = ctx.clock()
    on = bool(ctx.store.get_settings()["points_watch"])
    live = {ch.login: ch for ch in r.live} if r else {}
    seen = {row["login"]: row for row in ctx.store.seen_channels(now)}
    totals = ctx.store.points_by_channel(now - timedelta(days=days))
    watching = {ch.login for ch in r.points_watching} if r else set()
    since = r.points_since if r else {}
    waiting = r.points_waiting if r else {}
    channels = []
    for lg in ctx.store.get_points_channels():
        ch, row, t = live.get(lg), seen.get(lg, {}), totals.get(lg, {})
        channels.append(PointsChannelOut(
            login=lg, live=ch is not None, game=(ch.game_name if ch else row.get("game")) or None,
            viewers=ch.viewers if ch else None, last_seen=row.get("last_seen"),
            watching=lg in watching, watching_since=since.get(lg) if lg in watching else None,
            waiting=waiting.get(lg) if on and ch is not None else None,
            points=t.get("points", 0), chests=t.get("chests", 0)))
    sums = ctx.store.points_since(now - timedelta(days=days))
    return PointsPageOut(on=on, paused=bool(r and r.state == State.PAUSED), days=days, channels=channels,
                         points=sums["points"], chests=sums["chests"])


TWITCH_LOGIN = r"^[A-Za-z0-9_]{1,25}$"


@api.get("/channels/lookup", response_model=ChannelLookupOut)
async def lookup_channel(request: Request,
                         login: str = Query(..., pattern=TWITCH_LOGIN)) -> ChannelLookupOut:
    """The add boxes' check: is there a Twitch channel by this name, and is it live? Asks Twitch now."""
    try:
        found = await _runner(_c(request)).lookup_channel(login.lower())
    except TWITCH_ERRORS as exc:
        raise HTTPException(status_code=502, detail="Couldn't reach Twitch to check that name.") from exc
    if found is None:
        return ChannelLookupOut(login=login.lower(), found=False)
    return ChannelLookupOut(found=True, **found)


@api.get("/points", response_model=PointsPageOut)
async def get_points(request: Request, days: int = Query(30, ge=1, le=365)) -> PointsPageOut:
    """The Channel points page: the list, who is live and watched, and what each one earned."""
    return _points_page(_c(request), days)


@api.put("/points/channels", response_model=PointsPageOut)
async def put_points_channels(body: PointsChannelsIn, request: Request,
                              days: int = Query(30, ge=1, le=365)) -> PointsPageOut:
    ctx = _c(request)
    before = set(ctx.store.get_points_channels())
    ctx.store.set_points_channels(body.channels)
    r = ctx.service.runner
    if r is not None and r.state != State.SIGNED_OUT:
        if set(ctx.store.get_points_channels()) - before:
            await r.refresh()  # a newly added streamer may be live already: look now
        else:
            await r.replan()
    return _points_page(ctx, days)


@api.post("/mine-now", status_code=204)
async def mine_now(body: MineNowIn, request: Request) -> None:
    ctx = _c(request)
    r = _runner(ctx)
    camp = next((c for c in r.campaigns if c.id == body.campaign_id), None)
    if camp is None:
        raise HTTPException(status_code=404, detail="No such campaign.")
    prefs = ctx.store.get_prefs()
    if prefs.priority_only and camp.game.name not in prefs.priority:
        raise HTTPException(status_code=409, detail=f"Priority only is on: add {camp.game.name} to Priority "
                            "to mine it.")
    r.mine_now(body.campaign_id)
    await r.replan()
    if not (r.plan and r.plan.current and r.plan.current.campaign_id == body.campaign_id):
        raise HTTPException(status_code=409, detail="Can't mine that campaign right now: it needs a linked "
                            "account, a live channel, or it's on your Never list.")


@api.post("/channel", status_code=204)
async def channel(body: ChannelIn, request: Request) -> None:
    r = _runner(_c(request))
    login = body.login.lower()
    if not any(ch.login == login for ch in r.live):
        raise HTTPException(status_code=404, detail="That channel isn't live with drops right now.")
    r.use_channel(login)
    await r.replan()
    if not (r.watching and r.watching.login == login):
        raise HTTPException(status_code=409, detail="That channel can't earn the campaign being mined.")


def session_alive(ctx: AppContext, token: str | None) -> Callable[[], bool]:
    """For the live-event stream: is this browser's page session still valid? (signed out, here or from
    another browser, or expired: the stream ends)"""
    return lambda: ctx.store.valid_web_session(token, ctx.clock())


@api.get("/events")
async def events(request: Request) -> StreamingResponse:
    ctx = _c(request)
    return StreamingResponse(sse_stream(ctx.bus, request.is_disconnected,
                                        allowed=session_alive(ctx, request.cookies.get(COOKIE))),
                             media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@api.post("/streak/end", status_code=204)
async def end_streak(request: Request) -> None:
    """Stop a watch-streak visit and go back to drops now."""
    await _runner(_c(request)).end_streak_visit()


@api.post("/refresh", status_code=204)
async def check_now(request: Request) -> None:
    """The idle card's "Check now": re-read campaigns and live channels immediately."""
    await _runner(_c(request)).refresh(force_campaigns=True, manual=True)


@api.post("/twitch/signin", status_code=202, response_model=SignInStatus)
async def signin_start(request: Request) -> SignInStatus:
    status = await _c(request).signin.start()
    if status is None:
        raise HTTPException(status_code=409, detail="A sign-in is already waiting for its code.")
    return SignInStatus(**status)


@api.get("/twitch/signin", response_model=SignInStatus)
async def signin_status(request: Request) -> SignInStatus:
    return SignInStatus(**_c(request).signin.status())


@api.delete("/twitch/signin", status_code=204)
async def signin_cancel(request: Request) -> None:
    _c(request).signin.cancel()


@api.post("/twitch/signout", status_code=204)
async def signout(request: Request) -> None:
    ctx = _c(request)
    await ctx.service.stop()
    ctx.store.clear_session()
    ctx.signin.reset()
    ctx.bus.publish("signin", {"status": "signed_out", "message": ""})


# Private names nobody can own in public DNS: reserved (.local mDNS, .home.arpa, .internal, .localhost) or
# never delegated and commonly used by home routers (.lan, .home, .localdomain)
LOCAL_SUFFIXES = (".local", ".home.arpa", ".internal", ".localhost", ".lan", ".home", ".localdomain")


class HostCheck:
    """Answer to an IP address, a local name, or a name listed in DROPWATCH_HOSTS.

    A web page elsewhere can point its own domain at this box's LAN address (DNS rebinding) and then
    talk to it as same-origin; the one thing it can't fake is the Host header, which still carries
    its domain. That domain is a public one the attacker owns, so it has a dot and a real top-level
    domain: bare server names (tower, nhomeserver) and private suffixes can't be it and need no listing
    (2026-10-11). Refusing other names keeps first-run setup and the login out of its reach; a reverse
    proxy's public name is the one thing DROPWATCH_HOSTS is still for."""

    def __init__(self, app, hosts: Iterable[str]) -> None:
        self.app = app
        self.hosts = {h.strip().lower().rstrip(".") for h in hosts if h.strip()}

    def allowed(self, host: str) -> bool:
        if "*" in self.hosts:
            return True
        host = host.strip().lower()
        if host.startswith("["):  # [v6]:port
            name = host[1:host.find("]")] if "]" in host else ""
        else:
            name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        name = name.rstrip(".")
        if not name:
            return False
        try:
            ipaddress.ip_address(name)
            return True
        except ValueError:
            pass
        return "." not in name or name.endswith(LOCAL_SUFFIXES) or name == "localhost" or name in self.hosts

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            host = next((v.decode("latin-1") for k, v in scope["headers"] if k == b"host"), "")
            if not self.allowed(host):
                name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
                body = (f"Dropwatch doesn't answer to the name '{name}' unless it's listed. Add it to "
                        "DROPWATCH_HOSTS (comma-separated) and restart, or open Dropwatch by IP address or "
                        "its local name.\n").encode()
                await send({"type": "http.response.start", "status": 400,
                            "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                                        (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def create_app(ctx: AppContext, web_dir: Path | None = None, hosts: Iterable[str] = ()) -> FastAPI:
    # the schema isn't served: `dropwatch openapi` builds it from app.openapi() for the page's types
    app = FastAPI(title="Dropwatch", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(HostCheck, hosts=list(hosts))
    app.state.ctx = ctx
    if ctx.started_at is None and ctx.store is not None:
        ctx.started_at = ctx.clock()
    app.state.login_limiter = LoginLimiter()
    app.state.login_lock = asyncio.Lock()
    app.include_router(public)
    app.include_router(private_auth)
    app.include_router(api)
    if web_dir is not None and (web_dir / "index.html").is_file():
        _serve_web(app, web_dir)
    return app


SEEN_SUGGESTIONS = 300  # offline channels offered in the favourites add box (most recent first)
NO_CACHE = {"Cache-Control": "no-cache"}  # a rebuilt page must not be served from a stale cache


def _serve_web(app: FastAPI, web_dir: Path) -> None:
    """The built page (web/dist): its assets, and index.html for every other non-API path."""
    if (web_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")
    index = web_dir / "index.html"
    root = web_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def page(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        # never hand a network path (\host\share, //host, c:) to the filesystem: on Windows that
        # would open an SMB connection to whoever named it
        if not path or path.startswith("/") or "\\" in path or ":" in path:
            return FileResponse(index, headers=NO_CACHE)
        # all handlers stay async (one event loop owns the store and runner); these checks are on
        # small local files, so the blocking cost is negligible
        f = (web_dir / path).resolve()  # noqa: ASYNC240
        if f.is_relative_to(root) and f.is_file():  # noqa: ASYNC240
            return FileResponse(f)
        return FileResponse(index, headers=NO_CACHE)

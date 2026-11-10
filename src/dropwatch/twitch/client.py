"""Twitch reads and writes the runner needs, built on Gql + parse."""
from __future__ import annotations

import logging
from datetime import datetime

from ..models import (
    Campaign,
    LiveChannel,
    Prefs,
    account_eligible,
    campaign_active,
    drop_earnable_now,
)
from ..planner import qualifies
from . import parse
from .gql import GqlError, op

log = logging.getLogger("dropwatch.client")


class TwitchClient:
    def __init__(self, gql, user_id: int, catalog=None):
        self._gql, self._user_id = gql, user_id
        self.catalog = catalog  # campaign list when Twitch hides it (TV login, spec §4)

    async def campaigns(self) -> list[Campaign]:
        inv = await self._gql.run(op("Inventory"))
        claimed = parse.claimed_benefits(inv)
        data = parse.inventory_campaigns(inv)
        dash = parse.dashboard_campaigns(await self._gql.run(op("Campaigns")))
        if dash:
            ids = list(dash)
            details = await self._gql.run_many(
                [op("CampaignDetails", channelLogin=str(self._user_id), dropID=i) for i in ids])
            fetched = {}
            for item in details:
                dc = ((item.get("data") or {}).get("user") or {}).get("dropCampaign")
                if dc:
                    fetched[dc["id"]] = parse.merge(dash.get(dc["id"], {}), dc)
            data = parse.merge(data, fetched)
        elif self.catalog is not None:
            # the TV login sees no dashboard: discover from the catalogue, the account's Inventory wins
            data = parse.merge(data, await self.catalog.campaigns())
        out = []
        for raw in data.values():
            try:
                c = parse.to_campaign(raw, claimed)
            except (KeyError, TypeError, ValueError) as exc:
                log.warning("Skipping campaign %s: unexpected shape (%s)", raw.get("id"), exc)
                continue
            if c is not None:
                out.append(c)
        return out

    async def live_channels(
        self, campaigns: list[Campaign], prefs: Prefs, now: datetime
    ) -> list[LiveChannel]:
        # Only campaigns the planner could actually pick: active, not Never, account-eligible,
        # with a drop earnable now.
        minable = [c for c in campaigns
                   if campaign_active(c, now) and c.game.name not in prefs.never
                   and account_eligible(c, prefs)
                   and any(drop_earnable_now(c, d, now) for d in c.drops)]
        seen: dict[str, LiveChannel] = {}
        # Every minable game's directory (drops on), batched: GQL_BATCH per request, posts in parallel under
        # the rate limit. One request per game took 13-38 s for ~57 games on 2026-10-10; batched ~1 s.
        games = list({c.game.id: c.game for c in minable}.values())
        drops_on = {"systemFilters": ["DROPS_ENABLED"]}
        lookups = [op("GameDirectory", slug=g.slug, options=drops_on) for g in games]
        resps = await self._gql.run_many(lookups) if lookups else []
        for game, resp in zip(games, resps, strict=True):
            for ch in parse.directory_channels(resp, game):
                seen.setdefault(ch.login, ch)
        # A channel-restricted campaign can only be mined on an allowed channel streaming its game with drops
        # on, which that game's directory lists (top channels by viewers, so its best pick is there too). Ask
        # by name only for campaigns the directory found none for, and always for special-event campaigns,
        # whose channels may stream any game. 2026-10-10: every allowed name (2,430 in 122 requests) took
        # 24 s; this took 3.5 s and left the same 65 campaigns minable.
        found = list(seen.values())
        ask = [c for c in minable if c.allowed_logins
               and (c.game.special or not any(qualifies(c, ch) for ch in found))]
        acl = {lg for c in ask for lg in c.allowed_logins} - set(seen)
        # favourites, and the Channel points list, which is watched whatever they stream
        acl |= (set(prefs.favourites) | set(prefs.points_channels)) - set(seen)
        if acl:
            for resp in await self._gql.run_many([op("GetStreamInfo", channel=lg) for lg in sorted(acl)]):
                ch = parse.stream_channel(resp)
                if ch is not None:
                    seen.setdefault(ch.login, ch)
        return list(seen.values())

    async def lookup_channel(self, login: str) -> dict | None:
        """A channel by login, live or not (the add boxes' check); None when Twitch has no such user."""
        resp = await self._gql.run(op("GetStreamInfo", channel=login))
        user = (resp.get("data") or {}).get("user") if isinstance(resp, dict) else None
        if not user or not user.get("login"):
            return None
        game = (user.get("broadcastSettings") or {}).get("game") or {}
        return {"login": user["login"].lower(), "display_name": user.get("displayName") or user["login"],
                "live": bool(user.get("stream")), "game": game.get("displayName") or game.get("name") or None}

    async def claim(self, claim_id: str) -> bool:
        try:
            resp = await self._gql.run(op("ClaimDrop", input={"dropInstanceID": claim_id}))
        except GqlError as exc:
            log.warning("Claim failed: %s", exc)
            return False
        result = (resp.get("data") or {}).get("claimDropRewards")
        return bool(result) and result.get("status") in (
            "ELIGIBLE_FOR_ALL", "DROP_INSTANCE_ALREADY_CLAIMED")

    async def waiting_points_claim(self, login: str) -> tuple[int, str] | None:
        """(channel id, claim id) when a channel points bonus chest is waiting for us on that channel."""
        resp = await self._gql.run(op("ChannelPointsContext", channelLogin=login))
        ch = ((resp.get("data") or {}).get("community") or {}).get("channel") or {}
        claim = (((ch.get("self") or {}).get("communityPoints") or {}).get("availableClaim") or {})
        return (int(ch["id"]), claim["id"]) if claim.get("id") and ch.get("id") else None

    async def waiting_points_claims(self, logins: list[str]) -> list[tuple[str, int, str]]:
        """(login, channel id, claim id) for each of these channels with a bonus chest waiting; one batch."""
        if not logins:
            return []
        out = []
        for lg, resp in zip(logins, await self._gql.run_many(
                [op("ChannelPointsContext", channelLogin=lg) for lg in logins]), strict=True):
            ch = ((resp.get("data") or {}).get("community") or {}).get("channel") or {}
            claim = (((ch.get("self") or {}).get("communityPoints") or {}).get("availableClaim") or {})
            if claim.get("id") and ch.get("id"):
                out.append((lg, int(ch["id"]), claim["id"]))
        return out

    async def claim_points(self, channel_id: int, claim_id: str) -> bool:
        try:
            resp = await self._gql.run(op("ClaimCommunityPoints",
                                          input={"claimID": claim_id, "channelID": str(channel_id)}))
        except GqlError as exc:
            log.warning("Points claim failed: %s", exc)
            return False
        result = (resp.get("data") or {}).get("claimCommunityPoints") or {}
        return bool(result.get("claim")) and not result.get("error")

    async def current_drop(self, channel_id: int) -> tuple[str, int] | None:
        resp = await self._gql.run(op("CurrentDrop", channelID=str(channel_id)))
        cur = ((resp.get("data") or {}).get("currentUser") or {}).get("dropCurrentSession")
        return (cur["dropID"], cur["currentMinutesWatched"]) if cur else None

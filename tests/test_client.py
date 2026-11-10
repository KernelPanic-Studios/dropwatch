import json
from datetime import UTC, datetime
from pathlib import Path

from dropwatch.models import Prefs
from dropwatch.twitch.client import TwitchClient

# when the fixtures were captured: their campaigns are running then (the real clock is past them all)
CAPTURED = datetime(2026, 10, 8, 6, tzinfo=UTC)

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


class FakeGql:
    def __init__(self):
        self.ops = []

    async def run(self, payload):
        self.ops.append(payload["operationName"])
        return {
            "Inventory": load("inventory.json"),
            "ViewerDropsDashboard": load("campaigns.json"),
            "DirectoryPage_Game": load("directory.json"),
            "DropsPage_ClaimDropRewards": {"data": {"claimDropRewards": {"status": "ELIGIBLE_FOR_ALL"}}},
            "DropCurrentSessionContext": {"data": {"currentUser": {"dropCurrentSession": {
                "dropID": "d1", "currentMinutesWatched": 23}}}},
        }[payload["operationName"]]

    async def run_many(self, payloads):
        self.batches = getattr(self, "batches", []) + [[p["operationName"] for p in payloads]]
        details = {d["data"]["user"]["dropCampaign"]["id"]: d for d in load("campaign_details.json")}
        out = []
        for p in payloads:
            if p["operationName"] != "DropCampaignDetails":
                out.append(await self.run(p))
                continue
            cid = p["variables"]["dropID"]
            out.append(details.get(cid) or {"data": {"user": {"dropCampaign": {"id": cid}}}})
        return out


async def test_campaigns_merges_inventory_dashboard_and_details():
    camps = await TwitchClient(FakeGql(), 42).campaigns()
    assert any(c.name == "Frights & Delights" for c in camps)
    assert len({c.id for c in camps}) == len(camps)


async def test_claim_and_current_drop():
    c = TwitchClient(FakeGql(), 42)
    assert await c.claim("inst") is True
    assert await c.current_drop(123) == ("d1", 23)


async def test_live_channels_skips_never_games():
    g = FakeGql()
    c = TwitchClient(g, 42)
    camps = await c.campaigns()
    never = frozenset(x.game.name for x in camps)
    await c.live_channels(camps, Prefs(never=never), CAPTURED)
    assert "DirectoryPage_Game" not in g.ops


async def test_live_channels_asks_for_every_game_in_batches_not_one_by_one():
    # 2026-10-10: one request per game took 13-38 s for ~57 games; batched (20 per request) took ~1 s
    g = FakeGql()
    c = TwitchClient(g, 42)
    camps = await c.campaigns()
    g.ops.clear()
    g.batches = []
    live = await c.live_channels(camps, Prefs(), CAPTURED)
    assert live
    assert any("DirectoryPage_Game" in b for b in g.batches)
    direct = [o for o in g.ops if o == "DirectoryPage_Game"]
    # every lookup went via a batch
    assert len(direct) == sum(b.count("DirectoryPage_Game") for b in g.batches)

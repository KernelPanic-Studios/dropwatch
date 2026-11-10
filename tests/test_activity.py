"""Activity (a new tab, approved mockup docs/design/pre-docker-mockup.html, 2026-10-10): what Dropwatch did,
from the events table (kept 7 days), with enough detail to say why."""
import asyncio

from apihelpers import client, logged_in, make_app
from test_points import make as points_runner
from test_runner import NOW, FakeClient, FakePubSub, FakeWatcher, camp, chan
from test_summaries import make as notifier

from dropwatch.alerts import Snapshot
from dropwatch.events import EventBus
from dropwatch.runner import Runner
from dropwatch.store import Store
from dropwatch.twitch.pubsub import PointsClaimable, StreamDown


def events(store, kind):
    return [d for k, _, d in store.recent_events(500) if k == kind]


async def test_a_switch_records_the_game_and_why(tmp_path):
    st = Store(tmp_path / "d.db")
    c = FakeClient([camp()], [chan("a", 7), chan("b", 8)])
    r = Runner(c, FakeWatcher(), FakePubSub(), st, user_id=42, clock=lambda: NOW)
    await r.refresh()
    first = r.watching.login
    c.live = [x for x in c.live if x.login != first]
    await r.handle(StreamDown(r.watching.id))
    (sw,) = events(st, "switched")
    assert sw["from"] == first and sw["to"] == r.watching.login
    assert (sw["campaign"], sw["game"], sw["from_live"]) == ("Frights", "Palia", False)  # it went offline
    assert sw["reason"] == "most urgent"


async def test_a_claim_records_its_game(tmp_path):
    st = Store(tmp_path / "d.db")
    c = FakeClient([camp(cur=60, claim_id="x1")], [chan("a", 7)])
    r = Runner(c, FakeWatcher(), FakePubSub(), st, user_id=42, clock=lambda: NOW)
    await r.refresh()
    (cl,) = events(st, "claimed")
    assert cl == {"campaign": "Frights", "reward": "Palcat Glasses", "game": "Palia"}


async def test_a_chest_records_the_channel_by_name(tmp_path):
    r, _, _ = points_runner(tmp_path)
    await r.refresh()
    await r.handle(PointsClaimable(7, "claim-1"))
    (p,) = events(r._store, "points_claimed")
    assert p["channel"] == "a"


async def test_a_sent_notification_is_recorded_with_where_it_went(tmp_path):
    n, _, st = notifier(tmp_path, None)
    bus = EventBus()

    async def send(title, body):
        return [{"name": "ntfy", "ok": True, "message": "sent"},
                {"name": "Discord", "ok": False, "message": "401"}]

    task = asyncio.create_task(n.run(bus, lambda: Snapshot(None, None, []), send))
    await asyncio.sleep(0)
    bus.publish("state", {"state": "signed_out"})
    await asyncio.sleep(0.05)
    task.cancel()
    (e,) = events(st, "notified")
    assert e == {"title": "Dropwatch: Twitch sign-in stopped working", "sent": ["ntfy"],
                 "failed": ["Discord"]}


async def test_activity_lists_known_events_newest_first_with_only_their_known_fields(tmp_path):
    app, ctx = make_app(tmp_path)
    ctx.store.log_event("switched", {"from": "a", "to": "b", "game": "Palia", "token": "secret!"})
    ctx.store.log_event("debug_dump", {"anything": 1})  # not an Activity kind
    ctx.store.log_event("claimed", {"campaign": "Frights", "reward": "Glasses"})
    c = await logged_in(app)
    r = (await c.get("/api/activity")).json()
    assert [e["kind"] for e in r["events"]] == ["claimed", "switched"]
    assert r["events"][1]["data"] == {"from": "a", "to": "b", "game": "Palia"}
    assert r["kept_days"] == 7
    async with client(app) as anon:
        assert (await anon.get("/api/activity")).status_code == 401


async def test_a_stream_that_ended_but_is_still_listed_counts_as_offline(tmp_path):
    # review fix: Twitch's directory lists a stream for minutes after it ends (runner.handle StreamDown)
    st = Store(tmp_path / "d.db")
    c = FakeClient([camp()], [chan("a", 7), chan("b", 8)])
    r = Runner(c, FakeWatcher(), FakePubSub(), st, user_id=42, clock=lambda: NOW)
    await r.refresh()
    first = r.watching.login
    await r.handle(StreamDown(r.watching.id))  # still in c.live
    (sw,) = events(st, "switched")
    assert sw["from"] == first and sw["from_live"] is False


async def test_activity_shows_the_whole_week_however_busy(tmp_path):
    # review fix: a 1000-row cap cut a busy week short while the page said "Kept for 7 days"
    app, ctx = make_app(tmp_path)
    for i in range(1200):
        ctx.store.log_event("points_claimed", {"channel": f"c{i}"})
    c = await logged_in(app)
    assert len((await c.get("/api/activity")).json()["events"]) == 1200

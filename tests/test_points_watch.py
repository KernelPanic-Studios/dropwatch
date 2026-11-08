"""Channel points page (asked for 2026-11-08): streamers on the Channel points list are watched whenever
they're live, for their points, apart from drops. Twitch counts two streams at once: the drop channel takes
one slot, the list's streamers fill the rest, top of the list first."""
from datetime import timedelta

from apihelpers import logged_in, make_app
from test_runner import NOW, FakeClient, FakePubSub, FakeWatcher, camp, chan

from dropwatch.backup import make_backup, restore_backup
from dropwatch.models import LiveChannel
from dropwatch.runner import FAILS_BEFORE_SWITCH, Runner
from dropwatch.store import Store
from dropwatch.twitch.pubsub import PointsEarned, StreamDown, topic


def streamer(login, cid, game="Just Chatting"):
    return LiveChannel(cid, login, 999, 50, False, f"b{cid}", game)


def make(tmp_path, live, campaigns=None, points=("alice", "bob", "carol"), store=None):
    st = store or Store(tmp_path / "d.db")
    st.set_points_channels(list(points))
    t = [NOW]
    c = FakeClient([camp()] if campaigns is None else campaigns, live)
    ws = [FakeWatcher(), FakeWatcher()]
    r = Runner(c, FakeWatcher(), FakePubSub(), st, user_id=42, clock=lambda: t[0], points_watchers=ws)
    return r, c, st, t, ws


def watching(r):
    return [ch.login for ch in r.points_watching]


async def test_one_streamer_is_watched_alongside_drops_top_of_the_list_first(tmp_path):
    r, *_ = make(tmp_path, [chan("a", 7), streamer("bob", 20), streamer("alice", 10)])
    await r.refresh()
    assert r.watching.login == "a"
    assert watching(r) == ["alice"] and r.points_waiting == {"bob": "full"}
    assert topic("stream_state", 10) in r._pubsub.topics and topic("user_points", 42) in r._pubsub.topics


async def test_with_no_drops_to_mine_two_streamers_are_watched(tmp_path):
    r, *_ = make(tmp_path, [streamer("bob", 20), streamer("alice", 10), streamer("carol", 30)], campaigns=[])
    await r.refresh()
    assert r.watching is None
    assert watching(r) == ["alice", "bob"] and r.points_waiting == {"carol": "full"}


async def test_a_streamer_the_drop_miner_is_on_already_earns_there(tmp_path):
    r, *_ = make(tmp_path, [chan("a", 7), streamer("bob", 20)], points=("a", "bob"))
    await r.refresh()
    assert r.watching.login == "a" and watching(r) == ["bob"] and r.points_waiting == {"a": "drops"}


async def test_each_tick_plays_every_points_stream_on_its_own_watcher(tmp_path):
    r, _, _, _, ws = make(tmp_path, [streamer("bob", 20), streamer("alice", 10)], campaigns=[])
    await r.refresh()
    await r.tick()
    await r.tick()
    assert sorted(w.sent[0] for w in ws) == ["alice", "bob"]
    assert all(len(set(w.sent)) == 1 and len(w.sent) == 2 for w in ws)  # each keeps its stream


async def test_a_stream_that_keeps_failing_is_set_aside_and_the_next_one_takes_its_slot(tmp_path):
    r, _, st, _, ws = make(tmp_path, [chan("a", 7), streamer("alice", 10), streamer("bob", 20)])
    await r.refresh()
    assert watching(r) == ["alice"]
    ws[0].ok = False
    for _ in range(FAILS_BEFORE_SWITCH):
        await r.tick()
    assert watching(r) == ["bob"] and "alice" in r._excluded
    kinds = [(k, d) for k, _, d in st.recent_events(50) if k in ("points_watch", "points_dropped")]
    assert ("points_dropped", {"channel": "alice"}) in kinds
    assert ("points_watch", {"channel": "alice", "on": False}) in kinds


async def test_a_streamer_going_offline_frees_the_slot_at_once(tmp_path):
    r, *_ = make(tmp_path, [chan("a", 7), streamer("alice", 10), streamer("bob", 20)])
    await r.refresh()
    await r.handle(StreamDown(10))
    assert watching(r) == ["bob"]


async def test_pause_stops_points_watching_and_resume_brings_it_back(tmp_path):
    r, _, _, t, ws = make(tmp_path, [streamer("alice", 10)], campaigns=[])
    await r.refresh()
    r.pause(NOW + timedelta(minutes=5))
    assert watching(r) == []
    await r.tick()
    assert ws[0].sent == []
    t[0] += timedelta(minutes=6)
    await r.tick()  # the pause ran out
    assert watching(r) == ["alice"] and ws[0].sent == ["alice"]


async def test_switched_off_the_list_is_kept_but_nothing_is_watched(tmp_path):
    st = Store(tmp_path / "d.db")
    st.put_settings({"points_watch": False})
    r, *_ = make(tmp_path, [streamer("alice", 10)], campaigns=[], store=st)
    await r.refresh()
    assert watching(r) == [] and st.get_points_channels() == ("alice", "bob", "carol")


async def test_watching_a_favourite_for_points_counts_as_its_streak_visit(tmp_path):
    st = Store(tmp_path / "d.db")
    st.set_lists([], set(), ["alice"])
    r, *_ = make(tmp_path, [chan("a", 7), streamer("alice", 10)], store=st)
    await r.refresh()
    assert r.watching.login == "a" and watching(r) == ["alice"]  # no detour: it earns its streak already


async def test_points_earned_are_totalled_per_streamer(tmp_path):
    r, _, st, _, _ = make(tmp_path, [streamer("alice", 10)], campaigns=[])
    await r.refresh()
    await r.handle(PointsEarned(10, "WATCH", 10))
    await r.handle(PointsEarned(10, "CLAIM", 50))
    assert st.points_by_channel(NOW - timedelta(days=1)) == {"alice": {"points": 60, "chests": 1}}


def test_the_list_is_in_backups_and_older_backups_leave_it_alone(tmp_path):
    st = Store(tmp_path / "d.db")
    st.set_points_channels(["Alice ", "bob", "alice", ""])
    assert st.get_points_channels() == ("alice", "bob")
    data = make_backup(st, NOW, secrets=False)
    assert data["points_channels"] == ["alice", "bob"]
    other = Store(tmp_path / "e.db")
    restore_backup(other, data)
    assert other.get_points_channels() == ("alice", "bob")
    del data["points_channels"]
    other.set_points_channels(["carol"])
    restore_backup(other, data)
    assert other.get_points_channels() == ("carol",)


async def test_api_lists_who_is_live_watched_and_what_they_earned(tmp_path):
    app, ctx = make_app(tmp_path)
    r, *_ = make(tmp_path, [chan("a", 7), streamer("alice", 10), streamer("bob", 20)], store=ctx.store)
    ctx.service.runner = r
    await r.refresh()
    ctx.store.add_points(NOW, "alice", "WATCH", 10)
    c = await logged_in(app)
    page = (await c.get("/api/points")).json()
    rows = [(x["login"], x["live"], x["watching"], x["waiting"], x["points"]) for x in page["channels"]]
    assert rows == [("alice", True, True, None, 10), ("bob", True, False, "full", 0),
                    ("carol", False, False, None, 0)]
    assert page["on"] is True and page["points"] == 10
    state = (await c.get("/api/state")).json()
    assert [w["channel"] for w in state["points_watching"]] == ["alice"]
    res = await c.put("/api/points/channels", json={"channels": ["bob", "alice"]})
    assert res.status_code == 200
    assert [x["login"] for x in res.json()["channels"]] == ["bob", "alice"]
    assert watching(r) == ["bob"]
    assert (await c.put("/api/points/channels", json={"channels": ["x"], "extra": 1})).status_code == 422

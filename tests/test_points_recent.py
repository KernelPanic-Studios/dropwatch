"""Chests left behind: a bonus chest stays claimable after we stop watching a channel, so each refresh also
looks at the channels watched in the last 7 days (asked for 2026-10-11; mills and glorious_e each had one
waiting since Oct 9)."""
import json
from datetime import UTC, datetime, timedelta

import test_runner
from test_runner import FakeClient, FakePubSub, FakeWatcher, chan

from dropwatch.runner import RECENT_CHEST_CHANNELS, Runner
from dropwatch.store import Store

# relative to the real clock: the store prunes events older than 7 days by real time (review fix)
NOW = datetime.now(UTC).replace(microsecond=0)


def camp():
    """test_runner's campaign, moved to run around the real clock like everything else here."""
    from dataclasses import replace

    c, shift = test_runner.camp(), NOW - test_runner.NOW
    drops = tuple(replace(d, starts_at=d.starts_at + shift, ends_at=d.ends_at + shift) for d in c.drops)
    return replace(c, starts_at=c.starts_at + shift, ends_at=c.ends_at + shift, drops=drops)


class ChestClient(FakeClient):
    def __init__(self, *a, chests=None):
        super().__init__(*a)
        self.chests, self.asked, self.claimed = dict(chests or {}), [], []

    async def waiting_points_claims(self, logins):
        self.asked.append(list(logins))
        return [(lg, *self.chests[lg]) for lg in logins if lg in self.chests]

    async def claim_points(self, channel_id, claim_id):
        self.claimed.append((channel_id, claim_id))
        return True


def watched_before(st, login, days_ago):
    at = (NOW - timedelta(days=days_ago)).isoformat()
    data = json.dumps({"from": "", "to": login})
    st._db.execute("INSERT INTO events VALUES (?, 'switched', ?)", (at, data))
    st._db.commit()


def make(tmp_path, chests, on=True):
    st = Store(tmp_path / "d.db")
    st.put_settings({"claim_points": on})
    c = ChestClient([camp()], [chan("a", 7)], chests=chests)
    return Runner(c, FakeWatcher(), FakePubSub(), st, user_id=42, clock=lambda: NOW), c, st


async def test_chests_on_recently_watched_channels_are_claimed(tmp_path):
    r, c, st = make(tmp_path, {"mills": (51, "chest-m"), "glorious_e": (63, "chest-g")})
    watched_before(st, "mills", 2)
    watched_before(st, "glorious_e", 1)
    await r.refresh()
    assert c.asked[-1][0] == "a"  # the channel being watched first, then the recent ones, newest first
    assert c.asked[-1][1:] == ["glorious_e", "mills"]
    assert sorted(c.claimed) == [(51, "chest-m"), (63, "chest-g")]
    got = sorted(d["channel"] for k, _, d in st.recent_events(50) if k == "points_claimed")
    assert got == ["glorious_e", "mills"]


async def test_only_the_last_week_and_at_most_the_cap(tmp_path):
    r, c, st = make(tmp_path, {})
    watched_before(st, "too_old", 7.5)  # still in the table (nothing logged since): the runner must skip it
    for i in range(RECENT_CHEST_CHANNELS + 5):
        watched_before(st, f"ch{i}", 1 + i / 1000)
    recent = r._recent_channels()
    assert "too_old" not in recent and len(recent) == RECENT_CHEST_CHANNELS
    assert recent[0] == "ch0"  # newest first


async def test_nothing_is_looked_up_with_channel_points_off(tmp_path):
    r, c, st = make(tmp_path, {"mills": (51, "chest-m")}, on=False)
    watched_before(st, "mills", 1)
    await r.refresh()
    assert c.asked == [] and c.claimed == []


async def test_channels_watched_more_than_a_week_ago_are_skipped(tmp_path):
    r, c, st = make(tmp_path, {})
    watched_before(st, "too_old", 7.5)  # still in the table (nothing logged since): the runner must skip it
    watched_before(st, "recent", 1)
    assert r._recent_channels() == ["recent"]

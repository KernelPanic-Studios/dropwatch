"""Keep copies of the images History shows (2026-10-10): Twitch's links can stop working after a campaign
ends. Only Twitch's image host is fetched."""
from datetime import timedelta

from apihelpers import NOW, logged_in, make_app

from dropwatch.images import ImageCache, box_art_144


class FakeGet:
    def __init__(self, body=b"\x89PNG...", ctype="image/png", status=200):
        self.body, self.ctype, self.status, self.urls = body, ctype, status, []

    async def __call__(self, url):
        self.urls.append(url)
        return self.status, self.ctype, self.body


async def test_fetches_twitch_images_once_and_names_them_by_url(tmp_path):
    get = FakeGet()
    cache = ImageCache(tmp_path / "images", get)
    url = "https://static-cdn.jtvnw.net/twitch-quests-assets/REWARD/abc.png"
    assert cache.local_url(url) is None
    assert await cache.ensure([url, url]) == 1
    assert await cache.ensure([url]) == 0  # already kept
    assert get.urls == [url]
    local = cache.local_url(url)
    assert local and local.startswith("api/img/") and local.endswith(".png")
    assert cache.file(local.rsplit("/", 1)[1]).read_bytes() == b"\x89PNG..."


async def test_refuses_other_hosts_non_images_and_huge_files(tmp_path):
    for url, get in [("https://evil.example/x.png", FakeGet()),
                     ("http://static-cdn.jtvnw.net/x.png", FakeGet()),  # not https
                     ("https://static-cdn.jtvnw.net/x.png", FakeGet(ctype="text/html")),
                     ("https://static-cdn.jtvnw.net/y.png", FakeGet(body=b"x" * (3 * 1024 * 1024 + 1))),
                     ("https://static-cdn.jtvnw.net/z.png", FakeGet(status=404))]:
        cache = ImageCache(tmp_path / "images", get)
        assert await cache.ensure([url]) == 0, url
        assert cache.local_url(url) is None
        if "static-cdn.jtvnw.net/" not in url or url.startswith("http:"):
            assert get.urls == [], url  # never even asked for


def test_box_art_is_kept_at_the_size_the_page_shows():
    assert box_art_144("https://static-cdn.jtvnw.net/ttv-boxart/491931_IGDB-{width}x{height}.jpg") \
        == "https://static-cdn.jtvnw.net/ttv-boxart/491931_IGDB-144x192.jpg"
    assert box_art_144("https://static-cdn.jtvnw.net/ttv-boxart/1_IGDB-120x160.jpg").endswith("1_IGDB-144x192.jpg")
    assert box_art_144("https://static-cdn.jtvnw.net/ttv-boxart/1338428218_IGDB.jpg").endswith("_IGDB-144x192.jpg")
    assert box_art_144("") == ""


async def test_history_serves_kept_copies_and_wanted_lists_every_history_image(tmp_path):
    app, ctx = make_app(tmp_path)
    art = "https://static-cdn.jtvnw.net/ttv-boxart/1_IGDB-{width}x{height}.jpg"
    reward = "https://static-cdn.jtvnw.net/twitch-quests-assets/REWARD/r.png"
    ctx.store.add_claim(NOW, "c1", "Frights", "Palia", [("Glasses", reward)], box_art_url=art)
    ctx.images = ImageCache(tmp_path / "images", FakeGet(body=b"IMG"))
    assert set(ctx.store.history_image_urls(NOW - timedelta(days=400))) == {reward, art}
    c = await logged_in(app)
    (claim,) = (await c.get("/api/history")).json()["claims"]
    assert claim["rewards"][0]["image_url"] == reward  # not kept yet: Twitch's own link
    await ctx.images.ensure([reward, box_art_144(art)])
    (claim,) = (await c.get("/api/history")).json()["claims"]
    local = claim["rewards"][0]["image_url"]
    assert local.startswith("api/img/") and claim["box_art_url"].startswith("api/img/")
    r = await c.get(local)
    assert r.status_code == 200 and r.content == b"IMG" and r.headers["content-type"] == "image/png"
    assert (await c.get("/api/img/..%2Fd.db")).status_code == 404
    assert (await c.get("/api/img/nothere00000000000000000.png")).status_code == 404
    await c.aclose()


async def test_reads_the_whole_body_even_in_chunks_and_never_follows_redirects():
    from dropwatch.images import MAX_BYTES, aiohttp_get

    class Content:
        def __init__(self, chunks):
            self.chunks = chunks

        async def read(self, n=-1):  # aiohttp returns only what has arrived, not the whole body
            return self.chunks[0]

        async def iter_chunked(self, n):
            for c in self.chunks:
                yield c

    class Resp:
        def __init__(self, chunks):
            self.status, self.headers, self.content = 200, {"Content-Type": "image/png"}, Content(chunks)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class Session:
        def __init__(self, chunks):
            self.chunks, self.kw = chunks, None

        def get(self, url, **kw):
            self.kw = kw
            return Resp(self.chunks)

    s = Session([b"aaa", b"bbb", b"ccc"])
    assert await aiohttp_get(s)("https://static-cdn.jtvnw.net/x.png") == (200, "image/png", b"aaabbbccc")
    assert s.kw["allow_redirects"] is False
    big = Session([b"x" * MAX_BYTES, b"y"])
    status, _, body = await aiohttp_get(big)("https://static-cdn.jtvnw.net/x.png")
    assert len(body) > MAX_BYTES  # over the cap: ensure() refuses it


def test_only_exact_hash_names_are_served(tmp_path):
    cache = ImageCache(tmp_path)
    good = "0123456789abcdef01234567.png"
    (tmp_path / good).write_bytes(b"x")
    (tmp_path / "x.png").write_bytes(b"x")
    assert cache.file(good) is not None
    for bad in ["../" + good, good + "\n", "X123456789abcdef01234567.png", "x.png", good + ".part"]:
        assert cache.file(bad) is None, bad


async def test_odd_urls_are_refused_and_dead_links_wait_a_day(tmp_path):
    get = FakeGet(status=404)
    clock = [NOW]
    cache = ImageCache(tmp_path, get, clock=lambda: clock[0])
    for url in ["https://user@static-cdn.jtvnw.net/x.png", "https://static-cdn.jtvnw.net:8443/x.png"]:
        assert await cache.ensure([url]) == 0 and get.urls == []
    url = "https://static-cdn.jtvnw.net/gone.png"
    await cache.ensure([url])
    await cache.ensure([url])
    assert get.urls == [url]  # a failure isn't retried at once
    clock[0] += timedelta(days=1, minutes=1)
    await cache.ensure([url])
    assert get.urls == [url, url]


def test_only_images_history_shows_in_full_are_wanted(tmp_path):
    from dropwatch.store import Store

    st = Store(tmp_path / "d.db")

    def row(cid, **over):
        cdn = "https://static-cdn.jtvnw.net/"
        base = {"id": cid, "name": cid, "game": "G", "box_art_url": f"{cdn}{cid}.jpg",
                "link_url": "", "ends_at": NOW + timedelta(hours=1), "linked": True, "badge": False,
                "rewards": [{"name": "r", "image_url": f"{cdn}{cid}-r.png", "claimed": False}],
                "impossible": False, "never": False, "priority": False, "pinned": False, "live": True,
                "watched": 0}
        return {**base, **over}

    st.log_campaigns(NOW, [row("started", watched=10), row("prio", priority=True),
                           row("unlinked", linked=False), row("untouched"),
                           row("never", never=True, watched=10)])
    wanted = " ".join(st.history_image_urls(NOW - timedelta(days=1)))
    for cid in ("started", "prio", "unlinked"):
        assert f"/{cid}.jpg" in wanted and f"/{cid}-r.png" in wanted
    assert "untouched" not in wanted and "/never" not in wanted

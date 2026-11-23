"""Settings › Proxy (issue #5): the proxy settings, read-only, and what this request looked like."""
import httpx
from apihelpers import make_app
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from dropwatch.api.app import create_app, host_name, is_local_name


async def proxy_info(app, host="192.168.1.10:5800", peer="192.168.1.10", headers=None):
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(peer, 1234)), base_url=f"http://{host}")
    async with c:
        assert (await c.post("/api/login", json={"password": "correct horse"})).status_code == 204
        r = await c.get("/api/proxy", headers=headers or {})
        assert r.status_code == 200, r.text
        return r.json()


async def test_direct_visit_shows_no_proxy(tmp_path):
    _, ctx = make_app(tmp_path)
    app = create_app(ctx, hosts=["dropwatch.example.com", " "], trusted=[""])
    got = await proxy_info(app)
    assert got == {"hosts": ["dropwatch.example.com"], "trusted": [], "host": "192.168.1.10:5800", "host_is_local": True,
                   "scheme": "http", "client": "192.168.1.10", "forwarded_for": None, "proxy_trusted": None,
                   "prefix": None}


async def test_untrusted_proxy_is_spotted_by_its_own_address(tmp_path):
    # the proxy isn't in FORWARDED_ALLOW_IPS: uvicorn leaves the client as the proxy, so every visitor
    # shares its login lockout
    _, ctx = make_app(tmp_path)
    app = ProxyHeadersMiddleware(create_app(ctx, hosts=["dropwatch.example.com"]), trusted_hosts=["127.0.0.1"])
    got = await proxy_info(app, host="dropwatch.example.com", peer="172.18.0.5",
                           headers={"x-forwarded-for": "203.0.113.7", "x-forwarded-proto": "https"})
    assert got["client"] == "172.18.0.5" and got["proxy_trusted"] is False and got["scheme"] == "http"
    assert got["host_is_local"] is False and got["forwarded_for"] == "203.0.113.7"


async def test_trusted_proxy_passes_the_visitor_through(tmp_path):
    _, ctx = make_app(tmp_path)
    inner = create_app(ctx, hosts=["dropwatch.example.com"], trusted=["172.18.0.5"])
    app = ProxyHeadersMiddleware(inner, trusted_hosts=["172.18.0.5"])
    got = await proxy_info(app, host="dropwatch.example.com", peer="172.18.0.5",
                           headers={"x-forwarded-for": "203.0.113.7", "x-forwarded-proto": "https",
                                    "x-forwarded-prefix": "/dropwatch"})
    assert got["client"] == "203.0.113.7" and got["proxy_trusted"] is True and got["scheme"] == "https"
    assert got["trusted"] == ["172.18.0.5"] and got["prefix"] == "/dropwatch"


async def test_proxy_needs_the_page_password(tmp_path):
    app, _ = make_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
        assert (await c.get("/api/proxy")).status_code == 401


def test_host_names():
    assert host_name("[::1]:5800") == "::1" and host_name("Tower.Local.:5800") == "tower.local"
    assert host_name("example.com") == "example.com" and host_name("") == ""
    assert is_local_name("192.168.1.10") and is_local_name("tower") and is_local_name("nas.home.arpa")
    assert not is_local_name("dropwatch.example.com") and not is_local_name("")

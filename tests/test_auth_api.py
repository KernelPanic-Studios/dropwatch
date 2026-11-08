from apihelpers import client, logged_in, make_app

PRIVATE = [
    ("GET", "/api/state"), ("GET", "/api/events"), ("POST", "/api/pause"), ("POST", "/api/resume"),
    ("POST", "/api/mine-now"), ("POST", "/api/channel"), ("GET", "/api/lists"), ("PUT", "/api/lists"),
    ("GET", "/api/suggestions"), ("GET", "/api/history"), ("GET", "/api/settings"), ("PUT", "/api/settings"),
    ("POST", "/api/twitch/signin"), ("DELETE", "/api/twitch/signin"), ("GET", "/api/twitch/signin"),
    ("POST", "/api/twitch/signout"), ("POST", "/api/logout"), ("POST", "/api/refresh"),
    ("GET", "/api/notify/channels"), ("PUT", "/api/notify/channels/{kind}"),
    ("DELETE", "/api/notify/channels/{kind}"), ("POST", "/api/notify/test"),
    ("GET", "/api/pins"), ("PUT", "/api/pins"), ("GET", "/api/about"),
    ("POST", "/api/needs/ignored/{campaign_id}"), ("DELETE", "/api/needs/ignored/{campaign_id}"),
    ("GET", "/api/backup"), ("POST", "/api/restore"), ("GET", "/api/activity"), ("POST", "/api/streak/end"),
    ("GET", "/api/sessions"), ("DELETE", "/api/sessions/{session_id}"),
    ("POST", "/api/sessions/sign-out-others"), ("GET", "/api/points"), ("PUT", "/api/points/channels"),
]


async def test_every_private_route_requires_session(tmp_path):
    app, _ = make_app(tmp_path)
    async with client(app) as c:
        for method, path in PRIVATE:
            r = await c.request(method, path, json={})
            assert r.status_code == 401, (method, path, r.status_code)


async def test_private_route_list_matches_app_routes(tmp_path):
    # read the schema, not app.routes: FastAPI 0.14x keeps included routers as lazy wrappers
    app, _ = make_app(tmp_path)
    public = {"/api/health", "/api/health/miner", "/api/me", "/api/setup", "/api/login"}
    routes = {(m.upper(), path) for path, ops in app.openapi()["paths"].items() for m in ops}
    assert {x for x in routes if x[1] not in public} == set(PRIVATE)


async def test_me_and_setup_flow(tmp_path):
    app, ctx = make_app(tmp_path, password=None)
    async with client(app) as c:
        assert (await c.get("/api/me")).json() == {"authenticated": False, "setup_required": True}
        assert (await c.post("/api/setup", json={"password": "short"})).status_code == 422
        r = await c.post("/api/setup", json={"password": "correct horse"})
        assert r.status_code == 204 and "dm_session" in r.cookies
        assert (await c.get("/api/me")).json() == {"authenticated": True, "setup_required": False}
        assert (await c.get("/api/state")).status_code != 401  # cookie accepted (stub until Task 7)


async def test_setup_refused_once_password_exists(tmp_path):
    app, ctx = make_app(tmp_path)
    async with client(app) as c:
        assert (await c.post("/api/setup", json={"password": "attacker pw"})).status_code == 409
    assert ctx.store.check_password("correct horse")


async def test_wrong_password_rejected(tmp_path):
    app, _ = make_app(tmp_path)
    async with client(app) as c:
        r = await c.post("/api/login", json={"password": "nope nope"})
        assert r.status_code == 401 and "dm_session" not in r.cookies


async def test_cookie_flags(tmp_path):
    app, _ = make_app(tmp_path)
    async with client(app) as c:
        r = await c.post("/api/login", json={"password": "correct horse"})
        sc = r.headers["set-cookie"].lower()
        assert "httponly" in sc and "samesite=strict" in sc and "max-age=" in sc


async def test_logout_invalidates_token(tmp_path):
    app, _ = make_app(tmp_path)
    c = await logged_in(app)
    token = c.cookies["dm_session"]
    assert (await c.post("/api/logout")).status_code == 204
    async with client(app) as other:
        other.cookies.set("dm_session", token)
        assert (await other.get("/api/state")).status_code == 401
    await c.aclose()


async def test_health_is_public(tmp_path):
    app, _ = make_app(tmp_path)
    async with client(app) as c:
        assert (await c.get("/api/health")).json() == {"ok": True}

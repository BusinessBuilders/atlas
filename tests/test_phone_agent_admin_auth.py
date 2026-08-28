# tests/test_phone_agent_admin_auth.py — getting into the owner dashboard, and
# being kept out of it.
#
# The dashboard this replaces put the shared admin token itself in the cookie,
# had no CSRF token, no lockout, no per-owner scope and no security headers:
# anyone who could read one cookie had the line's password, "sign out" could
# only ever be advice, and a page on another site could post to /save. These
# tests pin the replacement, end to end over a real aiohttp server:
#
#   * an unauthenticated page is a redirect to sign in, and leaks nothing;
#   * the cookie carries a random session id with HttpOnly/Secure/SameSite;
#   * a wrong code is refused, logged with its source, and written to `events`;
#   * five wrong codes lock the address out with a Retry-After;
#   * a mutating POST without the session's CSRF token changes nothing;
#   * signing out ends the session ON THE SERVER;
#   * an owner of one business cannot read another business's anything.
#
# No real caller data anywhere: +1555…/CAtest… and invented names only.
import asyncio
import importlib.util
import logging
import sys
from http.cookies import SimpleCookie

import aiohttp
import pytest
from aiohttp import web

from test_phone_agent_plugin import PLUGINS_DIR, _import_service

ADMIN_DIR = PLUGINS_DIR / "phone_agent" / "admin"
ADMIN_MODULE = "phone_agent_admin_under_test"

ONE_BUSINESS = (
    '\n[owners.jo]\ntoken_env = "PHONE_OWNER_JO_TOKEN"\nprofiles = ["acme"]\n'
)
OTHER_BUSINESS = (
    '\n[profiles.other]\nbusiness_name = "Other Co"\nservices = "other work"\n'
    'owner_name = "Sam"\ngreeting = "hello"\n'
)


def load_admin():
    """Import the admin PACKAGE the way service.py does.

    Cached in sys.modules under one name so the package's own `from . import`
    lines resolve — a package loaded twice would give two copies of the CSRF
    secret and two lockout tables.
    """
    if ADMIN_MODULE in sys.modules:
        return sys.modules[ADMIN_MODULE]
    spec = importlib.util.spec_from_file_location(
        ADMIN_MODULE, ADMIN_DIR / "__init__.py",
        submodule_search_locations=[str(ADMIN_DIR)])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[ADMIN_MODULE] = module
    spec.loader.exec_module(module)
    return module


async def health_ok():
    """A healthy snapshot in the shape service.health_snapshot() returns."""
    return {
        "bridge": "ok", "model_backend": "ok", "probe_error": "",
        "probe_checked_at": 1756000000.0, "brain": "default", "model": "m",
        "unreachable_brains": [], "profiles": ["acme"], "numbers": 1,
        "ntfy": "off", "ntfy_failures": 0,
        "last_delivery": {"ts": None, "call_sid": None, "ok": None, "error": ""},
        "recent_events": [],
    }, True


class Client:
    """An HTTP client that carries the session cookie by hand.

    aiohttp's own jar will not send a `Secure` cookie to an http:// URL, and
    the real dashboard is only ever reached over the https address
    `tailscale serve` publishes. Holding the cookie here lets the test assert
    the real flags on the real Set-Cookie header AND keep using the session.
    """

    def __init__(self, session: aiohttp.ClientSession, base: str) -> None:
        self.session, self.base, self.cookies = session, base, {}

    def _headers(self, extra=None) -> dict:
        headers = dict(extra or {})
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        return headers

    def _remember(self, response) -> None:
        for raw in response.headers.getall("Set-Cookie", []):
            jar = SimpleCookie()
            jar.load(raw)
            for name, morsel in jar.items():
                if morsel.value:
                    self.cookies[name] = morsel.value
                else:
                    self.cookies.pop(name, None)

    async def get(self, path, *, headers=None, allow_redirects=True):
        response = await self.session.get(
            self.base + path, headers=self._headers(headers),
            allow_redirects=allow_redirects)
        self._remember(response)
        return response

    async def post(self, path, data=None, *, headers=None, allow_redirects=False):
        response = await self.session.post(
            self.base + path, data=data or {}, headers=self._headers(headers),
            allow_redirects=allow_redirects)
        self._remember(response)
        return response

    async def sign_in(self, code: str):
        response = await self.post("/sign-in", {"code": code})
        assert response.status == 303, await response.text()
        return response

    async def csrf(self, path: str = "/") -> str:
        """The token this session's forms carry, read off a real page."""
        page = await (await self.get(path)).text()
        marker = 'name="csrf" value="'
        assert marker in page, "no CSRF token on the page"
        return page.split(marker, 1)[1].split('"', 1)[0]


class Dashboard:
    def __init__(self, svc, admin, client, app) -> None:
        self.svc, self.admin, self.client, self.app = svc, admin, client, app
        self.store = svc.STORE


def dashboard_kwargs(svc, *, health=health_ok, brain_health=None, store=True):
    """Every dependency `build_admin_app` needs, wired to a real service.

    One place, so a test that builds the app by hand cannot drift from the one
    the service itself builds — that drift is exactly what let the old
    dashboard ship 39 lines behind the file it was deployed over.
    """
    return dict(
        get_state=lambda: (svc.NUMBERS, svc.PROFILES),
        get_config=lambda: svc.CONFIG,
        get_brains=lambda: (svc.BRAINS, svc.ACTIVE_BRAIN),
        get_branding=lambda: svc.BRANDING,
        get_owners=lambda: svc.OWNERS,
        get_health=health,
        get_brain_health=(lambda: svc.BRAIN_HEALTH) if brain_health is None
        else (lambda: brain_health),
        apply_config=svc.apply_config,
        delivery_targets=svc.delivery_targets,
        profile_setting=svc.profile_setting,
        opening_line=svc.opening_line,
        parse_config=svc.parse_config,
        config_from_diff=svc.config_from_diff,
        acknowledge_delivery_failure=svc.acknowledge_delivery_failure,
        public_base=svc.PUBLIC_BASE,
        product_defaults=svc.PRODUCT_DEFAULTS,
        store=svc.STORE if store else None,
    )


def dashboard(svc, *, health=health_ok, brain_health=None):
    """Serve the real dashboard against a real service module."""
    admin = load_admin()
    app = admin.build_admin_app(**dashboard_kwargs(
        svc, health=health, brain_health=brain_health))
    return _Serving(svc, admin, app)


class _Serving:
    def __init__(self, svc, admin, app) -> None:
        self.svc, self.admin, self.app = svc, admin, app

    async def __aenter__(self):
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, "127.0.0.1", 0).start()
        base = f"http://127.0.0.1:{self.runner.addresses[0][1]}"
        self.session = aiohttp.ClientSession()
        return Dashboard(self.svc, self.admin, Client(self.session, base), self.app)

    async def __aexit__(self, *exc):
        await self.session.close()
        await self.runner.cleanup()
        return False


@pytest.fixture
def line(tmp_path, monkeypatch):
    """A service with one business, one whole-line login and one per-business
    login."""
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    return _import_service(tmp_path, monkeypatch,
                           extra_env={"ADMIN_TOKEN": "line-code"},
                           cfg_extra=ONE_BUSINESS)


# --------------------------------------------------------------- the gate --

async def test_the_dashboard_redirects_a_stranger_to_sign_in(line):
    async with dashboard(line) as dash:
        response = await dash.client.get("/", allow_redirects=False)
        assert response.status == 302
        assert response.headers["Location"] == "/sign-in"
        assert "acme" not in await response.text()


async def test_the_sign_in_page_names_the_product_not_an_env_var(line):
    async with dashboard(line) as dash:
        page = await (await dash.client.get("/sign-in")).text()
    assert "Access code" in page
    assert 'autocomplete="current-password"' in page
    assert 'for="code"' in page and 'id="code"' in page
    assert 'aria-live="assertive"' in page
    for jargon in ("ADMIN_TOKEN", "env file", "TOML", "journalctl", "profile key"):
        assert jargon not in page, f"{jargon!r} is on the sign-in page"


async def test_a_wrong_code_is_refused_logged_and_recorded(line, caplog):
    async with dashboard(line) as dash:
        with caplog.at_level(logging.WARNING, logger="atlas-phone"):
            response = await dash.client.post("/sign-in", {"code": "not-it"})
        assert response.status == 401
        page = await response.text()
        assert "not recognised" in page
        assert dash.client.cookies == {}

    assert "dashboard sign-in FAILED from 127.0.0.1" in caplog.text
    [event] = dash.store.list_events([], include_unscoped=True)
    assert event["kind"] == "dashboard_signin_failed"
    assert "127.0.0.1" in event["detail"]
    assert "not-it" not in event["detail"]          # never the attempted code


async def test_the_right_code_sets_a_session_cookie_with_the_right_flags(line):
    async with dashboard(line) as dash:
        response = await dash.client.sign_in("line-code")
        raw = response.headers["Set-Cookie"]
        assert "HttpOnly" in raw
        assert "Secure" in raw
        assert "SameSite=Strict" in raw
        assert "Max-Age=1209600" in raw

        session_id = dash.client.cookies["phone_session"]
        assert session_id != "line-code"            # never the secret itself
        assert len(session_id) >= 32
        row = dash.store.get_session(session_id)
        assert row is not None and row["owner_key"] == "_admin"

        assert (await dash.client.get("/", allow_redirects=False)).status == 200


async def test_a_signed_in_owner_is_sent_on_from_the_sign_in_page(line):
    async with dashboard(line) as dash:
        await dash.client.sign_in("line-code")
        response = await dash.client.get("/sign-in", allow_redirects=False)
        assert response.status == 302
        assert response.headers["Location"] == "/"


async def test_a_forged_session_id_is_not_a_session(line):
    async with dashboard(line) as dash:
        dash.client.cookies["phone_session"] = "made-up"
        response = await dash.client.get("/", allow_redirects=False)
        assert response.status == 302


async def test_an_idle_session_expires(line, monkeypatch):
    async with dashboard(line) as dash:
        await dash.client.sign_in("line-code")
        session_id = dash.client.cookies["phone_session"]
        with dash.store.conn:
            dash.store.conn.execute(
                "UPDATE sessions SET last_seen = last_seen - ? WHERE id = ?",
                (1209601, session_id))
        response = await dash.client.get("/", allow_redirects=False)
        assert response.status == 302
        assert dash.store.get_session(session_id) is None


# ------------------------------------------------------------- lock-out ----

async def test_five_wrong_codes_lock_the_address_out(line, caplog):
    async with dashboard(line) as dash:
        with caplog.at_level(logging.WARNING, logger="atlas-phone"):
            for _ in range(4):
                assert (await dash.client.post(
                    "/sign-in", {"code": "no"})).status == 401
            fifth = await dash.client.post("/sign-in", {"code": "no"})
            assert fifth.status == 429
            sixth = await dash.client.post("/sign-in", {"code": "no"})

        assert sixth.status == 429
        assert int(sixth.headers["Retry-After"]) <= 60
        assert "Try again in" in await sixth.text()
        # even the RIGHT code waits out the lock
        assert (await dash.client.post("/sign-in", {"code": "line-code"})).status == 429

    assert caplog.text.count("dashboard sign-in FAILED") == 5


async def test_rotating_the_forwarded_header_does_not_buy_extra_guesses(line):
    """The lockout counted whatever `X-Forwarded-For` said, first element
    first — so a guesser who put a fresh made-up address in that header got a
    fresh bucket of five guesses every time, and the lockout counted to five
    forever without ever locking anything.

    `tailscale serve` (Go's httputil.ReverseProxy) APPENDS the address it saw
    to whatever the client sent, so the LAST element is the proxy's own
    observation and the only element the client cannot choose. This is a
    guesser sending a different address on every attempt, through that proxy.
    """
    async with dashboard(line) as dash:
        codes = []
        for attempt in range(6):
            response = await dash.client.post(
                "/sign-in", {"code": "no"},
                headers={"X-Forwarded-For": f"203.0.113.{attempt}, 127.0.0.1"})
            codes.append(response.status)

    assert codes == [401, 401, 401, 401, 429, 429]


def test_a_forwarded_header_is_only_believed_from_the_local_proxy(line):
    """The dashboard listens on loopback and is published by a proxy on this
    same machine. A request whose PEER is not loopback did not come through
    that proxy, so its `X-Forwarded-For` is a string a stranger typed."""
    auth = load_admin().auth

    class Request:
        def __init__(self, remote, forwarded=None):
            self.remote = remote
            self.headers = {} if forwarded is None else {
                "X-Forwarded-For": forwarded}

    gate = auth.Auth(store=line.STORE, get_owners=lambda: line.OWNERS,
                     get_state=lambda: (line.NUMBERS, line.PROFILES))

    # through the proxy: the address the PROXY saw, which it appended last
    assert gate.client_ip(Request("127.0.0.1", "9.9.9.9, 100.64.0.7")) == "100.64.0.7"
    assert gate.client_ip(Request("::1", "9.9.9.9, 100.64.0.7")) == "100.64.0.7"
    assert gate.client_ip(Request("127.0.0.1")) == "127.0.0.1"
    # not through the proxy: the header is ignored entirely
    assert gate.client_ip(Request("198.51.100.7", "9.9.9.9")) == "198.51.100.7"
    assert gate.client_ip(Request("198.51.100.7", "9.9.9.9, 8.8.8.8")) == "198.51.100.7"
    assert gate.client_ip(Request(None)) == "unknown"


async def test_a_flood_from_many_addresses_locks_the_form_for_everyone(line,
                                                                       caplog):
    """A per-address lockout alone is only a speed limit per address. Twenty
    wrong codes in fifteen minutes from ANYWHERE closes the form for a minute,
    so a guesser spread across addresses runs into the same wall."""
    async with dashboard(line) as dash:
        with caplog.at_level(logging.WARNING, logger="atlas-phone"):
            for attempt in range(21):
                await dash.client.post(
                    "/sign-in", {"code": "no"},
                    headers={"X-Forwarded-For": f"198.51.100.{attempt}"})
            # an address that has never guessed, and the RIGHT code
            fresh = await dash.client.post(
                "/sign-in", {"code": "no"},
                headers={"X-Forwarded-For": "192.0.2.200"})
            right = await dash.client.post("/sign-in", {"code": "line-code"})

    assert fresh.status == 429
    assert right.status == 429
    assert int(right.headers["Retry-After"]) <= 60
    assert "dashboard sign-in LOCKED for every address" in caplog.text
    kinds = [e["kind"] for e in dash.store.list_events([], include_unscoped=True)]
    assert "dashboard_signin_locked" in kinds


async def test_a_good_sign_in_clears_the_failures(line):
    async with dashboard(line) as dash:
        for _ in range(3):
            await dash.client.post("/sign-in", {"code": "no"})
        await dash.client.sign_in("line-code")
        for _ in range(4):
            assert (await dash.client.post("/sign-in", {"code": "no"})).status == 401


# ----------------------------------------------------------------- CSRF ----

async def test_a_post_without_the_csrf_token_changes_nothing(line):
    async with dashboard(line) as dash:
        await dash.client.sign_in("line-code")
        session_id = dash.client.cookies["phone_session"]

        response = await dash.client.post("/sign-out", {})
        assert response.status == 403
        assert "out of date" in await response.text()
        assert dash.store.get_session(session_id) is not None   # still signed in


async def test_a_post_from_another_site_is_refused(line):
    async with dashboard(line) as dash:
        await dash.client.sign_in("line-code")
        token = await dash.client.csrf()
        response = await dash.client.post(
            "/sign-out", {"csrf": token},
            headers={"Origin": "https://evil.example"})
        assert response.status == 403
        assert "another website" in await response.text()


async def test_a_form_posted_by_a_real_browser_is_not_mistaken_for_another_site(line):
    """Every page here is served with `Referrer-Policy: no-referrer`, and
    browsers answer that by sending `Origin: null` on the forms those pages
    post. Reading that as "another website" refused every real form on the
    dashboard while every test that used a plain HTTP client passed."""
    async with dashboard(line) as dash:
        await dash.client.sign_in("line-code")
        token = await dash.client.csrf()
        response = await dash.client.post("/sign-out", {"csrf": token},
                                          headers={"Origin": "null"})
        assert response.status == 303, await response.text()


async def test_signing_out_ends_the_session_on_the_server(line):
    async with dashboard(line) as dash:
        await dash.client.sign_in("line-code")
        session_id = dash.client.cookies["phone_session"]
        token = await dash.client.csrf()

        response = await dash.client.post("/sign-out", {"csrf": token})
        assert response.status == 303
        assert response.headers["Location"] == "/sign-in"
        assert dash.store.get_session(session_id) is None
        assert (await dash.client.get("/", allow_redirects=False)).status == 302


async def test_signing_out_everywhere_ends_every_session(line):
    async with dashboard(line) as dash:
        phone = await (await dash.client.post("/sign-in", {"code": "line-code"})).text()
        assert phone is not None
        elsewhere = dash.store.create_session("_admin")

        await dash.client.sign_in("line-code")
        token = await dash.client.csrf()
        response = await dash.client.post("/sign-out-all", {"csrf": token})
        assert response.status == 303
        assert dash.store.get_session(elsewhere) is None


# -------------------------------------------------------------- headers ----

async def test_every_authenticated_response_carries_the_security_headers(line):
    async with dashboard(line) as dash:
        await dash.client.sign_in("line-code")
        response = await dash.client.get("/")
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "style-src 'self' https://fonts.googleapis.com" in csp
        assert "font-src https://fonts.gstatic.com" in csp
        assert "unsafe-inline" not in csp


async def test_the_redirect_to_sign_in_carries_them_too(line):
    async with dashboard(line) as dash:
        response = await dash.client.get("/", allow_redirects=False)
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Cache-Control"] == "no-store"


async def test_the_bundled_assets_are_served_from_this_machine(line):
    async with dashboard(line) as dash:
        css = await dash.client.get("/static/app.css")
        assert css.status == 200 and css.content_type == "text/css"
        htmx = await dash.client.get("/static/htmx.min.js")
        body = await htmx.text()
        assert htmx.status == 200
        assert "htmx 2.0.10" in body                 # vendored, version recorded
        assert "unpkg.com" in body                   # …and where it came from


async def test_the_sign_in_button_says_when_it_is_working(line):
    """A button that looks unpressed while the server is checking gets pressed
    again. The state is set by an external script served from this machine —
    the page's CSP allows no inline script, and none is used."""
    async with dashboard(line) as dash:
        page = await (await dash.client.get("/sign-in")).text()
        response = await dash.client.get("/static/app.js")
        script = await response.text()
        stylesheet = await dash.client.get("/static/app.css")

    assert response.status == 200
    assert response.content_type in ("application/javascript", "text/javascript")

    # cache-busted by the same bundle digest the stylesheet carries
    version = page.split("/static/app.css?v=", 1)[1].split('"', 1)[0]
    assert version and f'/static/app.js?v={version}"' in page
    assert stylesheet.status == 200

    # the words are in the template, where a reseller's copy lives; the script
    # only carries them from the attribute onto the button
    assert 'data-busy-label="Checking…"' in page
    assert "data-busy-label" in script
    assert "button.disabled = true" in script
    assert "eval(" not in script
    for handler in ("onsubmit", "onclick", "innerHTML"):
        assert handler not in script


# --------------------------------------------------------------- tenancy ---

async def test_an_owner_of_one_business_reads_only_that_business(tmp_path,
                                                                 monkeypatch):
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    svc = _import_service(tmp_path, monkeypatch,
                          extra_env={"ADMIN_TOKEN": "line-code"},
                          cfg_extra=OTHER_BUSINESS + ONE_BUSINESS)
    store = svc.STORE
    store.start_call("CA00000000000000000000000000000mine", "acme",
                     "+15550001234", "+15550001111", "b", "m")
    store.end_call("CA00000000000000000000000000000mine", "message_taken", "", 1, [])
    store.add_message("CA00000000000000000000000000000mine", "acme", "Dana",
                      "+15550001234", None, "a leaking sink", "Dana\nleaking sink")
    store.start_call("CA0000000000000000000000000theirs", "other",
                     "+15550009999", "+15550002222", "b", "m")
    store.end_call("CA0000000000000000000000000theirs", "message_taken", "", 1, [])
    store.add_message("CA0000000000000000000000000theirs", "other", "Marcus",
                      "+15550009999", None, "a hosting question",
                      "Marcus\nhosting question")

    async with dashboard(svc) as dash:
        await dash.client.sign_in("jo-code")
        page = await (await dash.client.get("/")).text()
        detail = await (await dash.client.get("/health/detail")).json()

    assert "a leaking sink" in page
    assert "a hosting question" not in page
    assert "Marcus" not in page
    assert detail["profiles"] == ["acme"]


async def test_the_model_screen_belongs_to_the_owner_of_the_whole_line(line):
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        page = await (await dash.client.get("/")).text()
        assert "/brain" not in page              # not even a link for them

        response = await dash.client.get("/brain")
        assert response.status == 403
        assert "manages the whole line" in await response.text()


async def test_a_login_removed_from_the_config_stops_working(line):
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        assert (await dash.client.get("/", allow_redirects=False)).status == 200
        line.OWNERS.pop("jo")
        assert (await dash.client.get("/", allow_redirects=False)).status == 302


def test_the_navigation_never_points_at_a_route_this_build_does_not_serve(line):
    """A screen lands task by task. A nav item for one that has not shipped
    would be a link into a 404 — so it is a startup failure instead."""
    admin = load_admin()
    urls = set()

    async def build():
        app = admin.build_admin_app(**dashboard_kwargs(line))
        urls.update(r.resource.canonical for r in app.router.routes())

    asyncio.run(build())
    assert urls, "the dashboard registered no routes at all"
    for item in admin.render.NAV:
        for entry in (item,) + tuple(item.children):
            if entry.url is not None:
                assert entry.url in urls, f"nav points at {entry.url}, a 404"


def test_the_dashboard_refuses_to_start_without_the_call_store(line):
    admin = load_admin()
    with pytest.raises(RuntimeError, match="call store"):
        admin.build_admin_app(**dashboard_kwargs(line, store=False))

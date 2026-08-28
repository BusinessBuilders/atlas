# tests/test_phone_agent_admin_overview.py — the two screens this dashboard
# opens on: the Overview, and the Brain screen behind it.
#
# The page this replaces answered "is my line working?" with a row of chips
# that were green whatever happened, a "recent calls" panel that grepped a log
# format the bridge had stopped writing, and no mention at all of the fact that
# the live model was licensed for testing only. These tests pin the answers:
#
#   * the line-status band is composed from five checks and is NEVER green
#     while one of them is failing — or merely unconfirmed;
#   * a model whose own label says "test only" gets a banner, not a chip;
#   * a panel that cannot read its data says so and the page still renders;
#   * an owner sees their own businesses and nothing else;
#   * a message that could not be delivered can be acknowledged, and that is
#     the only thing besides a successful delivery that clears /health;
#   * switching the model is confirmed, refuses an unreachable backend without
#     an override, and round-trips the whole config through the same
#     fail-closed path as every other save.
#
# No real caller data anywhere: +1555…/CAtest… and invented names only.
import sqlite3
import time
import tomllib

import pytest
from test_phone_agent_admin_auth import (ONE_BUSINESS, OTHER_BUSINESS,
                                         dashboard, health_ok, load_admin)
from test_phone_agent_plugin import _import_service

DAY = 86400.0

TWO_BRAINS = '''active_brain = "cloud_test"

[numbers]
"+15085550143" = "acme"

[brains.local_qwen]
label = "Private qwen"
base_url = "http://127.0.0.1:11434/v1"
model = "qwen2.5:7b-instruct"

[brains.cloud_test]
label = "Cloud GLM — test only"
base_url = "https://example.invalid/v1"
model = "glm-5.2"
api_key_env = "TEST_BRAIN_KEY"
extra_body = "{\\"thinking\\": {\\"type\\": \\"disabled\\"}}"

[profiles.acme]
business_name = "Acme Co"
services = "widget repair"
owner_name = "Jo"
greeting = "hi"
'''


@pytest.fixture
def line(tmp_path, monkeypatch):
    return _import_service(tmp_path, monkeypatch,
                           extra_env={"ADMIN_TOKEN": "line-code"})


@pytest.fixture
def two_brains(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_BRAIN_KEY", "not-a-real-key")
    return _import_service(tmp_path, monkeypatch,
                           extra_env={"ADMIN_TOKEN": "line-code"},
                           cfg_text=TWO_BRAINS)


def _real_call(svc, *, sid="CA000000000000000000000000000real", profile="acme",
               started=None, outcome="message_taken", no_info=False):
    svc.STORE.start_call(sid, profile, "+15550001234", "+15550001111",
                         "local_qwen", "m")
    svc.STORE.end_call(sid, "no_info_given" if no_info else outcome, "", 1, [])
    if started is not None:
        with sqlite3.connect(svc.STORE.path) as conn:
            conn.execute("UPDATE calls SET started_at=?, ended_at=?, duration_s=? "
                         "WHERE call_sid=?", (started, started + 72, 72.0, sid))
    return sid


async def _page(svc, path="/", *, code="line-code", health=health_ok):
    async with dashboard(svc, health=health) as dash:
        await dash.client.sign_in(code)
        response = await dash.client.get(path)
        assert response.status == 200, await response.text()
        return await response.text()


# ====================================================== the design system ===

def _luminance(hex_colour: str) -> float:
    raw = hex_colour.lstrip("#")
    channels = [int(raw[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
              for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _mix(a: str, b: str, part: float) -> str:
    """What CSS color-mix(in srgb, a <part>%, b) produces."""
    a, b = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(
        f"{round(int(a[i:i + 2], 16) * part + int(b[i:i + 2], 16) * (1 - part)):02x}"
        for i in (0, 2, 4))


def test_the_unbranded_palette_is_readable():
    """An install with no [branding] is the product's own face. These are the
    ratios WCAG 2.2 AA asks for: 4.5:1 for text, 3:1 for a control's outline
    and the focus ring."""
    colors = load_admin().render.DEFAULT_COLORS
    bg, card, fg = colors["bg"], colors["bg_elevated"], colors["fg"]

    assert _contrast(fg, bg) >= 4.5                       # body text
    assert _contrast(fg, card) >= 4.5
    assert _contrast(colors["fg_muted"], card) >= 4.5     # hint text
    assert _contrast(colors["fg_muted"], bg) >= 4.5
    # the button's label is the page colour on the accent, at 13px — small text
    assert _contrast(bg, colors["accent"]) >= 4.5
    assert _contrast(colors["accent"], card) >= 3.0       # the focus ring
    assert _contrast(_mix(fg, bg, 0.62), card) >= 3.0     # control borders
    for state in ("ok", "warn", "danger"):
        text = _mix(colors[state], fg, 0.5)
        assert _contrast(text, card) >= 4.5, state


def test_branding_becomes_css_custom_properties(two_brains):
    """Every colour and font on the page comes from the config, so a reseller's
    look is a setting and this vendor's is not compiled in."""
    admin = load_admin()
    branding = two_brains.Branding(
        vendor_name="Acme Digital", product_name="Front Desk",
        colors={"bg": "#101010", "accent": "#ff8800", "gold": "#ddaa22"},
        fonts={"body": "Inter"})
    css = admin.render.brand_css(branding)

    assert "--brand-bg: #101010;" in css
    assert "--brand-accent: #ff8800;" in css
    assert "--brand-warn: #ddaa22;" in css        # a brand's gold IS its amber
    assert "--brand-fg: #e8e8e8;" in css          # untouched keys keep default
    assert "--font-body: 'Inter'," in css
    assert "--font-display: system-ui" in css     # unnamed roles stay system
    assert admin.render.google_fonts_url(branding) == (
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700"
        "&display=swap")


def test_a_colour_that_is_not_a_colour_is_refused_loudly(two_brains, caplog):
    """These values are written into a stylesheet this server hands out."""
    import logging

    admin = load_admin()
    branding = two_brains.Branding(
        colors={"accent": "red; } body { display: none"},
        fonts={"body": "Inter'); @import url(https://evil.example/x.css"})
    with caplog.at_level(logging.WARNING, logger="atlas-phone"):
        css = admin.render.brand_css(branding)

    assert "display: none" not in css
    assert "evil.example" not in css
    assert "--brand-accent: #3b82f6;" in css      # the default, instead
    assert "is not a colour" in caplog.text
    assert "is not a font family name" in caplog.text
    assert admin.render.google_fonts_url(branding) == ""


# ================================================== the line-status band ====
# Pure: the verdict is computed from what the page already read, so it can be
# checked without a browser or a server.

def _snapshot(**overrides) -> dict:
    body = {
        "bridge": "ok", "model_backend": "ok", "probe_error": "",
        "probe_checked_at": time.time(), "brain": "local_qwen", "model": "m",
        "unreachable_brains": [], "ntfy_failures": 0,
        "last_delivery": {"ts": None, "call_sid": None, "ok": None, "error": ""},
    }
    body.update(overrides)
    return body


def _status(**kwargs):
    admin = load_admin()
    defaults = dict(health=_snapshot(), numbers={"+15550001111": "acme"},
                    profiles=("acme",), last_call_at=time.time(),
                    notify_failure=None)
    defaults.update(kwargs)
    return admin.status.line_status(**defaults)


def test_a_working_line_is_green():
    band = _status()
    assert band.level == "ok"
    assert band.headline == "Your line is answering"


def test_a_dead_model_takes_the_line_down():
    band = _status(health=_snapshot(model_backend="UNREACHABLE",
                                    probe_error="TimeoutError"))
    assert band.level == "down"
    assert "not answering" in band.headline
    assert "TimeoutError" in band.headline


def test_another_businesss_dead_model_is_still_amber():
    """A profile on its own backend must never be broken with a green band."""
    band = _status(health=_snapshot(unreachable_brains=["backup"]))
    assert band.level == "warn"
    assert "backup" in band.summary


def test_a_dead_model_that_is_not_this_owners_is_not_named_to_them():
    """On a shared line, a backend key is a name the reseller chose for
    somebody's business. An owner of one business is told about their own
    backends and never about anyone else's."""
    band = _status(health=_snapshot(unreachable_brains=["someone_elses"]),
                   owner_brains={"local_qwen"})
    assert band.level == "ok"
    assert "someone_elses" not in band.summary

    mine = _status(health=_snapshot(unreachable_brains=["mine"]),
                   owner_brains={"local_qwen", "mine"})
    assert mine.level == "warn"
    assert "mine" in mine.summary


def test_a_number_pointing_nowhere_takes_the_line_down():
    band = _status(numbers={})
    assert band.level == "down"
    assert "No phone number" in band.headline


def test_failing_alerts_name_the_target_they_are_failing_to():
    band = _status(health=_snapshot(ntfy_failures=3),
                   notify_failure={"target": "ntfy topic phone-acme",
                                   "error": "TimeoutError"})
    assert band.level == "warn"
    assert "ntfy topic phone-acme" in band.summary


def test_a_delivery_that_never_landed_is_amber():
    band = _status(health=_snapshot(
        last_delivery={"ts": time.time(), "call_sid": "CAx", "ok": False,
                       "error": "TimeoutError"}))
    assert band.level == "warn"


def test_an_unprobed_model_is_not_green_yet():
    band = _status(health=_snapshot(model_backend="pending"))
    assert band.level == "warn"
    assert "not been confirmed" in band.headline


def test_a_line_with_no_calls_is_not_confirmed_yet():
    band = _status(last_call_at=None)
    assert band.level == "warn"
    assert "not been confirmed" in band.headline


def test_a_line_quiet_for_a_day_is_not_confirmed_today():
    band = _status(last_call_at=time.time() - 2 * DAY)
    assert band.level == "warn"
    assert "24 hours" in band.summary


# ============================================================= the page =====

async def test_the_overview_tells_a_new_owner_what_to_do_with_the_real_number(line):
    page = await _page(line)
    assert "No calls yet" in page
    assert "(555) 000-1111" in page          # the number really configured
    assert "555-0142" not in page            # nothing from the design boards


async def test_the_overview_shows_the_days_numbers_and_the_week(line):
    noon = _local_noon()
    _real_call(line, sid="CA00000000000000000000000000today", started=noon)
    _real_call(line, sid="CA000000000000000000000000today2", started=noon - 60,
               no_info=True)
    _real_call(line, sid="CA0000000000000000000000000older",
               started=noon - 3 * DAY)

    page = await _page(line)
    assert "Calls today" in page
    assert "No calls yet" not in page
    assert "<svg" in page and "bar-handled" in page      # the 7-day chart


def _local_noon() -> float:
    """Midday today. Seeding "a minute ago" makes a test that fails for the two
    minutes after local midnight."""
    return time.mktime(time.localtime()[:3] + (12, 0, 0, 0, 0, -1))


async def test_a_test_call_is_not_business(line):
    line.STORE.start_call("CAtest_demo", "acme", "+15550001234", "+15550001111",
                          "b", "m", is_test=True)
    line.STORE.end_call("CAtest_demo", "message_taken", "", 1, [])
    line.STORE.add_message("CAtest_demo", "acme", "Sarah", "+15550001234", None,
                           "a demo message", "Sarah\na demo message")
    page = await _page(line)
    assert "a demo message" not in page
    assert "Sarah" not in page


async def test_the_latest_messages_panel_reads_the_store(line):
    sid = _real_call(line)
    line.STORE.add_message(sid, "acme", "Dana Whitfield", "+17745550142", None,
                           "a quote for a landscaping website",
                           "Dana\na quote for a landscaping website")
    page = await _page(line)
    assert "Dana Whitfield" in page
    assert "a quote for a landscaping website" in page
    assert "(774) 555-0142" in page                   # formatted for calling back
    assert "New" in page


async def test_a_business_that_keeps_its_own_pad_still_shows_its_messages(
        tmp_path, monkeypatch):
    """The old dashboard read ONE Markdown pad file, so a business pointed at
    its own pad looked like a business with no messages and the page had to
    carry a warning about it. Messages come from the store now: every business
    is there, whatever file its pad copy is written to."""
    svc = _import_service(
        tmp_path, monkeypatch, extra_env={"ADMIN_TOKEN": "line-code"},
        cfg_extra=f'messages_file = "{tmp_path / "acme-pad.md"}"\n')
    sid = _real_call(svc)
    svc.STORE.add_message(sid, "acme", "Marcus Tran", "+15085550177", None,
                          "a hosting renewal question", "Marcus\nhosting")

    page = await _page(svc)
    assert "Marcus Tran" in page
    assert "a hosting renewal question" in page
    assert "pad" not in page.lower()          # and no file jargon about it


async def test_a_store_that_cannot_be_read_gives_a_reason_not_a_500(line,
                                                                    monkeypatch):
    """This is the screen an owner opens when something is wrong. It is the
    last screen allowed to become an error page."""
    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(line.STORE, "list_messages", boom)
    page = await _page(line)
    assert "Could not read your messages: OperationalError: database is locked" in page
    assert "Calls today" in page                       # the rest still renders


async def test_every_panel_that_fails_says_which_one(line, monkeypatch):
    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(line.STORE, "stats", boom)
    monkeypatch.setattr(line.STORE, "list_events", boom)
    page = await _page(line)
    assert "Could not read your call numbers: OperationalError: disk I/O error" in page
    assert "Could not read what needs attention: OperationalError" in page


async def test_the_alerts_list_reads_seven_days_of_stored_events(line):
    now = time.time()
    line.STORE.add_event("acme", None, "error", "ntfy_push_failed",
                         "2 consecutive: TimeoutError")
    line.STORE.add_event("acme", None, "warning", "watchdog", "call ran long")
    line.STORE.add_event("acme", None, "error", "summarizer_failed", "long ago")
    line.STORE.add_event("acme", None, "info", "dashboard_signin",
                         "an ordinary sign-in")
    with sqlite3.connect(line.STORE.path) as conn:
        conn.execute("UPDATE events SET ts = ? WHERE kind = 'summarizer_failed'",
                     (now - 8 * DAY,))

    page = await _page(line)
    assert "A message alert did not reach your phone" in page
    assert "A call ran long and was wrapped up" in page
    assert "A call could not be written up" not in page      # older than 7 days
    assert "an ordinary sign-in" not in page                 # info is not an alert


async def test_the_band_says_how_old_the_answer_is_and_never_probes(line):
    """Health comes from the background refresher's cache. A page load that
    could start a model request was a way to spend the owner's money with a
    refresh key."""
    probed = []

    async def snapshot():
        probed.append(1)
        return health_ok.__wrapped__() if False else await health_ok()

    page = await _page(line, health=snapshot)
    assert "Checked" in page and "ago" in page
    assert len(probed) == 1                     # read once, from the cache


async def test_the_status_band_can_be_refreshed_on_its_own(line):
    async with dashboard(line) as dash:
        await dash.client.sign_in("line-code")
        response = await dash.client.get("/overview/status")
        band = await response.text()
    assert response.status == 200
    assert 'id="line-status"' in band
    assert "hx-get=\"/overview/status\"" in band
    assert "<html" not in band                   # a panel, not a whole page


async def test_health_detail_answers_json(line):
    async with dashboard(line) as dash:
        await dash.client.sign_in("line-code")
        body = await (await dash.client.get("/health/detail")).json()
    assert body["bridge"] == "ok"
    assert body["line_status"]["level"] in ("ok", "warn", "down")
    assert [c["name"] for c in body["line_status"]["checks"]] == [
        "answering", "brain", "phone_network", "numbers", "notifications"]


async def test_the_overview_speaks_the_owners_language(line):
    page = await _page(line)
    for jargon in ("journal", "TOML", "businesses.toml", "env file",
                   "profile key", "hot-apply", "ADMIN_TOKEN", "systemctl"):
        assert jargon not in page, f"{jargon!r} is on the owner's dashboard"


# ------------------------------------------------- production-safety banner --

async def test_a_test_only_model_gets_a_banner(two_brains):
    page = await _page(two_brains)
    assert "test model that isn't licensed for business use" in page
    assert "glm-5.2" in page
    assert 'role="alert"' in page


async def test_a_production_model_gets_no_banner(two_brains):
    two_brains.ACTIVE_BRAIN = "local_qwen"
    page = await _page(two_brains)
    assert "test model that isn't licensed" not in page


# ------------------------------------------- the undelivered-message alert --

async def test_an_undelivered_message_can_be_acknowledged(line):
    """/health stays red until the next message gets through OR the owner says
    they have seen this one. Nothing in the process clears it by itself."""
    line._note_delivery("CA000000000000000000000000000real", ok=False,
                        error="TimeoutError")
    assert line.public_health()[0] == 503

    async with dashboard(line, health=line.health_snapshot) as dash:
        await dash.client.sign_in("line-code")
        page = await (await dash.client.get("/")).text()
        assert "could not be delivered" in page
        assert "Mark as seen" in page

        token = await dash.client.csrf()
        response = await dash.client.post("/acknowledge-delivery",
                                          {"csrf": token})
        assert response.status == 303
        assert response.headers["Location"] == "/?acknowledged=1"

    assert line.LAST_DELIVERY["ok"] is True
    assert line.public_health()[0] == 200
    kinds = [e["kind"] for e in line.STORE.list_events([], include_unscoped=True)]
    assert "delivery_failure_acknowledged" in kinds


async def test_marking_nothing_as_seen_does_not_claim_it_did(line):
    """The alert can clear itself between the page being drawn and the button
    being pressed — saying "marked as seen" then would be a small lie."""
    assert line.LAST_DELIVERY["ok"] is None
    async with dashboard(line, health=line.health_snapshot) as dash:
        await dash.client.sign_in("line-code")
        token = await dash.client.csrf()
        response = await dash.client.post("/acknowledge-delivery",
                                          {"csrf": token})
        assert response.status == 303
        assert response.headers["Location"] == "/"


def _two_business_line(tmp_path, monkeypatch):
    """One line, two businesses, and an owner who holds only the first."""
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    return _import_service(tmp_path, monkeypatch,
                           extra_env={"ADMIN_TOKEN": "line-code"},
                           cfg_extra=OTHER_BUSINESS + ONE_BUSINESS)


def _failed_delivery_for(svc, profile: str, *, error: str) -> str:
    """A message alert that failed, on a call belonging to one business."""
    sid = f"CA00000000000000000000000000{profile[:5]:_<5}"
    svc.STORE.start_call(sid, profile, "+15550001234", "+15550001111", "b", "m")
    svc.STORE.end_call(sid, "message_taken", "", 1, [])
    svc._note_delivery(sid, ok=False, error=error)
    return sid


async def test_another_businesss_failed_delivery_is_not_this_owners_to_see(
        tmp_path, monkeypatch):
    """LAST_DELIVERY is one slot for the whole bridge. The banner printed it to
    everybody — so an owner on a shared line read an error naming another
    business's push target, and could clear their tripwire for them."""
    svc = _two_business_line(tmp_path, monkeypatch)
    _failed_delivery_for(svc, "other", error="TimeoutError: ntfy.other-co.example")

    async with dashboard(svc, health=svc.health_snapshot) as dash:
        await dash.client.sign_in("jo-code")           # owns "acme" only
        page = await (await dash.client.get("/")).text()

    assert "could not be delivered" not in page
    assert "Mark as seen" not in page
    assert "other-co.example" not in page


async def test_the_health_json_does_not_hand_over_the_same_error_either(
        tmp_path, monkeypatch):
    """Hiding the banner and leaving the same sentence one URL away would be a
    fix in appearance only — /health/detail carries the same field."""
    svc = _two_business_line(tmp_path, monkeypatch)
    _failed_delivery_for(svc, "other", error="TimeoutError: ntfy.other-co.example")

    async with dashboard(svc, health=svc.health_snapshot) as dash:
        await dash.client.sign_in("jo-code")
        scoped = await (await dash.client.get("/health/detail")).json()
        raw = await (await dash.client.get("/health/detail")).text()
        await dash.client.post("/sign-out",
                               {"csrf": await dash.client.csrf()})
        await dash.client.sign_in("line-code")
        whole_line = await (await dash.client.get("/health/detail")).json()

    assert "last_delivery" not in scoped
    assert "other-co.example" not in raw
    # the owner of the whole line still gets the whole picture
    assert whole_line["last_delivery"]["ok"] is False
    assert "other-co.example" in whole_line["last_delivery"]["error"]


async def test_an_owner_cannot_clear_another_businesss_failed_delivery(
        tmp_path, monkeypatch):
    svc = _two_business_line(tmp_path, monkeypatch)
    _failed_delivery_for(svc, "other", error="TimeoutError")
    assert svc.public_health()[0] == 503

    async with dashboard(svc, health=svc.health_snapshot) as dash:
        await dash.client.sign_in("jo-code")
        token = await dash.client.csrf()
        response = await dash.client.post("/acknowledge-delivery",
                                          {"csrf": token})
        assert response.status == 403
        assert "another business" in await response.text()

    assert svc.LAST_DELIVERY["ok"] is False            # still failing
    assert svc.public_health()[0] == 503
    kinds = [e["kind"] for e in svc.STORE.list_events([], include_unscoped=True)]
    assert "delivery_failure_acknowledged" not in kinds


async def test_the_owner_of_the_business_it_belongs_to_clears_it(
        tmp_path, monkeypatch):
    svc = _two_business_line(tmp_path, monkeypatch)
    _failed_delivery_for(svc, "acme", error="TimeoutError")

    async with dashboard(svc, health=svc.health_snapshot) as dash:
        await dash.client.sign_in("jo-code")
        page = await (await dash.client.get("/")).text()
        assert "could not be delivered" in page
        token = await dash.client.csrf()
        response = await dash.client.post("/acknowledge-delivery",
                                          {"csrf": token})
        assert response.status == 303
        assert response.headers["Location"] == "/?acknowledged=1"

    assert svc.LAST_DELIVERY["ok"] is True
    assert svc.public_health()[0] == 200


async def test_acknowledging_needs_the_csrf_token(line):
    line._note_delivery("CA000000000000000000000000000real", ok=False,
                        error="TimeoutError")
    async with dashboard(line, health=line.health_snapshot) as dash:
        await dash.client.sign_in("line-code")
        response = await dash.client.post("/acknowledge-delivery", {})
        assert response.status == 403
    assert line.LAST_DELIVERY["ok"] is False
    assert line.public_health()[0] == 503


# ========================================================= the Brain screen ==

async def test_the_brain_screen_shows_where_each_model_runs(two_brains):
    page = await _page(two_brains, "/brain")
    assert "Private qwen" in page
    assert "Private — on this machine" in page          # loopback base_url
    assert "Cloud GLM — test only" in page
    assert "Cloud" in page
    assert "Test only — not licensed for production" in page
    assert "Approved for business use" in page
    assert "Not checked yet" in page                     # honest about the probe
    assert "Answering now" in page


async def test_the_brain_screen_shows_the_last_check_and_when(two_brains):
    two_brains.BRAIN_HEALTH["local_qwen"] = {
        "reachable": True, "probe_error": "", "checked_at": time.time() - 20,
        "attempts": 0, "next_at": 0.0}
    two_brains.BRAIN_HEALTH["cloud_test"] = {
        "reachable": False, "probe_error": "ClientConnectorError: no route",
        "checked_at": time.time() - 60, "attempts": 2, "next_at": 0.0}
    page = await _page(two_brains, "/brain")
    assert "Answering" in page and "20 seconds ago" in page
    assert "Not answering (ClientConnectorError: no route)" in page


async def test_switching_asks_first_and_names_the_model(two_brains):
    page = await _page(two_brains, "/brain?switch=local_qwen")
    assert "<dialog" in page
    assert "Switch to Private qwen?" in page
    assert "qwen2.5:7b-instruct" in page
    assert "applies to the next call" in page
    assert 'name="csrf"' in page


async def test_a_switch_without_the_csrf_token_changes_nothing(two_brains):
    async with dashboard(two_brains) as dash:
        await dash.client.sign_in("line-code")
        response = await dash.client.post("/brain", {"brain": "local_qwen"})
        assert response.status == 403
    assert two_brains.ACTIVE_BRAIN == "cloud_test"


async def test_switching_to_a_model_that_did_not_answer_is_refused(two_brains):
    two_brains.BRAIN_HEALTH["local_qwen"] = {
        "reachable": False, "probe_error": "ConnectionRefusedError",
        "checked_at": time.time(), "attempts": 1, "next_at": 0.0}
    async with dashboard(two_brains) as dash:
        await dash.client.sign_in("line-code")
        token = await dash.client.csrf("/brain")
        response = await dash.client.post(
            "/brain", {"csrf": token, "brain": "local_qwen"})
        page = await response.text()

    assert response.status == 200
    assert "did not answer when it was last checked" in page
    assert "every caller hears an apology" in page
    assert two_brains.ACTIVE_BRAIN == "cloud_test"           # nothing changed


async def test_the_override_lets_the_owner_switch_anyway(two_brains):
    two_brains.BRAIN_HEALTH["local_qwen"] = {
        "reachable": False, "probe_error": "ConnectionRefusedError",
        "checked_at": time.time(), "attempts": 1, "next_at": 0.0}
    async with dashboard(two_brains) as dash:
        await dash.client.sign_in("line-code")
        token = await dash.client.csrf("/brain")
        response = await dash.client.post(
            "/brain", {"csrf": token, "brain": "local_qwen", "override": "on"})
        assert response.status == 303
    assert two_brains.ACTIVE_BRAIN == "local_qwen"


async def test_a_switch_keeps_every_other_setting_in_the_config_file(two_brains):
    """The switch re-writes the WHOLE file through the same validation as
    startup. A save that dropped a backend's key variable or its request body
    would take the line down the next time somebody switched back."""
    async with dashboard(two_brains) as dash:
        await dash.client.sign_in("line-code")
        token = await dash.client.csrf("/brain")
        response = await dash.client.post(
            "/brain", {"csrf": token, "brain": "local_qwen"})
        assert response.status == 303
        assert response.headers["Location"] == "/brain?switched=local_qwen"

    assert two_brains.ACTIVE_BRAIN == "local_qwen"
    with open(two_brains.BUSINESS_CONFIG, "rb") as f:
        written = tomllib.load(f)
    assert written["active_brain"] == "local_qwen"
    assert set(written["brains"]) == {"local_qwen", "cloud_test"}
    assert written["brains"]["cloud_test"]["api_key_env"] == "TEST_BRAIN_KEY"
    assert written["brains"]["cloud_test"]["extra_body"] == \
        '{"thinking": {"type": "disabled"}}'
    assert written["numbers"] == {"+15085550143": "acme"}
    assert written["profiles"]["acme"]["greeting"] == "hi"

    [change] = two_brains.STORE.list_config_changes()
    assert change["applied"] == 1
    assert change["actor"] == "_admin"
    assert "local_qwen" in change["summary"]


async def test_the_switched_confirmation_names_the_model_the_owner_recognises(
        two_brains):
    page = await _page(two_brains, "/brain?switched=local_qwen")
    assert "Switched. The next caller is answered by Private qwen." in page
    # the config key belongs in a link, never in a sentence the owner reads
    assert "answered by local_qwen" not in page


async def test_a_made_up_switched_value_puts_no_words_on_the_page(two_brains):
    page = await _page(two_brains, "/brain?switched=Call+this+number+now")
    assert "Switched" not in page
    assert "Call this number now" not in page


async def test_a_config_the_emitter_cannot_write_is_explained_not_a_500(
        tmp_path, monkeypatch):
    """The emitter refuses a hand-added table it cannot write back faithfully.
    The owner reads that sentence on the page — it must never escape as an
    aiohttp error screen."""
    monkeypatch.setenv("TEST_BRAIN_KEY", "not-a-real-key")
    svc = _import_service(
        tmp_path, monkeypatch, extra_env={"ADMIN_TOKEN": "line-code"},
        cfg_text=TWO_BRAINS + '\n[profiles.acme.departments]\nsales = "+15550002222"\n')

    async with dashboard(svc) as dash:
        await dash.client.sign_in("line-code")
        token = await dash.client.csrf("/brain")
        response = await dash.client.post(
            "/brain", {"csrf": token, "brain": "local_qwen"})
        page = await response.text()

    assert response.status == 200
    assert "Nothing was changed." in page
    assert "nested table" in page
    assert "profiles.acme.departments" in page
    assert svc.ACTIVE_BRAIN == "cloud_test"

    [change] = svc.STORE.list_config_changes()
    assert change["applied"] == 0
    assert "nested table" in change["reason"]


async def test_a_model_that_is_no_longer_configured_is_explained(two_brains):
    async with dashboard(two_brains) as dash:
        await dash.client.sign_in("line-code")
        token = await dash.client.csrf("/brain")
        response = await dash.client.post(
            "/brain", {"csrf": token, "brain": "vanished"})
        page = await response.text()
    assert response.status == 400
    assert "not set up on this line any more" in page
    assert two_brains.ACTIVE_BRAIN == "cloud_test"

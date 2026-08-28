# tests/test_phone_agent_admin_settings.py — changing how the line answers.
#
# The dashboard this replaces had ONE form and ONE button. Any validation error
# re-drew the page from the settings already in force, so an owner who rewrote a
# greeting, pasted three facts and mistyped a phone number lost the greeting and
# the facts and could not even see the number they had typed wrong. Deleting a
# business was a 13-pixel checkbox inside that same form, over a file with no
# backup and no history. These tests pin the replacement:
#
#   * a refused save comes back with EVERY submitted value still in it, and the
#     reason beside the field it belongs to (dashboard audit D.1);
#   * a save that works writes the config, backs the old one up, records what
#     changed, and hot-applies it — one path, `service.apply_config`;
#   * a form built before somebody else's save is refused with 409, not applied;
#   * switching a capability off is confirmed in words naming the consequence;
#   * hours round-trip into `hours.open_state`, times are read the way people
#     write them, and "always open" is said out loud;
#   * a number is validated, tidied, and refused when it is already on the line;
#   * a test alert is a REAL push, logged, with the real result shown;
#   * removing a business needs its name typed, is reversible for 30 days, and
#     unhooks its numbers;
#   * every read and every write is scoped to the businesses one login owns.
#
# No real caller data anywhere: +1555…/CAtest… and invented names only.
import asyncio
import dataclasses
import html
import os
import re
import time
import tomllib

import pytest
from test_phone_agent_admin_auth import (ONE_BUSINESS, dashboard, health_ok, load_admin)
from test_phone_agent_plugin import _import_service

DAY = 86400.0


@pytest.fixture
def line(tmp_path, monkeypatch):
    """One business, a whole-line login and a login scoped to that business."""
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    return _import_service(tmp_path, monkeypatch,
                           extra_env={"ADMIN_TOKEN": "line-code"},
                           cfg_extra=ONE_BUSINESS)


TWO_BUSINESSES = '''[numbers]
"+15550001111" = "acme"
"+15550002222" = "other"

[owners.jo]
token_env = "PHONE_OWNER_JO_TOKEN"
profiles = ["acme"]

[profiles.acme]
business_name = "Acme Co"
services = "widget repair"
owner_name = "Jo"
greeting = "hi"
facts = "Email: office@acme.test"

[profiles.other]
business_name = "Other Co"
services = "other work"
owner_name = "Sam"
greeting = "hello"
'''


@pytest.fixture
def two(tmp_path, monkeypatch):
    """Two businesses on one line, and a login that owns only the first."""
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    return _import_service(
        tmp_path, monkeypatch, extra_env={"ADMIN_TOKEN": "line-code"},
        cfg_text=TWO_BUSINESSES)


def _config_text(svc) -> str:
    """What is on disk right now, read and closed."""
    with open(svc.BUSINESS_CONFIG, encoding="utf-8") as f:
        return f.read()


def _backups(svc) -> list:
    directory = os.path.dirname(svc.BUSINESS_CONFIG)
    return [name for name in os.listdir(directory) if ".bak-" in name]


def _text(markup: str) -> str:
    """The page as one line of readable text: entities decoded, whitespace
    collapsed. These tests are about the words an owner reads, not about where
    a template happened to wrap them or which characters HTML escapes.
    """
    return re.sub(r"\s+", " ", html.unescape(str(markup)))


async def _signed_in(dash, code="line-code"):
    await dash.client.sign_in(code)
    return dash.client


async def _save(client, path: str, fields: dict, *, version=None,
                page="/settings/acme"):
    """Submit one section form the way the browser does, htmx and all."""
    body = _text(await (await client.get(page)).text())
    csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
    if version is None:
        version = body.split('name="version" value="', 1)[1].split('"', 1)[0]
    data = dict(fields)
    data["csrf"], data["version"] = csrf, str(version)
    return await client.post(path, data, headers={"HX-Request": "true"})


# ================================================= the one save path =========

def test_apply_config_writes_backs_up_and_records(line):
    """Every settings save goes through here: the file is written, the old one
    is kept, the change is written down, and the live line is answering on the
    new settings before the call returns."""
    profiles = dict(line.CONFIG.profiles)
    profiles["acme"] = dict(profiles["acme"], greeting="Thanks for calling.")
    config = dataclasses.replace(line.CONFIG, profiles=profiles)

    assert line.apply_config(config, "jo", "Changed the greeting") is None

    assert line.PROFILES["acme"]["greeting"] == "Thanks for calling."
    assert "Thanks for calling." in _config_text(line)
    assert _backups(line), "the config was replaced with no copy of the old one"
    rows = line.STORE.list_config_changes()
    assert rows[0]["summary"] == "Changed the greeting"
    assert rows[0]["actor"] == "jo"
    assert rows[0]["applied"] == 1
    assert "+greeting" in rows[0]["diff"] or "greeting" in rows[0]["diff"]


def test_a_refused_save_changes_nothing_and_says_why(line):
    """Fail-closed: an invalid config leaves the file and the live line alone,
    and the refusal is written down too — "I changed it and nothing happened"
    has to have an answer."""
    before = _config_text(line)
    profiles = dict(line.CONFIG.profiles)
    profiles["acme"] = dict(profiles["acme"], forward_to="call my mobile")
    config = dataclasses.replace(line.CONFIG, profiles=profiles)

    reason = line.apply_config(config, "jo", "Changed the transfer number")

    assert reason and "E.164" in reason
    assert _config_text(line) == before
    assert "forward_to" not in line.PROFILES["acme"]
    row = line.STORE.list_config_changes()[0]
    assert row["applied"] == 0 and "E.164" in row["reason"]


def test_the_recorded_diff_carries_both_versions_exactly(line):
    """Activity's "put this back" rebuilds the previous file from the stored
    diff, so the diff has to be a complete record of both — not three lines of
    context around a change."""
    before = _config_text(line)
    profiles = dict(line.CONFIG.profiles)
    profiles["acme"] = dict(profiles["acme"], greeting="Good morning.")
    line.apply_config(dataclasses.replace(line.CONFIG, profiles=profiles),
                      "jo", "Changed the greeting")

    diff = line.STORE.list_config_changes()[0]["diff"]
    assert line.config_from_diff(diff, side="before") == before
    assert line.config_from_diff(diff, side="after") == _config_text(line)


# ============================================ removed businesses in the file ==

DELETED_CONFIG = '''[numbers]
"+15550001111" = "acme"

[profiles.acme]
business_name = "Acme Co"
services = "widget repair"
owner_name = "Jo"
greeting = "hi"

[deleted_profiles.oldco]
business_name = "Old Co"
services = "nothing now"
owner_name = "Sam"
greeting = "hello"
deleted_at = "2026-08-01T09:00:00-04:00"
'''


def test_a_removed_business_survives_a_save_word_for_word(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch, cfg_text=DELETED_CONFIG)
    assert svc.CONFIG.deleted_profiles["oldco"]["business_name"] == "Old Co"
    assert "oldco" not in svc.PROFILES

    text = svc.config_toml(svc.CONFIG)
    assert "[deleted_profiles.oldco]" in text
    assert 'deleted_at = "2026-08-01T09:00:00-04:00"' in text
    # and it round-trips through the validator unchanged
    assert svc.parse_config(tomllib.loads(text)).deleted_profiles \
        == svc.CONFIG.deleted_profiles


def test_a_removed_business_without_a_date_is_refused(tmp_path, monkeypatch):
    """"Restorable for 30 days" is a promise the file has to be able to keep."""
    with pytest.raises(SystemExit):
        _import_service(tmp_path, monkeypatch,
                        cfg_text=DELETED_CONFIG.replace(
                            'deleted_at = "2026-08-01T09:00:00-04:00"\n', ""))


def test_a_removed_business_cannot_shadow_a_live_one(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        _import_service(tmp_path, monkeypatch,
                        cfg_text=DELETED_CONFIG.replace(
                            "[deleted_profiles.oldco]",
                            "[deleted_profiles.acme]"))


# ==================================================== the settings screen ====

async def test_the_settings_screen_shows_this_business_in_owner_words(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/settings")).text())

    assert "Acme Co" in page
    assert 'id="business_name"' in page and 'for="business_name"' in page
    assert 'id="greeting"' in page
    for jargon in ("profile key", "businesses.toml", "TOML", "journalctl",
                   "hot-apply", "env file"):
        assert jargon not in page, f"{jargon!r} is on the settings screen"


async def test_saving_a_section_applies_it_and_says_so(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        response = await _save(dash.client, "/settings/acme/identity", {
            "business_name": "Acme Repairs", "services": "widget repair",
            "owner_name": "Jo"})
        body = _text(await response.text())

    assert response.status == 200, body
    assert "Saved — live on the next call." in body
    assert 'aria-live="polite"' in body
    assert line.PROFILES["acme"]["business_name"] == "Acme Repairs"


async def test_a_refused_section_keeps_every_word_that_was_typed(line):
    """Dashboard audit D.1, the highest-impact defect in the old file: the
    re-render comes from the SUBMITTED values, never from the live config."""
    async with dashboard(line) as dash:
        await _signed_in(dash)
        response = await _save(dash.client, "/settings/acme/identity", {
            "business_name": "", "services": "widget repair and restoration",
            "owner_name": "Josephine"})
        body = _text(await response.text())

    assert response.status == 400
    # what they typed is still in the boxes
    assert 'value="widget repair and restoration"' in body
    assert 'value="Josephine"' in body
    # the reason is beside the field that caused it
    assert "The business name is needed" in body
    assert 'aria-invalid="true"' in body
    # and nothing on the live line moved
    assert line.PROFILES["acme"]["business_name"] == "Acme Co"
    assert line.PROFILES["acme"]["owner_name"] == "Jo"


async def test_a_form_built_before_somebody_elses_save_is_refused(line):
    """A tab left open on another device must not silently overwrite the save
    somebody else has made since."""
    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/settings/acme")).text())
        csrf = page.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        stale = page.split('name="version" value="', 1)[1].split('"', 1)[0]

        # somebody else saves from another device in the meantime
        line.apply_config(
            dataclasses.replace(line.CONFIG, profiles={
                "acme": dict(line.CONFIG.profiles["acme"],
                             owner_name="Josephine")}),
            "line", "Changed the business details for Acme Co")

        response = await dash.client.post(
            "/settings/acme/identity",
            {"csrf": csrf, "version": stale, "business_name": "Acme Repairs",
             "services": "widget repair", "owner_name": "Jo"},
            headers={"HX-Request": "true"})
        body = _text(await response.text())

    assert response.status == 409
    assert "out of date" in body
    # the other device's work is untouched, and so is everything else
    assert line.PROFILES["acme"]["owner_name"] == "Josephine"
    assert line.PROFILES["acme"]["business_name"] == "Acme Co"


async def test_the_greeting_section_shows_what_the_caller_hears(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/settings/acme")).text())

    spoken = line.opening_line(line.PROFILES["acme"], None)
    assert "AI assistant" in spoken and "recorded" in spoken
    assert spoken in page
    assert "seconds at a normal speaking pace" in page


async def test_a_greeting_that_is_too_long_comes_back_with_every_word_in_it(line):
    """The greeting is the section an owner writes and rewrites, and its limit
    lives somewhere else (`config_edit.LIMITS`) than the sections whose
    keep-your-typing behaviour is already pinned. Losing 611 typed characters
    to a refusal is the exact failure this dashboard was rebuilt to remove."""
    typed = ("Thanks for calling Acme Co, this is the assistant. " * 13)[:610] + "!"
    assert len(typed) == 611

    async with dashboard(line) as dash:
        await _signed_in(dash)
        response = await _save(dash.client, "/settings/acme/greeting", {
            "greeting": typed, "ai_disclosure": "on", "recording_notice": "on",
            "ai_disclosure_text": "I'm the AI assistant for {business_name}.",
            "recording_notice_text": "This call may be recorded and transcribed."})
        body = await response.text()

    assert response.status == 400
    assert "That is 611 characters" in _text(body)
    # every character back, not a truncation and not the saved value
    assert typed in html.unescape(body)
    assert line.PROFILES["acme"]["greeting"] == "hi"


async def test_switching_off_a_notice_needs_the_waiver_on_the_record(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        response = await _save(dash.client, "/settings/acme/greeting", {
            "greeting": "hi", "recording_notice": "on",
            "ai_disclosure_text": "I'm the AI assistant for {business_name}.",
            "recording_notice_text": "This call may be recorded and transcribed."})
        body = _text(await response.text())

    assert response.status == 400
    assert "right to be told they are speaking to a machine" in body
    assert line.profile_setting(line.PROFILES["acme"], "ai_disclosure") is True

    async with dashboard(line) as dash:
        await _signed_in(dash)
        response = await _save(dash.client, "/settings/acme/greeting", {
            "greeting": "hi", "recording_notice": "on",
            "ack_disclosure_waived": "on",
            "ai_disclosure_text": "I'm the AI assistant for {business_name}.",
            "recording_notice_text": "This call may be recorded and transcribed."})

    assert response.status == 200, await response.text()
    assert line.profile_setting(line.PROFILES["acme"], "ai_disclosure") is False


async def test_facts_are_rows_and_the_empty_state_is_honest(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        response = await _save(dash.client, "/settings/acme/facts",
                               {"fact": ["Hours: 9 to 5 Eastern",
                                         "Email: office@acme.test", ""]})
        assert response.status == 200, await response.text()
        assert line.PROFILES["acme"]["facts"] == (
            "Hours: 9 to 5 Eastern\nEmail: office@acme.test")

        # clearing them all disables the agent's ability to answer anything,
        # so it is confirmed in those words
        refused = await _save(dash.client, "/settings/acme/facts", {"fact": ""})
        body = _text(await refused.text())
        assert refused.status == 400
        assert "will not be able to answer a single question" in body
        assert 'name="confirm_disable"' in body
        assert line.PROFILES["acme"]["facts"]

        gone = await _save(dash.client, "/settings/acme/facts",
                           {"fact": "", "confirm_disable": "on"})
        assert gone.status == 200, await gone.text()
        assert "facts" not in line.PROFILES["acme"]
        # and the empty state on the panel says what that costs, in the
        # owner's own terms rather than leaving a blank box
        assert "single question about your business" in await gone.text()


async def test_a_transfer_number_is_read_the_way_people_write_it(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        response = await _save(dash.client, "/settings/acme/transfer", {
            "transfer_on": "on", "forward_to": "(774) 555-0142",
            "phrase": list(line.DEFAULT_TRANSFER_PHRASES)})
        assert response.status == 200, await response.text()

    assert line.PROFILES["acme"]["forward_to"] == "+17745550142"
    # the standard phrase list is not written back out as an edit of itself
    assert "transfer_phrases" not in line.PROFILES["acme"]


async def test_a_number_that_is_not_a_number_keeps_what_was_typed(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        response = await _save(dash.client, "/settings/acme/transfer", {
            "transfer_on": "on", "forward_to": "ring my mobile",
            "phrase": ["operator"]})
        body = _text(await response.text())

    assert response.status == 400
    assert "ring my mobile" in body
    assert "Enter a full phone number with area code" in body
    assert "forward_to" not in line.PROFILES["acme"]


async def test_turning_transfer_off_names_the_consequence(line):
    line.apply_config(
        dataclasses.replace(
            line.CONFIG,
            profiles={"acme": dict(line.CONFIG.profiles["acme"],
                                   forward_to="+15085550100")}),
        "setup", "Set a transfer number")
    async with dashboard(line) as dash:
        await _signed_in(dash)
        refused = await _save(dash.client, "/settings/acme/transfer",
                              {"phrase": ["operator"]})
        body = _text(await refused.text())
        assert refused.status == 400
        assert "no longer be able to reach a person" in body
        assert line.PROFILES["acme"]["forward_to"] == "+15085550100"

        done = await _save(dash.client, "/settings/acme/transfer",
                           {"phrase": ["operator"], "confirm_disable": "on"})
        assert done.status == 200, await done.text()
    assert "forward_to" not in line.PROFILES["acme"]


async def test_the_standard_phrases_are_in_the_boxes_not_a_hidden_rule(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/settings/acme")).text())

    for phrase in ("operator", "speak to a person", "goodbye", "nothing else"):
        assert f'value="{phrase}"' in page, phrase
    assert "standard phrases every line starts with" in page


async def test_advanced_shows_settings_this_bridge_does_not_read(tmp_path,
                                                                monkeypatch):
    """Task 5a carry-forward: a hand-written setting nothing acts on is kept by
    every save, and the owner is told which one it is."""
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    svc = _import_service(tmp_path, monkeypatch,
                          extra_env={"ADMIN_TOKEN": "line-code"},
                          cfg_extra='hurs = "9-5"\n' + ONE_BUSINESS)
    async with dashboard(svc) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/settings/acme")).text())

    assert "Settings this line does not read" in page
    assert "hurs" in page


async def test_one_owner_cannot_change_another_businesss_settings(two):
    async with dashboard(two) as dash:
        await _signed_in(dash, "jo-code")
        page = await dash.client.get("/settings/other")
        assert page.status == 404
        assert "Other Co" not in await page.text()

        response = await _save(dash.client, "/settings/other/identity",
                               {"business_name": "Taken Over",
                                "services": "x", "owner_name": "y"},
                               page="/settings/acme")
        assert response.status == 404
    assert two.PROFILES["other"]["business_name"] == "Other Co"


# ============================================================== the hours ====

async def test_hours_round_trip_into_the_answering_code(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/hours/acme")).text())
        assert "Always open" in body
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = body.split('name="version" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/hours/acme", {
            "csrf": csrf, "version": version,
            "timezone": "America/New_York",
            "open_mon": "on", "from_mon": "9:00 AM", "to_mon": "5:00 PM",
            "open_tue": "on", "from_tue": "09:00", "to_tue": "17:00",
            "after_hours": "message",
            "after_hours_greeting": "We're closed — I can take a message.",
            "holiday": ["2026-11-26", "2026-12-24..2026-12-26"],
        })
        assert response.status == 303, await response.text()

    profile = line.PROFILES["acme"]
    assert profile["hours"] == {"mon": "09:00-17:00", "tue": "09:00-17:00"}
    assert profile["holidays"] == ["2026-11-26", "2026-12-24..2026-12-26"]

    from datetime import datetime
    from zoneinfo import ZoneInfo
    import hours as hours_lib

    zone = ZoneInfo("America/New_York")
    open_monday = datetime(2026, 8, 31, 10, 0, tzinfo=zone)     # a Monday
    closed_sunday = datetime(2026, 8, 30, 10, 0, tzinfo=zone)
    thanksgiving = datetime(2026, 11, 26, 10, 0, tzinfo=zone)
    assert hours_lib.open_state(profile, open_monday).open is True
    assert hours_lib.open_state(profile, closed_sunday).open is False
    assert hours_lib.open_state(profile, thanksgiving).reason == "holiday"


async def test_a_time_nobody_can_read_keeps_the_rest_of_the_form(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/hours/acme")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = body.split('name="version" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/hours/acme", {
            "csrf": csrf, "version": version, "timezone": "America/New_York",
            "open_mon": "on", "from_mon": "half nine", "to_mon": "5:00 PM",
            "after_hours": "message", "after_hours_greeting": "Closed today.",
            "holiday": "2026-11-26",
        })
        page = _text(await response.text())

    assert response.status == 400
    assert "half nine" in page                    # what they typed is still there
    assert "Closed today." in page
    assert 'value="2026-11-26"' in page
    assert "not a time this line can read" in page
    assert "hours" not in line.PROFILES["acme"]


async def test_hours_without_a_timezone_are_refused_with_the_reason(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/hours/acme")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = body.split('name="version" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/hours/acme", {
            "csrf": csrf, "version": version, "timezone": "",
            "open_mon": "on", "from_mon": "9:00 AM", "to_mon": "5:00 PM",
            "after_hours": "message", "after_hours_greeting": "",
        })
        page = _text(await response.text())

    assert response.status == 400
    assert "need a time zone" in page


async def test_after_hours_transfer_needs_somewhere_to_transfer_to(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/hours/acme")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = body.split('name="version" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/hours/acme", {
            "csrf": csrf, "version": version, "timezone": "America/New_York",
            "after_hours": "transfer", "after_hours_greeting": "",
        })
        page = _text(await response.text())

    assert response.status == 400
    assert "nowhere to go" in page


# ============================================================= the numbers ===

async def test_numbers_shows_the_webhook_and_whether_it_has_ever_fired(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/numbers")).text())
    assert "(555) 000-1111" in page
    assert line.PUBLIC_BASE + "/voice/incoming" in page
    assert "Never seen a call from the phone network" in page

    line.STORE.start_call("CA000000000000000000000000000num", "acme",
                          "+15550009999", "+15550001111", "default", "m")
    line.STORE.end_call("CA000000000000000000000000000num", "message_taken",
                        "", 1, [])
    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/numbers")).text())
    assert "Verified" in page


async def test_a_number_already_on_the_line_is_refused_by_name(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/numbers")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = body.split('name="version" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/numbers", {
            "csrf": csrf, "version": version,
            "business_for:+15550001111": "acme",
            "new_number": "(555) 000-1111", "new_business": "acme"})
        page = _text(await response.text())

    assert response.status == 400
    assert "already on this line" in page
    assert len(line.NUMBERS) == 1


async def test_a_number_that_is_not_a_number_is_refused(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/numbers")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = body.split('name="version" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/numbers", {
            "csrf": csrf, "version": version,
            "business_for:+15550001111": "acme",
            "new_number": "the shop phone", "new_business": "acme"})
        page = _text(await response.text())

    assert response.status == 400
    assert "the shop phone" in page
    assert "Enter a full phone number with area code" in page
    assert len(line.NUMBERS) == 1


async def test_a_new_number_is_tidied_into_the_form_the_network_wants(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/numbers")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = body.split('name="version" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/numbers", {
            "csrf": csrf, "version": version,
            "business_for:+15550001111": "acme",
            "new_number": "(555) 000-2222", "new_business": "acme"})
        assert response.status == 303, await response.text()

    assert line.NUMBERS["+15550002222"] == "acme"


async def test_a_scoped_owner_sees_their_numbers_read_only(two):
    async with dashboard(two) as dash:
        await _signed_in(dash, "jo-code")
        page = _text(await (await dash.client.get("/numbers")).text())
        assert "(555) 000-1111" in page
        assert "(555) 000-2222" not in page
        assert "Save numbers" not in page

        body = _text(await (await dash.client.get("/settings/acme")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        refused = await dash.client.post("/numbers", {
            "csrf": csrf, "version": "1",
            "business_for:+15550002222": "acme"})
        assert refused.status == 403
    assert two.NUMBERS["+15550002222"] == "other"


# ======================================================== the notifications ==

async def test_the_send_test_button_really_sends_and_says_what_happened(
        line, monkeypatch):
    sent = {}

    async def fake_push(target, *, title, body, priority=None, session=None):
        sent.update(url=target.ntfy_url, topic=target.ntfy_topic, body=body,
                    title=title, priority=priority)
        return True, ""

    monkeypatch.setattr(line, "push_ntfy", fake_push)
    line.apply_config(
        dataclasses.replace(
            line.CONFIG,
            profiles={"acme": dict(line.CONFIG.profiles["acme"],
                                   ntfy_url="https://push.acme.test",
                                   ntfy_topic="acme-phone")}),
        "setup", "Set a push target")

    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/notifications/acme")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/notifications/acme/test",
                                          {"csrf": csrf})
        page = _text(await response.text())

    assert response.status == 200, page
    assert sent["url"] == "https://push.acme.test"
    assert sent["topic"] == "acme-phone"
    assert "Test alert sent to" in page
    logged = line.STORE.list_notify(["acme"])
    assert logged and logged[0]["ok"] == 1
    assert logged[0]["target"] == "ntfy_test"


async def test_a_test_that_failed_says_so_loudly(line, monkeypatch):
    async def fake_push(target, *, title, body, priority=None, session=None):
        return False, "ConnectionError: name or service not known"

    monkeypatch.setattr(line, "push_ntfy", fake_push)
    line.apply_config(
        dataclasses.replace(
            line.CONFIG,
            profiles={"acme": dict(line.CONFIG.profiles["acme"],
                                   ntfy_url="https://push.acme.test",
                                   ntfy_topic="acme-phone")}),
        "setup", "Set a push target")

    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/notifications/acme")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/notifications/acme/test",
                                          {"csrf": csrf})
        page = _text(await response.text())

    assert response.status == 400
    assert "did not go through" in page
    assert "name or service not known" in page
    logged = line.STORE.list_notify(["acme"])
    assert logged and logged[0]["ok"] == 0


async def test_a_line_with_nowhere_to_push_refuses_the_test_in_words(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/notifications/acme")).text())
        assert "No push address is set up" in body
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/notifications/acme/test",
                                          {"csrf": csrf})
        page = _text(await response.text())
    assert response.status == 400
    assert "nowhere to send a test" in page


async def test_the_line_default_is_labelled_as_the_default(tmp_path,
                                                           monkeypatch):
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    svc = _import_service(
        tmp_path, monkeypatch,
        extra_env={"ADMIN_TOKEN": "line-code",
                   "NTFY_URL": "https://push.line.test",
                   "NTFY_TOPIC": "the-line"},
        cfg_extra=ONE_BUSINESS)
    async with dashboard(svc) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/notifications/acme")).text())
    assert "using the line" in page and "own alert address" in page
    assert "https://push.line.test/the-line" in page


async def test_a_scoped_owner_is_not_shown_the_lines_own_push_address(
        tmp_path, monkeypatch):
    """Two businesses on one line can both fall back to the line's own push
    address. Naming that address to the owner of one hands them the
    subscription to their neighbours' messages, and they cannot change the
    line's default anyway — the answer is a topic of their own, which the
    screen already asks them for."""
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    svc = _import_service(
        tmp_path, monkeypatch,
        extra_env={"ADMIN_TOKEN": "line-code",
                   "NTFY_URL": "https://push.line.test",
                   "NTFY_TOPIC": "neighbours-topic"},
        cfg_extra=ONE_BUSINESS)

    async def fake_push(target, *, title, body, priority=None, session=None):
        return True, ""

    monkeypatch.setattr(svc, "push_ntfy", fake_push)
    async with dashboard(svc) as dash:
        await _signed_in(dash, "jo-code")
        raw = await (await dash.client.get("/notifications/acme")).text()
        csrf = raw.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/notifications/acme/test",
                                          {"csrf": csrf})
        receipt = await response.text()

    # They are still told WHERE their messages go, in words…
    assert "using the line" in _text(raw) and "own alert address" in _text(raw)
    assert response.status == 200, _text(receipt)
    assert "Test alert sent to the line's own alert address" in _text(receipt)
    # …and the address itself is in neither page. Hunted in the RAW markup,
    # because most of a value reaches a page inside a value= attribute.
    for page in (raw, receipt):
        assert "push.line.test" not in page
        assert "neighbours-topic" not in page


# ============================================================== the activity ==

async def test_activity_lists_the_change_with_its_diff_and_puts_it_back(line):
    line.apply_config(
        dataclasses.replace(line.CONFIG, profiles={
            "acme": dict(line.CONFIG.profiles["acme"],
                         greeting="Good morning, Acme.")}),
        "jo", "Changed the greeting callers hear for Acme Co")
    assert line.PROFILES["acme"]["greeting"] == "Good morning, Acme."

    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/activity")).text())
        assert "Changed the greeting callers hear for Acme Co" in page
        assert "Good morning, Acme." in page          # the diff on expand
        change_id = str(line.STORE.list_config_changes()[0]["id"])
        assert f'href="/activity?restore={change_id}"' in page

        # the button opens a confirm; the confirm is what posts
        dialog = _text(await (await dash.client.get(
            f"/activity?restore={change_id}")).text())
        assert "Everything changed since then will be undone" in dialog
        assert 'name="confirm" value="on"' in dialog
        csrf = dialog.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post(
            "/activity/restore",
            {"csrf": csrf, "change_id": change_id, "confirm": "on"})
        assert response.status == 303, await response.text()

    assert line.PROFILES["acme"]["greeting"] == "hi"
    assert line.STORE.list_config_changes()[0]["summary"].startswith(
        "Put the settings back")


async def test_activity_shows_sign_ins_and_what_the_line_reported(line):
    line.STORE.add_event(None, None, "warning", "dashboard_signin_failed",
                         "wrong access code from 127.0.0.1")
    line.STORE.add_event("acme", None, "error", "brain_unreachable",
                         "the model did not answer")
    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/activity")).text())

    assert "Someone tried to sign in with the wrong access code" in page
    assert "The model that answers calls did not respond" in page


async def test_an_owner_of_one_business_is_not_told_there_are_no_sign_ins(two):
    """A sign-in belongs to the whole line, not to one business, so a scoped
    owner is shown none of them. "No sign-in has been recorded yet" was a lie
    to the very person who had just signed in to read that page."""
    two.STORE.add_event(None, None, "warning", "dashboard_signin_failed",
                        "wrong access code from 127.0.0.1")
    async with dashboard(two) as dash:
        await _signed_in(dash, "jo-code")
        scoped = _text(await (await dash.client.get("/activity")).text())
    assert "No sign-in has been recorded yet" not in scoped
    assert "only shown to the login that manages all of it" in scoped
    assert "wrong access code" not in scoped

    async with dashboard(two) as dash:
        await _signed_in(dash)
        whole = _text(await (await dash.client.get("/activity")).text())
    assert "only shown to the login that manages all of it" not in whole
    assert "Someone tried to sign in with the wrong access code" in whole


async def test_a_scoped_owner_only_sees_changes_that_touched_their_business(two):
    two.apply_config(
        dataclasses.replace(two.CONFIG, profiles=dict(
            two.CONFIG.profiles,
            other=dict(two.CONFIG.profiles["other"],
                       greeting="Other Co, secret greeting"))),
        "line", "Changed the greeting callers hear for Other Co")
    two.apply_config(
        dataclasses.replace(two.CONFIG, profiles=dict(
            two.CONFIG.profiles,
            acme=dict(two.CONFIG.profiles["acme"], greeting="Acme, hello"))),
        "line", "Changed the greeting callers hear for Acme Co")

    async with dashboard(two) as dash:
        await _signed_in(dash, "jo-code")
        page = _text(await (await dash.client.get("/activity")).text())

    # the sentence is rebuilt from the lines that are theirs — the stored one
    # describes the whole save and is not theirs to be told
    assert "Settings changed for Acme Co" in page
    assert "Changed the greeting callers hear for Acme Co" not in page
    assert "Other Co" not in page
    assert "secret greeting" not in page
    # and the whole-line restore is not offered to them
    assert 'action="/activity/restore"' not in page


async def test_a_scoped_owner_cannot_restore_a_whole_version(two):
    two.apply_config(
        dataclasses.replace(two.CONFIG, profiles=dict(
            two.CONFIG.profiles,
            acme=dict(two.CONFIG.profiles["acme"], greeting="Acme, hello"))),
        "line", "Changed the greeting callers hear for Acme Co")
    change_id = two.STORE.list_config_changes()[0]["id"]

    async with dashboard(two) as dash:
        await _signed_in(dash, "jo-code")
        body = _text(await (await dash.client.get("/settings/acme")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post(
            "/activity/restore",
            {"csrf": csrf, "change_id": str(change_id), "confirm": "on"})

    assert response.status == 403
    assert two.PROFILES["acme"]["greeting"] == "Acme, hello"


# ====================================================== removing a business ==

async def test_removing_a_business_needs_its_name_typed(two):
    async with dashboard(two) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/business/other/delete")).text())
        assert "Type “Other Co” exactly" in page
        csrf = page.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = page.split('name="version" value="', 1)[1].split('"', 1)[0]
        wrong = await dash.client.post("/business/other/delete", {
            "csrf": csrf, "version": version, "confirm": "other"})
        assert wrong.status == 400
        assert "not the name of this business" in _text(await wrong.text())
    assert "other" in two.PROFILES


async def test_a_business_a_login_depends_on_cannot_be_removed(two):
    """`[owners.jo]` covers Acme and nothing else. Removing Acme would leave
    that sign-in opening nothing, which the config refuses — so the screen says
    so in words before offering the button, not afterwards in the validator's."""
    async with dashboard(two) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/business/acme/delete")).text())
        assert "covers this business and nothing else" in page
        assert 'name="confirm"' not in page
    assert "acme" in two.PROFILES


async def test_removing_a_business_is_reversible_and_unhooks_its_numbers(two):
    async with dashboard(two) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/business/other/delete")).text())
        csrf = page.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = page.split('name="version" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/business/other/delete", {
            "csrf": csrf, "version": version, "confirm": "Other Co"})
        assert response.status == 303, await response.text()

        assert "other" not in two.PROFILES
        assert "+15550002222" not in two.NUMBERS
        assert "+15550001111" in two.NUMBERS          # the rest of the line is untouched
        assert two.CONFIG.deleted_profiles["other"]["business_name"] == "Other Co"
        assert two.CONFIG.deleted_profiles["other"]["deleted_at"]

        activity = _text(await (await dash.client.get("/activity")).text())
        assert "Removed businesses" in activity
        assert "Other Co" in activity
        assert 'href="/activity?restore-business=other"' in activity
        dialog = _text(await (await dash.client.get(
            "/activity?restore-business=other")).text())
        assert "Bring Other Co back?" in dialog
        csrf = dialog.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        back = await dash.client.post(
            "/activity/restore-business",
            {"csrf": csrf, "business": "other", "confirm": "on"})
        assert back.status == 303, await back.text()

    assert two.PROFILES["other"]["business_name"] == "Other Co"
    assert "deleted_at" not in two.PROFILES["other"]
    assert "other" not in two.CONFIG.deleted_profiles


async def test_the_only_business_on_a_line_cannot_be_removed(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/business/acme/delete")).text())
        assert "only business on your line" in page
        assert 'name="confirm"' not in page
    assert "acme" in line.PROFILES


async def test_a_business_removed_too_long_ago_is_not_offered_back(tmp_path,
                                                                   monkeypatch):
    from datetime import datetime, timedelta

    long_ago = (datetime.now().astimezone()
                - timedelta(days=45)).replace(microsecond=0).isoformat()
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    svc = _import_service(
        tmp_path, monkeypatch, extra_env={"ADMIN_TOKEN": "line-code"},
        cfg_text=DELETED_CONFIG.replace('deleted_at = "2026-08-01T09:00:00-04:00"',
                                        f'deleted_at = "{long_ago}"'))
    async with dashboard(svc) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/activity")).text())
        assert "past the 30-day window" in page
        assert 'restore-business=oldco' not in page   # not even offered
        csrf = page.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post(
            "/activity/restore-business",
            {"csrf": csrf, "business": "oldco", "confirm": "on"})
        assert response.status == 303
    assert "oldco" not in svc.PROFILES


# ================================================ carry-forwards, tasks 7-8 ==

def test_a_scoped_owner_is_not_shown_the_lines_own_push_failures():
    """The whole line's push counters can be another business's target failing.
    A scoped owner judged on them gets amber for something they cannot see,
    cannot fix and are never told the name of."""
    admin = load_admin()
    health = {"bridge": "ok", "model_backend": "ok", "probe_error": "",
              "probe_checked_at": time.time(), "brain": "default", "model": "m",
              "unreachable_brains": [], "ntfy_failures": 4,
              "last_delivery": {"ts": None, "call_sid": None, "ok": False,
                                "error": "someone else's host"}}
    common = dict(health=health, numbers={"+15550001111": "acme"},
                  profiles=("acme",), last_call_at=time.time())

    whole = admin.status.line_status(**common, whole_line=True)
    assert whole.level == "warn"

    scoped = admin.status.line_status(**common, whole_line=False,
                                      last_notify={"ok": 1, "target": "ntfy"})
    assert scoped.level == "ok"
    assert "Alerts delivering" in scoped.summary

    own_failure = admin.status.line_status(
        **common, whole_line=False,
        last_notify={"ok": 0, "target": "ntfy"})
    assert own_failure.level == "warn"
    assert "did not get through" in own_failure.summary


async def test_health_detail_hides_the_lines_push_health_from_one_business(two):
    async with dashboard(two) as dash:
        await _signed_in(dash, "jo-code")
        body = await (await dash.client.get("/health/detail")).json()
    assert "ntfy" not in body
    assert "ntfy_failures" not in body

    async with dashboard(two) as dash:
        await _signed_in(dash, "line-code")
        body = await (await dash.client.get("/health/detail")).json()
    assert "ntfy_failures" in body


async def test_a_store_that_will_not_answer_is_not_called_another_business(two):
    """The acknowledge button's two "no" answers are not the same answer."""
    async def unhealthy():
        picture, ok = await health_ok()
        picture["last_delivery"] = {"ts": time.time(),
                                    "call_sid": "CAtest0000000000000000000000ack",
                                    "ok": False, "error": "push refused"}
        return picture, ok

    async with dashboard(two, health=unhealthy) as dash:
        await _signed_in(dash, "jo-code")
        body = _text(await (await dash.client.get("/settings/acme")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]

        def explode(_sid):
            raise sqlite_error()

        import sqlite3

        def sqlite_error():
            return sqlite3.OperationalError("database is locked")

        original = two.STORE.get_call
        two.STORE.get_call = explode
        try:
            response = await dash.client.post("/acknowledge-delivery",
                                              {"csrf": csrf})
            page = _text(await response.text())
        finally:
            two.STORE.get_call = original

    assert response.status == 503
    assert "Could not check whose message this was" in page
    assert "belongs to another business" not in page


async def test_the_sign_in_page_says_it_is_locked_before_it_is_used(line):
    async with dashboard(line) as dash:
        for _ in range(5):
            await dash.client.post("/sign-in", {"code": "nope"})
        response = await dash.client.get("/sign-in")
        page = _text(await response.text())

    assert response.status == 429
    assert "Too many wrong access codes" in page
    assert "Retry-After" in response.headers


async def test_the_messages_heading_moves_with_the_badge(line):
    line.STORE.start_call("CA000000000000000000000000000msg", "acme",
                          "+15550009999", "+15550001111", "default", "m")
    line.STORE.end_call("CA000000000000000000000000000msg", "message_taken",
                        "", 1, [])
    message_id = line.STORE.add_message("CA000000000000000000000000000msg",
                                        "acme", "Dana", "+15550009999", "",
                                        "wants a quote", "wants a quote")
    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/messages")).text())
        assert 'id="messages-count"' in body
        assert "1 waiting" in body
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post(
            f"/messages/{message_id}/status",
            {"csrf": csrf, "status": "done", "back": "/messages"},
            headers={"HX-Request": "true"})
        swapped = _text(await response.text())

    assert 'id="messages-count"' in swapped
    assert 'hx-swap-oob="true"' in swapped
    assert "0 waiting" in swapped


async def test_the_calls_first_run_state_is_not_shown_when_it_is_a_guess(line):
    """The probe that tells "no calls yet" from "only test calls" can fail. A
    page that answers "ring your number to test it" on a read that did not
    happen is inventing a fact."""
    async with dashboard(line) as dash:
        await _signed_in(dash)
        original = line.STORE.list_calls
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("database is locked")
            return []

        line.STORE.list_calls = flaky
        try:
            page = _text(await (await dash.client.get("/calls")).text())
        finally:
            line.STORE.list_calls = original

    assert "Could not read your call log" in page
    assert "Ring" not in page.split("Could not read")[0][-400:]


def test_the_store_scopes_a_caller_delete_to_one_logins_businesses(line):
    """The store, not the caller, decides whether a delete is inside a login's
    businesses — a call row whose business was removed from the config is
    invisible to anything that enumerates the config."""
    line.STORE.start_call("CAtest00000000000000000000000mine", "acme",
                          "+15550007777", "+15550001111", "default", "m")
    line.STORE.end_call("CAtest00000000000000000000000mine", "message_taken",
                        "", 1, [])
    line.STORE.start_call("CAtest0000000000000000000000theirs", "gone_biz",
                          "+15550007777", "+15550002222", "default", "m")
    line.STORE.end_call("CAtest0000000000000000000000theirs", "message_taken",
                        "", 1, [])

    with pytest.raises(PermissionError) as refusal:
        line.STORE.delete_caller("+15550007777", profile_keys=["acme"])
    assert "1 other business" in str(refusal.value)
    assert "gone_biz" not in str(refusal.value)
    assert line.STORE.get_call("CAtest00000000000000000000000mine") is not None

    removed = line.STORE.delete_caller("+15550007777", profile_keys=None)
    assert int(removed) >= 2
    assert line.STORE.get_call("CAtest00000000000000000000000mine") is None


def test_a_truncated_scan_never_names_one_business_on_the_delete_event(line):
    """`caller_deleted` is filed against a business only when the scan actually
    saw them all — otherwise it is filed against none."""
    admin = load_admin()
    from types import SimpleNamespace

    session = SimpleNamespace(profile_keys=("acme",), sees_whole_line=True,
                              owner_key="line")
    events = []
    store = SimpleNamespace(
        list_calls=lambda keys, **kw: [
            {"from_number": "+15550007777", "profile_key": "acme",
             "call_sid": f"CAtest{n:026d}"}
            for n in range(admin.views_calls.SCAN_LIMIT)],
        delete_caller=lambda number, profile_keys=None: line.callstore.Deletion(
            3, ["CAtest00000000000000000000000000"]),
        add_event=lambda *args, **kwargs: events.append(args),
    )
    deps = SimpleNamespace(store=store)

    result = admin.views_calls._delete_caller(deps, session, "+15550007777")

    assert result["reason"] == ""
    assert events and events[0][0] is None, (
        "the event named one business off a scan that may not have seen them all")


def test_the_flash_slot_is_emptied_when_a_login_ends(line):
    """A dict keyed by session id that nothing removes from holds a signed-out
    owner's last message for as long as the process runs."""
    async def run():
        async with dashboard(line) as dash:
            await _signed_in(dash)
            body = _text(await (await dash.client.get("/settings/acme")).text())
            csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
            # a save that redirects leaves exactly one receipt behind
            await dash.client.post("/settings/acme/identity", {
                "csrf": csrf,
                "version": body.split('name="version" value="', 1)[1]
                               .split('"', 1)[0],
                "business_name": "Acme Repairs", "services": "widget repair",
                "owner_name": "Jo"})
            assert dash.app[dash.admin.render.FLASH]
            await dash.client.post("/sign-out", {"csrf": csrf})
            return dict(dash.app[dash.admin.render.FLASH])

    assert asyncio.get_event_loop_policy() is not None
    left = asyncio.run(run())
    assert left == {}


async def test_a_long_note_says_what_was_kept(line):
    line.STORE.start_call("CA00000000000000000000000000note", "acme",
                          "+15550009999", "+15550001111", "default", "m")
    line.STORE.end_call("CA00000000000000000000000000note", "message_taken",
                        "", 1, [])
    line.STORE.add_message("CA00000000000000000000000000note", "acme", "Dana",
                           "+15550009999", "", "wants a quote", "wants a quote")
    admin = load_admin()
    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = await (await dash.client.get(
            "/calls/CA00000000000000000000000000note")).text()
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post(
            "/calls/CA00000000000000000000000000note/note",
            {"csrf": csrf,
             "note": "x" * (admin.views_calls.NOTE_MAX_CHARS + 50)})
        assert response.status == 303
        assert response.headers["Location"].endswith("saved=note_cut")
        page = _text(await (await dash.client.get(
            "/calls/CA00000000000000000000000000note?saved=note_cut")).text())

    assert "longer than a note can be" in page
    assert str(admin.views_calls.NOTE_MAX_CHARS) in page


async def test_the_overview_counts_waiting_messages_without_reading_them(line):
    """Messages are never deleted, only aged of their words: counting them by
    listing them grows without bound on a line that is working."""
    admin = load_admin()
    asked = []
    original = line.STORE.list_messages

    def watched(keys, status=None, include_test=False, **kwargs):
        asked.append((status, kwargs.get("limit"), kwargs.get("oldest_first")))
        return original(keys, status, include_test, **kwargs)

    line.STORE.list_messages = watched
    try:
        async with dashboard(line) as dash:
            await _signed_in(dash)
            assert (await dash.client.get("/")).status == 200
    finally:
        line.STORE.list_messages = original

    waiting_reads = [row for row in asked if row[0] == "new"]
    assert waiting_reads, "the Overview never asked for the waiting messages"
    for _status, limit, oldest in waiting_reads:
        assert limit == 1 and oldest is True, (
            "the waiting tile read the whole list instead of one row")
    assert admin.render.count_waiting is not None


# ================================================== nav and cross-cutting ====

async def test_the_settings_screens_are_all_in_the_navigation(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/settings")).text())
    for url in ("/settings", "/hours", "/numbers", "/notifications", "/brain",
                "/activity"):
        assert f'href="{url}"' in page, url


async def test_every_settings_screen_labels_its_controls(line):
    """WCAG 2.2 AA: every control has a label a screen reader can find, and the
    hints are attached to the fields they explain."""
    import re

    async with dashboard(line) as dash:
        await _signed_in(dash)
        for path in ("/settings/acme", "/hours/acme", "/numbers",
                     "/notifications/acme", "/activity"):
            page = _text(await (await dash.client.get(path)).text())
            ids = set(re.findall(r'\bid="([^"]+)"', page))
            for target in re.findall(r'\bfor="([^"]+)"', page):
                assert target in ids, f"{path}: label points at missing {target}"
            for described in re.findall(r'aria-describedby="([^"]+)"', page):
                for token in described.split():
                    assert token in ids, f"{path}: aria-describedby {token} missing"
            # every control an owner can actually reach is named for a screen
            # reader. Hidden inputs carry no meaning to read out; they have ids
            # only so a save can hand the new version to the other sections.
            for tag in re.findall(r'<input[^>]*>', page):
                if 'type="hidden"' in tag:
                    continue
                found = re.search(r'\bid="([^"]+)"', tag)
                assert found, f"{path}: a control with no id: {tag[:80]}"
                assert f'for="{found.group(1)}"' in page, (
                    f"{path}: the control {found.group(1)} has no label")


async def test_a_saved_section_hands_the_new_version_to_the_others(line):
    """Every section on this page carries the same version. Without this, saving
    the greeting would leave the other seven holding a number that is now old,
    and the owner's next save — of something nobody else touched — would come
    back "this page is out of date"."""
    async with dashboard(line) as dash:
        await _signed_in(dash)
        response = await _save(dash.client, "/settings/acme/identity", {
            "business_name": "Acme Repairs", "services": "widget repair",
            "owner_name": "Jo"})
        body = await response.text()
        assert response.status == 200, body

        # the panel that saved, plus one out-of-band input per other section
        assert body.count('hx-swap-oob="true"') == 7
        version = str(line.STORE.newest_config_change_id())
        for name in load_admin().views_settings.SECTIONS:
            assert f'id="version-{name}"' in body, name
        assert body.count(f'value="{version}"') >= 8

        # and a second save from a different section goes through
        again = await _save(dash.client, "/settings/acme/instructions",
                            {"extra_instructions": "Offer a callback for prices."},
                            version=version)
        assert again.status == 200, await again.text()
    assert line.PROFILES["acme"]["extra_instructions"] == (
        "Offer a callback for prices.")


async def test_the_page_never_asks_the_browser_for_an_inline_style(line):
    """htmx settles a `style` ATTRIBUTE onto every element it matches by id,
    which this page's Content-Security-Policy refuses — a console full of
    refusals on a page a customer is looking at. It is configured off."""
    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = await (await dash.client.get("/settings")).text()

    config = page.split("name=\"htmx-config\" content='", 1)[1].split("'", 1)[0]
    settled = __import__("json").loads(config)["attributesToSettle"]
    assert "style" not in settled
    assert "class" in settled
    # and nothing on the page carries one of its own
    assert " style=" not in page


async def test_the_sign_in_page_says_it_is_shut_during_a_line_wide_lock(line):
    """Twenty-one wrong codes from twenty-one addresses shuts the form for
    everybody for a minute. An address that has never guessed has to be TOLD
    that, not shown a form that refuses the right code."""
    admin = load_admin()
    async with dashboard(line) as dash:
        for n in range(admin.auth.GLOBAL_FAILURES_BEFORE_LOCK + 1):
            await dash.client.post(
                "/sign-in", {"code": "nope"},
                # Trusted only because the peer is loopback, which is what the
                # real deployment's proxy is; the LAST hop is the one believed.
                headers={"X-Forwarded-For": f"198.51.100.{n}"})
        response = await dash.client.get(
            "/sign-in", headers={"X-Forwarded-For": "203.0.113.77"})
        page = _text(await response.text())

    assert response.status == 429
    assert "closed to everybody" in page or "Too many wrong access codes" in page
    assert "disabled" in page


async def test_a_refusal_keeps_your_typing_with_javascript_off_too(line):
    """No htmx header, so this is a plain browser posting a plain form. A
    redirect here would rebuild the page from the settings in force and throw
    away everything typed — defect D.1 arriving by the back door."""
    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/settings/acme")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = body.split('name="version" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/settings/acme/transfer", {
            "csrf": csrf, "version": version, "transfer_on": "on",
            "forward_to": "ring the shop", "phrase": ["operator", "put me through"]})
        page = _text(await response.text())

    assert response.status == 400
    assert "Location" not in response.headers
    # the whole page came back, with what was typed still in the boxes
    assert "ring the shop" in page
    assert 'value="put me through"' in page
    assert "Enter a full phone number with area code" in page
    # and every other section is still drawn, from the live settings
    assert 'id="section-greeting"' in page and 'id="section-facts"' in page
    assert "forward_to" not in line.PROFILES["acme"]


# ============================== what a scoped owner may read in a diff =======

HAND_WRITTEN = '''[numbers]
"+15550001111" = "acme"
"+15550002222" = "other"

[owners.jo]
token_env = "PHONE_OWNER_JO_TOKEN"
profiles = ["acme"]

[profiles.acme]
greeting = "hi"
owner_name = "Jo"
business_name = "Acme Co"
services = "widget repair"

[profiles.other]
ntfy_url = "https://push.other.test"
ntfy_topic = "other-co-secret-topic"
greeting = "hello"
owner_name = "Sam"
business_name = "Other Co"
services = "other work"
'''


@pytest.fixture
def hand_written(tmp_path, monkeypatch):
    """Two businesses in a file nobody has saved from the dashboard yet — so
    the FIRST save rewrites the whole thing, which is the case that leaked."""
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    return _import_service(tmp_path, monkeypatch,
                           extra_env={"ADMIN_TOKEN": "line-code"},
                           cfg_text=HAND_WRITTEN)


async def test_a_scoped_owner_never_reads_another_business_out_of_a_diff(
        hand_written):
    """The stored diff carries every line of BOTH versions so a restore can be
    exact. A first save on a hand-written config therefore rewrites the whole
    file — and the rendered diff has to be filtered to this owner's own
    businesses BEFORE the context window is worked out, or three lines of
    "context" around their own change hand them the neighbour's push topic."""
    hand_written.apply_config(
        dataclasses.replace(hand_written.CONFIG, profiles=dict(
            hand_written.CONFIG.profiles,
            acme=dict(hand_written.CONFIG.profiles["acme"],
                      greeting="Good morning, Acme."))),
        "line", "Changed the greeting callers hear for Acme Co")

    async with dashboard(hand_written) as dash:
        await _signed_in(dash, "jo-code")
        scoped = _text(await (await dash.client.get("/activity")).text())

    # their own change is there, in their own words
    assert "Settings changed for Acme Co" in scoped
    assert "Good morning, Acme." in scoped
    # and not one line of the business next door
    assert "other-co-secret-topic" not in scoped
    assert "push.other.test" not in scoped
    assert "[profiles.other]" not in scoped
    assert "Other Co" not in scoped
    assert "Sam" not in scoped
    # said out loud, rather than silently trimmed
    assert "other businesses on this line changed in the same save" in scoped

    async with dashboard(hand_written) as dash:
        await _signed_in(dash, "line-code")
        whole = _text(await (await dash.client.get("/activity")).text())

    # the account that manages the line sees all of it
    assert "other-co-secret-topic" in whole
    assert "[profiles.other]" in whole


def test_the_diff_filter_is_pure_and_keeps_the_owners_own_lines(hand_written):
    """The exact shape of the first save on a hand-written file: the emitter
    puts every key in its own order, so the neighbour's whole section moves and
    lands in the diff as changed lines."""
    admin = load_admin()
    with open(hand_written.BUSINESS_CONFIG, encoding="utf-8") as f:
        before = f.read()
    after = hand_written.config_toml(hand_written.CONFIG).replace(
        'greeting = "hi"', 'greeting = "Good morning."')
    diff = hand_written.config_diff(before, after)

    # unfiltered, the neighbour IS in there — which is what had to be filtered
    everything = admin.views_activity.visible_diff(
        diff, None, rebuild=hand_written.config_from_diff)
    assert any("other-co-secret-topic" in line["text"] for line in everything)

    mine = admin.views_activity.visible_diff(
        diff, ("acme",), rebuild=hand_written.config_from_diff)
    text = " ".join(line["text"] for line in mine)
    assert "Good morning." in text and "Acme Co" in text
    assert "other-co-secret-topic" not in text
    assert "push.other.test" not in text
    assert "Sam" not in text
    assert admin.views_activity.OTHER_BUSINESSES in text


# ==================================== a removed business and its sign-ins ====

TWO_LOGINS = TWO_BUSINESSES.replace(
    'profiles = ["acme"]', 'profiles = ["acme", "other"]')


@pytest.fixture
def shared_login(tmp_path, monkeypatch):
    """One scoped login that covers BOTH businesses, so removing one leaves it
    with something and the delete is allowed."""
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    return _import_service(tmp_path, monkeypatch,
                           extra_env={"ADMIN_TOKEN": "line-code"},
                           cfg_text=TWO_LOGINS)


async def test_a_removed_business_gives_its_logins_back_when_it_returns(
        shared_login):
    """Removing a business takes it out of every sign-in's list, because a list
    naming a business the config no longer has is refused. Putting it back has
    to put THAT back too, or "restorable for 30 days" is a promise about the
    settings only and Jo quietly loses a business she used to work."""
    async with dashboard(shared_login) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get(
            "/business/other/delete")).text())
        # the consequence is named before the button, not discovered afterwards
        assert "These sign-ins will lose this business until it is restored: jo" \
            in page
        csrf = page.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = page.split('name="version" value="', 1)[1].split('"', 1)[0]
        response = await dash.client.post("/business/other/delete", {
            "csrf": csrf, "version": version, "confirm": "Other Co"})
        assert response.status == 303, await response.text()

    assert list(shared_login.OWNERS["jo"].profiles) == ["acme"]
    put_away = shared_login.CONFIG.deleted_profiles["other"]
    assert put_away["owners"] == ["jo"]
    # and it survives a round trip through the file
    reparsed = shared_login.parse_config(
        tomllib.loads(shared_login.config_toml(shared_login.CONFIG)))
    assert reparsed.deleted_profiles["other"]["owners"] == ["jo"]

    async with dashboard(shared_login) as dash:
        await _signed_in(dash)
        dialog = _text(await (await dash.client.get(
            "/activity?restore-business=other")).text())
        assert "These sign-ins get it back: jo." in dialog
        csrf = dialog.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        back = await dash.client.post(
            "/activity/restore-business",
            {"csrf": csrf, "business": "other", "confirm": "on"})
        assert back.status == 303, await back.text()
        after = _text(await (await dash.client.get("/activity")).text())

    assert sorted(shared_login.OWNERS["jo"].profiles) == ["acme", "other"]
    assert "These sign-ins can see it again: jo." in after
    # the bookkeeping key does not come back as a business setting
    assert "owners" not in shared_login.PROFILES["other"]
    assert "deleted_at" not in shared_login.PROFILES["other"]


async def test_a_scoped_login_really_gets_the_business_back(shared_login):
    """Not just the config text — Jo can open it again."""
    async with dashboard(shared_login) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get(
            "/business/other/delete")).text())
        csrf = page.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = page.split('name="version" value="', 1)[1].split('"', 1)[0]
        await dash.client.post("/business/other/delete", {
            "csrf": csrf, "version": version, "confirm": "Other Co"})

    async with dashboard(shared_login) as dash:
        await _signed_in(dash, "jo-code")
        assert (await dash.client.get("/settings/other")).status == 404

    async with dashboard(shared_login) as dash:
        await _signed_in(dash)
        dialog = _text(await (await dash.client.get(
            "/activity?restore-business=other")).text())
        csrf = dialog.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        await dash.client.post("/activity/restore-business",
                               {"csrf": csrf, "business": "other",
                                "confirm": "on"})

    async with dashboard(shared_login) as dash:
        await _signed_in(dash, "jo-code")
        assert (await dash.client.get("/settings/other")).status == 200


def test_a_removed_business_may_name_the_logins_that_had_it(tmp_path,
                                                            monkeypatch):
    with_owners = DELETED_CONFIG.replace(
        'deleted_at = "2026-08-01T09:00:00-04:00"',
        'deleted_at = "2026-08-01T09:00:00-04:00"\nowners = ["jo"]')
    svc = _import_service(tmp_path, monkeypatch, cfg_text=with_owners)
    assert svc.CONFIG.deleted_profiles["oldco"]["owners"] == ["jo"]
    assert 'owners = ["jo"]' in svc.config_toml(svc.CONFIG)

    with pytest.raises(SystemExit):
        _import_service(tmp_path, monkeypatch,
                        cfg_text=with_owners.replace('owners = ["jo"]',
                                                     'owners = "jo"'))


# =========================================== a number this line can dial =====

def test_only_a_number_the_phone_network_can_route_is_accepted():
    """A seven-digit local number padded to `+5550001` would save a setting that
    can never match an incoming call, and the owner would find out when
    somebody could not get through."""
    e164 = load_admin().config_edit.e164

    assert e164("(774) 555-0100") == ("+17745550100", "")
    assert e164("7745550100") == ("+17745550100", "")
    assert e164("1 (774) 555-0100") == ("+17745550100", "")
    assert e164("+44 20 7946 0018") == ("+442079460018", "")
    assert e164("") == ("", "")

    for refused in ("555-0001", "1234-5678", "12345", "+123", "ring my mobile",
                    "+1234567890123456"):
        kept, why = e164(refused)
        assert kept == refused, refused          # what was typed comes back
        assert "Enter a full phone number with area code" in why, refused


async def test_a_local_number_is_refused_on_the_transfer_field(line):
    async with dashboard(line) as dash:
        await _signed_in(dash)
        response = await _save(dash.client, "/settings/acme/transfer", {
            "transfer_on": "on", "forward_to": "555-0001",
            "phrase": ["operator"]})
        body = _text(await response.text())

    assert response.status == 400
    assert "555-0001" in body                     # still in the box
    assert "Enter a full phone number with area code" in body
    assert "forward_to" not in line.PROFILES["acme"]


# ============================================= restoring is confirmed =======

async def test_neither_restore_happens_without_the_confirm(line):
    """A stale tab, or a form somebody rebuilt, must not put a whole version of
    the settings back on one unconfirmed POST."""
    line.apply_config(
        dataclasses.replace(line.CONFIG, profiles={
            "acme": dict(line.CONFIG.profiles["acme"], greeting="Changed.")}),
        "line", "Changed the greeting callers hear for Acme Co")
    change_id = str(line.STORE.list_config_changes()[0]["id"])

    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/settings/acme")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]

        unconfirmed = await dash.client.post(
            "/activity/restore", {"csrf": csrf, "change_id": change_id})
        assert unconfirmed.status == 400
        assert "was not confirmed" in _text(await unconfirmed.text())

        no_business = await dash.client.post(
            "/activity/restore-business", {"csrf": csrf, "business": "acme"})
        assert no_business.status == 400
        assert "was not confirmed" in _text(await no_business.text())

    assert line.PROFILES["acme"]["greeting"] == "Changed."


async def test_the_restore_confirm_is_really_modal(line):
    line.apply_config(
        dataclasses.replace(line.CONFIG, profiles={
            "acme": dict(line.CONFIG.profiles["acme"], greeting="Changed.")}),
        "line", "Changed the greeting callers hear for Acme Co")
    change_id = str(line.STORE.list_config_changes()[0]["id"])

    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = await (await dash.client.get(
            f"/activity?restore={change_id}")).text()

    assert "<dialog" in page and 'aria-modal="true"' in page
    # the page behind it is out of reach, which is what makes aria-modal true
    assert '<div class="shell" inert>' in page
    # and the URL cannot put words of its own on the page
    async with dashboard(line) as dash:
        await _signed_in(dash)
        invented = await (await dash.client.get(
            "/activity?restore=999999")).text()
    assert "<dialog" not in invented


async def test_a_refused_restore_is_not_dressed_as_a_success(line):
    """"Nothing was changed" in the colour of a done job is the screen lying
    about what happened."""
    line.apply_config(
        dataclasses.replace(line.CONFIG, profiles={
            "acme": dict(line.CONFIG.profiles["acme"], greeting="Changed.")}),
        "line", "Changed the greeting callers hear for Acme Co")

    async with dashboard(line) as dash:
        await _signed_in(dash)
        body = _text(await (await dash.client.get("/settings/acme")).text())
        csrf = body.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        # a change id that is not on this line any more
        await dash.client.post("/activity/restore",
                               {"csrf": csrf, "change_id": "424242",
                                "confirm": "on"})
        page = await (await dash.client.get("/activity")).text()

    assert "notice notice-bad" in page
    assert 'role="alert"' in page
    assert "Nothing was changed." in _text(page)


# ================================ one push, for the test and the message =====

async def test_the_test_alert_and_a_real_message_are_the_same_request(line):
    """The button an owner presses has to ride on the request their customers'
    messages ride on, or it is a test of something else."""
    seen = []

    class Recorder:
        def post(self, url, **kwargs):
            seen.append({"url": url, "headers": dict(kwargs["headers"]),
                         "timeout": kwargs["timeout"].total,
                         "body": kwargs["data"]})
            return self

        async def __aenter__(self):
            class Response:
                status = 200
            return Response()

        async def __aexit__(self, *exc):
            return False

        async def close(self):
            return None

    targets = line.DeliveryTargets(messages_file="/dev/null",
                                   ntfy_url="https://push.acme.test",
                                   ntfy_topic="acme-phone")
    session = Recorder()

    # what a caller's message sends
    ok, why = await line.push_ntfy(targets, title="Acme Co — new message",
                                   body="a message", session=session)
    assert (ok, why) == (True, "")
    # what the dashboard's test button sends
    ok, why = await line.push_ntfy(targets, title="Acme Co — test alert",
                                   body="a test", session=session)
    assert (ok, why) == (True, "")

    message, test = seen
    assert message["url"] == test["url"] == "https://push.acme.test/acme-phone"
    assert message["timeout"] == test["timeout"] == line.NTFY_TIMEOUT_SECONDS
    assert set(message["headers"]) == set(test["headers"]) == {"Title"}

    # and the dashboard really calls it — same function, not a copy
    admin = load_admin()
    assert not hasattr(admin.views_notifications, "push")
    source = (admin.views_notifications.__file__)
    with open(source, encoding="utf-8") as f:
        body = f.read()
    assert "deps.push_ntfy(" in body
    assert "aiohttp.ClientSession" not in body


async def test_a_push_with_nowhere_to_go_says_so_instead_of_raising(line):
    ok, why = await line.push_ntfy(
        line.DeliveryTargets(messages_file="/dev/null", ntfy_url="",
                             ntfy_topic=""),
        title="t", body="b")
    assert ok is False
    assert "no push address is set up" in why


# ===================== the diff walker is a tenancy control, so: =============

def test_a_second_hunk_belongs_to_no_business_until_a_header_says_so(
        hand_written):
    """`@@` means the next line comes from somewhere else in the file. Carrying
    the last-seen table across it attributes a hunk that starts mid-table to
    whichever business was named further up — which on a shared line hands one
    owner the next one's settings."""
    import difflib

    admin = load_admin()
    before = hand_written.config_toml(hand_written.CONFIG)
    after = (before
             .replace('business_name = "Acme Co"', 'business_name = "Acme Repairs"')
             .replace('ntfy_topic = "other-co-secret-topic"',
                      'ntfy_topic = "changed-topic"'))
    # Short context on purpose: two hunks, the first carrying [profiles.acme]
    # in its context and the second starting in the middle of [profiles.other].
    short = "\n".join(difflib.unified_diff(
        before.splitlines(), after.splitlines(), lineterm="", n=1))
    assert len([line for line in short.splitlines()
                if line.startswith("@@")]) == 2, "the test needs two hunks"
    assert "[profiles.acme]" in short
    assert "[profiles.other]" not in short      # the second hunk has no header

    mine = admin.views_activity.visible_diff(
        short, ("acme",), rebuild=hand_written.config_from_diff)
    text = " ".join(line["text"] for line in mine)
    assert "Acme Repairs" in text                       # their own change
    assert "other-co-secret-topic" not in text          # not the neighbour's
    assert "changed-topic" not in text

    everything = admin.views_activity.visible_diff(
        short, None, rebuild=hand_written.config_from_diff)
    assert any("changed-topic" in line["text"] for line in everything)


def test_the_recorded_diff_is_one_hunk_so_the_walker_sees_every_header(line):
    """The walker fails closed across `@@` either way, but this is the invariant
    that keeps a whole-file diff readable: one hunk, every header in it."""
    before = _config_text(line)
    after = before.replace('greeting = "hi"', 'greeting = "Good day."')
    diff = line.config_diff(before, after)

    hunks = [row for row in diff.splitlines() if row.startswith("@@")]
    assert len(hunks) == 1, f"config_diff emitted {len(hunks)} hunks"
    # every line of both versions is in it, which is what makes a restore exact
    assert line.config_from_diff(diff, side="before") == before
    assert line.config_from_diff(diff, side="after") == after


FENCE = '"' * 3
LITERAL_FENCE = "'" * 3

# Probe (a): a literal (single-quoted) TOML string whose CONTENT ends in a
# triple quote. The emitter rewrites it on the new side with each quote
# escaped, so the fence appears an odd number of times and only on the old
# side. That desynchronised the quote-tracker of two rounds ago, and made the
# substring scan of one round ago call the diff unsplittable — but every
# string on BOTH sides ends on the line it starts on, so the parser reads it
# and the walker splits it exactly.
ODD_FENCE_DIFF = "\n".join([
    "--- businesses.toml (before)",
    "+++ businesses.toml (after)",
    "@@ -1,9 +1,9 @@",
    " [profiles.acme]",
    ' business_name = "Acme Co"',
    f"-notes = {LITERAL_FENCE[0]}ends with {FENCE}{LITERAL_FENCE[0]}",
    '+notes = "ends with \\"\\"\\""',
    '-greeting = "hi"',
    '+greeting = "hello"',
    " [profiles.other]",
    ' ntfy_topic = "other-co-secret-topic"',
    ' business_name = "Other Co"',
])

# Probe (b): a multi-line literal body that CONTAINS a line reading exactly
# like a table header. The fake header moves attribution and Acme's own
# change lands under the business next door — the one shape that really
# cannot be split, and the parser is what says so.
FENCE_BODY_DIFF = "\n".join([
    "@@ -1,9 +1,9 @@",
    " [profiles.acme]",
    ' business_name = "Acme Co"',
    f" extra_instructions = {LITERAL_FENCE}",
    " [profiles.other]",
    ' ntfy_topic = "other-co-secret-topic"',
    f" {LITERAL_FENCE}",
    '-greeting = "hi"',
    '+greeting = "hello"',
])


def test_a_diff_with_a_multi_line_string_cannot_be_split_up_at_all(line):
    """Inside a multi-line TOML value, a line reading like `[profiles.other]`
    is somebody's prose — and a diff cannot tell. So it is not split: a scoped
    reader gets nothing derived from a guess."""
    admin = load_admin()
    rebuild = line.config_from_diff
    certain = admin.views_activity.attribution_is_certain

    # The mechanism, pinned: the old side is valid TOML, and the PARSER says
    # its `extra_instructions` runs across lines and carries the fake header.
    # No quote-counting is involved in the decision.
    old = tomllib.loads(rebuild(FENCE_BODY_DIFF, side="before"))
    assert "[profiles.other]\n" in old["profiles"]["acme"]["extra_instructions"]
    assert "other" not in old["profiles"]
    assert certain(FENCE_BODY_DIFF, rebuild=rebuild) is False
    # nothing downstream may act on an attribution nobody can make
    assert admin.views_activity.sections_touched(
        FENCE_BODY_DIFF, rebuild=rebuild) == set()
    assert admin.views_activity.visible_diff(
        FENCE_BODY_DIFF, ("acme",), rebuild=rebuild) == []
    assert admin.views_activity.visible_diff(
        FENCE_BODY_DIFF, ("other",), rebuild=rebuild) == []
    # the account that manages the line still sees the whole thing
    whole = admin.views_activity.visible_diff(FENCE_BODY_DIFF, None,
                                              rebuild=rebuild)
    assert any("other-co-secret-topic" in row["text"] for row in whole)

    # a diff the emitter wrote has no multi-line value in it, so it is split
    plain = "\n".join([
        "@@ -1,5 +1,5 @@",
        " [profiles.acme]",
        '-greeting = "hi"',
        '+greeting = "hello"',
        " [profiles.other]",
        ' ntfy_topic = "other-co-secret-topic"',
    ])
    assert certain(plain, rebuild=rebuild) is True
    assert admin.views_activity.sections_touched(plain, rebuild=rebuild) == {"acme"}
    mine = admin.views_activity.visible_diff(plain, ("acme",), rebuild=rebuild)
    text = " ".join(row["text"] for row in mine)
    assert "hello" in text and "other-co-secret-topic" not in text


def test_a_fence_inside_a_one_line_string_is_not_a_multi_line_string(line):
    """Three quotes INSIDE a one-line string — the literal `'ends with \"\"\"'`
    on the old side, the emitter's `"ends with \\"\\"\\""` on the new — open
    nothing. Both sides parse, the value has no line break in it, and the
    walker's split is exact. A quote count made this diff unreadable to its
    own owner; the parser reads it."""
    admin = load_admin()
    rebuild = line.config_from_diff
    for side in ("before", "after"):
        parsed = tomllib.loads(rebuild(ODD_FENCE_DIFF, side=side))
        assert parsed["profiles"]["acme"]["notes"] == 'ends with """'
        assert "\n" not in parsed["profiles"]["acme"]["notes"]

    assert admin.views_activity.attribution_is_certain(
        ODD_FENCE_DIFF, rebuild=rebuild) is True
    assert admin.views_activity.sections_touched(
        ODD_FENCE_DIFF, rebuild=rebuild) == {"acme"}
    mine = admin.views_activity.visible_diff(ODD_FENCE_DIFF, ("acme",),
                                             rebuild=rebuild)
    text = " ".join(row["text"] for row in mine)
    assert "ends with" in text and "hello" in text
    assert "other-co-secret-topic" not in text
    # nothing of the neighbour's changed, so their view has no lines in it
    theirs = admin.views_activity.visible_diff(ODD_FENCE_DIFF, ("other",),
                                               rebuild=rebuild)
    assert all(row["kind"] == "gap" for row in theirs)
    assert not any("ends with" in row["text"] for row in theirs)


async def test_a_scoped_owner_gets_one_dull_sentence_for_an_unsplittable_diff(
        two):
    """Both probe shapes, through the real screen. The multi-line body is not
    split: none of the neighbour's topic, key or name reaches a scoped owner,
    and the row still appears so they are not told a change never happened.
    The one-line fence IS split, and the owner reads her own lines from it."""
    for probe in (ODD_FENCE_DIFF, FENCE_BODY_DIFF):
        two.STORE.record_config_change(
            actor="the_other_manager", summary="Removed the business Other Co",
            diff=probe, applied=True, reason="")

    async with dashboard(two) as dash:
        await _signed_in(dash, "jo-code")
        scoped = _text(await (await dash.client.get("/activity")).text())
    async with dashboard(two) as dash:
        await _signed_in(dash)
        whole = _text(await (await dash.client.get("/activity")).text())

    # the multi-line body: the reader learns only that something changed
    assert scoped.count(
        "Settings on this line changed (the line owner can see the details)") == 1
    assert "somebody who manages this line" in scoped
    # the one-line fence: her own change, in her own words, with her own lines
    assert scoped.count("Settings changed for Acme Co") == 1
    assert "ends with" in scoped
    assert scoped.count("What changed") == 1
    for secret in ("other-co-secret-topic", "[profiles.other]", "Other Co",
                   "Removed the business", "the_other_manager"):
        assert secret not in scoped, secret
    # nothing to put back, either way
    assert "restore=" not in scoped

    # the account that manages the line sees every one of them
    assert whole.count("Removed the business Other Co") == 2
    assert "other-co-secret-topic" in whole
    assert "the_other_manager" in whole


def test_believing_a_header_inside_a_quoted_body_moves_the_wrong_lines(line):
    """Why the certainty rule is not paranoia: with the fence body believed,
    Acme's own change lands under the business next door — which is a leak in
    whichever direction the reader happens to own."""
    admin = load_admin()
    walked = list(admin.views_activity._walk(FENCE_BODY_DIFF))
    changed = {key for key, line_ in walked if line_[:1] in "+-"}

    # the walker on its own really is fooled — the greeting change reads as
    # `other`'s, not Acme's
    assert changed == {"other"}
    # which is exactly why nothing is allowed to use it here
    assert admin.views_activity.sections_touched(
        FENCE_BODY_DIFF, rebuild=line.config_from_diff) == set()


def test_an_indented_table_header_still_ends_the_business_before_it(line):
    admin = load_admin()
    diff = "\n".join([
        "@@ -1,4 +1,4 @@",
        " [profiles.acme]",
        '-greeting = "hi"',
        '+greeting = "hello"',
        "   [numbers]",
        '+"+15550009999" = "acme"',
    ])
    # the indented table is not acme's, so the number line belongs to nobody
    assert admin.views_activity.sections_touched(
        diff, rebuild=line.config_from_diff) == {"acme"}
    assert admin.views_activity.line_wide(
        diff, rebuild=line.config_from_diff) is True


# ============ a tenant's text cannot make the line's history unreadable =====

async def test_three_apostrophes_in_a_greeting_do_not_poison_the_line(two):
    """The emitter escapes `"` and line breaks but writes `'` as it is, so a
    tenant who types ''' gets it into the file verbatim — on ONE line, inside
    a basic string, valid TOML. That is not a multi-line string. Read as one,
    every later change on the line was unreadable to its own owners for ever,
    because every recorded diff carries the whole file."""
    two.apply_config(
        dataclasses.replace(two.CONFIG, profiles=dict(
            two.CONFIG.profiles,
            acme=dict(two.CONFIG.profiles["acme"],
                      greeting="it's '''fine'''"))),
        "jo", "Changed the greeting callers hear for Acme Co")
    two.apply_config(
        dataclasses.replace(two.CONFIG, profiles=dict(
            two.CONFIG.profiles,
            other=dict(two.CONFIG.profiles["other"],
                       greeting="Other Co, secret greeting"))),
        "line", "Changed the greeting callers hear for Other Co")

    # the premise: the apostrophes are in the file as typed, and it is TOML
    on_disk = _config_text(two)
    assert "greeting = \"it's '''fine'''\"" in on_disk
    assert tomllib.loads(on_disk)["profiles"]["acme"]["greeting"] == "it's '''fine'''"

    admin = load_admin()
    rebuild = two.config_from_diff
    later, earlier = two.STORE.list_config_changes()[:2]
    assert "'''" in later["diff"]                   # it carries the whole file
    certain = admin.views_activity.attribution_is_certain
    assert certain(earlier["diff"], rebuild=rebuild) is True
    assert certain(later["diff"], rebuild=rebuild) is True
    assert admin.views_activity.sections_touched(
        later["diff"], rebuild=rebuild) == {"other"}

    async with dashboard(two) as dash:
        await _signed_in(dash, "jo-code")
        scoped = _text(await (await dash.client.get("/activity")).text())

    # her own change is there, as hers, with its lines
    assert scoped.count("Settings changed for Acme Co") == 1
    assert "by you" in scoped
    assert "it's '''fine'''" in scoped
    # and the neighbour's save is filtered out, not shown as a dull row
    assert admin.views_activity.UNCERTAIN_SUMMARY not in scoped
    assert "secret greeting" not in scoped
    assert "Other Co" not in scoped


def test_line_breaks_inside_a_value_do_not_poison_the_line(two):
    """Facts are rows joined with a line break and instructions are paragraphs;
    the emitter writes both as `\\n` on ONE line. A value that contains a line
    break is not a string written across lines — the rule is about the lines
    of the file, never the characters of a value — or every business with
    two facts would be unreadable to its owner for ever."""
    two.apply_config(
        dataclasses.replace(two.CONFIG, profiles=dict(
            two.CONFIG.profiles,
            acme=dict(two.CONFIG.profiles["acme"],
                      facts="Email: office@acme.test\nHours: 9-5",
                      extra_instructions="Be brief.\n\nNever quote a price."))),
        "jo", "Changed the facts for Acme Co")

    on_disk = _config_text(two)
    assert 'facts = "Email: office@acme.test\\nHours: 9-5"' in on_disk
    assert "\n" in tomllib.loads(on_disk)["profiles"]["acme"]["facts"]

    admin = load_admin()
    diff = two.STORE.list_config_changes()[0]["diff"]
    assert admin.views_activity.attribution_is_certain(
        diff, rebuild=two.config_from_diff) is True
    assert admin.views_activity.sections_touched(
        diff, rebuild=two.config_from_diff) == {"acme"}


def test_escaped_triple_quotes_written_by_the_emitter_are_certain(two):
    """`\"\"\"` typed into a greeting comes out as `\\"\\"\\"` on one line."""
    two.apply_config(
        dataclasses.replace(two.CONFIG, profiles=dict(
            two.CONFIG.profiles,
            acme=dict(two.CONFIG.profiles["acme"], greeting='say """hi"""'))),
        "jo", "Changed the greeting callers hear for Acme Co")

    on_disk = _config_text(two)
    assert 'greeting = "say \\"\\"\\"hi\\"\\"\\""' in on_disk
    admin = load_admin()
    diff = two.STORE.list_config_changes()[0]["diff"]
    assert '\\"\\"\\"' in diff
    assert admin.views_activity.attribution_is_certain(
        diff, rebuild=two.config_from_diff) is True
    assert admin.views_activity.sections_touched(
        diff, rebuild=two.config_from_diff) == {"acme"}


def test_a_diff_with_a_side_that_is_not_toml_is_uncertain(two):
    """A file edited by hand until it no longer parses can still be the
    "before" of a save. Nothing can say where its lines belong, so nothing
    is guessed — in either direction."""
    admin = load_admin()
    rebuild = two.config_from_diff
    good = _config_text(two)
    for broken in (good.replace('greeting = "hi"', 'greeting = "hi'),
                   good.replace("[profiles.acme]", "[profiles.acme")):
        old_side_broken = two.config_diff(broken, good)
        with pytest.raises(tomllib.TOMLDecodeError):
            tomllib.loads(rebuild(old_side_broken, side="before"))
        tomllib.loads(rebuild(old_side_broken, side="after"))
        assert admin.views_activity.attribution_is_certain(
            old_side_broken, rebuild=rebuild) is False
        assert admin.views_activity.sections_touched(
            old_side_broken, rebuild=rebuild) == set()

        new_side_broken = two.config_diff(good, broken)
        assert admin.views_activity.attribution_is_certain(
            new_side_broken, rebuild=rebuild) is False


def test_a_diff_that_cannot_be_rebuilt_is_uncertain_and_says_so(two, caplog):
    admin = load_admin()

    def cannot(diff, *, side):
        raise RuntimeError("no reader today")

    plain = "\n".join([
        "@@ -1,2 +1,2 @@", " [profiles.acme]",
        '-greeting = "hi"', '+greeting = "hello"',
    ])
    with caplog.at_level("WARNING", logger="atlas-phone"):
        assert admin.views_activity.attribution_is_certain(
            plain, rebuild=cannot) is False
    assert "could not rebuild" in caplog.text


def test_line_wide_says_nothing_when_the_diff_cannot_be_split_up(line):
    """`line_wide` is public, and a public helper does not guess: "shared" is
    an attribution like any other."""
    admin = load_admin()
    diff = "\n".join([
        "@@ -1,7 +1,8 @@",
        " [numbers]",
        ' "+15550001111" = "acme"',
        '+"+15550009999" = "acme"',
        " [profiles.acme]",
        f" extra_instructions = {LITERAL_FENCE}",
        " [profiles.other]",
        f" {LITERAL_FENCE}",
    ])
    # the walker on its own would call the added number line-wide
    assert any(row[:1] == "+" and not key
               for key, row in admin.views_activity._walk(diff))
    assert admin.views_activity.attribution_is_certain(
        diff, rebuild=line.config_from_diff) is False
    assert admin.views_activity.line_wide(
        diff, rebuild=line.config_from_diff) is False


def test_a_scoped_reader_is_not_handed_the_actor_column(two):
    """The template shows `actor_label`; the login name itself is popped off
    the row as well, so keeping it from this reader is not one template edit
    away."""
    import types

    admin = load_admin()
    deps = types.SimpleNamespace(get_state=lambda: (two.NUMBERS, two.PROFILES),
                                 config_from_diff=two.config_from_diff)
    jo = admin.auth_module.Session(id="s", owner_key="jo",
                                   profile_keys=("acme",), sees_whole_line=False)
    plain = "\n".join([
        "@@ -1,2 +1,2 @@", " [profiles.acme]",
        '-greeting = "hi"', '+greeting = "hello"',
    ])

    def recorded(diff):
        return {"id": 1, "ts": 0.0, "actor": "the_other_manager",
                "summary": "Changed the settings", "diff": diff,
                "applied": 1, "reason": ""}

    for diff in (plain, FENCE_BODY_DIFF):
        row = admin.views_activity.decorate_change(deps, recorded(diff), jo)
        assert "actor" not in row and "diff" not in row
        assert row["actor_label"] == "somebody who manages this line"

    whole = admin.views_activity.decorate_change(deps, recorded(plain), None)
    assert whole["actor"] == "the_other_manager"


# ================ what a scoped owner is TOLD a change was ==================

async def test_a_scoped_owner_is_not_told_what_happened_to_anybody_else(
        hand_written):
    """The stored summary is written for whoever made the change and describes
    the whole save. "Removed the business Other Co" is the truth, and it is not
    this reader's truth to be told — but the save rewrote Acme's lines too, so
    the change IS on her screen and the sentence has to be rebuilt."""
    async with dashboard(hand_written) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get(
            "/business/other/delete")).text())
        csrf = page.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = page.split('name="version" value="', 1)[1].split('"', 1)[0]
        removed = await dash.client.post("/business/other/delete", {
            "csrf": csrf, "version": version, "confirm": "Other Co"})
        assert removed.status == 303, await removed.text()

    stored = hand_written.STORE.list_config_changes()[0]["summary"]
    assert stored == "Removed the business Other Co"

    async with dashboard(hand_written) as dash:
        await _signed_in(dash, "jo-code")
        scoped = _text(await (await dash.client.get("/activity")).text())
    async with dashboard(hand_written) as dash:
        await _signed_in(dash)
        whole = _text(await (await dash.client.get("/activity")).text())

    # the account that manages the line reads what was recorded
    assert stored in whole
    assert "Removed businesses" in whole

    # the change reached her screen — the save rewrote her business's lines
    assert "Settings changed for Acme Co" in scoped
    assert "settings shared by the whole line" in scoped
    # and told her nothing about the business next door, in any panel
    assert stored not in scoped
    assert "Other Co" not in scoped
    assert "other-co-secret-topic" not in scoped
    assert "Removed businesses" not in scoped


async def test_a_scoped_owner_is_not_told_which_other_login_made_a_change(two):
    two.apply_config(
        dataclasses.replace(two.CONFIG, profiles=dict(
            two.CONFIG.profiles,
            acme=dict(two.CONFIG.profiles["acme"], greeting="Acme, hello"))),
        "the_other_manager", "Changed the greeting callers hear for Acme Co")

    async with dashboard(two) as dash:
        await _signed_in(dash, "jo-code")
        scoped = _text(await (await dash.client.get("/activity")).text())
    assert "the_other_manager" not in scoped
    assert "somebody who manages this line" in scoped

    async with dashboard(two) as dash:
        await _signed_in(dash)
        whole = _text(await (await dash.client.get("/activity")).text())
    assert "the_other_manager" in whole


async def test_a_scoped_owner_is_not_handed_a_refusal_about_another_business(
        two):
    """A refusal names the field the validator stopped on, which on a save that
    also touched somebody else is somebody else's field."""
    two.STORE.record_config_change(
        actor="line", summary="Changed the settings",
        diff="\n".join([
            "@@ -1,6 +1,6 @@",
            " [profiles.acme]",
            '-greeting = "hi"',
            '+greeting = "hello"',
            " [profiles.other]",
            '-forward_to = "+15550003333"',
            '+forward_to = "the shop mobile"',
        ]),
        applied=False,
        reason="profile 'other' forward_to 'the shop mobile' is not an E.164 number")

    async with dashboard(two) as dash:
        await _signed_in(dash, "jo-code")
        scoped = _text(await (await dash.client.get("/activity")).text())
    assert "the shop mobile" not in scoped
    assert "profile 'other'" not in scoped
    assert "Refused, so nothing changed" in scoped

    async with dashboard(two) as dash:
        await _signed_in(dash)
        whole = _text(await (await dash.client.get("/activity")).text())
    assert "the shop mobile" in whole


async def test_a_scoped_owner_still_sees_a_removed_business_that_was_theirs(
        shared_login):
    """Scoping the removed list is not "hide everything": a business Jo used to
    work, removed, is hers to know about — that is what `owners` records."""
    async with dashboard(shared_login) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get(
            "/business/other/delete")).text())
        csrf = page.split('name="csrf" value="', 1)[1].split('"', 1)[0]
        version = page.split('name="version" value="', 1)[1].split('"', 1)[0]
        await dash.client.post("/business/other/delete", {
            "csrf": csrf, "version": version, "confirm": "Other Co"})

    async with dashboard(shared_login) as dash:
        await _signed_in(dash, "jo-code")
        scoped = _text(await (await dash.client.get("/activity")).text())

    assert "Removed businesses" in scoped
    assert "Other Co" in scoped
    # but putting it back is not hers to do, so it is not offered
    assert "restore-business=other" not in scoped


# ================ the login that owns the whole line has a NAME =============

async def test_the_activity_screen_never_shows_the_legacy_logins_config_key(line):
    """`_admin` is the key the pre-owners access code gets. It is a name in a
    settings file; the person reading their own Activity screen owns a
    plumbing company, and on their screen this login is the Line owner."""
    line.apply_config(
        dataclasses.replace(line.CONFIG, profiles={
            "acme": dict(line.CONFIG.profiles["acme"], greeting="Changed.")}),
        line.LEGACY_OWNER_KEY, "Changed the greeting callers hear for Acme Co")

    async with dashboard(line) as dash:
        await _signed_in(dash)                      # the ADMIN_TOKEN login
        page = _text(await (await dash.client.get("/activity")).text())

    assert line.LEGACY_OWNER_KEY not in page
    assert "by Line owner" in page
    assert "Line owner signed in from 127.0.0.1" in page


async def test_a_sign_in_recorded_before_this_still_reads_as_the_line_owner(line):
    """The sentence is STORED, so rows written by an older build already carry
    the key. They are read for as long as they are kept."""
    line.STORE.add_event(None, None, "info", "dashboard_signin",
                         "_admin signed in from 100.64.0.9")

    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = _text(await (await dash.client.get("/activity")).text())

    assert "Line owner signed in from 100.64.0.9" in page
    assert "_admin" not in page


# ====================== the confirm works with no JavaScript ================

async def test_the_confirm_dialog_carries_its_own_cancel_link(line):
    """Escape closing the dialog is JavaScript, and JavaScript here is only
    ever an enhancement: the way out of the question is a plain link the
    server rendered, which works with scripting off and is what the Escape
    handler follows."""
    line.apply_config(
        dataclasses.replace(line.CONFIG, profiles={
            "acme": dict(line.CONFIG.profiles["acme"], greeting="Changed.")}),
        "line", "Changed the greeting callers hear for Acme Co")
    change_id = str(line.STORE.list_config_changes()[0]["id"])

    async with dashboard(line) as dash:
        await _signed_in(dash)
        page = await (await dash.client.get(
            f"/activity?restore={change_id}")).text()

    assert '<dialog class="confirm" open aria-modal="true"' in page
    assert ('<a class="btn btn-quiet" href="/activity" data-dialog-cancel '
            'autofocus>Cancel</a>') in page
    # and nothing on the page depends on a script the CSP would refuse anyway
    assert "<script>" not in page

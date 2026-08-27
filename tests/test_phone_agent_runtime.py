# tests/test_phone_agent_runtime.py — what the line DOES while a call is live.
#
# Task 5b of the productization plan: after-hours behaviour, the call-length
# watchdog, the per-caller turn budget, the block list, per-business delivery,
# spoken opt-outs, the keypress answer, graceful shutdown, retention
# scheduling, token usage and the masked caller number in the journal.
#
# Same standard as the hardening suite: real handlers, a real websocket, a real
# model backend and a real push receiver on loopback. The only things held
# still are clocks — service._now for "is the business open", service._monotonic
# for "has this call run too long" — because a test must not wait ten minutes
# to prove a ten-minute limit.
import asyncio
import json
import logging
import os
import sqlite3
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from aiohttp import web
from test_phone_agent_hardening import (
    CALL_SID,
    FakeBrain,
    FakeNtfy,
    _connect_expecting_status,
    _drain_until_last,
    _twilio_post_kwargs,
    phone_line,
    prompt_frame,
    run_call,
    setup_frame,
)
from test_phone_agent_plugin import _import_service

SECOND_CALL = "CAtest00000000002"
DIALED = "+15550001111"

# A Thursday, in the profile's own timezone: 03:00 New York is out of hours for
# a nine-to-five, 10:00 is in them.
CLOSED_AT = datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc)     # 03:00 EDT
OPEN_AT = datetime(2026, 8, 27, 14, 0, tzinfo=timezone.utc)      # 10:00 EDT
NINE_TO_FIVE = (
    'forward_to = "+15550002222"\n'
    'timezone = "America/New_York"\n'
    'hours = { thu = "09:00-17:00" }\n'
)


def freeze(svc, monkeypatch, moment: datetime) -> None:
    """Hold the wall clock still, so "open or closed" is a decision the test
    makes rather than a decision the calendar makes."""
    monkeypatch.setattr(svc, "_now", lambda: moment)


def no_speech_wait(svc, monkeypatch) -> None:
    """Skip the pause that lets a closing sentence play out. It is real
    behaviour (Twilio would clip the goodbye without it) but it is seconds of
    nothing, and every ending under test here waits it out."""
    monkeypatch.setattr(svc, "speech_seconds", lambda text: 0.0)


async def drive(line, frames, *, call_sid=CALL_SID, profile="acme", during=None,
                idle=0.25):
    """One real call: send `frames`, optionally do something while it runs, then
    read everything the bridge says until it goes quiet for `idle` seconds.

    Returns .spoken (everything the caller would have heard) and .ends (the
    session-ending messages, with their handoff reasons).
    """
    svc = line.svc
    url = (f"{line.base}/voice/relay?token={svc.WS_TOKEN}"
           f"&call={call_sid}&profile={profile}")
    spoken: list[str] = []
    ends: list[dict] = []
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url) as ws:
            for frame in frames:
                await ws.send_str(json.dumps(frame))
            if during is not None:
                await during(ws)
            while True:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=idle)
                except TimeoutError:
                    break
                if msg.type is not aiohttp.WSMsgType.TEXT:
                    break
                data = json.loads(msg.data)
                if data.get("type") == "end":
                    ends.append(data)
                else:
                    spoken.append(data.get("token") or "")
            await ws.close()
    await asyncio.sleep(0.2)
    return SimpleNamespace(spoken="".join(spoken), ends=ends)


def one_call(svc, call_sid=CALL_SID) -> dict:
    call = svc.STORE.get_call(call_sid)
    assert call is not None, f"no call row for {call_sid}"
    return call


def kinds(svc) -> list:
    return [e["kind"] for e in svc.RECENT_EVENTS]


# ============================================================ step 1: hours ==
# Out of hours a message-taking business must not transfer, and the caller who
# asks for a person has to be told so — by the persona AND by the gates, which
# is two changes that have to agree.

async def test_out_of_hours_the_persona_loses_its_transfer_section(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra=NINE_TO_FIVE) as line:
        freeze(line.svc, monkeypatch, CLOSED_AT)
        await run_call(line, [setup_frame(), prompt_frame("hello")])

        system = line.brain.stream_bodies[-1]["messages"][0]["content"]
        assert "TRANSFERRING THE CALL" not in system
        assert line.svc.TRANSFER_MARKER not in system


async def test_in_hours_the_same_profile_still_offers_a_transfer(tmp_path, monkeypatch):
    """The control: nothing about the persona changes while the shop is open."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra=NINE_TO_FIVE) as line:
        freeze(line.svc, monkeypatch, OPEN_AT)
        await run_call(line, [setup_frame(), prompt_frame("hello")])

        system = line.brain.stream_bodies[-1]["messages"][0]["content"]
        assert "TRANSFERRING THE CALL" in system


async def test_out_of_hours_a_caller_asking_for_a_person_is_not_transferred(
        tmp_path, monkeypatch):
    """Even if the model emits the transfer marker, the gates refuse it and the
    caller hears the message-taking line instead of ringing an empty office."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra=NINE_TO_FIVE) as line:
        svc = line.svc
        freeze(svc, monkeypatch, CLOSED_AT)
        no_speech_wait(svc, monkeypatch)
        line.brain.reply = "Connecting you now. [TRANSFER CALL]"

        result = await drive(line, [setup_frame(),
                                    prompt_frame("let me speak to a person")])

        assert "can't connect calls on this line" in result.spoken
        assert result.ends == []
        assert one_call(svc)["outcome"] != "transferred"


async def test_in_hours_that_same_request_does_transfer(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra=NINE_TO_FIVE) as line:
        svc = line.svc
        freeze(svc, monkeypatch, OPEN_AT)
        no_speech_wait(svc, monkeypatch)
        line.brain.reply = "Connecting you now. [TRANSFER CALL]"

        result = await drive(line, [setup_frame(),
                                    prompt_frame("let me speak to a person")])

        assert [json.loads(e["handoffData"])["reason"] for e in result.ends] == \
            ["transfer"]
        assert one_call(svc)["outcome"] == "transferred"


async def test_an_after_hours_message_is_its_own_outcome(tmp_path, monkeypatch):
    """The owner reading the call log can tell which messages came in while the
    business was shut."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra=NINE_TO_FIVE) as line:
        svc = line.svc
        freeze(svc, monkeypatch, CLOSED_AT)
        await run_call(line, [setup_frame(), prompt_frame("please call me back")])

        assert one_call(svc)["outcome"] == "after_hours_message"
        assert line.brain.note in line.pad.read_text(encoding="utf-8")


async def test_in_hours_the_same_message_is_an_ordinary_one(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra=NINE_TO_FIVE) as line:
        svc = line.svc
        freeze(svc, monkeypatch, OPEN_AT)
        await run_call(line, [setup_frame(), prompt_frame("please call me back")])

        assert one_call(svc)["outcome"] == "message_taken"


async def test_after_hours_transfer_mode_keeps_transferring(tmp_path, monkeypatch):
    """A business that forwards out of hours is not a business that takes
    messages out of hours — after_hours = "transfer" changes nothing here."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra=NINE_TO_FIVE + 'after_hours = "transfer"\n') as line:
        freeze(line.svc, monkeypatch, CLOSED_AT)
        await run_call(line, [setup_frame(), prompt_frame("hello")])

        system = line.brain.stream_bodies[-1]["messages"][0]["content"]
        assert "TRANSFERRING THE CALL" in system


async def test_the_open_closed_decision_is_carried_from_greeting_to_persona(
        tmp_path, monkeypatch):
    """The greeting is composed when Twilio asks for TwiML; the persona is
    built when the websocket opens, seconds later. At the closing minute those
    two used to disagree — the caller was told the shop was shut and then
    offered a transfer to a phone nobody was next to."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra=NINE_TO_FIVE) as line:
        svc = line.svc
        # 17:00 New York exactly: closed, and the TwiML is composed as closed
        freeze(svc, monkeypatch, datetime(2026, 8, 27, 21, 0, tzinfo=timezone.utc))
        status, _xml = await _incoming(line, {"To": DIALED, "From": "+15085551234",
                                              "CallSid": CALL_SID})
        assert status == 200

        # the socket opens a minute earlier by the bridge's clock — the moment
        # a fresh decision would come back "open"
        freeze(svc, monkeypatch, datetime(2026, 8, 27, 20, 59, tzinfo=timezone.utc))
        await run_call(line, [setup_frame(), prompt_frame("please call me back")])

        system = line.brain.stream_bodies[-1]["messages"][0]["content"]
        assert "TRANSFERRING THE CALL" not in system
        assert one_call(svc)["outcome"] == "after_hours_message"


async def test_a_relay_with_no_carried_decision_still_answers(tmp_path, monkeypatch):
    """A bridge restarted between the TwiML and the websocket has no decision
    to carry. The caller is answered on a fresh one, and the journal says so."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra=NINE_TO_FIVE) as line:
        svc = line.svc
        freeze(svc, monkeypatch, CLOSED_AT)
        assert svc.CALL_DECISIONS == {}
        await run_call(line, [setup_frame(), prompt_frame("please call me back")])

        system = line.brain.stream_bodies[-1]["messages"][0]["content"]
        assert "TRANSFERRING THE CALL" not in system
        assert one_call(svc)["outcome"] == "after_hours_message"


def test_a_carried_decision_is_read_once_and_ages_out(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    closed = svc.hours.OpenState(open=False, reason="hours", next_open=None)

    svc.remember_call_decision("CAone", closed, 1000.0)
    assert svc.recall_call_decision("CAone", 1000.5) is closed
    assert svc.recall_call_decision("CAone", 1000.5) is None       # single use

    svc.remember_call_decision("CAtwo", closed, 1000.0)
    stale = 1000.0 + svc.CALL_DECISION_TTL_SECONDS + 1
    assert svc.recall_call_decision("CAtwo", stale) is None        # aged out
    # and a later call prunes what the websocket never came for
    svc.remember_call_decision("CAthree", closed, 1000.0)
    svc.remember_call_decision("CAfour", closed, stale)
    assert list(svc.CALL_DECISIONS) == ["CAfour"]


def test_takes_messages_only_reads_the_mode_and_the_state(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    profile = svc.PROFILES["acme"]
    closed = svc.hours.OpenState(open=False, reason="hours", next_open=None)
    opened = svc.hours.OpenState(open=True, reason="hours", next_open=None)

    assert svc.takes_messages_only(profile, closed) is True     # default mode
    assert svc.takes_messages_only(profile, opened) is False
    assert svc.takes_messages_only(profile, None) is False
    profile["after_hours"] = "same"
    assert svc.takes_messages_only(profile, closed) is False


# ========================================================= step 2: watchdog ==

async def test_the_watchdog_wraps_up_a_call_that_runs_too_long(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        no_speech_wait(svc, monkeypatch)
        monkeypatch.setattr(svc, "WATCHDOG_TICK_SECONDS", 0.02)
        clock = {"t": 0.0}
        monkeypatch.setattr(svc, "_monotonic", lambda: clock["t"])

        async def run_out_the_clock(ws):
            await asyncio.sleep(0.2)          # the call is under way
            clock["t"] = 10_000.0             # …and now it is over its limit
            await asyncio.sleep(0.2)

        result = await drive(line, [setup_frame(), prompt_frame("please call me back")],
                             during=run_out_the_clock)

        assert "I need to wrap up now" in result.spoken
        assert [json.loads(e["handoffData"])["reason"] for e in result.ends] == ["end"]
        assert "watchdog" in kinds(svc)
        call = one_call(svc)
        assert call["outcome"] == "message_taken"      # a message did come of it
        assert call["decision_reason"] == "watchdog"
        assert line.brain.note in line.pad.read_text(encoding="utf-8")


async def test_the_watchdog_on_a_silent_call_records_a_hang_up(tmp_path, monkeypatch):
    """Nobody said anything, so there is no message — the row must not claim
    one was taken."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        no_speech_wait(svc, monkeypatch)
        monkeypatch.setattr(svc, "WATCHDOG_TICK_SECONDS", 0.02)
        clock = {"t": 0.0}
        monkeypatch.setattr(svc, "_monotonic", lambda: clock["t"])

        async def run_out_the_clock(ws):
            await asyncio.sleep(0.2)
            clock["t"] = 10_000.0
            await asyncio.sleep(0.2)

        result = await drive(line, [setup_frame()], during=run_out_the_clock)

        assert "I need to wrap up now" in result.spoken
        assert "watchdog" in kinds(svc)
        assert one_call(svc)["outcome"] == "caller_hung_up"
        assert not line.pad.exists()


async def test_a_normal_call_is_never_wrapped_up(tmp_path, monkeypatch):
    """The control: the clock does not move, so the watchdog says nothing."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        monkeypatch.setattr(svc, "WATCHDOG_TICK_SECONDS", 0.02)
        monkeypatch.setattr(svc, "_monotonic", lambda: 0.0)

        result = await drive(line, [setup_frame(), prompt_frame("hello")])

        assert "wrap up" not in result.spoken
        assert "watchdog" not in kinds(svc)


# ====================================================== step 3: turn budget ==

async def test_a_caller_past_their_hourly_budget_is_refused_politely(
        tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra="caller_turn_budget_per_hour = 2\n") as line:
        svc = line.svc
        no_speech_wait(svc, monkeypatch)

        result = await drive(line, [
            setup_frame(),
            prompt_frame("hello"),
            prompt_frame("my sink is leaking"),
            prompt_frame("and the tap drips"),
        ])

        assert "reached its limit for now" in result.spoken
        assert [json.loads(e["handoffData"])["reason"] for e in result.ends] == ["end"]
        assert "rate_limited" in kinds(svc)
        call = one_call(svc)
        assert call["outcome"] == "rate_limited"
        # what they DID say still reaches the owner — the refusal promises that
        assert line.brain.note in line.pad.read_text(encoding="utf-8")


async def test_a_caller_inside_their_budget_is_left_alone(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra="caller_turn_budget_per_hour = 5\n") as line:
        svc = line.svc
        result = await drive(line, [setup_frame(), prompt_frame("hello"),
                                    prompt_frame("my sink is leaking")])

        assert "reached its limit" not in result.spoken
        assert "rate_limited" not in kinds(svc)
        assert one_call(svc)["outcome"] == "message_taken"


def test_a_number_setting_that_is_not_a_number_stops_what_asked_for_it(
        tmp_path, monkeypatch):
    """Validation refuses these at boot and on save. If one ever gets past that,
    it must not be quietly read as zero — which would mean "no budget at all"."""
    svc = _import_service(tmp_path, monkeypatch)
    assert svc.profile_number(svc.PROFILES["acme"], "max_call_seconds") == 600
    svc.PROFILES["acme"]["max_call_seconds"] = "ten minutes"
    with pytest.raises(ValueError):
        svc.profile_number(svc.PROFILES["acme"], "max_call_seconds")


def test_turn_buckets_are_per_business_and_reset_on_the_hour(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    start = 1_700_000_000.0
    caller = "+15085551234"

    assert svc.note_caller_turn("acme", caller, 2, start) is True
    assert svc.note_caller_turn("acme", caller, 2, start + 1) is True
    assert svc.note_caller_turn("acme", caller, 2, start + 2) is False
    # another business's budget is its own
    assert svc.note_caller_turn("other", caller, 2, start + 2) is True

    later = start + svc.RATE_LIMIT_WINDOW_SECONDS
    assert svc.note_caller_turn("acme", caller, 2, later) is True
    # the hour that has passed is gone, and so is the business nobody called
    assert list(svc.CALLER_TURN_BUCKETS[("acme", caller)]) == [
        int(later // svc.RATE_LIMIT_WINDOW_SECONDS)]
    assert ("other", caller) not in svc.CALLER_TURN_BUCKETS


# ======================================================== step 4: block list ==

BLOCKED_CALLER = "+15085559999"


async def _incoming(line, form) -> tuple[int, str]:
    async with aiohttp.ClientSession() as session:
        async with session.post(
                f"{line.base}/voice/incoming",
                **_twilio_post_kwargs(line, "/voice/incoming", form)) as resp:
            return resp.status, await resp.text()


async def test_a_blocked_caller_gets_one_line_and_a_hangup(tmp_path, monkeypatch,
                                                           caplog):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra=f'block_list = ["{BLOCKED_CALLER}"]\n') as line:
        svc = line.svc
        with caplog.at_level(logging.INFO, logger="atlas-phone"):
            status, xml = await _incoming(line, {
                "To": DIALED, "From": BLOCKED_CALLER, "CallSid": CALL_SID})

        assert status == 200
        assert "<Hangup/>" in xml
        assert "we can't take calls from this number" in xml
        assert "ConversationRelay" not in xml          # no session, no model
        assert "blocked" in kinds(svc)
        call = one_call(svc)
        assert call["outcome"] == "blocked"
        assert call["decision_reason"] == "block_list"
        assert call["from_number"] == BLOCKED_CALLER   # the store still knows
        assert BLOCKED_CALLER not in caplog.text       # the journal does not


async def test_a_caller_who_is_not_on_the_list_is_answered(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra=f'block_list = ["{BLOCKED_CALLER}"]\n') as line:
        status, xml = await _incoming(line, {
            "To": DIALED, "From": "+15085551234", "CallSid": CALL_SID})

        assert status == 200
        assert "ConversationRelay" in xml


# ================================================ step 5: per-business delivery ==

def _other_profile(*, pad="", ntfy_url="", ntfy_topic="", timezone_name="",
                   extra="") -> str:
    lines = ["", "[profiles.other]", 'business_name = "Other Co"',
             'services = "roofing"', 'owner_name = "Sam"', 'greeting = "hello"']
    if pad:
        lines.append(f'messages_file = "{pad}"')
    if ntfy_url:
        lines.append(f'ntfy_url = "{ntfy_url}"')
        lines.append(f'ntfy_topic = "{ntfy_topic}"')
    if timezone_name:
        lines.append(f'timezone = "{timezone_name}"')
    if extra:
        lines.append(extra)
    return "\n".join(lines) + "\n"


async def test_two_businesses_get_two_pads_and_two_push_topics(tmp_path, monkeypatch):
    """Business A's owner must never be the one who reads business B's
    messages — the pad and the push are the two places that could go wrong."""
    second_push = FakeNtfy()
    await second_push.start()
    other_pad = tmp_path / "other-pad.md"
    cfg = _other_profile(pad=str(other_pad), ntfy_url=second_push.base_url,
                         ntfy_topic="other-topic", timezone_name="Asia/Tokyo")
    try:
        async with phone_line(tmp_path, monkeypatch, cfg_extra=cfg) as line:
            await run_call(line, [setup_frame(), prompt_frame("hello")])
            await run_call(line, [setup_frame(call_sid=SECOND_CALL),
                                  prompt_frame("hello")],
                           call_sid=SECOND_CALL, profile="other")

            acme_pad = line.pad.read_text(encoding="utf-8")
            other = other_pad.read_text(encoding="utf-8")
            assert "Acme Co line" in acme_pad and "Other Co line" not in acme_pad
            assert "Other Co line" in other and "Acme Co line" not in other
            assert [p["topic"] for p in line.ntfy.pushes] == ["phone"]
            assert [p["topic"] for p in second_push.pushes] == ["other-topic"]
            # and the second business's pad is stamped in ITS timezone
            assert "JST" in other
            assert datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d") in other
    finally:
        await second_push.stop()


async def test_a_business_without_its_own_targets_uses_the_line_defaults(
        tmp_path, monkeypatch):
    """Nothing changes for a config that never heard of per-business delivery."""
    async with phone_line(tmp_path, monkeypatch, cfg_extra=_other_profile()) as line:
        await run_call(line, [setup_frame(call_sid=SECOND_CALL), prompt_frame("hello")],
                       call_sid=SECOND_CALL, profile="other")

        assert "Other Co line" in line.pad.read_text(encoding="utf-8")
        assert [p["topic"] for p in line.ntfy.pushes] == ["phone"]


def test_delivery_targets_fall_back_to_the_environment(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch,
                          extra_env={"MESSAGES_FILE": str(tmp_path / "env-pad.md"),
                                     "NTFY_URL": "https://push.example",
                                     "NTFY_TOPIC": "env-topic"})
    plain = svc.delivery_targets(svc.PROFILES["acme"])
    assert plain.messages_file == str(tmp_path / "env-pad.md")
    assert (plain.ntfy_url, plain.ntfy_topic) == ("https://push.example", "env-topic")

    svc.PROFILES["acme"]["messages_file"] = "~/own-pad.md"
    svc.PROFILES["acme"]["ntfy_url"] = "https://own.example/"
    svc.PROFILES["acme"]["ntfy_topic"] = "own-topic"
    own = svc.delivery_targets(svc.PROFILES["acme"])
    assert own.messages_file == os.path.expanduser("~/own-pad.md")
    assert (own.ntfy_url, own.ntfy_topic) == ("https://own.example", "own-topic")


async def test_the_dashboard_says_when_a_business_keeps_its_own_pad(
        tmp_path, monkeypatch):
    """The pad panel reads ONE file. A business with its own pad would look
    like a business with no messages."""
    import importlib.util

    from test_phone_agent_plugin import PLUGINS_DIR

    svc = _import_service(tmp_path, monkeypatch,
                          cfg_extra=_other_profile(pad=str(tmp_path / "other-pad.md")))
    spec = importlib.util.spec_from_file_location(
        "phone_agent_admin_pad_notice", PLUGINS_DIR / "phone_agent" / "admin.py")
    assert spec is not None and spec.loader is not None
    admin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admin)

    async def snapshot():
        return {"bridge": "ok", "model_backend": "ok", "model": "m",
                "profiles": ["acme"], "numbers": 1, "ntfy": "off"}, True

    app = admin.build_admin_app(
        token="sesame", health_snapshot=snapshot,
        get_state=lambda: (svc.NUMBERS, svc.PROFILES),
        get_brains=lambda: ({}, ""),
        get_branding=lambda: svc.BRANDING,
        get_owners=lambda: svc.OWNERS,
        get_prompts=lambda: svc.SYSTEM_PROMPTS,
        apply_config_text=svc.apply_config_text,
        emit_business_toml=svc.emit_business_toml,
        messages_file=str(tmp_path / "messages.md"),
        known_keys=svc._PROFILE_KNOWN_KEYS,
        store=svc.STORE,
    )
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    base = f"http://127.0.0.1:{runner.addresses[0][1]}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{base}/login", data={"token": "sesame"},
                                    allow_redirects=False) as resp:
                assert resp.status == 303
            session.cookie_jar.update_cookies({admin.COOKIE: "sesame"})
            async with session.get(base + "/") as resp:
                page = await resp.text()
    finally:
        await runner.cleanup()

    assert "Showing the default pad only" in page
    assert "1 business(es) keep their own pad" in page
    assert "other" in page.split("Showing the default pad only")[1][:200]


async def test_a_business_can_run_on_its_own_brain(tmp_path, monkeypatch):
    backup = FakeBrain()
    backup.reply = "This is the other brain speaking."
    await backup.start()
    try:
        async with phone_line(tmp_path, monkeypatch, ntfy=False,
                              cfg_extra=_other_profile()) as line:
            svc = line.svc
            svc.BRAINS["backup"] = svc.Brain(
                key="backup", label="backup", base_url=backup.base_url,
                model="backup-model", api_key_env="", extra_body={})
            svc.PROFILES["other"]["brain"] = "backup"

            await run_call(line, [setup_frame(call_sid=SECOND_CALL),
                                  prompt_frame("hello")],
                           call_sid=SECOND_CALL, profile="other")

            assert backup.stream_bodies, "the profile's own brain never answered"
            assert not line.brain.stream_bodies, "the active brain answered anyway"
            call = one_call(svc, SECOND_CALL)
            assert call["brain"] == "backup"
            assert call["model"] == "backup-model"
    finally:
        await backup.stop()


async def test_a_brain_that_vanished_is_loud_and_the_call_still_lands(
        tmp_path, monkeypatch):
    """Validation refuses this, so it can only happen if the config changed
    underneath a running bridge. The caller must still be answered."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra=_other_profile()) as line:
        svc = line.svc
        svc.PROFILES["other"]["brain"] = "a-brain-that-was-deleted"

        await run_call(line, [setup_frame(call_sid=SECOND_CALL), prompt_frame("hello")],
                       call_sid=SECOND_CALL, profile="other")

        assert "brain_missing" in kinds(svc)
        assert one_call(svc, SECOND_CALL)["brain"] == svc.ACTIVE_BRAIN
        assert line.brain.note in line.pad.read_text(encoding="utf-8")


# ============================================================ step 6: opt-out ==

@pytest.mark.parametrize("said", [
    "please stop calling me",
    "take me off your list",
    "do not call this number again",
    "don't call me again",
    "DONT CALL ME.",
])
def test_every_opt_out_phrase_is_recognised(tmp_path, monkeypatch, said):
    svc = _import_service(tmp_path, monkeypatch)
    assert svc.detect_opt_out(said) != ""


def test_an_ordinary_sentence_is_not_an_opt_out(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    assert svc.detect_opt_out("can you call me back this afternoon") == ""


async def test_an_opt_out_is_recorded_and_changes_nothing_else(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        await run_call(line, [setup_frame(),
                              prompt_frame("please take me off your list")])

        events = [e for e in svc.RECENT_EVENTS if e["kind"] == "opt_out"]
        assert events, "a caller asked to be taken off the list and nothing recorded it"
        assert events[-1]["call_sid"] == CALL_SID
        # the call itself carried on exactly as it would have
        assert one_call(svc)["outcome"] == "message_taken"
        assert line.brain.note in line.pad.read_text(encoding="utf-8")
        stored = [e for e in svc.STORE.conn.execute(
            "SELECT kind, call_sid FROM events WHERE kind = 'opt_out'")]
        assert stored and stored[0]["call_sid"] == CALL_SID


# =========================================================== step 7: keypress ==

def test_mask_digits_hides_everything_but_the_last_two(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    assert svc.mask_digits("5") == "•"                       # never revealed
    assert svc.mask_digits("42") == "••42"
    assert svc.mask_digits("4111") == "••11"
    assert svc.mask_digits("4111111111111111") == "••11"     # length is hidden too
    assert svc.mask_digits("") == "•"


def test_the_persona_knows_there_is_no_keypad_menu(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    prompt = svc.SYSTEM_PROMPTS["acme"]
    assert "no touch-tone menu" in prompt
    assert "[keypress: ••34]" in prompt


async def test_a_keypress_is_answered_and_its_digits_are_hidden(tmp_path, monkeypatch,
                                                                caplog):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        monkeypatch.setattr(svc, "KEYPRESS_RUN_SECONDS", 0.05)
        with caplog.at_level(logging.INFO, logger="atlas-phone"):
            result = await drive(line, [setup_frame(),
                                        {"type": "dtmf", "digits": "4111"}])

        assert result.spoken == line.brain.reply       # Atlas said something back
        assert "[keypress: ••11]" in line.brain.summarizer_transcript
        for where in (line.brain.summarizer_transcript,
                      line.pad.read_text(encoding="utf-8"), caplog.text):
            assert "4111" not in where
        turns = one_call(svc)["turns"]
        assert [(t["role"], t["text"]) for t in turns] == [
            ("keypress", "[keypress: ••11]"),
            ("agent", line.brain.reply),
        ]


# Twilio sends one dtmf event per keypress. This is the shape that matters.
CARD_NUMBER = "4539123456787890"


async def test_a_card_number_keyed_one_digit_at_a_time_is_one_masked_turn(
        tmp_path, monkeypatch, caplog):
    """Sixteen events, one per keypress. One turn per event would have put the
    card number back together for anyone reading the transcript — each digit
    masked to itself is no mask at all."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra="caller_turn_budget_per_hour = 5\n") as line:
        svc = line.svc
        monkeypatch.setattr(svc, "KEYPRESS_RUN_SECONDS", 0.25)

        with caplog.at_level(logging.INFO, logger="atlas-phone"):
            result = await drive(line, [setup_frame()]
                                 + [{"type": "dtmf", "digit": d} for d in CARD_NUMBER],
                                 idle=0.6)

        turns = [(t["role"], t["text"]) for t in one_call(svc)["turns"]]
        assert turns == [("keypress", "[keypress: ••90]"),
                         ("agent", line.brain.reply)]
        # one acknowledgement, not sixteen
        assert result.spoken == line.brain.reply
        assert len(line.brain.stream_bodies) == 1
        # the summarizer sees one masked line
        transcript = line.brain.summarizer_transcript
        assert transcript.count("[keypress:") == 1
        assert "[keypress: ••90]" in transcript
        # and the number is nowhere: not whole, not in any run of it
        pad = line.pad.read_text(encoding="utf-8")
        for where in (transcript, pad, caplog.text):
            assert CARD_NUMBER not in where
            assert CARD_NUMBER[:-1] not in where
            assert CARD_NUMBER[:8] not in where
        # one run costs one turn of the hourly budget, not sixteen
        assert "rate_limited" not in kinds(svc)
        assert sum(svc.CALLER_TURN_BUCKETS[("acme", "+15550001234")].values()) == 1


async def test_a_single_keypress_is_never_revealed(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        monkeypatch.setattr(svc, "KEYPRESS_RUN_SECONDS", 0.05)
        await drive(line, [setup_frame(), {"type": "dtmf", "digit": "7"}])

        assert [t["text"] for t in one_call(svc)["turns"] if t["role"] == "keypress"] \
            == ["[keypress: •]"]
        assert "7" not in line.brain.summarizer_transcript.split("[keypress:")[1][:6]


async def test_two_runs_far_enough_apart_are_two_turns(tmp_path, monkeypatch):
    """A caller who keys an extension, waits, then keys another has made two
    keypresses — not one long one."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        monkeypatch.setattr(svc, "KEYPRESS_RUN_SECONDS", 0.1)

        async def second_run(ws):
            await asyncio.sleep(0.3)          # longer than the run window
            await ws.send_str(json.dumps({"type": "dtmf", "digits": "78"}))
            await asyncio.sleep(0.3)

        await drive(line, [setup_frame(), {"type": "dtmf", "digits": "12"}],
                    during=second_run, idle=0.4)

        keyed = [t["text"] for t in one_call(svc)["turns"] if t["role"] == "keypress"]
        assert keyed == ["[keypress: ••12]", "[keypress: ••78]"]


# =========================================================== step 8: shutdown ==

async def test_a_shutdown_finishes_the_delivery_and_closes_the_store(
        tmp_path, monkeypatch):
    """SIGTERM arrives mid-call. The caller's message has to land anyway."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        app = web.Application()
        app.router.add_get("/voice/relay", svc.voice_relay)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        svc.track_server(runner, site)
        port = runner.addresses[0][1]
        url = (f"http://127.0.0.1:{port}/voice/relay"
               f"?token={svc.WS_TOKEN}&call={CALL_SID}&profile=acme")

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url) as ws:
                await ws.send_str(json.dumps(setup_frame()))
                await ws.send_str(json.dumps(prompt_frame("please call me back")))
                await _drain_until_last(ws)
                await asyncio.sleep(0.15)
                # hold the summarizer open so the delivery is genuinely in
                # flight when the shutdown starts
                line.brain.summary_delay = 0.4
                await svc.shutdown("test")

        assert line.pad.exists(), "the shutdown took the caller's message with it"
        assert line.brain.note in line.pad.read_text(encoding="utf-8")
        assert svc.IN_FLIGHT_DELIVERIES == set()
        assert svc.SHUTTING_DOWN is True
        with pytest.raises(sqlite3.ProgrammingError):
            svc.STORE.conn.execute("SELECT 1")

        # and a new call is refused rather than started and cut off
        refused = (f"{line.base}/voice/relay?token={svc.WS_TOKEN}"
                   f"&call={SECOND_CALL}&profile=acme")
        assert await _connect_expecting_status(line, refused) == 503


async def test_a_shutdown_waits_for_a_delivery_whose_call_is_already_gone(
        tmp_path, monkeypatch):
    """The hard case: the relay handler has already been torn down and only the
    shielded delivery is left. Nothing is awaiting it but the shutdown itself —
    if that does not wait, the store closes underneath a message being written.
    """
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        handlers: list = []

        async def traced(request):
            handlers.append(asyncio.current_task())
            return await svc.voice_relay(request)

        app = web.Application()
        app.router.add_get("/voice/relay", traced)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = runner.addresses[0][1]
        url = (f"http://127.0.0.1:{port}/voice/relay"
               f"?token={svc.WS_TOKEN}&call={CALL_SID}&profile=acme")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url) as ws:
                    await ws.send_str(json.dumps(setup_frame()))
                    await ws.send_str(json.dumps(prompt_frame("please call me back")))
                    await _drain_until_last(ws)
                    await asyncio.sleep(0.15)
                    line.brain.summary_delay = 0.5
                    handlers[0].cancel()          # unwinds into the finally:
                    await asyncio.sleep(0.1)
                    handlers[0].cancel()          # lands on the shielded await
                    await asyncio.sleep(0.1)

                    assert svc.IN_FLIGHT_DELIVERIES, \
                        "the delivery did not outlive its relay handler"
                    await svc.shutdown("test")

            assert line.pad.exists(), "the shutdown did not wait for the delivery"
            assert line.brain.note in line.pad.read_text(encoding="utf-8")
            assert svc.IN_FLIGHT_DELIVERIES == set()
        finally:
            await runner.cleanup()


async def test_a_shutdown_with_nothing_in_flight_is_quiet(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        await svc.shutdown("test")
        assert svc.SHUTTING_DOWN is True
        await svc.shutdown("test")           # idempotent: no second teardown


# ===================================================== step 9: health recovery ==

async def test_a_failed_delivery_keeps_health_degraded_until_one_succeeds(
        tmp_path, monkeypatch):
    """/health is what the external tripwire pages on. A message that could not
    be written must keep the line marked sick until one actually lands — never
    time out on its own."""
    blocked = tmp_path / "pad-that-is-a-directory"
    blocked.mkdir()
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          messages_file=str(blocked)) as line:
        svc = line.svc
        assert svc.public_health() == (200, {"status": "ok"})

        await run_call(line, [setup_frame(), prompt_frame("please call me back")])
        assert svc.LAST_DELIVERY["ok"] is False
        status, body = svc.public_health()
        assert status == 503 and body["reason"] == "last message delivery failed"

        # a day passes and nothing is fixed: still 503
        svc.LAST_DELIVERY["ts"] -= 86400
        assert svc.public_health()[0] == 503

        # the pad is writable again and one message lands: recovered
        monkeypatch.setattr(svc, "MESSAGES_FILE", str(tmp_path / "working-pad.md"))
        await run_call(line, [setup_frame(call_sid=SECOND_CALL),
                              prompt_frame("please call me back")],
                       call_sid=SECOND_CALL)
        assert svc.LAST_DELIVERY["ok"] is True
        assert svc.public_health() == (200, {"status": "ok"})


# ========================================================== step 10: retention ==

def test_the_retention_sweep_ages_out_every_profile(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch, cfg_extra="retention_days = 30\n")
    store = svc.STORE
    store.start_call("CAold", "acme", "+15085551234", DIALED, "b", "m")
    store.add_turn("CAold", 1, "caller", "words from six weeks ago")
    store.add_event("acme", "CAold", "info", "no_info_note", "nothing to act on")
    with store.conn:
        store.conn.execute("UPDATE calls SET started_at = ? WHERE call_sid = 'CAold'",
                           (time.time() - 42 * 86400,))
        store.conn.execute("UPDATE events SET ts = ? WHERE kind = 'no_info_note'",
                           (time.time() - 42 * 86400,))

    assert svc.purge_all_profiles() == {"acme": 1}

    assert store.get_call("CAold") is not None          # the aggregate survives
    assert store.get_call("CAold")["turns"] == []       # the words do not
    assert store.conn.execute(
        "SELECT COUNT(*) FROM events WHERE kind = 'no_info_note'").fetchone()[0] == 0


def test_one_profile_with_a_broken_setting_does_not_stop_the_others(
        tmp_path, monkeypatch):
    """A sweep that gave up at the first bad profile would silently stop
    honouring every other business's retention promise."""
    svc = _import_service(tmp_path, monkeypatch, cfg_extra=_other_profile())
    svc.RECENT_EVENTS.clear()
    svc.PROFILES["acme"]["retention_days"] = "ninety"

    removed = svc.purge_all_profiles()

    assert list(removed) == ["other"]
    failures = [e for e in svc.RECENT_EVENTS if e["kind"] == "retention_failed"]
    assert failures and "ninety" in failures[0]["detail"]


def test_a_retention_failure_is_recorded_not_swallowed(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    svc.RECENT_EVENTS.clear()

    class Unhappy:
        def purge_expired(self, *args, **kwargs):
            raise RuntimeError("database is locked")

        def add_event(self, *args, **kwargs):
            pass

    monkeypatch.setattr(svc, "STORE", Unhappy())
    assert svc.purge_all_profiles() == {}
    failures = [e for e in svc.RECENT_EVENTS if e["kind"] == "retention_failed"]
    assert failures and "database is locked" in failures[0]["detail"]


async def test_the_retention_task_waits_then_repeats(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    runs: list = []
    monkeypatch.setattr(svc, "purge_all_profiles", lambda: runs.append(1) or {})
    monkeypatch.setattr(svc, "RETENTION_FIRST_RUN_SECONDS", 0.15)
    monkeypatch.setattr(svc, "RETENTION_INTERVAL_SECONDS", 0.05)

    task = asyncio.create_task(svc.retention_task())
    try:
        await asyncio.sleep(0.05)
        assert runs == [], "the sweep ran before the boot delay was over"
        await asyncio.sleep(0.25)
        assert len(runs) >= 2, "the sweep did not repeat"
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_the_store_and_its_write_ahead_log_are_owner_only(tmp_path, monkeypatch):
    """calls.db-wal holds the same transcripts as calls.db, for as long as it
    takes SQLite to check them back in."""
    svc = _import_service(tmp_path, monkeypatch)
    data_dir = Path(svc.PHONE_DATA_DIR)
    present = [p for p in ("calls.db", "calls.db-wal", "calls.db-shm")
               if (data_dir / p).exists()]
    assert "calls.db" in present and "calls.db-wal" in present
    for name in present:
        assert stat.S_IMODE((data_dir / name).stat().st_mode) == 0o600, name


# ======================================================== step 11: token usage ==

async def test_the_call_row_carries_the_tokens_the_brain_reported(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        line.brain.usage = {"prompt_tokens": 120, "completion_tokens": 30}

        await run_call(line, [setup_frame(), prompt_frame("hello"),
                              prompt_frame("my sink is leaking")])

        assert line.brain.stream_bodies[0]["stream_options"] == {"include_usage": True}
        call = one_call(svc)
        assert call["prompt_tokens"] == 240        # two turns, summed
        assert call["completion_tokens"] == 60


async def test_a_brain_that_reports_nothing_leaves_the_columns_empty(
        tmp_path, monkeypatch):
    """Empty is the honest answer: a zero would read as a call that cost
    nothing."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        await run_call(line, [setup_frame(), prompt_frame("hello")])
        call = one_call(line.svc)
        assert call["prompt_tokens"] is None and call["completion_tokens"] is None


async def test_a_backend_that_rejects_stream_options_is_asked_once(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        line.brain.reject_stream_options = True

        await svc.refresh_brain_health()
        body, model_ok = await svc.health_snapshot()

        assert model_ok is True                    # the backend itself is fine
        assert "stream_options" in body["probe_error"]
        assert svc.ACTIVE_BRAIN in svc.BRAINS_WITHOUT_STREAM_OPTIONS
        assert "stream_options_unsupported" in kinds(svc)

        # asked once, not on every refresh
        asked = len(line.brain.stream_bodies)
        line.brain.reject_stream_options = False
        await svc.refresh_brain_health()
        again, _ = await svc.health_snapshot()
        assert again["probe_error"] == ""
        assert len(line.brain.stream_bodies) == asked

        # and the option is left out of that brain's calls from here on
        await run_call(line, [setup_frame(), prompt_frame("hello")])
        assert "stream_options" not in line.brain.stream_bodies[-1]
        assert line.brain.note in line.pad.read_text(encoding="utf-8")


async def test_a_backend_that_accepts_stream_options_keeps_being_asked(
        tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        await svc.refresh_brain_health()
        body, model_ok = await svc.health_snapshot()
        assert model_ok is True and body["probe_error"] == ""
        assert svc.BRAINS_WITHOUT_STREAM_OPTIONS == set()

        # the point of the flag staying clear: every call still asks
        await run_call(line, [setup_frame(), prompt_frame("hello")])
        await run_call(line, [setup_frame(call_sid=SECOND_CALL), prompt_frame("hello")],
                       call_sid=SECOND_CALL)
        asked = [b.get("stream_options") for b in line.brain.stream_bodies[-2:]]
        assert asked == [{"include_usage": True}, {"include_usage": True}]


async def test_a_profile_only_brain_that_rejects_still_answers_the_first_turn(
        tmp_path, monkeypatch, caplog):
    """The rejecting backend may be one only a single business uses. Its caller
    must not hear the error line on every turn forever while the probe watches
    a brain nobody dialled."""
    fussy = FakeBrain()
    fussy.reject_stream_options = True
    fussy.reply = "The fussy brain answered anyway."
    await fussy.start()
    try:
        async with phone_line(tmp_path, monkeypatch, ntfy=False,
                              cfg_extra=_other_profile()) as line:
            svc = line.svc
            svc.BRAINS["fussy"] = svc.Brain(
                key="fussy", label="fussy", base_url=fussy.base_url,
                model="fussy-model", api_key_env="", extra_body={})
            svc.PROFILES["other"]["brain"] = "fussy"

            with caplog.at_level(logging.WARNING, logger="atlas-phone"):
                result = await drive(line, [setup_frame(), prompt_frame("hello")],
                                     profile="other")

            # the caller heard the reply, not the apology — the retry worked
            assert result.spoken == fussy.reply
            assert svc.BRAINS_WITHOUT_STREAM_OPTIONS == {"fussy"}
            assert "stream_options_unsupported" in kinds(svc)
            assert caplog.text.count("rejects stream_options") == 1

            # the second call never asks again
            await run_call(line, [setup_frame(call_sid=SECOND_CALL),
                                  prompt_frame("hello")], call_sid=SECOND_CALL,
                           profile="other")
            assert all("stream_options" not in body for body in fussy.stream_bodies)
    finally:
        await fussy.stop()


async def test_every_brain_a_profile_can_use_is_probed(tmp_path, monkeypatch):
    """The refresher used to watch only the active brain, so a business on its
    own backend had nobody looking at it."""
    other_brain = FakeBrain()
    await other_brain.start()
    try:
        async with phone_line(tmp_path, monkeypatch, ntfy=False,
                              cfg_extra=_other_profile()) as line:
            svc = line.svc
            svc.BRAINS["theirs"] = svc.Brain(
                key="theirs", label="theirs", base_url=other_brain.base_url,
                model="their-model", api_key_env="", extra_body={})
            svc.PROFILES["other"]["brain"] = "theirs"

            assert svc.referenced_brains() == {svc.ACTIVE_BRAIN, "theirs"}
            await svc.refresh_brain_health()

            assert svc.BRAIN_HEALTH["theirs"]["reachable"] is True
            assert other_brain.model_hits == 1
    finally:
        await other_brain.stop()


# ============================================== step 3 (round 2): /health ==

async def test_the_public_health_endpoint_never_calls_a_model(tmp_path, monkeypatch):
    """It is reachable from the whole internet. A probe on this path let anyone
    with a refresh key spend the owner's money on chat completions."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        async with aiohttp.ClientSession() as session:
            for _ in range(50):
                async with session.get(f"{line.base}/health") as resp:
                    assert resp.status == 200
                    assert await resp.json() == {"status": "ok"}

        assert line.brain.model_hits == 0
        assert line.brain.stream_bodies == []


async def test_the_refresher_fills_the_cache_and_health_reads_it(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        # nothing probed yet: unknown is not sick
        assert svc.BRAIN_HEALTH == {}
        assert svc.public_health() == (200, {"status": "ok"})
        body, model_ok = await svc.health_snapshot()
        assert body["model_backend"] == "pending" and model_ok is True
        assert body["probe_checked_at"] is None

        await svc.refresh_brain_health()
        assert svc.BRAIN_HEALTH[svc.ACTIVE_BRAIN]["reachable"] is True
        body, model_ok = await svc.health_snapshot()
        assert body["model_backend"] == "ok" and body["probe_checked_at"] is not None
        assert svc.public_health() == (200, {"status": "ok"})


async def test_a_brain_that_dies_turns_health_red_on_the_next_sweep(
        tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        await svc.refresh_brain_health(now=0.0)
        assert svc.public_health()[0] == 200

        line.brain.models_status = 500
        await svc.refresh_brain_health(now=1.0)          # the very next sweep

        status, body = svc.public_health()
        assert status == 503 and body["reason"] == "model backend unreachable"
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{line.base}/health") as resp:
                assert resp.status == 503


async def test_an_unreachable_brain_is_asked_less_and_less_often(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        line.brain.models_status = 500

        await svc.refresh_brain_health(now=0.0)
        state = svc.BRAIN_HEALTH[svc.ACTIVE_BRAIN]
        assert state["reachable"] is False
        assert (state["attempts"], state["next_at"]) == (1, 60.0)

        await svc.refresh_brain_health(now=10.0)          # inside the backoff
        assert state["attempts"] == 1, "it asked again while backing off"

        for moment, expected in ((60.0, 300), (400.0, 1800), (3000.0, 21600),
                                 (40000.0, 21600)):
            await svc.refresh_brain_health(now=moment)
            assert state["next_at"] == moment + expected

        # and a backend that comes back is trusted again immediately
        line.brain.models_status = 200
        await svc.refresh_brain_health(now=200000.0)
        assert state["reachable"] is True and state["attempts"] == 0
        assert svc.public_health()[0] == 200


async def test_the_health_refresher_keeps_running(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        monkeypatch.setattr(svc, "HEALTH_REFRESH_SECONDS", 0.05)
        task = asyncio.create_task(svc.health_refresh_task())
        try:
            await asyncio.sleep(0.2)
            assert svc.BRAIN_HEALTH[svc.ACTIVE_BRAIN]["reachable"] is True
            assert line.brain.model_hits >= 2
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


# ====================================================== step 12: the journal ==

def test_mask_number_shows_only_the_last_four(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    assert svc.mask_number("+15085551234") == "•••••••1234"
    assert svc.mask_number("+441234567890") == "••••••••7890"
    assert svc.mask_number("unknown") == "unknown"
    assert svc.mask_number("") == "unknown"
    assert svc.mask_number("+123") == "•••"


async def test_the_journal_never_holds_a_whole_caller_number(tmp_path, monkeypatch,
                                                             caplog):
    caller = "+15085557788"
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        with caplog.at_level(logging.INFO, logger="atlas-phone"):
            status, _xml = await _incoming(line, {
                "To": DIALED, "From": caller, "CallSid": CALL_SID})
            assert status == 200
            await run_call(line, [setup_frame(caller=caller), prompt_frame("hello")])

        assert caller not in caplog.text
        assert "•••••••7788" in caplog.text
        # the store still holds the real number — retention and delete_caller
        # are what removes it, not a log line that never had it
        assert one_call(line.svc)["from_number"] == caller

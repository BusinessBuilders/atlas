# tests/test_phone_agent_twilio.py — the Twilio-side surface of the phone line.
#
# Task 6 of the productization plan: the status callback that records what the
# carrier says a call was, the inbound-SMS webhook that turns a text into a
# message on the owner's pad, the warm-transfer whisper that tells the human
# who is being handed to them, the fallback TwiML the VPS serves when this
# machine is unreachable, and the script that puts those URLs on the number.
#
# Same standard as the rest of the suite: real handlers on a real loopback
# socket, a real (fake) Twilio REST API on another one. Nothing here talks to
# Twilio, and no test needs a secret — the account SID is "ACtest" and the auth
# token is "t", exactly as _import_service boots the service with.
import importlib.util
import json
import logging
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import aiohttp
import pytest
from aiohttp import web
from test_phone_agent_hardening import (
    CALL_SID,
    WS_SECRET,
    FakeNtfy,
    _connect_expecting_status,
    _twilio_post_kwargs,
    phone_line,
    prompt_frame,
    run_call,
    setup_frame,
    wstoken_module,
)
from test_phone_agent_plugin import _import_service

REPO = Path(__file__).resolve().parents[1]
PHONE_DEPLOY = REPO / "deploy" / "phone"
FALLBACK_TEMPLATE = PHONE_DEPLOY / "fallback.xml.template"
NGINX_CONF = PHONE_DEPLOY / "nginx-phone-fallback.conf"
TWILIO_CONFIG = REPO / "plugins" / "phone_agent" / "twilio_config.py"

DIALED = "+15550001111"
CALLER = "+15085557788"          # not a +1555 number: a real-looking caller
MESSAGE_SID = "SMtest0000000000000000000000001"


# ------------------------------------------------------------- helpers -----

async def _post(line, path: str, **kwargs):
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{line.base}{path}", **kwargs) as resp:
            return resp.status, await resp.text()


async def _get(line, path: str, **kwargs):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{line.base}{path}", **kwargs) as resp:
            return resp.status, await resp.text()


def kinds(svc) -> list:
    return [e["kind"] for e in svc.RECENT_EVENTS]


def one_row(svc, sql: str, params=()):
    return svc.STORE.conn.execute(sql, params).fetchone()


def twilio_config_module():
    """Import the number-configuration script as a module (it is a CLI, but
    every decision it makes is a pure function that can be tested alone)."""
    spec = importlib.util.spec_from_file_location(
        "twilio_config_under_test", TWILIO_CONFIG)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ========================================================= /voice/status ====

async def test_status_callback_rejects_an_unsigned_post(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        status, _ = await _post(line, "/voice/status", data={
            "CallSid": CALL_SID, "CallStatus": "completed"})
        assert status == 403


async def test_status_callback_records_what_the_carrier_says(tmp_path, monkeypatch):
    """Ours and Twilio's idea of a call differ often enough that both belong in
    the row — this is where theirs arrives."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        await run_call(line, [setup_frame(caller=CALLER), prompt_frame("hello")])

        form = {"CallSid": CALL_SID, "CallStatus": "completed",
                "CallDuration": "37", "Price": "-0.0085"}
        status, body = await _post(line, "/voice/status",
                                   **_twilio_post_kwargs(line, "/voice/status", form))

        assert status == 200
        assert body.strip() == "<Response></Response>"
        row = one_row(line.svc, "SELECT twilio_status, twilio_duration_s, twilio_price "
                                "FROM calls WHERE call_sid = ?", (CALL_SID,))
        assert (row["twilio_status"], row["twilio_duration_s"],
                row["twilio_price"]) == ("completed", 37, "-0.0085")


async def test_an_early_status_has_no_duration_and_no_price(tmp_path, monkeypatch):
    """Twilio calls back on `ringing` too, with neither number. Empty must stay
    empty — a zero would read as a call that connected and cost nothing."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        await run_call(line, [setup_frame(caller=CALLER), prompt_frame("hello")])

        form = {"CallSid": CALL_SID, "CallStatus": "ringing",
                "CallDuration": "", "Price": ""}
        status, _ = await _post(line, "/voice/status",
                                **_twilio_post_kwargs(line, "/voice/status", form))

        assert status == 200
        row = one_row(line.svc, "SELECT twilio_status, twilio_duration_s, twilio_price "
                                "FROM calls WHERE call_sid = ?", (CALL_SID,))
        assert row["twilio_status"] == "ringing"
        assert row["twilio_duration_s"] is None and row["twilio_price"] is None


async def test_a_status_for_a_call_we_never_saw_is_a_warning_not_a_500(
        tmp_path, monkeypatch):
    """Twilio retries a 5xx, so our own gap in the record must never be
    answered with one — it is a 200 and an event."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        line.svc.RECENT_EVENTS.clear()
        form = {"CallSid": "CAtest99999999999", "CallStatus": "completed",
                "CallDuration": "12"}
        status, _ = await _post(line, "/voice/status",
                                **_twilio_post_kwargs(line, "/voice/status", form))

        assert status == 200
        events = [e for e in line.svc.RECENT_EVENTS
                  if e["kind"] == "status_for_unknown_call"]
        assert events and events[0]["level"] == "warning"
        assert events[0]["call_sid"] == "CAtest99999999999"


# ========================================================= /sms/incoming ====

def _sms_form(body="My gutter is leaking, can someone call me back?",
              caller=CALLER, to=DIALED, sid=MESSAGE_SID) -> dict:
    return {"MessageSid": sid, "From": caller, "To": to, "Body": body}


async def test_sms_rejects_an_unsigned_post(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        status, _ = await _post(line, "/sms/incoming", data=_sms_form())
        assert status == 403


async def test_an_inbound_text_becomes_a_message_on_the_pad(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch) as line:
        form = _sms_form()
        status, body = await _post(line, "/sms/incoming",
                                   **_twilio_post_kwargs(line, "/sms/incoming", form))

        # empty TwiML: nothing is sent back until A2P 10DLC registration
        assert status == 200
        assert body.strip() == "<Response></Response>"

        call = line.svc.STORE.get_call(MESSAGE_SID)
        assert call is not None
        assert (call["profile_key"], call["from_number"], call["to_number"]) == (
            "acme", CALLER, DIALED)
        assert call["outcome"] == "message_taken"
        assert call["is_test"] == 0

        messages = line.svc.STORE.list_messages(["acme"])
        assert len(messages) == 1
        assert messages[0]["need"] == form["Body"]
        assert messages[0]["callback"] == CALLER
        assert messages[0]["status"] == "new"

        pad = line.pad.read_text(encoding="utf-8")
        assert form["Body"] in pad
        assert "text message" in pad.lower()
        assert MESSAGE_SID in pad

        assert line.ntfy.pushes and form["Body"] in line.ntfy.pushes[0]["body"]
        assert "Text" in line.ntfy.pushes[0]["headers"]["Title"]


async def test_a_blocked_number_cannot_reach_the_owner_by_text(tmp_path, monkeypatch):
    """The block list is how an owner stops a nuisance. A number whose CALL is
    refused must not be able to put a message on the pad and a push on their
    phone by texting instead."""
    nuisance = "+15085550123"
    async with phone_line(tmp_path, monkeypatch,
                          cfg_extra=f'block_list = ["{nuisance}"]\n') as line:
        status, body = await _post(
            line, "/sms/incoming",
            **_twilio_post_kwargs(line, "/sms/incoming", _sms_form(caller=nuisance)))

        assert status == 200 and body.strip() == "<Response></Response>"
        assert line.svc.STORE.list_messages(["acme"], include_test=True) == []
        assert not line.pad.exists()
        assert line.ntfy.pushes == []
        # …but it is still on the record: "did that number get through?"
        assert line.svc.STORE.get_call(MESSAGE_SID)["outcome"] == "blocked"
        assert "blocked" in kinds(line.svc)


async def test_a_number_not_on_the_list_still_gets_through(tmp_path, monkeypatch):
    """The control: the block list must not quietly swallow everyone."""
    async with phone_line(tmp_path, monkeypatch,
                          cfg_extra='block_list = ["+15085550123"]\n') as line:
        await _post(line, "/sms/incoming",
                    **_twilio_post_kwargs(line, "/sms/incoming", _sms_form()))

        assert len(line.svc.STORE.list_messages(["acme"])) == 1
        assert len(line.ntfy.pushes) == 1


async def test_the_same_text_delivered_twice_is_kept_once(tmp_path, monkeypatch):
    """Twilio retries a webhook that timed out, and the push can take ten
    seconds. One slow push must not become two messages the owner answers."""
    async with phone_line(tmp_path, monkeypatch) as line:
        form = _sms_form()
        for _ in range(2):
            status, _body = await _post(
                line, "/sms/incoming",
                **_twilio_post_kwargs(line, "/sms/incoming", form))
            assert status == 200

        assert len(line.svc.STORE.list_messages(["acme"])) == 1
        assert line.pad.read_text(encoding="utf-8").count(form["Body"]) == 1
        assert len(line.ntfy.pushes) == 1
        assert "sms_already_recorded" in kinds(line.svc)


async def test_a_text_to_an_unmapped_number_is_recorded_and_answered_emptily(
        tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        line.svc.RECENT_EVENTS.clear()
        form = _sms_form(to="+15559998888")
        status, body = await _post(line, "/sms/incoming",
                                   **_twilio_post_kwargs(line, "/sms/incoming", form))

        assert status == 200
        assert body.strip() == "<Response></Response>"
        assert "sms_for_unmapped_number" in kinds(line.svc)
        assert line.svc.STORE.get_call(MESSAGE_SID) is None
        assert line.svc.STORE.list_messages(["acme"]) == []


async def test_the_journal_never_holds_the_texter_number_or_their_words(
        tmp_path, monkeypatch, caplog):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        form = _sms_form(body="my card number is 4111 1111 1111 1111")
        with caplog.at_level(logging.INFO, logger="atlas-phone"):
            await _post(line, "/sms/incoming",
                        **_twilio_post_kwargs(line, "/sms/incoming", form))

        assert CALLER not in caplog.text
        assert "4111" not in caplog.text
        assert "•••••••7788" in caplog.text


async def test_a_text_body_is_scrubbed_and_capped(tmp_path, monkeypatch):
    """A newline in the body would otherwise write a line of its own into the
    pad, and 40kB of text would sit in the store forever."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        form = _sms_form(body="line one\nline two\r\n" + "x" * 4000)
        await _post(line, "/sms/incoming",
                    **_twilio_post_kwargs(line, "/sms/incoming", form))

        need = line.svc.STORE.list_messages(["acme"])[0]["need"]
        assert "\n" not in need and "\r" not in need
        assert need.startswith("line one line two ")
        assert len(need) == line.svc.MAX_SMS_BODY_CHARS


async def test_a_text_from_a_fixture_number_is_flagged_as_a_test(
        tmp_path, monkeypatch):
    """Same rule as calls: a +1555 number can never sit in the owner's message
    list looking like a paying customer."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        form = _sms_form(caller="+15550009999")
        await _post(line, "/sms/incoming",
                    **_twilio_post_kwargs(line, "/sms/incoming", form))

        assert line.svc.STORE.get_call(MESSAGE_SID)["is_test"] == 1
        assert line.svc.STORE.list_messages(["acme"]) == []          # hidden
        assert len(line.svc.STORE.list_messages(["acme"], include_test=True)) == 1


async def test_a_text_goes_to_the_businesss_own_pad_and_topic(tmp_path, monkeypatch):
    """Per-business delivery, the same path a call's message takes: business
    A's owner must never be the one who reads business B's texts."""
    second_push = FakeNtfy()
    await second_push.start()
    other_pad = tmp_path / "other-pad.md"
    cfg = (
        "\n[profiles.other]\nbusiness_name = \"Other Ltd\"\nservices = \"things\"\n"
        "owner_name = \"Sam\"\ngreeting = \"hello\"\n"
        f'messages_file = "{other_pad}"\n'
        f'ntfy_url = "{second_push.base_url}"\nntfy_topic = "other-topic"\n'
    )
    try:
        async with phone_line(tmp_path, monkeypatch, cfg_extra=cfg) as line:
            line.svc.NUMBERS["+15550002222"] = "other"

            form = _sms_form(to="+15550002222")
            await _post(line, "/sms/incoming",
                        **_twilio_post_kwargs(line, "/sms/incoming", form))

            assert form["Body"] in other_pad.read_text(encoding="utf-8")
            assert not line.pad.exists()
            assert line.ntfy.pushes == []
            assert [p["topic"] for p in second_push.pushes] == ["other-topic"]
    finally:
        await second_push.stop()


async def test_a_text_whose_push_fails_degrades_the_line(tmp_path, monkeypatch):
    """The owner learns about messages FROM the push. A dead push channel is a
    message nobody is watching — it must show on /health."""
    async with phone_line(tmp_path, monkeypatch) as line:
        line.ntfy.status = 500
        await _post(line, "/sms/incoming",
                    **_twilio_post_kwargs(line, "/sms/incoming", _sms_form()))

        assert "ntfy_push_failed" in kinds(line.svc)
        status, body = line.svc.public_health()
        assert status == 503 and "notification" in body["reason"]


# ======================================================== /voice/whisper ====

def _relay_token(svc, call_sid=CALL_SID) -> str:
    """A per-call websocket token, for the tests that set WS_SECRET — with a
    secret set the shared static token stops being accepted."""
    return wstoken_module().mint(WS_SECRET.encode(), call_sid, time.time())


def _whisper_token(svc, call_sid=CALL_SID, now=None, ttl=None) -> str:
    now = time.time() if now is None else now
    ttl = svc.WHISPER_TOKEN_TTL_SECONDS if ttl is None else ttl
    return wstoken_module().mint(WS_SECRET.encode(), svc.whisper_subject(call_sid),
                                 now, ttl)


def _say(twiml: str) -> str:
    root = ET.fromstring(twiml)
    said = root.find("Say")
    assert said is not None, twiml
    return (said.text or "").strip()


async def test_whisper_refuses_a_bad_token(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        status, _ = await _post(line, f"/voice/whisper?call={CALL_SID}&t=nonsense")
        assert status == 403


async def test_whisper_refuses_a_token_minted_for_another_call(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        token = _whisper_token(line.svc, call_sid="CAtest00000000002")
        status, _ = await _post(line, f"/voice/whisper?call={CALL_SID}&t={token}")
        assert status == 403


async def test_whisper_refuses_an_expired_token(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        token = _whisper_token(line.svc, now=time.time() - 600, ttl=300)
        status, _ = await _post(line, f"/voice/whisper?call={CALL_SID}&t={token}")
        assert status == 403


async def test_a_relay_token_cannot_fetch_the_whisper(tmp_path, monkeypatch):
    """The two tokens are minted from the same secret, so they are separated by
    what they are bound to — otherwise one leaked URL would open the other."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        relay = wstoken_module().mint(WS_SECRET.encode(), CALL_SID, time.time())
        status, _ = await _post(line, f"/voice/whisper?call={CALL_SID}&t={relay}")
        assert status == 403


async def test_a_whisper_token_cannot_open_the_relay(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        token = _whisper_token(line.svc)
        url = (f"{line.base}/voice/relay?token={token}&call={CALL_SID}&profile=acme")
        assert await _connect_expecting_status(line, url) == 401


async def test_the_whisper_says_who_is_being_transferred_and_what_they_said(
        tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        await run_call(line, [setup_frame(caller=CALLER),
                              prompt_frame("my gutter is falling off the house")],
                       token=_relay_token(line.svc))

        token = _whisper_token(line.svc)
        status, twiml = await _post(line, f"/voice/whisper?call={CALL_SID}&t={token}")

        assert status == 200
        said = _say(twiml)
        assert said.startswith("Incoming transfer from •••••••7788.")
        assert "my gutter is falling off the house" in said
        # the human sees the caller ID on their own phone; this line never
        # carries the whole number
        assert CALLER not in twiml


async def test_the_whisper_is_fetched_by_get_too(tmp_path, monkeypatch):
    """Twilio's <Number url=…> is a POST by default and a GET when the TwiML
    says so — a whisper that only answered one of them is a silent call."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        await run_call(line, [setup_frame(caller=CALLER), prompt_frame("hello there")],
                       token=_relay_token(line.svc))
        token = _whisper_token(line.svc)
        status, twiml = await _get(line, f"/voice/whisper?call={CALL_SID}&t={token}")
        assert status == 200 and "hello there" in _say(twiml)


async def test_the_whisper_trims_a_long_turn(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        long_turn = "I need someone to look at the roof " + "and the gutters " * 30
        await run_call(line, [setup_frame(caller=CALLER), prompt_frame(long_turn)],
                       token=_relay_token(line.svc))

        token = _whisper_token(line.svc)
        _status, twiml = await _post(line, f"/voice/whisper?call={CALL_SID}&t={token}")

        spoken = _say(twiml).split("They said: ", 1)[1]
        assert len(spoken) <= line.svc.MAX_WHISPER_TURN_CHARS + 1     # + the full stop
        assert spoken.startswith("I need someone to look at the roof")


async def test_the_whisper_never_reads_out_a_keypress(tmp_path, monkeypatch):
    """A caller who keys digits is as often typing a card number as an
    extension, and the masked run is meaningless read aloud. The whisper says
    the last thing the caller SAID, even when the last turn was keyed."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        await run_call(line, [setup_frame(caller=CALLER),
                              prompt_frame("my gutter is falling off")],
                       token=_relay_token(line.svc))
        line.svc.STORE.add_turn(CALL_SID, 9, "keypress", "[keypress: ••11]")

        token = _whisper_token(line.svc)
        _status, twiml = await _post(line, f"/voice/whisper?call={CALL_SID}&t={token}")

        said = _say(twiml)
        assert said.endswith("They said: my gutter is falling off.")
        assert "keypress" not in said


async def test_a_whisper_for_a_call_with_no_record_still_answers(tmp_path, monkeypatch):
    """The token proves the transfer is real, so the human is connected either
    way — but a call the store never got is an event worth having."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        line.svc.RECENT_EVENTS.clear()
        token = _whisper_token(line.svc)
        status, twiml = await _post(line, f"/voice/whisper?call={CALL_SID}&t={token}")

        assert status == 200
        assert _say(twiml) == "Incoming transfer."
        assert "whisper_without_call" in kinds(line.svc)


async def test_a_whisper_for_a_call_with_nothing_said_is_short(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        line.svc.STORE.start_call(CALL_SID, "acme", CALLER, DIALED, "b", "m")
        token = _whisper_token(line.svc)
        _status, twiml = await _post(line, f"/voice/whisper?call={CALL_SID}&t={token}")
        assert _say(twiml) == "Incoming transfer from •••••••7788."


# ----------------------------------------- the transfer TwiML that uses it --

async def _action_twiml(line, reason="transfer", call_sid=CALL_SID) -> str:
    form = {"CallSid": call_sid, "HandoffData": json.dumps({"reason": reason})}
    path = "/voice/action?profile=acme"
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{line.base}{path}",
                                **_twilio_post_kwargs(line, path, form)) as resp:
            assert resp.status == 200
            return await resp.text()


async def test_a_transfer_dials_through_the_whisper(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra='forward_to = "+15550002222"\n',
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        twiml = await _action_twiml(line)

        number = ET.fromstring(twiml).find("Dial/Number")
        assert number is not None and number.text == "+15550002222"
        url = urlparse(number.attrib["url"])
        assert url.path.endswith("/voice/whisper")
        query = parse_qs(url.query)
        assert query["call"] == [CALL_SID]
        assert wstoken_module().verify(
            WS_SECRET.encode(), query["t"][0],
            line.svc.whisper_subject(CALL_SID), time.time())


async def test_the_whisper_token_is_short_lived(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra='forward_to = "+15550002222"\n',
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        twiml = await _action_twiml(line)
        token = parse_qs(urlparse(
            ET.fromstring(twiml).find("Dial/Number").attrib["url"]).query)["t"][0]

        assert line.svc.WHISPER_TOKEN_TTL_SECONDS == 300
        expiry = wstoken_module().expiry_of(token)
        assert 0 < expiry - time.time() <= 300


async def test_the_transfer_url_a_caller_would_fetch_actually_works(
        tmp_path, monkeypatch):
    """End to end: the URL in the TwiML is the URL Twilio fetches, and it plays
    the summary. A whisper URL that 403s is a silent transfer."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra='forward_to = "+15550002222"\n',
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        await run_call(line, [setup_frame(caller=CALLER),
                              prompt_frame("please put me through to a person")],
                       token=_relay_token(line.svc))
        twiml = await _action_twiml(line)
        url = urlparse(ET.fromstring(twiml).find("Dial/Number").attrib["url"])

        status, whisper = await _post(line, f"{url.path.split('/phone')[-1]}?{url.query}")
        assert status == 200
        assert "please put me through to a person" in _say(whisper)


async def test_without_a_ws_secret_the_transfer_still_dials_and_says_why(
        tmp_path, monkeypatch):
    """The whisper is a nicety; connecting the caller is not. With no secret to
    sign a token there is nothing to verify, so the whisper is off — loudly."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra='forward_to = "+15550002222"\n') as line:
        line.svc.RECENT_EVENTS.clear()
        twiml = await _action_twiml(line)

        number = ET.fromstring(twiml).find("Dial/Number")
        assert number is not None and "url" not in number.attrib
        assert "whisper_unavailable" in kinds(line.svc)

        # and with no secret, nothing can pass the token check either
        status, _ = await _post(line, f"/voice/whisper?call={CALL_SID}&t=anything")
        assert status == 403


async def test_a_hangup_never_carries_a_whisper(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra='forward_to = "+15550002222"\n',
                          extra_env={"WS_SECRET": WS_SECRET}) as line:
        twiml = await _action_twiml(line, reason="end")
        assert "whisper" not in twiml and "<Dial>" not in twiml


# ===================================================== the fallback TwiML ====

def test_the_fallback_template_is_in_the_deploy_folder():
    assert FALLBACK_TEMPLATE.exists(), FALLBACK_TEMPLATE
    text = FALLBACK_TEMPLATE.read_text(encoding="utf-8")
    assert "{{SAY}}" in text and "{{ACTION}}" in text


def test_a_business_with_a_forward_number_gets_dialled_through():
    tc = twilio_config_module()
    xml = tc.render_fallback("Acme Plumbing", "+15085550100")
    root = ET.fromstring(xml)
    assert "Acme Plumbing" in (root.find("Say").text or "")
    assert root.find("Dial/Number").text == "+15085550100"
    assert root.find("Hangup") is None


def test_a_business_without_one_hears_an_apology_and_a_hangup():
    tc = twilio_config_module()
    xml = tc.render_fallback("Acme Plumbing", "")
    root = ET.fromstring(xml)
    assert "Acme Plumbing" in (root.find("Say").text or "")
    assert root.find("Dial") is None
    assert root.find("Hangup") is not None


def test_a_business_name_with_an_ampersand_still_renders_valid_xml():
    tc = twilio_config_module()
    xml = tc.render_fallback("Smith & Sons", "+15085550100")
    assert "Smith &amp; Sons" in xml
    assert "Smith & Sons" in (ET.fromstring(xml).find("Say").text or "")


def test_the_nginx_snippet_serves_the_rendered_file_as_xml():
    assert NGINX_CONF.exists(), NGINX_CONF
    text = NGINX_CONF.read_text(encoding="utf-8")
    assert "location = /phone/fallback.xml" in text
    assert "default_type text/xml;" in text
    assert text.count("{") == text.count("}")
    # the per-number files the renderer writes need a home too
    assert "fallback-" in text


# ======================================================= twilio_config.py ====

INTENDED_FIELDS = ("voice_url", "voice_fallback_url", "status_callback", "sms_url")


def _numbers_config(tmp_path, extra="") -> Path:
    cfg = tmp_path / "businesses.toml"
    cfg.write_text(
        '[numbers]\n"+15088863046" = "business_builders"\n\n'
        "[profiles.business_builders]\nbusiness_name = \"Business Builders\"\n"
        "services = \"websites and automation\"\nowner_name = \"William\"\n"
        "greeting = \"hi\"\nforward_to = \"+15085550100\"\n" + extra,
        encoding="utf-8")
    return cfg


def test_the_intended_settings_are_the_four_urls(tmp_path):
    tc = twilio_config_module()
    mapping = tc.load_numbers(_numbers_config(tmp_path))
    intended = tc.intended_settings("https://ai.business-builder.online/phone", mapping)

    assert set(intended) == {"+15088863046"}
    want = intended["+15088863046"]
    assert set(want) == set(INTENDED_FIELDS)
    assert want["voice_url"] == "https://ai.business-builder.online/phone/voice/incoming"
    assert want["status_callback"] == "https://ai.business-builder.online/phone/voice/status"
    assert want["sms_url"] == "https://ai.business-builder.online/phone/sms/incoming"
    assert want["voice_fallback_url"] == (
        "https://ai.business-builder.online/phone/fallback.xml")


def test_two_numbers_get_two_fallback_files(tmp_path):
    """One shared fallback file can only name one business — so as soon as
    there are two, each number gets its own."""
    tc = twilio_config_module()
    cfg = _numbers_config(tmp_path, extra=(
        "\n[profiles.other]\nbusiness_name = \"Other Ltd\"\nservices = \"things\"\n"
        "owner_name = \"Sam\"\ngreeting = \"hello\"\n"))
    cfg.write_text(cfg.read_text(encoding="utf-8").replace(
        '[numbers]\n"+15088863046" = "business_builders"\n',
        '[numbers]\n"+15088863046" = "business_builders"\n"+15085550199" = "other"\n'),
        encoding="utf-8")
    mapping = tc.load_numbers(cfg)
    intended = tc.intended_settings("https://example.test/phone", mapping)

    assert intended["+15088863046"]["voice_fallback_url"] == (
        "https://example.test/phone/fallback-15088863046.xml")
    assert intended["+15085550199"]["voice_fallback_url"] == (
        "https://example.test/phone/fallback-15085550199.xml")


def test_the_plan_is_only_what_differs():
    tc = twilio_config_module()
    current = {"voice_url": "https://old.test/voice", "voice_fallback_url": None,
               "status_callback": "", "sms_url": "https://demo.twilio.com/welcome/sms/reply"}
    intended = {"voice_url": "https://new.test/voice/incoming",
                "voice_fallback_url": "https://new.test/fallback.xml",
                "status_callback": "https://new.test/voice/status",
                "sms_url": "https://new.test/sms/incoming"}

    assert tc.plan(current, intended) == intended

    settled = tc.plan(dict(intended), intended)
    assert settled == {}

    current["voice_url"] = intended["voice_url"]
    partial = tc.plan(current, intended)
    assert "voice_url" not in partial and len(partial) == 3


def test_a_missing_field_reads_as_unset_not_as_a_difference():
    """Twilio omits a field it has never been given; None and "" mean the same
    thing, and neither is a reason to say a URL "changed" when it did not."""
    tc = twilio_config_module()
    assert tc.plan({"sms_url": None}, {"sms_url": ""}) == {}
    assert tc.plan({}, {"sms_url": ""}) == {}


def test_the_api_parameters_are_twilios_own_names():
    tc = twilio_config_module()
    assert tc.api_params({"voice_url": "u", "sms_url": "s"}) == {
        "VoiceUrl": "u", "SmsUrl": "s"}


def test_rendering_writes_one_file_per_number(tmp_path):
    tc = twilio_config_module()
    out = tmp_path / "rendered"
    mapping = tc.load_numbers(_numbers_config(tmp_path))
    written = tc.render_all(mapping, out)

    assert [p.name for p in written] == ["fallback-15088863046.xml"]
    xml = written[0].read_text(encoding="utf-8")
    assert ET.fromstring(xml).find("Dial/Number").text == "+15085550100"


# ------------------------------------------------- the CLI, against a fake --

class FakeTwilioApi:
    """Twilio's REST API, as far as this script uses it: list the numbers on an
    account, and update one."""

    def __init__(self) -> None:
        self.numbers = [{
            "sid": "PNtest0000000000000000000000001",
            "phone_number": "+15088863046",
            "friendly_name": "Business Builders",
            "voice_url": "https://ai.business-builder.online/phone/voice/incoming",
            "voice_fallback_url": None,
            "status_callback": None,
            "sms_url": "https://demo.twilio.com/welcome/sms/reply",
        }]
        self.updates: list[dict] = []
        self.auth_seen: list[str] = []
        self.list_status = 200
        self.base_url = ""
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json",
                           self._list)
        app.router.add_post(
            "/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers/{pn}.json", self._update)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", 0).start()
        self.base_url = f"http://127.0.0.1:{self._runner.addresses[0][1]}"

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    async def _list(self, request: web.Request) -> web.Response:
        self.auth_seen.append(request.headers.get("Authorization", ""))
        if self.list_status != 200:
            return web.json_response(
                {"message": "Authenticate", "status": self.list_status},
                status=self.list_status)
        return web.json_response({"incoming_phone_numbers": self.numbers})

    async def _update(self, request: web.Request) -> web.Response:
        self.auth_seen.append(request.headers.get("Authorization", ""))
        form = dict(await request.post())
        self.updates.append({"pn": request.match_info["pn"], "form": form})
        return web.json_response(self.numbers[0])


AUTH_TOKEN = "not-a-real-token"


def _cli_env(tmp_path, api, monkeypatch, **overrides) -> None:
    """Put the script's whole world in the environment, exactly as the operator
    would have it after sourcing the phone env file."""
    env = {
        "TWILIO_ACCOUNT_SID": "ACtest0000000000000000000000001",
        "TWILIO_AUTH_TOKEN": AUTH_TOKEN,
        "PUBLIC_BASE": "https://ai.business-builder.online/phone",
        "BUSINESS_CONFIG": str(_numbers_config(tmp_path)),
        "TWILIO_API_BASE": api.base_url,
        # a path that does not exist: nothing may be read out of the developer's
        # own phone configuration
        "ATLAS_PHONE_ENV": str(tmp_path / "no-such-env-file"),
    }
    env.update(overrides)
    for key in list(env) + ["TWILIO_PHONE"]:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        if value is not None:
            monkeypatch.setenv(key, value)


@asynccontextmanager
async def fake_twilio():
    api = FakeTwilioApi()
    await api.start()
    try:
        yield api
    finally:
        await api.stop()


async def _run(tc, argv, capsys) -> tuple[int, str, str]:
    code = await tc.run(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


async def test_show_prints_current_and_intended_and_changes_nothing(
        tmp_path, monkeypatch, capsys):
    tc = twilio_config_module()
    async with fake_twilio() as api:
        _cli_env(tmp_path, api, monkeypatch)
        code, out, err = await _run(tc, ["--show"], capsys)

    assert code == 0, err
    assert "+15088863046" in out
    assert "https://demo.twilio.com/welcome/sms/reply" in out            # current
    assert "https://ai.business-builder.online/phone/sms/incoming" in out  # intended
    assert "voice_fallback_url" in out
    assert api.updates == []
    assert AUTH_TOKEN not in out + err


async def test_apply_writes_only_the_fields_that_differ(tmp_path, monkeypatch, capsys):
    tc = twilio_config_module()
    async with fake_twilio() as api:
        _cli_env(tmp_path, api, monkeypatch)
        code, out, err = await _run(tc, ["--apply", "--out", str(tmp_path / "r")],
                                    capsys)

    assert code == 0, err
    assert len(api.updates) == 1
    form = api.updates[0]["form"]
    # voice_url already matches, so it is not written
    assert set(form) == {"VoiceFallbackUrl", "StatusCallback", "SmsUrl"}
    assert form["SmsUrl"] == "https://ai.business-builder.online/phone/sms/incoming"
    assert form["VoiceFallbackUrl"] == (
        "https://ai.business-builder.online/phone/fallback.xml")
    assert api.auth_seen and all(a.startswith("Basic ") for a in api.auth_seen)
    assert AUTH_TOKEN not in out + err


async def test_apply_with_nothing_to_change_writes_nothing(
        tmp_path, monkeypatch, capsys):
    tc = twilio_config_module()
    async with fake_twilio() as api:
        api.numbers[0].update(
            voice_fallback_url="https://ai.business-builder.online/phone/fallback.xml",
            status_callback="https://ai.business-builder.online/phone/voice/status",
            sms_url="https://ai.business-builder.online/phone/sms/incoming")
        _cli_env(tmp_path, api, monkeypatch)
        code, out, err = await _run(tc, ["--apply", "--out", str(tmp_path / "r")],
                                    capsys)

    assert code == 0, err
    assert api.updates == []
    assert "already" in out.lower()


async def test_a_number_twilio_does_not_have_is_loud(tmp_path, monkeypatch, capsys):
    tc = twilio_config_module()
    async with fake_twilio() as api:
        api.numbers[0]["phone_number"] = "+15085550000"
        _cli_env(tmp_path, api, monkeypatch)
        code, _out, err = await _run(tc, ["--show"], capsys)

    assert code != 0
    assert "+15088863046" in err
    assert "not on this Twilio account" in err


async def test_an_api_error_stops_the_script(tmp_path, monkeypatch, capsys):
    """A 401 from Twilio must never read as "nothing to change"."""
    tc = twilio_config_module()
    async with fake_twilio() as api:
        api.list_status = 401
        _cli_env(tmp_path, api, monkeypatch)
        code, _out, err = await _run(tc, ["--show"], capsys)

    assert code != 0
    assert "401" in err
    assert AUTH_TOKEN not in err


async def test_the_script_refuses_without_a_public_base(tmp_path, monkeypatch, capsys):
    tc = twilio_config_module()
    async with fake_twilio() as api:
        _cli_env(tmp_path, api, monkeypatch, PUBLIC_BASE=None)
        code, _out, err = await _run(tc, ["--show"], capsys)

    assert code != 0 and "PUBLIC_BASE" in err
    assert api.auth_seen == []


@pytest.mark.parametrize("missing", ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"])
async def test_the_script_refuses_without_twilio_credentials(
        tmp_path, monkeypatch, capsys, missing):
    tc = twilio_config_module()
    async with fake_twilio() as api:
        _cli_env(tmp_path, api, monkeypatch, **{missing: None})
        code, _out, err = await _run(tc, ["--show"], capsys)

    assert code != 0 and missing in err
    assert api.auth_seen == []


async def test_render_writes_the_files_without_touching_twilio(
        tmp_path, monkeypatch, capsys):
    tc = twilio_config_module()
    out_dir = tmp_path / "rendered"
    async with fake_twilio() as api:
        _cli_env(tmp_path, api, monkeypatch)
        code, _out, err = await _run(tc, ["--render", "--out", str(out_dir)], capsys)

    assert code == 0, err
    assert (out_dir / "fallback-15088863046.xml").exists()
    assert api.auth_seen == []


async def test_the_script_reads_the_phone_env_file_when_the_shell_has_nothing(
        tmp_path, monkeypatch, capsys):
    """The operator runs this by hand; the credentials live in the same env
    file systemd hands the bridge."""
    env_file = tmp_path / "env"
    env_file.write_text(
        "# the phone line's settings\n"
        f"TWILIO_ACCOUNT_SID=ACtest0000000000000000000000001\n"
        f"TWILIO_AUTH_TOKEN={AUTH_TOKEN}\n"
        'PUBLIC_BASE="https://ai.business-builder.online/phone"\n',
        encoding="utf-8")
    tc = twilio_config_module()
    async with fake_twilio() as api:
        _cli_env(tmp_path, api, monkeypatch, TWILIO_ACCOUNT_SID=None,
                 TWILIO_AUTH_TOKEN=None, PUBLIC_BASE=None,
                 ATLAS_PHONE_ENV=str(env_file))
        code, out, err = await _run(tc, ["--show"], capsys)

    assert code == 0, err
    assert "+15088863046" in out
    assert AUTH_TOKEN not in out + err


async def test_no_flag_at_all_does_nothing_and_says_how(tmp_path, monkeypatch, capsys):
    tc = twilio_config_module()
    async with fake_twilio() as api:
        _cli_env(tmp_path, api, monkeypatch)
        code, _out, err = await _run(tc, [], capsys)

    assert code == 2
    assert "--show" in err and "--apply" in err
    assert api.updates == [] and api.auth_seen == []


def test_the_script_runs_as_a_command(tmp_path):
    """It is a CLI the operator types, not only a module tests import."""
    done = subprocess.run([sys.executable, str(TWILIO_CONFIG), "--help"],
                          capture_output=True, text=True, timeout=60,
                          cwd=str(tmp_path))
    assert done.returncode == 0, done.stderr
    assert "--show" in done.stdout and "--apply" in done.stdout


# ============================================ the routes are actually served ==

def test_every_new_route_is_registered(tmp_path, monkeypatch):
    """The handlers above are only reachable because _serve() mounts them —
    a route tested through a test-only app and never mounted is a route that
    does not exist."""
    svc = _import_service(tmp_path, monkeypatch)
    source = Path(svc.__file__).read_text(encoding="utf-8")
    for line in ('add_post("/voice/status", voice_status)',
                 'add_post("/sms/incoming", sms_incoming)',
                 'add_post("/voice/whisper", voice_whisper)',
                 'add_get("/voice/whisper", voice_whisper)'):
        assert line in source, line

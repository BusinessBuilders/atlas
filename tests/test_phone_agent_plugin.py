# tests/test_phone_agent_plugin.py — the shipped phone_agent plugin:
# loader acceptance, and the phone_line_status handler against a real local
# HTTP server (up / degraded / down / non-loopback refusal).
import asyncio
from pathlib import Path
from types import SimpleNamespace

from plugin_loader import load_plugins, plugin_load_errors

PLUGINS_DIR = Path(__file__).resolve().parents[1] / "plugins"


def _load_handler():
    loaded = load_plugins(reserved_names=set(), plugins_dir=str(PLUGINS_DIR))
    assert plugin_load_errors() == []
    by_name = {p.name: p for p in loaded}
    assert "phone_line_status" in by_name
    tool = by_name["phone_line_status"]
    assert tool.risk == "low"
    assert tool.requires_confirmation is False
    return tool.handler


def _call(handler, monkeypatch, health_url):
    monkeypatch.setenv("ATLAS_PHONE_HEALTH_URL", health_url)
    captured = {}

    async def capture(result):
        captured.update(result)

    asyncio.run(handler(SimpleNamespace(arguments={}, result_callback=capture)))
    return captured


def _serve_health(payload: dict, status: int = 200):
    """Tiny one-shot health server on an ephemeral loopback port."""
    from aiohttp import web

    async def run(started: asyncio.Event, stop: asyncio.Event, port_box: list):
        async def health(_):
            return web.json_response(payload, status=status)

        app = web.Application()
        app.router.add_get("/health", health)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port_box.append(runner.addresses[0][1])
        started.set()
        await stop.wait()
        await runner.cleanup()

    return run


def _with_server(handler, monkeypatch, payload, status=200):
    async def go():
        started, stop, port_box = asyncio.Event(), asyncio.Event(), []
        server = asyncio.create_task(_serve_health(payload, status)(started, stop, port_box))
        await started.wait()
        captured = {}

        async def capture(result):
            captured.update(result)

        monkeypatch.setenv(
            "ATLAS_PHONE_HEALTH_URL", f"http://127.0.0.1:{port_box[0]}/health"
        )
        await handler(SimpleNamespace(arguments={}, result_callback=capture))
        stop.set()
        await server
        return captured

    return asyncio.run(go())


def test_loader_accepts_phone_agent():
    _load_handler()


def test_line_up(monkeypatch):
    handler = _load_handler()
    result = _with_server(
        handler, monkeypatch,
        {"bridge": "ok", "model_backend": "ok", "model": "m",
         "profiles": ["a"], "numbers": 1},
    )
    assert result["ok"] is True
    assert result["line"] == "up"
    assert result["profiles"] == ["a"]


def test_line_degraded_when_model_backend_unreachable(monkeypatch):
    handler = _load_handler()
    result = _with_server(
        handler, monkeypatch,
        {"bridge": "ok", "model_backend": "UNREACHABLE", "model": "m",
         "profiles": ["a"], "numbers": 1},
        status=503,
    )
    assert result["ok"] is True
    assert result["line"].startswith("DEGRADED")


def test_bridge_down_fails_loud(monkeypatch):
    handler = _load_handler()
    # nothing listens on this port
    result = _call(handler, monkeypatch, "http://127.0.0.1:1/health")
    assert result["ok"] is False
    assert "DOWN" in result["error"]
    assert "atlas-phone-bridge" in result["error"]


def test_non_loopback_refused(monkeypatch):
    handler = _load_handler()
    result = _call(handler, monkeypatch, "http://10.0.0.5:8890/health")
    assert result["ok"] is False
    assert "loopback" in result["error"]


def test_service_config_validation_is_fail_closed(tmp_path):
    """service.py must refuse a businesses.toml whose number maps to a missing
    profile: importing the module with that config must exit 1 with the reason
    on stderr (the fail-closed boot contract)."""
    import os
    import subprocess
    import sys

    bad = tmp_path / "businesses.toml"
    bad.write_text(
        '[numbers]\n"+15550001111" = "ghost"\n\n'
        "[profiles.real]\nbusiness_name = \"X\"\nservices = \"y\"\n"
        "owner_name = \"Z\"\ngreeting = \"hi\"\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.update(
        TWILIO_ACCOUNT_SID="ACtest", TWILIO_AUTH_TOKEN="t", BRIDGE_PORT="1",
        PUBLIC_BASE="https://example.test/phone", WS_TOKEN="w",
        OLLAMA_URL="http://127.0.0.1:1/v1", MODEL="m",
        BUSINESS_CONFIG=str(bad),
        # The boot opens a real call store before it reads the business
        # config; without this the subprocess would create one in the
        # developer's ~/.local/share/atlas-phone.
        PHONE_DATA_DIR=str(tmp_path / "phone-data"),
    )
    service = PLUGINS_DIR / "phone_agent" / "service.py"
    check = subprocess.run(
        [sys.executable, "-c",
         "import tomllib, sys, importlib.util\n"
         "spec = importlib.util.spec_from_file_location('svc', sys.argv[1])\n"
         "m = importlib.util.module_from_spec(spec)\n"
         "spec.loader.exec_module(m)\n",
         str(service)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert check.returncode == 1
    assert "not defined" in check.stderr


# ---- service module unit tests (persona sandbox + end-call scrubbing) ------

def _import_service(tmp_path, monkeypatch, extra_env=None, cfg_extra=""):
    """Import service.py in-process with a stub env and a valid config."""
    import importlib.util

    cfg = tmp_path / "businesses.toml"
    cfg.write_text(
        '[numbers]\n"+15550001111" = "acme"\n\n'
        "[profiles.acme]\nbusiness_name = \"Acme Co\"\nservices = \"widget repair\"\n"
        "owner_name = \"Jo\"\ngreeting = \"hi\"\n"
        "facts = \"Email: office@acme.test\\nHours: 9-5\"\n" + cfg_extra,
        encoding="utf-8",
    )
    # ADMIN_TOKEN too: it is the legacy dashboard login, and one left in the
    # developer's environment would give every test an implicit owner.
    for k in ("NTFY_URL", "NTFY_TOPIC", "MESSAGES_FILE", "ADMIN_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    stub = dict(
        TWILIO_ACCOUNT_SID="ACtest", TWILIO_AUTH_TOKEN="t", BRIDGE_PORT="1",
        PUBLIC_BASE="https://example.test/phone", WS_TOKEN="w",
        OLLAMA_URL="http://127.0.0.1:1/v1", MODEL="m", BUSINESS_CONFIG=str(cfg),
        **(extra_env or {}),
    )
    # Every import opens a real call store. It goes under tmp_path, never in
    # the developer's ~/.local/share/atlas-phone — unless a test names its own.
    stub.setdefault("PHONE_DATA_DIR", str(tmp_path / "phone-data"))
    for k, v in stub.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location(
        "phone_agent_service_under_test",
        PLUGINS_DIR / "phone_agent" / "service.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_persona_is_self_contained(tmp_path, monkeypatch):
    """The phone persona must be built ONLY from the profile — no resident
    Atlas import (a live call leaked the owner's nickname through it)."""
    svc = _import_service(tmp_path, monkeypatch)
    prompt = svc.SYSTEM_PROMPTS["acme"]
    assert "Acme Co" in prompt
    assert "widget repair" in prompt
    assert "Jo" in prompt
    assert "office@acme.test" in prompt          # facts made it in
    assert svc.END_CALL_MARKER in prompt          # hangup instruction present
    assert "NO tools" in prompt
    # nothing outside the profile: no persona import machinery exists at all
    assert not hasattr(svc, "load_atlas_persona")


def test_scrubber_marker_split_across_tokens(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    scrubber = svc.MarkerScrubber()
    spoken = ""
    for token in ["Goodbye, have a great day! ", "[EN", "D CA", "LL]"]:
        spoken += scrubber.feed(token)
    spoken += scrubber.flush()
    assert svc.END_CALL_MARKER not in spoken
    assert "[" not in spoken
    assert spoken.strip() == "Goodbye, have a great day!"
    assert scrubber.found == {"end"}


def test_scrubber_plain_text_passes_through(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    scrubber = svc.MarkerScrubber()
    spoken = ""
    for token in ["We build ", "websites [really ", "nice ones] daily."]:
        spoken += scrubber.feed(token)
    spoken += scrubber.flush()
    assert spoken == "We build websites [really nice ones] daily."
    assert scrubber.found == set()


def test_scrubber_text_after_marker_still_spoken(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    scrubber = svc.MarkerScrubber()
    spoken = scrubber.feed("Bye now! [END CALL] Take care.") + scrubber.flush()
    assert spoken == "Bye now!  Take care."
    assert scrubber.found == {"end"}


def test_scrubber_transfer_marker(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    scrubber = svc.MarkerScrubber()
    spoken = ""
    for token in ["Connecting you now. ", "[TRANSFER", " CALL]"]:
        spoken += scrubber.feed(token)
    spoken += scrubber.flush()
    assert spoken.strip() == "Connecting you now."
    assert scrubber.found == {"transfer"}


def test_gates_built_at_boot_and_hot_apply(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    assert "acme" in svc.GATES
    assert svc.GATES["acme"].transfer_available is False  # stub has no forward_to
    good = svc.emit_business_toml(
        {"+15550001111": "acme"},
        {"acme": {"business_name": "Acme Co", "services": "x", "owner_name": "Jo",
                  "greeting": "hi", "forward_to": "+15085550100",
                  "transfer_phrases": "front desk please"}},
    )
    assert svc.apply_config_text(good) == []
    assert svc.GATES["acme"].transfer_available is True
    joined = svc.normalize_speech("front desk please")
    assert any(p.search(joined) for p in svc.GATES["acme"].transfer_patterns)


def test_bad_phrase_config_refused(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    bad = svc.emit_business_toml(
        {"+15550001111": "acme"},
        {"acme": {"business_name": "A", "services": "x", "owner_name": "J",
                  "greeting": "hi", "transfer_phrases": "y" * 121}},
    )
    errors = svc.apply_config_text(bad)
    assert errors and "transfer_phrases" in errors[0]


def test_persona_transfer_and_honesty_rules(tmp_path, monkeypatch):
    svc = _import_service(
        tmp_path, monkeypatch, cfg_extra='forward_to = "+15085550100"\n'
    )
    prompt = svc.SYSTEM_PROMPTS["acme"]
    assert "operator" in prompt                       # explicit-ask instruction
    assert "is NOT a request" in prompt               # name-mention loophole closed
    assert "never state that an appointment" in prompt.lower() or \
        "never say an appointment" in prompt.lower()
    assert "did not give as their own" in prompt      # no invented names
    assert "never guess or extrapolate" in prompt     # D6 one-source-of-truth rule
    # the agent must know it's hearing STT text and that its own name gets
    # misheard ("hi Atlas" -> "Hey, Alice" on a real call)
    assert "speech recognition" in prompt
    assert "similar-sounding name" in prompt


def test_action_twiml(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    dial = svc.action_response_twiml("transfer", "+15085550100")
    assert "<Dial><Number>+15085550100</Number></Dial>" in dial
    assert "<Hangup/>" in dial  # no-answer fallback still ends the call
    assert svc.action_response_twiml("end", "+15085550100") == (
        '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'
    )
    # transfer requested but no forward number configured -> hang up, never 500
    assert "<Dial>" not in svc.action_response_twiml("transfer", "")


def test_transfer_section_only_with_forward_to(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    assert "TRANSFERRING" not in svc.SYSTEM_PROMPTS["acme"]

    svc2 = _import_service(
        tmp_path, monkeypatch, cfg_extra='forward_to = "+15085550100"\n'
    )
    assert "TRANSFERRING" in svc2.SYSTEM_PROMPTS["acme"]
    assert svc2.TRANSFER_MARKER in svc2.SYSTEM_PROMPTS["acme"]


def test_bad_forward_to_refused(tmp_path, monkeypatch):
    import pytest

    with pytest.raises(SystemExit):
        _import_service(tmp_path, monkeypatch, cfg_extra='forward_to = "call my cell"\n')


# ---- dashboard plumbing (emitter, hot-apply, admin app) --------------------

def test_emit_business_toml_roundtrips(tmp_path, monkeypatch):
    import tomllib

    svc = _import_service(tmp_path, monkeypatch)
    numbers = {"+15550001111": "acme"}
    profiles = {"acme": {
        "business_name": 'Acme "Co"', "services": "widget repair",
        "owner_name": "Jo", "greeting": "hi",
        "facts": "Email: office@acme.test\nHours: 9-5",
        "hand_added_key": "survives",
    }}
    text = svc.emit_business_toml(numbers, profiles)
    n2, p2 = svc.parse_business_config(tomllib.loads(text))
    assert n2 == numbers
    assert p2["acme"]["business_name"] == 'Acme "Co"'
    assert p2["acme"]["facts"] == "Email: office@acme.test\nHours: 9-5"
    assert p2["acme"]["hand_added_key"] == "survives"


def test_apply_config_text_is_fail_closed_and_hot(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    before_prompt = svc.SYSTEM_PROMPTS["acme"]

    errors = svc.apply_config_text("this is [ not toml")
    assert errors and "TOML" in errors[0]
    errors = svc.apply_config_text(
        '[numbers]\n"+15550001111" = "ghost"\n\n'
        '[profiles.real]\nbusiness_name = "X"\nservices = "y"\n'
        'owner_name = "Z"\ngreeting = "hi"\n'
    )
    assert errors and "not defined" in errors[0]
    assert svc.SYSTEM_PROMPTS["acme"] == before_prompt  # nothing changed

    good = svc.emit_business_toml(
        {"+15550001111": "acme"},
        {"acme": {"business_name": "Acme Co", "services": "widget repair",
                  "owner_name": "Jo", "greeting": "hello there"}},
    )
    assert svc.apply_config_text(good) == []
    assert svc.PROFILES["acme"]["greeting"] == "hello there"
    assert "hello there" not in before_prompt
    with open(svc.BUSINESS_CONFIG, encoding="utf-8") as f:
        assert 'greeting = "hello there"' in f.read()


def test_extra_instructions_added_to_prompt(tmp_path, monkeypatch):
    svc = _import_service(
        tmp_path, monkeypatch,
        cfg_extra='extra_instructions = "Mention the summer special."\n',
    )
    assert "Mention the summer special." in svc.SYSTEM_PROMPTS["acme"]
    assert "never override the HARD RULES" in svc.SYSTEM_PROMPTS["acme"]


# ---- call-control gates (spec 2026-07-26, rev 2) ---------------------------

def test_normalize_speech(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    # U+2019 apostrophe, casing, punctuation, whitespace
    assert svc.normalize_speech("That’s ALL, thanks!!") == "that's all thanks"
    assert svc.normalize_speech("  Hang   up.  ") == "hang up"
    assert svc.normalize_speech("") == ""


def test_parse_phrase_lines_caps_and_hygiene(tmp_path, monkeypatch):
    import pytest

    svc = _import_service(tmp_path, monkeypatch)
    # blank/whitespace lines dropped BEFORE the empty check; dedupe keeps order
    assert svc.parse_phrase_lines("operator\n\n   \nOperator\nreal person\n") == [
        "operator", "real person",
    ]
    assert svc.parse_phrase_lines("   \n\n") == []
    with pytest.raises(ValueError):
        svc.parse_phrase_lines("\n".join(f"phrase {i}" for i in range(65)))
    with pytest.raises(ValueError):
        svc.parse_phrase_lines("x" * 121)


def test_owner_token_short_name_rule(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    assert svc.owner_token("William Donovan") == "william"
    # first name under 3 chars -> full name is used (EDGE: syllable collisions)
    assert svc.owner_token("Jo Smith") == "jo smith"


def test_compile_phrases_escaping_and_owner_expansion(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    pats = svc.compile_phrases(["talk to {owner}", "price (usd)"], "William D")
    joined = svc.normalize_speech("can i talk to william about the price (usd)?")
    assert any(p.search(joined) for p in pats[:1])
    assert any(p.search(joined) for p in pats[1:])  # metachars escaped, not a crash
    # word boundaries: 'bye' phrase must not match 'buyer'
    pats2 = svc.compile_phrases(["bye now"], "W")
    assert not any(p.search(svc.normalize_speech("the buyer now wants two")) for p in pats2)


def test_bare_owner_phrase_rejected_loudly(tmp_path, monkeypatch):
    import pytest

    svc = _import_service(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        svc.parse_phrase_lines("operator\n{owner}\n")
    # case-variant placeholder is canonicalized, not silently degraded (BLIND-4)
    assert svc.parse_phrase_lines("speak to {OWNER}") == ["speak to {owner}"]
    assert svc.parse_phrase_lines("speak to { Owner }") == ["speak to {owner}"]


def test_transfer_hint_uses_profiles_own_phrase(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    default_gates = svc.build_call_gates(
        {"business_name": "A", "services": "x", "owner_name": "Jo Smith",
         "greeting": "hi", "forward_to": "+15085550100"}
    )
    assert default_gates.transfer_hint == "operator"
    custom = svc.build_call_gates(
        {"business_name": "A", "services": "x", "owner_name": "Jo Smith",
         "greeting": "hi", "forward_to": "+15085550100",
         "transfer_phrases": "front desk please\noperator"}
    )
    assert custom.transfer_hint == "front desk please"  # BLIND-2: never lie


def test_alias_mishearing_rewritten_at_source(tmp_path, monkeypatch):
    """'hi Atlas' arrives from STT as 'Hey, Alice' — the inbound text is
    rewritten to the assistant's real name so the model never sees the wrong
    one. A caller INTRODUCING themself as Alice is untouched."""
    svc = _import_service(tmp_path, monkeypatch)
    gates = svc.build_call_gates(
        {"business_name": "A", "services": "x", "owner_name": "Jo Smith",
         "greeting": "hi", "forward_to": "+15085550100"}
    )
    assert svc.resolve_alias_mishearing("Hey, Alice. How's it going?", gates) == \
        "Hey, Atlas. How's it going?"
    assert svc.resolve_alias_mishearing("Is at last there?", gates) == \
        "Is Atlas there?"
    # a real Alice keeps her name
    assert svc.resolve_alias_mishearing("Hi, my name is Alice Green.", gates) == \
        "Hi, my name is Alice Green."
    assert svc.resolve_alias_mishearing("This is Alice from the bakery.", gates) == \
        "This is Alice from the bakery."
    # untouched when no alias appears
    assert svc.resolve_alias_mishearing("I need a website quote.", gates) == \
        "I need a website quote."
    # custom assistant name gets no stock aliases; profile overrides do
    custom = svc.build_call_gates(
        {"business_name": "A", "services": "x", "owner_name": "Jo Smith",
         "greeting": "hi", "assistant_name": "Nova",
         "assistant_aliases": "nover\nnova scotia"}
    )
    assert svc.resolve_alias_mishearing("hi nover, you there?", custom) == \
        "hi Nova, you there?"
    assert svc.resolve_alias_mishearing("Hey, Alice.", custom) == "Hey, Alice."


def test_loose_marker_detection(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    assert svc.loose_marker_spoken("Goodbye! [ END CALL ]") is True
    assert svc.loose_marker_spoken("Goodbye! [end  call]") is True
    assert svc.loose_marker_spoken("Goodbye now, take care.") is False


def test_default_phrases_have_no_bare_owner_or_bare_transfer(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    assert "{owner}" not in svc.DEFAULT_TRANSFER_PHRASES  # only inside verb phrases
    assert all(p != "transfer" for p in svc.DEFAULT_TRANSFER_PHRASES)
    bare_owner = [p for p in svc.DEFAULT_TRANSFER_PHRASES if p.strip() == "{owner}"]
    assert bare_owner == []
    # every owner-referencing default is verb-framed (ARCH-1)
    for p in svc.DEFAULT_TRANSFER_PHRASES:
        if "{owner}" in p:
            assert any(v in p for v in ("speak", "talk", "get")), p


def test_scrubber_case_variant_marker_caught(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    scrubber = svc.MarkerScrubber()
    spoken = scrubber.feed("Goodbye now! [end call]") + scrubber.flush()
    assert "end call" not in spoken.lower()
    assert scrubber.found == {"end"}
    scrubber2 = svc.MarkerScrubber()
    spoken2 = scrubber2.feed("Bye! [End Call]") + scrubber2.flush()
    assert "[" not in spoken2
    assert scrubber2.found == {"end"}


def test_scrubber_truncated_marker_never_spoken(tmp_path, monkeypatch):
    """A stream cut mid-marker must not say '[END' to a customer."""
    svc = _import_service(tmp_path, monkeypatch)
    scrubber = svc.MarkerScrubber()
    spoken = scrubber.feed("Goodbye! [END CA")
    spoken += scrubber.flush()  # stream truncated here
    assert spoken.strip() == "Goodbye!"
    assert scrubber.found == set()


def test_overpromise_detector(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    hits = svc.detect_overpromise(
        "Got it, Alice! William will meet with you at 9 AM tomorrow — you're booked."
    )
    assert "booked" in hits
    assert svc.detect_overpromise("I've sent the estimate to your email.") != []
    # the persona's legitimate repeat-back flow must NOT trip the detector
    assert svc.detect_overpromise("Let me confirm your number: 555-0100?") == []
    assert svc.detect_overpromise("William will get back to you to confirm.") == []


def _gates(svc, forward=True, transfer_raw="", end_raw=""):
    profile = {
        "business_name": "Acme Co", "services": "x", "owner_name": "William D",
        "greeting": "hi",
    }
    if forward:
        profile["forward_to"] = "+15085550100"
    if transfer_raw:
        profile["transfer_phrases"] = transfer_raw
    if end_raw:
        profile["end_phrases"] = end_raw
    return svc.build_call_gates(profile)


def test_incident_replay_never_authorizes(tmp_path, monkeypatch):
    """The 2026-07-26 call: caller says the owner's name, model marks
    transfer. Must be blocked with no-caller-request."""
    svc = _import_service(tmp_path, monkeypatch)
    gates = _gates(svc)
    utts = [
        "I wanted to make an appointment with William.",
        "Yeah. It would be tomorrow at 9AM.",
        "Never told you my name. My name is William, actually.",
    ]
    action, reason = svc.decide_call_action(
        "Oh, hello William! Let me start again. I'll connect you now.",
        {"transfer"}, utts, gates,
    )
    assert action is None
    assert reason == "no-caller-request"


def test_operator_authorizes_transfer(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    gates = _gates(svc)
    action, reason = svc.decide_call_action(
        "Of course, connecting you now.", {"transfer"},
        ["Operator, please."], gates,
    )
    assert (action, reason) == ("transfer", "authorized")
    action, _ = svc.decide_call_action(
        "Connecting you now.", {"transfer"},
        ["Can I speak with William please"], gates,
    )
    assert action == "transfer"


def test_affirmation_flow_and_stale_consent(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    gates = _gates(svc)
    # operator -> (agent question) -> "yes" => authorized
    action, _ = svc.decide_call_action(
        "Connecting you now.", {"transfer"},
        ["I need the operator", "yes please"], gates,
    )
    assert action == "transfer"
    # stale consent: phrase 3 turns back but last utterance is NOT an affirmation
    action, reason = svc.decide_call_action(
        "Connecting you now.", {"transfer"},
        ["get me the operator", "actually about my invoice", "the total looks wrong"],
        gates,
    )
    assert action is None
    assert reason == "no-caller-request"
    # BLIND-1: a "yes" answering an UNRELATED question must not ride an
    # "operator" from two turns earlier — consent and confirmation adjacent only
    action, reason = svc.decide_call_action(
        "Connecting you now.", {"transfer"},
        ["operator", "what are your hours", "yes"], gates,
    )
    assert action is None
    assert reason == "no-caller-request"
    # AUDIT-1: "do it" is not in the spec's affirmation set
    action, _ = svc.decide_call_action(
        "Connecting you now.", {"transfer"}, ["operator", "do it"], gates,
    )
    assert action is None


def test_question_in_reply_blocks_everything(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    gates = _gates(svc)
    for q in ["Shall I connect you?", "Connecting now, okay？", "جاهز؟"]:
        action, reason = svc.decide_call_action(q, {"transfer"}, ["operator"], gates)
        assert action is None
        assert reason == "question-in-reply"


def test_end_gate_standalone_no_vs_sentence(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    gates = _gates(svc)
    action, _ = svc.decide_call_action("Goodbye!", {"end"}, ["No."], gates)
    assert action == "end"
    action, reason = svc.decide_call_action(
        "Goodbye!", {"end"}, ["no, actually can you also check hosting"], gates
    )
    assert action is None
    assert reason == "no-caller-request"
    action, _ = svc.decide_call_action(
        "Thanks for calling. Goodbye!", {"end"}, ["that's all, goodbye"], gates
    )
    assert action == "end"


def test_both_markers_each_own_gate(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    gates = _gates(svc)
    # only END is caller-authorized -> end wins even though transfer marked
    action, _ = svc.decide_call_action(
        "Goodbye!", {"end", "transfer"}, ["nothing else, goodbye"], gates
    )
    assert action == "end"
    # only TRANSFER authorized -> transfer
    action, _ = svc.decide_call_action(
        "Connecting you.", {"end", "transfer"}, ["operator"], gates
    )
    assert action == "transfer"


def test_transfer_unavailable_without_forward_to(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    gates = _gates(svc, forward=False)
    action, reason = svc.decide_call_action(
        "Connecting you now.", {"transfer"}, ["operator"], gates
    )
    assert action is None
    assert reason == "transfer-unavailable"


def test_no_marker_reason(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    gates = _gates(svc)
    assert svc.decide_call_action("Hello!", set(), ["operator"], gates) == (
        None, "no-marker",
    )


def test_admin_app_auth_and_save(tmp_path, monkeypatch):
    """The dashboard: no token -> login page; wrong token -> rejected; right
    token -> dashboard; a bad save is rejected and changes nothing."""
    import importlib.util

    import aiohttp
    from aiohttp import web

    svc = _import_service(tmp_path, monkeypatch)
    spec = importlib.util.spec_from_file_location(
        "phone_agent_admin_under_test", PLUGINS_DIR / "phone_agent" / "admin.py"
    )
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

    async def drive():
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = runner.addresses[0][1]
        base = f"http://127.0.0.1:{port}"
        results = {}
        async with aiohttp.ClientSession() as s:
            async with s.get(base + "/") as r:
                results["anon"] = await r.text()
            async with s.post(base + "/login", data={"token": "wrong"}) as r:
                results["bad_login"] = await r.text()
            async with s.post(base + "/login", data={"token": "sesame"},
                              allow_redirects=False) as r:
                results["login_status"] = r.status
                cookie = r.cookies.get(admin.COOKIE)
                assert cookie is not None
            s.cookie_jar.update_cookies({admin.COOKIE: "sesame"})
            async with s.get(base + "/") as r:
                results["dash"] = await r.text()
            async with s.post(base + "/save",
                              data={"numbers_text": "+15550001111 = ghost"}) as r:
                results["bad_save"] = await r.text()
        await runner.cleanup()
        return results

    results = asyncio.run(drive())
    assert "Admin token" in results["anon"]          # login gate
    assert "acme" not in results["anon"]             # nothing leaks pre-auth
    assert "Wrong token" in results["bad_login"]
    assert results["login_status"] == 303
    assert "profile: acme" in results["dash"]
    # phrase gates are dashboard-editable as MULTILINE fields (ARCH-8: a
    # single-line input would silently collapse the newline list on save)
    assert "name='acme::transfer_phrases'" in results["dash"]
    assert "name='acme::end_phrases'" in results["dash"]
    assert results["dash"].count("<textarea") >= 5  # facts, extra, 2 phrase fields, numbers
    assert "Not applied" in results["bad_save"]
    assert svc.NUMBERS == {"+15550001111": "acme"}   # unchanged by bad save


def test_message_entry_format(tmp_path, monkeypatch):
    svc = _import_service(tmp_path, monkeypatch)
    entry = svc.format_message_entry(
        when="2026-07-20 19:45 EDT", business_name="Acme Co",
        caller_id="+15550001234", note="Sam\n+15550001234\nneeds a widget fixed",
        call_sid="CAtest123", turns=3,
    )
    assert "+15550001234" in entry
    assert "Acme Co line" in entry
    assert "needs a widget fixed" in entry
    assert "CAtest123" in entry
    assert entry.startswith("\n## ")


def test_ntfy_half_config_refused(tmp_path, monkeypatch):
    """NTFY_URL without NTFY_TOPIC (or vice versa) must refuse to boot —
    a half-configured push channel is a silent-drop waiting to happen."""
    import pytest

    with pytest.raises(SystemExit):
        _import_service(tmp_path, monkeypatch, extra_env={"NTFY_URL": "http://127.0.0.1:1"})

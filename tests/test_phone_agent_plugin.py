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
    for k in ("NTFY_URL", "NTFY_TOPIC", "MESSAGES_FILE"):
        monkeypatch.delenv(k, raising=False)
    stub = dict(
        TWILIO_ACCOUNT_SID="ACtest", TWILIO_AUTH_TOKEN="t", BRIDGE_PORT="1",
        PUBLIC_BASE="https://example.test/phone", WS_TOKEN="w",
        OLLAMA_URL="http://127.0.0.1:1/v1", MODEL="m", BUSINESS_CONFIG=str(cfg),
        **(extra_env or {}),
    )
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


def test_honor_markers_blocks_questions(tmp_path, monkeypatch):
    """The 2026-07-22 bug: the model glued [END CALL] to an intake question
    ('what time works best for you?') and hung up mid-call. The bridge, not
    the model, has the last word."""
    svc = _import_service(tmp_path, monkeypatch)
    assert svc.honor_markers("What time works best for you?", {"end"}) == "blocked"
    assert svc.honor_markers('May I have your name?"', {"transfer"}) == "blocked"
    assert svc.honor_markers("Goodbye, have a great day!", {"end"}) == "end"
    assert svc.honor_markers("Connecting you now.", {"transfer"}) == "transfer"
    assert svc.honor_markers("Connecting you now.", {"transfer", "end"}) == "transfer"
    assert svc.honor_markers("Anything else?", set()) is None


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
        get_prompts=lambda: svc.SYSTEM_PROMPTS,
        apply_config_text=svc.apply_config_text,
        emit_business_toml=svc.emit_business_toml,
        messages_file=str(tmp_path / "messages.md"),
        known_keys=svc._PROFILE_KNOWN_KEYS,
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

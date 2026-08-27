# tests/test_phone_agent_brains.py — the phone agent's BRAINS feature:
# named model backends ([brains.*] + active_brain in businesses.toml) that the
# owner switches on the dashboard. This shipped on the deployed bridge with no
# tests at all; these are the tests it never had. Everything here is
# fail-closed by design — a brain whose key env var is unset, or whose
# extra_body is not a JSON object, must stop the config being accepted rather
# than let a call reach the wrong backend (or no backend) at 2am.
import pytest
from test_phone_agent_plugin import _import_service

BRAINS_TOML = '''
active_brain = "cloud"
[numbers]
"+15550000001" = "acme"
[brains.local]
label = "Local"
base_url = "http://127.0.0.1:11434/v1"
model = "qwen2.5:7b-instruct"
[brains.cloud]
label = "Cloud"
base_url = "https://example.invalid/v1"
model = "big-model"
api_key_env = "TEST_BRAIN_KEY"
extra_body = "{\\"thinking\\": {\\"type\\": \\"disabled\\"}}"
[profiles.acme]
business_name = "Acme"
services = "widgets"
owner_name = "Pat"
greeting = "Thanks for calling Acme."
'''


@pytest.fixture
def svc(tmp_path, monkeypatch):
    """The service module imported in-process against a stub env (the same
    helper the rest of the phone-agent suite uses)."""
    return _import_service(tmp_path, monkeypatch)


def test_brains_parse_and_active(svc, monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_BRAIN_KEY", "k")
    config = svc.load_business_config(_write(tmp_path, BRAINS_TOML))
    assert config.active_brain == "cloud"
    assert set(config.brains) == {"local", "cloud"}
    assert config.brains["cloud"].extra_body == {"thinking": {"type": "disabled"}}
    assert config.brains["local"].base_url == "http://127.0.0.1:11434/v1"


def test_active_brain_must_exist(svc, monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_BRAIN_KEY", "k")
    with pytest.raises(ValueError, match="active_brain"):
        svc.load_business_config(_write(tmp_path, BRAINS_TOML.replace('active_brain = "cloud"', 'active_brain = "nope"')))


def test_api_key_env_must_be_set(svc, monkeypatch, tmp_path):
    monkeypatch.delenv("TEST_BRAIN_KEY", raising=False)
    with pytest.raises(ValueError, match="TEST_BRAIN_KEY"):
        svc.load_business_config(_write(tmp_path, BRAINS_TOML))


def test_extra_body_must_be_object(svc, monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_BRAIN_KEY", "k")
    bad = BRAINS_TOML.replace('extra_body = "{\\"thinking\\": {\\"type\\": \\"disabled\\"}}"', 'extra_body = "[1,2]"')
    with pytest.raises(ValueError, match="extra_body"):
        svc.load_business_config(_write(tmp_path, bad))


def test_request_args_never_override_call_keys(svc, monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_BRAIN_KEY", "k")
    brains = svc.load_business_config(_write(tmp_path, BRAINS_TOML)).brains
    brains["cloud"].extra_body = {"model": "evil", "stream": False, "thinking": {"type": "disabled"}}
    url, headers, body = svc.brain_request_args(brains["cloud"], {"model": "big-model", "messages": [], "stream": True})
    assert url.endswith("/chat/completions") and headers["Authorization"] == "Bearer k"
    assert body["model"] == "big-model" and body["stream"] is True and body["thinking"] == {"type": "disabled"}


def test_emit_round_trips_brains(svc, monkeypatch, tmp_path):
    """Every brain survives a dashboard save — including the ones that are not
    the active one. Dropping `local` on the way through would strand the owner
    on the cloud brain with no way back."""
    monkeypatch.setenv("TEST_BRAIN_KEY", "k")
    config = svc.load_business_config(_write(tmp_path, BRAINS_TOML))
    text = svc.emit_business_toml(config.numbers, config.profiles, config.brains,
                                  config.active_brain, config.branding, config.owners)
    again = svc.load_business_config(_write(tmp_path, text, name="rt.toml"))
    assert again.active_brain == config.active_brain
    assert set(again.brains) == {"local", "cloud"}
    assert again.brains["cloud"].api_key_env == "TEST_BRAIN_KEY"
    assert again.brains["cloud"].extra_body == config.brains["cloud"].extra_body
    assert again.brains["local"] == config.brains["local"]


def _write(tmp_path, text, name="b.toml"):
    p = tmp_path / name; p.write_text(text); return str(p)

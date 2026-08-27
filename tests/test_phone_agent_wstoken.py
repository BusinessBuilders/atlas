# tests/test_phone_agent_wstoken.py — per-call websocket tokens (audit H-8).
# The relay URL used to carry one static, never-rotating WS_TOKEN through
# nginx's access log; anyone who read that log once could open relay sessions
# forever. These are the tests for the replacement: a short-lived HMAC bound to
# ONE CallSid. Pure functions — no network, no state, no clock of their own.
import importlib.util
from pathlib import Path

import pytest

WSTOKEN_PATH = Path(__file__).resolve().parents[1] / "plugins" / "phone_agent" / "wstoken.py"
SECRET = b"test-secret"
OTHER_SECRET = b"test-secret-2"


@pytest.fixture(scope="module")
def wstoken():
    spec = importlib.util.spec_from_file_location("phone_agent_wstoken_under_test", WSTOKEN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mint_verify_round_trip(wstoken):
    token = wstoken.mint(SECRET, "CAabc123", now=1000.0)
    assert wstoken.verify(SECRET, token, "CAabc123", now=1000.0) is True
    assert wstoken.verify(SECRET, token, "CAabc123", now=1119.0) is True  # inside the 120s ttl


def test_token_wire_format_is_exp_dot_hmac(wstoken):
    token = wstoken.mint(SECRET, "CAabc123", now=1000.0, ttl_s=60)
    exp, _, sig = token.partition(".")
    assert exp == "1060"
    assert len(sig) == 64 and all(c in "0123456789abcdef" for c in sig)
    # the token carries no caller/business detail — only an expiry and a digest
    assert "CAabc123" not in token


def test_expired_token_rejected(wstoken):
    token = wstoken.mint(SECRET, "CAabc123", now=1000.0, ttl_s=120)
    assert wstoken.verify(SECRET, token, "CAabc123", now=1120.0) is True   # exactly at expiry
    assert wstoken.verify(SECRET, token, "CAabc123", now=1120.5) is False  # one tick past


def test_tampered_token_rejected(wstoken):
    token = wstoken.mint(SECRET, "CAabc123", now=1000.0)
    exp, _, sig = token.partition(".")
    flipped = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    assert wstoken.verify(SECRET, f"{exp}.{flipped}", "CAabc123", now=1000.0) is False
    # extending the expiry does not re-sign it
    assert wstoken.verify(SECRET, f"{int(exp) + 9999}.{sig}", "CAabc123", now=1000.0) is False
    # a different server secret never validates
    assert wstoken.verify(OTHER_SECRET, token, "CAabc123", now=1000.0) is False


def test_wrong_call_sid_rejected(wstoken):
    """The whole point: a token stolen from one call cannot open another."""
    token = wstoken.mint(SECRET, "CAabc123", now=1000.0)
    assert wstoken.verify(SECRET, token, "CAdifferent", now=1000.0) is False
    assert wstoken.verify(SECRET, token, "", now=1000.0) is False


def test_malformed_tokens_rejected_without_raising(wstoken):
    for bad in ["", ".", "notanumber.abc", "1000", "1000.", ".abc", "1e9.abc", "  ", "1000.abc.def"]:
        assert wstoken.verify(SECRET, bad, "CAabc123", now=1000.0) is False


def test_expiry_of_reads_the_expiry_for_pruning(wstoken):
    token = wstoken.mint(SECRET, "CAabc123", now=1000.0, ttl_s=45)
    assert wstoken.expiry_of(token) == 1045
    for bad in ["", "nope.abc", "1000"]:
        assert wstoken.expiry_of(bad) == 0

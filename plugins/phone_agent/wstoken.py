"""Per-call websocket tokens for the phone bridge (audit H-8).

The relay URL Twilio opens used to carry ONE static secret (`WS_TOKEN`) that
never rotated. That URL crosses nginx on the public VPS, whose access log
records the full request URI by default — so a single log read handed anyone a
key to the relay, for every call, forever.

A token here is bound to one CallSid and one short window:

    token = "<exp>.<hmac_sha256_hex(secret, '<call_sid>.<exp>')>"

`voice_incoming` mints one into the TwiML it hands Twilio; `voice_relay`
verifies it against the CallSid before the websocket is accepted, and again
against the CallSid in the `setup` event. A leaked token is useless: it is
bound to a call that is already over, and the bridge consumes it once.

Pure functions on purpose — no clock, no network, no state. The caller passes
`now`, so expiry is testable without sleeping and the whole module is
side-effect free.
"""

import hashlib
import hmac

DEFAULT_TTL_SECONDS = 120


def _signature(secret: bytes, call_sid: str, exp: int) -> str:
    return hmac.new(secret, f"{call_sid}.{exp}".encode(), hashlib.sha256).hexdigest()


def mint(secret: bytes, call_sid: str, now: float, ttl_s: int = DEFAULT_TTL_SECONDS) -> str:
    """A token authorizing exactly one relay session for `call_sid`.

    The default TTL is deliberately short: Twilio opens the websocket
    immediately after fetching the TwiML, so two minutes is generous.
    """
    exp = int(now) + int(ttl_s)
    return f"{exp}.{_signature(secret, str(call_sid), exp)}"


def verify(secret: bytes, token: str, call_sid: str, now: float) -> bool:
    """True only for an unexpired token this secret minted for THIS call_sid.

    Never raises: a malformed token from a stranger is simply not valid. The
    digest comparison is constant-time (hmac.compare_digest).
    """
    exp_text, dot, signature = str(token).partition(".")
    if not dot or not signature or not call_sid:
        return False
    if not exp_text.isdigit():
        return False
    exp = int(exp_text)
    if now > exp:
        return False
    return hmac.compare_digest(_signature(secret, str(call_sid), exp), signature)


def expiry_of(token: str) -> int:
    """The token's expiry as a unix timestamp, or 0 if it has none.

    Used only to prune the bridge's consumed-token set — it reads the
    unauthenticated prefix, so it must never be used to decide validity.
    """
    exp_text, dot, _ = str(token).partition(".")
    if not dot or not exp_text.isdigit():
        return 0
    return int(exp_text)

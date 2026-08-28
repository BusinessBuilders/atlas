"""Who is at the owner dashboard, and which businesses they may see.

Three jobs, all of them security-critical:

  * **Sessions.** The cookie carries a random session id, never the owner's
    access code. The id is a row in the store's `sessions` table, so signing
    out really ends the session on the server — the old dashboard put the
    shared secret itself in the cookie, which meant "sign out" could only ever
    be advice.
  * **CSRF.** Every mutating form carries a token derived from the session id
    with a per-process secret, and the `Origin` header must match the host the
    request arrived on. `SameSite=Strict` alone is a browser promise, not a
    check we make.
  * **Lockout.** Five wrong codes from one address inside fifteen minutes and
    that address waits a minute; twenty from anywhere at all in the same
    fifteen minutes and the form closes for a minute for everybody, because a
    per-address limit on its own is only a speed limit per address. Every
    failure is logged with its source and written to `events`, because
    "somebody is guessing at my dashboard" is a thing the owner has to be able
    to find out afterwards.

Tenancy lives here too: a `Session` carries the profile keys its owner is
allowed to read, and every store read in the dashboard is given that list.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from aiohttp import web

log = logging.getLogger("atlas-phone")

COOKIE = "phone_session"
# 14 days, slid forward every time the owner uses the dashboard.
SESSION_MAX_AGE = 1209600
FAILURE_WINDOW_SECONDS = 900          # 15 minutes
FAILURES_BEFORE_LOCK = 5
LOCK_SECONDS = 60
# The same window, counted across every address at once. One owner mistypes
# their code a few times a month; twenty wrong codes from anywhere inside
# fifteen minutes is somebody working through a list.
GLOBAL_FAILURES_BEFORE_LOCK = 20
GLOBAL_LOCK_SECONDS = 60
# The wildcard an owner's `profiles` list uses to mean "every business".
ALL_PROFILES = "*"
SIGN_IN_PATH = "/sign-in"
# The pre-owners login: one shared access code in the environment, with the
# run of the whole line. `service.LEGACY_OWNER_KEY` gives it this key, which is
# a name for a settings file and not a thing to print at a customer — every
# other owner key was typed by whoever set the line up, so it is a name a human
# chose and is shown as it is. A test pins the two spellings together.
LEGACY_OWNER_KEY = "_admin"
LEGACY_OWNER_NAME = "Line owner"


def owner_name(key: str) -> str:
    """The words for one login, as the person reading the dashboard sees them."""
    return LEGACY_OWNER_NAME if str(key) == LEGACY_OWNER_KEY else str(key)


def _is_loopback(address: str) -> bool:
    """True when this peer is this machine — i.e. the local reverse proxy.

    Anything unparseable is NOT loopback: a name we cannot resolve to an
    address must never buy the trust that lets a header speak for the peer.
    """
    text = str(address or "").strip().strip("[]")
    if not text:
        return False
    if text == "localhost":
        return True
    try:
        return ipaddress.ip_address(text.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class Session:
    """One signed-in owner, and the businesses they may read.

    `profile_keys` is already resolved against the live config: an owner of the
    whole line gets today's profiles, not the ones that existed when they
    signed in. `sees_whole_line` is what gates the controls that are not
    per-business — the model that answers every call, and the events that
    belong to no business at all.
    """
    id: str
    owner_key: str
    profile_keys: tuple
    sees_whole_line: bool


class Auth:
    def __init__(self, *, store, get_owners, get_state) -> None:
        self.store = store
        self._get_owners = get_owners
        self._get_state = get_state
        # Per process: a restart invalidates the tokens on any page still open,
        # which shows the owner "this page is out of date — reload" instead of
        # silently accepting a form built before the restart.
        self._csrf_secret = secrets.token_bytes(32)
        self._failures: dict[str, list] = {}
        self._locked_until: dict[str, float] = {}
        # Every failure, whatever address it came from, and when the form was
        # last closed to everybody because of them.
        self._global_failures: list = []
        self._global_locked_until = 0.0

    # ------------------------------------------------------------ owners --

    def _owner_token(self, owner) -> str:
        """The access code for one owner, read from the environment by NAME.

        The token never appears in businesses.toml — the config only names the
        variable — so this is the one place the secret is touched, and it is
        never logged, rendered or stored.
        """
        return os.environ.get(owner.token_env, "").strip()

    def owner_for_code(self, code: str):
        """The owner whose access code this is, or None.

        Every owner is compared even after a match so the time this takes says
        nothing about which login exists.
        """
        code = str(code or "")
        found = None
        for owner in self._get_owners().values():
            expected = self._owner_token(owner)
            if not expected:
                # parse_owners_config refuses an owner whose env var is unset,
                # so this only happens if the variable was emptied after boot.
                log.warning("dashboard owner %r has no access code set in the "
                            "environment (%s) — nobody can sign in as them",
                            owner.key, owner.token_env)
                continue
            if hmac.compare_digest(code, expected) and found is None:
                found = owner
        return found

    def profiles_for(self, owner) -> tuple:
        """The businesses this owner may read, resolved against the live config."""
        _, profiles = self._get_state()
        if ALL_PROFILES in owner.profiles:
            return tuple(sorted(profiles))
        return tuple(sorted(k for k in owner.profiles if k in profiles))

    def sees_whole_line(self, owner) -> bool:
        return ALL_PROFILES in owner.profiles

    # ---------------------------------------------------------- sessions --

    def start_session(self, owner) -> str:
        return self.store.create_session(owner.key)

    def session_for(self, request: web.Request):
        """The signed-in owner behind this request, or None.

        Expiry is measured from LAST USE, not from sign-in: the cookie's
        Max-Age is renewed on every request, so the session and the cookie
        agree on when fourteen idle days are up.
        """
        session_id = request.cookies.get(COOKIE, "")
        if not session_id:
            return None
        row = self.store.get_session(session_id)
        if row is None:
            return None
        if time.time() - float(row["last_seen"]) > SESSION_MAX_AGE:
            self.store.delete_session(session_id)
            return None
        owner = self._get_owners().get(row["owner_key"])
        if owner is None:
            # The login was removed from the config while they were signed in.
            self.store.delete_session(session_id)
            log.warning("dashboard session for owner %r ended: that login no "
                        "longer exists in businesses.toml", row["owner_key"])
            return None
        self.store.touch_session(session_id)
        return Session(id=session_id, owner_key=owner.key,
                       profile_keys=self.profiles_for(owner),
                       sees_whole_line=self.sees_whole_line(owner))

    def require(self, request: web.Request) -> Session:
        """The session, or a redirect to the sign-in page."""
        session = self.session_for(request)
        if session is None:
            raise web.HTTPFound(SIGN_IN_PATH)
        return session

    def set_cookie(self, response: web.StreamResponse, session_id: str) -> None:
        response.set_cookie(COOKIE, session_id, max_age=SESSION_MAX_AGE,
                            httponly=True, secure=True, samesite="Strict",
                            path="/")

    def clear_cookie(self, response: web.StreamResponse) -> None:
        response.del_cookie(COOKIE, path="/")

    # -------------------------------------------------------------- csrf --

    def csrf_token(self, session: Session) -> str:
        return hmac.new(self._csrf_secret, session.id.encode(),
                        hashlib.sha256).hexdigest()

    def check_csrf(self, request: web.Request, session: Session, form) -> str:
        """"" when this mutating request may proceed, else the reason it may not.

        The reason is shown to the owner — a form that silently does nothing is
        the failure mode this whole pass exists to remove.

        `Origin: null` is treated as "no origin information", NOT as a foreign
        site: browsers send exactly that for a form posted from a page served
        with `Referrer-Policy: no-referrer`, which is every page this dashboard
        serves. Refusing it would refuse every real form. The per-session token
        below is the check that actually stops a forged post; the origin
        comparison is the second lock, and it still catches a post from a named
        site that is not this one.
        """
        origin = request.headers.get("Origin", "").strip()
        host = urlsplit(origin).netloc if origin else ""
        if host and host != request.host:
            log.warning("dashboard refused a %s from another site "
                        "(Origin %s, host %s)", request.path, origin,
                        request.host)
            return ("That request came from another website, so it was not "
                    "carried out.")
        if not hmac.compare_digest(str(form.get("csrf", "")),
                                   self.csrf_token(session)):
            return ("This page was out of date, so nothing was changed. Reload "
                    "and try again.")
        return ""

    # ----------------------------------------------------------- lockout --

    def client_ip(self, request: web.Request) -> str:
        """Where a sign-in attempt came from — the part the client cannot pick.

        Two rules, and both of them are the lockout's whole worth:

        **Believe `X-Forwarded-For` only from loopback.** The dashboard listens
        on 127.0.0.1 and is published to the owner's private network by a proxy
        on this same machine, so a request whose PEER is not loopback did not
        come through that proxy and its header is a string a stranger typed.

        **Take the LAST element, never the first.** `tailscale serve` — Go's
        `httputil.ReverseProxy` — APPENDS the address it saw to whatever the
        client sent, so the header is `<whatever the client claimed>, <the
        address the proxy saw>`. Reading the first element gave a guesser a
        fresh bucket of five attempts for every made-up address they put in it,
        which is unlimited guessing with a lockout bolted to the side of it.
        The last element is the proxy's own observation.

        A guesser who is already ON this machine can still put an address in
        that header, which is what the global counter in `note_failure` is for.
        """
        peer = str(request.remote or "").strip()
        if _is_loopback(peer):
            chain = [part.strip() for part
                     in request.headers.get("X-Forwarded-For", "").split(",")]
            hops = [part for part in chain if part]
            if hops:
                return hops[-1]
        return peer or "unknown"

    def lock_remaining(self, ip: str) -> int:
        """Seconds this address must wait, or 0.

        A global lock outranks the per-address one: while the form is closed it
        is closed for everybody, including an address that has never guessed
        and including the right code.
        """
        until = max(self._locked_until.get(ip, 0.0), self._global_locked_until)
        remaining = until - time.time()
        return int(remaining) + 1 if remaining > 0 else 0

    def note_failure(self, ip: str, *, detail: str = "") -> int:
        """Record one wrong access code. Returns the lock in seconds, or 0.

        Loud on purpose, in both places: the journal line is what an operator
        greps tonight, and the `events` row is what answers "was somebody
        guessing at this last week" after the journal has rotated away.
        """
        now = time.time()
        recent = [t for t in self._failures.get(ip, [])
                  if now - t < FAILURE_WINDOW_SECONDS]
        recent.append(now)
        self._failures[ip] = recent
        self._forget_old_addresses(now)
        locked = 0
        if len(recent) >= FAILURES_BEFORE_LOCK:
            self._locked_until[ip] = now + LOCK_SECONDS
            self._failures[ip] = []
            locked = LOCK_SECONDS
        log.warning("dashboard sign-in FAILED from %s (%d in the last 15 "
                    "minutes%s)%s", ip, len(recent),
                    f", locked for {locked}s" if locked else "",
                    f" — {detail}" if detail else "")
        try:
            self.store.add_event(
                None, None, "warning", "dashboard_signin_failed",
                f"wrong access code from {ip}"
                + (f"; that address is locked for {locked}s" if locked else ""))
        except Exception:
            # The journal line above has already fired. A store that cannot
            # take the event must not stop the sign-in page from answering.
            log.exception("call store: could not record the failed sign-in")
        return max(locked, self._note_global_failure(now))

    def _note_global_failure(self, now: float) -> int:
        """The same failure, counted across every address. Returns the lock.

        A per-address limit is a speed limit per address: a guesser with a list
        of addresses — or one who can write the forwarded header — pays nothing
        for it. This is the ceiling on the whole form, and it is deliberately
        loud, because closing the owner out for a minute is something they may
        ring up about.
        """
        self._global_failures = [t for t in self._global_failures
                                 if now - t < FAILURE_WINDOW_SECONDS]
        self._global_failures.append(now)
        if len(self._global_failures) <= GLOBAL_FAILURES_BEFORE_LOCK:
            return 0
        seen = len(self._global_failures)
        self._global_locked_until = now + GLOBAL_LOCK_SECONDS
        self._global_failures = []
        log.warning("dashboard sign-in LOCKED for every address for %ds: %d "
                    "wrong access codes in the last 15 minutes, from any "
                    "number of addresses", GLOBAL_LOCK_SECONDS, seen)
        try:
            self.store.add_event(
                None, None, "warning", "dashboard_signin_locked",
                f"{seen} wrong access codes in 15 minutes; the sign-in page is "
                f"closed to everybody for {GLOBAL_LOCK_SECONDS}s")
        except Exception:
            log.exception("call store: could not record the sign-in lockout")
        return GLOBAL_LOCK_SECONDS

    def note_success(self, ip: str) -> None:
        """One owner getting their code right clears THEIR address only.

        The global counter is left alone on purpose: somebody signing in
        successfully is not evidence that the other nineteen wrong codes in the
        last quarter of an hour were innocent.
        """
        self._failures.pop(ip, None)
        self._locked_until.pop(ip, None)

    def _forget_old_addresses(self, now: float) -> None:
        """Keep the failure table from growing without bound under a scanner."""
        if len(self._failures) <= 1000:
            return
        for ip, attempts in list(self._failures.items()):
            if not attempts or now - attempts[-1] >= FAILURE_WINDOW_SECONDS:
                self._failures.pop(ip, None)
        for ip, until in list(self._locked_until.items()):
            if until <= now:
                self._locked_until.pop(ip, None)

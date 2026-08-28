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
    that address waits a minute. Every failure is logged with its source and
    written to `events`, because "somebody is guessing at my dashboard" is a
    thing the owner has to be able to find out afterwards.

Tenancy lives here too: a `Session` carries the profile keys its owner is
allowed to read, and every store read in the dashboard is given that list.
"""
from __future__ import annotations

import hashlib
import hmac
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
# The wildcard an owner's `profiles` list uses to mean "every business".
ALL_PROFILES = "*"
SIGN_IN_PATH = "/sign-in"


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
        """Where a sign-in attempt came from.

        The dashboard listens on loopback only and is published to the owner's
        private network by a reverse proxy on this same machine, so
        `X-Forwarded-For` here is written by that proxy and is the only place
        the real address survives.
        """
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.remote or "unknown"

    def lock_remaining(self, ip: str) -> int:
        """Seconds this address must wait, or 0."""
        remaining = self._locked_until.get(ip, 0.0) - time.time()
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
        return locked

    def note_success(self, ip: str) -> None:
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

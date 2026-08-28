"""Is the phone line answering properly? One answer, composed from five.

Pure functions with no I/O so the verdict can be unit-tested: the caller hands
in what it already read (the cached health snapshot, the number map, the newest
call, the newest failed notification) and gets back the band the Overview
paints across the top of the page.

The rule that matters: the band is never green while a sub-check is failing,
and it is never green while a sub-check is simply UNKNOWN either. A line whose
model has not been probed yet, or that has not taken a call the phone network
signed for in a day, has not been confirmed — and saying "all good" about
something nobody has checked is the exact failure this dashboard exists to
stop.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

# How recently the phone network must have sent us a call we could verify
# before the dashboard will say the webhook is confirmed.
VERIFIED_WINDOW_SECONDS = 86400

OK, UNKNOWN, WARN, DOWN = "ok", "unknown", "warn", "down"
_SEVERITY = {OK: 0, UNKNOWN: 1, WARN: 2, DOWN: 3}


@dataclass(frozen=True)
class Check:
    """One thing that has to be true for the line to be working."""
    name: str
    label: str
    level: str
    detail: str


@dataclass(frozen=True)
class LineStatus:
    level: str
    headline: str
    checks: tuple

    @property
    def summary(self) -> str:
        return " · ".join(check.detail for check in self.checks)

    @property
    def problems(self) -> tuple:
        return tuple(c for c in self.checks if c.level != OK)


def _brain_check(health: dict) -> Check:
    backend = str(health.get("model_backend", ""))
    others = [name for name in health.get("unreachable_brains") or []
              if name != health.get("brain")]
    if backend == "UNREACHABLE":
        why = str(health.get("probe_error", "")).strip()
        return Check("brain", "The model that answers", DOWN,
                     "The model that answers calls is not responding"
                     + (f" ({why})" if why else ""))
    if backend == "pending":
        return Check("brain", "The model that answers", UNKNOWN,
                     "Still checking the model that answers calls")
    if others:
        listed = ", ".join(sorted(others))
        return Check("brain", "The model that answers", WARN,
                     f"One of your businesses answers on a model that is not "
                     f"responding ({listed})")
    return Check("brain", "The model that answers", OK, "Model responding")


def _twilio_check(last_call_at, now: float) -> Check:
    if last_call_at is None:
        return Check("phone_network", "Phone network", UNKNOWN,
                     "No calls yet, so the phone network connection has not "
                     "been confirmed")
    age = now - float(last_call_at)
    if age > VERIFIED_WINDOW_SECONDS:
        return Check("phone_network", "Phone network", UNKNOWN,
                     "No calls in the last 24 hours, so the phone network "
                     "connection has not been confirmed today")
    return Check("phone_network", "Phone network", OK,
                 "Phone network verified")


def _numbers_check(numbers: dict, profiles) -> Check:
    known = set(profiles)
    mapped = [n for n, key in numbers.items() if key in known]
    if not mapped:
        if numbers:
            return Check("numbers", "Your numbers", DOWN,
                         "Your phone numbers do not point at a business yet")
        return Check("numbers", "Your numbers", DOWN,
                     "No phone number is set up yet")
    return Check("numbers", "Your numbers", OK,
                 f"{len(mapped)} number{'' if len(mapped) == 1 else 's'} answering")


def _notify_check(health: dict, notify_failure) -> Check:
    failures = int(health.get("ntfy_failures") or 0)
    last = dict(health.get("last_delivery") or {})
    target = str((notify_failure or {}).get("target", "")).strip()
    named = f" to {target}" if target else ""
    if failures:
        return Check("notifications", "Message alerts", WARN,
                     f"Message alerts{named} are failing "
                     f"({failures} in a row)")
    if last.get("ok") is False:
        return Check("notifications", "Message alerts", WARN,
                     f"The last message alert{named} did not get through")
    return Check("notifications", "Message alerts", OK, "Alerts delivering")


def line_status(*, health: dict, numbers: dict, profiles, last_call_at=None,
                notify_failure=None, now=None) -> LineStatus:
    """The band across the top of the Overview."""
    moment = time.time() if now is None else float(now)
    bridge_ok = str(health.get("bridge", "")) == "ok"
    checks = (
        Check("answering", "Answering calls", OK if bridge_ok else DOWN,
              "Answering calls" if bridge_ok
              else "The phone service is not answering"),
        _brain_check(health),
        _twilio_check(last_call_at, moment),
        _numbers_check(numbers, profiles),
        _notify_check(health, notify_failure),
    )
    worst = max(_SEVERITY[c.level] for c in checks)
    if worst == _SEVERITY[DOWN]:
        down = [c for c in checks if c.level == DOWN]
        return LineStatus(DOWN, f"Your line is not answering — {down[0].detail}",
                          checks)
    if worst == _SEVERITY[WARN]:
        return LineStatus(WARN, "Your line needs attention", checks)
    if worst == _SEVERITY[UNKNOWN]:
        return LineStatus(WARN, "Your line has not been confirmed yet", checks)
    return LineStatus(OK, "Your line is answering", checks)


# ------------------------------------------------------ production safety --
# A Brain carries no "is this licensed for business use" field, so the label is
# the signal: an owner (or the installer) writes "test only" into the label of
# a backend whose plan forbids answering real customers. If a `production` flag
# is ever added to [brains.*], read it here first and keep the label rule as
# the fallback.

def is_test_only(brain) -> bool:
    """True when this backend's label says it is not for real customers."""
    production = getattr(brain, "production", None)
    if production is False:
        return True
    return "test only" in str(getattr(brain, "label", "")).lower()


def runs_where(brain) -> str:
    """Where a backend runs, in the owner's terms."""
    base = str(getattr(brain, "base_url", ""))
    host = base.split("//", 1)[-1].split("/", 1)[0].split("@")[-1]
    host = host.rsplit(":", 1)[0].strip("[]").lower()
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return "Private — on this machine"
    return "Cloud"

"""The Overview: "is my phone being answered properly?", answered in five
seconds, above the fold, on a phone.

Two rules run through everything here:

  * **Nothing is probed on this path.** The health picture comes from the cache
    a background task fills every minute, and the page says how old it is. A
    dashboard refresh must never be able to start a billable model request.
  * **A panel that cannot read says so.** Every store read is wrapped: the
    reason lands in the panel, the page still renders 200. This screen is where
    an owner comes when something is wrong, so it is the last screen allowed to
    become an error page.
"""
from __future__ import annotations

import asyncio
import logging
import time

from aiohttp import web

from . import render, status

log = logging.getLogger("atlas-phone")

ALERT_WINDOW_SECONDS = 7 * 86400
LATEST_MESSAGES = 5

# What each operational event MEANS, for the person who owns the phone line
# rather than the person who wrote the service. An event kind with no sentence
# here is shown with its own words tidied up — better a slightly technical line
# than a silent one.
ALERT_WORDS = {
    "brain_unreachable": "The model that answers calls did not respond",
    "brain_missing": "A business points at a model that is not set up",
    "config_backup_failed": "A settings backup could not be written",
    "dashboard_signin_failed": "Someone tried to sign in with the wrong access code",
    "delivery_failed": "A message could not be delivered",
    "delivery_failure_acknowledged": "You marked a failed message alert as seen",
    "delivery_interrupted": "A message delivery was cut short",
    "fallback_write_failed": "The backup copy of a message could not be written",
    "greeting_failed": "A greeting could not be built",
    "health_refresh_failed": "The line's own health check could not run",
    "hours_failed": "Your opening hours could not be read",
    "ntfy_push_failed": "A message alert did not reach your phone",
    "opt_out": "A caller asked not to be contacted again",
    "pad_write_failed": "A message could not be written down",
    "rate_limited": "A caller was slowed down for calling too often",
    "retention_failed": "The clear-out of old records did not run",
    "store_read_failed": "Something could not be read back from your records",
    "store_write_failed": "Something could not be saved to your records",
    "summarizer_failed": "A call could not be written up",
    "timezone_failed": "A business time zone could not be read",
    "twilio_relay_error": "The phone network reported a problem mid-call",
    "undelivered_no_push_channel": "A message could not be sent anywhere",
    "unhandled_relay_event": "The phone network sent something unexpected",
    "urgent_push_failed": "An urgent alert did not reach your phone",
    "watchdog": "A call ran long and was wrapped up",
    "watchdog_end_failed": "A long call could not be wrapped up",
    "ws_auth_rejected": "Something tried to connect to your line without permission",
}

MESSAGE_STATUS_WORDS = {
    "new": ("New", "accent"),
    "in_progress": ("In progress", "info"),
    "done": ("Done", "ghost"),
}


def alert_words(kind: str) -> str:
    return ALERT_WORDS.get(kind) or str(kind).replace("_", " ").capitalize()


def _read(what: str, fn, *args, **kwargs):
    """(value, reason) for one panel's data. Never raises.

    `reason` is a sentence the owner reads in place of the panel. The failure
    is logged with its traceback as well — a panel quietly showing "nothing
    here" when the truth is "the database would not open" is the dishonesty
    this dashboard was rebuilt to remove.
    """
    try:
        return fn(*args, **kwargs), ""
    except Exception as e:
        log.exception("dashboard: could not read %s", what)
        return None, f"Could not read {what}: {type(e).__name__}: {e}"


def _oldest_waiting(messages) -> float | None:
    waiting = [m["created_at"] for m in messages if m["status"] == "new"]
    return min(waiting) if waiting else None


def gather(deps, session, *, now=None) -> dict:
    """Every store read the Overview needs, in one blocking call.

    Called through asyncio.to_thread: these are SQLite reads on the same event
    loop that is streaming a live call's audio.
    """
    moment = time.time() if now is None else float(now)
    keys = list(session.profile_keys)
    store = deps.store
    whole_line = session.sees_whole_line

    stats, stats_error = _read("your call numbers", store.stats, keys, 7,
                               now=moment)
    messages, messages_error = _read("your messages", store.list_messages, keys,
                                     limit=LATEST_MESSAGES)
    waiting, waiting_error = _read("your messages", store.list_messages, keys,
                                   status="new")
    alerts, alerts_error = _read("what needs attention", store.list_events, keys,
                                 since=moment - ALERT_WINDOW_SECONDS,
                                 levels=("warning", "error"), limit=20,
                                 include_unscoped=whole_line)
    newest, newest_error = _read("your call log", store.list_calls, keys, limit=1)
    notify, _notify_error = _read("your alert history", store.list_notify, keys,
                                  ok=False, limit=1, include_unscoped=whole_line)
    for alert in alerts or []:
        alert["label"] = alert_words(alert["kind"])
    for message in messages or []:
        label, tone = MESSAGE_STATUS_WORDS.get(
            message["status"], (str(message["status"]).replace("_", " "), "ghost"))
        message["status_label"], message["status_tone"] = label, tone
    return {
        "stats": stats, "stats_error": stats_error,
        "messages": messages or [], "messages_error": messages_error,
        "waiting_count": len(waiting or []),
        "oldest_waiting_at": _oldest_waiting(waiting or []),
        "waiting_error": waiting_error,
        "alerts": alerts or [], "alerts_error": alerts_error,
        "last_call_at": (newest[0]["started_at"] if newest else None),
        "calls_error": newest_error,
        "notify_failure": (notify[0] if notify else None),
    }


def owner_brains(deps, session):
    """The model backends this owner's businesses actually answer on.

    An owner of the whole line gets None, which means "all of them". Anyone
    else is told about their own backends only: a brain key is a name the
    reseller chose, and it can belong to a business that is not theirs.
    """
    if session.sees_whole_line:
        return None
    brains, active = deps.get_brains()
    _numbers, profiles = deps.get_state()
    mine = {active}
    for key in session.profile_keys:
        chosen = str(profiles.get(key, {}).get("brain", "")).strip()
        if chosen in brains:
            mine.add(chosen)
    return mine


def scoped_numbers(deps, session) -> dict:
    """The phone numbers this owner's businesses answer on."""
    numbers, _profiles = deps.get_state()
    known = set(session.profile_keys)
    return {number: key for number, key in numbers.items() if key in known}


def sparkline(per_day) -> dict:
    """The 7-day call chart as plain geometry.

    Rectangles with x/y/width/height attributes, not CSS: the page's
    Content-Security-Policy allows no inline styles at all, and a chart that
    silently rendered as a flat line would be worse than no chart.
    """
    days = list(per_day or [])
    tallest = max([int(d["calls"]) for d in days] or [0])
    slot, height = 44, 96
    bars = []
    for index, day in enumerate(days):
        calls = int(day["calls"])
        no_info = int(day["no_info"])
        handled = max(0, calls - no_info)

        def scale(n):
            return int(round(height * n / tallest)) if tallest else 0

        bars.append({
            "x": index * slot + slot // 6,
            "handled_h": scale(handled), "handled_y": height - scale(handled),
            "no_info_h": scale(no_info),
            "no_info_y": height - scale(handled) - scale(no_info),
            "label": time.strftime("%a", time.strptime(day["date"], "%Y-%m-%d")),
            "calls": calls, "no_info": no_info, "date": day["date"],
        })
    return {"bars": bars, "width": max(1, len(bars)) * slot, "height": height,
            "bar_width": slot - 2 * (slot // 6), "any": tallest > 0}


def active_brain(deps):
    brains, active = deps.get_brains()
    return brains.get(active)


def business_label(deps, session) -> str:
    """Whose line this is, in the heading: the business, or how many there are."""
    _numbers, profiles = deps.get_state()
    names = [str(profiles.get(key, {}).get("business_name", "")).strip() or key
             for key in session.profile_keys]
    if len(names) == 1:
        return names[0]
    if not names:
        return "No business set up yet"
    return f"{len(names)} businesses"


async def overview(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    health, _model_ok = await deps.get_health()
    data = await asyncio.to_thread(gather, deps, session)
    numbers = scoped_numbers(deps, session)
    brain = active_brain(deps)
    band = status.line_status(
        health=health, numbers=numbers, profiles=session.profile_keys,
        last_call_at=data["last_call_at"], notify_failure=data["notify_failure"],
        owner_brains=owner_brains(deps, session))
    stats = data["stats"] or {}
    per_day = stats.get("per_day") or []
    week_total = sum(int(d["calls"]) for d in per_day)
    delivery = dict(health.get("last_delivery") or {})
    return render.page(
        request, deps, "overview.html", session=session,
        band=band, health=health, data=data, numbers=numbers,
        stats=stats, chart=sparkline(per_day),
        week_average=(round(week_total / len(per_day)) if per_day else 0),
        test_only_brain=(brain if brain is not None and status.is_test_only(brain)
                         else None),
        can_switch_brain=session.sees_whole_line,
        delivery=delivery, delivery_failed=delivery.get("ok") is False,
        checked_at=health.get("probe_checked_at"),
        first_run=(data["last_call_at"] is None and not data["calls_error"]),
        acknowledged=bool(request.query.get("acknowledged")),
        today_label=time.strftime("%A, %B %-d"),
        business_label=business_label(deps, session),
    )


async def status_band(request: web.Request) -> web.Response:
    """Just the line-status band, so the page can keep it current without a
    reload. Same reads, same rules — htmx swaps this in every 30 seconds."""
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    health, _model_ok = await deps.get_health()
    data = await asyncio.to_thread(gather, deps, session)
    band = status.line_status(
        health=health, numbers=scoped_numbers(deps, session),
        profiles=session.profile_keys, last_call_at=data["last_call_at"],
        notify_failure=data["notify_failure"],
        owner_brains=owner_brains(deps, session))
    return render.partial(request, deps, "_status_band.html", session=session,
                          band=band, checked_at=health.get("probe_checked_at"))


async def health_detail(request: web.Request) -> web.Response:
    """The health picture as JSON, for an owner who wants the raw answer.

    Scoped like every other read: the snapshot names every business on the
    line, and an owner of one business may not read the others.
    """
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    health, _model_ok = await deps.get_health()
    data = await asyncio.to_thread(gather, deps, session)
    numbers = scoped_numbers(deps, session)
    band = status.line_status(
        health=health, numbers=numbers, profiles=session.profile_keys,
        last_call_at=data["last_call_at"], notify_failure=data["notify_failure"],
        owner_brains=owner_brains(deps, session))
    body = dict(health)
    body["profiles"] = list(session.profile_keys)
    body["numbers"] = len(numbers)
    if not session.sees_whole_line:
        # These name backends the whole line shares; an owner of one business
        # is not shown the others' machinery.
        body.pop("unreachable_brains", None)
        body.pop("brain", None)
        body.pop("model", None)
        body.pop("probe_error", None)     # can name the backend's own host
        body.pop("recent_events", None)
    body["line_status"] = {
        "level": band.level, "headline": band.headline,
        "checks": [{"name": c.name, "level": c.level, "detail": c.detail}
                   for c in band.checks],
    }
    return web.json_response(body)


async def acknowledge_delivery(request: web.Request) -> web.Response:
    """"I have seen it" for a message that could not be delivered.

    The public health endpoint stays 503 until the next successful delivery or
    until this is clicked — an owner who has read the message on this screen
    has taken it from here, and the tripwire should stop paging.
    """
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    form = await request.post()
    reason = deps.auth.check_csrf(request, session, form)
    if reason:
        return render.page(request, deps, "refused.html", session=session,
                           status=403, reason=reason)
    acknowledged = await asyncio.to_thread(deps.acknowledge_delivery_failure,
                                           session.owner_key)
    # Only say "marked as seen" when there was something to mark: the alert may
    # have cleared itself between the page being drawn and the button pressed.
    raise web.HTTPSeeOther("/?acknowledged=1" if acknowledged else "/")

"""When the business is open, and what the line does when it is not.

The dashboard this replaces had no idea a business ever closed. Everything on
this screen is a real setting the answering code already reads — the weekly
table, the holidays, the timezone, and what an out-of-hours caller is offered —
so what is drawn here is what a caller at nine on a Sunday morning actually
gets.

Two rules worth naming:

  * **Times are read the way people write them.** "9:00 AM", "9am" and "09:00"
    all mean the same thing and are stored the one way the service reads.
  * **The empty state is honest.** No schedule means the line answers the same
    way at 3am as at 3pm, and the screen says exactly that rather than showing
    seven blank rows that imply otherwise.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from datetime import datetime

from aiohttp import web

from . import config_edit as edit
from . import render

# service.py puts the plugin's own directory on sys.path; when the dashboard is
# loaded on its own (tests) it may not have run yet. `hours` imports nothing
# from the service, so there is no cycle — this is the module that owns what a
# day range and a holiday mean, and reading them from a second copy here is how
# the two would drift.
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)
import hours as hours_lib  # noqa: E402

log = logging.getLogger("atlas-phone")

DAY_NAMES = (("mon", "Monday"), ("tue", "Tuesday"), ("wed", "Wednesday"),
             ("thu", "Thursday"), ("fri", "Friday"), ("sat", "Saturday"),
             ("sun", "Sunday"))
AFTER_HOURS_WORDS = (
    ("message", "Take a message",
     "The agent explains you are closed and takes the caller's details."),
    ("transfer", "Still offer a transfer",
     "Out-of-hours callers can still ask to be put through to a person."),
    ("same", "Answer the same way",
     "No difference between an open hour and a closed one."),
)
# The zones a small business on this product is actually in, plus whatever the
# business already has set. A list of six hundred IANA names is not a setting
# anybody can use, and the current value is always in the list so a save can
# never quietly move a business to another timezone.
COMMON_ZONES = (
    ("America/New_York", "Eastern — New York"),
    ("America/Chicago", "Central — Chicago"),
    ("America/Denver", "Mountain — Denver"),
    ("America/Phoenix", "Mountain, no daylight saving — Phoenix"),
    ("America/Los_Angeles", "Pacific — Los Angeles"),
    ("America/Anchorage", "Alaska — Anchorage"),
    ("Pacific/Honolulu", "Hawaii — Honolulu"),
    ("America/Halifax", "Atlantic — Halifax"),
    ("Europe/London", "United Kingdom — London"),
    ("Europe/Dublin", "Ireland — Dublin"),
    ("Europe/Lisbon", "Portugal — Lisbon"),
    ("Europe/Madrid", "Spain — Madrid"),
    ("Europe/Paris", "France — Paris"),
    ("Europe/Berlin", "Germany — Berlin"),
    ("Europe/Amsterdam", "Netherlands — Amsterdam"),
    ("Europe/Rome", "Italy — Rome"),
    ("Europe/Stockholm", "Sweden — Stockholm"),
    ("Europe/Warsaw", "Poland — Warsaw"),
    ("Europe/Athens", "Greece — Athens"),
    ("Europe/Helsinki", "Finland — Helsinki"),
)
_CLOCK = re.compile(r"^\s*([0-9]{1,2})\s*[:.]?\s*([0-9]{2})?\s*([ap])\.?m\.?\s*$",
                    re.IGNORECASE)
_PLAIN = re.compile(r"^\s*([0-9]{1,2})\s*[:.]\s*([0-9]{2})\s*$")


def parse_clock(text: str) -> tuple:
    """("HH:MM", "") for anything a person would write, else ("", why not)."""
    typed = str(text or "").strip()
    if not typed:
        return "", "Give a time, like 9:00 AM."
    match = _CLOCK.match(typed)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        half = match.group(3).lower()
        if not 1 <= hour <= 12:
            return "", f"“{typed}” is not a time on a clock face."
        hour = (hour % 12) + (12 if half == "p" else 0)
    else:
        match = _PLAIN.match(typed)
        if not match:
            return "", (f"“{typed}” is not a time this line can read. Write it "
                        "like 9:00 AM, or 09:00.")
        hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return "", f"“{typed}” is not a time that exists."
    return f"{hour:02d}:{minute:02d}", ""


def show_clock(value: str) -> str:
    """"09:00" as the owner would say it out loud."""
    try:
        return datetime.strptime(str(value), "%H:%M").strftime(
            "%-I:%M %p")
    except ValueError:
        return str(value)


def zone_choices(current: str) -> list:
    listed = list(COMMON_ZONES)
    current = str(current or "").strip()
    if current and current not in {name for name, _label in listed}:
        listed.insert(0, (current, f"{current} (set on this line)"))
    return listed


# ----------------------------------------------------------- what is there --

def read_hours(deps, profile: dict) -> dict:
    table = dict(edit.setting(deps, profile, "hours") or {})
    days = []
    for key, name in DAY_NAMES:
        span = str(table.get(key, "")).strip()
        start, _sep, end = span.partition("-")
        days.append({
            "key": key, "name": name, "open": bool(span),
            "from": show_clock(start) if start else "9:00 AM",
            "to": show_clock(end) if end else "5:00 PM",
            "overnight": bool(span) and start > end,
        })
    holidays = [str(item).strip() for item
                in edit.setting(deps, profile, "holidays") or []]
    return {
        "days": days, "holidays": holidays,
        "timezone": str(edit.setting(deps, profile, "timezone")),
        "after_hours": str(edit.setting(deps, profile, "after_hours")),
        "after_hours_greeting": str(edit.setting(deps, profile,
                                                 "after_hours_greeting")),
        "always_open": not table and not holidays,
    }


def submitted_hours(deps, form) -> dict:
    days = []
    for key, name in DAY_NAMES:
        days.append({
            "key": key, "name": name,
            "open": edit.checked(form, f"open_{key}"),
            "from": edit.text_of(form, f"from_{key}"),
            "to": edit.text_of(form, f"to_{key}"),
            "overnight": False,
        })
    return {
        "days": days,
        "holidays": edit.rows_of(form, "holiday"),
        "timezone": edit.text_of(form, "timezone"),
        "after_hours": edit.text_of(form, "after_hours"),
        "after_hours_greeting": edit.text_of(form, "after_hours_greeting"),
        "always_open": False,
    }


def validate(deps, values: dict, profile: dict) -> tuple:
    """(errors by field, the profile settings to write)."""
    errors: dict = {}
    table: dict = {}
    for day in values["days"]:
        if not day["open"]:
            continue
        start, start_error = parse_clock(day["from"])
        end, end_error = parse_clock(day["to"])
        if start_error or end_error:
            errors[f"day_{day['key']}"] = start_error or end_error
            continue
        try:
            hours_lib.parse_day_range(f"{start}-{end}")
        except ValueError as e:
            errors[f"day_{day['key']}"] = str(e)
            continue
        table[day["key"]] = f"{start}-{end}"
        day["overnight"] = start > end

    holidays = list(values["holidays"])
    for item in holidays:
        try:
            hours_lib.parse_holiday(item)
        except ValueError as e:
            errors["holidays"] = str(e)
            break
    if len(holidays) > edit.MAX_HOLIDAYS:
        errors["holidays"] = (f"That is {len(holidays)} closures. Keep it to "
                              f"{edit.MAX_HOLIDAYS}.")

    zone = values["timezone"].strip()
    if (table or holidays) and not zone:
        errors["timezone"] = ("Opening hours need a time zone, or nobody can "
                              "say what nine o'clock means. Pick the one the "
                              "business is in.")
    elif zone:
        try:
            hours_lib.profile_zone({"timezone": zone})
        except ValueError as e:
            errors["timezone"] = str(e)

    modes = deps.product_defaults.get("after_hours_modes", ("message",))
    if values["after_hours"] not in modes:
        errors["after_hours"] = ("Pick one of the three things the line can do "
                                 "after hours.")
    elif values["after_hours"] == "transfer" and not str(
            profile.get("forward_to", "")).strip():
        errors["after_hours"] = ("This business has no number to transfer to, "
                                 "so an out-of-hours caller would have nowhere "
                                 "to go. Set one up under Transfer to a person "
                                 "first.")
    long = edit.too_long("after_hours_greeting", values["after_hours_greeting"])
    if long:
        errors["after_hours_greeting"] = long

    updates = {
        "hours": table or None,
        "holidays": holidays or None,
        "timezone": zone or None,
        "after_hours": edit.default_or_none(deps, "after_hours",
                                            values["after_hours"]),
        "after_hours_greeting": values["after_hours_greeting"] or None,
    }
    return errors, updates


def open_now(deps, profile: dict) -> dict:
    """What the line is doing this minute, in the owner's words."""
    try:
        state = hours_lib.open_state(profile, datetime.now().astimezone())
    except ValueError as e:
        return {"level": "warn", "text": f"Your opening hours cannot be read: {e}"}
    if state.reason == "always":
        return {"level": "ok", "text": "Open — the line answers the same way "
                                       "around the clock"}
    if state.open:
        return {"level": "ok", "text": "Open right now"}
    if state.next_open is None:
        return {"level": "warn",
                "text": "Closed, and nothing in the next two weeks reopens it"}
    return {"level": "warn",
            "text": "Closed right now · opens "
                    + state.next_open.strftime("%A at %-I:%M %p")}


# -------------------------------------------------------------- the screen --

def page_context(deps, session, key: str, *, values=None, errors=None,
                 error: str = "", saved: bool = False) -> dict:
    profile = edit.profile_of(deps, key)
    values = read_hours(deps, profile) if values is None else values
    return {
        "business_key": key, "business": edit.business_name(deps, key),
        "businesses": edit.businesses(deps, session),
        "values": values, "errors": dict(errors or {}), "error": error,
        "saved": saved, "version": edit.version(deps),
        "zones": zone_choices(values["timezone"]),
        "after_hours_choices": AFTER_HOURS_WORDS,
        "forward_to": str(profile.get("forward_to", "")),
        "state": open_now(deps, profile),
    }


async def _no_such_business(request, deps, session) -> web.Response:
    return await render.page(
        request, deps, "refused.html", session=session, status=404,
        reason=("That business is not on your line. It may have been removed, "
                "or it belongs to somebody else."))


async def _page(request, deps, session, key: str, *, status=200, **overrides):
    if not key:
        return await render.page(
            request, deps, "refused.html", session=session, status=404,
            reason=("There is no business on your line to set opening hours "
                    "for yet."))
    context = await asyncio.to_thread(page_context, deps, session, key,
                                      **overrides)
    return await render.page(request, deps, "hours.html", session=session,
                             status=status,
                             flash=render.pop_flash(request, session),
                             **context)


async def hours(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    key = edit.chosen_business(deps, session, request.query.get("business", ""))
    return await _page(request, deps, session, key)


async def hours_for(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    key = request.match_info["profile"]
    if key not in set(session.profile_keys) or not edit.profile_of(deps, key):
        return await _no_such_business(request, deps, session)
    return await _page(request, deps, session, key)


async def save_hours(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    key = request.match_info["profile"]
    if key not in set(session.profile_keys) or not edit.profile_of(deps, key):
        return await _no_such_business(request, deps, session)
    form = await request.post()
    reason = deps.auth.check_csrf(request, session, form)
    if reason:
        return await render.page(request, deps, "refused.html", session=session,
                                 status=403, reason=reason)
    if await asyncio.to_thread(edit.is_stale, deps, form):
        return await _page(request, deps, session, key, status=409,
                           values=submitted_hours(deps, form),
                           error=edit.STALE_MESSAGE)
    profile = edit.profile_of(deps, key)
    values = submitted_hours(deps, form)
    errors, updates = validate(deps, values, profile)
    if errors:
        return await _page(request, deps, session, key, status=400,
                           values=values, errors=errors)
    error = await asyncio.to_thread(
        edit.save, deps, session,
        profiles=edit.profiles_with(deps, key, updates),
        summary=f"Changed the opening hours for {edit.business_name(deps, key)}")
    if error:
        return await _page(request, deps, session, key, status=400,
                           values=values,
                           error=f"Nothing was changed. {error}")
    log.info("dashboard: %s changed the opening hours for %s",
             session.owner_key, key)
    render.set_flash(request, session, "Opening hours saved — live on the next "
                                       "call.")
    raise web.HTTPSeeOther(f"/hours/{key}")

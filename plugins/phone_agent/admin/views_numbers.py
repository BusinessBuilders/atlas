"""The phone numbers on this line, and which business each one answers for.

The screen this replaces was a textarea of `+15550000001 = business_key` lines,
with no way to tell whether the phone network was actually pointed at this
bridge. Here:

  * a number's business is a `<select>` of real businesses, never typed text;
  * a number is validated and tidied into the form the phone network wants
    before it is saved, so an owner can type what is printed on their card;
  * the same number twice is refused by name, because the second line silently
    won the old parse and one business quietly stopped being reachable;
  * every number says when the phone network last called it — the only honest
    evidence the webhook is wired up — and the exact address to paste into the
    Twilio console when it never has.

Numbers belong to the whole line: they are how the line is wired, and one
business's owner cannot be allowed to point somebody else's number at
themselves. An owner of one business sees their own numbers, read only.
"""
from __future__ import annotations

import asyncio
import logging
import time

from aiohttp import web

from . import config_edit as edit
from . import render

log = logging.getLogger("atlas-phone")

# How recently the phone network must have called a number for the screen to
# call it verified. Matches the line-status band's own window, so the two
# cannot say different things about the same fact.
VERIFIED_WINDOW_SECONDS = 86400
WEBHOOK_PATH = "/voice/incoming"


def webhook_url(deps) -> str:
    return str(deps.public_base or "").rstrip("/") + WEBHOOK_PATH


def _seen(last_at, now: float) -> dict:
    if last_at is None:
        return {"level": "unknown", "text": "Never seen a call from the phone "
                                            "network", "at": None}
    if now - float(last_at) > VERIFIED_WINDOW_SECONDS:
        return {"level": "warn", "text": "No calls in the last 24 hours",
                "at": last_at}
    return {"level": "ok", "text": "Verified", "at": last_at}


def gather(deps, session, *, now=None) -> dict:
    """Every number this login may see, with what is known about each."""
    moment = time.time() if now is None else float(now)
    numbers, profiles = deps.get_state()
    mine = set(session.profile_keys)
    listed = [(number, key) for number, key in numbers.items()
              if session.sees_whole_line or key in mine]
    seen, error = render.guarded_read(
        "when your numbers last took a call",
        deps.store.last_call_per_number, [n for n, _k in listed])
    rows = []
    for number, key in sorted(listed):
        profile = profiles.get(key) or {}
        rows.append({
            "number": number, "profile_key": key,
            "business": str(profile.get("business_name", "")).strip() or key,
            "known": key in profiles,
            "seen": _seen((seen or {}).get(number), moment),
        })
    return {
        # Named apart from the page's own `error`: one is "this list could not
        # be read", the other is "your change was refused".
        "rows": rows, "load_error": error,
        "businesses": edit.businesses(deps, session),
        "can_change": session.sees_whole_line,
        "webhook": webhook_url(deps),
        "version": edit.version(deps),
    }


async def _page(request, deps, session, *, status=200, error="", values=None,
                errors=None) -> web.Response:
    data = await asyncio.to_thread(gather, deps, session)
    return await render.page(
        request, deps, "numbers.html", session=session, status=status,
        error=error, errors=dict(errors or {}), values=dict(values or {}),
        flash=render.pop_flash(request, session), **data)


async def numbers(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    return await _page(request, deps, session)


def _read_form(form) -> dict:
    """What was submitted: one business per existing number, plus the new one."""
    assignments = {}
    for name in form.keys():
        if name.startswith("business_for:"):
            assignments[name.split(":", 1)[1]] = str(form.get(name, "")).strip()
    return {
        "assignments": assignments,
        "removed": set(edit.rows_of(form, "remove")),
        "new_number": edit.text_of(form, "new_number"),
        "new_business": edit.text_of(form, "new_business"),
    }


def build_numbers(deps, session, values: dict) -> tuple:
    """(the new number map, errors by field). Nothing is written here."""
    live, profiles = deps.get_state()
    errors: dict = {}
    owned = {key for key, _name in edit.businesses(deps, session)}
    updated: dict = {}
    for number, key in live.items():
        if number in values["removed"]:
            continue
        wanted = values["assignments"].get(number, key)
        if wanted != key and wanted not in owned:
            errors[f"business_for:{number}"] = (
                "That is not a business on this line. Reload the page and pick "
                "one of the businesses listed.")
            wanted = key
        updated[number] = wanted

    typed = values["new_number"]
    if typed or values["new_business"]:
        number, problem = edit.e164(typed)
        if problem:
            errors["new_number"] = problem
        elif number in updated:
            # The old free-text box let the second line quietly win, and one
            # business stopped being reachable with nothing said about it.
            errors["new_number"] = (
                f"{number} is already on this line, answering for "
                f"{_name_of(deps, updated[number])}. Change it in the list "
                "above instead of adding it twice.")
        elif values["new_business"] not in owned:
            errors["new_business"] = "Pick the business this number answers for."
        else:
            updated[number] = values["new_business"]
    return updated, errors


def _name_of(deps, key: str) -> str:
    _numbers, profiles = deps.get_state()
    return str((profiles.get(key) or {}).get("business_name", "")).strip() or key


async def save_numbers(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    if not session.sees_whole_line:
        return await render.page(
            request, deps, "refused.html", session=session, status=403,
            reason=("Which business a phone number answers for is how the whole "
                    "line is wired, so only the account that manages the whole "
                    "line can change it."))
    form = await request.post()
    reason = deps.auth.check_csrf(request, session, form)
    if reason:
        return await render.page(request, deps, "refused.html", session=session,
                                 status=403, reason=reason)
    if await asyncio.to_thread(edit.is_stale, deps, form):
        return await _page(request, deps, session, status=409,
                           error=edit.STALE_MESSAGE)
    values = _read_form(form)
    updated, errors = build_numbers(deps, session, values)
    if errors:
        return await _page(request, deps, session, status=400, values=values,
                           errors=errors)
    if not updated:
        return await _page(
            request, deps, session, status=400, values=values,
            error=("A phone line needs at least one number, or there is nothing "
                   "for a caller to ring. Nothing was changed."))
    error = await asyncio.to_thread(edit.save, deps, session, numbers=updated,
                                    summary="Changed which business each phone "
                                            "number answers for")
    if error:
        return await _page(request, deps, session, status=400, values=values,
                           error=f"Nothing was changed. {error}")
    log.info("dashboard: %s changed the number map (%d number(s))",
             session.owner_key, len(updated))
    render.set_flash(request, session,
                     "Your numbers were saved — live on the next call.")
    raise web.HTTPSeeOther("/numbers")

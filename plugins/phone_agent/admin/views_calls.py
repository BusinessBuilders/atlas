"""The call log, and one call in full.

The screen this replaces ran `journalctl` in the request handler and grepped it
for a log format the bridge had stopped writing, so it showed an empty list and
said nothing was wrong. Everything here reads the call store instead, and three
rules run through all of it:

  * **Scope first, always.** Every read is given `session.profile_keys`. A call
    that belongs to another business on the same line is a 404, never a 403: a
    403 confirms the call exists, which is itself the leak.
  * **A list masks the number; the call's own page shows it.** A call log is
    read over the owner's shoulder in a shop. The whole number is on the page
    only its owner can open, where it is also the thing they have to dial.
  * **A panel that cannot read says so.** The reason lands in the panel and the
    page still renders — this is the screen an owner opens when they think
    something is wrong.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from urllib.parse import urlencode

from aiohttp import web

from . import render, status
from .views_overview import MESSAGE_STATUS_WORDS, _read

log = logging.getLogger("atlas-phone")

PAGE_SIZE = 50
# The most of one caller's calls this page reads back to decide whether the
# owner has any at all. It is NOT the safety check — the store enforces the
# scope of a delete itself, exactly and without a limit.
SCAN_LIMIT = 1000
# A note is the owner's own words about one job, not a document. The box says
# so and the server holds to it, because a form field's maxlength is a
# suggestion to a browser and nothing at all to anything else.
NOTE_MAX_CHARS = 2000
# Mirrors service.PROFILE_DEFAULTS["retention_days"]: what the line keeps when a
# business has not chosen for itself. A test pins the two together, because a
# dashboard promising "kept for 90 days" while the purge runs at 30 would be a
# lie told in the owner's own words.
DEFAULT_RETENTION_DAYS = 90

# What each ending MEANS to the person who owns the phone line, and the colour
# it earns. These are the words on the pills; the keys never reach the page.
OUTCOME_WORDS = {
    "message_taken": ("Message taken", "ok"),
    "transferred": ("Transferred", "info"),
    "caller_hung_up": ("Hung up", "ghost"),
    "no_info_given": ("Couldn't help", "warn"),
    "agent_error": ("Needs attention", "bad"),
    "blocked": ("Blocked", "bad"),
    "rate_limited": ("Limited", "warn"),
    "after_hours_message": ("After-hours message", "ok"),
}
# The order the filter offers them in: the ones an owner looks for first.
OUTCOME_ORDER = ("message_taken", "after_hours_message", "transferred",
                 "no_info_given", "caller_hung_up", "agent_error",
                 "rate_limited", "blocked")
NOTIFY_WORDS = {
    "sent": ("Sent to your phone", "ok"),
    "failed": ("Did not reach you", "bad"),
    "escalated": ("Sent as an urgent alert", "warn"),
    "off": ("No alert set up", "ghost"),
    "sending": ("Still going out", "ghost"),
}
# A call row written by the text handler, not the voice one: the body IS the
# message, so there is no transcript and no length to show.
SMS_REASON = "sms"


# ------------------------------------------------------------- the filters --

def _date_epoch(text: str, *, end_of_day: bool = False):
    """A `YYYY-MM-DD` from a date box as a local moment, or None if unreadable."""
    try:
        day = datetime.strptime(str(text).strip(), "%Y-%m-%d")
    except ValueError:
        return None
    if end_of_day:
        day = day.replace(hour=23, minute=59, second=59)
    return day.astimezone().timestamp()


def read_filters(query, session, profiles) -> dict:
    """What the owner asked to see, and anything in the URL that made no sense.

    Nothing here can widen the scope: `keys` always comes from the session. A
    business the owner does not own is reported as a filter that could not be
    used, and the list stays scoped to everything they DO own.
    """
    raw = {name: str(query.get(name, "")).strip()
           for name in ("from", "to", "outcome", "profile", "has_message", "q",
                        "show_test", "page")}
    problems = []

    since = _date_epoch(raw["from"]) if raw["from"] else None
    if raw["from"] and since is None:
        problems.append("That start date could not be read, so it was left out.")
    until = _date_epoch(raw["to"], end_of_day=True) if raw["to"] else None
    if raw["to"] and until is None:
        problems.append("That end date could not be read, so it was left out.")

    outcome = raw["outcome"] if raw["outcome"] in OUTCOME_WORDS else None
    if raw["outcome"] and outcome is None:
        problems.append("That outcome is not one this line records, so it was "
                        "left out.")

    keys = tuple(session.profile_keys)
    profile = ""
    if raw["profile"]:
        if raw["profile"] in keys:
            profile, keys = raw["profile"], (raw["profile"],)
        else:
            problems.append("That business is not one of yours, so every "
                            "business you own is shown.")

    has_message = {"yes": True, "no": False}.get(raw["has_message"])
    if raw["has_message"] and has_message is None:
        problems.append("That message filter could not be read, so it was "
                        "left out.")

    try:
        page = max(1, int(raw["page"] or 1))
    except ValueError:
        page = 1
        problems.append("That page number could not be read, so the newest "
                        "calls are shown.")

    return {
        "raw": raw, "keys": keys, "since": since, "until": until,
        "outcome": outcome, "profile": profile, "has_message": has_message,
        "q": raw["q"], "show_test": raw["show_test"] in ("1", "on", "yes"),
        "page": page, "problems": problems,
        "any": bool(raw["from"] or raw["to"] or outcome or profile or raw["q"]
                    or has_message is not None),
    }


def filter_query(filters: dict, **changes) -> str:
    """The current filters as a query string, with a page number swapped in."""
    values = {"from": filters["raw"]["from"], "to": filters["raw"]["to"],
              "outcome": filters["outcome"], "profile": filters["profile"],
              "has_message": filters["raw"]["has_message"], "q": filters["q"],
              "show_test": "1" if filters["show_test"] else ""}
    values.update(changes)
    kept = {k: v for k, v in values.items() if v not in ("", None)}
    return ("?" + urlencode(kept)) if kept else ""


# ------------------------------------------------------------ the call rows --

def business_names(deps) -> dict:
    """Every business on the line by the name its owner calls it."""
    _numbers, profiles = deps.get_state()
    return {key: str(profile.get("business_name", "")).strip() or key
            for key, profile in profiles.items()}


def retention_days(deps, session):
    """How long this owner's words are kept — the SHORTEST window they own.

    An owner of three businesses set to 90, 90 and 30 days is told 30: the
    sentence has to be true of everything on the screen.
    """
    _numbers, profiles = deps.get_state()
    windows = []
    for key in session.profile_keys:
        profile = profiles.get(key)
        if profile is None:
            continue
        value = profile.get("retention_days", DEFAULT_RETENTION_DAYS)
        try:
            windows.append(int(value))
        except (TypeError, ValueError):
            log.warning("dashboard: business %r has an unreadable retention "
                        "setting (%r) — the call log is not naming a window",
                        key, value)
            return None
    return min(windows) if windows else None


def decorate_call(row: dict, message, names: dict) -> dict:
    """One call row in the owner's words: the ending, who rang, where it landed."""
    label, tone = OUTCOME_WORDS.get(
        row.get("outcome") or "",
        ("Still on the call" if row.get("ended_at") is None else "Ended", "ghost"))
    row["outcome_label"], row["outcome_tone"] = label, tone
    row["is_text"] = str(row.get("decision_reason") or "") == SMS_REASON
    row["business"] = names.get(row["profile_key"], row["profile_key"])
    row["caller_name"] = (message or {}).get("caller_name") or ""
    row["message_id"] = (message or {}).get("id")
    if message:
        status_label, status_tone = MESSAGE_STATUS_WORDS.get(
            message["status"],
            (str(message["status"]).replace("_", " "), "ghost"))
        row["status_label"], row["status_tone"] = status_label, status_tone
    else:
        row["status_label"], row["status_tone"] = "", ""
    return row


def gather_calls(deps, session, query) -> dict:
    """Every store read the call log needs: the page of calls, then the
    messages those calls left.

    Two queries, both bounded by the page: the call list, and one lookup of the
    messages belonging to exactly the calls on screen. The Overview's `gather()`
    is six reads and is deliberately not used here.
    """
    filters = read_filters(query, session, deps.get_state()[1])
    rows, error = _read(
        "your call log", deps.store.list_calls, filters["keys"],
        since=filters["since"], until=filters["until"],
        outcome=filters["outcome"], has_message=filters["has_message"],
        include_test=filters["show_test"], q=filters["q"] or None,
        # One extra row answers "is there another page" without a count query.
        limit=PAGE_SIZE + 1, offset=(filters["page"] - 1) * PAGE_SIZE)
    rows = list(rows or [])
    has_next = len(rows) > PAGE_SIZE
    rows = rows[:PAGE_SIZE]

    messages, messages_error = {}, ""
    if rows:
        found, messages_error = _read(
            "your messages", deps.store.list_messages, filters["keys"],
            include_test=True, call_sids=[r["call_sid"] for r in rows])
        for message in found or []:
            # Newest first, so the first one seen for a call is the one to show.
            messages.setdefault(message["call_sid"], message)
    names = business_names(deps)
    for row in rows:
        decorate_call(row, messages.get(row["call_sid"]), names)

    # "No calls yet — ring your number to test it" is the wrong thing to say to
    # a line whose only calls ARE tests with the box unticked. One extra
    # bounded read settles it, and only ever on a page that came back empty.
    empty_start = (not rows and not filters["any"] and not error
                   and filters["page"] == 1)
    only_tests, probe_error = False, ""
    if empty_start and not filters["show_test"]:
        probe, probe_error = _read("your call log", deps.store.list_calls,
                                   filters["keys"], include_test=True, limit=1)
        only_tests = bool(probe)
    return {"filters": filters, "rows": rows,
            # A probe that could not run must not leave the page saying "no
            # calls yet — ring your number to test it" as though that were a
            # fact somebody checked.
            "error": error or probe_error,
            "messages_error": messages_error, "has_next": has_next,
            "only_tests": only_tests,
            "first_run": (empty_start and not only_tests and not probe_error)}


def owner_numbers(deps, session) -> list:
    """The phone numbers this owner's businesses answer on."""
    numbers, _profiles = deps.get_state()
    known = set(session.profile_keys)
    return [number for number, key in numbers.items() if key in known]


def _list_context(deps, session, data: dict) -> dict:
    filters = data["filters"]
    return {
        "numbers": owner_numbers(deps, session),
        "rows": data["rows"], "error": data["error"],
        "messages_error": data["messages_error"], "filters": filters,
        "has_next": data["has_next"], "first_run": data["first_run"],
        "only_tests": data["only_tests"],
        "next_query": filter_query(filters, page=filters["page"] + 1),
        "prev_query": filter_query(filters, page=filters["page"] - 1)
        if filters["page"] > 2 else filter_query(filters),
        "first_row": (filters["page"] - 1) * PAGE_SIZE + 1,
        "last_row": (filters["page"] - 1) * PAGE_SIZE + len(data["rows"]),
        "many_businesses": len(session.profile_keys) > 1,
    }


def _page_context(deps, session) -> dict:
    """The half of the Calls page htmx never redraws: the filter controls and
    the sentence about how long words are kept."""
    _numbers, profiles = deps.get_state()
    return {
        "businesses": [(key, str(profiles.get(key, {}).get("business_name", "")).strip()
                        or key) for key in session.profile_keys],
        "outcomes": [(key, OUTCOME_WORDS[key][0]) for key in OUTCOME_ORDER],
        "retention": retention_days(deps, session),
    }


async def calls(request: web.Request) -> web.Response:
    """The call log. An htmx request gets only the list, so changing a filter
    redraws the results and leaves the rest of the page where it was."""
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    data = await asyncio.to_thread(gather_calls, deps, session, request.query)
    context = _list_context(deps, session, data)
    if request.headers.get("HX-Request"):
        return render.partial(request, deps, "_calls_list.html",
                              session=session, **context)
    # The receipt a delete left for exactly one page load, if this is it.
    deleted = (render.pop_flash(request, session)
               if request.query.get("deleted") else None)
    return await render.page(request, deps, "calls.html", session=session,
                             deleted=deleted, **_page_context(deps, session),
                             **context)


# --------------------------------------------------------- one call in full --

def _turn_role(role: str) -> str:
    return role if role in ("caller", "agent", "keypress") else "caller"


def gather_call(deps, session, call_sid: str) -> dict:
    """One call, its message, and the note a call that left nothing still has.

    Returns `{"refused": sentence}` when the store would not answer, and
    `{"missing": True}` both for a call that does not exist and for one that
    belongs to another business — the same answer, so neither confirms the
    other.
    """
    call, error = _read("this call", deps.store.get_call, call_sid)
    if error:
        return {"refused": error}
    if call is None or str(call.get("profile_key") or "") not in set(
            session.profile_keys):
        return {"missing": True}

    keys = (call["profile_key"],)
    found, messages_error = _read("this call's message", deps.store.list_messages,
                                  keys, include_test=True, call_sids=[call_sid])
    message = (found or [None])[0] if found else None
    events, events_error = _read("what this call left behind",
                                 deps.store.list_events, keys,
                                 call_sid=call_sid, limit=20)
    no_info_note = next((str(e["detail"] or "") for e in events or []
                         if e["kind"] == "no_info_note"), "")

    names = business_names(deps)
    decorate_call(call, message, names)
    for turn in call["turns"]:
        turn["role"] = _turn_role(turn["role"])
    try:
        flags = list(json.loads(call.get("overpromise_flags") or "[]"))
    except (TypeError, ValueError):
        flags = []

    brains, _active = deps.get_brains()
    brain = brains.get(str(call.get("brain") or ""))
    notify_label, notify_tone = NOTIFY_WORDS.get(
        str(call.get("notify_status") or ""), ("", "ghost"))
    return {
        "call": call, "message": message, "messages_error": messages_error,
        "no_info_note": no_info_note, "events_error": events_error,
        "overpromise": flags,
        "brain_label": (brain.label.strip() or call["brain"]) if brain
        else str(call.get("model") or ""),
        "brain_runs": status.runs_where(brain) if brain else "",
        "brain_gone": brain is None,
        "notify_label": notify_label, "notify_tone": notify_tone,
    }


async def _not_found(request, deps, session) -> web.Response:
    """The same answer for a call that never existed and one that is not
    theirs. Anything else would let a stranger enumerate the line's calls."""
    return await render.page(
        request, deps, "refused.html", session=session, status=404,
        reason=("That call is not on your line. It may have been deleted, or "
                "aged out of your records."))


async def call_detail(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    call_sid = request.match_info["sid"]
    data = await asyncio.to_thread(gather_call, deps, session, call_sid)
    if data.get("refused"):
        return await render.page(request, deps, "refused.html", session=session,
                           status=503, reason=data["refused"])
    if data.get("missing"):
        return await _not_found(request, deps, session)
    return await render.page(
        request, deps, "call_detail.html", session=session,
        saved=str(request.query.get("saved", "")), delete_error="",
        note_max=NOTE_MAX_CHARS,
        deleting=request.query.get("delete") == "1", **data)


# ---------------------------------------------------- actions on one call ----

async def _call_in_scope(deps, session, call_sid: str):
    """The call, or None when it is not this owner's. Never says which."""
    call, error = await asyncio.to_thread(_read, "this call",
                                          deps.store.get_call, call_sid)
    if error:
        raise RuntimeError(error)
    if call is None or str(call.get("profile_key") or "") not in set(
            session.profile_keys):
        return None
    return call


async def _message_of(deps, call):
    found = await asyncio.to_thread(deps.store.list_messages,
                                    (call["profile_key"],), include_test=True,
                                    call_sids=[call["call_sid"]])
    return found[0] if found else None


async def _guard(request, deps, session):
    """The CSRF check every mutating form goes through. Returns a refusal page
    or None."""
    form = await request.post()
    reason = deps.auth.check_csrf(request, session, form)
    if reason:
        return form, await render.page(request, deps, "refused.html", session=session,
                                 status=403, reason=reason)
    return form, None


async def mark_handled(request: web.Request) -> web.Response:
    """"I have dealt with this" — the message this call left is finished."""
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    _form, refused = await _guard(request, deps, session)
    if refused is not None:
        return refused
    call_sid = request.match_info["sid"]
    call = await _call_in_scope(deps, session, call_sid)
    if call is None:
        return await _not_found(request, deps, session)
    message = await _message_of(deps, call)
    if message is None:
        return await render.page(
            request, deps, "refused.html", session=session, status=400,
            reason=("This call did not leave a message, so there is nothing to "
                    "mark as handled."))
    await asyncio.to_thread(deps.store.set_message_status, message["id"], "done")
    log.info("dashboard: %s marked the message on %s handled",
             session.owner_key, call_sid)
    raise web.HTTPSeeOther(f"/calls/{call_sid}?saved=handled")


async def add_note(request: web.Request) -> web.Response:
    """The owner's own words, kept with the message this call left.

    A note is not caller speech, so the retention purge leaves it alone: what
    the owner wrote about a job outlives the transcript of the call it came
    from.
    """
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    form, refused = await _guard(request, deps, session)
    if refused is not None:
        return refused
    call_sid = request.match_info["sid"]
    call = await _call_in_scope(deps, session, call_sid)
    if call is None:
        return await _not_found(request, deps, session)
    message = await _message_of(deps, call)
    if message is None:
        return await render.page(
            request, deps, "refused.html", session=session, status=400,
            reason=("Notes are kept with the message a call leaves, and this "
                    "call did not leave one."))
    typed = str(form.get("note", ""))
    # A note longer than the box holds used to be cut off in silence, so the
    # owner's last two sentences were simply gone and nothing said so. It is
    # still cut — the store's column is not a document — but the page says it
    # happened, with the number, so the rest can be written down somewhere else.
    cut = len(typed) > NOTE_MAX_CHARS
    await asyncio.to_thread(deps.store.set_message_status, message["id"],
                            message["status"], typed[:NOTE_MAX_CHARS])
    if cut:
        log.warning("dashboard: %s wrote a note of %d characters on %s; the "
                    "last %d were not kept", session.owner_key, len(typed),
                    call_sid, len(typed) - NOTE_MAX_CHARS)
    raise web.HTTPSeeOther(
        f"/calls/{call_sid}?saved={'note_cut' if cut else 'note'}")


# ------------------------------------------------------- deleting a caller ---

def caller_calls(deps, session, number: str) -> tuple:
    """(this owner's calls from one number, whether the scan hit its ceiling).

    Used to answer "do you have any of these at all" and to tag the event with
    the business they belong to. It is deliberately NOT the safety check: the
    store decides whether a delete is inside this login's businesses, because a
    call row whose business was removed from the config is invisible to
    anything that enumerates the config — and that is precisely the row a
    scoped delete must not take.
    """
    number = str(number or "").strip()
    rows = deps.store.list_calls(session.profile_keys, q=number,
                                 include_test=True, limit=SCAN_LIMIT)
    return ([row for row in rows if str(row["from_number"]) == number],
            len(rows) >= SCAN_LIMIT)


# Why a delete did not happen, and the answer each reason earns. A key, not a
# sentence: matching on the words of a message is how a rewording quietly turns
# a 403 into a 400.
REFUSAL_STATUS = {"not_yours": 403, "unknown": 400}


def _delete_caller(deps, session, number: str) -> dict:
    """The whole delete, in one blocking call: check, remove, write it down.

    Returns `{"reason": key, "text": sentence}` when nothing was deleted, or
    the receipt when something was.
    """
    mine, truncated = caller_calls(deps, session, number)
    if not mine:
        return {"reason": "unknown",
                "text": ("No calls from that number are on your line. Type it "
                         "exactly as it appears on the call, including the "
                         "country code.")}
    profiles = {row["profile_key"] for row in mine}
    # None means the whole line — the account that owns every business on it.
    scope = None if session.sees_whole_line else session.profile_keys
    try:
        removed = deps.store.delete_caller(number, profile_keys=scope)
    except PermissionError as refusal:
        # The store counted the other businesses and named no key; neither do
        # we. Nothing was deleted.
        log.warning("dashboard: %s tried to delete a caller who has also rung "
                    "another business on this line", session.owner_key)
        said = str(refusal)
        return {"reason": "not_yours",
                "text": (said[0].upper() + said[1:] + ", so deleting its "
                         "records is not yours to do. Ask whoever manages the "
                         "whole line.")}
    try:
        # The kind and the counts, never the number: this row outlives the
        # delete, and a "deleted this caller" event naming them would be the
        # record the owner just asked us to destroy.
        deps.store.add_event(
            # None whenever the scan stopped at its ceiling: the businesses it
            # saw are then only the ones it got to, and an event filed against
            # ONE of them would be a scoped owner's evidence that the delete
            # touched only theirs — which is exactly what nobody knows.
            profiles.pop() if len(profiles) == 1 and not truncated else None,
            None, "warning", "caller_deleted",
            f"{session.owner_key} deleted every record of one caller: "
            f"{int(removed)} rows across {len(removed.call_sids)} calls")
    except Exception:
        log.exception("call store: could not record the caller deletion")
    log.warning("dashboard: %s deleted %d rows for one caller (%d calls)",
                session.owner_key, int(removed), len(removed.call_sids))
    return {"reason": "", "rows": int(removed),
            "call_sids": list(removed.call_sids)}


async def delete_caller(request: web.Request) -> web.Response:
    """Erase every record of one caller — the "delete my data" request.

    The owner types the number back, exactly, because there is no undo: the
    calls, the words, the messages and the alert history all go. That
    confirmation is MANDATORY, so this always starts from the call it was asked
    from: no call, or a call that is not theirs, and there is nothing to
    confirm the number against — which is a 404, the same answer as a call that
    never existed.
    """
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    form, refused = await _guard(request, deps, session)
    if refused is not None:
        return refused
    typed = str(form.get("number", "")).strip()
    call_sid = str(form.get("call_sid", "")).strip()
    call = await _call_in_scope(deps, session, call_sid) if call_sid else None
    if call is None:
        return await _not_found(request, deps, session)

    if typed != str(call["from_number"]):
        return await _refused_delete(
            request, deps, session, call_sid, 400,
            "The number you typed does not match this caller. Type it exactly "
            "as it appears above, including the country code.")

    result = await asyncio.to_thread(_delete_caller, deps, session, typed)
    if result["reason"]:
        return await _refused_delete(request, deps, session, call_sid,
                                     REFUSAL_STATUS[result["reason"]],
                                     result["text"])

    # Redirect, don't render: a receipt rendered straight onto the POST comes
    # back when the owner refreshes, and "refresh re-runs the delete" is not
    # something to leave in a product. The receipt waits one page for them.
    render.set_flash(request, session, result)
    raise web.HTTPSeeOther("/calls?deleted=1")


async def _refused_delete(request, deps, session, call_sid: str,
                          status_code: int, sentence: str) -> web.Response:
    """The call's own page again, with the delete box open and the reason in
    it. Nothing was deleted."""
    data = await asyncio.to_thread(gather_call, deps, session, call_sid)
    if data.get("missing") or data.get("refused"):
        return await _not_found(request, deps, session)
    return await render.page(request, deps, "call_detail.html", session=session,
                             status=status_code, saved="", deleting=True,
                             note_max=NOTE_MAX_CHARS,
                             delete_error=sentence, **data)

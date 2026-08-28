"""The message inbox: what a caller wanted, and what the owner did about it.

This is the screen the phone line exists for. Three rules:

  * **A message is work, so it has a state.** New, in progress, done — changed
    from the list without opening anything, and the change is a real write the
    next page load agrees with.
  * **Every action is the real action.** Call back is a `tel:` link with the
    whole number, because the point is that a thumb dials it. Copy puts the
    message on the clipboard. Nothing here is decorative.
  * **The export is a real file.** A header row, one line per message, quoting
    that survives a comma or a quote in a caller's own words, and no cell a
    spreadsheet will run as a formula.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import time

from aiohttp import web

from . import render
from .views_overview import MESSAGE_STATUS_WORDS, _read

log = logging.getLogger("atlas-phone")

STATUSES = ("new", "in_progress", "done")
STATUS_TABS = (("new", "New"), ("in_progress", "In progress"), ("done", "Done"),
               ("", "All"))
# Longer than this and the card clamps the body behind a "Show more" the owner
# opens; nothing is ever cut off, and every word is in the page either way.
CLAMP_CHARS = 240
# What each state can move to, in the owner's words. The button that would put
# a message back where it already is never appears.
NEXT_ACTIONS = {
    "new": (("in_progress", "Working on it"), ("done", "Done")),
    "in_progress": (("done", "Done"),),
    "done": (("new", "Reopen"),),
}
CSV_COLUMNS = ("When", "Caller", "Call back", "Email", "What they wanted",
               "Status", "Your note", "Business", "Call reference")
# A spreadsheet treats a cell opening with any of these as a formula, and the
# text in these cells is a stranger's own words read down a phone line.
FORMULA_STARTERS = ("=", "+", "-", "@", "\t", "\r")


def decorate_message(message: dict, names: dict) -> dict:
    """One message in the owner's words: what it says, what state it is in."""
    label, tone = MESSAGE_STATUS_WORDS.get(
        message["status"], (str(message["status"]).replace("_", " "), "ghost"))
    message["status_label"], message["status_tone"] = label, tone
    body = str(message.get("need") or message.get("summary") or "").strip()
    message["body"] = body or ("The words of this message have aged out of your "
                               "records. Its caller, time and status are kept.")
    message["clamped"] = len(message["body"]) > CLAMP_CHARS
    message["actions"] = NEXT_ACTIONS.get(message["status"], ())
    message["business"] = names.get(message["profile_key"],
                                    message["profile_key"])
    who = str(message.get("caller_name") or "").strip()
    message["who"] = who or "Name not given"
    message["initials"] = "".join(
        part[0].upper() for part in who.split()[:2]) or "?"
    message["dial"] = str(message.get("callback")
                          or message.get("from_number") or "").strip()
    return message


def gather_messages(deps, session, wanted: str) -> dict:
    """The owner's messages, newest first, in one read."""
    from . import views_calls          # for the business names, one source only

    chosen = wanted if wanted in STATUSES else None
    rows, error = _read("your messages", deps.store.list_messages,
                        session.profile_keys, status=chosen)
    names = views_calls.business_names(deps)
    for message in rows or []:
        decorate_message(message, names)
    # `chosen`, never `status`: render.page() takes `status` for the HTTP code.
    return {"messages": rows or [], "error": error, "chosen": chosen or "",
            "wanted": wanted}


async def messages(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    wanted = str(request.query.get("status", "")).strip()
    data = await asyncio.to_thread(gather_messages, deps, session, wanted)
    unknown = bool(wanted) and wanted not in STATUSES
    return render.page(
        request, deps, "messages.html", session=session, tabs=STATUS_TABS,
        many_businesses=len(session.profile_keys) > 1,
        unknown_status=unknown, **data)


def _message_in_scope(deps, session, message_id: int):
    """One message this owner owns, or None.

    There is no read-one-message-by-id in the store, and adding one that did
    not take the owner's businesses would be a hole. This asks the scoped
    query — the same one the list uses — and picks the row out of it.
    """
    for message in deps.store.list_messages(session.profile_keys,
                                            include_test=True):
        if int(message["id"]) == int(message_id):
            return message
    return None


def _set_status(deps, session, message_id: int, wanted: str):
    """(the card, how many are still waiting), or (None, 0) when it is not
    theirs. One blocking call: these are SQLite reads on the loop that carries
    live calls."""
    message = _message_in_scope(deps, session, message_id)
    if message is None:
        return None, 0
    deps.store.set_message_status(message["id"], wanted)
    updated = _message_in_scope(deps, session, message_id)
    from . import views_calls
    card = decorate_message(updated, views_calls.business_names(deps))
    return card, render.waiting_badge(deps, session)()


async def message_status(request: web.Request) -> web.Response:
    """Move one message along. htmx gets the card back; a browser without it
    gets the list it came from."""
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    form = await request.post()
    reason = deps.auth.check_csrf(request, session, form)
    if reason:
        return render.page(request, deps, "refused.html", session=session,
                           status=403, reason=reason)
    wanted = str(form.get("status", "")).strip()
    if wanted not in STATUSES:
        return render.page(
            request, deps, "refused.html", session=session, status=400,
            reason=("That is not a state a message can be in, so nothing was "
                    "changed. Reload the page and try again."))
    try:
        message_id = int(request.match_info["id"])
    except ValueError:
        message_id = -1
    updated, waiting = await asyncio.to_thread(_set_status, deps, session,
                                               message_id, wanted)
    if updated is None:
        # Not theirs, or gone. The same answer either way.
        return render.page(
            request, deps, "refused.html", session=session, status=404,
            reason=("That message is not on your line. It may have been "
                    "deleted, or aged out of your records."))
    log.info("dashboard: %s moved a message to %s", session.owner_key, wanted)
    if request.headers.get("HX-Request"):
        # The card, plus the navigation's waiting count swapped out of band: a
        # badge still reading "2" beside the message just moved off the list is
        # the screen contradicting itself.
        return render.partial(request, deps, "_message_card.html",
                              session=session, message=updated,
                              many_businesses=len(session.profile_keys) > 1,
                              oob_waiting=waiting,
                              back=str(form.get("back", "/messages")))
    back = str(form.get("back", "")).strip()
    raise web.HTTPSeeOther(back if back.startswith("/messages") else "/messages")


# ------------------------------------------------------------------- csv ----

def _cell(value) -> str:
    """One cell, safe to open in a spreadsheet.

    A caller's words go into this file and somebody opens it in Excel, where a
    cell starting `=` is a formula that runs. The leading quote is what stops
    that; every character the caller said is still in the file.
    """
    text = "" if value is None else str(value)
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    if text.startswith(FORMULA_STARTERS):
        return "'" + text
    return text


def messages_csv_text(rows, names: dict) -> str:
    """The export, as RFC 4180 text: quotes doubled, commas kept, CRLF rows."""
    out = io.StringIO()
    writer = csv.writer(out, dialect="excel", quoting=csv.QUOTE_MINIMAL,
                        lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for message in rows:
        label, _tone = MESSAGE_STATUS_WORDS.get(
            message["status"], (str(message["status"]).replace("_", " "), ""))
        writer.writerow([
            _cell(time.strftime("%Y-%m-%d %H:%M",
                                time.localtime(float(message["created_at"])))),
            _cell(message.get("caller_name") or "Name not given"),
            _cell(message.get("callback") or message.get("from_number")),
            _cell(message.get("email")),
            _cell(message.get("need") or message.get("summary")),
            _cell(label),
            _cell(message.get("note")),
            _cell(names.get(message["profile_key"], message["profile_key"])),
            _cell(message["call_sid"]),
        ])
    return out.getvalue()


async def messages_csv(request: web.Request) -> web.Response:
    """The messages on screen, as a file. Scoped like every other read, and
    filtered by the same status tab the owner is looking at."""
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    wanted = str(request.query.get("status", "")).strip()
    status = wanted if wanted in STATUSES else None
    rows = await asyncio.to_thread(deps.store.list_messages,
                                   session.profile_keys, status)
    from . import views_calls
    body = messages_csv_text(rows, views_calls.business_names(deps))
    stamp = time.strftime("%Y-%m-%d")
    log.info("dashboard: %s exported %d message(s)", session.owner_key,
             len(rows))
    return web.Response(
        # The byte-order mark is here on purpose: without it Excel on Windows
        # reads a UTF-8 file as Windows-1252 and turns an accented name into
        # mojibake. Every other spreadsheet skips it.
        body=("﻿" + body).encode("utf-8"),
        content_type="text/csv", charset="utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="messages-{stamp}.csv"'})

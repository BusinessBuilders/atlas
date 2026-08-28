"""What changed on this line, who changed it, and how to put it back.

After an incident — "the agent started telling callers the wrong hours" — the
old dashboard could not say when the change was made, by whom, or what it was.
There was one log line, in a journal that had already been vacuumed. This
screen answers all three:

  * **every settings change**, as a sentence, with the exact lines that changed
    on expand, and a button that puts the previous version back through the
    same fail-closed validation as any other save;
  * **every sign-in**, including the failures and the lockouts, which is how an
    owner finds out somebody was guessing at their dashboard last week;
  * **what the service itself reported** — a model that stopped answering, a
    clear-out that did not run — in the owner's words rather than the
    service's;
  * **the businesses that were removed**, and the button that brings one back.

Tenancy: a change is shown to an owner of one business only when it TOUCHED one
of their businesses. The check reads the CHANGED lines of the diff, never the
whole text — a stored diff carries every line of both versions, so "does this
mention my business" would be true of every change ever made.
"""
from __future__ import annotations

import asyncio
import logging
import re
import tomllib
from datetime import datetime

from aiohttp import web

from . import config_edit as edit
from . import render
from .views_overview import alert_words

log = logging.getLogger("atlas-phone")

CHANGES_READ = 200
CHANGES_SHOWN = 50
EVENTS_SHOWN = 25
SIGN_IN_KINDS = ("dashboard_signin", "dashboard_signin_failed",
                 "dashboard_signin_locked")
# Around a changed line, so the diff on screen is the change and its
# neighbourhood — not the whole config file, which is what the stored diff
# holds so that "put it back" can be exact.
CONTEXT_LINES = 3
_HEADER = re.compile(r"^[ +-]\[(profiles|deleted_profiles)\.([A-Za-z0-9_-]+)\]\s*$")


def _diff_body(diff: str) -> list:
    return [line for line in str(diff).splitlines()
            if not line.startswith(("---", "+++", "@@", "\\"))]


def _walk(diff: str):
    """(the business each line belongs to, the line) — "" outside any profile."""
    current = ""
    for line in _diff_body(diff):
        header = _HEADER.match(line)
        if header:
            current = header.group(2)
            yield current, line
            continue
        if line[1:2] == "[" and line[:1] in " +-":
            current = ""                       # some other table
        yield current, line


def sections_touched(diff: str) -> set:
    """Which businesses this change actually altered."""
    return {key for key, line in _walk(diff) if key and line[:1] in "+-"}


def line_wide(diff: str) -> bool:
    """True when it altered something outside any one business — the numbers,
    the models, the branding, the logins."""
    return any(line[:1] in "+-" for key, line in _walk(diff) if not key)


def visible_diff(diff: str) -> list:
    """The changed lines and a few either side, for the panel that expands."""
    body = _diff_body(diff)
    wanted: set = set()
    for index, line in enumerate(body):
        if line[:1] in "+-":
            wanted.update(range(max(0, index - CONTEXT_LINES),
                                min(len(body), index + CONTEXT_LINES + 1)))
    shown, last = [], None
    for index in sorted(wanted):
        if last is not None and index > last + 1:
            shown.append({"kind": "gap", "text": "…"})
        kind = {"+": "added", "-": "removed"}.get(body[index][:1], "same")
        shown.append({"kind": kind, "text": body[index][1:]})
        last = index
    return shown


def decorate_change(change: dict) -> dict:
    change["lines"] = visible_diff(change.get("diff") or "")
    # Only a change that went through, and that recorded what the file looked
    # like beforehand, can be put back.
    change["can_restore"] = bool(change.get("applied")) and bool(change["lines"])
    change["actor_label"] = str(change.get("actor") or "somebody on this line")
    return change


def changes_for(deps, session) -> tuple:
    """(the changes this login may read, the reason none could be read)."""
    rows, error = render.guarded_read("your settings history",
                                      deps.store.list_config_changes,
                                      CHANGES_READ)
    if error:
        return [], error
    mine = set(session.profile_keys)
    kept = []
    for change in rows or []:
        if not session.sees_whole_line:
            # A diff names other customers' numbers, greetings and push
            # targets. An owner of one business reads only what touched theirs.
            if not (sections_touched(change.get("diff") or "") & mine):
                continue
        kept.append(decorate_change(dict(change)))
        if len(kept) >= CHANGES_SHOWN:
            break
    return kept, ""


def deleted_businesses(deps, days: int) -> list:
    """The businesses that were put away, newest first."""
    config = deps.get_config()
    stamp_key = str(deps.product_defaults.get("deleted_at_key", "deleted_at"))
    now = datetime.now().astimezone()
    listed = []
    for key, profile in (config.deleted_profiles or {}).items():
        try:
            when = datetime.fromisoformat(str(profile.get(stamp_key, "")).strip())
        except ValueError:
            when = None
        age = (now - when).days if when is not None else None
        listed.append({
            "key": key,
            "name": str(profile.get("business_name", "")).strip() or key,
            "at": when.timestamp() if when is not None else None,
            "age_days": age,
            "restorable": age is not None and age < days,
            "window_days": days,
        })
    listed.sort(key=lambda row: row["at"] or 0, reverse=True)
    return listed


def gather(deps, session) -> dict:
    changes, changes_error = changes_for(deps, session)
    events, events_error = render.guarded_read(
        "what happened on your line", deps.store.list_events,
        session.profile_keys, limit=EVENTS_SHOWN * 4,
        include_unscoped=session.sees_whole_line)
    signed = [dict(row, label=alert_words(row["kind"]))
              for row in events or [] if row["kind"] in SIGN_IN_KINDS]
    reported = [dict(row, label=alert_words(row["kind"]))
                for row in events or []
                if row["kind"] not in SIGN_IN_KINDS
                and row["level"] in ("warning", "error")]
    days = int(deps.product_defaults.get("recovery_days", 30))
    removed, removed_error = render.guarded_read("your removed businesses",
                                                 deleted_businesses, deps, days)
    return {
        "changes": changes, "changes_error": changes_error,
        "sign_ins": signed[:EVENTS_SHOWN], "events_error": events_error,
        "service_events": reported[:EVENTS_SHOWN],
        "removed": removed or [], "removed_error": removed_error,
        "recovery_days": days,
        "whole_line": session.sees_whole_line,
    }


async def activity(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    data = await asyncio.to_thread(gather, deps, session)
    return await render.page(request, deps, "activity.html", session=session,
                             flash=render.pop_flash(request, session), **data)


# ------------------------------------------------------------ putting back --

async def _refused(request, deps, session, sentence: str, status: int = 400):
    return await render.page(request, deps, "refused.html", session=session,
                             status=status, reason=sentence)


async def restore(request: web.Request) -> web.Response:
    """Undo one settings change: put the file back the way it was before it.

    Re-validated on the way in like any other save — a version that was fine a
    month ago can name a model that has since been removed, and that has to be
    a refusal with the reason, never a line that stops answering.
    """
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    if not session.sees_whole_line:
        return await _refused(
            request, deps, session,
            "Putting a whole version of the settings back changes every "
            "business on this line, so only the account that manages the whole "
            "line can do it.", 403)
    form = await request.post()
    reason = deps.auth.check_csrf(request, session, form)
    if reason:
        return await _refused(request, deps, session, reason, 403)
    try:
        change_id = int(str(form.get("change_id", "")).strip())
    except ValueError:
        return await _refused(request, deps, session,
                              "That is not a settings change on this line.", 400)
    error = await asyncio.to_thread(_restore_change, deps, session, change_id)
    render.set_flash(
        request, session,
        f"Nothing was changed. {error}" if error
        else "Your settings were put back — live on the next call.")
    raise web.HTTPSeeOther("/activity")


def _restore_change(deps, session, change_id: int):
    rows = deps.store.list_config_changes(CHANGES_READ)
    change = next((row for row in rows if int(row["id"]) == change_id), None)
    if change is None:
        return ("That settings change is no longer in your history, so there is "
                "nothing to put back.")
    text = deps.config_from_diff(change.get("diff") or "", side="before")
    if not text.strip():
        return ("That change did not record what the settings looked like "
                "beforehand, so there is nothing to put back.")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return f"that version of the settings can no longer be read ({e})."
    try:
        config = deps.parse_config(data)
    except (ValueError, KeyError) as e:
        return f"that version is no longer valid: {e}"
    return deps.apply_config(
        config, session.owner_key,
        f"Put the settings back to before: {change['summary']}")


async def restore_business(request: web.Request) -> web.Response:
    """Bring one removed business back, with the settings it had that day."""
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    form = await request.post()
    reason = deps.auth.check_csrf(request, session, form)
    if reason:
        return await _refused(request, deps, session, reason, 403)
    key = str(form.get("business", "")).strip()
    error = await asyncio.to_thread(_restore_business, deps, session, key)
    render.set_flash(
        request, session,
        f"Nothing was changed. {error}" if error
        else "That business is back. No phone number answers for it yet — set "
             "one on the Numbers screen.")
    raise web.HTTPSeeOther("/activity")


def _restore_business(deps, session, key: str):
    if not session.sees_whole_line:
        # A scoped login's businesses come from the LIVE config, so a removed
        # one is never among them: there is no scope that could allow this.
        return ("Only the account that manages the whole line can bring a "
                "removed business back.")
    config = deps.get_config()
    removed = dict(config.deleted_profiles or {})
    if key not in removed:
        return "That business is not in your removed list."
    days = int(deps.product_defaults.get("recovery_days", 30))
    stamp_key = str(deps.product_defaults.get("deleted_at_key", "deleted_at"))
    try:
        age = (datetime.now().astimezone()
               - datetime.fromisoformat(str(removed[key].get(stamp_key, "")))).days
    except ValueError:
        age = None
    if age is None or age >= days:
        return (f"That business was removed more than {days} days ago, which is "
                "past the window this screen can bring it back from.")
    profile = {name: value for name, value in removed.pop(key).items()
               if name != stamp_key}
    profiles = dict(config.profiles)
    profiles[key] = profile
    name = str(profile.get("business_name", "")).strip() or key
    return edit.save(deps, session, profiles=profiles,
                     deleted_profiles=removed,
                     summary=f"Brought the business {name} back")

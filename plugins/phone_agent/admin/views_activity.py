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
import dataclasses
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


# What is said in place of the lines a scoped owner may not read. The change is
# on their screen because it touched one of THEIR businesses; this says plainly
# that the same save did other things, without saying what or to whom.
OTHER_BUSINESSES = "…other businesses on this line changed in the same save"
LINE_WIDE = "…settings shared by the whole line changed in the same save"


def visible_diff(diff: str, keys=None) -> list:
    """The changed lines and a few either side, for the panel that expands.

    `keys` is None for an owner of the whole line: they see every line. For an
    owner of one business it is their profile keys, and every line belonging to
    anybody else — another business, or a table that belongs to the line rather
    than to any business — is dropped BEFORE the context window is worked out.

    That order matters and is the whole fix: filtering afterwards would still
    pull a neighbour's `ntfy_topic` onto the screen as three lines of "context"
    around a change of their own. The stored diff carries every line of both
    versions so a restore can be exact, which means a first save on a
    hand-written config rewrites the entire file — and without this, one
    business's owner read the whole line's settings.
    """
    walked = list(_walk(diff))
    if keys is None:
        body, elsewhere, others = [line for _key, line in walked], False, False
    else:
        allowed = set(keys)
        body = [line for key, line in walked if key in allowed]
        others = any(line[:1] in "+-" and key and key not in allowed
                     for key, line in walked)
        elsewhere = any(line[:1] in "+-" and not key for key, line in walked)

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
    if others:
        shown.append({"kind": "gap", "text": OTHER_BUSINESSES})
    if elsewhere:
        shown.append({"kind": "gap", "text": LINE_WIDE})
    return shown


def decorate_change(change: dict, keys=None) -> dict:
    diff = change.get("diff") or ""
    change["lines"] = visible_diff(diff, keys)
    # Read off the WHOLE diff, never the filtered view: whether a version can
    # be put back is a fact about the change, not about who is looking at it.
    change["can_restore"] = bool(change.get("applied")) and bool(_diff_body(diff))
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
        kept.append(decorate_change(
            dict(change),
            None if session.sees_whole_line else session.profile_keys))
        if len(kept) >= CHANGES_SHOWN:
            break
    return kept, ""


def deleted_businesses(deps, days: int) -> list:
    """The businesses that were put away, newest first."""
    config = deps.get_config()
    stamp_key = str(deps.product_defaults.get("deleted_at_key", "deleted_at"))
    owners_key = str(deps.product_defaults.get("deleted_owners_key", "owners"))
    now = datetime.now().astimezone()
    listed = []
    for key, profile in (config.deleted_profiles or {}).items():
        try:
            when = datetime.fromisoformat(str(profile.get(stamp_key, "")).strip())
        except ValueError:
            when = None
        # Clamped at nought: a `deleted_at` in the future (a clock that was
        # wrong, a hand-edited file) would otherwise come out negative and read
        # as "31 days left" on a thirty-day window.
        age = max(0, (now - when).days) if when is not None else None
        listed.append({
            "key": key,
            "name": str(profile.get("business_name", "")).strip() or key,
            "at": when.timestamp() if when is not None else None,
            "age_days": age,
            "restorable": age is not None and age < days,
            "window_days": days,
            # The sign-ins that get it back, named on the confirm.
            "owners": [str(name) for name in profile.get(owners_key, [])],
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


def _confirming(data: dict, query) -> dict:
    """What a confirm dialog is asking about, resolved against the rows that
    are really on this page — so the URL cannot put a summary, a date or a
    business name of its own in front of the owner."""
    wanted = str(query.get("restore", "")).strip()
    change = next((c for c in data["changes"]
                   if str(c["id"]) == wanted and c["can_restore"]), None)
    business = str(query.get("restore-business", "")).strip()
    removed = next((row for row in data["removed"]
                    if row["key"] == business and row["restorable"]), None)
    return {"confirming": change, "confirming_business": removed,
            "dialog_open": change is not None or removed is not None}


def _note(flash):
    """The receipt a redirect left, as {text, ok}. A refusal is not styled like
    a success — "Nothing was changed" in the colour of a done job is the screen
    lying about what happened."""
    if isinstance(flash, dict):
        return flash
    return {"text": str(flash), "ok": True} if flash else None


async def activity(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    data = await asyncio.to_thread(gather, deps, session)
    if not session.sees_whole_line:
        # Neither restore is theirs to start, so neither dialog is theirs to open.
        confirm = {"confirming": None, "confirming_business": None,
                   "dialog_open": False}
    else:
        confirm = _confirming(data, request.query)
    return await render.page(request, deps, "activity.html", session=session,
                             note=_note(render.pop_flash(request, session)),
                             **confirm, **data)


# ------------------------------------------------------------ putting back --

# Both restores are confirmed in a dialog first. The server checks it as well
# as drawing it: a POST that arrives without it — a stale tab, a form somebody
# rebuilt — is refused rather than quietly carried out.
UNCONFIRMED = ("That change was not confirmed, so nothing was put back. Open "
               "Activity and use the button on the version you want.")


def _confirmed(form) -> bool:
    return str(form.get("confirm", "")).strip().lower() in ("on", "1", "true",
                                                            "yes")


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
    if not _confirmed(form):
        return await _refused(request, deps, session, UNCONFIRMED, 400)
    try:
        change_id = int(str(form.get("change_id", "")).strip())
    except ValueError:
        return await _refused(request, deps, session,
                              "That is not a settings change on this line.", 400)
    error = await asyncio.to_thread(_restore_change, deps, session, change_id)
    render.set_flash(request, session, {
        "ok": not error,
        "text": (f"Nothing was changed. {error}" if error
                 else "Your settings were put back — live on the next call.")})
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
    if not _confirmed(form):
        return await _refused(request, deps, session, UNCONFIRMED, 400)
    key = str(form.get("business", "")).strip()
    error, given = await asyncio.to_thread(_restore_business, deps, session, key)
    back = "That business is back. No phone number answers for it yet — set one on the Numbers screen."
    if given:
        back += (" These sign-ins can see it again: " + ", ".join(given) + ".")
    render.set_flash(request, session, {
        "ok": not error,
        "text": f"Nothing was changed. {error}" if error else back})
    raise web.HTTPSeeOther("/activity")


def _restore_business(deps, session, key: str):
    """(the refusal, or ""), and the logins that got it back."""
    if not session.sees_whole_line:
        # A scoped login's businesses come from the LIVE config, so a removed
        # one is never among them: there is no scope that could allow this.
        return ("Only the account that manages the whole line can bring a "
                "removed business back."), []
    config = deps.get_config()
    removed = dict(config.deleted_profiles or {})
    if key not in removed:
        return "That business is not in your removed list.", []
    days = int(deps.product_defaults.get("recovery_days", 30))
    stamp_key = str(deps.product_defaults.get("deleted_at_key", "deleted_at"))
    owners_key = str(deps.product_defaults.get("deleted_owners_key", "owners"))
    try:
        age = (datetime.now().astimezone()
               - datetime.fromisoformat(str(removed[key].get(stamp_key, "")))).days
    except ValueError:
        age = None
    if age is None or age >= days:
        return (f"That business was removed more than {days} days ago, which is "
                "past the window this screen can bring it back from."), []
    put_away = removed.pop(key)
    profile = {name: value for name, value in put_away.items()
               if name not in (stamp_key, owners_key)}
    profiles = dict(config.profiles)
    profiles[key] = profile
    # The sign-ins that could see it the day it went get it back. Any that have
    # since been taken out of the config are simply not there to give it to.
    wanted = [str(name) for name in put_away.get(owners_key, [])]
    owners = dict(config.owners)
    given = []
    for name in wanted:
        owner = owners.get(name)
        if owner is None or key in list(owner.profiles):
            continue
        owners[name] = dataclasses.replace(owner,
                                           profiles=list(owner.profiles) + [key])
        given.append(name)
    name = str(profile.get("business_name", "")).strip() or key
    refusal = edit.save(deps, session, profiles=profiles, owners=owners,
                        deleted_profiles=removed,
                        summary=f"Brought the business {name} back")
    return (refusal or ""), ([] if refusal else given)

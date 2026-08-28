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
# A table header, and any table header at all. Both allow leading whitespace,
# because TOML does: an indented `[profiles.x]` this did not recognise would
# leave the walker attributing that business's lines to the PREVIOUS one, which
# on a shared line is a leak rather than a cosmetic miss.
_HEADER = re.compile(
    r"^[ +-]\s*\[(profiles|deleted_profiles)\.([A-Za-z0-9_-]+)\]\s*$")
_ANY_TABLE = re.compile(r"^[ +-]\s*\[")
# TOML's multi-line string fence. A line inside one is text somebody wrote, not
# a table header, however much it looks like one.
_FENCE = '"' * 3


def _walk(diff: str):
    """(the business each line belongs to, the line) — "" outside any profile.

    This is a tenancy control, not a formatting nicety: `visible_diff` drops
    every line it cannot attribute to the reader's own businesses, so anything
    mis-attributed here is one business's settings shown to another. It is
    written to fail CLOSED — a line it is unsure about belongs to no business,
    and a scoped reader does not see it.

    Three things it has to get right, in the order they bite:

      * **A hunk boundary resets the table.** `@@` means the next line comes
        from somewhere else in the file entirely, so a hunk starting in the
        middle of a table belongs to no known one until a header says
        otherwise. `config_diff` emits unlimited context and therefore a single
        hunk today, but that is an invariant of one function — carrying the
        current table across `@@` would silently become a leak the day
        anything shortened it.
      * **A header inside a multi-line string is not a header.** A triple-quoted
        TOML value can hold a line reading exactly like a profile header. The
        two sides of a diff are two different files, so the fence state is
        tracked for each: a removed line is read against the old file's state,
        an added one against the new file's, and a context line counts as
        inside a string if EITHER thinks so — the direction that hides rather
        than reveals.
      * **Any other table ends the current one**, indented or not.
    """
    current = ""
    in_old = in_new = False
    for line in str(diff).splitlines():
        if line.startswith(("---", "+++", "\\")):
            continue
        if line.startswith("@@"):
            current, in_old, in_new = "", False, False
            continue
        mark, text = line[:1], line[1:]
        inside = (in_old or in_new) if mark == " " else (
            in_old if mark == "-" else in_new)
        if text.count(_FENCE) % 2:
            if mark in " -":
                in_old = not in_old
            if mark in " +":
                in_new = not in_new
        if not inside:
            header = _HEADER.match(line)
            if header:
                current = header.group(2)
                yield current, line
                continue
            if _ANY_TABLE.match(line):
                current = ""                   # some other table
        yield current, line


def _diff_body(diff: str) -> list:
    """Every content line of a diff, hunk and file headers dropped."""
    return [line for _key, line in _walk(diff)]


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


def _named(names: list) -> str:
    """"Acme Co", "Acme Co and Riverside", "Acme Co, Riverside and Third"."""
    listed = list(names)
    if len(listed) <= 1:
        return listed[0] if listed else ""
    return ", ".join(listed[:-1]) + " and " + listed[-1]


def scoped_summary(deps, diff: str, keys) -> str:
    """What this change did TO THIS OWNER'S businesses, in the owner's words.

    The stored summary is written for whoever made the change and describes the
    whole save: "Removed the business Other Co" is the truth, and it is not
    this reader's truth to be told. So a scoped reader gets a sentence built
    from the same filtered lines their diff is built from — never the stored
    one — and the names come from the live config, not from the diff.
    """
    _numbers, profiles = deps.get_state()
    mine = set(keys)
    touched = sorted(sections_touched(diff) & mine)
    names = [str((profiles.get(key) or {}).get("business_name", "")).strip()
             or key for key in touched]
    if names:
        sentence = f"Settings changed for {_named(names)}"
    else:
        # It is on their screen because it touched one of theirs; if nothing
        # names one now, say only that something on the line changed.
        sentence = "Settings on this line changed"
    if line_wide(diff):
        sentence += ", and settings shared by the whole line"
    return sentence


def decorate_change(deps, change: dict, session=None) -> dict:
    """One change as the reader in front of it may see it.

    `session` is None for an owner of the whole line: they get the change
    exactly as it was recorded. For anybody else every field is rebuilt from
    the part of the diff that is theirs — the lines, the sentence, who did it,
    and why it was refused — because each of those was written about the whole
    save and each of them can name a business next door.
    """
    diff = change.get("diff") or ""
    scoped = session is not None and not session.sees_whole_line
    keys = tuple(session.profile_keys) if scoped else None
    change["lines"] = visible_diff(diff, keys)
    # Read off the WHOLE diff, never the filtered view: whether a version can
    # be put back is a fact about the change, not about who is looking at it.
    change["can_restore"] = bool(change.get("applied")) and bool(_diff_body(diff))
    actor = str(change.get("actor") or "")
    if not scoped:
        change["actor_label"] = actor or "somebody on this line"
        return change
    change["summary"] = scoped_summary(deps, diff, keys)
    # A login name is a fact about who else manages this line.
    change["actor_label"] = ("you" if actor and actor == session.owner_key
                             else "somebody who manages this line")
    if change.get("reason") and (
            sections_touched(diff) - set(keys) or line_wide(diff)):
        # The validator names the field it refused, which on a save that also
        # touched another business is that business's field.
        change["reason"] = ""
    # The raw diff is not rendered, but it is the thing being kept from this
    # reader — it does not travel to the template at all.
    change.pop("diff", None)
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
        kept.append(decorate_change(deps, dict(change), session))
        if len(kept) >= CHANGES_SHOWN:
            break
    return kept, ""


def deleted_businesses(deps, days: int, owner_key=None) -> list:
    """The businesses that were put away, newest first.

    `owner_key` is None for an owner of the whole line: they see every one. For
    anybody else only the ones their own sign-in used to cover are listed —
    which is what `owners` was recorded for. A row that does not say who could
    see it is shown to nobody but the line's owner: a business removed by hand,
    or before this was recorded, must not become the one place a neighbour's
    name appears.
    """
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
        covered = [str(name) for name in profile.get(owners_key, [])]
        if owner_key is not None and owner_key not in covered:
            continue
        listed.append({
            "key": key,
            "name": str(profile.get("business_name", "")).strip() or key,
            "at": when.timestamp() if when is not None else None,
            "age_days": age,
            "restorable": age is not None and age < days,
            "window_days": days,
            # The sign-ins that get it back, named on the confirm.
            "owners": covered,
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
    removed, removed_error = render.guarded_read(
        "your removed businesses", deleted_businesses, deps, days,
        None if session.sees_whole_line else session.owner_key)
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

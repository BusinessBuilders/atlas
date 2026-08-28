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
# TOML's two multi-line string fences. Their presence anywhere in a diff means
# a line that looks like a table header might be somebody's prose — see
# `attribution_is_certain`.
_FENCES = ('"' * 3, "'" * 3)

# What a scoped reader is told about a change this module cannot safely take
# apart. It is deliberately dull: the honest content is "something changed, and
# it is not mine to show you".
UNCERTAIN_SUMMARY = ("Settings on this line changed (the line owner can see "
                     "the details)")
UNKNOWN_ACTOR = "somebody who manages this line"


def attribution_is_certain(diff: str) -> bool:
    """Can this diff be split up by business at all?

    False as soon as `\"\"\"` or `'''` appears ANYWHERE in it, on either side or
    in context. Inside a multi-line TOML string a line reading exactly like
    `[profiles.other]` is somebody's prose, and no amount of tracking makes
    that decidable from a diff: the two sides are two different files, a fence
    opened on one side may never close on the other, and one missed header
    means a business's settings are attributed to its neighbour. So this does
    not try. A diff with a fence in it is not split at all — a scoped reader
    gets one dull sentence saying something changed.

    The cost is nothing in practice: `emit_business_toml` escapes newlines and
    only ever writes single-line basic strings, so every diff recorded after
    the first dashboard save is certain. Only a config still carrying a
    hand-written multi-line value can be uncertain, and only until it is saved.
    """
    text = str(diff or "")
    return not any(fence in text for fence in _FENCES)


def _walk(diff: str):
    """(the business each line belongs to, the line) — "" outside any profile.

    A tenancy control, not a formatting nicety: `visible_diff` drops every line
    it cannot attribute to the reader's own businesses, so a line mis-attributed
    here is one business's settings shown to another. Two rules, both failing
    CLOSED — a line it is unsure about belongs to no business, and a scoped
    reader does not see it:

      * **A hunk boundary resets the table.** `@@` means the next line comes
        from somewhere else in the file entirely, so a hunk starting in the
        middle of a table belongs to no known one until a header says
        otherwise. `config_diff` emits unlimited context and therefore a single
        hunk today, but that is an invariant of one function — carrying the
        current table across `@@` would silently become a leak the day
        anything shortened it.
      * **Any other table ends the current one**, indented or not.

    It does NOT try to work out whether a header is really prose inside a
    multi-line string. That question is settled before this runs, for the whole
    diff at once, by `attribution_is_certain` — because a walker that gets it
    wrong gets it wrong in the direction that shows one customer another's
    settings.
    """
    current = ""
    for line in str(diff).splitlines():
        if line.startswith(("---", "+++", "\\")):
            continue
        if line.startswith("@@"):
            current = ""
            continue
        header = _HEADER.match(line)
        if header:
            current = header.group(2)
            yield current, line
            continue
        if _ANY_TABLE.match(line):
            current = ""                       # some other table
        yield current, line


@dataclasses.dataclass(frozen=True)
class Reading:
    """One recorded diff, walked ONCE and asked everything at the same time.

    A row on the Activity screen needs the body, the businesses it touched,
    whether it touched anything shared, and the lines to draw. Working each of
    those out from the raw text meant walking the same diff seven times per
    row; this walks it once.
    """
    certain: bool
    walked: tuple

    @property
    def body(self) -> list:
        return [line for _key, line in self.walked]

    @property
    def touched(self) -> set:
        """The businesses this change altered — EMPTY when the diff cannot be
        split up safely, so nothing downstream can act on a guess."""
        if not self.certain:
            return set()
        return {key for key, line in self.walked if key and line[:1] in "+-"}

    @property
    def touches_shared(self) -> bool:
        """Something outside any one business changed — the numbers, the
        models, the branding, the logins. Only meaningful when `certain`."""
        return any(line[:1] in "+-" for key, line in self.walked if not key)


def read_diff(diff) -> Reading:
    text = str(diff or "")
    return Reading(certain=attribution_is_certain(text),
                   walked=tuple(_walk(text)))


def _diff_body(diff: str) -> list:
    """Every content line of a diff, hunk and file headers dropped."""
    return read_diff(diff).body


def sections_touched(diff: str) -> set:
    """Which businesses this change altered, or nothing when it cannot be
    told."""
    return read_diff(diff).touched


def line_wide(diff: str) -> bool:
    """True when it altered something outside any one business."""
    return read_diff(diff).touches_shared


# What is said in place of the lines a scoped owner may not read. The change is
# on their screen because it touched one of THEIR businesses; this says plainly
# that the same save did other things, without saying what or to whom.
OTHER_BUSINESSES = "…other businesses on this line changed in the same save"
LINE_WIDE = "…settings shared by the whole line changed in the same save"


def _visible(reading: Reading, keys=None) -> list:
    """The changed lines and a few either side, for the panel that expands.

    `keys` is None for an owner of the whole line: they see every line, always,
    whether or not the diff can be split up. For anybody else, a diff that
    cannot be split up yields NOTHING — the row still appears, saying only that
    something changed.

    When it can be split up, every line belonging to somebody else is dropped
    BEFORE the context window is worked out. That order is the whole point:
    filtering afterwards would still pull a neighbour's `ntfy_topic` onto the
    screen as three lines of "context" around a change of the reader's own.
    """
    if keys is None:
        body, elsewhere, others = reading.body, False, False
    elif not reading.certain:
        return []
    else:
        allowed = set(keys)
        body = [line for key, line in reading.walked if key in allowed]
        others = any(line[:1] in "+-" and key and key not in allowed
                     for key, line in reading.walked)
        elsewhere = any(line[:1] in "+-" and not key
                        for key, line in reading.walked)

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


def visible_diff(diff: str, keys=None) -> list:
    return _visible(read_diff(diff), keys)


def _named(names: list) -> str:
    """"Acme Co", "Acme Co and Riverside", "Acme Co, Riverside and Third"."""
    listed = list(names)
    if len(listed) <= 1:
        return listed[0] if listed else ""
    return ", ".join(listed[:-1]) + " and " + listed[-1]


def scoped_summary(deps, reading: Reading, keys) -> str:
    """What this change did TO THIS OWNER'S businesses, in the owner's words.

    The stored summary is written for whoever made the change and describes the
    whole save: "Removed the business Other Co" is the truth, and it is not
    this reader's truth to be told. So a scoped reader gets a sentence built
    from the same lines their diff is built from — never the stored one — and
    the names come from the live config, not from the diff.
    """
    _numbers, profiles = deps.get_state()
    touched = sorted(reading.touched & set(keys))
    names = [str((profiles.get(key) or {}).get("business_name", "")).strip()
             or key for key in touched]
    if names:
        sentence = f"Settings changed for {_named(names)}"
    else:
        # It is on their screen because it touched one of theirs; if nothing
        # names one now, say only that something on the line changed.
        sentence = "Settings on this line changed"
    if reading.touches_shared:
        sentence += ", and settings shared by the whole line"
    return sentence


def decorate_change(deps, change: dict, session=None, reading=None) -> dict:
    """One change as the reader in front of it may see it.

    `session` is None for an owner of the whole line: they get the change
    exactly as it was recorded. For anybody else every field is rebuilt from
    the part of the diff that is theirs — the lines, the sentence, who did it,
    and why it was refused — because each of those was written about the whole
    save and each of them can name a business next door. And when the diff
    cannot be split up at all, they get none of it: one sentence saying
    something changed, and nothing derived from a guess.
    """
    if reading is None:
        reading = read_diff(change.get("diff") or "")
    scoped = session is not None and not session.sees_whole_line
    keys = tuple(session.profile_keys) if scoped else None
    change["lines"] = _visible(reading, keys)
    # Read off the WHOLE diff, never the filtered view: whether a version can
    # be put back is a fact about the change, not about who is looking at it.
    change["can_restore"] = bool(change.get("applied")) and bool(reading.body)
    actor = str(change.get("actor") or "")
    if not scoped:
        change["actor_label"] = actor or "somebody on this line"
        return change
    # A login name is a fact about who else manages this line.
    change["actor_label"] = ("you" if actor and actor == session.owner_key
                             else UNKNOWN_ACTOR)
    if not reading.certain:
        change["summary"] = UNCERTAIN_SUMMARY
        change["actor_label"] = UNKNOWN_ACTOR
        change["lines"] = []
        change["reason"] = ""
        change["can_restore"] = False
        change.pop("diff", None)
        return change
    change["summary"] = scoped_summary(deps, reading, keys)
    if change.get("reason") and (
            reading.touched - set(keys) or reading.touches_shared):
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
        reading = read_diff(change.get("diff") or "")
        if not session.sees_whole_line and reading.certain:
            # A diff names other customers' numbers, greetings and push
            # targets. An owner of one business reads only what touched theirs.
            # A diff that cannot be split up is NOT filtered out here — it is
            # listed, as one dull sentence, because "was I affected?" is not a
            # question this can answer either.
            if not (reading.touched & mine):
                continue
        kept.append(decorate_change(deps, dict(change), session, reading))
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

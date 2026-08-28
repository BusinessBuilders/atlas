"""How one business answers its phone — eight sections, eight separate saves.

The screen this replaces was one enormous form with one button, and any
validation error re-drew it from the settings ALREADY IN FORCE: an owner who
rewrote a greeting and pasted three facts, then mistyped a phone number, lost
the greeting and the facts and could not even see the number they had typed
wrong. Everything here is built against that:

  * **Each section saves on its own.** Nothing an owner did not touch is
    submitted, so nothing an owner did not touch can be lost.
  * **A refusal is drawn from what was submitted**, with the reason beside the
    field it belongs to. Never from `get_state()`. This is not negotiable.
  * **A form carries the version it was built from.** Somebody saving from
    another device between the page load and the button press gets a refusal,
    not a silent overwrite of their work.
  * **Turning a capability off is confirmed in words.** Clearing the transfer
    number stops callers reaching a person; clearing the facts leaves the agent
    unable to answer anything. Neither happens because a box was emptied.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
from datetime import datetime

from aiohttp import web

from . import config_edit as edit
from . import render

log = logging.getLogger("atlas-phone")

SECTIONS = ("identity", "greeting", "facts", "instructions", "transfer",
            "ending", "names", "advanced")
SECTION_TITLES = {
    "identity": "Identity",
    "greeting": "Greeting",
    "facts": "What the agent may say",
    "instructions": "Extra instructions",
    "transfer": "Transfer to a person",
    "ending": "Ending a call",
    "names": "Name recognition",
    "advanced": "Advanced",
}
SAVED_MESSAGE = "Saved — live on the next call."
# What an owner is warned they are switching OFF, in the consequence's own
# words. Nothing here happens because a box was left empty.
CONSEQUENCES = {
    "facts": ("Your agent will not be able to answer a single question about "
              "your business — callers who ask about hours, pricing or where "
              "you work will be told it cannot say."),
    "forward_to": ("Callers will no longer be able to reach a person. Everyone "
                   "who asks for one will be offered a message instead."),
    "transfer_phrases": ("The standard list of phrases goes back into use, so "
                         "callers asking for \"an operator\" or \"a real "
                         "person\" are offered a transfer again."),
    "end_phrases": ("The standard list of phrases goes back into use, so "
                    "callers saying \"goodbye\" or \"that's all\" end the call "
                    "again."),
    "assistant_aliases": ("Your assistant will no longer recognise callers "
                          "mispronouncing its name."),
}


# ---------------------------------------------------------- what is there --

def _rows_or_standard(deps, profile, name: str) -> tuple:
    """(the rows to show, whether they are the product's standard list).

    "Leave it empty and you get the standard set" was a rule written in small
    grey text under a box. Here the standard phrases are simply IN the boxes,
    where they can be read, edited and removed one at a time.
    """
    typed = [line.strip() for line in str(profile.get(name, "")).splitlines()
             if line.strip()]
    if typed:
        return typed, False
    return list(deps.product_defaults.get(name, ())), True


def _standard_aliases(deps, assistant_name: str) -> list:
    """The mishearings the product already knows about for this name."""
    table = deps.product_defaults.get("assistant_aliases", {})
    return list(table.get(str(assistant_name).strip().lower(), ()))


def read_identity(deps, profile) -> dict:
    return {"business_name": str(profile.get("business_name", "")),
            "services": str(profile.get("services", "")),
            "owner_name": str(profile.get("owner_name", ""))}


def read_greeting(deps, profile) -> dict:
    return {
        "greeting": str(profile.get("greeting", "")),
        "ai_disclosure": bool(edit.setting(deps, profile, "ai_disclosure")),
        "ai_disclosure_text": str(edit.setting(deps, profile,
                                               "ai_disclosure_text")),
        "recording_notice": bool(edit.setting(deps, profile,
                                              "recording_notice")),
        "recording_notice_text": str(edit.setting(deps, profile,
                                                  "recording_notice_text")),
        "ack_disclosure_waived": bool(edit.setting(deps, profile,
                                                   "ack_disclosure_waived")),
    }


def read_facts(deps, profile) -> dict:
    return {"facts": [line.strip() for line
                      in str(profile.get("facts", "")).splitlines()
                      if line.strip()]}


def read_instructions(deps, profile) -> dict:
    return {"extra_instructions": str(profile.get("extra_instructions", ""))}


def read_transfer(deps, profile) -> dict:
    phrases, standard = _rows_or_standard(deps, profile, "transfer_phrases")
    return {"forward_to": str(profile.get("forward_to", "")),
            "transfer_on": bool(str(profile.get("forward_to", "")).strip()),
            "phrases": phrases, "phrases_are_standard": standard}


def read_ending(deps, profile) -> dict:
    phrases, standard = _rows_or_standard(deps, profile, "end_phrases")
    return {"phrases": phrases, "phrases_are_standard": standard}


def read_names(deps, profile) -> dict:
    name = str(profile.get("assistant_name", "")).strip()
    typed = [line.strip() for line
             in str(profile.get("assistant_aliases", "")).splitlines()
             if line.strip()]
    return {"assistant_name": name,
            "aliases": typed or _standard_aliases(deps, name or "Atlas"),
            "aliases_are_standard": not typed}


def read_advanced(deps, profile) -> dict:
    return {"model": str(profile.get("model", "")),
            "brain": str(edit.setting(deps, profile, "brain")),
            "retention_days": str(edit.setting(deps, profile,
                                               "retention_days"))}


READERS = {"identity": read_identity, "greeting": read_greeting,
           "facts": read_facts, "instructions": read_instructions,
           "transfer": read_transfer, "ending": read_ending,
           "names": read_names, "advanced": read_advanced}


# ------------------------------------------------------ what was submitted --

def _required(values: dict, errors: dict, name: str, what: str) -> None:
    value = str(values.get(name, "")).strip()
    if not value:
        errors[name] = f"{what} is needed — a caller hears it on every call."
        return
    long = edit.too_long(name, value)
    if long:
        errors[name] = long


def parse_identity(deps, form, profile) -> tuple:
    values = {name: edit.text_of(form, name)
              for name in ("business_name", "services", "owner_name")}
    errors: dict = {}
    _required(values, errors, "business_name", "The business name")
    _required(values, errors, "services", "What you do")
    _required(values, errors, "owner_name", "Who takes messages")
    updates = {name: values[name] for name in values}
    return values, errors, updates, "Changed the business details"


def parse_greeting(deps, form, profile) -> tuple:
    values = {
        "greeting": edit.text_of(form, "greeting"),
        "ai_disclosure": edit.checked(form, "ai_disclosure"),
        "ai_disclosure_text": edit.text_of(form, "ai_disclosure_text"),
        "recording_notice": edit.checked(form, "recording_notice"),
        "recording_notice_text": edit.text_of(form, "recording_notice_text"),
        "ack_disclosure_waived": edit.checked(form, "ack_disclosure_waived"),
    }
    errors: dict = {}
    _required(values, errors, "greeting", "The greeting")
    for flag, text_name, what in (
            ("ai_disclosure", "ai_disclosure_text", "The AI disclosure"),
            ("recording_notice", "recording_notice_text",
             "The recording notice")):
        if values[flag] and not values[text_name].strip():
            errors[text_name] = (f"{what} is switched on, so the caller would "
                                 "hear nothing where it should be. Write the "
                                 "sentence, or switch it off.")
        long = edit.too_long(text_name, values[text_name])
        if long:
            errors[text_name] = long
    switching_off = not (values["ai_disclosure"] and values["recording_notice"])
    if switching_off and not values["ack_disclosure_waived"]:
        errors["ack_disclosure_waived"] = (
            "Callers in many places have a right to be told they are speaking "
            "to a machine and that the call is kept. If this line genuinely "
            "does not need one of these, tick the box to say so on the record.")
    updates = {"greeting": values["greeting"]}
    for flag in ("ai_disclosure", "recording_notice", "ack_disclosure_waived"):
        updates[flag] = edit.default_or_none(deps, flag, values[flag])
    for text_name in ("ai_disclosure_text", "recording_notice_text"):
        updates[text_name] = edit.default_or_none(deps, text_name,
                                                  values[text_name]) or None
    return values, errors, updates, "Changed the greeting callers hear"


def parse_facts(deps, form, profile) -> tuple:
    values = {"facts": edit.rows_of(form, "fact")}
    errors: dict = {}
    for fact in values["facts"]:
        long = edit.too_long("fact", fact)
        if long:
            errors["facts"] = long
            break
    if len(values["facts"]) > edit.MAX_FACTS:
        errors["facts"] = (f"That is {len(values['facts'])} facts. Keep it to "
                           f"{edit.MAX_FACTS} — everything here is read to the "
                           "agent on every single call.")
    had = bool(str(profile.get("facts", "")).strip())
    if had and not values["facts"] and not edit.checked(form, "confirm_disable"):
        errors["confirm_disable"] = CONSEQUENCES["facts"]
    return (values, errors, {"facts": "\n".join(values["facts"]) or None},
            "Changed what the agent may tell callers")


def parse_instructions(deps, form, profile) -> tuple:
    values = {"extra_instructions": edit.text_of(form, "extra_instructions")}
    errors: dict = {}
    long = edit.too_long("extra_instructions", values["extra_instructions"])
    if long:
        errors["extra_instructions"] = long
    return (values, errors,
            {"extra_instructions": values["extra_instructions"] or None},
            "Changed the extra instructions")


def _phrase_errors(deps, rows: list) -> str:
    cap = int(deps.product_defaults.get("max_phrases", 64))
    longest = int(deps.product_defaults.get("max_phrase_len", 120))
    if len(rows) > cap:
        return f"That is {len(rows)} phrases. Keep it to {cap}."
    for phrase in rows:
        if len(phrase) > longest:
            return (f"“{phrase[:40]}…” is {len(phrase)} characters. "
                    f"Keep every phrase under {longest} — these are things a "
                    "caller says, not sentences.")
    return ""


def _phrase_update(deps, rows: list, name: str):
    """The value to write: None when the rows ARE the product's standard list,
    so a config that never listed them still does not."""
    if not rows or list(rows) == list(deps.product_defaults.get(name, ())):
        return None
    return "\n".join(rows)


def parse_transfer(deps, form, profile) -> tuple:
    on = edit.checked(form, "transfer_on")
    typed = edit.text_of(form, "forward_to")
    rows = edit.rows_of(form, "phrase")
    number, number_error = edit.e164(typed) if on else ("", "")
    values = {"transfer_on": on, "forward_to": typed if number_error else
              (number if on else typed),
              "phrases": rows, "phrases_are_standard": False}
    errors: dict = {}
    if on and not typed:
        errors["forward_to"] = ("Give the number to ring, or switch the "
                                "transfer off.")
    elif number_error:
        errors["forward_to"] = number_error
    phrase_problem = _phrase_errors(deps, rows)
    if phrase_problem:
        errors["phrases"] = phrase_problem
    had = str(profile.get("forward_to", "")).strip()
    confirmed = edit.checked(form, "confirm_disable")
    if had and not on and not confirmed:
        errors["confirm_disable"] = CONSEQUENCES["forward_to"]
    elif (str(profile.get("transfer_phrases", "")).strip() and not rows
            and not confirmed):
        errors["confirm_disable"] = CONSEQUENCES["transfer_phrases"]
    updates = {"forward_to": number if on else None,
               "transfer_phrases": _phrase_update(deps, rows,
                                                  "transfer_phrases")}
    return values, errors, updates, "Changed how callers reach a person"


def parse_ending(deps, form, profile) -> tuple:
    rows = edit.rows_of(form, "phrase")
    values = {"phrases": rows, "phrases_are_standard": False}
    errors: dict = {}
    problem = _phrase_errors(deps, rows)
    if problem:
        errors["phrases"] = problem
    if (str(profile.get("end_phrases", "")).strip() and not rows
            and not edit.checked(form, "confirm_disable")):
        errors["confirm_disable"] = CONSEQUENCES["end_phrases"]
    return (values, errors,
            {"end_phrases": _phrase_update(deps, rows, "end_phrases")},
            "Changed the phrases that end a call")


def parse_names(deps, form, profile) -> tuple:
    name = edit.text_of(form, "assistant_name")
    rows = edit.rows_of(form, "alias")
    values = {"assistant_name": name, "aliases": rows,
              "aliases_are_standard": False}
    errors: dict = {}
    long = edit.too_long("assistant_name", name)
    if long:
        errors["assistant_name"] = long
    problem = _phrase_errors(deps, rows)
    if problem:
        errors["aliases"] = problem
    if (str(profile.get("assistant_aliases", "")).strip() and not rows
            and not edit.checked(form, "confirm_disable")):
        errors["confirm_disable"] = CONSEQUENCES["assistant_aliases"]
    standard = _standard_aliases(deps, name or "Atlas")
    updates = {"assistant_name": name or None,
               "assistant_aliases": ("\n".join(rows)
                                     if rows and rows != standard else None)}
    return values, errors, updates, "Changed the assistant's name"


def parse_advanced(deps, form, profile) -> tuple:
    values = {"model": edit.text_of(form, "model"),
              "brain": edit.text_of(form, "brain"),
              "retention_days": edit.text_of(form, "retention_days")}
    errors: dict = {}
    long = edit.too_long("model", values["model"])
    if long:
        errors["model"] = long
    brains, _active = deps.get_brains()
    if values["brain"] and values["brain"] not in brains:
        errors["brain"] = ("That model is not set up on this line. Reload the "
                           "page and pick one of the models listed.")
    smallest, largest = _retention_limits(deps)
    try:
        days = int(values["retention_days"])
    except ValueError:
        days = None
        errors["retention_days"] = ("Give a whole number of days — how long a "
                                    "caller's words are kept.")
    else:
        if not smallest <= days <= largest:
            errors["retention_days"] = (
                f"{days} is outside the range this line can keep records for "
                f"({smallest} to {largest} days).")
    updates = {"model": values["model"] or None,
               "brain": values["brain"] or None,
               "retention_days": (edit.default_or_none(deps, "retention_days",
                                                       days)
                                  if days is not None else None)}
    return values, errors, updates, "Changed the advanced settings"


def _retention_limits(deps) -> tuple:
    for name, smallest, largest in deps.product_defaults.get("number_limits", ()):
        if name == "retention_days":
            return int(smallest), int(largest)
    return 1, 3650


PARSERS = {"identity": parse_identity, "greeting": parse_greeting,
           "facts": parse_facts, "instructions": parse_instructions,
           "transfer": parse_transfer, "ending": parse_ending,
           "names": parse_names, "advanced": parse_advanced}


# ------------------------------------------------------- drawing a section --

def _preview(deps, profile: dict, values: dict) -> dict:
    """Exactly what the caller hears first, built by the caller's own code.

    `opening_line` is the function the live call uses, so this is the caller's
    experience and not a second guess at it. A profile whose notices cannot be
    filled in raises there — on this screen that becomes a sentence, never a
    broken preview and never a 500.
    """
    trial = dict(profile)
    trial.update({
        "greeting": values.get("greeting", ""),
        "ai_disclosure": values.get("ai_disclosure", True),
        "ai_disclosure_text": values.get("ai_disclosure_text", ""),
        "recording_notice": values.get("recording_notice", True),
        "recording_notice_text": values.get("recording_notice_text", ""),
    })
    try:
        spoken = deps.opening_line(trial, None)
    except (ValueError, KeyError) as e:
        return {"line": "", "problem": f"This greeting cannot be spoken: {e}"}
    return {"line": spoken, "problem": "",
            "characters": len(spoken), "seconds": edit.spoken_seconds(spoken)}


def section_extras(deps, key: str, section: str, values: dict) -> dict:
    """Everything a section shows beside its own fields."""
    profile = edit.profile_of(deps, key)
    if section == "greeting":
        return {"preview": _preview(deps, profile, values)}
    if section == "transfer":
        return {"standard": list(deps.product_defaults.get("transfer_phrases",
                                                           ()))}
    if section == "ending":
        return {"standard": list(deps.product_defaults.get("end_phrases", ()))}
    if section == "names":
        return {"standard": _standard_aliases(
            deps, values.get("assistant_name") or "Atlas")}
    if section == "advanced":
        brains, active = deps.get_brains()
        known = set(deps.product_defaults.get("known_profile_keys", ()))
        return {
            "brains": [(name, brain.label.strip() or name)
                       for name, brain in sorted(brains.items())],
            "active_brain": active,
            "retention_range": _retention_limits(deps),
            "timezone_missing": not str(
                edit.setting(deps, profile, "timezone")).strip(),
            # Settings somebody hand-wrote that this bridge does not read. Shown
            # rather than hidden: they survive every save, and an owner looking
            # at a setting that does nothing deserves to be told which one.
            "unknown": sorted((name, str(value)) for name, value
                              in profile.items() if name not in known),
        }
    return {}


def section_context(deps, session, key: str, section: str, *, values=None,
                    errors=None, error: str = "", saved: bool = False,
                    version_id=None) -> dict:
    profile = edit.profile_of(deps, key)
    values = READERS[section](deps, profile) if values is None else values
    context = {
        "profile_key": key, "name": section,
        # `fields`, not `values`: a template asking a dict for `.values` gets
        # the dict's own method, not the entry named "values".
        "title": SECTION_TITLES[section], "fields": values,
        "errors": dict(errors or {}), "error": error, "saved": saved,
        "saved_message": SAVED_MESSAGE,
        "version": edit.version(deps) if version_id is None else version_id,
        # Filled in only by a save that went through; see the frame template.
        "oob_versions": (),
    }
    context.update(section_extras(deps, key, section, values))
    return context


# Which column each section is drawn in, following the approved board: the
# things an owner comes here to change on the left, the ones they set once on
# the right.
MAIN_COLUMN = ("greeting", "facts", "transfer", "instructions")
SIDE_COLUMN = ("identity", "ending", "names", "advanced")


def page_context(deps, session, key: str) -> dict:
    """The whole Business screen: every section, drawn from the live settings."""
    version_id = edit.version(deps)
    drawn = {name: section_context(deps, session, key, name,
                                   version_id=version_id)
             for name in SECTIONS}
    return {
        "business_key": key,
        "business": edit.business_name(deps, key),
        "businesses": edit.businesses(deps, session),
        "main_sections": [drawn[name] for name in MAIN_COLUMN],
        "side_sections": [drawn[name] for name in SIDE_COLUMN],
    }


# -------------------------------------------------------------- the screen --

async def _no_such_business(request, deps, session) -> web.Response:
    return await render.page(
        request, deps, "refused.html", session=session, status=404,
        reason=("That business is not on your line. It may have been removed, "
                "or it belongs to somebody else."))


async def _settings_page(request, deps, session, key: str) -> web.Response:
    if not key:
        return await render.page(
            request, deps, "refused.html", session=session, status=404,
            reason=("There is no business on your line to set up yet. Whoever "
                    "manages the line adds one."))
    context = await asyncio.to_thread(page_context, deps, session, key)
    return await render.page(request, deps, "settings.html", session=session,
                             flash=render.pop_flash(request, session),
                             **context)


async def settings(request: web.Request) -> web.Response:
    """The business an owner lands on: the one they asked for, or their first."""
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    key = edit.chosen_business(deps, session,
                               request.query.get("business", ""))
    return await _settings_page(request, deps, session, key)


async def settings_for(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    key = request.match_info["profile"]
    if key not in set(session.profile_keys) or not edit.profile_of(deps, key):
        return await _no_such_business(request, deps, session)
    return await _settings_page(request, deps, session, key)


async def save_section(request: web.Request) -> web.Response:
    """One section, saved on its own — and drawn again from what was typed."""
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    key = request.match_info["profile"]
    section = request.match_info["section"]
    if section not in SECTIONS:
        return await render.page(
            request, deps, "refused.html", session=session, status=404,
            reason="There is no such settings section on this screen.")
    if key not in set(session.profile_keys) or not edit.profile_of(deps, key):
        return await _no_such_business(request, deps, session)
    form = await request.post()
    reason = deps.auth.check_csrf(request, session, form)
    if reason:
        return await render.page(request, deps, "refused.html", session=session,
                                 status=403, reason=reason)

    if await asyncio.to_thread(edit.is_stale, deps, form):
        log.warning("dashboard: %s submitted a settings form built before the "
                    "settings changed — nothing was saved", session.owner_key)
        return await _answer(request, deps, session, key, section,
                             values=None, error=edit.STALE_MESSAGE,
                             status=409)

    profile = edit.profile_of(deps, key)
    values, errors, updates, summary = PARSERS[section](deps, form, profile)
    if errors:
        return await _answer(request, deps, session, key, section,
                             values=values, errors=errors, status=400)
    error = await asyncio.to_thread(
        edit.save, deps, session,
        profiles=edit.profiles_with(deps, key, updates),
        summary=f"{summary} for {edit.business_name(deps, key)}")
    if error:
        return await _answer(request, deps, session, key, section,
                             values=values,
                             error=f"Nothing was changed. {error}", status=400)
    return await _answer(request, deps, session, key, section, values=None,
                         saved=True)


async def _answer(request, deps, session, key: str, section: str, *,
                  values, errors=None, error: str = "", saved: bool = False,
                  status: int = 200) -> web.Response:
    """The section again — as its own panel for htmx, as the page for a browser
    without it.

    `values=None` means "read them back from the settings now in force", which
    is only ever right after a save that WORKED.
    """
    context = await asyncio.to_thread(
        section_context, deps, session, key, section, values=values,
        errors=errors, error=error, saved=saved)
    if saved:
        # Every other section on this page is now carrying an old version.
        context["oob_versions"] = tuple(name for name in SECTIONS
                                        if name != section)
    if request.headers.get("HX-Request"):
        # The panel alone, under the same name the page's own loop gives it, so
        # one template draws this section in both places.
        return render.partial(request, deps, f"_section_{section}.html",
                              session=session, status=status, section=context)
    if saved:
        render.set_flash(request, session, SAVED_MESSAGE)
    else:
        render.set_flash(request, session,
                         error or "That change was not saved — the reasons are "
                                  "beside the fields below.")
    raise web.HTTPSeeOther(f"/settings/{key}#section-{section}")


# ---------------------------------------------------- removing a business --

def _logins_left_with_nothing(deps, key: str) -> list:
    """Sign-ins that cover ONLY this business, and would be left covering none.

    A login with an empty list of businesses is refused by the config, so this
    has to be caught before the delete is offered rather than surfacing as the
    validator's own sentence about `[owners.*]` — which is a sentence about a
    file, to somebody who has never seen it.
    """
    return sorted(name for name, owner in (deps.get_owners() or {}).items()
                  if list(owner.profiles) == [key])


def _deletion(deps, key: str) -> dict:
    """What removing this business would do, worked out before it is offered."""
    numbers, profiles = deps.get_state()
    mapped = [number for number, owner in numbers.items() if owner == key]
    left = [name for name in profiles if name != key]
    remaining_numbers = [n for n in numbers if n not in set(mapped)]
    orphaned = _logins_left_with_nothing(deps, key)
    blocked = ""
    if not left:
        blocked = ("This is the only business on your line, and a phone line "
                   "has to answer as somebody. Add another business before "
                   "removing this one.")
    elif not remaining_numbers:
        blocked = ("Every phone number on this line answers for this business. "
                   "Point them at another business first, on the Numbers "
                   "screen.")
    elif orphaned:
        listed = ", ".join(orphaned)
        blocked = (f"The sign-in for {listed} covers this business and nothing "
                   "else, so removing it would leave that login with nothing to "
                   "open. Whoever set your line up has to give that sign-in "
                   "another business, or take it away, first.")
    return {"numbers": mapped, "blocked": blocked,
            "recovery_days": int(deps.product_defaults.get("recovery_days", 30))}


async def delete_page(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    key = request.match_info["profile"]
    if key not in set(session.profile_keys) or not edit.profile_of(deps, key):
        return await _no_such_business(request, deps, session)
    return await _delete_page(request, deps, session, key, error="")


async def _delete_page(request, deps, session, key: str, *, error: str,
                       status: int = 200) -> web.Response:
    version = await asyncio.to_thread(edit.version, deps)
    return await render.page(
        request, deps, "delete_business.html", session=session, status=status,
        business_key=key, business=edit.business_name(deps, key),
        version=version, error=error, **_deletion(deps, key))


async def delete_business(request: web.Request) -> web.Response:
    """Put one business away — reversibly, and only when its name is typed.

    A soft delete: the settings move to `[deleted_profiles.*]` in the config
    with the date, its numbers stop answering for it, and Activity can put the
    whole thing back for thirty days. The old dashboard did this with a 13-pixel
    checkbox inside the form that saved everything else, over a file with no
    backup.
    """
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
        return await _delete_page(request, deps, session, key,
                                  error=edit.STALE_MESSAGE, status=409)
    plan = _deletion(deps, key)
    if plan["blocked"]:
        return await _delete_page(request, deps, session, key,
                                  error=plan["blocked"], status=400)
    name = edit.business_name(deps, key)
    if str(form.get("confirm", "")).strip() != name:
        return await _delete_page(
            request, deps, session, key, status=400,
            error=(f"That is not the name of this business. Type "
                   f"“{name}” exactly to remove it."))
    error = await asyncio.to_thread(_remove, deps, session, key, name)
    if error:
        return await _delete_page(request, deps, session, key,
                                  error=f"Nothing was changed. {error}",
                                  status=400)
    log.warning("dashboard: %s removed the business %r", session.owner_key, key)
    render.set_flash(request, session,
                     f"{name} was removed. You can put it back from Activity "
                     f"for {plan['recovery_days']} days.")
    raise web.HTTPSeeOther("/activity")


def _remove(deps, session, key: str, name: str):
    config = deps.get_config()
    profiles = {k: v for k, v in config.profiles.items() if k != key}
    numbers = {n: owner for n, owner in config.numbers.items() if owner != key}
    put_away = dict(config.profiles[key])
    put_away[str(deps.product_defaults.get("deleted_at_key", "deleted_at"))] = (
        datetime.now().astimezone().replace(microsecond=0).isoformat())
    removed = dict(config.deleted_profiles)
    removed[key] = put_away
    # Every sign-in stops covering it too. One that named ONLY this business is
    # refused before we get here (`_deletion`), so nobody is left with a login
    # that opens nothing.
    owners = {
        owner_key: dataclasses.replace(
            owner, profiles=[p for p in owner.profiles if p != key])
        for owner_key, owner in config.owners.items()}
    return edit.save(deps, session, profiles=profiles, numbers=numbers,
                     deleted_profiles=removed, owners=owners,
                     summary=f"Removed the business {name}")

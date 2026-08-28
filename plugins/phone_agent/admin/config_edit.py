"""What every settings screen shares: whose business, which version, one save.

Three ideas run through all of it.

  * **One save path.** A greeting, the opening hours, a number's business and a
    removed business all end in `deps.apply_config`, which emits the whole file,
    validates it fail-closed, backs the old one up, hot-applies it and writes
    the audit row. There is no second, quieter way for the live line to change.
  * **Your typing survives a refusal.** A screen that fails validation is drawn
    again from what was SUBMITTED, never from the settings in force — that was
    the single worst defect in the dashboard this replaces, and it cost people
    the paragraph they had just written on a phone.
  * **A stale form is refused, not applied.** Every form carries the id of the
    newest settings change. If somebody saved from another device in between,
    the form is out of date and the save stops — last-write-wins on a business
    phone line is a way to silently undo somebody else's work.
"""
from __future__ import annotations

import copy
import dataclasses
import logging
import re

log = logging.getLogger("atlas-phone")

STALE_MESSAGE = ("This page is out of date — reload to see the latest settings. "
                 "Nothing was changed.")
# What a phone number has to look like once the dashboard has tidied it up.
E164 = re.compile(r"^\+[0-9]{7,15}$")
# Room for a sentence somebody reads out loud, not a document. The server holds
# to these: a maxlength attribute is a suggestion to a browser and nothing at
# all to anything else.
LIMITS = {
    "business_name": 120,
    "services": 240,
    "owner_name": 80,
    "assistant_name": 40,
    "greeting": 400,
    "after_hours_greeting": 400,
    "ai_disclosure_text": 240,
    "recording_notice_text": 240,
    "extra_instructions": 6000,
    "fact": 240,
    "model": 120,
    "ntfy_url": 200,
    "ntfy_topic": 120,
}
MAX_FACTS = 60
MAX_HOLIDAYS = 60


# ------------------------------------------------------------ whose line --

def businesses(deps, session) -> list:
    """(key, name) for every business this login may change, in name order."""
    _numbers, profiles = deps.get_state()
    listed = [(key, str(profiles.get(key, {}).get("business_name", "")).strip()
               or key)
              for key in session.profile_keys if key in profiles]
    listed.sort(key=lambda pair: pair[1].lower())
    return listed


def chosen_business(deps, session, wanted: str) -> str:
    """The business a screen is about: the one asked for, or the first one they
    own. "" when this login owns none, which the screens say out loud."""
    owned = [key for key, _name in businesses(deps, session)]
    wanted = str(wanted or "").strip()
    if wanted and wanted in owned:
        return wanted
    return owned[0] if owned else ""


def profile_of(deps, key: str) -> dict:
    _numbers, profiles = deps.get_state()
    return dict(profiles.get(key) or {})


def business_name(deps, key: str) -> str:
    return str(profile_of(deps, key).get("business_name", "")).strip() or key


def setting(deps, profile: dict, name: str, fallback=""):
    """One business setting, the product's own default filled in.

    `profile_setting` knows the defaults for everything in the product's
    settings table and raises for anything else — the required fields
    (business name, greeting…) and the free text ones have no default but their
    own emptiness.
    """
    try:
        return deps.profile_setting(profile, name)
    except KeyError:
        return profile.get(name, fallback)


# ------------------------------------------------------- optimistic saves --

def version(deps) -> int:
    """The id of the newest settings change — what a form carries so a save
    built before somebody else's is refused instead of overwriting it."""
    try:
        return int(deps.store.newest_config_change_id())
    except Exception:
        # A version we cannot read must not silently become "0", which every
        # form would then match. Refusing every save until the store answers is
        # the safe direction, and -1 never equals a form's number.
        log.exception("dashboard: could not read the settings version")
        return -1


def is_stale(deps, form) -> bool:
    """True when this form was built before the settings changed underneath it."""
    try:
        submitted = int(str(form.get("version", "")).strip())
    except ValueError:
        return True
    return submitted != version(deps)


def save(deps, session, profiles=None, numbers=None, deleted_profiles=None,
         owners=None, *, summary: str):
    """Apply one change to the whole config. Returns the refusal, or None.

    Only the parts a screen actually edited are passed in; everything else
    comes from the config in force at this moment, so two screens saving
    different things cannot undo each other.
    """
    config = deps.get_config()
    changes = {}
    if profiles is not None:
        changes["profiles"] = profiles
    if numbers is not None:
        changes["numbers"] = numbers
    if deleted_profiles is not None:
        changes["deleted_profiles"] = deleted_profiles
    if owners is not None:
        changes["owners"] = owners
    return deps.apply_config(dataclasses.replace(config, **changes),
                             session.owner_key, summary)


def profiles_with(deps, key: str, updates: dict) -> dict:
    """Every business as it is now, with `key`'s settings changed.

    A deep copy: nothing here may touch the dictionaries a live call is reading
    until the whole file has been validated and hot-applied.
    """
    profiles = copy.deepcopy(deps.get_state()[1])
    profile = dict(profiles.get(key) or {})
    for name, value in updates.items():
        if value is None:
            profile.pop(name, None)
        else:
            profile[name] = value
    profiles[key] = profile
    return profiles


def default_or_none(deps, name: str, value):
    """`value`, or None when it is exactly what the product does anyway.

    Writing a setting that matches the default back into the file is harmless
    but noisy; leaving it out keeps a customer's config readable and keeps the
    default in ONE place — the service's own table.
    """
    try:
        if deps.profile_setting({}, name) == value:
            return None
    except KeyError:
        pass
    return value


# -------------------------------------------------------------- the input --

def text_of(form, name: str, limit: int = 0) -> str:
    """One typed field, tidied but never silently shortened."""
    value = str(form.get(name, "")).replace("\r\n", "\n").strip()
    if limit and len(value) > limit:
        return value[:limit * 2]      # kept for redisplay; the check refuses it
    return value


def rows_of(form, name: str) -> list:
    """A repeatable row group, in the order it was typed, blanks dropped."""
    return [str(value).strip() for value in form.getall(name, [])
            if str(value).strip()]


def checked(form, name: str) -> bool:
    return str(form.get(name, "")).strip().lower() in ("on", "1", "true", "yes")


def e164(text: str) -> tuple:
    """(the number in the form the phone network wants, the reason it is not).

    An owner types the number the way they read it off a business card, in
    brackets and hyphens; the phone network wants it as a plus, a country code
    and nothing else. Doing that for them here is the difference between a
    setting that works and a form that keeps saying no.
    """
    typed = str(text or "").strip()
    if not typed:
        return "", ""
    digits = re.sub(r"[^0-9]", "", typed)
    if typed.startswith("+"):
        candidate = "+" + digits
    elif len(digits) == 10:
        candidate = "+1" + digits          # a North American number as dialled
    elif len(digits) == 11 and digits.startswith("1"):
        candidate = "+" + digits
    else:
        candidate = "+" + digits if digits else ""
    if not E164.match(candidate):
        return typed, ("That is not a phone number this line can dial. Write it "
                       "as you would dial it — (555) 000-0001 — or with the "
                       "country code, like +15550000001.")
    return candidate, ""


def too_long(name: str, value: str) -> str:
    limit = LIMITS.get(name, 0)
    if limit and len(value) > limit:
        return (f"That is {len(value)} characters. Keep it to {limit} — this is "
                "read out loud, not filed away.")
    return ""


# Roughly what the line's own text-to-speech takes: 150 words a minute, the
# same rate service.speech_seconds() uses to decide how long to wait before
# hanging up. It is an estimate and the screen says so.
SECONDS_PER_WORD = 0.45


def spoken_seconds(text: str) -> int:
    return max(1, round(SECONDS_PER_WORD * len(str(text).split())))

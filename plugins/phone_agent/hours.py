"""Opening hours for the phone agent — pure functions, no I/O.

A business profile in businesses.toml can say when it is open:

    timezone = "America/New_York"        # IANA name; required once the two
                                         # settings below are used
    hours = { mon = "09:00-17:00", tue = "09:00-17:00" }
    holidays = ["2026-11-26", "2026-12-24..2026-12-26"]

Rules, deliberately boring:
  * A day left OUT of the `hours` table is closed all day. No table at all
    means the line is always open (what every profile did before hours
    existed) — that stays the default so nothing changes under an owner who
    never touched this.
  * A range whose end is before its start is an OVERNIGHT shift: "18:00-02:00"
    on Tuesday runs until 02:00 on Wednesday morning. The shift belongs to the
    day it STARTED on, so a Tuesday holiday takes Wednesday's small hours
    with it.
  * A holiday closes the whole local day, whatever the hours table says.
  * Everything is evaluated in the PROFILE's timezone, never the host's. The
    bridge may run in one state and answer for a business in another.

`open_state()` never guesses: a profile with hours and no timezone raises
rather than quietly using the machine's zone, and a `now` without a timezone
is refused for the same reason. Both are caught at config-validation time by
service.py, so a live call cannot be the first thing to find out.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Monday-first, matching datetime.weekday().
DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# How far ahead next_open will look before answering "I don't know". A month
# of holidays is a real answer of None, not a wrong date.
NEXT_OPEN_HORIZON_DAYS = 14

_RANGE_RE = re.compile(r"^([0-9]{2}):([0-9]{2})-([0-9]{2}):([0-9]{2})$")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


@dataclass(frozen=True)
class OpenState:
    """Whether the line is open right now, why, and — when it is closed — the
    next local datetime it opens (None when nothing is scheduled inside the
    horizon)."""
    open: bool
    reason: str              # "hours" | "holiday" | "always"
    next_open: datetime | None


def parse_day_range(value) -> tuple[time, time]:
    """"09:00-17:00" -> (09:00, 17:00). Raises ValueError with a sentence an
    owner can act on."""
    text = str(value).strip()
    match = _RANGE_RE.match(text)
    if not match:
        raise ValueError(
            f"opening hours {text!r} must look like \"09:00-17:00\" — two "
            "24-hour times separated by a hyphen"
        )
    start_h, start_m, end_h, end_m = (int(part) for part in match.groups())
    for hour, minute in ((start_h, start_m), (end_h, end_m)):
        if hour > 23 or minute > 59:
            raise ValueError(
                f"opening hours {text!r} contain a time that does not exist — "
                "hours are 00-23 and minutes 00-59"
            )
    start, end = time(start_h, start_m), time(end_h, end_m)
    if start == end:
        raise ValueError(
            f"opening hours {text!r} open and close at the same minute. For a "
            "day that is closed, leave it out of the table; for one that never "
            "closes, remove the hours table."
        )
    return start, end


def parse_holiday(value) -> tuple[date, date]:
    """"2026-12-25" or "2026-12-24..2026-12-26" -> (first_day, last_day),
    both inclusive."""
    text = str(value).strip()
    first, sep, last = text.partition("..")
    parts = [first, last] if sep else [first]
    parsed = []
    for part in parts:
        part = part.strip()
        if not _DATE_RE.match(part):
            raise ValueError(
                f"holiday {text!r} must be a date like \"2026-12-25\", or a range "
                "like \"2026-12-24..2026-12-26\""
            )
        try:
            parsed.append(date.fromisoformat(part))
        except ValueError:
            raise ValueError(f"holiday {text!r} is not a real date")
    start = parsed[0]
    end = parsed[-1]
    if end < start:
        raise ValueError(
            f"holiday range {text!r} ends before it starts — write the earlier "
            "date first"
        )
    return start, end


def parse_hours_table(value) -> dict[str, tuple[time, time]]:
    """Validate a whole `hours` table. Raises ValueError naming the day."""
    if not isinstance(value, dict):
        raise ValueError(
            'hours must be a table like { mon = "09:00-17:00", tue = "09:00-17:00" }'
        )
    table: dict[str, tuple[time, time]] = {}
    for day, raw in value.items():
        key = str(day).strip().lower()
        if key not in DAY_KEYS:
            raise ValueError(
                f"hours has a day called {day!r} — use {', '.join(DAY_KEYS)} "
                "(leave a day out to be closed that day)"
            )
        if not isinstance(raw, str):
            raise ValueError(
                f"hours for {key} must be text like \"09:00-17:00\", not "
                f"{type(raw).__name__}"
            )
        table[key] = parse_day_range(raw)
    return table


def parse_holidays(value) -> list[tuple[date, date]]:
    """Validate a whole `holidays` list."""
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(
            'holidays must be a list like ["2026-11-26", "2026-12-24..2026-12-26"]'
        )
    return [parse_holiday(item) for item in value]


def profile_zone(profile: Mapping) -> tzinfo:
    """The profile's timezone. Falls back to the host's zone ONLY when the
    profile schedules nothing — a profile with hours or holidays and no
    timezone is a question nobody can answer, so it raises."""
    name = str(profile.get("timezone", "") or "").strip()
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise ValueError(
                f"timezone {name!r} is not a name this machine knows. Use an IANA "
                'name like "America/New_York" or "Europe/London".'
            )
    if profile.get("hours") or profile.get("holidays"):
        raise ValueError(
            'opening hours and holidays need a timezone — add timezone = '
            '"America/New_York" (or wherever the business is) to the profile'
        )
    host = datetime.now().astimezone().tzinfo
    assert host is not None      # astimezone() always attaches one
    return host


def _in_holidays(day: date, holidays: list[tuple[date, date]]) -> bool:
    return any(start <= day <= end for start, end in holidays)


def _covers(moment: time, span: tuple[time, time]) -> bool:
    """Is `moment` inside the part of `span` that falls on the span's OWN day?
    (The post-midnight tail of an overnight shift belongs to the next day and
    is handled by the caller.)"""
    start, end = span
    if start < end:
        return start <= moment < end
    return moment >= start


def _spills_into_next_morning(span: tuple[time, time], moment: time) -> bool:
    start, end = span
    return start > end and moment < end


def open_state(profile: Mapping, now: datetime) -> OpenState:
    """Is this business open at `now`? `now` must be timezone-aware; it is
    converted into the profile's timezone before anything is decided."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError(
            "open_state needs a timezone-aware `now` — a naive clock silently "
            "means the host's zone, which is not necessarily the business's"
        )
    zone = profile_zone(profile)
    table = parse_hours_table(profile.get("hours") or {})
    holidays = parse_holidays(profile.get("holidays") or [])

    local = now.astimezone(zone)
    today = local.date()

    if not table and not holidays:
        return OpenState(True, "always", None)

    if _in_holidays(today, holidays):
        return OpenState(False, "holiday", _next_open(local, table, holidays, zone))

    if not table:
        # Always open, except on the holidays handled above.
        return OpenState(True, "always", None)

    span = table.get(DAY_KEYS[today.weekday()])
    if span is not None and _covers(local.time(), span):
        return OpenState(True, "hours", None)

    yesterday = today - timedelta(days=1)
    last_night = table.get(DAY_KEYS[yesterday.weekday()])
    if (last_night is not None
            and not _in_holidays(yesterday, holidays)
            and _spills_into_next_morning(last_night, local.time())):
        return OpenState(True, "hours", None)

    return OpenState(False, "hours", _next_open(local, table, holidays, zone))


def _next_open(local: datetime, table: dict[str, tuple[time, time]],
               holidays: list[tuple[date, date]], zone: tzinfo) -> datetime | None:
    """The next local datetime this business opens, or None when nothing opens
    inside NEXT_OPEN_HORIZON_DAYS."""
    today = local.date()
    for offset in range(0, NEXT_OPEN_HORIZON_DAYS + 1):
        day = today + timedelta(days=offset)
        if _in_holidays(day, holidays):
            continue
        if not table:
            # No schedule: the day the holidays end, the line is open again
            # from midnight.
            candidate = datetime.combine(day, time(0, 0), tzinfo=zone)
        else:
            span = table.get(DAY_KEYS[day.weekday()])
            if span is None:
                continue
            candidate = datetime.combine(day, span[0], tzinfo=zone)
        if candidate > local:
            return candidate
    return None

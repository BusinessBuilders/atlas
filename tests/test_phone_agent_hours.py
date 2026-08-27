# tests/test_phone_agent_hours.py — the phone agent's opening-hours engine.
#
# A receptionist that answers "we're open" at 2am, or takes a message on a
# Tuesday morning because a holiday range was read wrong, is worse than no
# receptionist. Everything here runs against FIXED clocks in a real timezone
# (America/New_York, which has DST) — no test may depend on when it runs.
import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

PLUGINS_DIR = Path(__file__).resolve().parents[1] / "plugins"
NY = ZoneInfo("America/New_York")

# A whole week clear of any DST transition: 2026-07-06 is a Monday.
MON = datetime(2026, 7, 6, tzinfo=NY)
TUE = datetime(2026, 7, 7, tzinfo=NY)
WED = datetime(2026, 7, 8, tzinfo=NY)
SAT = datetime(2026, 7, 11, tzinfo=NY)
NEXT_MON = datetime(2026, 7, 13, tzinfo=NY)

WEEKDAYS_9_5 = {
    "mon": "09:00-17:00", "tue": "09:00-17:00", "wed": "09:00-17:00",
    "thu": "09:00-17:00", "fri": "09:00-17:00",
}


def _load_hours():
    """hours.py is a pure module — no env, no sockets, no store."""
    spec = importlib.util.spec_from_file_location(
        "phone_agent_hours_under_test", PLUGINS_DIR / "phone_agent" / "hours.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hours():
    return _load_hours()


def _profile(**extra) -> dict:
    profile = {"business_name": "Acme Plumbing", "services": "drains",
               "owner_name": "Jo", "greeting": "hi",
               "timezone": "America/New_York"}
    profile.update(extra)
    return profile


def _at(day: datetime, hour: int, minute: int = 0) -> datetime:
    return day.replace(hour=hour, minute=minute)


# ------------------------------------------------------------ open/closed --

def test_open_inside_the_weekday_range(hours):
    state = hours.open_state(_profile(hours=WEEKDAYS_9_5), _at(TUE, 10))
    assert state.open is True
    assert state.reason == "hours"
    assert state.next_open is None          # already open: nothing to wait for


def test_closed_after_hours_points_at_tomorrow_morning(hours):
    state = hours.open_state(_profile(hours=WEEKDAYS_9_5), _at(TUE, 18))
    assert state.open is False
    assert state.reason == "hours"
    assert state.next_open == _at(WED, 9)


def test_closed_before_opening_points_at_this_morning(hours):
    state = hours.open_state(_profile(hours=WEEKDAYS_9_5), _at(TUE, 8))
    assert state.open is False
    assert state.next_open == _at(TUE, 9)


def test_a_day_left_out_of_the_table_is_closed_all_day(hours):
    """Saturday is not in the table at all — that means closed, and the next
    opening is Monday, not 'sometime'."""
    state = hours.open_state(_profile(hours=WEEKDAYS_9_5), _at(SAT, 11))
    assert state.open is False
    assert state.reason == "hours"
    assert state.next_open == _at(NEXT_MON, 9)


def test_the_closing_minute_is_closed(hours):
    """17:00-17:59 must not answer 'we're open' when the range ends at 17:00."""
    assert hours.open_state(_profile(hours=WEEKDAYS_9_5), _at(TUE, 16, 59)).open is True
    assert hours.open_state(_profile(hours=WEEKDAYS_9_5), _at(TUE, 17, 0)).open is False


def test_no_hours_table_means_always_open(hours):
    state = hours.open_state(_profile(), datetime(2026, 7, 11, 3, 30, tzinfo=NY))
    assert state.open is True
    assert state.reason == "always"
    assert state.next_open is None


# -------------------------------------------------------- overnight ranges --

def test_an_overnight_range_is_open_after_midnight(hours):
    """18:00-02:00 on Tuesday is still Tuesday's shift at 01:00 on Wednesday."""
    profile = _profile(hours={"tue": "18:00-02:00"})
    assert hours.open_state(profile, _at(TUE, 19)).open is True
    assert hours.open_state(profile, _at(WED, 1)).open is True
    assert hours.open_state(profile, _at(WED, 3)).open is False


def test_an_overnight_range_does_not_leak_into_a_day_it_never_started(hours):
    """Monday 01:00 is not covered by TUESDAY's overnight shift."""
    profile = _profile(hours={"tue": "18:00-02:00"})
    assert hours.open_state(profile, _at(MON, 1)).open is False


# ---------------------------------------------------------------- holidays --

def test_a_holiday_date_closes_the_whole_day(hours):
    profile = _profile(hours=WEEKDAYS_9_5, holidays=["2026-07-07"])
    state = hours.open_state(profile, _at(TUE, 10))
    assert state.open is False
    assert state.reason == "holiday"
    assert state.next_open == _at(WED, 9)


def test_a_holiday_range_closes_every_day_in_it(hours):
    profile = _profile(hours={d: "09:00-17:00" for d in
                              ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
                       holidays=["2026-12-24..2026-12-26"])
    for day in (24, 25, 26):
        state = hours.open_state(profile, datetime(2026, 12, day, 10, tzinfo=NY))
        assert state.open is False and state.reason == "holiday", day
    # the 23rd and the 27th are ordinary days
    assert hours.open_state(profile, datetime(2026, 12, 23, 10, tzinfo=NY)).open is True
    assert hours.open_state(profile, datetime(2026, 12, 27, 10, tzinfo=NY)).open is True
    # and the wait is until the morning after the range ends
    closed = hours.open_state(profile, datetime(2026, 12, 24, 10, tzinfo=NY))
    assert closed.next_open == datetime(2026, 12, 27, 9, tzinfo=NY)


def test_holidays_without_an_hours_table_close_only_that_day(hours):
    """A business that never closes still closes on Christmas."""
    profile = _profile(holidays=["2026-12-25"])
    assert hours.open_state(profile, datetime(2026, 12, 25, 10, tzinfo=NY)).reason == "holiday"
    open_again = hours.open_state(profile, datetime(2026, 12, 25, 10, tzinfo=NY)).next_open
    assert open_again == datetime(2026, 12, 26, 0, 0, tzinfo=NY)
    assert hours.open_state(profile, datetime(2026, 12, 26, 10, tzinfo=NY)).open is True


def test_a_holiday_takes_its_overnight_shift_with_it(hours):
    """Tuesday is a holiday, so Tuesday's 18:00-02:00 shift never started and
    Wednesday 01:00 is closed."""
    profile = _profile(hours={"tue": "18:00-02:00", "wed": "18:00-02:00"},
                       holidays=["2026-07-07"])
    assert hours.open_state(profile, _at(WED, 1)).open is False


# ------------------------------------------------------------- DST + zones --

def test_the_fall_back_hour_resolves_without_exception(hours):
    """2026-11-01 01:00-02:00 happens twice in New York. A range spanning it
    must answer, not raise."""
    profile = _profile(hours={"sun": "18:00-02:00", "sat": "18:00-02:00"})
    for hour in (0, 1, 2, 3):
        state = hours.open_state(profile, datetime(2026, 11, 1, hour, 30, tzinfo=NY))
        assert isinstance(state.open, bool)


def test_the_spring_forward_gap_resolves_without_exception(hours):
    """2026-03-08 02:00-03:00 does not exist in New York."""
    profile = _profile(hours={"sun": "02:00-10:00"})
    state = hours.open_state(profile, datetime(2026, 3, 8, 4, tzinfo=NY))
    assert state.open is True


def test_the_profile_timezone_decides_not_the_hosts(hours):
    """10:00 in London is 05:00 in New York — closed."""
    london = datetime(2026, 7, 7, 10, tzinfo=ZoneInfo("Europe/London"))
    assert hours.open_state(_profile(hours=WEEKDAYS_9_5), london).open is False
    assert hours.open_state(
        _profile(hours=WEEKDAYS_9_5, timezone="Europe/London"), london).open is True


# ------------------------------------------------------------- fail loudly --

def test_hours_without_a_timezone_raise(hours):
    profile = {"business_name": "Acme", "hours": WEEKDAYS_9_5}
    with pytest.raises(ValueError, match="timezone"):
        hours.open_state(profile, _at(TUE, 10))


def test_a_naive_clock_is_refused(hours):
    """A naive datetime silently means 'the host's idea of now' — on a machine
    in another zone that answers the wrong question."""
    with pytest.raises(ValueError, match="timezone-aware"):
        hours.open_state(_profile(hours=WEEKDAYS_9_5), datetime(2026, 7, 7, 10))


def test_next_open_gives_up_honestly_past_the_horizon(hours):
    """Closed for a month of holidays: better None than a wrong date."""
    profile = _profile(hours=WEEKDAYS_9_5, holidays=["2026-07-01..2026-08-31"])
    state = hours.open_state(profile, _at(TUE, 10))
    assert state.open is False and state.next_open is None


# ------------------------------------------------- the shared field parsers --

@pytest.mark.parametrize("value", ["9-5", "09:00", "09:00–17:00", "25:00-26:00",
                                   "09:00-17:60", "", "09:00-09:00"])
def test_a_bad_day_range_is_refused(hours, value):
    with pytest.raises(ValueError):
        hours.parse_day_range(value)


@pytest.mark.parametrize("value", ["2026-13-01", "Dec 25", "2026-12-26..2026-12-24",
                                   "2026-12-24...2026-12-26", ""])
def test_a_bad_holiday_is_refused(hours, value):
    with pytest.raises(ValueError):
        hours.parse_holiday(value)


def test_a_single_holiday_date_is_a_one_day_range(hours):
    from datetime import date
    assert hours.parse_holiday("2026-12-25") == (date(2026, 12, 25), date(2026, 12, 25))
    assert hours.parse_holiday("2026-12-24..2026-12-26") == (
        date(2026, 12, 24), date(2026, 12, 26))

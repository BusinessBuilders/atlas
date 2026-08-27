# tests/test_phone_agent_callstore.py — the SQLite call store.
#
# Until this module existed the ONLY record of a call was a journald INFO line
# holding the caller's verbatim words (audit H-7): no retention, no way to
# delete one caller, and a dashboard whose "call log" was a journalctl grep
# that returned nothing. These tests pin the replacement:
#
#   * a real SQLite file on disk (tmp_path) — no in-memory shortcut, because
#     WAL mode, foreign keys and the ON DELETE CASCADE path only exist on a
#     real file;
#   * the store RAISES on anything it cannot do — the service decides how to be
#     loud, never the store;
#   * the retention horizon and the per-caller delete really remove rows;
#   * fixture calls are flagged (is_test) so "Sarah from Rose Bakery" can never
#     again sit in the owner's message list looking like a paying customer;
#   * and, end to end over a real websocket, one call writes exactly one calls
#     row, N turns and one message — while the journal holds no caller text.
#
# No real caller data anywhere: +1555…/CAtest… and invented names only.
import importlib.util
import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pytest

from test_phone_agent_hardening import phone_line, prompt_frame, run_call, setup_frame

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "phone_agent"
DAY = 86400.0


def _load(name: str):
    path = PLUGIN_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"phone_agent_{name}_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def callstore():
    return _load("callstore")


@pytest.fixture(scope="module")
def migrate_pad():
    return _load("migrate_pad")


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "calls.db")


@pytest.fixture
def store(callstore, db_path):
    s = callstore.CallStore(db_path)
    yield s
    s.close()


def _sql(path: str) -> sqlite3.Connection:
    """A second, independent connection — the tests read what really landed on
    disk, not what the store thinks it wrote."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _add_call(store, call_sid="CA0000000000000000000000000000001",
              profile="acme", frm="+17770001111", started=None, outcome="message_taken",
              is_test=False):
    store.start_call(call_sid, profile, frm, "+15550001111", "local_qwen",
                     "test-model", is_test=is_test)
    store.end_call(call_sid, outcome, "", 1, [])
    if started is not None:
        with _sql(store.path) as conn:
            conn.execute("UPDATE calls SET started_at=?, ended_at=?, duration_s=? "
                         "WHERE call_sid=?", (started, started + 30, 30.0, call_sid))
    return call_sid


# ------------------------------------------------------------- the schema --

def test_the_store_creates_its_schema_on_a_fresh_file(store, db_path):
    assert Path(db_path).exists()
    with _sql(db_path) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    for table in ("calls", "turns", "messages", "events", "config_changes",
                  "notify_log", "sessions"):
        assert table in tables, f"{table} missing from the schema"


def test_the_store_is_wal_with_foreign_keys_on(store, db_path):
    with _sql(db_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert store.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_opening_the_same_file_twice_is_safe(callstore, db_path, store):
    """A dashboard process and the bridge both hold the file open."""
    second = callstore.CallStore(db_path)
    try:
        _add_call(store)
        assert second.get_call("CA0000000000000000000000000000001") is not None
    finally:
        second.close()


def test_a_store_on_a_missing_directory_raises(callstore, tmp_path):
    """Fail-closed: the service turns this into a refusal to start, not a
    bridge that answers calls and records nothing."""
    with pytest.raises(sqlite3.Error):
        callstore.CallStore(str(tmp_path / "nope" / "calls.db"))


# --------------------------------------------------------- the test flag ---

@pytest.mark.parametrize("call_sid, from_number, expected", [
    ("CAtest_pad_1784591071", "+17770001111", True),
    ("CA4116a2657c8da7bb1ad79843aee3af4a", "+15555550142", True),
    ("CA4116a2657c8da7bb1ad79843aee3af4a", "+17770001111", False),
    ("CAtest00000000001", "+15550001234", True),
    ("", "", False),
])
def test_is_test_call(callstore, call_sid, from_number, expected):
    assert callstore.is_test_call(call_sid, from_number) is expected


def test_start_call_flags_test_rows_when_asked(store):
    store.start_call("CAtest_x", "acme", "+15550009999", "+15550001111",
                     "local_qwen", "test-model", is_test=True)
    assert store.get_call("CAtest_x")["is_test"] == 1


# ------------------------------------------------------- the call itself ---

def test_start_turns_end_round_trip(store):
    store.start_call("CAround1", "acme", "+17770001111", "+15550001111",
                     "local_qwen", "test-model")
    store.add_turn("CAround1", 1, "caller", "my sink is leaking")
    store.add_turn("CAround1", 1, "agent", "I can take a message", ttft_ms=140)
    store.add_turn("CAround1", 2, "keypress", "[keypress: 5]")
    store.end_call("CAround1", "message_taken", "", 2, ["send you"],
                   prompt_tokens=310, completion_tokens=42)

    call = store.get_call("CAround1")
    assert call["profile_key"] == "acme"
    assert call["from_number"] == "+17770001111"
    assert call["brain"] == "local_qwen"
    assert call["model"] == "test-model"
    assert call["outcome"] == "message_taken"
    assert call["caller_turns"] == 2
    assert call["prompt_tokens"] == 310 and call["completion_tokens"] == 42
    assert json.loads(call["overpromise_flags"]) == ["send you"]
    assert call["ended_at"] >= call["started_at"]
    assert call["duration_s"] >= 0
    assert [(t["n"], t["role"], t["text"]) for t in call["turns"]] == [
        (1, "caller", "my sink is leaking"),
        (1, "agent", "I can take a message"),
        (2, "keypress", "[keypress: 5]"),
    ]
    assert call["turns"][1]["ttft_ms"] == 140
    assert call["turns"][0]["ttft_ms"] is None


def test_get_call_is_none_for_an_unknown_call(store):
    assert store.get_call("CAnever") is None


def test_a_turn_for_an_unknown_call_raises(store):
    """A turn with no call row is a lost turn — the foreign key makes it loud."""
    with pytest.raises(sqlite3.Error):
        store.add_turn("CAnever", 1, "caller", "hello")


def test_starting_the_same_call_twice_raises(store):
    store.start_call("CAdup", "acme", "+17770001111", "+15550001111", "b", "m")
    with pytest.raises(sqlite3.Error):
        store.start_call("CAdup", "acme", "+17770001111", "+15550001111", "b", "m")


def test_end_call_stores_ttft_percentiles(store):
    store.start_call("CAperc", "acme", "+17770001111", "+15550001111", "b", "m")
    for i, ttft in enumerate([300, 100, 200, 900], start=1):
        store.add_turn("CAperc", i, "caller", "hi")
        store.add_turn("CAperc", i, "agent", "hello", ttft_ms=ttft)
    store.end_call("CAperc", "message_taken", "", 4, [])

    call = store.get_call("CAperc")
    # nearest-rank over [100, 200, 300, 900]: p50 = 2nd, p95 = 4th
    assert call["ttft_ms_p50"] == 200
    assert call["ttft_ms_p95"] == 900


def test_end_call_without_agent_turns_leaves_percentiles_empty(store):
    store.start_call("CAnottft", "acme", "+17770001111", "+15550001111", "b", "m")
    store.end_call("CAnottft", "caller_hung_up", "", 0, [])
    call = store.get_call("CAnottft")
    assert call["ttft_ms_p50"] is None and call["ttft_ms_p95"] is None


def test_end_call_on_an_unknown_call_raises(store):
    with pytest.raises(KeyError):
        store.end_call("CAnever", "message_taken", "", 1, [])


def test_the_outcome_enum_is_the_spec_list(callstore):
    assert set(callstore.OUTCOMES) == {
        "message_taken", "transferred", "caller_hung_up", "no_info_given",
        "agent_error", "blocked", "rate_limited", "after_hours_message",
    }


def test_an_unknown_outcome_raises(store):
    store.start_call("CAbadout", "acme", "+17770001111", "+15550001111", "b", "m")
    with pytest.raises(ValueError):
        store.end_call("CAbadout", "went_fine", "", 1, [])


def test_update_twilio_records_the_carriers_own_numbers(store):
    _add_call(store, call_sid="CAtw")
    store.update_twilio("CAtw", "completed", 74, "-0.0085")
    call = store.get_call("CAtw")
    assert call["twilio_status"] == "completed"
    assert call["twilio_duration_s"] == 74
    assert call["twilio_price"] == "-0.0085"


def test_update_twilio_on_an_unknown_call_raises(store):
    with pytest.raises(KeyError):
        store.update_twilio("CAnever", "completed", 1, "0")


# ------------------------------------------------------------ list_calls ---

def test_list_calls_hides_test_calls_by_default(store):
    _add_call(store, call_sid="CAreal1", frm="+17770001111")
    _add_call(store, call_sid="CAtest_fixture", frm="+15550001234", is_test=True)

    assert [c["call_sid"] for c in store.list_calls(["acme"])] == ["CAreal1"]
    assert {c["call_sid"] for c in store.list_calls(["acme"], include_test=True)} == {
        "CAreal1", "CAtest_fixture"}


def test_list_calls_is_scoped_to_the_profiles_asked_for(store):
    _add_call(store, call_sid="CAacme", profile="acme")
    _add_call(store, call_sid="CAother", profile="other")
    assert [c["call_sid"] for c in store.list_calls(["other"])] == ["CAother"]
    assert len(store.list_calls(["acme", "other"])) == 2
    assert store.list_calls([]) == []


def test_list_calls_filters_by_window_outcome_and_message(store):
    now = time.time()
    _add_call(store, call_sid="CAold", started=now - 10 * DAY, outcome="no_info_given")
    _add_call(store, call_sid="CAnew", started=now - 1 * DAY, outcome="message_taken")
    store.add_message("CAnew", "acme", "Dana", "+17770002222", None,
                      "wants a quote", "Dana\n+17770002222\nwants a quote")

    recent = store.list_calls(["acme"], since=now - 2 * DAY)
    assert [c["call_sid"] for c in recent] == ["CAnew"]
    assert [c["call_sid"] for c in store.list_calls(["acme"], until=now - 5 * DAY)] == ["CAold"]
    assert [c["call_sid"] for c in store.list_calls(["acme"], outcome="no_info_given")] == ["CAold"]
    assert [c["call_sid"] for c in store.list_calls(["acme"], has_message=True)] == ["CAnew"]
    assert [c["call_sid"] for c in store.list_calls(["acme"], has_message=False)] == ["CAold"]


def test_list_calls_searches_number_sid_and_message_text(store):
    _add_call(store, call_sid="CAsearch1", frm="+17770001111")
    _add_call(store, call_sid="CAsearch2", frm="+17770002222")
    store.add_message("CAsearch2", "acme", "Dana Whitfield", "+17770002222",
                      "dana@example.invalid", "roof estimate", "Dana Whitfield\nroof estimate")

    assert [c["call_sid"] for c in store.list_calls(["acme"], q="0002222")] == ["CAsearch2"]
    assert [c["call_sid"] for c in store.list_calls(["acme"], q="whitfield")] == ["CAsearch2"]
    assert [c["call_sid"] for c in store.list_calls(["acme"], q="search1")] == ["CAsearch1"]
    assert store.list_calls(["acme"], q="nobody-said-this") == []


def test_list_calls_pages_newest_first(store):
    now = time.time()
    for i in range(5):
        _add_call(store, call_sid=f"CApage{i}", started=now - i * DAY)
    page1 = store.list_calls(["acme"], limit=2)
    page2 = store.list_calls(["acme"], limit=2, offset=2)
    assert [c["call_sid"] for c in page1] == ["CApage0", "CApage1"]
    assert [c["call_sid"] for c in page2] == ["CApage2", "CApage3"]


def test_list_calls_reports_the_message_count(store):
    _add_call(store, call_sid="CAmsgcount")
    assert store.list_calls(["acme"])[0]["message_count"] == 0
    store.add_message("CAmsgcount", "acme", "Dana", None, None, None, "note")
    assert store.list_calls(["acme"])[0]["message_count"] == 1


# -------------------------------------------------------------- messages ---

def test_add_message_returns_its_id_and_defaults_to_new(store):
    _add_call(store, call_sid="CAmsg1")
    msg_id = store.add_message("CAmsg1", "acme", "Dana", "+17770002222",
                               "dana@example.invalid", "roof estimate",
                               "Dana\n+17770002222\nroof estimate")
    assert isinstance(msg_id, int) and msg_id > 0
    [msg] = store.list_messages(["acme"])
    assert msg["id"] == msg_id
    assert msg["status"] == "new"
    assert msg["caller_name"] == "Dana"
    assert msg["callback"] == "+17770002222"
    assert msg["email"] == "dana@example.invalid"
    assert msg["need"] == "roof estimate"
    assert msg["review_flag"] == 0
    assert msg["from_number"] == "+17770001111"      # joined from the call
    assert msg["call_sid"] == "CAmsg1"


def test_add_message_for_an_unknown_call_raises(store):
    with pytest.raises(sqlite3.Error):
        store.add_message("CAnever", "acme", "Dana", None, None, None, "note")


def test_list_messages_hides_test_calls_by_default(store):
    _add_call(store, call_sid="CAmsgreal")
    _add_call(store, call_sid="CAtest_msg", frm="+15550001234", is_test=True)
    store.add_message("CAmsgreal", "acme", "Dana", None, None, None, "real")
    store.add_message("CAtest_msg", "acme", "Sarah", None, None, None, "fixture")

    assert [m["summary"] for m in store.list_messages(["acme"])] == ["real"]
    assert len(store.list_messages(["acme"], include_test=True)) == 2


def test_list_messages_can_be_narrowed_to_specific_calls(store):
    """The dashboard looks up the status of ten calls — it must not read every
    message this line has ever taken to do it."""
    for i in range(3):
        _add_call(store, call_sid=f"CAmsgnarrow{i}")
        store.add_message(f"CAmsgnarrow{i}", "acme", "Dana", None, None, None, f"note {i}")

    wanted = ["CAmsgnarrow0", "CAmsgnarrow2"]
    got = store.list_messages(["acme"], call_sids=wanted)
    assert sorted(m["call_sid"] for m in got) == wanted
    assert len(store.list_messages(["acme"], limit=1)) == 1
    assert store.list_messages(["acme"], call_sids=[]) == []
    assert len(store.list_messages(["acme"])) == 3          # unchanged default


def test_set_message_status_moves_it_and_stamps_updated_at(store):
    _add_call(store, call_sid="CAstatus")
    msg_id = store.add_message("CAstatus", "acme", "Dana", None, None, None, "note")
    before = store.list_messages(["acme"])[0]["updated_at"]
    time.sleep(0.01)
    store.set_message_status(msg_id, "in_progress", note="calling her back")
    [msg] = store.list_messages(["acme"], status="in_progress")
    assert msg["status"] == "in_progress"
    assert msg["note"] == "calling her back"
    assert msg["updated_at"] > before
    store.set_message_status(msg_id, "done")
    assert store.list_messages(["acme"], status="new") == []
    assert store.list_messages(["acme"], status="done")[0]["note"] == "calling her back"


def test_set_message_status_refuses_an_unknown_status(store):
    _add_call(store, call_sid="CAstatus2")
    msg_id = store.add_message("CAstatus2", "acme", "Dana", None, None, None, "note")
    with pytest.raises(ValueError):
        store.set_message_status(msg_id, "archived")
    assert store.list_messages(["acme"])[0]["status"] == "new"


def test_set_message_status_on_an_unknown_message_raises(store):
    with pytest.raises(KeyError):
        store.set_message_status(4242, "done")


def test_review_flag_survives(store):
    _add_call(store, call_sid="CAreview")
    store.add_message("CAreview", "acme", None, None, None, None,
                      "the agent may have overpromised", review_flag=True)
    assert store.list_messages(["acme"])[0]["review_flag"] == 1


# ---------------------------------------------------- events + notify log --

def test_add_event_keeps_what_the_ring_forgets(store):
    _add_call(store, call_sid="CAevent")
    store.add_event("acme", "CAevent", "error", "ntfy_push_failed", "2 consecutive: TimeoutError")
    store.add_event("acme", None, "warning", "unhandled_relay_event", "event type 'zzz'")
    with _sql(store.path) as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM events ORDER BY id")]
    assert [r["kind"] for r in rows] == ["ntfy_push_failed", "unhandled_relay_event"]
    assert rows[0]["level"] == "error" and rows[0]["call_sid"] == "CAevent"
    assert rows[1]["call_sid"] is None


def test_an_event_for_an_unknown_call_is_still_kept(store):
    """A scanner's rejected websocket names a CallSid that never existed — the
    event is exactly the one an operator needs, so no foreign key here."""
    store.add_event(None, "CAwho-even-is-this", "error", "ws_auth_rejected", "bad token")
    with _sql(store.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_log_notify_records_both_outcomes(store):
    _add_call(store, call_sid="CAnotify")
    store.log_notify("acme", "ntfy", True, call_sid="CAnotify")
    store.log_notify("acme", "ntfy", False, error="TimeoutError", call_sid="CAnotify")
    with _sql(store.path) as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM notify_log ORDER BY id")]
    assert [r["ok"] for r in rows] == [1, 0]
    assert rows[1]["error"] == "TimeoutError"
    assert rows[0]["target"] == "ntfy"


# ------------------------------------------------------------------ stats --

def _local_noon() -> float:
    """Midday today, local time. Seeding "60 seconds ago" makes a test that
    fails for the two minutes after midnight — from noon, "an hour either way"
    is still the same day everywhere."""
    return datetime.now().astimezone().replace(
        hour=12, minute=0, second=0, microsecond=0).timestamp()


def test_stats_counts_today_and_the_window(store):
    noon = _local_noon()
    _add_call(store, call_sid="CAtoday1", started=noon - 60)
    _add_call(store, call_sid="CAtoday2", started=noon - 120, outcome="no_info_given")
    _add_call(store, call_sid="CAyesterday", started=noon - 1 * DAY)
    _add_call(store, call_sid="CAlastmonth", started=noon - 40 * DAY)
    _add_call(store, call_sid="CAtest_today", started=noon - 60, frm="+15550001234",
              is_test=True)
    store.add_message("CAtoday1", "acme", "Dana", None, None, None, "note")

    stats = store.stats(["acme"], days=7, now=noon)
    assert stats["calls_today"] == 2                 # the fixture call is not one
    assert stats["no_info_today"] == 1
    assert stats["messages_waiting"] == 1
    assert stats["avg_duration_s"] == pytest.approx(30.0)
    assert len(stats["per_day"]) == 7
    today = datetime.fromtimestamp(noon).strftime("%Y-%m-%d")
    assert stats["per_day"][-1] == {"date": today, "calls": 2, "no_info": 1}
    yesterday = datetime.fromtimestamp(noon - DAY).strftime("%Y-%m-%d")
    assert stats["per_day"][-2] == {"date": yesterday, "calls": 1, "no_info": 0}
    assert stats["per_day"][0]["calls"] == 0         # empty days are still days


def test_stats_measures_today_from_the_moment_it_is_given(store):
    """`now` is injectable so the window is a fact, not whatever the clock
    happens to say when the suite runs."""
    noon = _local_noon()
    _add_call(store, call_sid="CAnoon", started=noon)

    assert store.stats(["acme"], days=3, now=noon)["calls_today"] == 1
    later = store.stats(["acme"], days=3, now=noon + 3 * DAY)
    assert later["calls_today"] == 0                 # three days on, not today
    assert [d["calls"] for d in later["per_day"]] == [0, 0, 0]
    assert store.stats(["acme"], days=5, now=noon + 2 * DAY)["per_day"][2]["calls"] == 1


def test_stats_on_an_empty_store(store):
    stats = store.stats(["acme"], days=3)
    assert stats == {"calls_today": 0, "messages_waiting": 0, "no_info_today": 0,
                     "avg_duration_s": None,
                     "per_day": stats["per_day"]}
    assert [d["calls"] for d in stats["per_day"]] == [0, 0, 0]


def test_stats_only_counts_waiting_messages(store):
    _add_call(store, call_sid="CAwaiting")
    first = store.add_message("CAwaiting", "acme", "Dana", None, None, None, "one")
    store.add_message("CAwaiting", "acme", "Ray", None, None, None, "two")
    assert store.stats(["acme"])["messages_waiting"] == 2
    store.set_message_status(first, "done")
    assert store.stats(["acme"])["messages_waiting"] == 1


# -------------------------------------------------------------- retention --

def test_purge_expired_drops_old_transcripts_but_keeps_the_call(store):
    now = time.time()
    old = _add_call(store, call_sid="CAoldcall", started=now - 100 * DAY)
    fresh = _add_call(store, call_sid="CAfreshcall", started=now - 2 * DAY)
    for call_sid in (old, fresh):
        store.add_turn(call_sid, 1, "caller", "my sink is leaking")
        store.add_turn(call_sid, 1, "agent", "I can take a message", ttft_ms=100)
        store.add_message(call_sid, "acme", "Dana", "+17770002222", None,
                          "leaking sink", "Dana\n+17770002222\nleaking sink")
    with _sql(store.path) as conn:
        conn.execute("UPDATE messages SET created_at=? WHERE call_sid=?",
                     (now - 100 * DAY, old))

    assert store.purge_expired("acme", 90) == 2

    assert store.get_call(old) is not None            # the aggregate survives
    assert store.get_call(old)["turns"] == []         # the words do not
    assert len(store.get_call(fresh)["turns"]) == 2
    by_call = {m["call_sid"]: m for m in store.list_messages(["acme"])}
    assert by_call[old]["summary"] is None
    assert by_call[old]["need"] is None
    assert by_call[old]["caller_name"] == "Dana"      # the row itself stays
    assert by_call[fresh]["summary"].startswith("Dana")
    assert store.purge_expired("acme", 90) == 0       # idempotent


def test_purge_expired_is_scoped_to_one_profile(store):
    now = time.time()
    a = _add_call(store, call_sid="CApurgeA", profile="acme", started=now - 100 * DAY)
    b = _add_call(store, call_sid="CApurgeB", profile="other", started=now - 100 * DAY)
    store.add_turn(a, 1, "caller", "hello")
    store.add_turn(b, 1, "caller", "hello")
    assert store.purge_expired("acme", 90) == 1
    assert len(store.get_call(b)["turns"]) == 1


def test_purge_expired_refuses_a_nonsense_horizon(store):
    with pytest.raises(ValueError):
        store.purge_expired("acme", 0)
    with pytest.raises(ValueError):
        store.purge_expired("acme", -5)


# ------------------------------------------------------- the delete path ---

def test_delete_caller_removes_every_row_for_that_number(store):
    victim = "+17770003333"
    keep = "+17770004444"
    store.start_call("CAdel1", "acme", victim, "+15550001111", "b", "m")
    store.add_turn("CAdel1", 1, "caller", "please delete me")
    store.add_turn("CAdel1", 1, "agent", "of course")
    store.end_call("CAdel1", "message_taken", "", 1, [])
    store.add_message("CAdel1", "acme", "Dana", victim, None, "delete me", "Dana")
    store.add_event("acme", "CAdel1", "error", "ntfy_push_failed", "TimeoutError")
    store.log_notify("acme", "ntfy", False, error="TimeoutError", call_sid="CAdel1")
    store.start_call("CAdel2", "acme", victim, "+15550001111", "b", "m")
    store.end_call("CAdel2", "caller_hung_up", "", 0, [])
    _add_call(store, call_sid="CAkeep", frm=keep)

    removed = store.delete_caller(victim)

    # 2 calls + 2 turns + 1 message + 1 event + 1 notify row
    assert int(removed) == 7
    assert sorted(removed.call_sids) == ["CAdel1", "CAdel2"]
    assert store.get_call("CAdel1") is None and store.get_call("CAdel2") is None
    assert store.list_messages(["acme"], include_test=True) == []
    assert store.get_call("CAkeep") is not None
    with _sql(store.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM notify_log").fetchone()[0] == 0


def test_delete_caller_for_an_unknown_number_removes_nothing(store):
    _add_call(store, call_sid="CAstays", frm="+17770001111")
    removed = store.delete_caller("+17770009999")
    assert int(removed) == 0 and removed.call_sids == []
    assert store.get_call("CAstays") is not None


def test_delete_caller_needs_a_number(store):
    with pytest.raises(ValueError):
        store.delete_caller("")


# ------------------------------------------------------- config + sessions --

def test_config_changes_round_trip(store):
    store.record_config_change("owner", "acme: greeting changed", "- old\n+ new", True, "")
    store.record_config_change("owner", "acme: bad toml", "", False, "unparseable TOML")
    rows = store.list_config_changes(10)
    assert [r["summary"] for r in rows] == ["acme: bad toml", "acme: greeting changed"]
    assert rows[0]["applied"] == 0 and rows[0]["reason"] == "unparseable TOML"
    assert rows[1]["applied"] == 1 and rows[1]["actor"] == "owner"
    assert len(store.list_config_changes(1)) == 1


def test_sessions_create_touch_get_delete(store):
    sid = store.create_session("owner")
    assert isinstance(sid, str) and len(sid) >= 32
    session = store.get_session(sid)
    assert session["owner_key"] == "owner"
    time.sleep(0.01)
    store.touch_session(sid)
    assert store.get_session(sid)["last_seen"] > session["last_seen"]
    store.delete_session(sid)
    assert store.get_session(sid) is None
    assert store.get_session("never-issued") is None


def test_delete_owner_sessions_logs_everyone_out(store):
    mine = [store.create_session("owner") for _ in range(3)]
    theirs = store.create_session("second_owner")
    assert store.delete_owner_sessions("owner") == 3
    assert all(store.get_session(s) is None for s in mine)
    assert store.get_session(theirs) is not None


def test_touching_an_unknown_session_raises(store):
    with pytest.raises(KeyError):
        store.touch_session("never-issued")


# ============================================================================
# The service, wired: one real call over a real websocket.
# ============================================================================

def _store_of(line):
    return line.svc.STORE


async def test_a_call_writes_one_row_its_turns_and_one_message(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch) as line:
        await run_call(line, [
            setup_frame(),
            prompt_frame("hi, my sink is leaking"),
            prompt_frame("my number is 555 0100"),
        ])

        store = _store_of(line)
        calls = store.list_calls(["acme"], include_test=True)
        assert len(calls) == 1
        call = store.get_call(calls[0]["call_sid"])
        assert call["profile_key"] == "acme"
        assert call["from_number"] == "+15550001234"
        assert call["is_test"] == 1                   # +1555 fixture caller
        assert call["model"] == "test-model"
        assert call["caller_turns"] == 2
        assert call["outcome"] == "message_taken"
        assert call["ended_at"] is not None

        roles = [t["role"] for t in call["turns"]]
        assert roles == ["caller", "agent", "caller", "agent"]
        assert [t["text"] for t in call["turns"] if t["role"] == "caller"] == [
            "hi, my sink is leaking", "my number is 555 0100"]
        agent_turns = [t for t in call["turns"] if t["role"] == "agent"]
        assert all(isinstance(t["ttft_ms"], int) and t["ttft_ms"] >= 0 for t in agent_turns)
        assert call["ttft_ms_p50"] is not None and call["ttft_ms_p95"] is not None

        messages = store.list_messages(["acme"], include_test=True)
        assert len(messages) == 1
        assert messages[0]["summary"] == line.brain.note
        assert messages[0]["status"] == "new"
        assert messages[0]["call_sid"] == call["call_sid"]


async def test_the_journal_holds_no_caller_text(tmp_path, monkeypatch, caplog):
    """Audit H-7: journald has no retention window and no way to delete one
    caller, so the caller's words must not be in it at all."""
    secret = "my card number is four two four two"
    with caplog.at_level(logging.INFO):
        async with phone_line(tmp_path, monkeypatch) as line:
            await run_call(line, [
                setup_frame(),
                prompt_frame(secret),
                {"type": "dtmf", "digit": "4242"},
            ])
            reply = line.brain.reply
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert secret not in logged
    assert "four two four two" not in logged
    assert "4242" not in logged
    assert reply not in logged                        # nor the agent's words
    assert f"{len(secret)} characters" in logged      # the count IS logged


async def test_a_keypress_is_a_stored_turn(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        await run_call(line, [setup_frame(), {"type": "dtmf", "digit": "5"}])
        store = _store_of(line)
        [call] = store.list_calls(["acme"], include_test=True)
        turns = store.get_call(call["call_sid"])["turns"]
        assert [(t["role"], t["text"]) for t in turns] == [("keypress", "[keypress: 5]")]


async def test_a_call_with_no_words_is_recorded_as_a_hang_up(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        await run_call(line, [setup_frame()])
        store = _store_of(line)
        [call] = store.list_calls(["acme"], include_test=True)
        assert call["outcome"] == "caller_hung_up"
        assert call["caller_turns"] == 0
        assert store.list_messages(["acme"], include_test=True) == []


async def test_a_transfer_is_recorded_as_the_outcome(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          cfg_extra='forward_to = "+15550002222"\n') as line:
        line.brain.reply = "Connecting you now. [TRANSFER CALL]"
        await run_call(line, [setup_frame(), prompt_frame("let me speak to a person")],
                       settle=3.0)
        store = _store_of(line)
        [call] = store.list_calls(["acme"], include_test=True)
        assert call["outcome"] == "transferred"
        assert call["decision_reason"] == "transfer"


REAL_CALL_SID = "CA00000000000000000000000000000001"
REAL_CALLER = "+17770001111"


async def test_a_no_message_call_writes_no_message_row(tmp_path, monkeypatch):
    """A call that left nothing to act on is not a message. A row here would
    sit in the owner's list at "new" forever and inflate messages-waiting —
    the note goes to the call's events instead, where the detail can show it.
    (A real caller, not a +1555 fixture, so it reaches the dashboard numbers.)"""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        line.brain.note = "No message — caller asked what services are offered."
        await run_call(line, [setup_frame(REAL_CALL_SID, REAL_CALLER),
                              prompt_frame("what do you do")],
                       call_sid=REAL_CALL_SID)
        store = _store_of(line)
        [call] = store.list_calls(["acme"])
        assert call["outcome"] == "no_info_given"
        assert store.list_messages(["acme"]) == []

        with _sql(store.path) as conn:
            notes = [dict(r) for r in conn.execute(
                "SELECT * FROM events WHERE kind = 'no_info_note'")]
        assert len(notes) == 1
        assert notes[0]["detail"].startswith("No message")
        assert notes[0]["call_sid"] == REAL_CALL_SID
        assert len(notes[0]["detail"]) <= line.svc.MAX_EVENT_DETAIL_CHARS

        stats = store.stats(["acme"])
        assert stats["messages_waiting"] == 0
        assert stats["no_info_today"] == 1


async def test_the_message_row_carries_what_the_summarizer_found(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        line.brain.note = ("Caller: Dana Whitfield\nCallback: +17770002222\n"
                           "dana@example.invalid\nNeeds a quote for a new roof.")
        await run_call(line, [setup_frame(), prompt_frame("i need a roof quote")])
        [msg] = _store_of(line).list_messages(["acme"], include_test=True)
        assert msg["caller_name"] == "Dana Whitfield"
        assert msg["callback"] == "+17770002222"
        assert msg["email"] == "dana@example.invalid"
        assert msg["need"] == "Needs a quote for a new roof."
        assert msg["summary"] == line.brain.note      # the note is kept whole


async def test_a_failed_summary_is_flagged_for_review(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        line.brain.chat_status = 200

        async def boom(*args, **kwargs):
            raise RuntimeError("summarizer down")

        monkeypatch.setattr(line.svc, "summarize_call", boom)
        await run_call(line, [setup_frame(), prompt_frame("hello")], drain=False)
        [msg] = _store_of(line).list_messages(["acme"], include_test=True)
        assert msg["review_flag"] == 1
        assert "MESSAGE EXTRACTION FAILED" in msg["summary"]


async def test_events_and_pushes_are_stored_too(tmp_path, monkeypatch):
    async with phone_line(tmp_path, monkeypatch) as line:
        line.ntfy.status = 500
        await run_call(line, [setup_frame(), prompt_frame("hello"), "not json"])
        store = _store_of(line)
        with _sql(store.path) as conn:
            kinds = [r["kind"] for r in conn.execute("SELECT kind FROM events")]
            pushes = [dict(r) for r in conn.execute("SELECT * FROM notify_log")]
        assert "relay_event_failed" in kinds
        assert "ntfy_push_failed" in kinds
        assert pushes and pushes[0]["ok"] == 0
        [call] = store.list_calls(["acme"], include_test=True)
        assert call["notify_status"] == "failed"


async def test_a_broken_store_never_costs_the_caller_their_call(tmp_path, monkeypatch, caplog):
    """The store is the record, not the product. If SQLite dies mid-call the
    caller still gets answered and the owner still gets the message — loudly."""
    async with phone_line(tmp_path, monkeypatch) as line:
        line.svc.STORE.close()                        # every write from here raises
        with caplog.at_level(logging.ERROR):
            await run_call(line, [setup_frame(), prompt_frame("hello")])
        assert line.pad.exists()                      # the message still landed
        assert line.brain.note in line.pad.read_text(encoding="utf-8")
        assert "store_write_failed" in "\n".join(r.getMessage() for r in caplog.records)


async def test_repeated_events_collapse_in_the_ring_but_not_in_the_store(tmp_path, monkeypatch):
    """A scanner hammering the relay must not flush the ring the dashboard
    reads — but every attempt still belongs in the store."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        svc.RECENT_EVENTS.clear()
        for _ in range(5):
            svc.record_event("error", "ws_auth_rejected", "bad token", "CAtest_scan")
        ring = [e for e in svc.RECENT_EVENTS if e["kind"] == "ws_auth_rejected"]
        assert len(ring) == 1
        assert ring[0]["count"] == 5
        with _sql(svc.STORE.path) as conn:
            stored = conn.execute(
                "SELECT COUNT(*) FROM events WHERE kind='ws_auth_rejected'").fetchone()[0]
        assert stored == 5

        svc.record_event("error", "pad_write_failed", "different kind", "CAtest_scan")
        assert svc.RECENT_EVENTS[-1]["kind"] == "pad_write_failed"


async def test_the_data_dir_and_the_database_are_private(tmp_path, monkeypatch):
    """The directory AND the file. sqlite creates its database with the
    process umask — usually 0644 — so a transcript store that only chmods the
    directory is still world-readable on a box with other accounts."""
    data_dir = tmp_path / "phone-data-perm"
    async with phone_line(tmp_path, monkeypatch, ntfy=False,
                          extra_env={"PHONE_DATA_DIR": str(data_dir)}) as line:
        assert line.svc.PHONE_DATA_DIR == str(data_dir)
        assert oct(data_dir.stat().st_mode & 0o777) == "0o700"
        assert oct((data_dir / "calls.db").stat().st_mode & 0o777) == "0o600"


def test_a_loose_data_dir_is_tightened_at_boot(tmp_path, monkeypatch, caplog):
    """A directory and database left readable by an earlier release (or made
    by hand) are tightened on the NEXT boot, loudly — not only on the boot
    that created them."""
    from test_phone_agent_plugin import _import_service

    data_dir = tmp_path / "loose-data"
    data_dir.mkdir(mode=0o755)
    db = data_dir / "calls.db"
    seed = _load("callstore").CallStore(str(db))
    seed.close()
    db.chmod(0o644)
    data_dir.chmod(0o755)

    with caplog.at_level(logging.WARNING):
        _import_service(tmp_path, monkeypatch,
                        extra_env={"PHONE_DATA_DIR": str(data_dir)})

    assert oct(data_dir.stat().st_mode & 0o777) == "0o700"
    assert oct(db.stat().st_mode & 0o777) == "0o600"
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "tightened to 0700" in logged
    assert "tightened to 0600" in logged


def test_the_bridge_refuses_to_start_without_a_usable_data_dir(tmp_path, monkeypatch):
    """Fail-closed at boot, in the style of every other refusal here: a bridge
    that answers calls and records nothing is the bug this task removes."""
    from test_phone_agent_plugin import _import_service

    blocker = tmp_path / "not-a-dir"
    blocker.write_text("i am a file", encoding="utf-8")
    with pytest.raises(SystemExit):
        _import_service(tmp_path, monkeypatch,
                        extra_env={"PHONE_DATA_DIR": str(blocker / "data")})


# ============================================================================
# migrate_pad.py — the 21 Markdown entries that were the only record.
# ============================================================================

PAD_FIXTURE = """# Phone messages — Atlas phone agent

## 2026-07-22 07:25 EDT — Acme Co line — call from +17770001111
Dana Whitfield
+17770001111
Needs a quote for a new roof.
*(CallSid CA4116a2657c8da7bb1ad79843aee3af4a, 4 caller turns — full transcript in `journalctl --user -u atlas-phone-bridge`)*

## 2026-07-26 07:37 EDT — Acme Co line — call from +17770002222
> Caller-derived text.
No message — caller hung up without leaving a message.
*(CallSid CAtest_end_1785065838, 1 caller turns — full transcript in `journalctl --user -u atlas-phone-bridge`)*

## 2026-08-02 15:01 EDT — Acme Co line — call from +15550001234
Ray Iverson
+15550001234
Interested in a service plan.
*(CallSid CA192d4074a69a5c0904e4a6ac43ad9904, 7 caller turns — full transcript in `journalctl --user -u atlas-phone-bridge`)*
"""


@pytest.fixture
def pad_file(tmp_path) -> Path:
    pad = tmp_path / "pad.md"
    pad.write_text(PAD_FIXTURE, encoding="utf-8")
    return pad


def test_migrate_pad_imports_every_entry(migrate_pad, callstore, pad_file, db_path, capsys):
    imported = migrate_pad.main(["--pad", str(pad_file), "--db", db_path,
                                 "--profile", "acme"])
    assert imported == 0

    store = callstore.CallStore(db_path)
    try:
        messages = store.list_messages(["acme"], include_test=True)
        assert len(messages) == 3
        calls = store.list_calls(["acme"], include_test=True)
        assert len(calls) == 3
        by_sid = {m["call_sid"]: m for m in messages}
        real = by_sid["CA4116a2657c8da7bb1ad79843aee3af4a"]
        assert real["from_number"] == "+17770001111"
        assert "Needs a quote for a new roof." in real["summary"]
        assert store.get_call(real["call_sid"])["caller_turns"] == 4
        assert store.get_call(real["call_sid"])["is_test"] == 0
        assert store.get_call(real["call_sid"])["outcome"] == "message_taken"
        # the '> Caller-derived text.' line is a pad convention, not the message
        assert not by_sid["CAtest_end_1785065838"]["summary"].startswith(">")
        assert store.get_call("CAtest_end_1785065838")["outcome"] == "no_info_given"
    finally:
        store.close()


def test_migrate_pad_flags_the_fixture_entries(migrate_pad, callstore, pad_file, db_path):
    migrate_pad.main(["--pad", str(pad_file), "--db", db_path, "--profile", "acme"])
    store = callstore.CallStore(db_path)
    try:
        flags = {c["call_sid"]: c["is_test"]
                 for c in store.list_calls(["acme"], include_test=True)}
    finally:
        store.close()
    assert flags["CA4116a2657c8da7bb1ad79843aee3af4a"] == 0     # a real caller
    assert flags["CAtest_end_1785065838"] == 1                  # CAtest…
    assert flags["CA192d4074a69a5c0904e4a6ac43ad9904"] == 1      # +1555…


def test_migrate_pad_is_idempotent(migrate_pad, callstore, pad_file, db_path, capsys):
    migrate_pad.main(["--pad", str(pad_file), "--db", db_path, "--profile", "acme"])
    capsys.readouterr()
    migrate_pad.main(["--pad", str(pad_file), "--db", db_path, "--profile", "acme"])
    out = capsys.readouterr().out
    assert "skipped (already imported): 3" in out
    store = callstore.CallStore(db_path)
    try:
        assert len(store.list_messages(["acme"], include_test=True)) == 3
    finally:
        store.close()


def test_migrate_pad_dry_run_writes_nothing(migrate_pad, callstore, pad_file, db_path, capsys):
    migrate_pad.main(["--pad", str(pad_file), "--db", db_path, "--profile", "acme",
                      "--dry-run"])
    out = capsys.readouterr().out
    assert "would import: 3" in out
    store = callstore.CallStore(db_path)
    try:
        assert store.list_messages(["acme"], include_test=True) == []
    finally:
        store.close()


def test_migrate_pad_prints_counts_and_no_caller_details(migrate_pad, pad_file,
                                                         db_path, capsys):
    migrate_pad.main(["--pad", str(pad_file), "--db", db_path, "--profile", "acme"])
    out = capsys.readouterr().out
    assert "entries found: 3" in out
    assert "imported: 3" in out
    assert "flagged as test: 2" in out
    for detail in ("Dana", "Whitfield", "roof", "+17770001111", "Ray", "Iverson"):
        assert detail not in out


def test_migrate_pad_names_a_callsid_that_appears_twice(migrate_pad, tmp_path,
                                                        db_path, capsys):
    """The live pad really does hold one call summarized twice. On a FIRST run
    that must not be reported as "already imported" — nothing was."""
    pad = tmp_path / "twice.md"
    repeat = PAD_FIXTURE.split("## ")[2]           # the CAtest_end entry again
    pad.write_text(PAD_FIXTURE + "\n## " + repeat, encoding="utf-8")
    migrate_pad.main(["--pad", str(pad), "--db", db_path, "--profile", "acme"])
    out = capsys.readouterr().out
    assert "entries found: 4" in out
    assert "imported: 3" in out
    assert "skipped (already imported): 0" in out
    assert "skipped (same CallSid twice in the pad): 1" in out


def test_migrate_pad_never_touches_the_pad(migrate_pad, pad_file, db_path):
    before = pad_file.read_bytes()
    mtime = pad_file.stat().st_mtime
    migrate_pad.main(["--pad", str(pad_file), "--db", db_path, "--profile", "acme"])
    assert pad_file.read_bytes() == before
    assert pad_file.stat().st_mtime == mtime


def test_migrate_pad_refuses_a_missing_pad(migrate_pad, tmp_path, db_path, capsys):
    rc = migrate_pad.main(["--pad", str(tmp_path / "nope.md"), "--db", db_path,
                           "--profile", "acme"])
    assert rc == 2
    assert "cannot read" in capsys.readouterr().err


def test_migrate_pad_reports_entries_it_cannot_parse(migrate_pad, tmp_path, db_path, capsys):
    """A pad entry with no CallSid footer has nothing to be idempotent about —
    it must be reported, never silently dropped."""
    pad = tmp_path / "broken.md"
    pad.write_text(PAD_FIXTURE + "\n## 2026-08-03 09:00 EDT — Acme Co line — "
                   "call from +17770005555\nsomething\n", encoding="utf-8")
    rc = migrate_pad.main(["--pad", str(pad), "--db", db_path, "--profile", "acme"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "unparseable (no CallSid): 1" in out


# ============================================================================
# What can be read out of a summarizer note — and what must NOT be guessed.
# ============================================================================

NOTE_CASES = [
    (
        "a labelled note gives every column",
        "Caller: Dana Whitfield\nCallback: +17770002222\n"
        "dana@example.invalid\nNeeds a quote for a new roof.",
        {"caller_name": "Dana Whitfield", "callback": "+17770002222",
         "email": "dana@example.invalid", "need": "Needs a quote for a new roof."},
    ),
    (
        "labels in a different order are the same note",
        "Needs: a roof quote\nName: Ray Iverson\nPhone: +17770003333",
        {"caller_name": "Ray Iverson", "callback": "+17770003333",
         "email": None, "need": "a roof quote"},
    ),
    (
        "a bare line is a need, never a name",
        "Wants pricing",
        {"caller_name": None, "callback": None, "email": None, "need": "Wants pricing"},
    ),
    (
        "a note that opens by saying what is missing",
        "The caller did not give a name.\nWants a quote for a new roof.",
        {"caller_name": None, "callback": None, "email": None,
         "need": "Wants a quote for a new roof."},
    ),
    (
        "when every line says what is missing, keep the last one",
        "No callback number was given.\nThe caller did not leave a name.",
        {"caller_name": None, "callback": None, "email": None,
         "need": "The caller did not leave a name."},
    ),
    (
        "an email is contact information all by itself",
        "dana@example.invalid",
        {"caller_name": None, "callback": None, "email": "dana@example.invalid",
         "need": None},
    ),
    (
        "a name stated in words",
        "The caller's name is Ray Iverson.\nWants a callback tomorrow morning.",
        {"caller_name": "Ray Iverson", "callback": None, "email": None,
         "need": "Wants a callback tomorrow morning."},
    ),
    (
        "a bare number line is the callback",
        "+17770002222\nNeeds someone to call back about a leak.",
        {"caller_name": None, "callback": "+17770002222", "email": None,
         "need": "Needs someone to call back about a leak."},
    ),
    (
        "a No message note yields nothing",
        "No message — caller asked what services are offered.",
        {"caller_name": None, "callback": None, "email": None, "need": None},
    ),
    (
        "an empty note yields nothing",
        "",
        {"caller_name": None, "callback": None, "email": None, "need": None},
    ),
    (
        "the four labelled lines the prompt asks for",
        "Name: Dana Whitfield\nCallback: +17770002222\n"
        "Email: dana@example.invalid\nNeed: A quote for a new roof.",
        {"caller_name": "Dana Whitfield", "callback": "+17770002222",
         "email": "dana@example.invalid", "need": "A quote for a new roof."},
    ),
    (
        "unknown is the prompt's word for nothing, not a value",
        "Name: unknown\nCallback: unknown\nEmail: unknown\nNeed: unknown",
        {"caller_name": None, "callback": None, "email": None, "need": None},
    ),
    (
        "a name in a sentence never swallows the rest of the clause",
        "Her name is Dana Whitfield and she wants a roof quote.",
        {"caller_name": "Dana Whitfield", "callback": None, "email": None,
         "need": "Her name is Dana Whitfield and she wants a roof quote."},
    ),
    (
        "an unlabelled note keeps its request, not its first line",
        "Dana Whitfield\n+17770002222\nNeeds a quote for a new roof.",
        {"caller_name": None, "callback": "+17770002222", "email": None,
         "need": "Needs a quote for a new roof."},
    ),
    (
        "the pad's caller-derived marker is not the message",
        "> Caller-derived text.\nWants a quote",
        {"caller_name": None, "callback": None, "email": None, "need": "Wants a quote"},
    ),
]


@pytest.mark.parametrize("note, expected", [(c[1], c[2]) for c in NOTE_CASES],
                         ids=[c[0] for c in NOTE_CASES])
def test_parse_message_fields(tmp_path, monkeypatch, note, expected):
    """Guessing a name out of an unlabelled first line put "Wants pricing" in
    the column where the owner expects a person. A name now comes only from a
    label or from the summarizer saying so in words."""
    from test_phone_agent_plugin import _import_service

    svc = _import_service(tmp_path, monkeypatch)
    assert svc.parse_message_fields(note) == expected


async def test_an_email_only_note_is_a_message_not_a_no_info_call(tmp_path, monkeypatch):
    """An email address IS something to act on — that call must reach the
    owner's message list, not the no-info pile."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        line.brain.note = "dana@example.invalid"
        await run_call(line, [setup_frame(), prompt_frame("email me a quote")])
        store = _store_of(line)
        [call] = store.list_calls(["acme"], include_test=True)
        assert call["outcome"] == "message_taken"
        [msg] = store.list_messages(["acme"], include_test=True)
        assert msg["email"] == "dana@example.invalid"


# ============================================================================
# Nothing owner-facing may promise a transcript the journal no longer holds.
# ============================================================================

def test_the_pad_entry_does_not_send_the_owner_to_the_journal(tmp_path, monkeypatch):
    from test_phone_agent_plugin import _import_service

    svc = _import_service(tmp_path, monkeypatch)
    entry = svc.format_message_entry(
        when="2026-08-27 09:15 EDT", business_name="Acme Co",
        caller_id="+17770001111", note="Wants a quote", call_sid="CAtest_footer",
        turns=3,
    )
    assert "journal" not in entry.lower()
    assert "transcript in the dashboard" in entry
    assert "CAtest_footer" in entry and "3 caller turns" in entry


async def test_the_failure_note_does_not_send_the_owner_to_the_journal(tmp_path,
                                                                       monkeypatch):
    """That note is read three times over — on the pad, in the push, and in the
    dashboard's message list — so it must name a place the transcript is."""
    async with phone_line(tmp_path, monkeypatch) as line:
        async def boom(*args, **kwargs):
            raise RuntimeError("summarizer down")

        monkeypatch.setattr(line.svc, "summarize_call", boom)
        await run_call(line, [setup_frame(), prompt_frame("hello")], drain=False)

        pad = line.pad.read_text(encoding="utf-8")
        [msg] = _store_of(line).list_messages(["acme"], include_test=True)
        push = line.ntfy.pushes[0]["body"]
        for text in (pad, msg["summary"], push):
            assert "MESSAGE EXTRACTION FAILED" in text
            assert "journal" not in text.lower()
        assert "in the dashboard" in msg["summary"]


# ============================================================================
# The dashboard's "Recent calls" panel — read from the store, not a log grep.
# ============================================================================

async def _admin_page(tmp_path, svc, patch=None) -> str:
    """Serve the real dashboard on loopback and fetch the real page."""
    import aiohttp
    from aiohttp import web

    admin = _load("admin")
    if patch is not None:
        patch(admin)

    async def snapshot():
        return {"bridge": "ok", "model_backend": "ok", "model": "m", "brain": "b",
                "profiles": ["acme"], "numbers": 1, "ntfy": "off"}, True

    app = admin.build_admin_app(
        token="sesame", health_snapshot=snapshot,
        get_state=lambda: (svc.NUMBERS, svc.PROFILES),
        get_brains=lambda: ({}, ""),
        get_prompts=lambda: svc.SYSTEM_PROMPTS,
        apply_config_text=svc.apply_config_text,
        emit_business_toml=svc.emit_business_toml,
        messages_file=str(tmp_path / "no-messages-yet.md"),
        known_keys=svc._PROFILE_KNOWN_KEYS,
        store=svc.STORE,
    )
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    port = runner.addresses[0][1]
    try:
        async with aiohttp.ClientSession() as session:
            session.cookie_jar.update_cookies({admin.COOKIE: "sesame"})
            async with session.get(f"http://127.0.0.1:{port}/") as resp:
                # 200 is part of every assertion here: a panel that raises must
                # not turn the owner's dashboard into a 500 page.
                assert resp.status == 200, await resp.text()
                return await resp.text()
    finally:
        await runner.cleanup()


async def test_recent_calls_panel_shows_the_stored_call(tmp_path, monkeypatch):
    """The panel used to grep journald for two log formats the bridge stopped
    writing, so a line answering calls all day printed "(no calls in the
    recent journal)" — a dashboard stating something false."""
    from test_phone_agent_plugin import _import_service

    svc = _import_service(tmp_path, monkeypatch)
    store = svc.STORE
    store.start_call(REAL_CALL_SID, "acme", REAL_CALLER, "+15550001111",
                     "local_qwen", "test-model")
    store.add_turn(REAL_CALL_SID, 1, "caller", "my sink is leaking")
    store.add_turn(REAL_CALL_SID, 1, "agent", "I can take a message for Jo")
    store.end_call(REAL_CALL_SID, "message_taken", "", 1, [])
    store.add_message(REAL_CALL_SID, "acme", "Dana", REAL_CALLER, None,
                      "leaking sink", "Dana\nleaking sink")

    page = await _admin_page(tmp_path, svc)

    assert "my sink is leaking" in page                  # the transcript is there
    assert "I can take a message for Jo" in page
    assert "Caller:" in page and "Atlas:" in page
    assert "message_taken" in page and "message: new" in page
    assert "journal" not in page.lower()                 # no stale promise
    assert "No calls recorded yet." not in page
    assert REAL_CALLER not in page                       # the number is masked
    assert "1111" in page                                # …still recognisable


async def test_recent_calls_panel_is_honest_when_there_are_no_calls(tmp_path,
                                                                    monkeypatch):
    from test_phone_agent_plugin import _import_service

    svc = _import_service(tmp_path, monkeypatch)
    page = await _admin_page(tmp_path, svc)
    assert "No calls recorded yet." in page
    assert "journal" not in page.lower()


async def test_recent_calls_panel_hides_test_calls(tmp_path, monkeypatch):
    """A demo call must not look like business on the owner's own screen."""
    from test_phone_agent_plugin import _import_service

    svc = _import_service(tmp_path, monkeypatch)
    svc.STORE.start_call("CAtest_demo", "acme", "+15550001234", "+15550001111",
                         "b", "m", is_test=True)
    svc.STORE.add_turn("CAtest_demo", 1, "caller", "this is only a demo call")
    svc.STORE.end_call("CAtest_demo", "message_taken", "", 1, [])

    page = await _admin_page(tmp_path, svc)
    assert "this is only a demo call" not in page
    assert "No calls recorded yet." in page


def test_the_summarizer_is_asked_for_labelled_lines(tmp_path, monkeypatch):
    """The parser's happy path is a labelled note, so the prompt has to ask
    for one — free prose is what put a whole clause in the name column."""
    from test_phone_agent_plugin import _import_service

    svc = _import_service(tmp_path, monkeypatch)
    prompt = svc.SUMMARIZER_PROMPT
    for label in ("Name:", "Callback:", "Email:", "Need:"):
        assert label in prompt
    assert "unknown" in prompt
    assert "No message" in prompt                     # the no-info escape survives
    assert svc.TRANSCRIPT_FENCE_OPEN in prompt        # and the injection fence


async def test_a_broken_store_does_not_take_the_dashboard_down(tmp_path, monkeypatch):
    """The recent-calls panel is one card on a page whose main job is editing
    the config. A store read that raised used to 500 the whole dashboard —
    including the page that tells the owner why a save was rejected."""
    from test_phone_agent_plugin import _import_service

    svc = _import_service(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(svc.STORE, "list_calls", boom)
    page = await _admin_page(tmp_path, svc)

    assert "Could not read recent calls: OperationalError: database is locked" in page
    assert "profile: acme" in page                    # the config form still renders
    assert "name='acme::greeting'" in page


# ============================================================================
# The caller ID the phone network gave us, where the owner needs it.
# ============================================================================

async def test_the_push_carries_the_caller_id(tmp_path, monkeypatch):
    """The push is read without the pad entry's header around it, and the
    summarizer is told not to copy the caller ID into its Callback line — so
    a caller who stated no number used to reach the owner's phone as
    "Callback: unknown" while we held the number all along."""
    async with phone_line(tmp_path, monkeypatch) as line:
        line.brain.note = ("Name: Dana Whitfield\nCallback: unknown\n"
                           "Email: unknown\nNeed: A quote for a new roof.")
        await run_call(line, [setup_frame(), prompt_frame("i need a roof quote")])

        push = line.ntfy.pushes[0]["body"]
        assert push.startswith("From: +15550001234 — Acme Co line\n")
        assert "A quote for a new roof." in push          # the note is intact
        assert line.brain.note in line.pad.read_text(encoding="utf-8")


async def test_the_message_row_falls_back_to_the_caller_id(tmp_path, monkeypatch):
    """The dashboard's call-back link always needs a number."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        line.brain.note = ("Name: Dana Whitfield\nCallback: unknown\n"
                           "Email: unknown\nNeed: A quote for a new roof.")
        await run_call(line, [setup_frame(), prompt_frame("i need a roof quote")])

        [msg] = _store_of(line).list_messages(["acme"], include_test=True)
        assert msg["callback"] == "+15550001234"          # the caller ID
        assert msg["caller_name"] == "Dana Whitfield"
        assert msg["summary"] == line.brain.note          # the note is unchanged


async def test_the_caller_id_alone_is_still_a_nothing_call(tmp_path, monkeypatch):
    """The no-info decision runs on the summarizer's fields ONLY: a call where
    the caller said nothing must not become a message just because the phone
    network knew their number."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        line.brain.note = ("Name: unknown\nCallback: unknown\n"
                           "Email: unknown\nNeed: unknown")
        await run_call(line, [setup_frame(REAL_CALL_SID, REAL_CALLER),
                              prompt_frame("hello?")],
                       call_sid=REAL_CALL_SID)

        store = _store_of(line)
        [call] = store.list_calls(["acme"])
        assert call["outcome"] == "no_info_given"
        assert store.list_messages(["acme"]) == []
        assert store.stats(["acme"])["messages_waiting"] == 0


async def test_an_unreadable_pad_does_not_take_the_dashboard_down(tmp_path, monkeypatch):
    """Same failure class as the calls panel: the pad read caught only
    FileNotFoundError, so a permission problem 500'd the page that tells the
    owner why their config save was rejected."""
    from test_phone_agent_plugin import _import_service

    svc = _import_service(tmp_path, monkeypatch)

    def denied(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    page = await _admin_page(
        tmp_path, svc,
        patch=lambda admin: monkeypatch.setattr(admin, "open", denied, raising=False),
    )
    assert "Could not read the message pad: PermissionError:" in page
    assert "profile: acme" in page                        # the config form survives
    assert "name='acme::greeting'" in page

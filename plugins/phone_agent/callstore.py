#!/usr/bin/env python3
"""The record of what happened on the phone line — one SQLite file.

Before this module the only record of a call was a journald INFO line holding
the caller's verbatim words: no retention window, no way to delete one
caller's data when they ask, and a dashboard whose "call log" was a journalctl
grep that returned nothing (audit H-7, M-1). This is the replacement. From
here on the journal carries CallSid and counts; the words live here, where
they can be shown, aged out, and deleted.

Design rules, deliberately narrow:

  * stdlib `sqlite3` only. This runs on the same box as the bridge and must
    keep working after an OS upgrade with nobody watching.
  * ONE connection per CallStore instance (`check_same_thread=False`, guarded
    by a lock), every write inside `with conn:` so a half-written call rolls
    back instead of lingering.
  * EVERY method raises on failure. The store never decides how loud a problem
    is — the service does, because only the service knows whether a caller is
    on the line. There is no `except: pass` in this file.
  * Test rows are flagged, not hidden: `is_test_call()` marks the fixture
    calls ("Sarah from Rose Bakery", CAtest…, +1555…) so they can never sit in
    the owner's message list looking like paying customers.

Retention and deletion:
  * `purge_expired(profile_key, retention_days)` drops the WORDS (turns, the
    free-text message summary/need, and the `no_info_note` events that hold a
    summary of a call which left no message) past the horizon and keeps the
    aggregates — the owner's call counts and outcomes survive forever, the
    transcripts do not.
  * `delete_caller(from_number)` is the CCPA/GDPR path: every row for that
    number goes.
"""

import json
import math
import os
import secrets
import sqlite3
import threading
import time

# The outcome vocabulary from the design spec (§3.4). `blocked`,
# `rate_limited` and `after_hours_message` belong to the gate work that lands
# next; they are defined here so the column's meaning never depends on which
# version of the service wrote the row.
OUTCOMES = (
    "message_taken",
    "transferred",
    "caller_hung_up",
    "no_info_given",
    "agent_error",
    "blocked",
    "rate_limited",
    "after_hours_message",
)
MESSAGE_STATUSES = ("new", "in_progress", "done")
# A keypress is its own role: it is a caller turn for conversation purposes,
# but it is digits off a keypad — the owner reading a transcript must be able
# to tell the difference at a glance.
TURN_ROLES = ("caller", "agent", "keypress")

DAY_SECONDS = 86400

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    call_sid          TEXT PRIMARY KEY,
    profile_key       TEXT NOT NULL,
    from_number       TEXT NOT NULL DEFAULT '',
    to_number         TEXT NOT NULL DEFAULT '',
    started_at        REAL NOT NULL,
    ended_at          REAL,
    duration_s        REAL,
    caller_turns      INTEGER NOT NULL DEFAULT 0,
    outcome           TEXT,
    decision_reason   TEXT,
    brain             TEXT,
    model             TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    ttft_ms_p50       INTEGER,
    ttft_ms_p95       INTEGER,
    overpromise_flags TEXT,
    notify_status     TEXT,
    twilio_status     TEXT,
    twilio_duration_s INTEGER,
    twilio_price      TEXT,
    is_test           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS calls_profile_started
    ON calls (profile_key, started_at DESC);
CREATE INDEX IF NOT EXISTS calls_from_number ON calls (from_number);

CREATE TABLE IF NOT EXISTS turns (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    call_sid TEXT NOT NULL REFERENCES calls (call_sid) ON DELETE CASCADE,
    n        INTEGER NOT NULL,
    role     TEXT NOT NULL,
    text     TEXT NOT NULL,
    ts       REAL NOT NULL,
    ttft_ms  INTEGER
);
CREATE INDEX IF NOT EXISTS turns_call ON turns (call_sid, n, id);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_sid    TEXT NOT NULL REFERENCES calls (call_sid) ON DELETE CASCADE,
    profile_key TEXT NOT NULL,
    caller_name TEXT,
    callback    TEXT,
    email       TEXT,
    need        TEXT,
    summary     TEXT,
    status      TEXT NOT NULL DEFAULT 'new',
    note        TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    review_flag INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS messages_profile_status
    ON messages (profile_key, status, created_at DESC);
CREATE INDEX IF NOT EXISTS messages_call ON messages (call_sid);

-- No foreign key on events.call_sid ON PURPOSE: the most important event this
-- table holds is a rejected websocket, whose CallSid is whatever the peer put
-- in the URL and belongs to no call at all. A constraint here would throw the
-- one event an operator needs away.
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    profile_key TEXT,
    call_sid    TEXT,
    level       TEXT NOT NULL,
    kind        TEXT NOT NULL,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts DESC);
CREATE INDEX IF NOT EXISTS events_call ON events (call_sid);

CREATE TABLE IF NOT EXISTS config_changes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    actor   TEXT,
    summary TEXT,
    diff    TEXT,
    applied INTEGER NOT NULL DEFAULT 0,
    reason  TEXT
);

CREATE TABLE IF NOT EXISTS notify_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    profile_key TEXT,
    call_sid    TEXT,
    target      TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS notify_log_call ON notify_log (call_sid);

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    owner_key  TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_seen  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_owner ON sessions (owner_key);
"""


def is_test_call(call_sid, from_number) -> bool:
    """True for calls that were never a customer.

    Every test call this project has ever made used a `CAtest…` CallSid or a
    +1555 reserved-for-fiction number. Rows flagged here stay out of the
    owner's message list and out of the numbers on the dashboard — the point
    is that "Sarah from Rose Bakery" can never again read as a real lead.
    """
    return (str(call_sid or "").startswith("CAtest")
            or str(from_number or "").startswith("+1555"))


def _percentile(values: list, pct: float):
    """Nearest-rank percentile of an ALREADY SORTED list; None when empty.

    Nearest-rank (not interpolation) because these are milliseconds a real
    caller waited: p95 should name a wait that actually happened.
    """
    if not values:
        return None
    rank = max(1, math.ceil(pct / 100.0 * len(values)))
    return values[min(rank, len(values)) - 1]


def _row_id(cursor: sqlite3.Cursor) -> int:
    """The id SQLite just assigned. A successful INSERT always has one; if it
    somehow does not, the caller is about to hand a null id to a dashboard —
    say so instead of returning a number that means nothing."""
    if cursor.lastrowid is None:
        raise RuntimeError("the insert reported no row id")
    return int(cursor.lastrowid)


def _like(term: str) -> str:
    """A LIKE pattern that treats the user's % and _ as literal characters."""
    escaped = str(term).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class Deletion(int):
    """How many rows a delete removed — and which calls they belonged to.

    It IS the row count, so `removed = store.delete_caller(n)` reads and
    compares like the integer the interface promises. It also carries
    `call_sids`, because the Markdown message pad is append-only text this
    store cannot edit: the dashboard shows those CallSids so the owner knows
    exactly which pad entries still need redacting by hand.
    """

    call_sids: list

    def __new__(cls, rows: int, call_sids):
        self = super().__new__(cls, rows)
        self.call_sids = list(call_sids)
        return self


class CallStore:
    """One SQLite file: calls, turns, messages, events, config changes,
    notification attempts and dashboard sessions.

    Raises on everything. A caller that wants to survive a broken store must
    say so out loud in its own log — see service.record_event.
    """

    def __init__(self, path: str) -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        # check_same_thread=False: the bridge and the dashboard live in one
        # asyncio loop today, but a future thread must not silently corrupt
        # anything — the lock below is what actually serialises access.
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        try:
            # WAL: a reader (dashboard) and the writer (a live call) must never
            # block each other; a blocked write is a lost message.
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA busy_timeout=5000")
            self.conn.executescript(SCHEMA)
        except BaseException:
            self.conn.close()
            raise

    def close(self) -> None:
        """Idempotent — closing twice is not an error worth raising."""
        with self._lock:
            self.conn.close()

    # ------------------------------------------------------------- calls --

    def start_call(self, call_sid: str, profile_key: str, from_number: str,
                   to_number: str, brain: str, model: str,
                   is_test: bool = False) -> None:
        """One row, written when Twilio sends `setup`. Raises if this CallSid
        already has a row — two sessions for one call is a bug worth seeing."""
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO calls (call_sid, profile_key, from_number, to_number, "
                "started_at, brain, model, is_test) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(call_sid), str(profile_key), str(from_number or ""),
                 str(to_number or ""), time.time(), str(brain or ""),
                 str(model or ""), 1 if is_test else 0),
            )

    def add_turn(self, call_sid: str, n: int, role: str, text: str,
                 ttft_ms=None) -> int:
        """One thing that was said (or keyed). `ttft_ms` is the wait before the
        agent's first word — None for anything the caller said. Returns the row
        id, which is how a turn still being typed (a run of keypresses) is
        rewritten in place instead of becoming one row per digit."""
        if role not in TURN_ROLES:
            raise ValueError(f"unknown turn role {role!r} (expected one of {TURN_ROLES})")
        with self._lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO turns (call_sid, n, role, text, ts, ttft_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(call_sid), int(n), role, str(text), time.time(),
                 None if ttft_ms is None else int(ttft_ms)),
            )
            return _row_id(cur)

    def set_turn_text(self, turn_id: int, text: str) -> None:
        """Rewrite one turn's text.

        The caller keying a card number sends one dtmf event per digit, and one
        row per digit would put the whole number back together for anyone
        reading the transcript. The bridge keeps ONE turn for the run and
        rewrites it as the digits arrive, so the row only ever holds the mask.
        """
        with self._lock, self.conn:
            cur = self.conn.execute(
                "UPDATE turns SET text = ? WHERE id = ?", (str(text), int(turn_id)))
            if cur.rowcount == 0:
                raise KeyError(f"no turn with id {turn_id!r}")

    def end_call(self, call_sid: str, outcome: str, decision_reason: str,
                 caller_turns: int, overpromise_flags, prompt_tokens=None,
                 completion_tokens=None) -> None:
        """Finalise the row: how the call ended, how long it ran, and the
        per-call TTFT percentiles computed from its agent turns."""
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome {outcome!r} (expected one of {OUTCOMES})")
        now = time.time()
        with self._lock, self.conn:
            row = self.conn.execute(
                "SELECT started_at FROM calls WHERE call_sid = ?", (str(call_sid),)
            ).fetchone()
            if row is None:
                raise KeyError(f"no call row for {call_sid!r} — end_call before start_call")
            ttfts = sorted(
                r[0] for r in self.conn.execute(
                    "SELECT ttft_ms FROM turns WHERE call_sid = ? AND role = 'agent' "
                    "AND ttft_ms IS NOT NULL", (str(call_sid),))
            )
            self.conn.execute(
                "UPDATE calls SET ended_at = ?, duration_s = ?, outcome = ?, "
                "decision_reason = ?, caller_turns = ?, overpromise_flags = ?, "
                "prompt_tokens = ?, completion_tokens = ?, ttft_ms_p50 = ?, "
                "ttft_ms_p95 = ? WHERE call_sid = ?",
                (now, max(0.0, now - float(row["started_at"])), outcome,
                 str(decision_reason or ""), int(caller_turns),
                 json.dumps(list(overpromise_flags or [])),
                 prompt_tokens, completion_tokens,
                 _percentile(ttfts, 50), _percentile(ttfts, 95), str(call_sid)),
            )

    def set_notify_status(self, call_sid: str, status: str) -> None:
        """How the owner was told about this call's message: sent / failed /
        off / escalated. The per-attempt detail is in notify_log; this is the
        one word the call log shows."""
        with self._lock, self.conn:
            cur = self.conn.execute(
                "UPDATE calls SET notify_status = ? WHERE call_sid = ?",
                (str(status), str(call_sid)))
            if cur.rowcount == 0:
                raise KeyError(f"no call row for {call_sid!r}")

    def update_twilio(self, call_sid: str, status: str, duration_s, price) -> None:
        """What the carrier says the call was — its own status, its own billed
        duration, its own price. Ours and theirs disagree often enough that
        both belong in the row."""
        with self._lock, self.conn:
            cur = self.conn.execute(
                "UPDATE calls SET twilio_status = ?, twilio_duration_s = ?, "
                "twilio_price = ? WHERE call_sid = ?",
                (str(status), None if duration_s is None else int(duration_s),
                 None if price is None else str(price), str(call_sid)),
            )
            if cur.rowcount == 0:
                raise KeyError(f"no call row for {call_sid!r}")

    def get_call(self, call_sid: str):
        """One call and everything said on it, or None. After the retention
        purge the row survives with an empty `turns` list — that is the point
        of the purge, not a bug."""
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM calls WHERE call_sid = ?", (str(call_sid),)).fetchone()
            if row is None:
                return None
            call = dict(row)
            call["turns"] = [dict(r) for r in self.conn.execute(
                "SELECT n, role, text, ts, ttft_ms FROM turns WHERE call_sid = ? "
                "ORDER BY id", (str(call_sid),))]
            return call

    def list_calls(self, profile_keys, *, since=None, until=None, outcome=None,
                   has_message=None, include_test=False, q=None,
                   limit=100, offset=0) -> list:
        """The call log, newest first, scoped to the profiles the reader owns.

        `q` searches the CallSid, the caller's number and the message fields —
        never the transcript, which the retention purge is allowed to delete.
        """
        keys = [str(k) for k in profile_keys]
        if not keys:
            return []
        where = ["c.profile_key IN (%s)" % ",".join("?" * len(keys))]
        params: list = list(keys)
        if not include_test:
            where.append("c.is_test = 0")
        if since is not None:
            where.append("c.started_at >= ?")
            params.append(float(since))
        if until is not None:
            where.append("c.started_at <= ?")
            params.append(float(until))
        if outcome is not None:
            where.append("c.outcome = ?")
            params.append(str(outcome))
        if has_message is not None:
            where.append(("EXISTS" if has_message else "NOT EXISTS")
                         + " (SELECT 1 FROM messages m WHERE m.call_sid = c.call_sid)")
        if q:
            pattern = _like(q)
            where.append(
                "(c.call_sid LIKE ? ESCAPE '\\' OR c.from_number LIKE ? ESCAPE '\\' "
                "OR EXISTS (SELECT 1 FROM messages m WHERE m.call_sid = c.call_sid AND ("
                "IFNULL(m.caller_name, '') LIKE ? ESCAPE '\\' OR "
                "IFNULL(m.callback, '') LIKE ? ESCAPE '\\' OR "
                "IFNULL(m.email, '') LIKE ? ESCAPE '\\' OR "
                "IFNULL(m.need, '') LIKE ? ESCAPE '\\' OR "
                "IFNULL(m.summary, '') LIKE ? ESCAPE '\\')))")
            params += [pattern] * 7
        params += [int(limit), int(offset)]
        with self._lock:
            rows = self.conn.execute(
                "SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.call_sid = "
                "c.call_sid) AS message_count FROM calls c WHERE "
                + " AND ".join(where)
                + " ORDER BY c.started_at DESC, c.rowid DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------- messages --

    def add_message(self, call_sid: str, profile_key: str, caller_name, callback,
                    email, need, summary, review_flag: bool = False) -> int:
        """The message the owner has to answer. Returns its id.

        `summary` is the note exactly as written on the pad; the other fields
        are what could be read out of it with confidence. Raises if the call
        row is missing — a message with no call is a message nobody can trace.
        """
        now = time.time()
        with self._lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO messages (call_sid, profile_key, caller_name, callback, "
                "email, need, summary, status, created_at, updated_at, review_flag) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)",
                (str(call_sid), str(profile_key), caller_name, callback, email,
                 need, summary, now, now, 1 if review_flag else 0),
            )
            return _row_id(cur)

    def set_message_status(self, id: int, status: str, note=None) -> None:
        """Move a message through new -> in_progress -> done. `note` is the
        owner's own words; passing None keeps whatever note is already there."""
        if status not in MESSAGE_STATUSES:
            raise ValueError(
                f"unknown message status {status!r} (expected one of {MESSAGE_STATUSES})")
        with self._lock, self.conn:
            cur = self.conn.execute(
                "UPDATE messages SET status = ?, note = COALESCE(?, note), "
                "updated_at = ? WHERE id = ?",
                (status, note, time.time(), int(id)))
            if cur.rowcount == 0:
                raise KeyError(f"no message with id {id!r}")

    def list_messages(self, profile_keys, status=None, include_test=False, *,
                      call_sids=None, limit=None) -> list:
        """The owner's message list, newest first, with the caller's number
        joined in from the call.

        `call_sids` narrows the query to specific calls and `limit` bounds it —
        a caller that wants the status of ten calls must not read every message
        this line has ever taken to find them.
        """
        keys = [str(k) for k in profile_keys]
        if not keys:
            return []
        where = ["m.profile_key IN (%s)" % ",".join("?" * len(keys))]
        params: list = list(keys)
        if status is not None:
            if status not in MESSAGE_STATUSES:
                raise ValueError(f"unknown message status {status!r}")
            where.append("m.status = ?")
            params.append(status)
        if not include_test:
            where.append("c.is_test = 0")
        if call_sids is not None:
            sids = [str(s) for s in call_sids]
            if not sids:
                return []
            where.append("m.call_sid IN (%s)" % ",".join("?" * len(sids)))
            params += sids
        sql = ("SELECT m.*, c.from_number, c.is_test, c.started_at AS call_started_at "
               "FROM messages m JOIN calls c ON c.call_sid = m.call_sid WHERE "
               + " AND ".join(where)
               + " ORDER BY m.created_at DESC, m.id DESC")
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ----------------------------------------------- events + notify log --

    def add_event(self, profile_key, call_sid, level: str, kind: str, detail) -> None:
        """One operational event, kept beyond the in-memory ring the dashboard
        reads. Never caller speech — kinds, counts and reasons only."""
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO events (ts, profile_key, call_sid, level, kind, detail) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), profile_key, call_sid, str(level), str(kind), detail),
            )

    def log_notify(self, profile_key, target: str, ok: bool, error=None,
                   call_sid=None) -> None:
        """Every attempt to tell the owner something — the successes too,
        because "when did the pushes stop working" is the question that
        matters at 2am. `call_sid` ties the attempt to a caller so
        delete_caller can remove it."""
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO notify_log (ts, profile_key, call_sid, target, ok, error) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), profile_key, call_sid, str(target),
                 1 if ok else 0, error),
            )

    def _scope_clause(self, profile_keys, include_unscoped: bool):
        """(sql fragment, params) restricting a query to the businesses one
        dashboard login owns.

        Some rows belong to no business at all — a rejected websocket, a failed
        sign-in, a config save. `include_unscoped` decides whether the reader is
        shown them: an owner of the whole line is, an owner of one business is
        NOT, because those rows can name another customer's number or profile.
        Returns None when the scope selects nothing, so the caller can answer
        with an empty list instead of a query that means "every row".
        """
        keys = [str(k) for k in profile_keys]
        parts, params = [], []
        if keys:
            parts.append("profile_key IN (%s)" % ",".join("?" * len(keys)))
            params += keys
        if include_unscoped:
            parts.append("profile_key IS NULL")
        if not parts:
            return None
        return "(" + " OR ".join(parts) + ")", params

    def list_events(self, profile_keys, *, since=None, levels=None, limit=50,
                    include_unscoped=False) -> list:
        """The operational events one owner may read, newest first.

        The dashboard's in-memory ring holds the last few minutes and dies with
        the process; this is what answers "when did this start" a week later,
        which is the whole reason the alerts list reads it and not the ring.
        """
        scope = self._scope_clause(profile_keys, include_unscoped)
        if scope is None:
            return []
        where, params = [scope[0]], list(scope[1])
        if since is not None:
            where.append("ts >= ?")
            params.append(float(since))
        if levels is not None:
            wanted = [str(level) for level in levels]
            if not wanted:
                return []
            where.append("level IN (%s)" % ",".join("?" * len(wanted)))
            params += wanted
        params.append(int(limit))
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE " + " AND ".join(where)
                + " ORDER BY ts DESC, id DESC LIMIT ?", params).fetchall()
        return [dict(r) for r in rows]

    def list_notify(self, profile_keys, *, ok=None, since=None, limit=20,
                    include_unscoped=False) -> list:
        """Attempts to tell the owner about a message, newest first.

        `ok=False` is the question the dashboard actually asks: WHICH target is
        failing. "Notifications are failing" with no target names nothing the
        owner can go and fix.
        """
        scope = self._scope_clause(profile_keys, include_unscoped)
        if scope is None:
            return []
        where, params = [scope[0]], list(scope[1])
        if ok is not None:
            where.append("ok = ?")
            params.append(1 if ok else 0)
        if since is not None:
            where.append("ts >= ?")
            params.append(float(since))
        params.append(int(limit))
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM notify_log WHERE " + " AND ".join(where)
                + " ORDER BY ts DESC, id DESC LIMIT ?", params).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------- stats --

    def stats(self, profile_keys, days: int = 7, *, now=None) -> dict:
        """The dashboard's numbers. Test calls are excluded everywhere here —
        a demo call must never move a number the owner reads as business.

        `now` names the moment "today" is measured from (default: the clock).
        Without it a test that seeds "60 seconds ago" fails for the two
        minutes after local midnight, when that timestamp lands on yesterday.
        """
        keys = [str(k) for k in profile_keys]
        moment = time.time() if now is None else float(now)
        day_list = [
            time.strftime("%Y-%m-%d", time.localtime(moment - i * DAY_SECONDS))
            for i in range(max(1, int(days)) - 1, -1, -1)
        ]
        per_day = {d: {"date": d, "calls": 0, "no_info": 0} for d in day_list}
        if not keys:
            return {"calls_today": 0, "messages_waiting": 0, "no_info_today": 0,
                    "avg_duration_s": None, "per_day": list(per_day.values())}
        marks = ",".join("?" * len(keys))
        today = day_list[-1]
        with self._lock:
            counted = self.conn.execute(
                "SELECT date(started_at, 'unixepoch', 'localtime') AS day, "
                "COUNT(*) AS calls, "
                "SUM(CASE WHEN outcome = 'no_info_given' THEN 1 ELSE 0 END) AS no_info "
                f"FROM calls WHERE profile_key IN ({marks}) AND is_test = 0 "
                "AND date(started_at, 'unixepoch', 'localtime') >= ? GROUP BY day",
                keys + [day_list[0]],
            ).fetchall()
            waiting = self.conn.execute(
                "SELECT COUNT(*) FROM messages m JOIN calls c ON c.call_sid = m.call_sid "
                f"WHERE m.profile_key IN ({marks}) AND m.status = 'new' AND c.is_test = 0",
                keys,
            ).fetchone()[0]
            avg = self.conn.execute(
                f"SELECT AVG(duration_s) FROM calls WHERE profile_key IN ({marks}) "
                "AND is_test = 0 AND duration_s IS NOT NULL "
                "AND date(started_at, 'unixepoch', 'localtime') >= ?",
                keys + [day_list[0]],
            ).fetchone()[0]
        for row in counted:
            if row["day"] in per_day:
                per_day[row["day"]] = {"date": row["day"], "calls": int(row["calls"]),
                                       "no_info": int(row["no_info"] or 0)}
        return {
            "calls_today": per_day[today]["calls"],
            "messages_waiting": int(waiting),
            "no_info_today": per_day[today]["no_info"],
            "avg_duration_s": None if avg is None else float(avg),
            "per_day": [per_day[d] for d in day_list],
        }

    # --------------------------------------------- retention + deletion ---

    def purge_expired(self, profile_key: str, retention_days: int, *,
                      now=None) -> int:
        """Age out the WORDS past the horizon; keep the aggregates.

        Turns are deleted outright, each expired message loses its free-text
        summary and need, and the `no_info_note` events go too — that event
        holds the summarizer's note for a call that left no message, which is
        caller-derived text like any other. The calls row, the message row and
        every other operational event stay, so the owner's history and counts
        never move. Returns the number of turns deleted.

        `now` names the moment the horizon is measured from (default: the
        clock), so a test can put a row exactly on the boundary. A row AT the
        horizon is KEPT: retention_days means "for this many days", and the
        last of them is a day the business still has.
        """
        retention_days = int(retention_days)
        if retention_days <= 0:
            raise ValueError("retention_days must be a positive number of days")
        moment = time.time() if now is None else float(now)
        horizon = moment - retention_days * DAY_SECONDS
        with self._lock, self.conn:
            deleted = self.conn.execute(
                "DELETE FROM turns WHERE call_sid IN (SELECT call_sid FROM calls "
                "WHERE profile_key = ? AND started_at < ?)",
                (str(profile_key), horizon),
            ).rowcount
            self.conn.execute(
                "UPDATE messages SET summary = NULL, need = NULL "
                "WHERE profile_key = ? AND created_at < ? "
                "AND (summary IS NOT NULL OR need IS NOT NULL)",
                (str(profile_key), horizon),
            )
            self.conn.execute(
                "DELETE FROM events WHERE kind = 'no_info_note' "
                "AND profile_key = ? AND ts < ?",
                (str(profile_key), horizon),
            )
        return int(deleted)

    def delete_caller(self, from_number: str) -> Deletion:
        """Remove every row this store holds for one caller — the CCPA/GDPR
        "delete my data" path.

        Returns the number of rows removed. The result also carries
        `.call_sids`: the Markdown message pad is append-only text this store
        does not own, so the dashboard shows those CallSids to tell the owner
        exactly which pad entries still have to be redacted by hand.
        """
        number = str(from_number or "").strip()
        if not number:
            raise ValueError("delete_caller needs the caller's number in E.164 form")
        with self._lock, self.conn:
            sids = [r[0] for r in self.conn.execute(
                "SELECT call_sid FROM calls WHERE from_number = ? ORDER BY started_at",
                (number,))]
            rows = 0
            if sids:
                marks = ",".join("?" * len(sids))
                for table in ("turns", "messages", "events", "notify_log"):
                    rows += self.conn.execute(
                        f"DELETE FROM {table} WHERE call_sid IN ({marks})", sids).rowcount
                rows += self.conn.execute(
                    "DELETE FROM calls WHERE from_number = ?", (number,)).rowcount
        return Deletion(rows, sids)

    # ------------------------------------------- config changes + sessions --

    def record_config_change(self, actor: str, summary: str, diff: str,
                             applied: bool, reason: str) -> int:
        """An audit line for every config save — including the REJECTED ones,
        which is where "I changed the greeting and nothing happened" gets
        answered. Returns the row id."""
        with self._lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO config_changes (ts, actor, summary, diff, applied, reason) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), actor, summary, diff, 1 if applied else 0, reason),
            )
            return _row_id(cur)

    def list_config_changes(self, limit: int = 50) -> list:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM config_changes ORDER BY ts DESC, id DESC LIMIT ?",
                (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    def create_session(self, owner_key: str) -> str:
        """A dashboard login. The id is the credential, so it comes from
        `secrets` — never a counter, never a uuid1."""
        session_id = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO sessions (id, owner_key, created_at, last_seen) "
                "VALUES (?, ?, ?, ?)", (session_id, str(owner_key), now, now))
        return session_id

    def touch_session(self, session_id: str) -> None:
        with self._lock, self.conn:
            cur = self.conn.execute(
                "UPDATE sessions SET last_seen = ? WHERE id = ?",
                (time.time(), str(session_id)))
            if cur.rowcount == 0:
                raise KeyError("no such session")

    def get_session(self, session_id: str):
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (str(session_id),)).fetchone()
        return None if row is None else dict(row)

    def delete_session(self, session_id: str) -> int:
        with self._lock, self.conn:
            return int(self.conn.execute(
                "DELETE FROM sessions WHERE id = ?", (str(session_id),)).rowcount)

    def delete_owner_sessions(self, owner_key: str) -> int:
        """Log one owner out everywhere — after a password change, or when the
        owner says a device was lost."""
        with self._lock, self.conn:
            return int(self.conn.execute(
                "DELETE FROM sessions WHERE owner_key = ?", (str(owner_key),)).rowcount)


def default_db_path() -> str:
    """Where the store lives: $PHONE_DATA_DIR/calls.db, default
    ~/.local/share/atlas-phone/calls.db. The service creates the directory
    (0700) at boot and refuses to start if it cannot."""
    data_dir = os.environ.get("PHONE_DATA_DIR", "").strip() or os.path.expanduser(
        "~/.local/share/atlas-phone")
    return os.path.join(data_dir, "calls.db")

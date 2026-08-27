#!/usr/bin/env python3
"""One-shot importer: the Markdown message pad -> the SQLite call store.

Until the call store existed, every message this line ever took lived in one
append-only Markdown file (`~/atlas-phone-messages.md`). This reads that file
and writes each entry into the store so the owner's dashboard shows the whole
history, not just the calls that arrive after the upgrade.

What it does NOT do:
  * It never writes to the pad. The pad is the original record and stays
    exactly as it is — read-only, byte for byte.
  * It never invents structure. A pad entry is free text written by a
    summarizer with no fixed shape, so the whole note is kept verbatim in
    `messages.summary` and only the facts printed in the entry's own header
    and footer (when, which number, which CallSid, how many caller turns) go
    into typed columns.
  * It never prints caller details. The output is counts — this tool runs in a
    terminal and its scrollback is not the place for a stranger's phone number.

Entries look like this (the format service.format_message_entry writes):

    ## 2026-07-22 07:25 EDT — Business Builders line — call from +1774…
    > Caller-derived text.            (newer entries only)
    …the note, 1-6 lines…
    *(CallSid CA4116…, 4 caller turns — full transcript in `journalctl …`)*

Usage:
    python migrate_pad.py --pad ~/atlas-phone-messages.md \\
        --db ~/.local/share/atlas-phone/calls.db --profile business_builders
    python migrate_pad.py --pad … --db … --dry-run

Idempotent: a CallSid already in the store is skipped, so running it twice
imports nothing the second time. Exit code 0 when everything parsed, 1 when
some entry could not be (it says how many), 2 when the pad cannot be read.
"""

import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import callstore  # noqa: E402  (needs the sys.path line above)

# "## 2026-07-22 07:25 EDT — Business Builders line — call from +17770001111"
HEADER_RE = re.compile(
    r"^##\s+(?P<when>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})(?:\s+(?P<tz>\S+))?\s*"
    r"[—-]\s*(?P<business>.+?)\s+line\s*[—-]\s*call from\s+(?P<caller>\S+)\s*$"
)
# "*(CallSid CA…, 4 caller turns — full transcript in `journalctl …`)*"
FOOTER_RE = re.compile(r"CallSid\s+(?P<sid>[A-Za-z0-9_]+)\s*,\s*(?P<turns>\d+)\s+caller turns")
# A pad convention, not part of the message.
CALLER_DERIVED_PREFIX = "> Caller-derived text."


def parse_pad(text: str) -> tuple[list, int]:
    """Split the pad into entries. Returns (entries, unparseable count).

    An entry with no CallSid footer cannot be de-duplicated on a second run,
    so it is counted and reported rather than imported blind.
    """
    entries: list = []
    unparseable = 0
    blocks = re.split(r"(?m)^(?=##\s)", text)
    for block in blocks:
        header = HEADER_RE.match(block.splitlines()[0] if block.strip() else "")
        if header is None:
            continue
        body_lines = []
        footer = None
        for line in block.splitlines()[1:]:
            found = FOOTER_RE.search(line)
            if found is not None:
                footer = found
                continue
            if line.strip() == CALLER_DERIVED_PREFIX:
                continue
            body_lines.append(line)
        if footer is None:
            unparseable += 1
            continue
        entries.append({
            "call_sid": footer.group("sid"),
            "caller_turns": int(footer.group("turns")),
            "from_number": header.group("caller"),
            "started_at": _pad_time(header.group("when")),
            "note": "\n".join(body_lines).strip(),
        })
    return entries, unparseable


def _pad_time(when: str) -> float:
    """The pad stamps local time with an abbreviation Python cannot map back to
    a zone, so the naive time is read as local — which is what the bridge that
    wrote it meant."""
    return datetime.strptime(when, "%Y-%m-%d %H:%M").astimezone().timestamp()


def import_entries(store, entries: list, profile_key: str) -> dict:
    """Write each entry as a minimal call + its message. Returns counts."""
    counts = {"imported": 0, "skipped": 0, "duplicate": 0, "test": 0}
    seen: set = set()
    for entry in entries:
        if store.get_call(entry["call_sid"]) is not None:
            # Two pad entries CAN carry the same CallSid — a call summarized
            # twice during testing. Say which kind of skip this was rather
            # than letting a first run report entries as "already imported".
            counts["duplicate" if entry["call_sid"] in seen else "skipped"] += 1
            continue
        seen.add(entry["call_sid"])
        is_test = callstore.is_test_call(entry["call_sid"], entry["from_number"])
        note = entry["note"]
        # The summarizer's own "No message" wording is the only outcome signal
        # a pad entry carries; anything else took a message.
        outcome = ("no_info_given" if note.lstrip().lower().startswith("no message")
                   else "message_taken")
        store.start_call(entry["call_sid"], profile_key, entry["from_number"], "",
                         "", "", is_test=is_test)
        store.end_call(entry["call_sid"], outcome, "imported from the message pad",
                       entry["caller_turns"], [])
        store.add_message(entry["call_sid"], profile_key, None, None, None, None, note)
        # The pad's timestamp is the truth about when the call happened; the
        # rows above were stamped "now" by the store, as live calls are.
        with store.conn:
            store.conn.execute(
                "UPDATE calls SET started_at = ?, ended_at = NULL, duration_s = NULL "
                "WHERE call_sid = ?", (entry["started_at"], entry["call_sid"]))
            store.conn.execute(
                "UPDATE messages SET created_at = ?, updated_at = ? WHERE call_sid = ?",
                (entry["started_at"], entry["started_at"], entry["call_sid"]))
        counts["imported"] += 1
        counts["test"] += 1 if is_test else 0
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Import the Markdown phone message pad into the call store.")
    parser.add_argument("--pad", required=True, help="path to the message pad (read-only)")
    parser.add_argument("--db", required=True, help="path to calls.db")
    parser.add_argument("--profile", default="default",
                        help="profile key these messages belong to")
    parser.add_argument("--dry-run", action="store_true",
                        help="parse and count, write nothing")
    args = parser.parse_args(argv)

    try:
        with open(args.pad, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"cannot read the pad at {args.pad}: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2

    entries, unparseable = parse_pad(text)
    # Two pad entries can carry the same CallSid (a call summarized twice
    # during testing). The store keys calls by CallSid, so the first wins and
    # the rest are counted as already-imported — the same answer a second run
    # would give.
    print(f"entries found: {len(entries)}")
    if unparseable:
        print(f"unparseable (no CallSid): {unparseable}")

    if args.dry_run:
        print(f"would import: {len(entries)}  (dry run — nothing written)")
        return 1 if unparseable else 0

    db_dir = os.path.dirname(os.path.abspath(args.db))
    if db_dir and not os.path.isdir(db_dir):
        os.makedirs(db_dir, mode=0o700, exist_ok=True)
    try:
        store = callstore.CallStore(args.db)
    except sqlite3.Error as e:
        print(f"cannot open the call store at {args.db}: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2
    try:
        counts = import_entries(store, entries, args.profile)
    finally:
        store.close()

    print(f"imported: {counts['imported']}")
    print(f"skipped (already imported): {counts['skipped']}")
    if counts["duplicate"]:
        print(f"skipped (same CallSid twice in the pad): {counts['duplicate']}")
    print(f"flagged as test: {counts['test']}")
    return 1 if unparseable else 0


if __name__ == "__main__":
    sys.exit(main())

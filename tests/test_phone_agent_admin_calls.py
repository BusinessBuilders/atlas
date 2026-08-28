# tests/test_phone_agent_admin_calls.py — the three screens an owner actually
# lives in: the call log, one call in full, and the message inbox.
#
# The dashboard this replaces had no call log at all: its "recent calls" panel
# shelled out to journalctl for a log format the bridge had stopped writing, so
# it showed nothing and said nothing was wrong. These tests pin the
# replacement, end to end over a real aiohttp server against a real store:
#
#   * every read AND every write is filtered to the businesses the login owns;
#     somebody else's call is a 404, not a 403 — a 403 confirms it exists;
#   * a list shows the caller's number masked to the last four; the call's own
#     page, which only its owner can open, shows the whole number to dial;
#   * a keypress stays masked wherever it is drawn;
#   * a panel that cannot read says so and the page still renders;
#   * the CSV is a real export — header row, one line per message, quoting that
#     survives a comma, and no cell a spreadsheet will run as a formula;
#   * deleting a caller takes the exact number typed back, names the calls it
#     removed, and says plainly which entries a person still has to redact.
#
# No real caller data anywhere: +1555…/CAtest… and invented names only.
import csv
import html
import inspect
import io
import sqlite3
import time

import pytest
from test_phone_agent_admin_auth import (ADMIN_DIR, ONE_BUSINESS,
                                         OTHER_BUSINESS, dashboard, health_ok,
                                         load_admin)
from test_phone_agent_plugin import _import_service

DAY = 86400.0
HTMX = {"HX-Request": "true"}
ADMIN_STATIC = ADMIN_DIR / "static"


@pytest.fixture
def line(tmp_path, monkeypatch):
    """One line, two businesses: `acme` (owner jo) and `other` (nobody's but
    the whole-line login's). This is the shape every tenancy test needs."""
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    return _import_service(tmp_path, monkeypatch,
                           extra_env={"ADMIN_TOKEN": "line-code"},
                           cfg_extra=ONE_BUSINESS + OTHER_BUSINESS)


def _call(svc, sid, *, profile="acme", frm="+15550000142", to="+15550001111",
          outcome="message_taken", reason="", turns=(), started=None,
          notify=None, is_test=False, brain="local_qwen", model="m",
          overpromise=()):
    """One call in the store, with whatever was said on it."""
    svc.STORE.start_call(sid, profile, frm, to, brain, model, is_test=is_test)
    for n, turn in enumerate(turns):
        role, text = turn[0], turn[1]
        ttft = turn[2] if len(turn) > 2 else None
        svc.STORE.add_turn(sid, n, role, text, ttft_ms=ttft)
    svc.STORE.end_call(sid, outcome, reason,
                       sum(1 for t in turns if t[0] == "caller"),
                       list(overpromise))
    if notify is not None:
        svc.STORE.set_notify_status(sid, notify)
    if started is not None:
        with sqlite3.connect(svc.STORE.path) as conn:
            conn.execute("UPDATE calls SET started_at = ?, ended_at = ?, "
                         "duration_s = ? WHERE call_sid = ?",
                         (started, started + 68, 68.0, sid))
    return sid


def _message(svc, sid, *, profile="acme", name="Dana Whitfield",
             callback="+15550000142", email=None, need="a quote for a website",
             summary="Dana Whitfield\na quote for a website"):
    return svc.STORE.add_message(sid, profile, name, callback, email, need,
                                 summary)


async def _text(dash, path, *, code="line-code", status=200, headers=None):
    await dash.client.sign_in(code)
    response = await dash.client.get(path, headers=headers)
    assert response.status == status, await response.text()
    return await response.text()


async def _page(svc, path, *, code="line-code", status=200, headers=None):
    async with dashboard(svc, health=health_ok) as dash:
        return await _text(dash, path, code=code, status=status,
                           headers=headers)


# ============================================================ the call log ===

async def test_the_call_log_needs_a_session(line):
    async with dashboard(line) as dash:
        response = await dash.client.get("/calls", allow_redirects=False)
        assert response.status == 302
        assert response.headers["Location"] == "/sign-in"


async def test_the_call_log_shows_this_owners_calls_in_owner_words(line):
    _call(line, "CA00000000000000000000000000mine1", turns=(
        ("agent", "Thanks for calling Acme Co.", 900),
        ("caller", "I need a quote for a roof."),
    ))
    _message(line, "CA00000000000000000000000000mine1")
    _call(line, "CA0000000000000000000000000theirs", profile="other",
          frm="+15550009999", outcome="no_info_given")

    page = await _page(line, "/calls", code="jo-code")

    assert "Message taken" in page
    # the caller's number is masked in a list — the last four only
    assert "•••••••0142" in page
    assert "+15550000142" not in page
    # the other business's call is not on this owner's page at all
    assert "0009999" not in page
    assert "CA0000000000000000000000000theirs" not in page


async def test_the_call_log_hides_test_calls_until_they_are_asked_for(line):
    _call(line, "CA00000000000000000000000000real1", turns=(("caller", "hello"),))
    _call(line, "CAtest0000000000000000000000demo1", is_test=True,
          frm="+15550001999", turns=(("caller", "this is a demo"),))

    page = await _page(line, "/calls")
    assert "•••••••1999" not in page

    with_tests = await _page(line, "/calls?show_test=1")
    assert "•••••••1999" in with_tests
    assert "Test" in with_tests


async def test_the_call_log_searches_what_was_said(line):
    _call(line, "CA0000000000000000000000000roof1", turns=(
        ("caller", "my roof is leaking after the storm"),))
    _call(line, "CA000000000000000000000000fence1", turns=(
        ("caller", "I want a fence quote"),))

    page = await _page(line, "/calls?q=leaking")
    assert "0000000000000000000000000roof1" in page or "roof1" in page
    assert "fence1" not in page


async def test_the_store_searches_the_transcript_as_well_as_the_message(line):
    """The search box promises "what was said". The words live in `turns`, so
    the query has to reach them — a box that quietly searched only the message
    summary would be a promise the product does not keep."""
    _call(line, "CA000000000000000000000000spoke1", turns=(
        ("caller", "the gutter is hanging off the back"),))
    found = line.STORE.list_calls(["acme"], q="gutter")
    assert [c["call_sid"] for c in found] == ["CA000000000000000000000000spoke1"]


async def test_filtering_to_nothing_offers_to_clear_the_filters(line):
    _call(line, "CA00000000000000000000000000mine1")
    page = await _page(line, "/calls?q=nothing-matches-this")
    assert "No calls match" in page
    assert "Clear filters" in page
    assert 'href="/calls"' in page


async def test_a_line_whose_only_calls_are_tests_says_that(line):
    """"No calls yet — ring your number to test it" is the wrong thing to say
    to a line whose only calls ARE tests with the box unticked."""
    _call(line, "CAtest0000000000000000000000demo1", is_test=True,
          frm="+15550001999", turns=(("caller", "this is a demo"),))
    page = await _page(line, "/calls", code="jo-code")
    assert "Only test calls so far" in page
    assert "No calls yet" not in page
    assert "Show test calls" in page


async def test_a_line_that_has_never_rung_says_what_to_dial(line):
    page = await _page(line, "/calls", code="jo-code")
    assert "No calls yet" in page
    # the REAL number for this business, not an example
    assert "(555) 000-1111" in page


async def test_the_call_log_says_how_long_calls_are_kept(line):
    page = await _page(line, "/calls", code="jo-code")
    assert "kept for 90 days" in page


async def test_the_retention_line_names_the_shortest_window_on_the_line(
        tmp_path, monkeypatch):
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "jo-code")
    svc = _import_service(
        tmp_path, monkeypatch, extra_env={"ADMIN_TOKEN": "line-code"},
        cfg_extra=OTHER_BUSINESS + "retention_days = 30\n")
    page = await _page(svc, "/calls")
    assert "kept for 30 days" in page


async def test_a_call_log_that_cannot_be_read_says_so_and_the_page_renders(line):
    async with dashboard(line) as dash:
        def boom(*a, **k):
            raise sqlite3.OperationalError("database is locked")
        dash.store.list_calls = boom
        page = await _text(dash, "/calls")
    assert "Could not read your call log" in page
    assert "database is locked" in page


async def test_a_text_message_is_a_text_not_a_call(line):
    """A text arrives as a call row with `decision_reason = "sms"`. It has no
    transcript and no duration, and showing "0:00" beside it reads as a call
    that failed."""
    _call(line, "SM00000000000000000000000000text1", reason="sms",
          turns=(("caller", "do you do gutters?"),))
    page = await _page(line, "/calls")
    assert "Text" in page
    assert "0:0" not in page


async def test_the_call_log_pages_fifty_at_a_time(line):
    now = time.time()
    for i in range(55):
        _call(line, f"CA00000000000000000000000000pg{i:03d}", started=now - i * 60)
    page = await _page(line, "/calls")
    assert "pg000" in page
    assert "pg049" in page
    assert "pg050" not in page
    assert "Older calls" in page

    second = await _page(line, "/calls?page=2")
    assert "pg050" in second
    assert "Newer calls" in second


async def test_drawing_the_call_log_asks_the_store_for_calls_once(line):
    """One page render, one call query. The Overview's `gather()` is six reads;
    a list that reached for it would put them on every page of the log."""
    _call(line, "CA00000000000000000000000000mine1")
    _message(line, "CA00000000000000000000000000mine1")
    async with dashboard(line) as dash:
        real, calls = dash.store.list_calls, []

        def counted(*a, **k):
            calls.append(k)
            return real(*a, **k)

        dash.store.list_calls = counted
        await _text(dash, "/calls")
    assert len(calls) == 1, calls


# ========================================================= one call in full ===

async def test_the_call_page_shows_the_whole_number_and_how_to_dial_it(line):
    sid = _call(line, "CA00000000000000000000000000mine1", turns=(
        ("agent", "Thanks for calling Acme Co.", 900),
        ("caller", "I need a quote."),
    ))
    _message(line, sid)
    page = await _page(line, f"/calls/{sid}", code="jo-code")

    assert "(555) 000-0142" in page
    assert 'href="tel:+15550000142"' in page
    assert 'data-copy="+15550000142"' in page


async def test_the_call_page_draws_the_conversation_with_both_sides(line):
    sid = _call(line, "CA00000000000000000000000000mine1", turns=(
        ("agent", "Thanks for calling Acme Co.", 900),
        ("caller", "I need a quote."),
        ("keypress", "[keypress: ••5]"),
    ))
    page = await _page(line, f"/calls/{sid}")

    assert "turn-agent" in page and "turn-caller" in page
    assert "turn-keypress" in page
    assert "Thanks for calling Acme Co." in page
    assert "I need a quote." in page
    # the digits stay hidden wherever they are drawn
    assert "Keypad" in page
    assert "[keypress: ••5]" in page


async def test_the_call_page_says_how_the_call_went(line):
    sid = _call(line, "CA00000000000000000000000000mine1", notify="sent",
                overpromise=("guarantee",), turns=(
                    ("agent", "one moment", 800),
                    ("agent", "here you go", 1600),
                    ("caller", "thanks"),
                ))
    _message(line, sid)
    page = await _page(line, f"/calls/{sid}")

    assert "How the call went" in page
    assert "Message taken" in page
    assert "0.8 s typical" in page
    assert "1.6 s slowest" in page
    assert "Sent to your phone" in page
    assert "guarantee" in page          # the overpromise flag is named


async def test_the_call_page_omits_the_prompt_section_when_nothing_stored_it(line):
    """The store keeps no copy of the prompt that was live for a call. A
    heading over an empty box would be a placeholder; the section is absent."""
    sid = _call(line, "CA00000000000000000000000000mine1")
    page = await _page(line, f"/calls/{sid}")
    assert "system prompt" not in page.lower()


async def test_a_call_with_no_details_shows_what_the_caller_said(line):
    sid = _call(line, "CA000000000000000000000000noinf1", outcome="no_info_given",
                turns=(("caller", "wrong number sorry"),))
    line.STORE.add_event("acme", sid, "info", "no_info_note",
                         "The caller rang the wrong number and hung up.")
    page = await _page(line, f"/calls/{sid}")

    # unescaped: the pill's words come through a template variable, so its
    # apostrophe is on the page as an entity and reads as one in a browser
    assert "Couldn't help" in html.unescape(page)
    assert "What the caller said" in page
    assert "rang the wrong number" in page


async def test_another_businesss_call_is_not_found_never_forbidden(line):
    sid = _call(line, "CA0000000000000000000000000theirs", profile="other",
                frm="+15550009999")
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        response = await dash.client.get(f"/calls/{sid}")
        body = await response.text()
    assert response.status == 404
    assert "0009999" not in body


async def test_a_call_that_never_existed_answers_the_same_way(line):
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        missing = await dash.client.get("/calls/CAnot0000000000000000000000000a")
        real = await dash.client.get(
            f"/calls/{_call(line, 'CA0000000000000000000000000theirs', profile='other')}")
    assert missing.status == real.status == 404
    assert await missing.text() == await real.text()


async def test_the_call_page_has_no_shell_instructions_anywhere(line):
    sid = _call(line, "CA00000000000000000000000000mine1", turns=(
        ("caller", "hello"),))
    _message(line, sid)
    for path in ("/calls", f"/calls/{sid}", "/messages"):
        page = (await _page(line, path)).lower()
        for jargon in ("journalctl", "systemctl", "sudo", "profile key",
                       "toml", "env file"):
            assert jargon not in page, f"{jargon!r} is on {path}"


# ------------------------------------------------------- actions on a call ---

async def test_marking_a_call_handled_finishes_its_message(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    message_id = _message(line, sid)
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf(f"/calls/{sid}")
        response = await dash.client.post(f"/calls/{sid}/handled", {"csrf": csrf})
    assert response.status == 303
    assert line.STORE.list_messages(["acme"])[0]["status"] == "done"
    assert message_id


async def test_marking_a_call_handled_without_the_token_changes_nothing(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    _message(line, sid)
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        response = await dash.client.post(f"/calls/{sid}/handled", {"csrf": "no"})
    assert response.status == 403
    assert line.STORE.list_messages(["acme"])[0]["status"] == "new"


async def test_a_note_is_kept_with_the_message_and_shown_again(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    _message(line, sid)
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf(f"/calls/{sid}")
        response = await dash.client.post(
            f"/calls/{sid}/note", {"csrf": csrf, "note": "Quote sent Thursday."})
        assert response.status == 303
        page = await (await dash.client.get(f"/calls/{sid}")).text()
    assert "Quote sent Thursday." in page
    assert line.STORE.list_messages(["acme"])[0]["note"] == "Quote sent Thursday."


async def test_another_businesss_call_cannot_be_marked_handled(line):
    sid = _call(line, "CA0000000000000000000000000theirs", profile="other")
    _message(line, sid, profile="other")
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf("/calls")
        response = await dash.client.post(f"/calls/{sid}/handled", {"csrf": csrf})
    assert response.status == 404
    assert line.STORE.list_messages(["other"])[0]["status"] == "new"


# =============================================================== messages ====

async def test_the_message_list_shows_the_message_and_how_to_answer_it(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    _message(line, sid, email="dana@example.invalid")
    page = await _page(line, "/messages", code="jo-code")

    assert "Dana Whitfield" in page
    assert "a quote for a website" in page
    assert 'href="tel:+15550000142"' in page      # call back, full number
    assert "(555) 000-0142" in page
    assert 'href="mailto:dana@example.invalid"' in page
    assert "New" in page


async def test_an_empty_inbox_says_nothing_is_waiting(line):
    page = await _page(line, "/messages", code="jo-code")
    assert "Nothing waiting" in page


async def test_the_message_list_pages_fifty_at_a_time(line):
    """Messages are never deleted, only aged of their words, so an unpaged list
    would eventually render every message a business has ever taken."""
    for i in range(120):
        sid = _call(line, f"CA0000000000000000000000000pg{i:03d}",
                    frm=f"+1555000{i:04d}")
        _message(line, sid, name=f"Caller {i:03d}")

    first = await _page(line, "/messages", code="jo-code")
    assert first.count("msg-card") == 50
    assert "Messages 1–50" in first
    assert "Older messages" in first
    assert "Newer messages" not in first

    third = await _page(line, "/messages?page=3", code="jo-code")
    assert third.count("msg-card") == 20
    assert "Messages 101–120" in third
    assert "Newer messages" in third
    assert "Older messages" not in third


async def test_the_waiting_count_in_the_heading_is_the_one_in_the_badge(line):
    """Two counts of the same thing that can disagree are worse than either.
    The heading and the badge are the same value, from one bounded COUNT."""
    for i in range(60):
        sid = _call(line, f"CA0000000000000000000000000ct{i:03d}",
                    frm=f"+1555001{i:04d}")
        _message(line, sid, name=f"Caller {i:03d}")

    page = await _page(line, "/messages", code="jo-code")
    assert "60 waiting · newest first" in page
    badge = page.split('id="nav-waiting"', 1)[1][:200]
    assert ">60<" in badge


async def test_counting_the_messages_never_reads_them_all(line):
    """The count is a COUNT. Drawing any page must not list every message a
    line has ever taken to find out how many are waiting."""
    for i in range(60):
        sid = _call(line, f"CA0000000000000000000000000cn{i:03d}",
                    frm=f"+1555002{i:04d}")
        _message(line, sid)
    assert line.STORE.count_messages(["acme"], "new") == 60
    assert line.STORE.count_messages(["acme"], "done") == 0
    assert line.STORE.count_messages(["other"]) == 0

    async with dashboard(line) as dash:
        real, sizes = dash.store.list_messages, []

        def counted(*a, **k):
            sizes.append(k.get("limit"))
            return real(*a, **k)

        dash.store.list_messages = counted
        await _text(dash, "/messages", code="jo-code")
    # one listing, and it asked for a page, not the table
    assert sizes == [51], sizes


async def test_moving_a_message_reads_one_row_not_the_whole_table(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    message_id = _message(line, sid)
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf("/messages")
        real_get, real_list = dash.store.get_message, dash.store.list_messages
        reads, listings = [], []

        def counted_get(mid):
            reads.append(mid)
            return real_get(mid)

        def counted_list(*a, **k):
            listings.append(k)
            return real_list(*a, **k)

        dash.store.get_message = counted_get
        dash.store.list_messages = counted_list
        response = await dash.client.post(
            f"/messages/{message_id}/status", {"csrf": csrf, "status": "done"},
            headers=HTMX)
    assert response.status == 200
    assert reads == [message_id]              # one indexed read by id
    assert listings == []                     # and no table scan at all
    assert line.STORE.list_messages(["acme"])[0]["status"] == "done"


async def test_the_message_list_is_filtered_by_status(line):
    first = _call(line, "CA00000000000000000000000000mine1")
    second = _call(line, "CA00000000000000000000000000mine2",
                   frm="+15550000777")
    _message(line, first, name="Dana Whitfield")
    done = _message(line, second, name="Marcus Tilley")
    line.STORE.set_message_status(done, "done")

    waiting = await _page(line, "/messages?status=new")
    assert "Dana Whitfield" in waiting and "Marcus Tilley" not in waiting

    finished = await _page(line, "/messages?status=done")
    assert "Marcus Tilley" in finished and "Dana Whitfield" not in finished


async def test_another_businesss_messages_are_never_listed(line):
    theirs = _call(line, "CA0000000000000000000000000theirs", profile="other",
                   frm="+15550009999")
    _message(line, theirs, profile="other", name="Not Yours")
    page = await _page(line, "/messages", code="jo-code")
    assert "Not Yours" not in page
    assert "0009999" not in page


async def test_the_nav_badge_counts_the_messages_still_waiting(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    _message(line, sid)
    page = await _page(line, "/", code="jo-code")
    assert "nav-badge" in page


async def test_changing_a_status_from_htmx_returns_just_the_card(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    message_id = _message(line, sid)
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf("/messages")
        response = await dash.client.post(
            f"/messages/{message_id}/status", {"csrf": csrf, "status": "done"},
            headers=HTMX)
        body = await response.text()
    assert response.status == 200
    assert "<!doctype html>" not in body.lower()
    assert "msg-card" in body
    assert "Done" in body
    assert line.STORE.list_messages(["acme"])[0]["status"] == "done"


async def test_moving_a_message_updates_the_waiting_count_beside_it(line):
    """The navigation says how many are waiting. Leaving it at 2 next to the
    message just moved off the list is the screen contradicting itself."""
    first = _call(line, "CA00000000000000000000000000mine1")
    second = _call(line, "CA00000000000000000000000000mine2",
                   frm="+15550000777")
    message_id = _message(line, first)
    _message(line, second, name="Marcus Tilley")
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        listing = await (await dash.client.get("/messages")).text()
        assert '<span class="tag tag-accent nav-badge" id="nav-waiting"' in listing
        assert ">2<" in listing.split('id="nav-waiting"', 1)[1][:200]

        csrf = await dash.client.csrf("/messages")
        body = await (await dash.client.post(
            f"/messages/{message_id}/status", {"csrf": csrf, "status": "done"},
            headers=HTMX)).text()
    assert 'hx-swap-oob="true"' in body
    assert ">1<" in body.split('id="nav-waiting"', 1)[1][:200]


async def test_changing_a_status_without_htmx_goes_back_to_the_list(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    message_id = _message(line, sid)
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf("/messages")
        response = await dash.client.post(
            f"/messages/{message_id}/status",
            {"csrf": csrf, "status": "in_progress", "back": "/messages?status=new"})
    assert response.status == 303
    assert response.headers["Location"] == "/messages?status=new"
    assert line.STORE.list_messages(["acme"])[0]["status"] == "in_progress"


async def test_a_status_that_is_not_a_status_changes_nothing(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    message_id = _message(line, sid)
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf("/messages")
        response = await dash.client.post(
            f"/messages/{message_id}/status", {"csrf": csrf, "status": "banana"})
    assert response.status == 400
    assert line.STORE.list_messages(["acme"])[0]["status"] == "new"


async def test_another_businesss_message_cannot_be_moved(line):
    theirs = _call(line, "CA0000000000000000000000000theirs", profile="other")
    message_id = _message(line, theirs, profile="other")
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf("/messages")
        response = await dash.client.post(
            f"/messages/{message_id}/status", {"csrf": csrf, "status": "done"})
    assert response.status == 404
    assert line.STORE.list_messages(["other"])[0]["status"] == "new"


async def test_a_long_message_is_clamped_but_never_cut(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    long_need = ("They described the whole job twice over. " * 12).strip()
    _message(line, sid, need=long_need)
    page = await _page(line, "/messages")
    assert long_need in page              # every word is on the page
    assert "Show more" in page or "msg-expand" in page


# ==================================================================== csv ====

def _csv_rows(body: str) -> list:
    return list(csv.reader(io.StringIO(body.lstrip("﻿"))))


async def test_the_export_is_a_real_csv_of_this_owners_messages(line):
    first = _call(line, "CA00000000000000000000000000mine1")
    second = _call(line, "CA00000000000000000000000000mine2",
                   frm="+15550000777")
    _message(line, first, name="Dana Whitfield",
             need="a quote, ideally this week", email="dana@example.invalid")
    _message(line, second, name="Marcus Tilley", need='he said "before Friday"')
    theirs = _call(line, "CA0000000000000000000000000theirs", profile="other")
    _message(line, theirs, profile="other", name="Not Yours")

    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        response = await dash.client.get("/messages.csv")
        body = await response.text()

    assert response.status == 200
    assert response.headers["Content-Type"].startswith("text/csv")
    stamp = time.strftime("%Y-%m-%d")
    assert f'filename="messages-{stamp}.csv"' in response.headers[
        "Content-Disposition"]

    rows = _csv_rows(body)
    assert rows[0][0] == "When"
    assert "Caller" in rows[0] and "Status" in rows[0]
    assert len(rows) == 3                       # header + this owner's two
    assert "Not Yours" not in body
    joined = [",".join(r) for r in rows]
    assert any("a quote, ideally this week" in r for r in joined)
    assert any('he said "before Friday"' in r for r in joined)


async def test_the_export_follows_the_status_you_are_looking_at(line):
    first = _call(line, "CA00000000000000000000000000mine1")
    second = _call(line, "CA00000000000000000000000000mine2",
                   frm="+15550000777")
    _message(line, first, name="Dana Whitfield")
    done = _message(line, second, name="Marcus Tilley")
    line.STORE.set_message_status(done, "done")

    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        body = await (await dash.client.get("/messages.csv?status=done")).text()
    assert "Marcus Tilley" in body
    assert "Dana Whitfield" not in body


async def test_the_export_cannot_smuggle_a_spreadsheet_formula(line):
    """A caller's words go into a file somebody opens in Excel. A cell that
    starts with `=` is a formula there, and this one dials a URL."""
    sid = _call(line, "CA00000000000000000000000000mine1")
    _message(line, sid, name="=HYPERLINK(\"http://evil.invalid\",\"click\")",
             need="+1+1")

    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        body = await (await dash.client.get("/messages.csv")).text()
    rows = _csv_rows(body)
    for cell in rows[1]:
        assert not cell.startswith(("=", "+", "-", "@")), cell
    assert "HYPERLINK" in body               # the words are still there


async def test_the_export_opens_correctly_in_a_spreadsheet(line):
    """The byte-order mark is deliberate: without it Excel on Windows reads a
    UTF-8 file as Windows-1252 and an accented name arrives as mojibake."""
    sid = _call(line, "CA00000000000000000000000000mine1")
    _message(line, sid, name="Renée Ó Súilleabháin")
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        raw = await (await dash.client.get("/messages.csv")).read()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "Renée Ó Súilleabháin" in raw.decode("utf-8")
    assert b"\r\n" in raw                      # RFC 4180 line endings


async def test_the_export_needs_a_session(line):
    async with dashboard(line) as dash:
        response = await dash.client.get("/messages.csv", allow_redirects=False)
    assert response.status == 302


# ======================================================== deleting a caller ===

async def test_deleting_a_caller_removes_every_row_and_names_the_calls(line):
    """The receipt arrives after a redirect, not rendered onto the POST: a
    rendered POST comes back on refresh, and refreshing must not try the delete
    again."""
    sid = _call(line, "CA00000000000000000000000000mine1", turns=(
        ("caller", "hello"),))
    _message(line, sid)
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf(f"/calls/{sid}")
        response = await dash.client.post(
            "/callers/delete",
            {"csrf": csrf, "number": "+15550000142", "call_sid": sid})
        assert response.status == 303
        assert response.headers["Location"] == "/calls?deleted=1"
        body = await (await dash.client.get("/calls?deleted=1")).text()
        again = await (await dash.client.get("/calls?deleted=1")).text()

    assert sid in body                                   # which calls went
    assert "by hand" in body                             # the pad sentence
    assert line.STORE.list_calls(["acme"]) == []
    assert line.STORE.list_messages(["acme"]) == []
    # the receipt is shown once; a reload is just the call log
    assert sid not in again
    assert "by hand" not in again


async def test_deleting_a_caller_is_written_down_without_the_number(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf(f"/calls/{sid}")
        await dash.client.post("/callers/delete",
                               {"csrf": csrf, "number": "+15550000142",
                                "call_sid": sid})
    events = [e for e in line.STORE.list_events(["acme"], limit=50)
              if e["kind"] == "caller_deleted"]
    assert len(events) == 1
    assert "0142" not in str(events[0]["detail"])
    assert "+1555" not in str(events[0]["detail"])


async def test_a_mistyped_number_deletes_nothing(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf(f"/calls/{sid}")
        response = await dash.client.post(
            "/callers/delete",
            {"csrf": csrf, "number": "+15550000143", "call_sid": sid})
        body = await response.text()
    assert response.status == 400
    assert "does not match this caller" in body
    assert len(line.STORE.list_calls(["acme"])) == 1


async def test_a_delete_with_no_call_to_confirm_against_is_refused(line):
    """The typed number is checked against the call the box was opened on. With
    no call there is nothing to check it against, so there is no delete."""
    _call(line, "CA00000000000000000000000000mine1")
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf("/calls")
        response = await dash.client.post(
            "/callers/delete", {"csrf": csrf, "number": "+15550000142"})
    assert response.status == 404
    assert len(line.STORE.list_calls(["acme"])) == 1


async def test_a_delete_against_another_businesss_call_is_not_found(line):
    theirs = _call(line, "CA0000000000000000000000000theirs", profile="other",
                   frm="+15550000142")
    _call(line, "CA00000000000000000000000000mine1")
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf("/calls")
        response = await dash.client.post(
            "/callers/delete",
            {"csrf": csrf, "number": "+15550000142", "call_sid": theirs})
    assert response.status == 404
    assert len(line.STORE.list_calls(["acme"])) == 1
    assert len(line.STORE.list_calls(["other"])) == 1


async def test_a_caller_whose_business_left_the_config_blocks_the_delete(line):
    """The cross-business check cannot be a walk of the config: a call row whose
    business was removed from businesses.toml is invisible to that, and it is
    exactly the row a scoped delete must not take. The STORE decides."""
    sid = _call(line, "CA00000000000000000000000000mine1")
    _call(line, "CA00000000000000000000000000gone01", profile="retired_co",
          frm="+15550000142")
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf(f"/calls/{sid}")
        response = await dash.client.post(
            "/callers/delete",
            {"csrf": csrf, "number": "+15550000142", "call_sid": sid})
        body = await response.text()
    assert response.status == 403
    assert "1 other business on this line" in body
    assert "retired_co" not in body         # counted, never named
    assert len(line.STORE.list_calls(["acme"])) == 1
    assert len(line.STORE.list_calls(["retired_co"])) == 1


async def test_the_whole_line_owner_can_delete_a_caller_from_every_business(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    _call(line, "CA0000000000000000000000000theirs", profile="other",
          frm="+15550000142")
    _call(line, "CA00000000000000000000000000gone01", profile="retired_co",
          frm="+15550000142")
    async with dashboard(line) as dash:
        await dash.client.sign_in("line-code")
        csrf = await dash.client.csrf(f"/calls/{sid}")
        response = await dash.client.post(
            "/callers/delete",
            {"csrf": csrf, "number": "+15550000142", "call_sid": sid})
    assert response.status == 303
    assert line.STORE.list_calls(["acme", "other", "retired_co"]) == []


async def test_a_caller_who_also_rang_another_business_is_refused(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    _call(line, "CA0000000000000000000000000theirs", profile="other",
          frm="+15550000142")
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf(f"/calls/{sid}")
        response = await dash.client.post(
            "/callers/delete",
            {"csrf": csrf, "number": "+15550000142", "call_sid": sid})
        body = await response.text()
    assert response.status == 403
    assert "1 other business on this line" in body
    assert "Other Co" not in body           # counted, never named
    assert len(line.STORE.list_calls(["acme"])) == 1
    assert len(line.STORE.list_calls(["other"])) == 1


async def test_deleting_a_caller_without_the_token_changes_nothing(line):
    sid = _call(line, "CA00000000000000000000000000mine1")
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        response = await dash.client.post(
            "/callers/delete",
            {"csrf": "wrong", "number": "+15550000142", "call_sid": sid})
    assert response.status == 403
    assert len(line.STORE.list_calls(["acme"])) == 1


# ================================================================ the shell ===

async def test_the_loading_line_is_the_only_thing_that_speaks(line):
    """A live region around the whole list makes a screen reader read every row
    again after a filter change. It belongs on the indicator alone — and the
    indicator has to exist in the empty and error states too."""
    for path in ("/calls", "/calls?q=nothing-matches-this"):
        page = await _page(line, path, code="jo-code")
        section = page.split('id="call-list"', 1)[1]
        assert 'aria-live' not in section.split(">", 1)[0]
        assert 'class="list-loading subtle htmx-indicator" role="status"' in section

    async with dashboard(line) as dash:
        def boom(*a, **k):
            raise sqlite3.OperationalError("database is locked")
        dash.store.list_calls = boom
        broken = await _text(dash, "/calls")
    assert 'class="list-loading subtle htmx-indicator" role="status"' in broken


async def test_the_show_more_words_are_in_the_page_not_in_the_stylesheet(line):
    """Text a stylesheet invents cannot be translated, searched or copied."""
    sid = _call(line, "CA00000000000000000000000000mine1")
    _message(line, sid, need=("They described the whole job twice over. " * 12).strip())
    page = await _page(line, "/messages", code="jo-code")
    assert ">Show more<" in page
    assert ">Show less<" in page
    css = (ADMIN_STATIC / "app.css").read_text(encoding="utf-8")
    assert 'content: "Show more"' not in css


async def test_a_note_longer_than_the_box_allows_is_cut_by_the_server(line):
    """A form's maxlength is a suggestion to a browser and nothing at all to
    anything else."""
    sid = _call(line, "CA00000000000000000000000000mine1")
    _message(line, sid)
    async with dashboard(line) as dash:
        await dash.client.sign_in("jo-code")
        csrf = await dash.client.csrf(f"/calls/{sid}")
        response = await dash.client.post(
            f"/calls/{sid}/note", {"csrf": csrf, "note": "x" * 5000})
        page = await (await dash.client.get(f"/calls/{sid}")).text()
    assert response.status == 303
    assert len(line.STORE.list_messages(["acme"])[0]["note"]) == 2000
    assert 'maxlength="2000"' in page


async def test_the_export_writes_its_byte_order_mark_as_an_escape(line):
    """An invisible character in the source is a character nobody reviewing
    this file can see."""
    source = (ADMIN_DIR / "views_messages.py").read_text(encoding="utf-8")
    assert '"\\ufeff"' in source
    assert "\ufeff" not in source


async def test_a_page_that_reads_no_messages_still_shows_the_waiting_count(line):
    """The count comes from the page shell, off the event loop — not from a
    store read the template does while it renders."""
    sid = _call(line, "CA00000000000000000000000000mine1")
    _message(line, sid)
    overview = await _page(line, "/", code="jo-code")
    badge = overview.split('id="nav-waiting"', 1)[1][:200]
    assert ">1<" in badge
    admin = load_admin()
    assert inspect.iscoroutinefunction(admin.render.page)
    assert not inspect.iscoroutinefunction(admin.render.partial)


async def test_the_navigation_now_offers_calls_and_messages(line):
    page = await _page(line, "/", code="jo-code")
    assert 'href="/calls"' in page
    assert 'href="/messages"' in page


async def test_the_call_log_promises_the_window_the_purge_really_uses(line):
    """"Kept for 90 days" has to be the number the clear-out actually runs at.
    A business that has not chosen gets the product default, and these two
    copies of it must not drift apart."""
    admin = load_admin()
    assert (admin.views_calls.DEFAULT_RETENTION_DAYS
            == line.PROFILE_DEFAULTS["retention_days"])


async def test_the_new_screens_add_no_inline_script(line):
    """The page's Content-Security-Policy allows scripts from this machine
    only. A copy button written as an onclick would simply not run."""
    sid = _call(line, "CA00000000000000000000000000mine1")
    _message(line, sid)
    for path in ("/calls", f"/calls/{sid}", "/messages"):
        page = await _page(line, path)
        for banned in ("onclick=", "onsubmit=", "javascript:", "<script>"):
            assert banned not in page, f"{banned!r} is on {path}"
    assert "data-copy=" in await _page(line, f"/calls/{sid}")


async def test_every_new_screen_is_reachable_from_its_own_nav(line):
    admin = load_admin()
    urls = {getattr(route.resource, "canonical", None)
            for route in dashboard(line).app.router.routes()}
    for item in admin.render.NAV:
        for entry in (item,) + tuple(item.children):
            if entry.url is not None:
                assert entry.url in urls

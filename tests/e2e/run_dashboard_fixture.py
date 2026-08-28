"""Start the real owner dashboard against a throwaway, obviously-fake line.

This is the instance the browser pass and `phone_dashboard_checks.py` drive. It
runs the REAL `plugins/phone_agent/service.py` and the REAL dashboard — nothing
here is a mock — but it points them at a temporary settings file and a
temporary database, so it can never read or write the live line.

Run it:

    cd <worktree>
    PYTHONPATH=<worktree>:<worktree>/src \\
      python tests/e2e/run_dashboard_fixture.py /tmp/dash-work 8931

The first argument is a working directory it creates (settings file + database
go inside it); the second is a port on 127.0.0.1. It prints the two access
codes and stays in the foreground until you stop it.

Two sign-ins:

  * `line-code`  — sees the whole line (both businesses, plus the Brain screen)
  * `acme-code`  — sees only Acme Plumbing (the tenancy proof)

The data is fiction on purpose: `+1555…` numbers reserved for drama, `CAtest…`
call ids, two invented businesses, and a model whose label says "test only" so
the production-safety banner is on screen. Nothing here belongs to a customer
and nothing here is committed to the live install.

What it seeds, and why each row exists:

  * a full call with a transcript, a keypress and a message (the Call detail
    screen has something to show);
  * one message in each of the three statuses — new, in progress, done;
  * a call that left nothing to act on (`no_info_given`);
  * a text message (SMS) row;
  * a blocked call (`blocked`);
  * a test call flagged `is_test=1`, hidden until "Show test calls";
  * a call belonging to the OTHER business, which the Acme sign-in must never
    see anywhere;
  * a failed message alert, so the Overview's "Mark as seen" button is real;
  * four settings changes, one of which touched both businesses.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "phone_agent"

CONFIG_TEXT = '''# Fixture settings for the dashboard browser pass. Fiction only.
active_brain = "bench_qwen"

[numbers]
"+15550001111" = "acme"
"+15550002222" = "riverside"

# The label carries the words "test only", which is what puts the
# production-safety banner on the Overview.
[brains.bench_qwen]
label = "Qwen 2.5 7B (test only)"
base_url = "http://127.0.0.1:11434/v1"
model = "qwen2.5:7b-instruct"

[brains.bench_cloud]
label = "Hosted fallback (test only)"
base_url = "https://api.example.invalid/v1"
model = "example-medium"
api_key_env = "FIXTURE_CLOUD_KEY"

[owners.jo]
token_env = "FIXTURE_ACME_TOKEN"
profiles = ["acme"]

[profiles.acme]
business_name = "Acme Plumbing"
services = "emergency plumbing, boiler service and bathroom fitting"
owner_name = "Jo Carter"
assistant_name = "Atlas"
greeting = "Thanks for calling Acme Plumbing, this is Atlas. How can I help?"
forward_to = "+15550003333"
facts = """Hours: Monday to Friday, 8 to 6 Eastern
Email: office@acmeplumbing.invalid
We cover Worcester County and 20 miles around it"""
extra_instructions = "Never quote a price on the phone. Offer a callback for anything about cost."
timezone = "America/New_York"
hours = { mon = "08:00-18:00", tue = "08:00-18:00", wed = "08:00-18:00", thu = "08:00-18:00", fri = "08:00-16:00" }
holidays = ["2026-11-26", "2026-12-24..2026-12-26"]
after_hours = "message"
after_hours_greeting = "Thanks for calling Acme Plumbing. We're closed right now, but I can take a message."
ntfy_url = "https://push.acme.invalid"
ntfy_topic = "acme-phone"
block_list = ["+15550009000"]
retention_days = 90

[profiles.riverside]
business_name = "Riverside Dental"
services = "general dentistry and hygiene appointments"
owner_name = "Sam Okafor"
assistant_name = "Atlas"
greeting = "Riverside Dental, this is Atlas speaking. How can I help?"
forward_to = "+15550004444"
timezone = "America/New_York"
ntfy_url = "https://push.riverside.invalid"
ntfy_topic = "riverside-phone"
'''


def build(work: pathlib.Path):
    """Load the service against the fixture config and seed the store."""
    work.mkdir(parents=True, exist_ok=True)
    config = work / "businesses.toml"
    config.write_text(CONFIG_TEXT, encoding="utf-8")

    # Anything inherited from the shell that would point the fixture at a real
    # push target or a real message pad is cleared, not overridden.
    for key in ("NTFY_URL", "NTFY_TOPIC", "MESSAGES_FILE", "PHONE_DB"):
        os.environ.pop(key, None)
    os.environ.update(
        TWILIO_ACCOUNT_SID="ACtestfixture", TWILIO_AUTH_TOKEN="fixture",
        BRIDGE_PORT="1", WS_TOKEN="fixture",
        PUBLIC_BASE="https://phone.example.invalid/phone",
        OLLAMA_URL="http://127.0.0.1:11434/v1", MODEL="qwen2.5:7b-instruct",
        BUSINESS_CONFIG=str(config), PHONE_DATA_DIR=str(work / "data"),
        ADMIN_TOKEN="line-code", FIXTURE_ACME_TOKEN="acme-code",
        FIXTURE_CLOUD_KEY="not-a-real-key",
    )

    sys.path.insert(0, str(PLUGIN))
    spec = importlib.util.spec_from_file_location(
        "phone_agent_service_fixture", PLUGIN / "service.py")
    svc = importlib.util.module_from_spec(spec)
    sys.modules["phone_agent_service_fixture"] = svc
    spec.loader.exec_module(svc)

    admin_dir = PLUGIN / "admin"
    admin_spec = importlib.util.spec_from_file_location(
        "phone_agent_admin_fixture", admin_dir / "__init__.py",
        submodule_search_locations=[str(admin_dir)])
    admin = importlib.util.module_from_spec(admin_spec)
    sys.modules["phone_agent_admin_fixture"] = admin
    admin_spec.loader.exec_module(admin)

    seed(svc)

    app = admin.build_admin_app(
        get_state=lambda: (svc.NUMBERS, svc.PROFILES),
        get_config=lambda: svc.CONFIG,
        get_brains=lambda: (svc.BRAINS, svc.ACTIVE_BRAIN),
        get_branding=lambda: svc.BRANDING,
        get_owners=lambda: svc.OWNERS,
        get_health=svc.health_snapshot,
        get_brain_health=lambda: svc.BRAIN_HEALTH,
        apply_config=svc.apply_config,
        delivery_targets=svc.delivery_targets,
        push_ntfy=svc.push_ntfy,
        profile_setting=svc.profile_setting,
        opening_line=svc.opening_line,
        parse_config=svc.parse_config,
        config_from_diff=svc.config_from_diff,
        acknowledge_delivery_failure=svc.acknowledge_delivery_failure,
        public_base=svc.PUBLIC_BASE,
        product_defaults=svc.PRODUCT_DEFAULTS,
        store=svc.STORE,
    )
    return svc, app, config


def seed(svc) -> None:
    """Write the fixture history. Every value here is invented."""
    store = svc.STORE
    now = time.time()

    # 1 — the headline call: a real conversation that left a message.
    quote = "CAtest0000000000000000000000quote"
    store.start_call(quote, "acme", "+15550009142", "+15550001111",
                     "bench_qwen", "qwen2.5:7b-instruct")
    for n, (role, text, ttft) in enumerate([
        ("agent", "Thanks for calling Acme Plumbing, this is Atlas. This call "
                  "may be recorded and transcribed. How can I help?", 780),
        ("caller", "Hi, my boiler is making a banging noise and the radiators "
                   "upstairs are cold. Can somebody come out this week?", None),
        ("agent", "That sounds like something Jo will want to look at. I can "
                  "take your name and the best number to reach you.", 1420),
        ("keypress", "[keypress: 5]", None),
        ("agent", "I heard a keypress — there is no menu on this line, so just "
                  "tell me and I will write it down.", 860),
        ("caller", "Dana Pike, 555-000-9142. Thursday afternoon is best.", None),
        ("agent", "Got it, Dana. Jo will call you back about the boiler. "
                  "Anything else?", 940),
        ("caller", "No, that is everything. Thank you.", None),
    ]):
        store.add_turn(quote, n, role, text, ttft_ms=ttft)
    store.end_call(quote, "message_taken", "", 3, ["guarantee"])
    store.set_notify_status(quote, "sent")
    store.add_message(
        quote, "acme", "Dana Pike", "+15550009142", "dana@example.invalid",
        "A boiler that bangs and cold upstairs radiators. Best time to reach "
        "her is Thursday afternoon, and she asked whether the call-out fee is "
        "charged separately from the repair.",
        "Dana Pike\n+15550009142\nboiler banging, upstairs radiators cold")
    store.log_notify("acme", "ntfy", True, None, quote)

    # 2 — a message already being worked on.
    quoting = "CAtest000000000000000000000fitting"
    store.start_call(quoting, "acme", "+15550009208", "+15550001111",
                     "bench_qwen", "qwen2.5:7b-instruct")
    store.add_turn(quoting, 0, "caller",
                   "I would like a quote for a new bathroom.")
    store.add_turn(quoting, 1, "agent", "I can take that down for Jo.", 690)
    store.end_call(quoting, "message_taken", "", 2, [])
    store.set_notify_status(quoting, "sent")
    in_progress = store.add_message(
        quoting, "acme", "Marcus Tilley", "+15550009208", None,
        "Wants a quote for a full bathroom fit, second floor, no rush.",
        "Marcus Tilley\n+15550009208\nbathroom fit quote")
    store.set_message_status(in_progress, "in_progress",
                             "Rang back, left a voicemail.")

    # 3 — a message already answered.
    booked = "CAtest0000000000000000000000leak"
    store.start_call(booked, "acme", "+15550009311", "+15550001111",
                     "bench_qwen", "qwen2.5:7b-instruct")
    store.add_turn(booked, 0, "caller", "There is a leak under my kitchen sink.")
    store.add_turn(booked, 1, "agent", "I will get that to Jo right away.", 720)
    store.end_call(booked, "message_taken", "", 2, [])
    store.set_notify_status(booked, "sent")
    done = store.add_message(
        booked, "acme", "Priya Ramanathan", "+15550009311", None,
        "Leak under the kitchen sink, water shut off at the valve.",
        "Priya Ramanathan\n+15550009311\nkitchen sink leak")
    store.set_message_status(done, "done", "Booked for Tuesday morning.")

    # 4 — a call that left nothing to act on.
    wrong = "CAtest000000000000000000000wrongno"
    store.start_call(wrong, "acme", "+15550009777", "+15550001111",
                     "bench_qwen", "qwen2.5:7b-instruct")
    store.add_turn(wrong, 0, "caller", "Sorry, wrong number.")
    store.end_call(wrong, "no_info_given", "", 1, [])
    store.add_event("acme", wrong, "info", "no_info_note",
                    "The caller rang the wrong number and hung up without "
                    "leaving anything to act on.")

    # 5 — a text message, not a call.
    text_sid = "SMtest00000000000000000000000text"
    store.start_call(text_sid, "acme", "+15550009433", "+15550001111",
                     "bench_qwen", "qwen2.5:7b-instruct")
    store.end_call(text_sid, "message_taken", "sms", 1, [])
    store.set_notify_status(text_sid, "sent")
    store.add_message(
        text_sid, "acme", "Ellis Nakamura", "+15550009433", None,
        "Asked whether the call-out fee covers the first hour of work.",
        "Ellis Nakamura\ncall-out fee question")

    # 6 — a blocked caller.
    blocked = "CAtest00000000000000000000blocked"
    store.start_call(blocked, "acme", "+15550009000", "+15550001111",
                     "bench_qwen", "qwen2.5:7b-instruct")
    store.end_call(blocked, "blocked", "block_list", 0, [])
    store.add_event("acme", blocked, "warning", "blocked",
                    "A number on the block list called and was turned away.")

    # 7 — a test call: flagged, so it is hidden until asked for.
    demo = "CAtest0000000000000000000000demo1"
    store.start_call(demo, "acme", "+15551230000", "+15550001111",
                     "bench_qwen", "qwen2.5:7b-instruct", is_test=True)
    store.add_turn(demo, 0, "caller", "This is a demo call, ignore it.")
    store.end_call(demo, "caller_hung_up", "", 1, [])

    # 8 — the other business, which the Acme sign-in must never see.
    theirs = "CAtest00000000000000000000riverside"
    store.start_call(theirs, "riverside", "+15550009520", "+15550002222",
                     "bench_qwen", "qwen2.5:7b-instruct")
    store.add_turn(theirs, 0, "caller",
                   "I need to move my hygienist appointment.")
    store.add_turn(theirs, 1, "agent", "I can pass that to Sam.", 810)
    store.end_call(theirs, "message_taken", "", 2, [])
    store.add_message(
        theirs, "riverside", "Toni Vasquez", "+15550009520", None,
        "Wants to move a hygienist appointment from Friday to the week after.",
        "Toni Vasquez\nmove hygienist appointment")

    # 9 — a message alert that did not get through, so "Mark as seen" is real.
    failed = "CAtest00000000000000000000alertbad"
    store.start_call(failed, "acme", "+15550009644", "+15550001111",
                     "bench_qwen", "qwen2.5:7b-instruct")
    store.add_turn(failed, 0, "caller", "My tap will not stop dripping.")
    store.end_call(failed, "message_taken", "", 2, [])
    store.set_notify_status(failed, "failed")
    store.add_message(
        failed, "acme", "Owen Brady", "+15550009644", None,
        "A dripping tap in the upstairs bathroom, not urgent.",
        "Owen Brady\ndripping tap")
    store.log_notify("acme", "ntfy", False,
                     "ClientConnectorDNSError: Cannot connect to host "
                     "push.acme.invalid:443", failed)
    svc.LAST_DELIVERY.update({
        "ts": now, "call_sid": failed, "ok": False,
        "error": "ClientConnectorDNSError: Cannot connect to host "
                 "push.acme.invalid:443",
    })

    # A couple of line-level events for the Overview's alert list.
    store.add_event(None, None, "warning", "dashboard_signin_failed",
                    "wrong access code from 100.64.0.9")
    store.add_event("acme", None, "error", "brain_unreachable",
                    "the model did not answer in 10s")

    # The model has been probed once and answered, so the band is not stuck on
    # "not confirmed yet" for a reason that has nothing to do with the screens.
    svc.BRAIN_HEALTH["bench_qwen"] = {
        "reachable": True, "probe_error": "", "checked_at": now - 25,
        "attempts": 0, "next_at": 0.0,
    }
    svc.BRAIN_HEALTH["bench_cloud"] = {
        "reachable": False,
        "probe_error": "ClientConnectorDNSError: api.example.invalid",
        "checked_at": now - 40, "attempts": 3, "next_at": now + 300,
    }

    # Four settings changes, so Activity has history to expand and restore.
    # The first is applied through the real save path, which writes the file,
    # the backup and the audit row exactly as the dashboard does.
    svc.apply_config(
        dataclasses.replace(svc.CONFIG, profiles=dict(
            svc.CONFIG.profiles,
            acme=dict(svc.CONFIG.profiles["acme"],
                      greeting="Thanks for calling Acme Plumbing, this is "
                               "Atlas. How can I help you today?"))),
        "jo", "Changed the greeting callers hear for Acme Plumbing")
    svc.apply_config(
        dataclasses.replace(svc.CONFIG, profiles=dict(
            svc.CONFIG.profiles,
            riverside=dict(svc.CONFIG.profiles["riverside"],
                           forward_to="+15550005555"))),
        "line-owner", "Changed where calls are forwarded for Riverside Dental")
    # One change that touched BOTH businesses at once — the case a scoped
    # owner must only see their own half of.
    svc.apply_config(
        dataclasses.replace(svc.CONFIG, profiles=dict(
            svc.CONFIG.profiles,
            acme=dict(svc.CONFIG.profiles["acme"],
                      extra_instructions="Never quote a price on the phone. "
                                         "Offer a callback for anything about "
                                         "cost, including the call-out fee."),
            riverside=dict(svc.CONFIG.profiles["riverside"],
                           services="general dentistry, hygiene appointments "
                                    "and emergency toothache"))),
        "line-owner", "Changed settings for Acme Plumbing and Riverside Dental")
    # And one the validator refused, so the list is honest about failures too.
    store.record_config_change(
        actor="jo", summary="Changed where calls are forwarded for Acme Plumbing",
        diff="", applied=False,
        reason="forward_to must be a phone number in the +15551234567 form")


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__)
        print("usage: run_dashboard_fixture.py <work-dir> <port>",
              file=sys.stderr)
        return 2
    work, port = pathlib.Path(argv[1]), int(argv[2])
    svc, app, config = build(work)

    from aiohttp import web
    print(f"settings file: {config}", flush=True)
    print(f"database:      {work / 'data'}", flush=True)
    print(f"dashboard:     http://127.0.0.1:{port}/", flush=True)
    print("access codes:  line-code (whole line) · acme-code (Acme Plumbing "
          "only)", flush=True)
    web.run_app(app, host="127.0.0.1", port=port, access_log=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

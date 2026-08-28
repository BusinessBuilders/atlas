#!/usr/bin/env python3
"""Put the phone line's URLs on the Twilio number — and show what is there now.

Twilio holds four settings per number that decide what happens to a call and a
text, and until this script existed they were set by hand in a web console with
no record anywhere of what they should be:

  voice_url           where a call goes            -> {PUBLIC_BASE}/voice/incoming
  voice_fallback_url  where a call goes when THAT  -> a static TwiML on the VPS
                      URL fails or times out          (see --render below)
  status_callback     what the carrier says the    -> {PUBLIC_BASE}/voice/status
                      call was, after it ends
  sms_url             where a text goes            -> {PUBLIC_BASE}/sms/incoming

The fallback is the one that matters at 2am. Without it, a bridge that is down
answers a customer with Twilio's own "an application error has occurred"
recording; with it, the caller hears one sentence and is put through to a
person. It is deliberately served by the PUBLIC VPS, not by this machine —
a fallback that lives on the machine that just died is not a fallback.

Usage:

    twilio_config.py --show                 what Twilio has vs what it should
    twilio_config.py --render [--out DIR]   write the fallback TwiML files
    twilio_config.py --apply                write the differing fields to Twilio
    twilio_config.py --apply-voice-url --yes   …including voice_url

`--show` and `--render` change nothing on Twilio. `--apply` writes ONLY the
fields that differ, and prints each one — except `voice_url`, which it never
writes. That one field is what makes the number answer at all, and pointing it
somewhere else is sometimes deliberate (a maintenance page, a second bridge, a
migration mid-flight); a wrong value there is a dead line, not a missing
feature. When it does not match, `--show` and `--apply` say so loudly and leave
it alone. Change it in the Twilio console, or with `--apply-voice-url --yes`.

Reads (never writes) the same settings file systemd hands the bridge —
~/.config/atlas-phone/env, or $ATLAS_PHONE_ENV — for TWILIO_ACCOUNT_SID,
TWILIO_AUTH_TOKEN and PUBLIC_BASE, so it works when typed by hand. Anything
already in the environment wins. The auth token is never printed, not even
partly, and never appears in an error message.

Two deliberate choices:

  * No Twilio SDK. This talks to the REST API with aiohttp and HTTP basic auth
    — the same dependency the bridge already has, so the deployment's Python
    environment does not grow a package for one script that runs twice a year.
  * Twilio updates a resource with POST, not PUT (their API predates the
    convention). Only the differing fields go in the body, so nothing this
    script does not understand can be overwritten by it.
"""

import argparse
import asyncio
import os
import re
import sys
import tomllib
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.sax.saxutils import escape as xml_escape

import aiohttp

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TEMPLATE_PATH = REPO / "deploy" / "phone" / "fallback.xml.template"
DEFAULT_OUT_DIR = REPO / "deploy" / "phone" / "rendered"
DEFAULT_ENV_FILE = "~/.config/atlas-phone/env"
DEFAULT_BUSINESS_CONFIG = "~/.config/atlas-phone/businesses.toml"
# Overridable so the tests can point the script at a Twilio-shaped server on
# loopback. It is never set in production.
DEFAULT_API_BASE = "https://api.twilio.com"

# The four fields this script owns, in the order a person reads them.
FIELDS = ("voice_url", "voice_fallback_url", "status_callback", "sms_url")
# The bridge routes those three of them point at. These paths MUST match the
# ones service.py registers in _serve(); the test suite ties the two together,
# because a typo here would point a live number at a 404 and every call would
# fall through to the fallback.
ROUTES = {
    "voice_url": "/voice/incoming",
    "status_callback": "/voice/status",
    "sms_url": "/sms/incoming",
}
# voice_url is READ but never written by --apply. It is the setting that
# decides whether the phone line answers at all: a wrong value there is a dead
# number, and it is the one field that may legitimately have been pointed
# somewhere else on purpose (a maintenance page, a second bridge, a migration).
# It changes by hand in the Twilio console, or with --apply-voice-url --yes.
GUARDED_FIELDS = ("voice_url",)
# Their names in Twilio's API, which are not their names in its JSON.
API_NAMES = {
    "voice_url": "VoiceUrl",
    "voice_fallback_url": "VoiceFallbackUrl",
    "status_callback": "StatusCallback",
    "sms_url": "SmsUrl",
}

# What the caller hears when this machine is unreachable. Two variants, because
# a business with nobody to forward to must be told the truth rather than put
# on hold forever.
FALLBACK_SAY_CONNECTING = (
    "{business_name} can't take your call through the assistant right now. "
    "Connecting you to a person."
)
FALLBACK_SAY_NO_FORWARD = (
    "Thanks for calling {business_name}. We're sorry — we can't take your call "
    "right now. Please try again in a few minutes."
)
# And what they hear when that forward rings out. Word for word the sentence
# the live line speaks in the same situation (service.action_response_twiml),
# so a caller gets the same answer whether the bridge was up or down. Without
# it a <Dial> nobody answers ends the call in silence, which reads to the
# caller as the business hanging up on them.
FALLBACK_SAY_NO_ANSWER = (
    "Sorry, no one could pick up. Please call back and leave a message."
)


@dataclass(frozen=True)
class NumberPlan:
    """One mapped number and the business behind it."""
    number: str
    profile_key: str
    business_name: str
    forward_to: str


def digits_of(number: str) -> str:
    """The number as filename-safe digits: +15088863046 -> 15088863046."""
    return re.sub(r"\D", "", str(number))


def fallback_filename(number: str) -> str:
    return f"fallback-{digits_of(number)}.xml"


# ------------------------------------------------------------ the config ---

def load_env_file(path) -> list:
    """Fill in TWILIO_* / PUBLIC_BASE from the phone line's env file.

    Only variables that are NOT already set are taken, so an operator can
    override any of them for one command. Returns the names it filled in (for
    the log line) — never the values.
    """
    filled: list = []
    try:
        text = Path(os.path.expanduser(str(path))).read_text(encoding="utf-8")
    except OSError:
        return filled                     # no file is normal; missing vars are loud
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        name, sep, value = line.partition("=")
        name = name.strip()
        if not sep or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            continue
        if os.environ.get(name, "").strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value:
            os.environ[name] = value
            filled.append(name)
    return filled


def load_numbers(config_path) -> dict:
    """{number: NumberPlan} from businesses.toml.

    Deliberately parses the config itself instead of importing service.py:
    importing the bridge opens its call store, binds its environment and
    refuses to load on any problem — none of which an operator asking "what is
    on the number" should have to satisfy.
    """
    path = Path(os.path.expanduser(str(config_path)))
    with open(path, "rb") as f:
        data = tomllib.load(f)
    numbers = data.get("numbers") or {}
    profiles = data.get("profiles") or {}
    if not numbers:
        raise ValueError(f"{path} has no [numbers] section — nothing to configure")
    plans: dict = {}
    for number, profile_key in numbers.items():
        profile = profiles.get(str(profile_key))
        if profile is None:
            raise ValueError(
                f"{path}: number {number} maps to profile {profile_key!r}, which "
                "is not defined")
        plans[str(number)] = NumberPlan(
            number=str(number), profile_key=str(profile_key),
            business_name=str(profile.get("business_name", "")).strip(),
            forward_to=str(profile.get("forward_to", "")).strip(),
        )
    return plans


# ----------------------------------------------------- what SHOULD be set ---

def intended_settings(public_base: str, plans: dict) -> dict:
    """{number: {field: url}} — what Twilio should hold for every mapped number.

    One number gets the plain `/fallback.xml`. As soon as there are two, each
    gets its own `/fallback-<digits>.xml`, because one shared file can only
    name one business and can only forward to one person — a second business
    sharing it would hear the first one's apology.
    """
    base = str(public_base).rstrip("/")
    shared = len(plans) == 1
    intended: dict = {}
    for number in plans:
        fallback = "fallback.xml" if shared else fallback_filename(number)
        intended[number] = {
            "voice_url": base + ROUTES["voice_url"],
            "voice_fallback_url": f"{base}/{fallback}",
            "status_callback": base + ROUTES["status_callback"],
            "sms_url": base + ROUTES["sms_url"],
        }
    return intended


def public_path(public_base: str) -> str:
    """The path PUBLIC_BASE is mounted at on the VPS ("/phone"), or "".

    Read from the configured base rather than assumed: this bridge has already
    moved between mounts once, and an instruction that says /phone when the
    base says something else sends the operator to the wrong nginx block.
    """
    return urlparse(str(public_base)).path.rstrip("/")


def plan(current: dict, intended: dict) -> dict:
    """Only the fields whose value has to change.

    Twilio omits a field it has never been given, so None and "" are the same
    absence — and neither is a reason to claim a URL changed when it did not.
    """
    changes: dict = {}
    for field, want in intended.items():
        have = current.get(field) or ""
        if str(have).strip() != str(want).strip():
            changes[field] = want
    return changes


def api_params(changes: dict) -> dict:
    """The change set under Twilio's own parameter names."""
    return {API_NAMES[field]: value for field, value in changes.items()}


# ------------------------------------------------------- the fallback TwiML -

def render_fallback(business_name: str, forward_to: str) -> str:
    """The TwiML the VPS serves when this machine cannot answer.

    With a forward number the caller is put through to a person, and told
    something if that person does not pick up; without one they get an apology
    and the call ends. Both are one short sentence: a caller who reached the
    fallback is already waiting.
    """
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if forward_to:
        say = FALLBACK_SAY_CONNECTING.format(business_name=business_name)
        action = (f"<Dial><Number>{xml_escape(forward_to)}</Number></Dial>"
                  f"<Say>{xml_escape(FALLBACK_SAY_NO_ANSWER)}</Say>")
    else:
        say = FALLBACK_SAY_NO_FORWARD.format(business_name=business_name)
        action = "<Hangup/>"
    return template.replace("{{SAY}}", xml_escape(say)).replace("{{ACTION}}", action)


def render_all(plans: dict, out_dir) -> list:
    """Write one fallback file per number. Returns the paths, in number order."""
    directory = Path(os.path.expanduser(str(out_dir)))
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for number in sorted(plans):
        entry = plans[number]
        path = directory / fallback_filename(number)
        path.write_text(render_fallback(entry.business_name, entry.forward_to),
                        encoding="utf-8")
        written.append(path)
    return written


# --------------------------------------------------------- the Twilio API ---

class TwilioError(RuntimeError):
    """A Twilio request that did not succeed. Never carries the auth token."""


async def fetch_numbers(session: aiohttp.ClientSession, api_base: str,
                        account_sid: str) -> dict:
    """{phone_number: the resource Twilio holds} for the whole account."""
    url = (f"{api_base}/2010-04-01/Accounts/{account_sid}"
           "/IncomingPhoneNumbers.json?PageSize=1000")
    held: dict = {}
    while url:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                detail = " ".join((await resp.text())[:300].split())
                raise TwilioError(
                    f"Twilio answered HTTP {resp.status} listing the account's "
                    f"numbers: {detail}")
            page = await resp.json()
        for entry in page.get("incoming_phone_numbers") or []:
            held[str(entry.get("phone_number", ""))] = entry
        # Twilio pages long lists; an account with more numbers than one page
        # must not silently look like it is missing them.
        next_uri = page.get("next_page_uri")
        url = urljoin(api_base, next_uri) if next_uri else ""
    return held


async def update_number(session: aiohttp.ClientSession, api_base: str,
                        account_sid: str, number_sid: str, changes: dict) -> None:
    url = (f"{api_base}/2010-04-01/Accounts/{account_sid}"
           f"/IncomingPhoneNumbers/{number_sid}.json")
    async with session.post(url, data=api_params(changes),
                            timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status not in (200, 201):
            detail = " ".join((await resp.text())[:300].split())
            raise TwilioError(
                f"Twilio answered HTTP {resp.status} updating {number_sid}: {detail}")


# ----------------------------------------------------------------- the CLI --

def basic_auth_header(user: str, password: str) -> str:
    """HTTP basic auth, built here rather than with aiohttp's helper: that
    helper's name and behaviour have moved between aiohttp releases, and this
    script has to keep working on whatever the deployment's venv holds. The
    header is created at the call and never stored on the session object."""
    return "Basic " + b64encode(f"{user}:{password}".encode()).decode()


def _mask_sid(sid: str) -> str:
    """An account SID is half an account credential. Only its shape is printed."""
    text = str(sid)
    return (text[:6] + "…" + text[-4:]) if len(text) > 12 else "…"


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(
            f"{name} is not set. It lives in the phone line's settings file "
            f"({os.environ.get('ATLAS_PHONE_ENV') or DEFAULT_ENV_FILE}); set it "
            "there or export it for this command.")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="twilio_config.py",
        description="Show or set the Twilio webhook URLs for the phone line's "
                    "numbers, and render the VPS fallback TwiML.")
    parser.add_argument("--show", action="store_true",
                        help="print what Twilio holds now vs what it should hold "
                             "(changes nothing)")
    parser.add_argument("--render", action="store_true",
                        help="write the fallback TwiML files (no network)")
    parser.add_argument("--apply", action="store_true",
                        help="write the differing fields to Twilio, and render "
                             "the fallback files. Never writes voice_url.")
    parser.add_argument("--apply-voice-url", action="store_true",
                        help="also write voice_url — the setting that decides "
                             "whether the line answers at all. Requires --yes.")
    parser.add_argument("--yes", action="store_true",
                        help="confirm --apply-voice-url. Nothing else needs it.")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR),
                        help=f"where --render/--apply write the fallback files "
                             f"(default: {DEFAULT_OUT_DIR})")
    return parser


def writable(changes: dict, *, include_voice_url: bool) -> dict:
    """The part of a change set --apply is allowed to write."""
    if include_voice_url:
        return dict(changes)
    return {f: v for f, v in changes.items() if f not in GUARDED_FIELDS}


def _print_number(entry: NumberPlan, current: dict, want: dict, changes: dict,
                  out_dir: Path, shared: bool, base_path: str) -> None:
    print(f"\n{entry.number}  {entry.profile_key}  \"{entry.business_name}\"")
    for field in FIELDS:
        have = current.get(field) or "(not set)"
        if field in changes:
            print(f"    {field:<19} now: {have}")
            print(f"    {'':<19} ->   {changes[field]}")
        else:
            print(f"    {field:<19} ok:  {want[field]}")
    name = "fallback.xml" if shared else fallback_filename(entry.number)
    where = (f"dials {entry.forward_to}" if entry.forward_to
             else "apologises and hangs up (this business has no forward_to)")
    print(f"    fallback file       {out_dir / fallback_filename(entry.number)}")
    print(f"                        serve it on the VPS as {base_path}/{name} "
          f"— {where}")


def _warn_voice_url(number: str, current, intended: str) -> None:
    """The one field --apply will not touch, said loudly enough to act on."""
    print(
        f"WARNING: {number} answers calls at {current or '(not set)'}, not at "
        f"{intended}. This script will NOT change that: voice_url is what makes "
        "the line answer at all, and pointing it somewhere else is sometimes "
        "deliberate. Change it in the Twilio console, or re-run with "
        "--apply-voice-url --yes once you are sure.",
        file=sys.stderr)


async def run(argv) -> int:
    """The whole script. Returns the exit code; raises nothing on a bad
    config or a Twilio error — those are printed and turned into a code."""
    args = build_parser().parse_args(list(argv))
    applying = args.apply or args.apply_voice_url
    if not (args.show or args.render or applying):
        print("nothing to do: pass --show to see what Twilio holds, --render to "
              "write the fallback TwiML, or --apply to set the URLs.",
              file=sys.stderr)
        return 2
    if args.apply_voice_url and not args.yes:
        print("twilio_config: --apply-voice-url changes the URL that makes this "
              "number answer at all. Add --yes if that is what you mean.",
              file=sys.stderr)
        return 2

    load_env_file(os.environ.get("ATLAS_PHONE_ENV") or DEFAULT_ENV_FILE)
    config_path = (os.environ.get("BUSINESS_CONFIG", "").strip()
                   or DEFAULT_BUSINESS_CONFIG)
    try:
        public_base = _require_env("PUBLIC_BASE").rstrip("/")
        plans = load_numbers(config_path)
    except (ValueError, OSError, tomllib.TOMLDecodeError) as e:
        print(f"twilio_config: {e}", file=sys.stderr)
        return 2
    intended = intended_settings(public_base, plans)
    out_dir = Path(os.path.expanduser(args.out))
    base_path = public_path(public_base)

    if args.render or applying:
        for path in render_all(plans, out_dir):
            print(f"rendered {path}")
    if args.render and not (args.show or applying):
        return 0

    try:
        account_sid = _require_env("TWILIO_ACCOUNT_SID")
        auth_token = _require_env("TWILIO_AUTH_TOKEN")
    except ValueError as e:
        print(f"twilio_config: {e}", file=sys.stderr)
        return 2
    api_base = (os.environ.get("TWILIO_API_BASE", "").strip()
                or DEFAULT_API_BASE).rstrip("/")

    print(f"Twilio account {_mask_sid(account_sid)} · public base {public_base}")
    headers = {"Authorization": basic_auth_header(account_sid, auth_token)}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            held = await fetch_numbers(session, api_base, account_sid)
            missing = [n for n in plans if n not in held]
            if missing:
                print("twilio_config: " + ", ".join(missing) + " — mapped in "
                      f"{config_path} but not on this Twilio account. Nothing was "
                      "changed; fix the mapping or buy the number first.",
                      file=sys.stderr)
                return 1

            planned: dict = {}
            warned: list = []
            for number in sorted(plans):
                current = {f: held[number].get(f) for f in FIELDS}
                changes = plan(current, intended[number])
                planned[number] = changes
                _print_number(plans[number], current, intended[number], changes,
                              out_dir, len(plans) == 1, base_path)
                if "voice_url" in changes and not args.apply_voice_url:
                    warned.append(number)

            # Said after the whole listing, on stderr, so it survives a pipe and
            # is the last thing on the screen.
            for number in warned:
                _warn_voice_url(number, held[number].get("voice_url"),
                                intended[number]["voice_url"])

            writes = {n: writable(c, include_voice_url=args.apply_voice_url)
                      for n, c in planned.items()}
            if not applying:
                total = sum(len(c) for c in writes.values())
                print(f"\n{total} setting(s) would change — run --apply to write them."
                      if total else "\nEverything --apply can write already matches."
                      if warned else "\nEverything already matches; --apply would "
                                     "write nothing.")
                return 0

            wrote = 0
            for number in sorted(plans):
                changes = writes[number]
                if not changes:
                    continue
                await update_number(session, api_base, account_sid,
                                    str(held[number]["sid"]), changes)
                wrote += len(changes)
                print(f"\nwrote {len(changes)} setting(s) to {number}: "
                      + ", ".join(sorted(changes)))
            print(f"\n{wrote} setting(s) written." if wrote
                  else "\nEverything --apply can write already matches; nothing "
                       "was written." if warned
                  else "\nEverything already matches; nothing was written.")
            return 0
    except (TwilioError, aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(f"twilio_config: {e}", file=sys.stderr)
        return 1


def main() -> None:
    sys.exit(asyncio.run(run(sys.argv[1:])))


if __name__ == "__main__":
    main()

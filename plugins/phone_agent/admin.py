"""Atlas phone agent — owner dashboard (admin.py).

A small, self-contained control panel served by the bridge process on a
SEPARATE local port. It edits businesses.toml through the same fail-closed
validation the boot path uses, and hot-applies good configs — no restart,
and a bad edit changes nothing.

Security model (do not weaken):
  * bound to 127.0.0.1 and exposed to the owner via a TAILNET-ONLY
    tailscale serve mapping — never on the public funnel path Twilio uses;
  * every request requires the ADMIN_TOKEN (login form -> HttpOnly cookie,
    compared with hmac.compare_digest);
  * the dashboard exists only when ADMIN_TOKEN is set.

No external assets — one HTML page, inline CSS, plain forms.
"""
from __future__ import annotations

import asyncio
import hmac
import html
import subprocess

from aiohttp import web

COOKIE = "atlas_admin"

_CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#101418;color:#e6e9ec;font:15px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:20px;margin:8px 0 2px}
h1 small{color:#8b97a3;font-weight:400;font-size:13px;margin-left:8px}
h2{font-size:15px;margin:28px 0 8px;color:#aeb8c2;text-transform:uppercase;letter-spacing:.06em}
.card{background:#171d24;border:1px solid #232c36;border-radius:10px;padding:16px;margin:10px 0}
.chips span{display:inline-block;background:#1d2630;border:1px solid #2a3642;border-radius:999px;padding:3px 12px;margin:2px 6px 2px 0;font-size:13px}
.chips .ok{border-color:#2c5d3f;color:#7fd6a4}
.chips .bad{border-color:#6b2f2f;color:#f29c9c}
label{display:block;color:#8b97a3;font-size:12.5px;margin:10px 0 3px}
input[type=text],input[type=password],textarea{width:100%;background:#0e131a;color:#e6e9ec;border:1px solid #2a3642;border-radius:7px;padding:8px 10px;font:inherit}
textarea{min-height:64px;resize:vertical}
textarea.tall{min-height:110px}
button{background:#2563eb;color:#fff;border:0;border-radius:8px;padding:9px 18px;font:inherit;cursor:pointer;margin-top:14px}
button:hover{background:#1d4fd8}
.errors{background:#2a1518;border:1px solid #6b2f2f;color:#f2b8b8;border-radius:8px;padding:10px 14px;margin:12px 0;white-space:pre-wrap}
.saved{background:#12241a;border:1px solid #2c5d3f;color:#9fdcb8;border-radius:8px;padding:10px 14px;margin:12px 0}
pre{background:#0e131a;border:1px solid #232c36;border-radius:8px;padding:12px;overflow-x:auto;font-size:12.5px;white-space:pre-wrap}
details summary{cursor:pointer;color:#8b97a3;margin:8px 0}
.del{color:#f29c9c;font-size:12.5px}
.hint{color:#68747f;font-size:12.5px;margin-top:4px}
"""


def _page(body: str, title: str = "Atlas Phone Agent") -> web.Response:
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )
    return web.Response(text=doc, content_type="text/html")


def _login_page(error: str = "") -> web.Response:
    err = f"<div class='errors'>{html.escape(error)}</div>" if error else ""
    return _page(
        "<h1>Atlas Phone Agent</h1><div class='card'><form method='post' action='/login'>"
        f"{err}<label>Admin token (ADMIN_TOKEN in the phone env file)</label>"
        "<input type='password' name='token' autofocus>"
        "<button>Sign in</button></form></div>",
        title="Sign in — Atlas Phone Agent",
    )


def build_admin_app(
    *, token: str, health_snapshot, get_state, get_prompts, apply_config_text,
    emit_business_toml, messages_file: str, known_keys: tuple,
) -> web.Application:

    def authed(request: web.Request) -> bool:
        return hmac.compare_digest(request.cookies.get(COOKIE, ""), token)

    async def login(request: web.Request) -> web.Response:
        form = await request.post()
        if not hmac.compare_digest(str(form.get("token", "")), token):
            return _login_page("Wrong token.")
        resp = web.Response(status=303, headers={"Location": "/"})
        resp.set_cookie(COOKIE, token, httponly=True, samesite="Strict",
                        max_age=60 * 60 * 24 * 30)
        return resp

    def _profile_form(key: str, profile: dict) -> str:
        def field(name: str, label: str, tall: bool = False, hint: str = "") -> str:
            value = html.escape(str(profile.get(name, "")))
            h = f"<div class='hint'>{html.escape(hint)}</div>" if hint else ""
            if name in ("facts", "extra_instructions", "transfer_phrases", "end_phrases",
                        "assistant_aliases"):
                return (f"<label>{html.escape(label)}</label>"
                        f"<textarea class='{'tall' if tall else ''}' "
                        f"name='{key}::{name}'>{value}</textarea>{h}")
            return (f"<label>{html.escape(label)}</label>"
                    f"<input type='text' name='{key}::{name}' value='{value}'>{h}")

        return (
            f"<div class='card'><h2>profile: {html.escape(key)}</h2>"
            + field("business_name", "Business name")
            + field("services", "Services (one plain-English line — the agent describes the business with this)")
            + field("owner_name", "Owner / message-taker name (callers hear “X will get back to you”)")
            + field("greeting", "Greeting (the first thing every caller hears)")
            + field("assistant_name", "Assistant name (optional, default Atlas)")
            + field("forward_to", "Forward calls to (optional, +1 format — enables “connect me to a person”)",
                    hint="Leave empty and the agent takes messages instead of transferring.")
            + field("model", "Model override (optional; must be a non-thinking model)")
            + field("facts", "Known facts — the ONLY specifics the agent may state (email, hours, service area, pricing posture; one per line)", tall=True)
            + field("extra_instructions", "Extra instructions — appended to this business's prompt (cannot override the safety rules)", tall=True)
            + field("transfer_phrases", "Transfer phrases — a caller must say one of these before a transfer can happen (one per line; {owner} = the owner's first name)",
                    hint="Leave empty to use the standard set (operator, transfer me, speak to a person, talk to {owner}, …). Listing your own REPLACES the standard set.")
            + field("end_phrases", "Hang-up phrases — a caller must say one of these before the agent may end the call (one per line)",
                    hint="Leave empty to use the standard set (goodbye, that's all, nothing else, hang up, …). Listing your own REPLACES the standard set.")
            + field("assistant_aliases", "Name mishearings — words the transcriber confuses with the assistant's name (one per line)",
                    hint="Callers greeting the agent get transcribed imperfectly (\"Atlas\" often arrives as \"Alice\"). The agent is told these are probably itself, not the caller's name. Empty = the standard set for the name Atlas.")
            + f"<label class='del'><input type='checkbox' name='{key}::__delete'> delete this profile</label>"
            "</div>"
        )

    async def index(request: web.Request) -> web.Response:
        if not authed(request):
            return _login_page()
        numbers, profiles = get_state()
        status, model_ok = await health_snapshot()

        chips = (
            f"<span class='ok'>bridge ok</span>"
            f"<span class='{'ok' if model_ok else 'bad'}'>model {html.escape(status['model_backend'])}</span>"
            f"<span>{html.escape(status['model'])}</span>"
            f"<span>{len(numbers)} number(s)</span>"
            f"<span>ntfy {status['ntfy']}</span>"
        )

        saved = "<div class='saved'>Saved and applied — live immediately, no restart.</div>" \
            if request.query.get("saved") else ""

        numbers_text = html.escape(
            "\n".join(f"{n} = {k}" for n, k in numbers.items())
        )
        profile_forms = "".join(_profile_form(k, p) for k, p in profiles.items())

        prompts = "".join(
            f"<details><summary>live prompt: {html.escape(k)}</summary>"
            f"<pre>{html.escape(p)}</pre></details>"
            for k, p in get_prompts().items()
        )

        try:
            with open(messages_file, encoding="utf-8") as f:
                pad = f.read()[-6000:]
        except FileNotFoundError:
            pad = "(no messages yet)"

        def _journal() -> str:
            try:
                out = subprocess.run(
                    ["journalctl", "--user", "-u", "atlas-phone-bridge",
                     "-n", "400", "--no-pager", "-o", "cat"],
                    capture_output=True, text=True, timeout=5,
                ).stdout
            except Exception as e:
                return f"(could not read journal: {e})"
            keep = [l for l in out.splitlines()
                    if any(t in l for t in ("caller (", "atlas (", "incoming call",
                                            "ended the call", "is transferring",
                                            "action callback"))]
            return "\n".join(keep[-40:]) or "(no calls in the recent journal)"

        transcript = await asyncio.to_thread(_journal)

        body = (
            "<h1>Atlas Phone Agent <small>owner dashboard</small></h1>"
            f"<div class='chips'>{chips}</div>{saved}"
            "<form method='post' action='/save'>"
            "<h2>Numbers</h2><div class='card'>"
            "<label>One per line: +15551234567 = profile_name</label>"
            f"<textarea name='numbers_text'>{numbers_text}</textarea></div>"
            f"<h2>Businesses</h2>{profile_forms}"
            "<div class='card'><h2>Add a business</h2>"
            "<label>New profile name (letters/underscores, e.g. acme_plumbing)</label>"
            "<input type='text' name='__new_key'>"
            "<div class='hint'>Fill its fields after it appears; a new profile needs "
            "business name, services, owner name, and greeting before a number can "
            "point at it.</div></div>"
            "<button>Save &amp; apply</button>"
            "<div class='hint'>Every save is validated exactly like service startup — "
            "a bad config is rejected with the reason and nothing changes. Calls in "
            "progress keep the settings they started with.</div>"
            "</form>"
            f"<h2>Live prompts</h2><div class='card'>{prompts}</div>"
            f"<h2>Message pad</h2><pre>{html.escape(pad)}</pre>"
            f"<h2>Recent calls</h2><pre>{html.escape(transcript)}</pre>"
        )
        return _page(body)

    async def save(request: web.Request) -> web.Response:
        if not authed(request):
            return _login_page()
        form = await request.post()
        _, current_profiles = get_state()

        errors: list[str] = []
        numbers: dict = {}
        for line in str(form.get("numbers_text", "")).splitlines():
            line = line.strip()
            if not line:
                continue
            if "=" not in line:
                errors.append(f"number line {line!r} must look like +15551234567 = profile_name")
                continue
            n, _, k = line.partition("=")
            numbers[n.strip()] = k.strip()

        profiles: dict = {}
        for key, profile in current_profiles.items():
            if form.get(f"{key}::__delete"):
                continue
            updated = dict(profile)  # unknown hand-added keys survive
            for field_name in known_keys:
                if f"{key}::{field_name}" in form:
                    value = str(form.get(f"{key}::{field_name}", "")).strip()
                    if value:
                        updated[field_name] = value
                    else:
                        updated.pop(field_name, None)
            profiles[key] = updated

        new_key = str(form.get("__new_key", "")).strip()
        if new_key:
            if new_key in profiles:
                errors.append(f"profile {new_key!r} already exists")
            else:
                profiles[new_key] = {
                    "business_name": "", "services": "", "owner_name": "",
                    "greeting": "",
                }
                errors.append(
                    f"profile {new_key!r} created in the form below — fill in its "
                    "required fields and save again"
                )

        if not errors:
            errors = apply_config_text(emit_business_toml(numbers, profiles))
        if errors:
            listing = "\n".join("• " + e for e in errors)
            # re-render the index with the error banner on top
            index_resp = await index(request)
            text = (index_resp.text or "").replace(
                "<h2>Numbers</h2>",
                f"<div class='errors'>Not applied:\n{html.escape(listing)}</div><h2>Numbers</h2>",
                1,
            )
            if new_key and f"profile: {html.escape(new_key)}" not in text:
                # show the new empty profile's form so it can be filled in
                text = text.replace(
                    "<div class='card'><h2>Add a business</h2>",
                    _profile_form(new_key, profiles.get(new_key, {}))
                    + "<div class='card'><h2>Add a business</h2>",
                    1,
                )
            return web.Response(text=text, content_type="text/html")
        return web.Response(status=303, headers={"Location": "/?saved=1"})

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/login", login)
    app.router.add_post("/save", save)
    return app

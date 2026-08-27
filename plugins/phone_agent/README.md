# phone_agent — Atlas answers the business phone

Gives Atlas a phone presence: callers dial a real Twilio number and talk to
Atlas — the same persona, running on the local model. One bridge serves many
businesses: each number maps to a profile (business name, services, greeting,
who takes messages) in a TOML file.

This plugin has two halves:

| Half | Runs where | Tools |
|---|---|---|
| `service.py` — the phone bridge | Its own systemd service (`deploy/systemd/atlas-phone-bridge.service`) | **NONE for callers** — sandboxed by design |
| `plugin.py` — `phone_line_status` | Inside Atlas's brain, via the plugin loader | One low-risk read-only tool for the OWNER |

## The caller sandbox (the point of the design)

Anyone on Earth can dial the number, and callers are **unverified**. So the
phone-facing model gets:

- **No tools, ever.** It cannot touch Atlas's tool registry — no invoices,
  no calendar, no files, no messages. It takes a message instead. This is
  not a config flag; caller tool access would be a separate reviewed feature.
- **Its own settings**, separate from Atlas's: `~/.config/atlas-phone/env`
  (secrets, ports, model) and `~/.config/atlas-phone/businesses.toml`
  (per-business identity). Nothing about the resident Atlas changes when you
  reconfigure the phone agent, and vice versa.
- **A non-thinking model** (`qwen2.5:7b-instruct` by default). Phone callers
  expect an answer in about a second; a thinking model reasons silently and
  callers hang up. If you point this at a thinking-capable model you must
  disable thinking explicitly.
- **A self-contained receptionist persona** built ONLY from the business
  profile — the resident Atlas persona is never imported (it carries the
  owner's private context, and on a live call it leaked the owner's nickname
  and role-played having tools). The prompt forbids inventing contact
  details, prices, or availability, and forbids claiming actions — the only
  facts it may state come from the profile's optional `facts` field, and its
  one promise is that a confirmed message reaches the owner.

Security on the wire: Twilio webhooks are HMAC signature-checked, the
websocket carries a secret token, and relay sessions from foreign Twilio
accounts are dropped. Config is validated at boot — a broken
`businesses.toml` stops the service loudly rather than mis-greeting a
customer. Calls to unmapped numbers hear a spoken config error and land in
the journal at ERROR.

## Call flow

1. Caller dials a mapped number.
2. Twilio POSTs `PUBLIC_BASE/voice/incoming` (signature-checked); the dialed
   number selects the business profile.
3. The bridge replies with TwiML pointing Twilio's ConversationRelay at
   `wss://…/voice/relay` (token + profile pinned in the URL). Twilio does STT.
4. The bridge streams a reply from the local model (persona + profile rules).
   Twilio does TTS. The model never leaves the machine — Twilio only sees text.

## Setup

1. `pip install aiohttp` into the Atlas venv (already present for core).
2. Copy `businesses.example.toml` → `~/.config/atlas-phone/businesses.toml`
   and fill in your real business(es). Every setting is commented there with
   its default. Check it any time with
   `python3 plugins/phone_agent/service.py --check` — it validates the config
   and every environment variable the config names, then exits without opening
   the call store or a socket, so it is safe to run beside the live bridge.
3. Create `~/.config/atlas-phone/env` (chmod 600) with:
   `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE`, `BRIDGE_PORT`,
   `PUBLIC_BASE`, `WS_TOKEN` (long random), `OLLAMA_URL`, `MODEL`,
   `ATLAS_REPO` (see the docstring in `service.py` for each).
4. Expose `BRIDGE_PORT` publicly at `PUBLIC_BASE`. With Tailscale Funnel
   (ports 443/8443/10000 only), a path mount keeps existing ports intact:
   `tailscale funnel --bg --https=10000 --set-path=/phone http://127.0.0.1:8890`
   → `PUBLIC_BASE=https://<host>.ts.net:10000/phone`. **Warning:** running
   `tailscale serve` on a port can silently drop that port's existing Funnel —
   re-check `tailscale funnel status` after any change, and never reassign a
   port another app depends on.
5. Point the Twilio number's voice webhook (POST) at
   `PUBLIC_BASE/voice/incoming`.
6. Install the service: put the checkout at `~/atlas-phone-deploy` (the path
   the unit files use) and run `deploy/phone/install.sh ~/atlas-phone-deploy`,
   then `systemctl --user enable --now atlas-phone-bridge`. The installer
   builds the venv and installs the units but deliberately starts nothing —
   see `deploy/phone/README.md` for the full runbook, the SSH tunnel and the
   failure alerts.
7. Verify: `curl -s http://127.0.0.1:<BRIDGE_PORT>/health` shows
   `"model_backend": "ok"` and your profiles — then call the number.

## Messages, caller ID, and hanging up

- After every call with caller turns, the bridge summarizes the transcript
  (one non-streamed pass on the same local model) into four labelled lines —
  `Name:` / `Callback:` / `Email:` / `Need:`, each `unknown` when the caller
  did not say — appended to the message pad (`MESSAGES_FILE`, default
  `~/atlas-phone-messages.md`) and stored as the call's message. Extraction
  failure writes a loud fallback entry pointing at the call in the dashboard,
  where the transcript is; a message never vanishes silently. Optional `NTFY_URL` + `NTFY_TOPIC` (set together
  or not at all) also push each note as a phone notification.
- The caller's real number comes from the phone network, not speech-to-text:
  it's injected into the call context so the agent *confirms* the callback
  number instead of transcribing digits.
- To hang up, the model ends its goodbye with the literal `[END CALL]`; the
  bridge scrubs the marker from speech, lets the goodbye play, then sends
  Twilio's end-session message. A caller speaking during that window cancels
  the hangup and the conversation continues.
- Profiles with `forward_to = "+1..."` can **transfer the call** via
  Twilio's `<Connect action>` callback (`/voice/action`, signature-checked)
  answering `<Dial>` to the forward number — original caller ID shown,
  apology + hangup on no answer. Profiles without `forward_to` never offer
  transfers, and a hallucinated transfer marker there is blocked rather
  than becoming a silent hangup.
- **The caller decides, not the AI.** A model marker alone never acts:
  `decide_call_action()` requires the CALLER to have explicitly asked —
  transfer needs a phrase like "operator" / "speak to a person" /
  "talk to {owner}" in the caller's recent words (or such a request plus a
  fresh "yes"), hangup needs a goodbye phrase or a standalone "no". Blocked
  attempts are WARNING-logged with the reason, and a blocked "connecting
  you now" is corrected out loud. Phrase lists are per-profile
  (`transfer_phrases` / `end_phrases`, dashboard-editable; empty = the
  standard set). Replies containing a question can never trigger an action.
- **Overpromise flagging**: commitment language the persona forbids
  ("booked", "you're all set", "I've sent") is detected deterministically —
  WARNING in the journal plus a ⚠ REVIEW prefix on the pad entry and push.
  Design + review record: `docs/superpowers/specs/2026-07-26-phone-call-
  control-hardening-design.md`.

## The call store (`callstore.py`)

Every call, every turn, every message and every operational event is written
to one SQLite file — `$PHONE_DATA_DIR/calls.db`, default
`~/.local/share/atlas-phone/calls.db`, created `0700` at boot. If that
directory cannot be created or the database cannot be opened, the bridge
**refuses to start**: a line that answers calls and records nothing is worse
than a line that is down.

- **The journal no longer holds what callers said.** It carries CallSid, turn
  number and character counts; the words live in the store, which has a
  retention horizon and a delete path (journald has neither).
- One `calls` row per call, opened at Twilio's `setup` and finalised in the
  relay's `finally:` with the outcome (`message_taken`, `transferred`,
  `caller_hung_up`, `no_info_given`, `agent_error`), the caller-turn count,
  overpromise flags and the per-call TTFT percentiles — the silence a caller
  actually sat through before the agent spoke, measured per turn.
- Calls made from a `CAtest…` CallSid or a `+1555…` number are flagged
  `is_test` and stay out of the owner's message list and numbers.
- `purge_expired(profile_key, retention_days)` deletes the transcript turns
  and blanks the free-text message summary past the horizon while keeping the
  call and message rows, so history and counts never move.
- `delete_caller("+1…")` removes every row this store holds for one caller
  (the "delete my data" path) and reports the CallSids it removed — the
  Markdown pad is append-only text, so those entries still have to be
  redacted by hand.

**Importing the old pad**: the messages taken before the store existed live
only in `~/atlas-phone-messages.md`. `migrate_pad.py` reads that file
(read-only — it never writes to the pad) and imports each entry:

```bash
python plugins/phone_agent/migrate_pad.py \
    --pad ~/atlas-phone-messages.md \
    --db ~/.local/share/atlas-phone/calls.db \
    --profile business_builders [--dry-run]
```

It prints counts only (never caller details) and is idempotent: a CallSid
already in the store is skipped, so running it twice imports nothing.

## Brains — switching the model that answers

A **brain** is a named model backend: a label, an OpenAI-compatible
`base_url`, a `model`, an optional `api_key_env` (the NAME of the env var in
`~/.config/atlas-phone/env` holding the bearer key — the key itself never
goes in the TOML), and an optional `extra_body` JSON object merged into every
chat request (that is where a cloud provider's explicit thinking kill-switch
lives). They are `[brains.*]` sections in the same `businesses.toml`, and the
top-level `active_brain` names the one answering calls.

Define none and nothing changes: `OLLAMA_URL` + `MODEL` from the env file are
the single implicit brain, exactly as before brains existed. Define some and
the dashboard shows them as radio buttons; saving switches instantly with no
restart, and **calls already in progress finish on the brain they started
with** — the brain is captured once per call, never mid-conversation. A
profile's own `model =` still wins over the brain's default model.

Validation is fail-closed like everything else here, at boot and on every
dashboard save: an `active_brain` naming a brain that does not exist, an
`api_key_env` naming an env var that is unset or empty, or an `extra_body`
that is not a JSON object is refused with a plain-English reason, and neither
the file nor the live config changes. `extra_body` merges *under* the call's
own keys, so a preset can never silently override `model`, `messages`, or
`stream`. `/health` and the dashboard chips always probe the ACTIVE brain, so
a bad switch shows up immediately instead of at the next call.

**Privacy follows the brain**: on a local brain, caller text never leaves the
machine; point `active_brain` at a hosted API and every caller turn is sent to
that vendor. Example config: `businesses.example.toml`.

## What a business profile can set

Beyond the four required keys (`business_name`, `services`, `owner_name`,
`greeting`), a profile can carry:

* **Opening hours** — `timezone` (IANA), `hours` (a day table; a day left out
  is closed, `"18:00-02:00"` is an overnight shift), `holidays` (dates or
  `"2026-12-24..2026-12-26"` ranges), `after_hours` (`message` | `transfer` |
  `same`) and an `after_hours_greeting`. No `hours` table = open all the time.
  `timezone` is required as soon as hours or holidays exist; without them the
  host's zone is used and the boot log says so.
* **What the caller is told** — `ai_disclosure` and `recording_notice`, both
  on by default, composed into the greeting by one function the dashboard
  preview also calls. When the greeting ends in a question the notices are
  spoken *before* it, so the caller does not talk over them. Neither can be
  switched off without `ack_disclosure_waived = true` in the same profile.
* **How the call sounds** — `language`, `tts_provider`, `voice`,
  `transcription_provider`, `hints`, `ignore_backchannel`; these become the
  `<ConversationRelay>` attributes. `language = "multi"` is accepted only with
  Deepgram + ElevenLabs.
* **Per-business plumbing** — `brain`, `messages_file`, `ntfy_url`/`ntfy_topic`,
  `max_call_seconds`, `caller_turn_budget_per_hour`, `block_list`,
  `retention_days`.

Every one of them is validated fail-closed at boot, on `--check`, and on every
dashboard save, with a sentence an owner can act on. Settings the bridge does
not read are kept in the file untouched and named in a boot warning — a typo
does nothing, but it never does nothing silently.

## Who may sign in, and whose name is on it

`[owners.<name>]` gives one dashboard login: `token_env` NAMES the environment
variable holding their token (never the token itself) and `profiles` lists the
businesses they may see, or `["*"]` for all of them. With no `[owners.*]` at
all the legacy `ADMIN_TOKEN` is the single login and sees everything, so
nothing breaks on an upgrade. `[branding]` puts a reseller's `vendor_name`,
`product_name`, `logo_path`, `support_email`, `colors` and `fonts` over the
dashboard; left out, it is plainly branded with its built-in palette.

## Owner dashboard

Set `ADMIN_TOKEN` in the env file and the bridge also serves a control
panel on `127.0.0.1:ADMIN_PORT` (default 8891) — expose it to the owner
**tailnet-only** (e.g. `tailscale serve --bg --https=8447
http://127.0.0.1:8891`), never on the public path Twilio uses. It edits
the number→business mapping and every profile field (greeting, services,
facts, extra prompt instructions, forward number), picks the active brain
when more than one is defined, shows the exact live prompt per business,
tails the message pad, and lists the last ten real calls from the call store
with their transcripts (test calls excluded, caller numbers masked).
Saves go through the same fail-closed validation as boot — a bad edit is
rejected with the reason and changes nothing — and good saves hot-apply
with no restart; in-flight calls keep the settings they started with.

## Operating

- Every call is transcribed into the call store (`calls.db`) and read from
  the owner dashboard. The journal carries CallSid, turn numbers and
  character counts only — never what anyone said (audit H-7).
- Ask Atlas "is the phone line up?" — that's the `phone_line_status` tool in
  this plugin (override the probe URL with `ATLAS_PHONE_HEALTH_URL`; loopback
  only).
- Add a business: new `[profiles.*]` + `[numbers]` entry, restart the service.
- Rotated the Twilio auth token? Update the env file and restart, or every
  webhook will be rejected as a bad signature.

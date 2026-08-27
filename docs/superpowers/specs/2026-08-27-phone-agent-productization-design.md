# Phone agent productization — design

**Date:** 2026-08-27 · **Branch:** `feat/phone-agent-product` (from `feat/phone-agent-plugin`)
**Goal (William, verbatim):** "audit the voice part of atlas code that is the phone agent it has a front end also so that we can make this work for any business see what is the industry standard and make sure our voice phone agent and dashboard is 100 %"

**Inputs:** the three audits committed alongside this spec —
`2026-08-27-phone-agent-code-audit.md` (40-item capability checklist: 12 present / 8 partial / 20 missing),
`2026-08-27-phone-agent-dashboard-audit.md` (routes, screenshots, WCAG measurements, redesign requirements),
`2026-08-27-ai-receptionist-industry-standard.md` (72-item industry checklist, compliance, latency, pricing — all cited).

## 0. What "100%" means here

A paying business — not Business Builders — can be put on this product and every one of William's hard rules holds: no placeholders, no mock data shown as real, no silent failures, professional customer-facing design, and every gap that remains is named in plain English. Concretely, "100%" is:

1. **One codebase.** The code answering the phone is the code in git with the tests — always. (Today production is an unversioned copy that is ahead of the tested copy and fails its own suite.)
2. **A second customer is safe.** Business A's owner can never see business B's callers. Each business has its own hours, timezone, greeting, disclosure lines, message destination, notification target, and login.
3. **A message never vanishes silently.** Every failure path that can lose a caller's message either delivers it another way or makes the line report itself unhealthy (which pages).
4. **Compliance defaults are the easy path.** Recording/transcription notice and AI disclosure are on by default, editable, and visible in the dashboard's greeting preview.
5. **The owner has a real dashboard.** Calls, transcripts, messages with status, settings that save per section and never lose typed input, hours, numbers, notifications, brain choice with production-use badges, and a change history — in Business Builders' brand (configurable, so a reseller can rebrand).
6. **What is not done is listed**, with the exact step that unblocks it.

## 1. Assumptions (in place of clarifying questions — the `/goal` directive rules out blocking)

| # | Assumption | If wrong |
|---|---|---|
| A1 | The product stays on **Twilio ConversationRelay** (Twilio does STT/TTS; we own the brain, logic, dashboard). No replatform to Retell/Vapi/Media Streams in this pass. | The all-local Media Streams pipeline noted on 2026-07-26 stays a future decision; nothing here blocks it. |
| A2 | **Transcripts are stored; audio is not recorded** in this pass. The recording/transcription notice is still on by default because transcripts are "recording" under most state laws. | `record_calls` per-profile toggle + `<Start><Recording channels="dual">` is a bounded follow-up (Phase 3). |
| A3 | The dashboard is **server-rendered (aiohttp + Jinja2) with htmx for section saves**, no build step, no CDN — maintainable by William with an AI session. | A SPA would need a JS toolchain nobody here maintains. |
| A4 | **Business Builders is the vendor brand** of this install; the client's business name is the subject. Branding is a `[branding]` config table so a reseller can change it — no BB values hardcoded in code. | — |
| A5 | The live line may be **cut over to the git checkout** in this session (a ~3-second restart) once the unified code passes its suite and a websocket simulation — with a rollback tag and the old directory archived, never deleted. | If William wants to hold the cutover, everything is staged and the command is one line. |
| A6 | The **brain key** is William's decision and is NOT changed here (HARD RULE: explicit, attributable billing; never a fallback to a subscription). The dashboard will show the current `glm_52_test` state as a red production-safety banner until he switches. | — |
| A7 | Twilio number settings (fallback URL, status callback, SMS URL) may be corrected via the API — they are additive/safer, and previous sessions changed VoiceUrl on his behalf. | Rollback = one API call each; values recorded in the plan. |
| A8 | No outbound calling, no SMS *sending* (A2P 10DLC registration is a 10–15 day William step), no payments by voice, no HIPAA claims. | Listed in §7. |

## 2. Approaches considered

**(a) Rebuild on a hosted builder (Retell/Vapi).** Buys latency tooling and dashboards, costs $0.13–0.31/min vs our ≈$0.09, and moves caller data to another vendor. Rejected: the audit shows our call-control core is *better* than the market's; what is missing is the product layer, which a builder platform would not supply either.

**(b) Patch the deployed `bridge.py` in place.** Fastest to "green" and exactly how the brains feature shipped untested. Rejected: it perpetuates the unversioned fork.

**(c) Unify into the plugin, deploy from git, then build the product layer in the unified code — recommended.** Every fix is written once, tested once, and shipped from a checkout. The dashboard is rebuilt as its own package with the audit's information architecture. This is the boring path and the only one compatible with rule 1.

## 3. Architecture (what changes, what stays)

### 3.1 Stays (deliberately — do not regress)
- Caller-facing model has **zero tools**; deterministic caller-consent gates for transfer/end; marker scrubber; overpromise detector; self-contained persona; fail-closed config validation shared by boot and dashboard save; Twilio HMAC validation on every webhook; `PUBLIC_BASE`-derived signature URLs; access log off.
- `businesses.toml` as the config format, hot-applied, with `api_key_env`-style indirection (secrets never in TOML).
- Reverse-SSH tunnel to the BB VPS + nginx as the public front door; `tunnel-guard.sh`.

### 3.2 Source of truth and deploy
- `plugins/phone_agent/` is the only editing target. `service.py` absorbs the deployed `bridge.py`'s brains feature (the diff is strictly additive); `admin.py` is replaced by an `admin/` package (§5).
- **New:** `deploy/systemd/atlas-phone-tunnel.service` + `deploy/phone/tunnel-guard.sh` enter the repo; `deploy/systemd/atlas-phone-bridge.service` points at a checkout and gains `Wants=network-online.target`, `Restart=always`, `StartLimitIntervalSec/Burst`, `OnFailure=atlas-phone-alert@%n.service` (a oneshot that pushes to ntfy — a failing unit must page, not loop).
- **Live layout after cutover:** `~/atlas-phone-deploy` = git worktree of this branch; its own `.venv` (aiohttp, jinja2); units installed from `deploy/systemd/`. `~/atlas-phone-bridge` → renamed `~/atlas-phone-bridge.archived-2026-08-27` (rollback for 30 days).
- Rollback tag before cutover: `pre-phone-product-cutover-2026-08-27` on the archived copy's contents committed to a `deploy-archive/2026-08-27` branch.

### 3.3 Config schema additions (`businesses.toml`, all validated fail-closed at boot and on save)

```toml
[branding]                      # vendor branding of the dashboard (NOT the client's business)
vendor_name = "Business Builders"
product_name = "Phone Agent"
logo_path = "/home/magiccat/BusinessBuilderWebsiteCurrent/BBcurrentsite/BBCurrent/public/assets/images/logo-full-light.png"  # optional
support_email = "donovan@business-builder.online"   # shown on the sign-in page; optional

[owners.william]                # dashboard logins; token via env NAME, never inline
token_env = "PHONE_OWNER_WILLIAM_TOKEN"
profiles = ["business_builders"]   # or ["*"] for every profile (the legacy ADMIN_TOKEN behaves as ["*"])

[profiles.business_builders]
# existing keys unchanged: business_name, services, owner_name, greeting, assistant_name,
# forward_to, model, facts, extra_instructions, transfer_phrases, end_phrases, assistant_aliases
timezone = "America/New_York"          # IANA; REQUIRED once hours/holidays are set; else boot WARNING + dashboard nag
hours = { mon = "09:00-17:00", tue = "09:00-17:00", wed = "09:00-17:00", thu = "09:00-17:00", fri = "09:00-17:00" }  # omitted day = closed; no table = always open
holidays = ["2026-11-26", "2026-12-25"]  # dates or "2026-12-24..2026-12-26"
after_hours = "message"                # message | transfer | same   (default message)
after_hours_greeting = "Thanks for calling Business Builders. We're closed right now, but I can take a message and William will call you back."
ai_disclosure = true                   # default true → "I'm an AI assistant" sentence composed into the opening line
ai_disclosure_text = "I'm the AI assistant for {business_name}."
recording_notice = true                # default true (transcripts are stored)
recording_notice_text = "This call may be recorded and transcribed."
language = "en-US"                     # ConversationRelay language (default "en-US", always emitted); "multi" allowed only when BOTH providers below are set explicitly to Deepgram+ElevenLabs (validated)
tts_provider = "ElevenLabs"            # Google | Amazon | ElevenLabs; DEFAULT "" = provider default, attribute OMITTED from the TwiML
voice = ""                             # provider voice id; DEFAULT "" = provider default, attribute OMITTED from the TwiML
transcription_provider = "Deepgram"    # Google | Deepgram; DEFAULT "" = provider default, attribute OMITTED from the TwiML
hints = ["Business Builders", "Atlas"] # STT bias terms
ignore_backchannel = true
brain = ""                             # per-profile brain override; empty = active_brain
messages_file = "~/atlas-phone-messages-business_builders.md"   # per-business pad; default derived from key
ntfy_url = ""                          # per-business; empty = env NTFY_URL/NTFY_TOPIC
ntfy_topic = ""
max_call_seconds = 600                 # watchdog: wrap-up line then end
caller_turn_budget_per_hour = 60       # per caller-ID; exceed → polite refusal + event
block_list = []                        # E.164; blocked → short spoken line + hangup, logged
retention_days = 90                    # transcript/summary purge horizon (call rows and messages stay)
```

Validation rules added: `forward_to` may not equal any mapped number (call loop); `timezone` must resolve via `zoneinfo`; `hours` values must be `HH:MM-HH:MM` (overnight ranges allowed); `language="multi"` requires both `transcription_provider = "Deepgram"` and `tts_provider = "ElevenLabs"` written out explicitly (an empty provider means Twilio's own, which cannot do it); non-string scalars are preserved by the emitter (bool/int/list/table), never stringified.

Unknown keys, ruled 2026-08-27 (the earlier "unknown keys are rejected (already)" was never true of the code and conflicts with the hardening pass): an unknown key inside a `[profiles.*]` section is **preserved byte-for-byte and named in a boot WARNING** — Task 3's M-6 work exists so that a setting somebody hand-wrote survives a dashboard save, and rejecting unknown keys and preserving hand-added keys are mutually exclusive. A misspelt setting therefore does nothing, but never does nothing silently. Unknown keys inside `[brains.*]`, `[branding]` and `[owners.*]`, and unknown top-level keys, **are rejected**: those tables are entirely the product's, nobody hand-annotates them, and a setting the bridge does not read there is one that looked applied and never was.

### 3.4 Call store — `callstore.py` (SQLite, `PHONE_DATA_DIR` default `~/.local/share/atlas-phone/`, file `calls.db`, WAL mode)
Tables: `calls` (call_sid PK, profile_key, from_number, to_number, started_at, ended_at, duration_s, caller_turns, outcome ∈ {message_taken, transferred, caller_hung_up, no_info_given, agent_error, blocked, rate_limited, after_hours_message}, decision_reason, brain, model, prompt_tokens, completion_tokens, ttft_ms_p50, ttft_ms_p95, overpromise_flags JSON, notify_status, twilio_status, twilio_duration_s, twilio_price, is_test) · `turns` (call_sid, n, role, text, ts, ttft_ms) · `messages` (id, call_sid, profile_key, caller_name, callback, email, need, summary, status ∈ {new, in_progress, done}, note, created_at, updated_at, review_flag) · `events` (ts, profile_key, call_sid, level, kind, detail — summarizer failure, ntfy failure, signature rejection, config rejection, watchdog, rate-limit, block) · `config_changes` (ts, actor, summary, diff, applied, reason) · `notify_log` (ts, profile_key, target, ok, error) · `sessions` (id, owner_key, created_at, last_seen).
Behaviour: one row per call written at `setup`, finalised in a `finally:`; per-turn TTFT recorded; migration imports the 21 pad entries with `is_test=1` for `^CAtest`/`+1555…`; nightly purge of `turns` + `messages.summary` older than `retention_days`; `delete_caller(from_number)` removes every row for that caller (CCPA/GDPR path); journald lines carry CallSid + counts only, never caller text.

### 3.5 Runtime hardening (the "no silent failure" pass)
C-4 loop guard + delivery in `finally` · H-1 pad-write failure → urgent ntfy + fallback file + `events` row + health degrade · H-2 ntfy failure counter → `/health` 503 with `ntfy: FAILING` (tripwire pages) · M-2 turn-race guard on history append and on every `send_json` · M-3 `else:` logging + `dtmf` recorded as a turn · M-7 brain probe logs the reason · M-8 tunnel unit start-limit + `OnFailure` · M-4 summarizer wraps the transcript in explicit untrusted-data delimiters, caps note length · H-6 `max_call_seconds` watchdog + per-caller turn budget · H-8 per-call websocket token = HMAC-SHA256(`WS_SECRET`, CallSid ‖ expiry) carried in the TwiML URL, verified with `compare_digest`, single-use · H-9 public `/health` → `{"status":"ok"}`/503 only; detail moves to the dashboard's `/health/detail` · M-6 config backup `businesses.toml.bak-<ISO>` (keep 100) + `config_changes` row before every replace · M-9 timezone-aware timestamps everywhere · M-10 forward-to loop check · L-1/L-3/L-6 as listed.

### 3.6 Hours engine — `hours.py`
`open_state(profile, now) -> {open: bool, reason: 'hours'|'holiday'|'always', next_open: datetime|None}` using `zoneinfo`. Applied at `voice_incoming`: closed → `after_hours_greeting` (if set) and, for `after_hours = "message"`, the TRANSFERRING persona section is omitted and `decide_call_action` cannot transfer (the agent takes a message). Pure functions, table-driven tests with fixed clocks (overnight ranges, DST edges, holidays, missing timezone).

### 3.7 Compliance defaults
Opening line = `greeting` + (ai_disclosure ? ai_disclosure_text) + (recording_notice ? recording_notice_text), composed by one function that the dashboard preview also calls, so what the owner sees is what the caller hears. Neither can be disabled without `ack_disclosure_waived = true` in the profile (fail-closed at boot with a clear error). Spoken opt-out phrases ("stop calling me", "take me off your list") are detected and logged as an event on the call.

### 3.8 ConversationRelay attributes
Emitted per profile: `language` (always), `ttsProvider`, `voice`, `transcriptionProvider` and `hints` (each **only when the profile sets it** — an empty attribute is a value to Twilio, not "use your default", and omitting them is what keeps this release from changing the voice existing callers hear), `ignoreBackchannel`, `dtmfDetection="true"`, `welcomeGreetingInterruptible="none"` (disclosure must be heard). `reportInputDuringAgentSpeech` stays at its default (`none`) in this pass — the bridge's turn logic is not designed for input during agent speech and changing it needs real-call testing; recorded in §7.

### 3.9 Twilio-side settings (via API, values recorded in the plan)
`voice_fallback_url` → a static TwiML on the BB VPS (`/phone/fallback.xml`: `<Dial>` to the profile's `forward_to`, else `<Say>` an apology) so an outage on this machine forwards callers to a human instead of "application error" · `status_callback` → `/voice/status` (signed) updating `calls.twilio_*` · `sms_url` → `/sms/incoming` (signed) writing a message + ntfy, replying with empty TwiML (no auto-reply until 10DLC). Warm transfer: `<Dial><Number url="/voice/whisper?call=…">` plays a one-line summary to the human before connecting (signed, TwiML `<Say>`).

## 4. Tenancy model
- Every read in the dashboard is scoped to the session's `profiles`. Legacy `ADMIN_TOKEN` = all profiles (so nothing breaks on cutover).
- Per-profile `messages_file`, `ntfy_*`, `brain`; calls/messages/events rows carry `profile_key`.
- Cookies hold a random session id (server-side table), `HttpOnly; Secure; SameSite=Strict`, 14-day sliding; CSRF token per session on every mutating form + `Origin` check; `/logout` and "sign out everywhere"; failed logins logged with source IP, 5/15 min then 60 s lockout; `Cache-Control: no-store`, `nosniff`, `Referrer-Policy: no-referrer`, CSP `frame-ancestors 'none'`.

## 5. Dashboard (owner-facing) — `plugins/phone_agent/admin/`
Information architecture from the dashboard audit §E, in owner vocabulary, WCAG 2.2 AA, three type sizes / two weights, 4-px spacing scale, green/amber/red reserved for health.
Screens: **Sign in** · **Overview** (line-status band composed from bridge/model/Twilio-verified-24h/number-mapping/notifications; production-safety banner when the active brain is marked test-only; today strip; 7-day sparkline; latest messages; alerts) · **Calls** (+ detail: conversation-style transcript, summary, caller chips, outcome, brain, TTFT, prompt that was live) · **Messages** (status workflow, tel:/copy, notes, CSV export) · **Settings per business** (sectioned, htmx per-section save, input preserved on validation error, greeting preview showing the composed opening line, facts as rows, transfer with consequence-confirm, advanced collapsed) · **Hours & availability** · **Numbers** (assignment via select, Twilio webhook status "verified N minutes ago") · **Notifications** (per-business targets, send-test with real result, delivery log) · **Brain** (cards with production-use badge, reachability, confirm-to-switch) · **Activity** (config history with restore, sign-ins, service events) · **Delete business** = type-the-name confirm, soft-delete, 30-day restore.
Tech: aiohttp + Jinja2 templates + vendored `htmx.min.js`; CSS custom properties = BB tokens (`--bb-black #0a0a0a`, `--bb-black-warm #1c1812`, `--bb-cream #f5e6c8`, `--bb-orange #e85d1a`, `--bb-teal`, `--bb-gold #d4a847`, `--bb-brick #c23b22`; body Bricolage Grotesque, display Funnel Display, wordmark Lobster Two — Google Fonts with system fallbacks) driven by `[branding]`; no blocking subprocess in handlers (health cached by a background task with "last checked").
**Mockup first:** a Claude Design canvas with BB branding (William's request) covering Sign in, Overview, Calls/detail, Messages, Settings, Hours, Brain — desktop + mobile — so he can tweak visually before implementation.

## 6. Verification standard for "done"
- Unit tests for every new module (hours, callstore, config schema, token, watchdog, gates unchanged) — suite green on the **shipped** artifact.
- WebSocket simulation against the running bridge for: normal message call, after-hours call, blocked caller, rate-limited caller, transfer with whisper TwiML, watchdog wrap-up, malformed frame mid-call (message still delivered), ntfy down (health 503 + urgent fallback).
- Public probes: `/health` minimal; signed webhook 200; forged 403; `/voice/status` signed; `/sms/incoming` signed; VPS fallback TwiML 200.
- Dashboard: Playwright screenshots desktop + mobile of every screen; contrast check; keyboard pass; validation-error round-trip preserves input; stale-form conflict rejected.
- Live cutover: unit active from the checkout, tripwires green, William's real test call = the one leg only he can do.

## 7. NOT DONE in this pass (each with the unblocking step)
1. **Compliant brain.** Live brain is `glm_52_test` (Z.AI coding plan — prohibited for production bots). Unblock: William adds Z.AI balance and clicks `glm_52_api`, or supplies another API key (his HARD RULE: explicit, attributable). Dashboard shows a red banner until then.
2. **SMS sending** (booking links, owner SMS) — needs A2P 10DLC registration (10–15 days, privacy/terms URLs). Inbound SMS is captured; nothing is sent.
3. **Calendar booking** (Google/Outlook/Calendly/Jobber…) — the 2026 dividing-line feature; a separate design.
4. **Website-scrape knowledge base** — the `facts` editor exists; auto-build from URL is a separate design.
5. **Audio recording + playback** — `record_calls` toggle + `<Start><Recording channels="dual">` + retention; the notice already covers transcripts.
6. **Spam screening beyond block list + rate limit** (STIR/SHAKEN attestation, known-spam lists).
7. **`reportInputDuringAgentSpeech`** tuning — needs real-call testing.
8. **HIPAA/BAA, SOC 2, terms of service** — legal/commercial, William + counsel.
9. **Multi-language auto-detect** is *configurable* (validated constraint) but untested with a real Spanish caller.
10. **P95 latency against the 700 ms bar** — instrumented (TTFT per turn) but no tuning done; GLM-5.2 measured 1.4–2.8 s TTFT on 2026-07-31.

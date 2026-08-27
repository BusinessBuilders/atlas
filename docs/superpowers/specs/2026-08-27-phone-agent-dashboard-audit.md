# Atlas Phone Agent — Owner Dashboard Audit

**Audited:** 2026-08-27
**Target:** `/home/magiccat/atlas-phone-bridge/admin.py` (306 lines, LIVE) — served by `bridge.py` PID 1251260 on `127.0.0.1:8891`, exposed tailnet-only at `https://magiccat.tail09c6c9.ts.net:8447`.
**Git copy compared:** `/home/magiccat/atlas-phone-plugin-wt/plugins/phone_agent/admin.py` (275 lines, HEAD `1d6acf3`).
**Method:** full source read of both files + `bridge.py` supporting functions; page HTML captured read-only with `curl -b atlas_admin=<token>` (GET only — **no form was submitted, no POST was made, no radio changed**); HTML re-served from a throwaway static port and screenshotted with Playwright at 1440×900 and ≈390×844. Screenshots and captured HTML in this directory.

> **Read-only compliance:** the only network calls made to the live service were two `GET /` requests (one authenticated, one not, to capture the sign-in state). Nothing was written. The temporary static server on :8977 was stopped and the port verified free.

---

## A. Inventory — routes, auth, fields, data

### A.1 Auth mechanics

| Aspect | Behavior | Line ref |
|---|---|---|
| Where the token goes | **HttpOnly cookie `atlas_admin`**, set by `POST /login`. Not a URL query param, not a header. | `admin.py:26`, `:89` |
| Cookie value | **The ADMIN_TOKEN itself**, verbatim — `resp.set_cookie(COOKIE, token, ...)`. There is no session ID, no derived value, no rotation. | `admin.py:89` |
| Cookie flags | `httponly=True`, `samesite="Strict"`, `max_age=2592000` (30 days). **`secure=True` is NOT set.** | `admin.py:89-90` |
| Comparison | `hmac.compare_digest` on both the cookie (`authed()`) and the form field (`login()`) — constant time. | `admin.py:82`, `:86` |
| Gate on every route | `index` and `save` both call `authed()` first; failure renders the login page (HTTP 200, not 401/403). | `admin.py:151-152`, `:229-230` |
| Existence gate | Dashboard is only started when `ADMIN_TOKEN` is non-empty. | `bridge.py:1445-1464` |
| Bind | `web.TCPSite(admin_runner, "127.0.0.1", ADMIN_PORT)`, default 8891. | `bridge.py:1460`, `:167` |
| **CSRF on Save** | **No token, no Origin check, no Referer check, no double-submit.** The only protection is the implicit `SameSite=Strict` cookie. | `admin.py:228-300` |
| Logout | **No route exists.** No way to end a session short of changing `ADMIN_TOKEN` and restarting the service. | `admin.py:302-306` |
| Failed-login handling | No rate limit, no lockout, no delay, no log line. `access_log=None` on the runner, and `login()` emits nothing on failure — brute force is silent and unlimited. | `admin.py:86-87`, `bridge.py:1458` |
| Security headers | None — no CSP, no `X-Frame-Options`, no `Referrer-Policy`, no `Cache-Control` on a page containing customer messages. | `admin.py:55-62` |

### A.2 Routes (complete — there are three)

| Method | Path | Handler | Effect |
|---|---|---|---|
| `GET` | `/` | `index` | Renders the entire dashboard, or the login page if unauthenticated. `admin.py:150-226`, `:303` |
| `POST` | `/login` | `login` | Sets the cookie on token match; re-renders login with "Wrong token." otherwise. 303 → `/`. `admin.py:84-91`, `:304` |
| `POST` | `/save` | `save` | Rebuilds the whole config from the form, validates, **hot-applies to the live phone line**, 303 → `/?saved=1`. `admin.py:228-300`, `:305` |

There is no `/health`, no `/logout`, no JSON API, no per-section endpoint. `/health` exists on the *bridge* app (port 8890), not on the admin app (`bridge.py:1424-1428`).

### A.3 Editable fields

**Brain (radio group, `active_brain`)** — `admin.py:127-148`. One radio per `[brains.*]` in `businesses.toml`; hidden entirely when only the implicit env-default brain exists (`admin.py:129`). Label + model + base_url shown. **Not present in the tracked git copy** (see A.6).

**Numbers** — one free-text `<textarea name="numbers_text">`, format `+15551234567 = profile_name`, one per line. `admin.py:207-209`, parsed at `:240-248`. E.164 and profile-existence are enforced server-side in `bridge.py:587-595`.

**Per business profile** — 12 fields, all named `{key}::{field}` (`admin.py:93-125`), matching `_PROFILE_KNOWN_KEYS` (`bridge.py:733-737`):

| Field | Control | Required? |
|---|---|---|
| `business_name` | text | yes (`_PROFILE_REQUIRED_KEYS`) |
| `services` | text | yes |
| `owner_name` | text | yes |
| `greeting` | text | yes |
| `assistant_name` | text | no (default "Atlas") |
| `forward_to` | text | no — E.164 validated if present (`bridge.py:604-609`) |
| `model` | text | no (per-profile model override) |
| `facts` | textarea `.tall` | no |
| `extra_instructions` | textarea `.tall` | no |
| `transfer_phrases` | textarea | no — empty means "standard set" |
| `end_phrases` | textarea | no — empty means "standard set" |
| `assistant_aliases` | textarea | no |
| `{key}::__delete` | **checkbox** | destructive |

**Add a business** — a single text input `__new_key`; submitting it creates an empty profile and *deliberately raises a pseudo-error* to re-render the form (`admin.py:264-276`).

**One `<form>`, one `<button>`.** Everything above — brain switch, numbers, all profiles, deletions, new profile — is submitted by the single `Save & apply` button (`admin.py:181` open, `:217` button, `:221` close). Verified in captured markup: `<form` count = 1, `<button` count = 1.

### A.4 Data displayed (read-only)

| Panel | Source | Line ref | State on the live line right now |
|---|---|---|---|
| Status chips | `health_snapshot()` — bridge ok, model backend reachable, active brain + model, number count, ntfy on/off | `admin.py:157-163`, `bridge.py:1398-1421` | `bridge ok` · `model ok` · `glm_52_test: glm-5.2` · `1 number(s)` · `ntfy on` |
| Live prompts | `SYSTEM_PROMPTS` dict, one `<details><pre>` per profile | `admin.py:173-177` | 1 collapsed entry, `business_builders` |
| Message pad | **last 6000 characters** of `~/atlas-phone-messages.md`, raw, in one `<pre>` | `admin.py:179-183` | 21 entries / 6,885 bytes → the oldest 885 bytes are cut, so the panel **opens mid-word on the string `0142`** |
| Recent calls | `journalctl --user -u atlas-phone-bridge -n 400`, grepped for 6 substrings, last 40 lines, run in a thread with a 5 s timeout | `admin.py:185-200` | **`(no calls in the recent journal)` — permanently empty** (verified: `journalctl --user -u atlas-phone-bridge` returns `-- No entries --`) |

### A.5 What it does NOT show

No call log (date, duration, outcome, answered/missed, recording). No audio playback. No transcript in the UI — every pad entry instead tells the owner to run `` `journalctl --user -u atlas-phone-bridge` ``. No caller history or repeat-caller grouping. No message status (new/read/done/callback-made) — the pad is append-only text. No search or filter. No analytics of any kind: calls/day, answered vs missed, avg duration, outcomes, cost per call, spend against the Z.AI balance. No business hours, holidays, or after-hours behavior. No voice selection or TTS preview. No transfer rules beyond one `forward_to` number. No notification settings (ntfy is env-only, shown as a chip). No Twilio number management, billing, or number provisioning. No config history, no diff, no undo. No service controls (restart, pause the line, take a voicemail-only mode). No error surface — a failed summarizer or failed ntfy push is logged at ERROR to journald only (`bridge.py:1018`, `:1039`), and the dashboard never shows it.

### A.6 Version-control drift (material)

- **`/home/magiccat/atlas-phone-bridge/` is not a git repository** (`fatal: not a git repository`). The code that hot-applies changes to a real business phone line is untracked, with no history and no rollback.
- The tracked plugin copy is **behind the live file by 39 diff lines**: it has no `get_brains`, no `_brain_card`, no `active_brain` handling, and its `emit_business_toml` call drops brains (`plugin/admin.py:250` vs live `:279-281`). Deploying the tracked copy over the live one would silently delete every `[brains.*]` section from `businesses.toml`.
- `~/.config/atlas-phone/` holds `businesses.toml` with **no `.bak`** (the `env` file has one; the config does not).

---

## B. Screenshot findings

Files: `dashboard-desktop.png` (1440×4835 full page), `dashboard-desktop-fold.png`, `dashboard-mobile.png` (375×7410 full page), `dashboard-mobile-fold.png`, `login-mobile.png`, plus `mobile-crop-pad.png` / `mobile-crop-fields.png`.

### B.1 What it looks like

A single dark page, 960px max-width, centered, system font, no logo, no navigation, no footer. Cards are `#171d24` on `#101418` with 1px `#232c36` borders. One accent colour (`#2563eb`) used once, on the only button. It reads as a competent internal debug tool — the visual vocabulary of a home-lab admin page, not of a product a small business pays for.

**Page length: 4,835px on desktop (5.4 screens) and 7,410px on mobile (8.8 screens).** There is no navigation, no anchors, no sticky header, no sections that collapse. Everything is always open.

### B.2 Broken

1. **The message pad opens mid-word.** `pad = f.read()[-6000:]` on a 6,885-byte file slices through the middle of an entry. The first thing under "MESSAGE PAD" is the orphan string `0142` followed by a sentence with no header. Visible in both screenshots. As the pad grows this gets worse, never better.
2. **"Recent calls" is empty and always will be.** It shells out to `journalctl --user -u atlas-phone-bridge`, which returns `-- No entries --` on this machine — the unit's journal has been vacuumed. The last thing an owner sees at the bottom of the page is `(no calls in the recent journal)` while 21 real calls sit in the pad above it. The only call-history feature in the product is a dead panel.
3. **Fabricated test data is interleaved with real customer messages, indistinguishable.** The pad contains three synthetic entries — `CallSid CAtest_pad_1784591071/…117/…148`, a caller named "Sarah" from `sarah@rosebakery.example` — plus ~10 entries from `+1555…` test numbers and entries with CallSids like `CAtest_guard_…`, `CAtest_transfer_…`, `CAtest0000000000000000000000000042`. They render identically to the six genuine calls from a real caller. This is exactly the "mock data presented as real" failure mode: an owner reading this panel cannot tell which messages to act on.
4. **One entry on-screen reads `MESSAGE EXTRACTION FAILED — read the full transcript in the journal (CallSid CAtest…042)`.** The product's own failure text is customer-visible, unstyled, and points at a Linux command.
5. **The live line is running on a brain whose own label says it must not be.** The selected radio reads *"GLM-5.2 cloud — TEST ONLY (coding-plan endpoint; against Z.AI terms for production use)"*. The status chip above it says only `glm_52_test: glm-5.2` in neutral grey — no warning colour, no banner. A dashboard whose job is to make the state of a business phone line obvious is presenting a terms-violating production config as normal.
6. **`facts` is empty for the live business.** The field labelled "the ONLY specifics the agent may state (email, hours, service area, pricing posture)" is blank, which is why so many pad entries read "caller wanted to book an appointment but did not provide enough information." The dashboard shows an empty box and no indication that this is why the agent can't answer questions.

### B.3 Ugly / confusing

7. **60% of the page is a monospace wall of raw Markdown.** The pad is rendered as literal source: `## 2026-07-26 09:50 EDT — …`, `*(CallSid CAxxx, 1 caller turns — full transcript in `journalctl --user -u atlas-phone-bridge`)*`. Every single message ends by instructing a non-technical owner to run a Linux command. "1 caller turns" is un-pluralised.
8. **Newest message is at the bottom** (the pad is append-only, `bridge.py:1026`). To see today's call you scroll past 20 older ones.
9. **The Save button is stranded mid-page.** It sits at ~y=913 of 4,835 — above Live prompts, Message pad, and Recent calls. From the bottom of the page you scroll up ~3,900px to save. On mobile it is ~4,300px above the fold you end on.
10. **`<h2>` does three unrelated jobs**: section header ("NUMBERS"), card title inside a card ("PROFILE: BUSINESS_BUILDERS"), and action-card title ("ADD A BUSINESS"). All uppercase, all the same size, so hierarchy is flat — a card title and a page section are visually identical.
11. **The most important text is the least readable.** `.hint` is `#68747f` at 12.5px = **3.55:1 contrast, fails WCAG AA (needs 4.5:1)** — and the hints carry the load-bearing warnings, e.g. *"Listing your own REPLACES the standard set."* Measured ratios for the whole palette are in B.5.
12. **Field boundaries are nearly invisible.** Input border `#2a3642` on card `#171d24` = **1.38:1**; card border `#232c36` on page `#101418` = **1.31:1**. WCAG 2.2 SC 1.4.11 requires 3:1 for UI component boundaries. Empty textareas read as holes rather than fields.
13. **The delete control is a bare native checkbox**, ~13×13px, labelled "delete this profile" in small red text at the bottom of a long card. WCAG 2.2 SC 2.5.8 wants 24×24 minimum. It is the single most destructive control on the page and the smallest.
14. **No `:focus` or `:focus-visible` rule exists anywhere in the CSS** (grep: 0 matches). Keyboard users get only the UA default ring on a dark background.
15. **12 of 18 form controls have no programmatic label** — 18 `<label>` elements, **0 with `for=`**, **0 inputs with `id=`**, **0 `aria-*` attributes**. Only the brain radios and the delete checkbox wrap their input (implicit association). Screen readers announce the profile fields as unlabelled; clicking a label does not focus its field.
16. **No `<fieldset>/<legend>` on the brain radio group**, and no `aria-live` on the success/error banners — a screen reader user gets no announcement that a save succeeded or failed.
17. **Zero client-side validation.** No `required`, no `pattern`, no `inputmode="tel"` on phone fields, no `autocomplete` on the token field. Every mistake costs a full round trip.
18. **The sign-in page leaks implementation at the user.** Its only label is *"Admin token (ADMIN_TOKEN in the phone env file)"* — it instructs a business owner to open a Linux env file. No product framing, no logo, no recovery path.
19. **No favicon** (404 in the browser console) — the browser tab shows a blank page icon.

### B.4 Mobile behaviour (≈390px; captured 375px)

- **No `@media` queries at all** (grep: 0 matches). The layout is fluid-only. It doesn't break — but nothing adapts either.
- Chips wrap to two rows and remain legible. Cards and inputs go full-width correctly. The `viewport` meta tag is present (`admin.py:58`).
- `pre { white-space: pre-wrap }` prevents horizontal scroll, but the cost is that 40-character CallSids and backticked shell commands wrap across three lines each. The message pad becomes ~3,000px of ragged monospace (see `mobile-crop-pad.png`). It is not readable as an inbox on a phone.
- Textareas keep their desktop `min-height` (64px / 110px). The `extra_instructions` field holds a long appointment policy in a 110px-tall box on a 390px screen — roughly 5 visible lines for ~15 lines of content.
- Total scroll: **8.8 screens**, with the Save button at screen 5 and read-only logs on screens 5–8.

### B.5 Measured contrast (WCAG 2.x)

| Element | fg / bg | Ratio | Verdict |
|---|---|---|---|
| body text | `#e6e9ec` / `#101418` | 15.18:1 | pass |
| section `h2` | `#aeb8c2` / `#101418` | 9.19:1 | pass |
| field label | `#8b97a3` / `#171d24` | 5.70:1 | pass |
| **`.hint` (12.5px)** | `#68747f` / `#171d24` | **3.55:1** | **FAIL** (needs 4.5:1) |
| chips ok / bad | `#7fd6a4` / `#f29c9c` on `#1d2630` | 8.79 / 7.30:1 | pass |
| error / saved banners | — | 10.11 / 10.37:1 | pass |
| button | `#ffffff` / `#2563eb` | 5.17:1 | pass |
| **input border** | `#2a3642` / `#171d24` | **1.38:1** | **FAIL** SC 1.4.11 (needs 3:1) |
| **card border** | `#232c36` / `#101418` | **1.31:1** | **FAIL** SC 1.4.11 |

Text contrast is mostly good. What fails is exactly the hint text that carries the warnings, and every control boundary.

### B.6 Would a paying customer trust this?

No. Three things settle it before design taste enters: the message inbox opens mid-word on the string `0142`; the call log says there are no calls while twenty-one messages sit above it; and fake test callers named "Sarah from Rose Bakery" appear as real messages. A first-time owner logging in sees a page that tells them to run `journalctl` to read their own customer's message.

---

## C. Gaps vs a professional AI-receptionist dashboard (ranked)

Ranked by what costs the owner money or trust first.

**1. No call log. (P0)**
The only call-history panel is a `journalctl` grep that returns nothing on this machine and depends on journald retention that has already discarded everything. There is no durable record of a single call: no date, no duration, no answered/missed, no outcome, no caller, no recording. Industry baseline is a call table with date/time, caller, duration, outcome, and a per-call detail view. Right now the product cannot answer "how many calls did we get last week?"

**2. No transcripts in the UI. (P0)**
Every message ends with `full transcript in \`journalctl --user -u atlas-phone-bridge\``. The transcript is written to journald only, is not retained, and is unreachable by the person who owns the business. This is the single most-used feature of every competing product and it is absent, while the UI advertises it as a shell command.

**3. Messages are an append-only text file, not an inbox. (P0)**
No status (new / read / responded / closed), no assignment, no search, no filter by number or date, no per-message actions (call back, email, mark done, export). Newest is at the bottom. The panel truncates at 6,000 characters mid-entry. An owner cannot work a lead list from this.

**4. Test data and real customer messages are indistinguishable. (P0)**
Three synthetic entries and ~10 `+1555…` test calls render identically to genuine ones. Any dashboard showing real business messages must never mix in fixtures.

**5. Zero analytics. (P1)**
No calls/day, no answered vs missed, no avg duration, no outcome breakdown (message taken / transferred / hung up / no info given), no repeat callers, no cost per call, no spend against the Z.AI balance. The pad shows at least six "caller wanted to book but did not provide enough information" entries — that is a measurable failure rate the dashboard never surfaces.

**6. No business hours / after-hours behaviour. (P1)**
No hours, no holidays, no closed-hours greeting, no "take a message only after 6pm", no timezone setting. Every competing product treats hours as a first-class screen.

**7. No error or health surface beyond five chips. (P1)**
Summarizer failure, ntfy push failure, and Twilio webhook rejections are logged at ERROR to journald and never shown. A message can silently degrade to `MESSAGE EXTRACTION FAILED` and the owner learns of it only by reading the pad. The chips show *backend reachable*, not *the line is answering calls correctly*.

**8. No notification settings. (P1)**
ntfy is env-only, surfaced as the word `on`. No email/SMS forwarding of messages, no per-profile recipients, no quiet hours, no test-notification button. For a receptionist product, "where does the message go" is a settings screen, not an environment variable.

**9. Transfer rules are one phone number. (P2)**
`forward_to` is a single E.164 string. No hours-based routing, no multiple destinations, no ring order, no fallback-to-voicemail, no per-caller rules. The transfer *phrases* are exposed as raw newline-separated text with a warning that filling them in silently replaces the defaults.

**10. No number management. (P2)**
Numbers are a free-text `key = value` textarea. No Twilio number list, no provisioning, no forwarding status, no verification that Twilio's webhook actually points at this bridge. Nothing tells the owner whether the number in the box is the number Twilio is calling.

**11. No greeting preview or voice control. (P2)**
The greeting is a text field. No TTS preview, no voice picker, no way to hear what a caller hears before it goes live on a real line.

**12. Configuration is presented as internals. (P2)**
"profile: business_builders", `+15088863046 = business_builders`, "Model override (must be a non-thinking model)", "Name mishearings", raw system prompts in a `<details>`. The owner is being asked to edit a config file through a browser rather than to configure a receptionist.

**13. No config history, diff, or undo. (P2)** — see section D.

**14. No multi-user, no roles, no per-user audit. (P3)**
One shared token equals full control. Fine for a single owner today; a blocker for delivering this to a client with staff.

---

## D. Security and UX risk in the current save flow

**D.1 Any validation error silently discards everything the owner typed. (Highest-impact defect in the file.)**
On failure, `save()` calls `await index(request)` (`admin.py:285`) and string-replaces an error banner into the returned HTML at `:286-290`. `index()` re-reads state from `get_state()` — the **live, last-applied** config — not from the submitted form. So the re-rendered page shows the old values. An owner who rewrites a greeting, pastes new facts, and fits a number line wrong loses the greeting and the facts, and cannot even see the number line they typed wrong, because it has been replaced by the previously-saved one. The error message names the bad line; the page no longer contains it. On a long form filled on a phone this is a data-loss bug, not a polish issue.

**D.2 The session cookie *is* the ADMIN_TOKEN.**
`resp.set_cookie(COOKIE, token, ...)` (`admin.py:89`) stores the shared secret from the env file directly in the browser for 30 days. There is no session identifier, so the cookie cannot be revoked, rotated, or scoped. Anything that can read the cookie jar (a browser-profile copy, a shared machine, a devtools screenshot) obtains the env-file secret itself, not a session. `secure=True` is also not set — the flag is harmless behind tailscale's TLS today, but it is one proxy change from being sent in the clear.

**D.3 No logout, no revocation, no expiry short of a service restart.**
There is no `/logout` route (`admin.py:302-306`). Ending a session requires editing `~/.config/atlas-phone/env` and restarting `atlas-phone-bridge.service` — which also drops any call in progress.

**D.4 Unlimited, unlogged token guessing.**
`login()` has no rate limit, no backoff, and no log line on failure; `access_log=None` on the runner (`bridge.py:1458`). `compare_digest` defeats timing attacks but nothing defeats volume, and nothing records that an attempt happened. There is no way to answer "has anyone tried to get in?"

**D.5 No CSRF defence beyond an implicit cookie flag.**
`POST /save` has no CSRF token, no Origin check, no Referer check (`admin.py:228-231`). `SameSite=Strict` currently blocks the cross-site form post, so this is not exploitable today — but the entire defence is one cookie attribute that a future change (a proxy that rewrites cookies, a switch to `Lax` for a redirect flow, an embedded iframe) would remove without any code in `save()` noticing. There is also no `X-Frame-Options`/CSP `frame-ancestors`, so the page is framable.

**D.6 Hot-apply to a live phone line with no confirmation and no staging.**
`apply_config_text` (`bridge.py:833-…`) writes `businesses.toml` atomically and swaps `NUMBERS/PROFILES/SYSTEM_PROMPTS/GATES/BRAINS/ACTIVE_BRAIN` in place. Validation is genuinely fail-closed and correct — a bad config changes nothing. But a *valid and wrong* config takes effect on the next incoming call with **no confirmation dialog, no preview, no diff, no "apply at" scheduling, and no staging line to test against.** Changing the greeting, switching the brain to an unreachable endpoint, or clearing `forward_to` all happen the instant the button is clicked.

**D.7 Deleting a business is a checkbox with no confirmation and no backup.**
`{key}::__delete` (`admin.py:123`) is a 13px checkbox. Ticking it and pressing the page's only button drops the profile from `profiles` (`admin.py:252-253`), and `emit_business_toml` writes a file that no longer contains it. `os.replace` overwrites `businesses.toml` in place — **there is no `.bak`, no versioned copy, and the directory contains none.** A mis-click plus a save permanently destroys a business's greeting, facts, instructions, and phrase lists. There is no undo.

**D.8 No audit trail.**
`apply_config_text` logs one line — profile count, number count, active brain — to journald, which on this machine has already been vacuumed to empty. There is no record of *what changed*, no before/after, no timestamp history, no actor. After an incident ("the agent started telling callers the wrong hours") there is no way to establish when or by whom the change was made.

**D.9 Blank field silently deletes the setting.**
`admin.py:257-261`: an empty submitted value calls `updated.pop(field_name, None)`. For required fields validation catches it. For optional ones it is silent and consequential — clearing `forward_to` disables human transfer entirely; clearing `transfer_phrases` or `end_phrases` reverts to the built-in set. The UI gives no confirmation that clearing a box turns a capability off.

**D.10 Last-write-wins with no concurrency check.**
The form carries the full config with no version, etag, or timestamp. A tab left open yesterday, submitted today, overwrites everything changed in between — including a brain switch made from another device — with no conflict detection. The stale radio is partially guarded (`admin.py:236` falls back to the current brain when blank) but a *stale non-blank* radio silently reverts the live brain.

**D.11 Blocking subprocess on every page render.**
`_journal()` runs `journalctl` with a 5-second timeout on each `GET /` (`admin.py:186-200`). It is off-thread so the event loop survives, but page load can stall up to 5s with no loading state, and `save()`'s error path runs it a **second** time via `index()`.

**D.12 Customer PII rendered with no cache control.**
The page contains caller phone numbers, names, email addresses, and message contents with no `Cache-Control: no-store`. It is cacheable by any intermediary and by the browser's back/forward cache after logout — which, since there is no logout, is moot but worth fixing when logout is added.

**D.13 The live file is unversioned.**
`/home/magiccat/atlas-phone-bridge/` is not a git repo. The tracked copy at `plugins/phone_agent/admin.py` is 39 lines behind and lacks brain support entirely; deploying it would strip every `[brains.*]` from the config on first save. There is no rollback path for the code either.

---

## E. Redesign requirements

Written for an implementer. Every screen below replaces part of the single scrolling page. Assume the same aiohttp process, the same tailnet-only exposure, the same fail-closed validation — the changes are to data model, information architecture, and interaction.

### E.0 Prerequisites (do these first — the UI cannot be built on the current data)

- **P0-a — Persist calls to a real store.** Add SQLite at `~/.local/share/atlas-phone/calls.db`. One row per call written at call end: `call_sid` (PK), `started_at`, `ended_at`, `duration_s`, `direction`, `to_number`, `from_number`, `profile_key`, `outcome` enum (`message_taken` | `transferred` | `caller_hung_up` | `no_info_given` | `agent_error`), `brain`, `model`, `caller_turns`, `summary`, `transcript_json`, `overpromise_flags`, `notify_status`. Journald must stop being the transcript store.
- **P0-b — Migrate the pad.** Import the 21 existing entries from `~/atlas-phone-messages.md` into the DB. Keep appending the Markdown pad if it is used elsewhere, but the dashboard must read the DB, never the file, and never a byte slice of it.
- **P0-c — Purge or flag fixtures.** Every row whose `call_sid` matches `^CAtest` or whose `from_number` is in the `+1555…` reserved range gets `is_test = 1`. Test rows are hidden by default and shown only behind an explicit "Show test calls" toggle, visually marked when shown. No fixture ever renders like a real message.
- **P0-d — Config history.** Before every `os.replace` on `businesses.toml`, write the outgoing file to `~/.config/atlas-phone/history/businesses-<ISO8601>.toml` and append a row to a `config_changes` table: timestamp, actor (session id), unified diff, applied/rejected, rejection reason. Keep 100 versions.
- **P0-e — Version the code.** `git init` the bridge directory or move it under the plugin repo, and reconcile the 39-line drift so the tracked copy includes brain support before anyone deploys it.

### E.1 Screen: Sign in

- Product name and a real mark. No environment-variable jargon.
- Label: "Access code". Helper text: "The code from your setup email." `type=password`, `autocomplete="current-password"`, `id`/`for` paired.
- **Issue a random session id on success; never store the shared secret in the cookie.** Server keeps `{session_id: (created_at, last_seen)}`. Cookie: `HttpOnly`, `Secure`, `SameSite=Strict`, 14-day max-age with sliding renewal.
- Rate limit: 5 attempts per IP per 15 minutes, then a 60-second lockout. Every failure logged with timestamp and source IP.
- States: idle · submitting (button disabled, "Checking…") · wrong code (inline, `aria-live="assertive"`, no field clearing) · locked out (with the time remaining).

### E.2 Screen: Overview (default landing)

Answers "is my phone being answered properly?" in five seconds, above the fold, on a phone.

- **Line status band, full-width, colour-coded.** Green "Your line is answering" / amber "Degraded — <reason>" / red "Not answering — <reason>". Composed from: bridge up, model backend reachable, Twilio webhook verified in the last 24h, ≥1 number mapped to a valid profile, notifications delivering. Never show a green chip when a sub-check is failing.
- **A production-safety warning is a banner, not a chip.** If the active brain's label or config marks it test/non-production (today: `glm_52_test`, "against Z.AI terms for production use"), render a persistent amber banner: "Your line is running on a test model that isn't licensed for business use. Switch to <production brain>." with a one-click switch. This condition currently exists in production and the UI does not mention it.
- **Today strip:** calls today · messages waiting · missed/no-info · avg duration. Each a link into a filtered Calls view.
- **7-day sparkline** of calls per day with answered vs no-info split.
- **Latest 5 messages**, as cards, newest first, with caller, time, one-line summary, and status pill.
- **Alerts list:** any summarizer failure, notification failure, or Twilio signature rejection in the last 7 days, with the call it belongs to.
- States: healthy · degraded (per-check reasons listed) · **first-run empty** ("No calls yet. Ring <number> to test your line." with the actual number) · loading (skeleton, never a blank panel) · stale (if the DB write is behind, say so).

### E.3 Screen: Calls

- Table (desktop) / cards (mobile): date-time, caller (with a name if the summary captured one), duration, outcome pill, profile, brain, message-status pill.
- Filters: date range, outcome, profile, number, has-message, unread-only, show-test-calls (off by default).
- Free-text search across summary and transcript.
- Sort by date descending **by default**.
- Row → **Call detail**: full turn-by-turn transcript rendered as a conversation (caller left, agent right), the structured summary, caller ID with click-to-call and click-to-copy, duration, outcome, which brain/model answered, the overpromise flag if set, notification delivery status, and the exact system prompt that was live for that call. Actions: mark handled, add an internal note, copy summary, export. Nothing here may tell the owner to run a shell command.
- States: results · no results for filter (with a clear-filters action) · never-any-calls empty · loading skeleton · load error (explicit, retryable).
- Retention statement visible: "Calls kept for N days."

### E.4 Screen: Messages

- The Calls list filtered to calls that produced a message, with workflow on top: status `New` / `In progress` / `Done`, set from the list without opening the row.
- Card shows: caller, time, business line, the summary body, callback number and email as tappable/copyable chips, and status.
- Actions: call back (`tel:`), copy email, mark done, snooze to a date, add note, export CSV.
- Unread count drives the nav badge.
- Sort newest first. Never truncate a message; if long, clamp with an explicit "Show more".
- States: unhandled queue · all-clear ("Nothing waiting") · loading · error.

### E.5 Screen: Receptionist settings (per business)

Sectioned, each section saving **independently** — no page-wide save.

1. **Identity** — Business name; what you do (one line, with a character counter and an example); who takes messages.
2. **Greeting** — text field with a live character/estimated-seconds count and a **Preview** button that plays the greeting through the same TTS the line uses. Show the exact sentence a caller will hear.
3. **What the agent may say** — the `facts` list, rebuilt as **repeatable rows** (add/remove/reorder) rather than a newline blob, with typed suggestions (hours, email, service area, pricing posture) and a prominent empty state: "Your agent currently can't answer any questions about your business. Add hours, email, and service area." This is the field that is empty on the live line today.
4. **Extra instructions** — auto-growing textarea, minimum 8 visible lines, with a note that it cannot override safety rules and a link to view the compiled prompt.
5. **Transfer** — toggle "Transfer callers to a person" → phone field with `inputmode="tel"`, live E.164 formatting, and inline validation before submit. Transfer phrases as repeatable rows with the standard set shown as pre-filled, removable defaults, so "empty means standard" is never a hidden rule.
6. **Ending a call** — end phrases, same repeatable-row treatment.
7. **Name recognition** — assistant name plus mishearing aliases as chips.
8. **Advanced** (collapsed) — model override, profile key, raw compiled prompt (read-only, copyable).

Requirements that apply to every field on this screen:
- `id`/`for` on every control. `aria-describedby` for hints. `<fieldset>/<legend>` for every group.
- Hint text at **≥4.5:1** contrast (replace `#68747f` with ≥`#8b97a3` on card backgrounds) and control borders at **≥3:1**.
- **Preserve user input on validation failure.** Re-render from the submitted values with per-field inline errors, never from `get_state()`. This is defect D.1 and is non-negotiable.
- Dirty tracking: a sticky "You have unsaved changes — Save / Discard" bar; `beforeunload` guard; disabled Save until dirty.
- Clearing an optional field that turns a capability off (`forward_to`, phrase lists) requires an explicit confirm naming the consequence: "Callers will no longer be able to reach a person. Continue?"
- Success is inline per section with `aria-live="polite"`, and states what changed: "Greeting updated — live on the next call."

### E.6 Screen: Hours & availability (new)

- Weekly schedule grid, per business, with a timezone selector.
- Holiday/closure dates with an optional custom closed-hours greeting.
- After-hours behaviour: take a message (default) / transfer anyway / different greeting.
- Empty state must be honest: "Always open — the agent answers 24/7 the same way."

### E.7 Screen: Numbers (new)

- List of numbers with formatted display (`(508) 886-3046`), the business each is assigned to (a `<select>`, not free text), and Twilio webhook status ("Verified 4 minutes ago" / "Never seen a signed request — check your Twilio console", with the exact URL to paste).
- Add a number via a validated E.164 field plus a business picker. Free-text `key = value` is removed entirely.
- Read-only Twilio account context: account SID (masked), line status.

### E.8 Screen: Notifications (new)

- Where messages go: push (ntfy), email, SMS — each with an on/off toggle, destination, and a **Send test** button that reports the real delivery result.
- Per-business recipients. Quiet hours. Notify-on: every call / messages only / urgent only.
- Delivery log: last 20 attempts with success or the actual error. Notification failure must be visible here and on Overview, never swallowed into journald.

### E.9 Screen: Model / brain

- Cards, not radios. Each shows: friendly name, what it costs, where it runs (private/on-device vs cloud), current reachability (live check with a timestamp), and a **production-use badge** — "Approved for business use" or "Test only — not licensed for production".
- Switching requires an explicit confirm dialog naming the new model and the fact that it applies to the next incoming call.
- Refuse to switch to an unreachable brain without an override checkbox.
- Show 7-day cost and call count per brain once cost data exists.

### E.10 Screen: Activity & history (new)

- Every config change: timestamp, what changed (human sentence — "Greeting changed", "Transfer number removed"), the diff on expand, and **Restore this version** with a confirm and a re-validation before applying.
- Sign-in events, including failed attempts.
- Service events (restarts, brain switches, validation rejections with the reason shown).

### E.11 Cross-cutting requirements

- **Navigation:** persistent left rail on desktop, bottom tab bar on mobile — Overview · Calls · Messages · Settings. Nothing over ~2 screens tall without in-page navigation or collapsible sections.
- **Destructive actions:** deleting a business requires typing the business name to confirm, is soft-delete with 30-day recovery from Activity, and is never a checkbox inside a form that saves other things.
- **Save model:** section-scoped saves with optimistic-concurrency tokens. A stale form is rejected with "This page is out of date — someone changed settings from another device" and a reload-and-merge path, never a silent overwrite.
- **CSRF:** per-session token in every mutating form, plus an `Origin` check. Do not rely on `SameSite` alone.
- **Headers:** `Cache-Control: no-store` on every authenticated page, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, CSP with `frame-ancestors 'none'`.
- **Logout** route that invalidates the session server-side, plus "Sign out all devices".
- **Accessibility target: WCAG 2.2 AA.** Every control labelled and reachable by keyboard in visual order; a visible `:focus-visible` ring at ≥3:1 against both the field and the page; 24×24 minimum target size; `aria-live` on every banner; heading levels that nest (`h1` page → `h2` section → `h3` card).
- **States for every panel:** loading (skeleton) · empty-first-run (tells the owner what to do) · empty-after-filter (offers to clear) · error (states what failed and how to retry) · success (states what changed and when it takes effect). No panel may render blank or mid-word.
- **Language:** owner vocabulary throughout — "business", "greeting", "call log", "who answers"; never "profile key", "TOML", "env file", "journalctl", "non-thinking model", "hot-apply".
- **Typography:** three sizes and two weights maximum — 13px meta / 15px body / 20px page title, 400 and 600. Section headers stop being uppercase `h2`s that double as card titles.
- **Spacing:** a 4px base scale (4/8/12/16/24/32/48). Consistent card padding, one rhythm between fields, generous space between sections.
- **Colour with purpose:** the accent is reserved for the primary action per screen; green/amber/red mean healthy/degraded/failed and appear nowhere decorative; test-vs-production is a colour signal, not grey body text.
- **Performance:** no blocking subprocess in a request handler. Health checks and any journal reads move to a background task with a cached result and a "last checked" timestamp.

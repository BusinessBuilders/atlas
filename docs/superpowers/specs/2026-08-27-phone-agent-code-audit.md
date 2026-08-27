# Atlas Phone Agent — code audit (read-only)

**Date:** 2026-08-27 · **Scope:** deployed bridge + git plugin form + design docs + live config shape + units
**Method:** full read of every file listed; `diff` deployed↔plugin; plugin test suite run twice (once against the plugin copy, once against a scratch copy of the *deployed* code); read-only HTTP GETs against `/health` locally and publicly. **Nothing was modified, restarted, or POSTed.**

Unless prefixed, `bridge.py:N` = `/home/magiccat/atlas-phone-bridge/bridge.py` and `admin.py:N` = `/home/magiccat/atlas-phone-bridge/admin.py` (the DEPLOYED copies). Plugin paths are written out in full.

### Test baseline (what I ran)

There is no `.venv` in `/home/magiccat/atlas-phone-plugin-wt`. I used the Atlas venv, as the plan document prescribes (`docs/superpowers/plans/2026-07-26-call-control-hardening.md:9`):

```
cd /home/magiccat/atlas-phone-plugin-wt && \
PYTHONPATH=/home/magiccat/atlas-phone-plugin-wt:/home/magiccat/atlas-phone-plugin-wt/src \
/home/magiccat/atlas/.venv/bin/python -m pytest -q tests/test_phone_agent_plugin.py
→ 43 passed in 0.72s
```

Then the identical suite against a scratch copy of the **deployed** files (`bridge.py`→`service.py`, deployed `admin.py`):

```
→ 1 failed, 42 passed
FAILED tests/test_phone_agent_plugin.py::test_admin_app_auth_and_save
E  TypeError: build_admin_app() missing 1 required keyword-only argument: 'get_brains'
```

**The code that is actually answering the business phone today fails its own test suite.** The "brains" feature shipped to production without the tests being updated.

---

## A. Architecture map (plain English)

### The call, end to end

1. **Someone dials +1 508-886-3046.** Twilio owns the number.
2. **Twilio POSTs `https://ai.business-builder.online/phone/voice/incoming`.** That hostname is a **VPS (66.42.116.215) running nginx**. nginx proxies to `127.0.0.1:8890` on the VPS, which is not a server — it is the far end of a **reverse-SSH tunnel** (`atlas-phone-tunnel.service:13`, `ssh -N -R 127.0.0.1:8890:127.0.0.1:8890 linuxuser@66.42.116.215`) back to the MagicCat desktop, where the bridge listens on `127.0.0.1:8890` (`bridge.py:1441`). Before each connect, `tunnel-guard.sh` SSHes to the VPS and evicts a stale forward squatting the port (`tunnel-guard.sh:29-49`).
3. **Signature check.** `voice_incoming` verifies Twilio's HMAC-SHA1 header against `PUBLIC_BASE + path` and a no-port variant (`bridge.py:1053-1077, 1094`). Failure → HTTP 403 + WARNING.
4. **The dialed number picks a business profile** from `[numbers]` in `businesses.toml` (`bridge.py:1099-1100`). Unmapped number → a spoken "this line isn't set up correctly" + an ERROR journal line (`bridge.py:1102-1107`, `_config_error_twiml` at 1081-1087).
5. **The bridge answers with TwiML** telling Twilio to open a ConversationRelay websocket to `wss://…/phone/voice/relay?token=<WS_TOKEN>&profile=<key>`, with `welcomeGreeting` = the profile's greeting, and an `action=` callback URL (`bridge.py:1112-1127`).
6. **Twilio opens the websocket** to `voice_relay` (`bridge.py:1230`). Gate: the static `WS_TOKEN` in the query string (1231), the profile must still exist (1235), and the `setup` event's `accountSid` must match ours (1272-1275). The caller's real caller-ID is appended to the system prompt (1279-1282).
7. **Twilio does speech-to-text** and sends each caller utterance as a `prompt` event (1286).
8. **Deterministic pre-processing:** a known mishearing of the assistant's own name is rewritten in the inbound text before the model ever sees it ("Hey, Alice" → "Hey, Atlas"), unless the caller is introducing themself by that name (`resolve_alias_mishearing`, 461-472, called at 1293).
9. **The LLM streams a reply.** `stream_reply` (1183) POSTs OpenAI-compatible `/chat/completions` with `stream: true` to the **active brain**. Each token passes through `MarkerScrubber` (866-931) and is forwarded to Twilio as `{"type":"text","token":…}`. Twilio does the text-to-speech.
10. **Control markers.** The model may end a reply with `[END CALL]` or `[TRANSFER CALL]`. The scrubber guarantees these are never spoken and records which were seen.
11. **`decide_call_action` is the single chokepoint** (553-570). A marker acts **only** if the CALLER explicitly authorized it: a transfer phrase in the caller's last utterance (or an adjacent "yes" refreshing the previous one — 530-543), an end phrase / standalone "no" (546-550), and never when the reply contains any question mark (561-562). Blocked transfers get a **server-authored spoken correction** so the caller isn't left hanging (1331-1343).
12. **Acting:** wait `speech_seconds(reply)` so the goodbye plays (1349), re-check no newer caller turn arrived (1350-1353), then send Twilio `{"type":"end","handoffData":{"reason":…}}` (1357-1360).
13. **Twilio calls back `/voice/action`** (`bridge.py:1143`), also signature-checked (1149). `reason == "transfer"` + a configured `forward_to` → TwiML `<Dial><Number>` (1130-1140). Anything else → `<Hangup/>`.
14. **Post-call extraction.** When the websocket closes and the call had caller turns (1383), `deliver_call_message` (999) runs one non-streamed summarizer pass (`summarize_call`, 966) on the same brain, prefixes a `⚠ REVIEW` banner if the overpromise detector fired during the call (1014-1019), and appends the note to the **message pad**.
15. **Notification.** If `NTFY_URL`+`NTFY_TOPIC` are set, the note is pushed (1032-1043).

### External dependencies

| Dependency | Role | Failure visible? |
|---|---|---|
| **Twilio** (number, ConversationRelay, STT, TTS, `<Dial>`) | The entire telephony layer | Only via Twilio console / caller complaint |
| **Z.AI** (`glm_52_test` / `glm_52_api` brains) — **currently live** | The LLM answering callers | `/health` `model_backend` + spoken apology |
| **Ollama** `127.0.0.1:11434` (`local_qwen` brain) | Alternate LLM | same |
| **ntfy** `127.0.0.1:8092`, topic `eve-approvals-9d921207` | Owner push of new messages | journal only (see F-6) |
| **nginx on VPS 66.42.116.215** | Public TLS front door | tripwire probe only |
| **reverse-SSH tunnel** (`atlas-phone-tunnel.service`) | Carries VPS:8890 → desktop:8890 | tripwire probe only |
| **journald** | The only transcript store | none |
| **fleet-tripwire** (`agent-fleet/scripts/tripwires.json:178-189`) | Probes the public `/health` every 30 min, severity critical | this is the only alerting |

### Everything it writes

| Path / target | Written by | Contents |
|---|---|---|
| `~/atlas-phone-messages.md` (`MESSAGES_FILE`) | `bridge.py:1024-1029` | Caller name, phone number, email, request, CallSid — **one global file for all businesses** |
| `~/.config/atlas-phone/businesses.toml` | `bridge.py:853-856` (atomic `os.replace`, **no backup**) | Whole config, rewritten on every dashboard save |
| `~/.config/atlas-phone/businesses.toml.tmp` | `bridge.py:853-855` | transient |
| journald (`atlas-phone-bridge`) | `bridge.py:1110, 1283, 1290, 1295, 1307` | **Full call transcripts + caller phone numbers**, INFO level |
| ntfy topic | `bridge.py:1034-1037` | The extracted message note |
| In-memory globals `NUMBERS/PROFILES/SYSTEM_PROMPTS/GATES/BRAINS/ACTIVE_BRAIN` | `bridge.py:838, 857-858` | hot-applied config |

Ports: bridge `127.0.0.1:8890` (1441), admin dashboard `127.0.0.1:8891` (1460, exposed tailnet-only via tailscale serve :8447).

---

## B. Divergence report — deployed vs plugin

`diff /home/magiccat/atlas-phone-bridge/bridge.py /home/magiccat/atlas-phone-plugin-wt/plugins/phone_agent/service.py` and the same for `admin.py`.

**Direction: the deployed copy is strictly AHEAD.** Every hunk is a deletion going deployed→plugin. **The plugin has zero features the deployed copy lacks.** The plugin is a snapshot from 2026-07-26 09:54; the deployed copy is 2026-07-31 08:02.

### Deployed-only (the whole "brains" feature, ~140 lines)

| Feature | Deployed | Plugin |
|---|---|---|
| Brains docs in module docstring | `bridge.py:93-113` | absent |
| End phrase `"that's it"` | `bridge.py:309` | **absent** — a caller saying "that's it" cannot end the call on the plugin |
| `load_business_config` → 4-tuple `(numbers, profiles, brains, active)` | `bridge.py:618-637` | 2-tuple, `service.py:596-614` |
| `parse_brains_config` (fail-closed validation of `[brains.*]`, `active_brain`, `api_key_env` must name a *set* env var, `extra_body` must be a JSON object) | `bridge.py:650-710` | **absent** |
| `brain_key` / `brain_request_args` (bearer header + `extra_body` merged *under* call keys) | `bridge.py:713-728` | **absent** |
| `emit_business_toml(numbers, profiles, brains, active_brain)` — round-trips `[brains.*]` | `bridge.py:747-773` | `emit_business_toml(numbers, profiles)`, `service.py:631+` — **drops brains** |
| Boot log of the active brain | `bridge.py:826-830` | absent |
| `apply_config_text` re-validates + swaps brains | `bridge.py:838, 845, 858-861` | `service.py:696, 715-716` |
| `summarize_call(..., brain)` uses the brain URL + auth | `bridge.py:966-987` | hardcoded `f"{OLLAMA_URL}/chat/completions"`, no headers, `service.py:822-841` |
| `deliver_call_message(..., brain)` | `bridge.py:999-1009` | `service.py:855-862` |
| `stream_reply(..., brain)` uses the brain URL + auth | `bridge.py:1183-1211` | `f"{OLLAMA_URL}/chat/completions"`, no headers, `service.py:1041-1062` |
| Brain captured once per call | `bridge.py:1244-1247` | `model = profile.model or DEFAULT_MODEL`, `service.py:1096` |
| `health_snapshot` probes the ACTIVE brain with auth; reports `"brain"` | `bridge.py:1398-1417` | probes `OLLAMA_URL` only, no `"brain"` key, `service.py:1248-1259` |
| admin `get_brains` kwarg | `admin.py:77` | absent, `plugins/phone_agent/admin.py:77` |
| admin `_brain_card` radio selector | `admin.py:127-148` | **absent** |
| admin brain chip in the status row | `admin.py:160` | `service.py`-shaped chip without brain |
| admin `save()` reads the `active_brain` radio, passes brains through | `admin.py:233-236, 279-281` | `admin.py:250` |

### What breaks if one replaces the other — verified

1. **Plugin `service.py` + deployed `admin.py`** → the bridge **crashes at startup** whenever `ADMIN_TOKEN` is set: `TypeError: build_admin_app() missing 1 required keyword-only argument: 'get_brains'`. I reproduced this exact error by running the plugin test suite against the deployed `admin.py`.
2. **Deployed `bridge.py` + plugin `admin.py`** → mirror image: `TypeError: build_admin_app() got an unexpected keyword argument 'get_brains'` — same boot crash.
3. **Deploying the plugin `service.py` as-is onto the live config — the dangerous one.** `parse_business_config` in the plugin reads only `data["numbers"]` and `data["profiles"]` (`service.py:577-615`); the live file's top-level `active_brain` and `[brains.*]` are **silently ignored**. The service would start clean and answer calls — but on `qwen2.5:7b-instruct` at local Ollama (from `OLLAMA_URL`/`MODEL`) instead of GLM-5.2. **A silent production model downgrade with no error anywhere.** Then the first dashboard save calls the plugin's two-arg `emit_business_toml`, which does not emit `[brains.*]` → **the brain definitions and the Z.AI key binding are permanently deleted from `businesses.toml`.**
4. **Systemd units also diverge.** Live `atlas-phone-bridge.service:7-8` runs `/home/magiccat/atlas-phone-bridge/.venv/bin/python bridge.py` with `Restart=on-failure`; the repo unit (`deploy/systemd/atlas-phone-bridge.service:13-14`) runs `%h/atlas/plugins/phone_agent/service.py` with `Restart=always`. The repo unit points at a path that does not contain the live code.
5. **The tunnel is not in the repo at all.** `deploy/systemd/` has no `atlas-phone-tunnel.service`, and `tunnel-guard.sh` exists nowhere in the worktree. The component whose failure killed the line for ~3h a night is entirely un-versioned.
6. **`/home/magiccat/atlas-phone-bridge` is not a git repo** (`git rev-parse` → "not a git repository"). Production has no version history and no rollback.

---

## C. Findings

Ranked. Each has file:line, what breaks, and the fix.

### CRITICAL

---

**C-1. Production code is unversioned and diverged from the only copy that has tests.**
`/home/magiccat/atlas-phone-bridge/` (not a git repo) vs `atlas-phone-plugin-wt/plugins/phone_agent/`; divergence table in §B; the sync step is a manual instruction in `docs/superpowers/plans/2026-07-26-call-control-hardening.md:18` — and it has already been missed once (the entire brains feature, 2026-07-31).

*Breaks:* no rollback on a bad edit to the live phone line; the tested artifact and the running artifact are different programs; a well-intentioned "deploy the plugin" silently downgrades the model and then destroys the brain config (§B item 3). A `.bak` file already sits in the deploy dir (`tunnel-guard.sh.bak-222416`) — backups by copy-paste.

*Fix:* make the git worktree the single source. Port the brains feature into `plugins/phone_agent/service.py` + `admin.py`, add `deploy/systemd/atlas-phone-tunnel.service` and `tunnel-guard.sh` to the repo, and change the live unit's `ExecStart` to a path inside a checkout. Delete `/home/magiccat/atlas-phone-bridge` as an editing target. Nothing else in this report should be built before this.

---

**C-2. Production code fails its own test suite; the entire brains feature has zero tests.**
`bridge.py:650-710` (`parse_brains_config`), `713-728` (`brain_key`, `brain_request_args`), `747-773` (brains emit), `admin.py:127-148, 233-236` — none of these are exercised by `tests/test_phone_agent_plugin.py`. Verified: deployed code → `1 failed, 42 passed`.

*Breaks:* the code path that chooses **which company's API gets the caller's speech** and **which bearer key is attached** is untested. `brain_request_args` merging `extra_body` under the call body (727) is what keeps GLM from entering thinking mode and stalling a live caller — untested. A regression here is invisible until a customer is on the phone.

*Fix:* extend `_import_service` with a `[brains.*]` fixture; test: missing `active_brain`, `active_brain` naming a nonexistent brain, `api_key_env` naming an unset var (must raise), `extra_body` not-an-object (must raise), `brain_request_args` never letting `extra_body` override `model`/`messages`/`stream`, and the emitter round-tripping brains. Add `get_brains` to the admin test call.

---

**C-3. Single-tenant by construction — message pad, notifications, and dashboard are all global.**
`bridge.py:155-157` (one `MESSAGES_FILE`), `158-159` (one `NTFY_URL`/`NTFY_TOPIC`), `1024-1029` (every profile appends to that one file), `admin.py:180-181` (dashboard renders the last 6000 chars of it), `admin.py:185-198` (dashboard tails the journal for **all** profiles), `admin.py:82` + `bridge.py:166` (one `ADMIN_TOKEN` for everybody).

*Breaks:* the moment there is a second paying business, business A's owner logging into the dashboard reads business B's callers' names, phone numbers, emails, and requests — and B's call transcripts. Both businesses' messages push to the same ntfy topic (live value: `eve-approvals-9d921207`, which is also EVE's approvals topic).

*Fix:* move `messages_file` and the ntfy target into the profile (`messages_file`, `ntfy_url`, `ntfy_topic`, falling back to the env defaults), and scope every dashboard read to the profiles the logged-in token owns. That needs per-business tokens: replace the single `ADMIN_TOKEN` with a `[owners.*]` table mapping a token to a list of profile keys.

---

**C-4. A malformed websocket frame destroys the caller's message.**
`bridge.py:1267` — `event = json.loads(msg.data)` is unguarded inside `async for msg in ws`.

*Breaks:* any non-JSON frame (or any exception raised anywhere in the message loop body — a `speak()` on a half-closed socket, a regex error in `resolve_alias_mishearing`) propagates out of the `async for`, out of the `async with aiohttp.ClientSession()`, and out of `voice_relay`. Execution never reaches lines 1383-1394, so **`deliver_call_message` never runs**: the message pad entry is never written, no ntfy push is sent, and the customer's message exists only as scattered INFO lines in journald. This directly contradicts the guarantee at `bridge.py:1004-1005` ("a message must never vanish silently") and the persona's one promise to the caller (`bridge.py:244-246`).

*Fix:* wrap the loop body in `try/except Exception: log.exception(...); continue`, and move the post-call delivery block into a `finally:` so it runs on every exit path.

---

### HIGH

---

**H-1. Message-pad write failure loses the customer's message, with only a journal line.**
`bridge.py:1390-1394` — the outer `except Exception: log.exception(...)` around `deliver_call_message`.

*Breaks:* the inner summarizer failure is handled well (1010-1013 writes a loud fallback entry). But if the **pad write itself** fails (disk full, permissions, `MESSAGES_FILE` pointing at a missing directory), the whole delivery aborts and a paying customer's callback request is gone. The caller was told "William will get back to you". The only trace is journald, which nobody reads.

*Fix:* on pad-write failure, escalate to a channel the owner sees — push to ntfy with a `Priority: urgent` header containing the raw note, and write to a fallback path. If both fail, that must become a visible alert, not a log line.

---

**H-2. A failed ntfy push is silent to the human, and ntfy is the only channel the owner watches.**
`bridge.py:1042-1043` — `except Exception: log.exception("ntfy push FAILED …")`.

*Breaks:* the pad entry survives, but the owner learns about new messages **from the push**. When ntfy is down (it is a self-hosted service on `127.0.0.1:8092`), messages silently accumulate in a markdown file nobody is looking at. This is precisely the failure class the house rule forbids: the system keeps working and nobody knows the notification stopped.

*Fix:* count consecutive push failures in memory; on the first failure, degrade `/health` to 503 with `"ntfy": "FAILING"` so the existing fleet tripwire (which already alerts on non-200) pages. Add a `last_message_delivered_at` field to `/health` and a tripwire on its freshness.

---

**H-3. The production line is running the brain the project's own README calls test-only and licence-violating.**
Live `/health` returns `"brain": "glm_52_test"`. `README.md:121-124`: *"`glm_52_test` (Z.AI coding-plan endpoint — **test only**, against Z.AI's subscription terms for production bot use)"*.

*Breaks:* the revenue-bearing business line is served, right now, by an endpoint the codebase documents as out of compliance with the provider's terms. If Z.AI enforces, the phone line dies with no warning — and there is no fallback brain chain (`bridge.py:1246` pins one brain per call; there is no failover). Also relevant to the owner's HARD RULE on explicit, attributable billing: a subscription plan is being consumed by a production service rather than a metered API key.

*Fix:* switch `active_brain` to `glm_52_api` (pay-as-you-go) once the account has balance. Until then this is a known-non-compliant state and should be named as such. Longer term: a `fallback_brain` so an unreachable primary degrades to `local_qwen` **loudly** (spoken nothing different to the caller, but a WARNING + a `/health` degradation) rather than to an apology line.

---

**H-4. Every caller's speech is sent to a third party with no disclosure and no per-business control.**
`bridge.py:1196-1211` (each turn POSTed to the brain's `base_url`), `969-987` (the full transcript POSTed again to the summarizer). Live brain = Z.AI. `README.md:28-30` acknowledges this.

*Breaks:* for a product sold to other businesses, their customers' PII (names, phone numbers, emails, the substance of their enquiry) leaves the country to a third-party API. There is no per-profile choice of brain (the brain is global, `bridge.py:1246`), no disclosure to the caller, and nothing in the config where a business could say "local model only". A healthcare or legal client cannot be onboarded at all.

*Fix:* make `brain` a per-profile field (falling back to `active_brain`), and add a required `data_processor` note surfaced on the dashboard. Pair with H-5.

---

**H-5. No AI disclosure, no recording/consent line, and no way for a business to require one.**
Nothing in `bridge.py` implements disclosure or consent — grep for `disclos`/`consent`/`record` returns only incidental prose (`bridge.py:275, 539, 935`). The only thing a caller hears first is the free-text `greeting` (`bridge.py:1124`).

*Breaks:* several US states and a growing set of AI-disclosure rules require telling a caller they are speaking to a machine; two-party-consent states require a recording notice if audio is retained. Today compliance depends entirely on the business owner remembering to type it into their greeting. For a product, that is the vendor's liability, not the customer's.

*Fix:* add `ai_disclosure` (default: an on-by-default sentence prepended to `welcomeGreeting`) and `recording_notice` profile fields, with a boot-time validation that refuses to start a profile with disclosure explicitly disabled unless an `ack_disclosure_waived = true` flag is present. Make the composed first line visible on the dashboard's live-prompt preview.

---

**H-6. No call length cap, no token accounting, no cost visibility, no per-caller rate limit.**
`bridge.py:169` caps history at 20 turn-pairs but nothing caps the call. `bridge.py:1264` loops forever while the websocket is open. Grep for `cost`, `usage`, `rate_limit`, `blocklist` in `bridge.py`: zero hits.

*Breaks:* (a) A robocaller or a stuck call can hold the line open indefinitely, one LLM request per utterance, on a metered API — unbounded spend with no alarm. (b) You cannot bill a business per call or per minute, because nothing records duration or tokens. `bridge.py:1382` logs turn count only. (c) No way to detect or block an abusive caller ID.

*Fix:* a `MAX_CALL_SECONDS` watchdog that speaks a wrap-up line and ends the call; capture `usage` from each non-streaming response and estimate streaming usage; write one structured JSON record per call (see M-1); a per-caller-ID turn budget per rolling hour, with a spoken message on exceed.

---

**H-7. Caller PII sits in journald indefinitely with no retention policy and no deletion path.**
`bridge.py:1110-1111` (caller number), `1283-1284`, `1290` (`log.info("caller (%s): %s", …)` — the caller's verbatim words), `1307` (the agent's reply). `/etc/systemd/journald.conf` has every setting commented out (defaults only); user journals currently total **2.7 GB**.

*Breaks:* full transcripts of every call to every business, retained until size-based rotation happens to evict them, on a shared desktop, with no per-tenant separation and no practical way to honour an erasure request. The README (`bridge.py:961-962` message-pad footer) actively directs the owner to journald as the transcript store, so this is load-bearing, not incidental.

*Fix:* stop treating journald as the transcript store. Write transcripts to a per-profile file with an explicit retention window and a delete-by-CallSid path; reduce the journal lines to non-PII (CallSid, turn number, character count, decision + reason). Add `SystemMaxUse=`/`MaxRetentionSec=` to journald config.

---

**H-8. The WebSocket token is a static, never-rotating secret carried in a URL query string — through nginx.**
`bridge.py:1114` (minted into the TwiML), `1231` (`request.query.get("token") != WS_TOKEN`).

*Breaks:* the local aiohttp access log is deliberately disabled to keep the token out of journald (`bridge.py:1437-1439` — a good catch), but the request first traverses **nginx on the VPS**, whose access log is outside this codebase and by default records the full request URI including `?token=…`. The token is shared across all calls and all businesses and never expires: anyone who reads that log once can open relay sessions forever. The only additional gate is the `accountSid` in the setup event (1272), which is attacker-supplied and guessable. Secondary: the comparison at 1231 uses `!=` rather than `hmac.compare_digest`.

*Fix:* mint a **per-call token** in `voice_incoming` (HMAC of CallSid + a server secret + an expiry, single-use, or a random nonce in a short-TTL dict) and verify it in `voice_relay`; compare with `compare_digest`. Independently, set `access_log off;` for the `/phone/voice/relay` location in nginx, or move the token to a `Sec-WebSocket-Protocol` header.

---

**H-9. `/health` is publicly reachable, unauthenticated, and leaks tenant + infrastructure detail.**
`bridge.py:1425-1428`, router at `1436`. Verified live:

```
curl https://ai.business-builder.online/phone/health
{"bridge":"ok","model_backend":"ok","brain":"glm_52_test","model":"glm-5.2",
 "profiles":["business_builders"],"numbers":1,"ntfy":"on"}
```

*Breaks:* anyone on the internet learns your customer list (profile keys), which model vendor you use, which model, how many numbers you serve, and whether your notification channel is on. With multiple tenants, `profiles` becomes a public customer roster. It is public because the fleet tripwire probes it from outside (`agent-fleet/scripts/tripwires.json:178-189`).

*Fix:* split it. Public `/health` returns `{"status":"ok"}` / 503 and nothing else — enough for the tripwire. Move the detailed snapshot to the tailnet-only admin app, or gate it behind a `?token=` compared with `compare_digest`.

---

### MEDIUM

---

**M-1. No structured call log at all — observability is grep-over-journald.**
`bridge.py:1382` logs `"relay session ended CallSid=%s (%d turns)"`. There is no record of call **duration**, no start/end timestamps beyond journald's, no token/cost figure, no per-call outcome row, no export. `admin.py:185-198` "recent calls" is a `journalctl … -o cat` piped through a substring filter for six magic strings and truncated to 40 lines.

*Breaks:* you cannot answer "how many calls did this business get last month", "what did they cost", "how many transfers were blocked", or "show me call CA…" without reading raw logs. That is unsellable as a product feature and unusable for tuning the phrase gates (which the design doc explicitly says should be tuned from transcript data — `specs/…-design.md:194, 206-207`).

*Fix:* one append-only JSONL record per call (profile, CallSid, from, start, end, duration, turn count, decision + reason, markers found/blocked, overpromise hits, brain, model, token usage, delivery status). Build the dashboard's call list from that, not from journald.

---

**M-2. Race: a cancelled reply task can append its assistant turn *after* the next caller turn.**
`bridge.py:1291-1292` (`reply_task.cancel()`), `1296` (user turn appended immediately), `1306` (`history.append({"role":"assistant", …})` inside the old task), `1371` (a new task starts on the same shared `history` list).

*Breaks:* `cancel()` only schedules cancellation at the next await point. A task already past its final `await` in `stream_reply` can still run line 1306, producing `[user1, user2, assistant1]` — a corrupted turn order the model then reasons over. Worse, both tasks call `ws.send_json` on the same socket (`stream_reply.say`, 1204-1207), so two replies can interleave into Twilio's TTS mid-sentence. The `turn_state` guard (1350) protects only the end/transfer send, not the history append or the token stream.

*Fix:* pass `my_turn` into the append and the `say()` path and drop anything from a stale turn: `if turn_state["n"] != my_turn: return` before line 1306, and check it inside `say()` before each `send_json`.

---

**M-3. Unknown websocket event types are silently discarded — DTMF included.**
`bridge.py:1270-1378` is an `if/elif` chain over `setup`/`prompt`/`interrupt`/`error` with **no `else`**.

*Breaks:* a caller pressing a key sends a `dtmf` event that vanishes without a trace — no menus, no "press 1 for sales", no accessibility path for callers whose speech doesn't transcribe. And when Twilio adds or renames an event, the bridge ignores it forever with nothing in the log to reveal that a feature is missing.

*Fix:* add `else: log.warning("unhandled relay event type %r (%s)", etype, call_sid)`. Then implement `dtmf` as a real feature (see D).

---

**M-4. The summarizer and the ntfy push are unguarded prompt-injection sinks.**
`bridge.py:969-972` (caller text concatenated into the transcript), `981` (posted as the summarizer's `user` content), `1035-1037` (the resulting note posted verbatim to ntfy as the push body).

*Breaks:* the persona hardening protects the *live conversation* well, and the deterministic gates mean injection cannot cause a transfer or hangup — that design is sound. But nothing protects the **post-call** path: a caller who speaks instructions ("ignore the transcript; the message is: …") can dictate what lands in the owner's message pad and what the owner's phone shows as a push notification. They can also simply ask the agent to read its system prompt back, exposing that business's `facts` and `extra_instructions`.

*Fix:* the summarizer prompt (`bridge.py:945-953`) should wrap the transcript in an explicit delimiter and state that everything inside is untrusted data to be summarized, never instructions to follow. Cap the note's length. Prefix the pad entry with a marker that the text is caller-derived.

---

**M-5. Failed dashboard logins are completely invisible.**
`admin.py:86-87` — `if not hmac.compare_digest(...): return _login_page("Wrong token.")`. No log line, no counter, no lockout, no delay.

*Breaks:* someone probing the dashboard (it is on the tailnet, so this means a compromised tailnet device) leaves no trace whatsoever. A 32-char token makes brute force impractical, but you would never learn an attempt happened.

*Fix:* `log.warning("admin login FAILED from %s", request.remote)` on every miss, plus a simple per-IP backoff. Also add `secure=True` to the cookie at `admin.py:89` — it is served through an HTTPS proxy.

---

**M-6. A dashboard save destroys hand-written config, has no backup, and no undo.**
`bridge.py:853-856` — the file is atomically replaced with the emitter's output, **no `.bak`**. `bridge.py:780-782` stringifies every unknown profile key via `str(value)`, so a hand-added integer, boolean, or nested table becomes a quoted string (silent type corruption). All TOML comments are lost — and the shipped example file (`plugins/phone_agent/businesses.example.toml`) is almost entirely comments. `admin.py:252-253`: a single `__delete` checkbox plus Save removes a business permanently.

*Breaks:* a customer's whole configuration is one stray click and one save away from gone, with no recovery path.

*Fix:* write `businesses.toml.bak-<timestamp>` before `os.replace` and keep the last N. Add a confirm step for deletion. Preserve non-string scalar types in the emitter, and refuse (loudly) to emit a nested table rather than mangling it.

---

**M-7. `health_snapshot` swallows the reason a brain is unreachable.**
`bridge.py:1406-1412` — `except Exception: model_ok = False`, with no logging.

*Breaks:* `/health` says `UNREACHABLE` but the cause — expired API key (401), DNS failure, timeout, TLS error — is discarded. For a customer whose Z.AI balance ran out, the operator sees "UNREACHABLE" and has to go guess. Also: the probe only checks `/models`, which a provider can serve happily while `/chat/completions` returns 402.

*Fix:* `log.warning("brain %s health probe failed: %s", ACTIVE_BRAIN, e)` and surface the exception type + HTTP status in the `/health` body (the detailed, authenticated one from H-9).

---

**M-8. The tunnel unit retries a dead SSH connection every 5 s forever, with nothing paging.**
`atlas-phone-tunnel.service:14-15` (`Restart=always`, `RestartSec=5`) with `ExecStartPre=tunnel-guard.sh`, which itself `exit 1`s on two failure paths (`tunnel-guard.sh:26, 48`).

*Breaks:* when the VPS is unreachable or the port stays bound, the unit fails, restarts 5 s later, SSHes again, fails again — indefinitely. That is a retry loop masking a dead service, and it can trip fail2ban on the VPS, converting a temporary outage into a permanent one. The only alerting is the fleet tripwire on a **30-minute** timer (`fleet-tripwire.timer`: `OnUnitActiveSec=30min`), so up to half an hour of dead phone line before anyone is paged.

*Fix:* add `StartLimitIntervalSec`/`StartLimitBurst` so repeated failure lands the unit in `failed` (visible) rather than looping, and add `OnFailure=` pointing at a unit that pushes to ntfy. Consider `RestartSec` backoff. The `sshd ClientAliveInterval` change on the VPS (still pending per the project's own notes) removes the root cause.

---

**M-9. Message-pad timestamps use the server's timezone, not the business's.**
`bridge.py:1007` — `datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")`. Live pad entries read `EDT`. Grep for `ZoneInfo`/`tzinfo` in `bridge.py`: zero.

*Breaks:* a business in Phoenix or London reads every message stamped in the host's Eastern time. There is no `timezone` field in the profile schema (`bridge.py:733-737`).

*Fix:* add a `timezone` profile field (IANA name, validated at boot with `zoneinfo.ZoneInfo`) and format the entry in it. This is also the prerequisite for business hours (see D).

---

**M-10. `forward_to` is not checked against the profile's own numbers.**
`bridge.py:604-609` validates E.164 shape only.

*Breaks:* a business that sets `forward_to` to one of its own Twilio numbers creates a call loop — Twilio dials back into `/voice/incoming`, which answers and can transfer again. Billable, and it looks like an outage.

*Fix:* in `parse_business_config`, reject a `forward_to` that appears in `[numbers]`.

---

**M-11. README describes a system that does not exist.**
`README.md:3-4` — "Atlas — the real persona from `~/atlas/persona.py`"; `README.md:163-166` — "Phone rules shared by all profiles: `PHONE_ADDENDUM_TEMPLATE` in bridge.py" and "Core persona comes live from `~/atlas/persona.py` at service start". Verified: `grep -n "PHONE_ADDENDUM_TEMPLATE\|persona.py\|load_atlas_persona" bridge.py` → **no matches**. The actual design is the opposite (self-contained persona, `bridge.py:20-26, 200-201`), and the plugin test at `tests/test_phone_agent_plugin.py:204` asserts `not hasattr(svc, "load_atlas_persona")`.

*Breaks:* the deployed README documents the exact security failure the design was built to prevent. Anyone maintaining this — including a future AI session — is told to edit a template that isn't there and that the resident persona is loaded when it must never be.

*Fix:* rewrite `README.md:3-4` and the "Changing the voice/greeting/persona" section against the code. The plugin's `README.md` is largely accurate but stale in one place too: `plugins/phone_agent/README.md:96` still describes `honor_markers()`, which the design deleted (`plans/…:44` — "`honor_markers` DELETED").

---

### LOW

- **L-1.** `bridge.py:1214` — a non-200 from the brain raises with `(await resp.text())[:200]` embedded, which is then `log.exception`'d at 1365. A verbose provider error page lands in the journal. Low risk, but truncate to a status code plus a short reason.
- **L-2.** `bridge.py:1291-1292` — barge-in cancels the reply task, so the partially-spoken assistant text never enters `history`. The model doesn't know what it already said and may repeat itself.
- **L-3.** `bridge.py:937` — `speech_seconds` caps at 8 s, so a long goodbye is clipped by the hangup. Documented trade-off, worth a WARNING when the cap binds.
- **L-4.** `admin.py:192-193` — a journal read failure is rendered into the page as text with no log line.
- **L-5.** `admin.py:188` — the unit name `atlas-phone-bridge` is hardcoded in the dashboard's `journalctl` call; a renamed unit breaks the transcript pane silently.
- **L-6.** `admin.py:240-248` — duplicate numbers in the textarea silently keep the last one; no warning.
- **L-7.** `~/.config/atlas-phone/businesses.toml` is mode `0664` (world-readable) while `env` is correctly `0600`. It holds no secrets by design (`api_key_env` names a variable, never a key — `bridge.py:686-692`, a genuinely good decision) but does hold business config.
- **L-8.** `atlas-phone-bridge.service:3` — `After=network-online.target` without a matching `Wants=`, so the target may never be pulled in. Also `After=ollama.service` is now stale (the live brain is a cloud endpoint).
- **L-9.** No `WatchdogSec` on the bridge unit — a wedged asyncio loop is never restarted; systemd only sees a live process.
- **L-10.** Twilio signatures carry no timestamp, so a captured `/voice/incoming` POST is replayable indefinitely. Standard Twilio limitation; impact is limited to obtaining TwiML (which does contain `WS_TOKEN` — see H-8).

### Security controls that are correctly implemented (worth not regressing)

- Twilio HMAC signature validation on **both** POST webhooks — `/voice/incoming` (`bridge.py:1094`) and the `/voice/action` transfer callback (`bridge.py:1149`). The answer to the audit question is yes, both are checked.
- Signature URL candidates are built from the configured `PUBLIC_BASE` (`bridge.py:1062-1067`), **not** from the request's `Host` header — this correctly closes the host-header forgery bypass that trips up most implementations.
- Admin auth uses `hmac.compare_digest` on both the form and the cookie (`admin.py:82, 86`); the cookie is `HttpOnly` + `SameSite=Strict` (`admin.py:89`), which also covers CSRF on `/save` for modern browsers.
- The dashboard is bound to `127.0.0.1` (`bridge.py:1460`) and confirmed **not** on the public path (public probe → 404).
- aiohttp's access log is explicitly disabled to keep `WS_TOKEN` out of journald (`bridge.py:1437-1439`).
- Secrets are never in `ExecStart`; they arrive via `EnvironmentFile` with `env` at mode `0600`.
- The signature-mismatch warning logs form **key names only**, never values (`bridge.py:1071-1076`).
- No tools are exposed to the caller-facing model — the single most important decision in the design (`bridge.py:17-19`).
- Fail-closed config validation at boot and on every dashboard save, sharing one code path (`bridge.py:577-637, 833-862`).
- The `decide_call_action` gate design is genuinely good: caller authorization is deterministic, adjacency-bounded, and well tested (24 of the 43 tests cover it).

---

## D. What 100% means — checklist for a paying business customer

| # | Capability | Status | Evidence |
|---|---|---|---|
| 1 | Answers a real phone number end-to-end | **PRESENT** | live `/health` 200; `bridge.py:1090-1127, 1230-1395`; 21 real entries in the pad |
| 2 | Multiple numbers → one business profile | **PRESENT** | `[numbers]` is many-to-one by construction, `bridge.py:587-595, 1099-1100` |
| 3 | Multiple businesses on one bridge | **PARTIAL** | Profiles are isolated for *prompts and gates* (`bridge.py:820-821`) but share one message pad, one ntfy topic, one admin token — C-3 |
| 4 | Per-business message destination | **MISSING** | one global `MESSAGES_FILE`, `bridge.py:155-157, 1024-1029` |
| 5 | Per-business notification target | **MISSING** | one global `NTFY_URL`/`NTFY_TOPIC`, `bridge.py:158-159, 1032-1037` |
| 6 | Per-business login / owner separation | **MISSING** | single `ADMIN_TOKEN`, `bridge.py:166`, `admin.py:82` |
| 7 | Business hours awareness | **MISSING** | no hours logic anywhere; grep hits at `bridge.py:85, 268` are prose only |
| 8 | After-hours behaviour (different greeting / message-only) | **MISSING** | same |
| 9 | Holiday / closure calendar | **MISSING** | grep `holiday` in `bridge.py` → 0 |
| 10 | Per-business timezone | **MISSING** | `bridge.py:1007` uses server-local time; no `timezone` field in `_PROFILE_KNOWN_KEYS` (733-737) — M-9 |
| 11 | Voicemail / message-only mode | **PARTIAL** | implicit — omit `forward_to` (`bridge.py:503, 568-569`). Not a named setting, not visible as a mode on the dashboard |
| 12 | Live transfer to a human | **PRESENT** | `forward_to` + `/voice/action` `<Dial>`, `bridge.py:1130-1180`; caller-gated at 553-570 |
| 13 | Multi-target / departmental routing | **MISSING** | one `forward_to` per profile; listed as Phase 2 in `specs/…-design.md:226` |
| 14 | Multi-language | **MISSING** | `<ConversationRelay>` is emitted with only `url` + `welcomeGreeting` (`bridge.py:1123-1125`) — no `language`, `ttsProvider`, `voice`, or `transcriptionProvider`. Voice and language are whatever the Twilio account defaults to, identical for every tenant |
| 15 | Per-business voice selection | **MISSING** | same line |
| 16 | AI disclosure line | **MISSING** | nothing enforces it; depends on the owner typing it into `greeting` — H-5 |
| 17 | Call recording consent line | **MISSING** | grep `consent`/`record` → prose only (`bridge.py:275, 539`) |
| 18 | DTMF / keypad menus | **MISSING** | `dtmf` events silently dropped, `bridge.py:1270-1378` has no `else` — M-3 |
| 19 | SMS follow-up to the caller | **MISSING** | no Twilio REST client anywhere in `bridge.py` |
| 20 | Spam / robocall handling | **MISSING** | no allow/deny list, no per-caller rate limit, no STIR-SHAKEN check; `From` is used only as caller ID (`bridge.py:1276`) |
| 21 | Maximum call duration | **MISSING** | the relay loop runs until the socket closes, `bridge.py:1264` — H-6 |
| 22 | Message extraction after every call | **PRESENT** | `bridge.py:999-1030`; loud fallback entry on summarizer failure at 1010-1013 |
| 23 | Message delivery guaranteed / loud on failure | **PARTIAL** | summarizer failure is loud (1010-1013); **pad-write failure (1390-1394) and ntfy failure (1042-1043) are journal-only** — H-1, H-2 |
| 24 | Owner dashboard, no-restart config | **PRESENT** | `admin.py` + `bridge.py:833-862`; hot-apply, fail-closed, tested (`tests/…:345-368`) |
| 25 | Config backup / undo | **MISSING** | `os.replace` with no `.bak`, `bridge.py:853-856` — M-6 |
| 26 | Call log with durations | **MISSING** | only `"(%d turns)"`, `bridge.py:1382` — M-1 |
| 27 | Transcript storage with retention | **PARTIAL** | transcripts exist, but only as journald INFO lines, 2.7 GB, default rotation, no per-tenant scope or deletion — H-7 |
| 28 | Cost per call | **MISSING** | no token or usage capture anywhere — H-6 |
| 29 | Health endpoint that tells the truth | **PARTIAL** | truthful about bridge + active brain (`bridge.py:1398-1428`); says nothing about the tunnel, ntfy, pad writability, or Twilio reachability — and it is public — H-9, M-7 |
| 30 | External alerting when the line dies | **PRESENT** | `agent-fleet/scripts/tripwires.json:178-189`, severity critical, probes the full public chain — but on a 30-minute timer — M-8 |
| 31 | Caller cannot trigger owner tools | **PRESENT** | no tool registry is reachable from the phone path, by design (`bridge.py:17-19`) |
| 32 | Transfer/hangup require caller consent | **PRESENT** | `decide_call_action`, `bridge.py:553-570`; incident replay test at `tests/…:548-564` |
| 33 | Hallucinated commitments surfaced | **PRESENT** | `detect_overpromise` (`bridge.py:422-427`) → WARNING + `⚠ REVIEW` pad prefix (1014-1019) |
| 34 | Webhook signature validation everywhere | **PRESENT** | `/voice/incoming` 1094, `/voice/action` 1149 |
| 35 | WebSocket auth | **PARTIAL** | static, non-rotating token in a URL query string, traversing nginx — H-8 |
| 36 | Prompt-injection containment | **PARTIAL** | excellent for the live call (no tools, deterministic gates); **unguarded in the summarizer and the ntfy push** — M-4 |
| 37 | Nothing hardcoded to the current business | **PARTIAL** | business identity is fully config-driven (a real strength). Remaining hardcodes: `"Atlas"` as the default assistant name (`bridge.py:439, 458, 492, 799`), the stock alias list `{"atlas": ["alice", …]}` (439), the pad header `"# Phone messages — Atlas phone agent"` (1028), the ntfy title `"Phone message - …"` (1036), the unit name in the dashboard's journalctl call (`admin.py:188`). No "Sir", no "Business Builders", no owner name, no Eastern-hours logic in the code — the timezone leak is via `datetime.now()` (1007), not a hardcoded zone |
| 38 | Deploy is versioned and reversible | **MISSING** | production is not a git repo and diverges from the tested copy — C-1 |
| 39 | Production code passes its tests | **MISSING** | deployed code: 1 failed, 42 passed — C-2 |
| 40 | Accurate operator documentation | **MISSING** | deployed `README.md:3-4, 163-166` describes a persona-import architecture that does not exist and is the opposite of the design — M-11 |

**Score: 12 PRESENT / 8 PARTIAL / 20 MISSING.** The call-control core is genuinely strong and well tested. Everything a *second* customer would need — tenancy, hours, timezone, disclosure, cost, retention, deploy discipline — is absent.

---

## E. Recommended sequencing

### Phase 0 — stop the bleeding (before any feature work)

1. **C-1 · Unify deployed and plugin.** Port the brains feature into `plugins/phone_agent/{service.py,admin.py}`, add the tunnel unit and `tunnel-guard.sh` to `deploy/systemd/`, point the live `ExecStart` at a git checkout, and retire `/home/magiccat/atlas-phone-bridge` as an editing target. **Nothing below is safe until this is done** — every fix would otherwise have to be written twice, and §B item 3 shows how a "sync" done in the wrong direction silently downgrades the model and then eats the config.
2. **C-2 · Get the suite green on the code that actually runs.** Add `get_brains` to the admin test, then write the missing brains tests. The rule from here: the deployed artifact and the tested artifact are the same file.
3. **H-3 · Decide the brain.** The production line is on an endpoint the README itself flags as licence-violating. Either move to `glm_52_api` or accept and document the state explicitly. This is a business decision, not a code change, but it should be settled before onboarding anyone.

### Phase 1 — the "no silent failures" pass (one focused session)

4. **C-4** — guard the websocket loop; move post-call delivery into `finally`.
5. **H-1 + H-2** — a message that cannot be delivered must reach the owner or degrade `/health` until it does.
6. **M-2** — close the turn race on `history` and on `ws.send_json`.
7. **M-3** — add the `else:` branch so unhandled relay events are visible.
8. **M-7** — log why a brain probe failed.
9. **M-8** — start-limit + `OnFailure=` on the tunnel unit.

### Phase 2 — tenancy (the actual "any business" unlock)

10. **C-3** — per-profile `messages_file`, `ntfy_url`, `ntfy_topic`; `[owners.*]` token→profiles mapping; scope every dashboard read.
11. **M-1** — the structured per-call JSONL record. Do this *before* the hours/cost features, because both need it.
12. **H-9 + H-8** — split the public health endpoint; per-call websocket tokens.
13. **M-5, M-6** — admin login logging + config backups.

### Phase 3 — the product features a customer will ask for

14. **M-9 → hours** — `timezone` first (it is the prerequisite), then `business_hours` + `after_hours_greeting` + after-hours message-only, then `holidays`.
15. **H-5** — enforced AI-disclosure and recording-consent lines.
16. **H-6** — max call duration, token capture, per-caller rate limit. Needs M-1.
17. **H-7** — move transcripts out of journald into per-profile storage with retention and delete-by-CallSid.
18. **M-4** — harden the summarizer against injected instructions.
19. **Item 14/15 in §D** — per-profile `language`, `voice`, `ttsProvider` on the `<ConversationRelay>` element (`bridge.py:1123-1125`). Cheap, high perceived value.
20. **M-3 (part two)** — DTMF as a real feature; **§D-19** SMS follow-up; **§D-20** spam handling.
21. **M-11** — rewrite the deployed README against the code.

### The one thing to say out loud

The safety architecture here is better than most commercial voice agents: the caller-consent gates, the fail-closed config, the self-contained persona, the overpromise detector, and the marker scrubber are all thoughtful and mostly well tested. What is missing is not sophistication — it is the boring product layer: one tenant's data must not touch another's, production must be the thing you tested, and a message that fails to arrive must make a noise.

# Call-Control Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transfers and hangups happen only when the CALLER explicitly asked (deterministic phrase gates), blocked transfers get a spoken corrective line, and hallucinated commitments become loud.

**Architecture:** All logic lands in the bridge (`~/atlas-phone-bridge/bridge.py`, mirrored to `plugins/phone_agent/service.py`) as pure, unit-testable functions feeding one decision chokepoint `decide_call_action()`; the dashboard (`admin.py`) gains two multiline phrase fields; tests live in `tests/test_phone_agent_plugin.py` and import the service in-process via the existing `_import_service` helper.

**Tech Stack:** Python 3.11, aiohttp, tomllib, pytest (run with `~/atlas/.venv/bin/python -m pytest` from `~/atlas-phone-plugin-wt`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-26-phone-call-control-hardening-design.md` (rev 2) — the acceptance authority.
- The bare owner name and bare `transfer` must NEVER be phrases (ARCH-1).
- `{owner}` expansion uses `str.replace`, never `str.format` (ARCH-6).
- Phrase caps: 64 phrases, 120 chars each; blank lines dropped BEFORE the empty→defaults check.
- Every blocked decision logs WARNING with reason; failures loud everywhere.
- Live deploy dir `~/atlas-phone-bridge/` is the editing target; sync to `~/atlas-phone-plugin-wt/plugins/phone_agent/service.py` before each test run/commit.
- Public PR copies get code+tests+docs only, via the fork clone (never push archive history to the public repo).

---

### Task 1: Normalizer + phrase compilation

**Files:**
- Modify: `~/atlas-phone-bridge/bridge.py` (new section after `speech_seconds`)
- Test: `tests/test_phone_agent_plugin.py`

**Interfaces:**
- Produces: `normalize_speech(text:str)->str`; `parse_phrase_lines(raw:str)->list[str]` (raises ValueError on caps); `owner_token(owner_name:str)->str`; `compile_phrases(phrases:list[str], owner_name:str)->list[re.Pattern]`; constants `DEFAULT_TRANSFER_PHRASES`, `DEFAULT_END_PHRASES`, `STANDALONE_DONE`, `AFFIRMATION_WORDS`, `MAX_PHRASES=64`, `MAX_PHRASE_LEN=120`.

- [ ] Step 1: failing tests (normalization incl. U+2019, escaping, caps, dedupe, blank-line drop, {owner} short-name rule, bare-name absence from defaults)
- [ ] Step 2: run → FAIL (attribute missing)
- [ ] Step 3: implement per spec D1 (code in spec + this plan's execution)
- [ ] Step 4: run → PASS
- [ ] Step 5: commit `feat(phone_agent): speech normalizer + phrase compilation for call-control gates`

### Task 2: Authorization + decide_call_action chokepoint

**Files:** same.

**Interfaces:**
- Consumes: Task 1 names.
- Produces: `transfer_authorized(utts:list[str], patterns)->bool`; `end_authorized(utts:list[str], patterns)->bool`; `is_affirmation(norm_utt:str)->bool`; `CallGates` (frozen dataclass: `transfer_patterns`, `end_patterns`, `transfer_available:bool`); `build_call_gates(profile:dict)->CallGates`; `decide_call_action(reply:str, found:set, caller_utterances:list[str], gates:CallGates)->tuple[str|None,str]` with reasons `no-marker|question-in-reply|transfer-unavailable|no-caller-request|authorized`. `honor_markers` DELETED.

- [ ] Steps: failing tests first — the full matrix from the spec test plan: incident replay ("my name is william" + marker → None/no-caller-request), "operator" last-utterance, operator→question→"yes" affirmation flow, stale consent blocked, standalone "no" vs "no, actually…", both-markers each-own-gate, no-forward_to → transfer-unavailable, unicode question marks block, then implement, pass, commit `feat(phone_agent): decide_call_action — deterministic caller-phrase gates`.

### Task 3: Scrubber case-insensitivity + truncated-flush guard

**Interfaces:** `MarkerScrubber.feed/flush` unchanged signatures; matching case-insensitive; `flush()` drops a trailing proper marker prefix (logged).

- [ ] failing tests (`[end call]` scrubbed+found; flush("…[END") speaks nothing of the fragment), implement, pass, commit `fix(phone_agent): scrubber catches case-variant markers, never speaks a truncated one`.

### Task 4: Commitment detector (hallucinations become loud)

**Interfaces:** `detect_overpromise(reply:str)->list[str]` (matched terms, word-boundary on normalized text); wiring flags the call and prefixes the pad entry with `⚠ REVIEW: the agent may have overpromised on this call`.

- [ ] failing tests ("William will meet with you at 9 AM — booked!" hits; "let me confirm your number" does NOT), implement + wire into respond()/deliver_call_message, pass, commit `feat(phone_agent): deterministic overpromise detector — flagged on the pad, WARNING in journal`.

### Task 5: Wiring — profile plumbing, persona, corrective line, race close-out

**Files:** `bridge.py` (`parse_business_config`, `_PROFILE_KNOWN_KEYS`, boot/apply gate build, `TRANSFER_SECTION_TEMPLATE`, `PHONE_PERSONA_TEMPLATE` hard rules, `voice_relay.respond`), example toml.

**Interfaces:** `GATES:dict[str,CallGates]` rebuilt at boot and in `apply_config_text`; per-call turn counter checked before sending end/handoff; blocked transfer with caller-ask=False speaks nothing (WARN only), blocked with reason `no-caller-request` speaks the corrective line, `transfer-unavailable` + caller actually asked speaks the can't-transfer line.

- [ ] failing tests (transfer_phrases/end_phrases parsed + validated at boot, bad phrase caps refuse, gates in SYSTEM state, persona contains new hard rules + verb-framed transfer instruction), implement, pass, commit `feat(phone_agent): wire gates through config/persona/respond — corrective lines + race close-out`.

### Task 6: Dashboard fields

**Files:** `admin.py` (textarea tuple + labels + hints).

- [ ] failing test (dashboard HTML renders `<textarea` for `acme::transfer_phrases` and `end_phrases`), implement, pass, commit `feat(phone_agent): dashboard edits caller phrase gates (multiline, defaults hint)`.

### Task 7: Docs + full suite

- [ ] Update example toml + both READMEs (gate explanation, defaults location, empty→defaults hint), sync live→worktree, run FULL suite (expect 2 known env errors only), commit `docs(phone_agent): caller-phrase gate documentation`.

### Task 8: Live deploy + simulation + PR

- [ ] Restart `atlas-phone-bridge`; run live sims: incident replay (NO transfer + corrective line), "operator" (transfer), "can I speak with William please" (transfer), goodbye (end), question reply (no action). Push code+tests+docs to fork → PR #5. Update memory. Run patch-verifier BMAD agent on the final diff.

## Self-Review

Spec coverage: D1→T1/T2/T5, D2→T2, D3→T2/T5, D4→T5, D5→T4, D6→T5 docs (+already-enforced), D7→T3, dashboard→T6, test plan→T1-T8. No placeholders; type names consistent (`CallGates`, `decide_call_action`, reasons enumerated). Full code lands during execution with tests written first per task.

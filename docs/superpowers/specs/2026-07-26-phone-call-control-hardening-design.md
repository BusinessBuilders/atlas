# Phone agent call-control hardening — design (rev 2, post-BMAD review)

**Date:** 2026-07-26 · **Trigger:** live call CAc9eea473… transferred to the
owner because the caller said "My name is William, actually" — no transfer
request existed. Same call: the agent addressed the caller by a name they
never gave ("Alice") and stated an appointment was booked ("William will meet
with you at 9 AM tomorrow"), which it is forbidden to do.

**Review:** three independent BMAD reviewers (architect, acceptance auditor,
edge-case hunter) returned APPROVE-WITH-CHANGES; their convergent findings
are folded in below and marked (ARCH-n / AUDIT-n / EDGE).

## Problem

The bridge trusts a 7B model with in-band control markers. Existing defenses
(prompt rules + a question-guard that inspects only the reply's final
character) are insufficient: transfer fired without any caller request, the
guard was dodged by a multi-sentence reply, and semantic rules (no
commitments, no invented names) fail silently.

Owner's directive: *"the person needs to say operator or do something else"*
— call control must be **deterministic and caller-driven**. Owner's second
directive: **one source of truth** for everything the agent tells customers.

## Design

### D1. Caller-phrase gates (deterministic, authoritative)

A control marker is honored only when the **caller** explicitly asked for
that action. Both must agree — model marker AND caller authorization; either
alone does nothing (WARNING logged with reason).

**Normalization (both phrases and utterances, same function):** NFKC
unicode normalization; curly apostrophes/quotes mapped to ASCII; lowercase;
punctuation stripped to spaces; whitespace collapsed. (EDGE: U+2019
apostrophes, casing.)

**Matching:** each phrase is `re.escape()`d and wrapped in word boundaries;
the window's utterances are **joined with a space** into one string before
matching (EDGE: requests split across STT prompt segments). Patterns are
**precompiled at config-apply time**, deduped, size-capped (64 phrases,
120 chars each — dashboard save rejects beyond that). (EDGE: metacharacters,
latency, dedupe.)

**Transfer authorization** (ARCH-3 stale-consent fix; tightened again after
code review — BLIND-1): authorized iff
- a transfer phrase matches the caller's **last utterance**, OR
- the last utterance is a short affirmation (normalized, ≤3 words drawn
  from: yes, yeah, yep, sure, ok, okay, please, correct, right, that's)
  AND a transfer phrase matches the **immediately preceding** caller
  utterance — the "operator" → "shall I connect you?" → "yes" flow.
  Consent and confirmation must be adjacent turns: a wider joined window
  let a "yes" answering an unrelated question ride a stale "operator" from
  two turns earlier (BLIND-1), so the joined-window variant was dropped.
  Consequence: a request split across two caller utterances no longer
  matches — that fails in the safe direction (message taken; R1).

**End authorization:** an end phrase matches the caller's **last utterance**,
or the last utterance is exactly one of the standalone-done utterances.

**Default transfer phrases (literal list — ARCH-5/EDGE, no bare tokens
except `operator`):** `operator`, `transfer me`, `transfer the call`,
`connect me to`, `speak to a person`, `talk to a person`, `speak with a
person`, `talk with a person`, `speak to a human`, `talk to a human`,
`speak to someone`, `talk to someone`, `real person`, `speak to {owner}`,
`speak with {owner}`, `talk to {owner}`, `talk with {owner}`,
`get {owner} on the phone`. Bare `transfer` and the bare owner name are
**deliberately absent** (ARCH-1: "My name is William" must never authorize).

**Default end phrases (substring):** `goodbye`, `bye now`, `hang up`,
`that's all`, `that'll be all`, `that is all`, `nothing else`, `no thanks`,
`no thank you`, `all set`, `we're done`, `i'm done`, `have a good`.
**Standalone-done utterances (full-utterance equality after normalization):**
`no`, `nope`, `bye`, `that's it`, `im good`, `i'm good`. (EDGE: bare "no" as
a substring would match "no, actually can you also…"; equality matching
cannot.)

**`{owner}` expansion** (ARCH-6/EDGE): `str.replace("{owner}", first)`,
never `str.format`. `first = owner_name.split()[0]` run through the same
normalizer; if it is shorter than 3 characters, the full `owner_name` is
used instead (EDGE: "Jo"/"Al" syllable collisions).

**Per-profile overrides** `transfer_phrases` / `end_phrases`: newline-
separated, dashboard textareas (ARCH-8: they join the multiline-field set,
not single-line inputs). Lines are stripped; blank/whitespace-only lines
are dropped BEFORE the empty-list check (EDGE: a whitespace line must not
become a match-everything phrase). An empty result falls back to defaults —
the dashboard says so next to the field. Disabling transfer entirely =
remove `forward_to` (which already removes the persona's transfer section).

**No-forward safety** (EDGE-16): when the profile has no `forward_to`,
transfer is never an available action — a hallucinated transfer marker is
blocked (`transfer-unavailable`), not sent to Twilio where the action
callback would hang up on the caller.

### D2. Strengthened question-guard (honest trade-off — ARCH-4)

A reply containing `?`, `？`, or `؟` anywhere blocks all markers (was: final
ASCII `?` only). This closes the embedded-question dodge from the incident.
It WILL also false-block natural tag-question goodbyes ("take care, okay?")
— we accept that deliberately: the phrase gate means the caller has already
said goodbye, so the worst case is the caller hangs up themselves, versus
the alternative worst case of hanging up mid-conversation. The guard is
defense-in-depth; the phrase gate is the primary control (a "?"-less
interrogative like "anything else [END CALL]" is still blocked by the
caller-phrase requirement — EDGE-5).

### D3. Decision chokepoint

`decide_call_action(reply, found, caller_utterances, gates) -> (action,
reason)` — pure, unit-tested, the ONLY decider (subsumes `honor_markers`,
which is removed — ARCH-7). It receives the full recent caller-utterance
list and slices windows internally. Each marker is tested against **its
own** gate; transfer takes precedence only when transfer itself is
authorized, otherwise end is considered on its own merits (EDGE-8). Reasons:
`question-in-reply`, `no-caller-request`, `transfer-unavailable`,
`no-marker`. Every block logs a WARNING with reason + recent caller text.

**Post-block caller recovery (ARCH-2):** a blocked **transfer** almost
certainly followed a spoken "connecting you now" sentence. The bridge then
speaks a server-authored corrective line (not model output):
"Just so you know — I can only connect you if you ask me to. If you'd like
{owner_name}, say the word operator." A blocked **end** needs no corrective
line (the call simply stays open; the caller talks on or hangs up). This
makes the block loud to the CALLER, not only the journal.

**Race close-out (EDGE-15):** the respond() task re-checks that no newer
caller prompt has arrived (per-call turn counter) immediately before sending
the end/handoff message after the speech-wait; if the world moved, abort.

### D4. Persona hardening (rules for what servers can't catch)

- Transfer section rewritten: transfer ONLY when the caller explicitly asks
  ("operator", "can I talk to a person / {owner}"); a caller merely
  mentioning {owner}'s name, or introducing themselves, is NOT a request.
- New hard rule: never state that an appointment, booking, order, or
  purchase is made, confirmed, or scheduled — only that the request will be
  passed to {owner}, who confirms.
- New hard rule: never address the caller by any name they did not give as
  their own; if they haven't given one, don't guess.

### D5. Commitment/name detector — hallucinations become LOUD (ARCH-9 + AUDIT-1)

Persona rules alone fail silently, which violates the fail-loud house rule.
A deterministic, zero-latency detector scans each completed reply for
commitment language (`booked`, `confirmed`, `scheduled`, `you're all set`,
`i've sent`, `i'll send`, `we've set up`, `reserved`) — on a hit: WARNING
log AND the call's message-pad entry is prefixed with
`⚠ REVIEW: the agent may have overpromised on this call` so the owner sees
it in the pad and the push notification. Detection only — no blocking (a
false positive costs a needless review flag, never a broken call). Name
hallucination remains undetectable deterministically → residual R2, but now
the commitment half of R2 is observed, not silent.

### D6. One source of truth for customer-facing information (owner directive)

Everything the agent may tell a customer lives in exactly one place: the
business profile (`businesses.toml`, edited on the dashboard).

- `greeting`, `services`, `facts`, `extra_instructions` are the ONLY
  customer-facing knowledge; the persona template contains behavior rules,
  never business information; the resident Atlas is never consulted.
- Facts rule tightened: the agent may repeat what THIS caller said in THIS
  call, but never carries information between calls, guesses, or
  extrapolates ("we probably also do X" is forbidden).
- The dashboard's live-prompt preview is the verification surface: what the
  page shows IS everything the agent knows for that business.
- **Plainly stated for the owner (AUDIT-2):** facts are still hand-
  maintained on the dashboard today. Auto-syncing them from a canonical
  document (website/wiki) is Phase 2, not built.

### D7. Scrubber robustness

- Marker scan becomes case-insensitive (lowercased shadow buffer, same
  offsets), so `[end call]` is caught, scrubbed, and gated rather than
  spoken (EDGE-10). Whitespace-variant markers (`[ END CALL ]`) remain
  unscrubbed but are detected post-reply and WARNING-logged.
- `flush()` drops (and logs) a trailing fragment that is a proper marker
  prefix instead of speaking it — a stream truncated mid-marker must not
  say "[END" to a customer (EDGE-21).

## Alternatives considered

Model-only prompting (status quo): rejected — the failure mode being fixed.
Server-side NLU intent classifier: rejected — a second model to distrust;
the owner asked for explicit phrases. Two-turn confirmation protocol:
rejected for v1; the affirmation rule in D1 captures its value
deterministically.

## Risk register

- **R1 missed legitimate phrasing** ("get me your manager") → no transfer;
  message taken instead (the safe direction the owner chose). Phrases are
  dashboard-tunable from real transcripts.
- **R2 semantic hallucinations**: commitments are now DETECTED and flagged
  (D5) but not blocked; invented names are neither — persona rules only.
  Accepted residual at this model size; revisit on model upgrade.
- **R3 premature end on a standalone "no"** needs model marker + exact
  "no" utterance + 8s of silence; worst case the caller calls back.
- **R4 negated phrase** ("don't transfer me") counts as authorization if
  the model also spuriously marks (EDGE-3). Accepted: requires two
  simultaneous failures; multi-word defaults shrink the surface; revisit
  with transcript data rather than building negation NLP now.
- **R5 innocent-context phrase** ("transfer my prescription" is excluded by
  D1's defaults, but "connect me to" + model marker could coincide) —
  false-positive path recorded per ARCH-5; mitigated by multi-word
  defaults + both-must-agree; dashboard tuning is the lever.

## Test plan

Unit: normalizer (unicode apostrophes, punctuation), phrase compilation
(escaping, dedupe, caps, {owner} expansion incl. short names), transfer/end
authorization matrices (incident replay "my name is william" must NOT
authorize; "operator"→question→"yes" must; stale consent without
affirmation must not; standalone "no" vs "no, actually…"), decide_call_action
full matrix (both markers, no forward_to, question variants ？/؟),
scrubber case-insensitivity + truncated-flush, commitment detector,
config plumbing + emitter round-trip, dashboard textarea rendering of the
new fields. Live simulation: incident replay (no transfer), "operator"
(transfer), "can I speak with William" (transfer), blocked-transfer
corrective line spoken, goodbye (end), question reply (block).

## Out of scope (Phase 2)

Facts auto-sync from a canonical business document; negation-aware
matching; two-turn confirmation protocol; per-department multi-target
routing; transcript-driven phrase suggestions.

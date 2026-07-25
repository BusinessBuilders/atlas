---
tool: brief_review
risk: medium
requires_confirmation: false
catalog: review the daily brief — "review my brief", "go through my tasks"; answers done / keep / not doing it
---

# brief_review

Owner-only: run this ONLY for William himself — never for phone-line callers
or non-owner speakers. When William asks to review his brief/tasks/queue:

1. Call `brief_review` with `action: "next"`.
2. Speak the item naturally: "«title». Did you do this?" State the total once
   at the start ("You have 4 open items."). Never read ids aloud.
3. Map his answer and call `action: "mark"` with the item's `id`:
   - yes / did it / done → `answer: "done"`
   - no / not yet → `answer: "keep"` (it comes back tomorrow)
   - we're not doing it / never / drop it → `answer: "dismissed"`
   Ambiguous answer? Ask once more — never guess a dismissal.
4. Repeat from step 1 until `item` is null, then close with one line:
   "Queue clear — 2 done, 1 dismissed, 1 kept."

Answers land in the shared review queue (`~/.local/state/review-queue/queue.db`)
— the same DB the Wealth OS dashboard's /review page writes, so one ack
silences every nagger including the 06:30 morning brief.

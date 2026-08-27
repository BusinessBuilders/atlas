# The Industry Standard for AI Voice Phone Agents / AI Receptionists (SMB market)

**Purpose:** a measuring stick. We build an AI receptionist on Twilio ConversationRelay with an owner dashboard. This document establishes what the market already ships, so we can see exactly where we meet, beat, or miss the bar.

**Research date:** 2026-08-27. Every claim below carries a source URL. Where a vendor's own page was read, that is noted; where only a third-party review was available, that is noted too — third-party pricing claims for this category go stale fast and frequently disagree with each other, so treat vendor-own-page figures as authoritative and third-party figures as indicative.

**A standing caveat on sources:** this category is saturated with competitor-written "review" and "pricing" blogs (CloudTalk, Retell, Dialora, Sonant, NextPhone, serviceagent.ai and others all publish comparison posts about rivals they are trying to displace). Those posts are useful for feature enumeration and directionally useful for pricing, but every one of them has a commercial motive. Vendor-own pages are cited in preference wherever they were retrievable.

---

## 1. FEATURE STANDARD

### 1.1 The market has three distinct layers

Buyers and analysts consistently split this market into three layers, and it matters for benchmarking because a "competitor" at one layer is not a competitor at another:

| Layer | What it is | Examples | Priced |
|---|---|---|---|
| **Infrastructure / builder platforms** | You build the agent; they supply orchestration, STT/TTS/LLM plumbing, telephony | Retell AI, Vapi, Bland AI, Synthflow, Twilio ConversationRelay itself | Per minute ($0.05–$0.31 all-in) |

| **Packaged AI receptionists** | Finished product an SMB owner self-serves in minutes | Rosie, Goodcall, Dialzara, My AI Front Desk/Frontdesk, Slang.ai, Sameday, Loman, RingCentral AI Receptionist | Flat monthly with minute or caller allowances ($29–$599/mo) |
| **Managed / human-hybrid** | Vendor runs it, humans back-stop the AI | Smith.ai (AI + human), Ruby (human), AnswerConnect, Abby Connect, PATLive | Per call or per minute ($95–$2,100/mo) |

Our product (ConversationRelay + owner dashboard, sold to SMBs) sits in **layer 2 — packaged AI receptionist** — but is built on layer-1 infrastructure. That means we are measured against Rosie/Goodcall/Dialzara on features and dashboard, and against Retell/Vapi on latency and cost stack. This is the single most important framing in this document.

Independent confirmation that inbound receptionist work is the centre of gravity of this market, not a niche: inbound voice agents are **52.1% of AI voice market revenue**, ahead of every outbound use case ([Grand View Research, via Cira's sourced statistics compilation](https://www.hicira.com/missed-call-statistics) — accessed 2026-08-27).

**One structural change worth flagging up front:** Synthflow, long cited as the leading no-code SMB voice-agent builder, has **withdrawn every self-serve tier and now sells only enterprise contracts starting at $30,000/year** ([synthflow.ai/pricing](https://synthflow.ai/pricing), accessed 2026-08-27). Any competitive analysis quoting Synthflow's old $29–$799 SMB plans is stale. See §5.3.

### 1.2 Feature matrix — packaged AI receptionists

Legend: ● = standard/included · ◐ = gated to a higher tier or an add-on · ○ = not offered / not found · ? = not verified

| Feature | Rosie | Goodcall | Dialzara | My AI Front Desk (Frontdesk) | Smith.ai (AI) | Slang.ai | Sameday | RingCentral AI Rcpt. | Ruby (human) |
|---|---|---|---|---|---|---|---|---|---|
| 24/7 answering | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Greeting / persona customisation | ● | ● | ● | ● | ◐ (custom prompting = Enterprise) | ● | ● | ● | ● |
| Custom voice selection | ● | ● | ● (50+ voices) | ● | ? | ● | ◐ (voice cloning higher tiers) | ● | n/a |
| Business hours / after-hours flow | ● | ● | ● | ● | ● | ● | ● | ● | ◐ |
| Appointment booking **in-call** | ◐ ($149 Scale+) | ● | ● | ● | ◐ (+$1.50/call) | ● (reservations) | ● | ● | ◐ |
| Calendar integrations | ◐ Google/Calendly/Acuity/Appointlet | ● Google Calendar | ● | ● (own AI Calendar; others via Zapier) | ● Calendly etc. | ● OpenTable/SevenRooms/Yelp | ● ServiceTitan/Jobber/Housecall Pro/Service Fusion/FieldRoutes | ● Google/Outlook | ● Calendly |
| Blind transfer | ◐ ($149+) | ● | ● | ● | ● | ● | ● | ● | ● |
| **Warm** transfer (AI briefs the human) | ◐ ($149+) | ? | ◐ ($99 Pro+) | ? | ● | ? | ● | ? | ● |
| Waterfall / multi-number escalation | ◐ ($299 Growth) | ? | ? | ? | ? | ? | ? | ? | ? |
| Voicemail / message taking | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Structured message scenarios | ● (2 / 5 / unlimited by tier) | ● (forms + logic flows) | ● (custom questions) | ● | ● | ● | ● | ● | ● |
| SMS to caller during call | ◐ ($149+) | ● | ● | ● | ◐ (+$0.50/call) | ● (order links) | ● | ● | ◐ |
| SMS/email notification to owner | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Spam / robocall screening | ● | ● | ● (+ allow/block lists) | ? | ● (20M+ known spam numbers) | ? | ? | ? | ● |
| Multi-language | ● EN/ES all plans | ● ~7 languages | ● 10+ w/ auto-detect | ● 20+ | ◐ bilingual +$1.00/call | ◐ EN/ES (+$99/mo bilingual) | ◐ higher tiers | ● 6+, switches mid-call | ● EN/ES |
| Knowledge base from **website scrape** | ● (website + Google Business Profile) | ● | ● (2-min setup from URL) | ● (KB pages, capped on free) | ? | ● | ? | ? | n/a |
| Document/file training | ◐ ($299 Growth) | ? | ● | ● | ◐ | ? | ? | ? | n/a |
| CRM integrations | ● Zapier (8,000+ apps) | ● Zapier (native in-app) | ● Zapier/Make | ● Zapier-first, no public API | ● 7,000+ via Zapier/Make + native (Salesforce, HubSpot, Clio) | ● POS/reservation | ● native FSM | ● Salesforce/HubSpot | ● Clio, Salesforce, HubSpot |
| Call recording | ● | ● | ● | ● | ◐ (+$0.25/call) | ● | ● | ● | ? |
| Transcripts | ● | ● | ● | ● | ● | ● | ● | ● | ○ |
| AI call summaries | ● | ● | ● | ● | ● | ● | ● | ● | ● (human notes) |
| Analytics dashboard | ● | ● | ● | ● | ● | ● (incl. on-site answer rate) | ● | ● | ● |
| Multi-location / multi-number | ◐ (Custom tier) | ● (per-location agents, one dashboard) | ● ($349 Elite) | ● | ◐ (Enterprise) | ● | ● | ● | ● |
| Human handoff to *staffed* agents | ○ AI-only | ○ AI-only | ○ AI-only | ○ AI-only | ● live NA agents | ○ | ○ | ○ | ● (all human) |
| Outbound calling | ◐ | ○ | ◐ (separate $750–$1,500/mo tiers) | ◐ (capped 2–20/day) | ◐ add-on | ○ (SMS only) | ● (review requests, CSAT) | ? | ◐ weekdays only |
| Payment / card capture | ○ | ○ | ○ | ○ (explicitly no payment processing) | ● (+$1.00/call) | ○ | ? | ? | ● |
| Website chat widget on same KB | ● | ? | ● ($39/mo or free w/ voice) | ● | ● | ? | ? | ● | ● (separate product) |
| Native mobile app for the owner | ● iOS + Android | ○ web only | ? | ? | ● | ? | ? | ● | ● |

**Sources for the matrix rows** (all accessed 2026-08-27):
- Rosie — vendor pricing page read directly: tiers $49 Professional / 250 min, $149 Scale / 1,000 min, $299 Growth / 2,000 min; Professional includes "Send appointment links by text", "Automatic spam detection", "Website chat widget"; Scale adds "Book appointments directly on your calendar", "Warm transfers – Rosie briefs your team before connecting", "Live call transfers", "Send texts to callers during the call"; Growth adds "Waterfall transfers – Rosie tries multiple numbers until someone answers" ([heyrosie.com/pricing](https://heyrosie.com/pricing)). Website + Google Business Profile training, EN/ES on every plan, Google Calendar/Calendly/Acuity/Appointlet booking, spam filtering, summaries and transcripts on every call ([Cekura review](https://www.cekura.ai/blogs/ai-answering-service); [Allo comparison](https://www.withallo.com/blog/best-bilingual-ai-receptionists)). Native iOS and Android app vs Goodcall's web-only dashboard ([Rosie's own comparison page](https://heyrosie.com/blog/rosie-ai-vs-goodcall) — vendor-authored, treat the competitor column with suspicion).
- Goodcall — vendor pricing page read directly: Starter/Growth/Scale with "Unlimited minutes and tokens", logic flows (1 / 3 / 25), team members (9 / 50), directory contacts, call & customer detail retention (7 days / 30 days / unlimited), unique-customer caps (100 / 250 / 500) with **$0.50 per customer over cap**, and Zapier "natively integrated within the Goodcall application" ([goodcall.com/pricing](https://www.goodcall.com/pricing)). Feature list — FAQ responses, lead capture, Google Calendar scheduling, spam/robocall filtering, transcripts and recordings, ~7 languages, self-service setup in minutes, began as Google's "CallJoy" ([Sonant review](https://www.sonant.ai/blog/goodcall-alternative-review)). Multi-location: separate AI receptionists per location with unique greetings, hours and routing from one dashboard ([Voksha guide](https://voksha.com/guide/best-ai-receptionists-2026)).
- Dialzara — vendor pricing and features pages read directly: $29 Lite (60 min, $0.48 overage) / $99 Pro (220 min, $0.45) / $199 Plus (500 min, $0.40) / $349 Elite (1,000 min, $0.35); **all plans include** a US phone number, call recordings, email/SMS notifications after each call, 50+ premium voices, call summaries, 24/7; blind transfer on Lite but **warm transfer only from $99 Pro**; multi-agent/multi-location on Elite ([dialzara.com/pricing](https://dialzara.com/pricing)). Features page: spam detection with behaviour-based screening plus manual allow/block lists, polite call-ending for unqualified callers, 10+ languages with auto-detect and bilingual greetings, caller memory, AI Configurator that builds the agent from a description ([dialzara.com/features](https://dialzara.com/features)). ~2-minute setup from a website URL, HIPAA-compliant claim ([dialzara.com comparison page](https://dialzara.com/compare/dialzara-vs-ringcentral) — vendor-authored).
- My AI Front Desk / Frontdesk — Free (20 voice min/mo, KB capped at 2 pages, 1 notification recipient, last 20 call logs), Business-in-a-Box $99/mo ($79 annual, 200 voice min, 100 chatbot conversations, 400 SMS), Partner/Enterprise custom; overage $0.25/min; outbound capped 2–20/day; 20+ languages; Zapier-first with no public API; **no payment processing**; own "AI Calendar" rather than direct Google sync ([serviceagent.ai breakdown citing myaifrontdesk.com/pricing](https://serviceagent.ai/blogs/front-desk-pricing); [Autocalls breakdown](https://autocalls.ai/article/my-ai-front-desk-pricing)). Note: sources disagree — CloudTalk reports a live $20/month Basic tier with a 7-day trial and no permanent free plan ([CloudTalk](https://www.cloudtalk.io/blog/my-ai-front-desk-pricing)), and getaira.io reports $64.99–$124.99 ([getaira.io](https://www.getaira.io/blog/ai-receptionist-pricing-guide)). **Treat Frontdesk pricing as unresolved.** Home-services integration hub documents ServiceTitan, Jobber, Workiz and Housecall Pro patterns via native calendar sync, webhooks and Zapier ([myaifrontdesk integrations hub, updated 2026-08-04](https://llms.myaifrontdesk.com/home-services-integrations)).
- Smith.ai — vendor pricing page read directly: Free (25 real calls/mo, $3.00 per extra call), Pro from $150/mo (75/150/300 calls at $2.00/$1.80/$1.67 each), Enterprise $500/$800/$1,000+ (300/500/1,000+ calls). Notably the plan table also meters **test calls** and **simulated calls** separately from real calls, and gates "Custom AI prompting", "Custom integrations" and "Full-service setup & optimization" to Enterprise only ([smith.ai/pricing/ai-receptionist](https://smith.ai/pricing/ai-receptionist)). **The per-call add-on menu is confirmed on Smith.ai's own pricing page** ([smith.ai/pricing](https://smith.ai/pricing)): call recording & transcription **$0.25/call**, dedicated Spanish line **$1.00/call**, conflict checks **$0.50/call**, accept collect calls **$0.50/call**, plus payment collection (supporting Square, PayPal, LawPay, TrialPay, CPACharge), third-party form input, and call routing rules per number/time-of-day/extension with sequential or simultaneous ring. Terms: month-to-month, no long-term contract, 30-day money-back up to $1,000 **excluding overage**. Note these add-ons are listed against the human Virtual Receptionist product; the AI Receptionist plan table is separate. CloudTalk additionally reports booking +$1.50/call and SMS +$0.50/call ([CloudTalk](https://www.cloudtalk.io/blog/my-ai-front-desk-pricing)) — those two specific line items were not visible on the page I read, so treat as unconfirmed.

  **The structural lesson for us:** Smith.ai monetises *recording and transcription* as a paid add-on. In the packaged-AI tier (Rosie, Dialzara, Goodcall) recording, transcript and summary are included on every plan. We should include them — charging for them reads as a managed-service convention, not an AI-product one. Spam: blocks 20M+ known spam numbers ([GetVoIP review](https://getvoip.com/blog/smith-ai-receptionist)). Human escalation to live North-America-based agents with context passed ([GetVoIP](https://getvoip.com/blog/smith-ai-receptionist)).
- Slang.ai — restaurant-vertical, **vendor pricing page read directly** ([slang.ai/pricing](https://www.slang.ai/pricing)): **Core from $379/location, Premium from $539/location** (the page also surfaces $399 and $599, i.e. annual vs monthly rates), Enterprise custom. Core includes end-to-end reservation management 24/7, **Direct SMS** (confirmations, ordering links, wine lists), **native CSAT capture on every call**, special-requests collection logged into OpenTable, and "User-Friendly Restaurant Prompts… without having to painstakingly train your AI". Premium adds custom branding, **reservation cross-selling to sister restaurants**, smarter routing, **missed-call capture** and priority support; Enterprise adds MFA/SSO. **Inbound voice only — outbound is SMS**; English and Spanish; reservations completed in OpenTable, SevenRooms and Yelp; **does not take phone orders**, it sends an SMS link to online ordering; measures on-site answer rate and analyses call recordings ([CloudTalk review verified against Slang's pricing page Aug 2026](https://www.cloudtalk.io/blog/slang-ai-review); [slang.ai comparison page](https://www.slang.ai/slang-ai-vs-yelp-host)). Bilingual +$99/mo and private events +$199/mo are reported by a competitor and were **not** visible on Slang's own pricing page ([AI Bunny](https://aibunny.tech/compare/aibunny-vs-slang-ai)) — treat as unconfirmed.
- Sameday — flat **$449–$789/month**, no per-minute meter, no contract; native booking into ServiceTitan plus Service Fusion, Jobber, FieldRoutes and Housecall Pro; outbound calls for CSAT and Google review requests; voice cloning and multilingual on higher tiers ([sameday.ai](https://sameday.ai/best-ai-receptionist-for-home-services); [Allo contractor comparison](https://www.withallo.com/blog/best-ai-receptionists-for-contractors)).
- RingCentral AI Receptionist — $59/mo for 100 minutes with $0.50/min overage billed in 30-second increments (per a competitor's page, so verify); multi-language including EN/ES/FR/IT/DE/PT with **mid-conversation language switching**; automatic recording and transcription on every call; SMS follow-ups with forms, instructions and links; per-location business hours, routing rules, greetings and SMS responses; CRM/scheduling/ecommerce connections ([ringcentral.com/ai-receptionist.html](https://www.ringcentral.com/ai-receptionist.html); pricing via [dialzara comparison](https://dialzara.com/compare/dialzara-vs-ringcentral)).
- Ruby — human, included as the price ceiling: $250/mo for 50 minutes, $395 for 100, $720 for 200, $1,725 for 500, overage rate unpublished, 3.0% credit-card fee, no free trial (21-day / 500-minute money-back guarantee); native Clio and Grasshopper, Salesforce/HubSpot, Calendly booking, and HIPAA mode rules Calendly out ([CloudTalk, verified on ruby.com 2026-08-24](https://www.cloudtalk.io/blog/ruby-receptionist-review)). Upfirst reports slightly different figures ($245/$385/$705/$1,695) ([upfirst.ai](https://upfirst.ai/blog/best-answering-services)) — a ~2% discrepancy, probably a pricing change between reads.

### 1.3 What is genuinely table stakes (you cannot sell without it)

Every packaged receptionist surveyed ships all of these. A product missing any one of them is not sellable to a general SMB:

1. **24/7 answering with unlimited concurrency.** Never a busy signal. This is the core promise — the human alternative cannot do it, and it is why the category exists.
2. **Custom greeting + business identity.** The AI opens with the business name.
3. **Business hours + a distinct after-hours behaviour.** 30–40% of inbound calls to local service businesses arrive after hours ([Magicline statistics compilation](https://www.magicline.ai/blog/ai-receptionist-statistics-2026)).
4. **Message taking with structured fields** — name, number, reason for calling — not a raw audio blob.
5. **Call transfer to a human** (blind at minimum).
6. **Owner notification the moment a call ends**, by SMS and/or email, containing the summary.
7. **Recording + transcript + AI summary of every call**, retrievable in a dashboard.
8. **Knowledge base built from the business's own website**, because no SMB owner will hand-author an FAQ.
9. **Keep the existing business number** via conditional call forwarding — nobody changes their number ([Trillet guide](https://trillet.ai/blogs/best-ai-receptionist-for-small-business-2026)).
10. **Spam/robocall screening.** Universal on the leaders and specifically called out as free/standard by Smith.ai, Goodcall, Rosie and Dialzara.
11. **Self-serve setup measured in minutes, not weeks.**

### 1.4 What is the 2026 competitive standard (leaders have it, laggards don't)

12. **In-call appointment booking into a real calendar** — not "we'll text you a booking link". This is now the sharpest dividing line in the category: Rosie explicitly gates it to $149 and OnCallClerk built an entire competitive campaign around that fact ([OnCallClerk](https://oncallclerk.com/compare/rosie-alternative), competitor-authored but the underlying Rosie tier gating is confirmed on Rosie's own pricing page).
13. **Warm transfer** — the AI briefs the human before connecting. Rosie ($149+), Dialzara ($99+), Smith.ai, Sameday and Synthflow (which ships three distinct transfer modes including an AI-generated summary whispered to the human, per [CloudTalk's Synthflow review](https://www.cloudtalk.io/blog/synthflow-ai-review)).
14. **Bilingual EN/ES minimum, auto-detected**, ideally with mid-call switching.
15. **SMS to the caller during or right after the call** (booking links, addresses, forms).
16. **Zapier/Make as the integration backstop** plus native connectors for the vertical that matters.
17. **Vertical-native booking** where the vertical has a system of record: ServiceTitan/Jobber/Housecall Pro for trades, OpenTable/SevenRooms for restaurants, Clio for legal. The trades buyers' guides are blunt that "taking a message is not the same as booking a job" and that Zapier hand-offs you have to re-key don't count ([NextPhone HVAC guide](https://www.getnextphone.com/blog/best-virtual-receptionist-for-hvac); [sameday.ai](https://sameday.ai/best-ai-receptionist-for-home-services)).
18. **Analytics beyond a call list** — volume, outcomes, peak hours, booking conversion, and ideally answer-rate/missed-call-recovery framing.
19. **Multi-location / multi-agent from one dashboard.**
20. **Caller memory** — recognising a repeat caller and their history. Only Avoca, Allo and Dialzara were found to offer this ([Allo](https://www.withallo.com/blog/best-ai-receptionists-for-contractors); [dialzara.com/features](https://dialzara.com/features)). This is a genuine differentiator, not table stakes, in 2026.

### 1.5 Google has left the field — and that matters

Worth recording because it removes the one "free, bundled, from the platform everyone already uses" threat to this category:

- **Google Business Profile call history and chat were discontinued on 31 July 2024.** Google's own support page: *"As of July 31, 2024, the chat and call history features are no longer available in your Business Profile."* Customers could no longer start chats from 15 July 2024, data was downloadable via Takeout only until 30 August 2024, quote requests were removed, and the `BUSINESS_CONVERSATIONS` metric was dropped from the Performance API ([Google Business Profile Help](https://support.google.com/business/answer/14919056?hl=en) — accessed 2026-08-27).
- **The My Business Q&A API was discontinued on 3 November 2025**, replaced by AI-generated contextual answers drawn from the business's website, reviews and description ([Google for Developers change log](https://developers.google.com/my-business/content/qanda/change-log)).
- **Goodcall is the residue of Google's effort here** — it began life as Google's "CallJoy" and is now independent ([Sonant](https://www.sonant.ai/blog/goodcall-alternative-review)).

Net effect: Google now *sends* calls to SMBs but gives them no tooling to answer, log or analyse those calls. Third-party call tracking and answering has become more necessary, not less. That is our tailwind.

### 1.6 What is NOT standard (safe to omit, or a deliberate wedge)

- **Payment / card capture over the phone.** Notably rare. Smith.ai offers it as a paid add-on; My AI Front Desk explicitly does not process payments. This is almost certainly because of the PCI burden (see §3).
- **Outbound calling.** Usually a separate product and a separate price (Dialzara $750–$1,500/mo tiers; Frontdesk caps outbound at 2–20/day; Slang.ai does not do outbound voice at all). Inbound receptionist and outbound campaign are different products with different compliance profiles.
- **Human fallback agents.** Only the managed/hybrid layer (Smith.ai, Ruby, AnswerConnect) has this. Pure-AI vendors uniformly do not.
- **On-call/emergency routing sophistication** beyond a single transfer number.
- **Native mobile app.** Rosie, Smith.ai and RingCentral have one; most competitors are web-only.

### 1.7 Documented failure modes — where these products actually break

Useful because these are the complaints our product will also receive, and several map straight to checklist items.

- **Weak escalation is the top caller complaint.** A tester citing a Trustpilot review of Goodcall describes a caller "pushed through sales style prompts" who "struggled to reach a real person"; the same review notes Goodcall's Starter tier keeps only **7 days of call history**, "very limited for reporting or going back to check on a dispute from two weeks ago" ([Lunacal](https://lunacal.ai/blogs/ai-receptionist) — accessed 2026-08-27). **An always-available path to a human, and retention long enough to settle a dispute, are not optional.**
- **Emotional and sensitive calls.** AI "may struggle with highly emotional callers — someone in distress, an angry customer, or a sensitive medical situation… it does not replicate genuine human empathy." Recommended practice is explicit escalation rules that transfer emotional calls to a human quickly ([Voksha](https://voksha.com/guide/what-is-an-ai-receptionist)).
- **Accents, poor cell signal and background noise** degrade recognition even at 95–98% nominal ASR accuracy (same source) — consistent with the WER benchmark data in §4.6.
- **Specialised knowledge.** The agent should capture and route deep legal/medical/financial questions, not attempt them (same source).
- **Caller resistance is real but declining**, and concentrated in older demographics (same source). Related: the share of consumers saying AI made their buying experience *worse* fell from 29% in 2025 to 18% in 2026, while 46% now say it made it better ([Invoca B2C Buyer Experience Report 2026, via Cira](https://www.hicira.com/missed-call-statistics)).
- **Latency directly drives abandonment.** One operator running AI receptionists for six months reported that cutting response delay lifted the share of callers who stayed on the line from **~72% to ~91%** — reported honestly by the source as "one shop's numbers, not a guarantee yours will match" ([Marblism](https://www.marblism.com/blog/best-ai-receptionist)). Treat as anecdote, but the direction matches every latency source in §4.
- **Two structural gaps across the whole category**, per a reviewer who tested ten tools: they handle only the phone channel, and **"they start every call from scratch. No memory of who called before"** ([Vellum](https://www.vellum.ai/blog/best-ai-receptionist-for-small-business)). This is why caller memory (§1.4, item 20) is the sharpest available differentiator.

---

## 2. DASHBOARD STANDARD

The dashboard is where a packaged AI receptionist earns its price. The voice agent is increasingly a commodity — ConversationRelay, Retell and Vapi all reach the same latency band — so what an SMB owner actually buys is **the ability to see what happened on the phone and change what happens next, without calling support.**

Vendors surveyed by reading their **help centres, product docs and app-store listings directly** (not review blogs): Rosie, Goodcall, Smith.ai, My AI Front Desk / "Frontdesk", Dialzara, Ruby, Slang.ai, RingCentral AI Receptionist (AIR), Avoca, Signpost, Podium, Sameday, Loman, Abby Connect, Numa, Nexa — plus the four developer platforms that set the technical ceiling (Synthflow, Retell, Vapi, Bland).

### 2.0 A structural finding that shapes everything below

**The category splits in half on whether it documents its own product at all.**

| Publishes real operational docs | Demo-gated — dashboard claims are marketing-derived only |
|---|---|
| Rosie, Goodcall, Smith.ai, Frontdesk, RingCentral AIR, Avoca, Signpost; Dialzara and Ruby (thin) | **Slang.ai** (support is a ticket form), **Loman** (best doc is a *partner's* KB), **Sameday** (email-only), **Numa**, **Nexa**, **Podium** (KB is JS-gated and unreadable) |

**Frontdesk publishes the most complete public spec of an SMB AI-receptionist dashboard in existence** — roughly 90 help articles describing individual buttons and modals ([Frontdesk Help Center](https://www.myaifrontdesk.com/help)). **RingCentral AIR** is the most complete enterprise-grade spec. **Avoca** is the deepest *operator* dashboard and publishes a full doc site with an `llms.txt` index despite having no public pricing ([help.avoca.ai](https://help.avoca.ai)).

Two consequences. First, **for the demo-gated half, every claim below is marketing-derived — their real screens may be materially richer or poorer.** Second, publishing real docs is itself a competitive signal: it is what lets a buyer self-qualify, and it is cheap for us to do.

### 2.1 The nine panels of a standard owner dashboard

**1. Call log — the home screen.** Date/time, caller ID, duration, outcome, with **audio playback, full transcript and AI summary on every call**. Universal in the documented tier. Rosie's terms state the data model outright: "Recordings and Transcripts are posted to your Account and available to you on your Dashboard" ([Rosie ToS](https://heyrosie.com/legal/terms)).

**Frontdesk sets the SMB ceiling.** Per call: audio player, chat-style transcript (AI left, caller right), summary, a **1–5 star call score with a written explanation**, a **sentiment breakdown as % positive/neutral/negative**, a **Pricing Details tab showing that call's cost**, and up to three owner-defined **Smart Call Analysis** scenarios extracting structured output as Text, JSON, Boolean or Number. Plus the boring things done well: search by phone/name/content, date-range filter, "Hide empty calls" toggle, red-dot unread with **Mark All Read**, **Share Call Log** link, and **Download → Select Columns** CSV export ([Call Logs](https://www.myaifrontdesk.com/help/calls-and-logs/call-logs)).

**Transcript search is rarer than you'd expect.** Smith.ai ships it explicitly ([Call Recording & Transcription](https://docs.smith.ai/article/fzv1b69n7t-call-recording-transcription-with-smith-ai)) and has the most structured call record of the hybrid set: **Status** (New Lead / Existing Client / Repeat / Attorney-Court Staff / Unknown), **Disposition** (Business / Personal / Wrong Number / Spam / Sales), **Priority**, plus an "Actions Taken" pie chart ([Using the Call Dashboard](https://docs.smith.ai/article/n40myw0flr-using-and-accessing-the-smith-ai-call-dashboard)).

**Retention is a live differentiator nobody advertises.** Smith.ai keeps recordings and transcripts **90 days** then you must download ([link](https://docs.smith.ai/article/fzv1b69n7t-call-recording-transcription-with-smith-ai)). Goodcall gates it: **7 / 30 / unlimited days by plan** ([goodcall.com/pricing](https://www.goodcall.com/pricing)). **Dialzara is the only vendor that lets the owner choose** — "Each customer controls their own retention window from the dashboard — common settings are 30, 90, or 365 days" ([dialzara.com/faqs](https://dialzara.com/faqs)).

**Owner-applied tagging is the weakest common link.** Real tags: Smith.ai, Signpost ("tagged with custom tags to easily sort and filter by call outcome" — [help.signpost.com](https://help.signpost.com/messaging-hub-full-guide)), Slang.ai Smart Tags, Abby. Rosie tags only automatically (a SPAM call-type tag). RingCentral's statuses are system-generated only.

**2. Message / lead inbox.** The AI always captures name, phone and reason; the owner adds business-specific questions. **How that's authored splits the field into four models:**

- **Free-text brief (Rosie).** Message Scenarios take a name plus a **≤500-character plain-language briefing** — "The brief is not a question list. Think of it like a quick note to a new receptionist" — with a **Suggest a Briefing** button, and a fallback to name + phone + reason if no scenario matches. Limits 2 / 5 / unlimited by plan ([Message Scenarios](https://heyrosie.com/support/en/articles/15171354-message-scenarios-have-rosie-collect-the-right-info-from-every-caller)).
- **Checkbox form (Smith.ai).** Always collects Full name, Reason, Best contact number; optional checkboxes add Email, Source, Business name, City & State; then **up to three custom labelled fields per caller type** ([Configure Caller Types](https://smithaivoiceassistant.freshdesk.com/support/solutions/articles/151000199808-how-to-configure-caller-types)).
- **Question-list workflow (Frontdesk).** Intake Forms feeding a response table rendering **one column per question, one row per submission**, with a *View full conversation* link ([Intake Form Responses](https://www.myaifrontdesk.com/help/calls-and-logs/intake-form-responses)).
- **Questionnaire with timing control (RingCentral).** Two questionnaires (new vs returning), ≤5 questions each, plus a **Capture options** setting — *Before transfer*, *At a natural break*, or *After greeting* — results in a **Leads tab** ([Using Lead capture](https://support.ringcentral.com/article-v2/using-lead-capture-with-the-ai-receptionist.html)).

**Read/unread and assignment is genuinely rare** — Frontdesk (unread dots, Mark All Read), Avoca ("Find, **assign**, reply to, and **resolve** customer conversations"), Podium (auto-assign + escalation rules). Most vendors treat the inbox as a read-only log. **Export** is confirmed for Frontdesk, Smith.ai, Avoca and Numa; **not verified for Rosie, Goodcall or Slang.ai** — Goodcall's practical export is the Zapier payload.

**3. Greeting, persona and instructions editor — the biggest architectural split in the category.** Four models, and picking one is the most consequential product decision here:

- **(i) Pure form, no prompt (Smith.ai).** The greeting is not even free text — "You will see a list of **three greeting options**. Make your selection and click Save" ([How To Change Your Greeting](https://smithaivoiceassistant.freshdesk.com/support/solutions/articles/151000199594-how-to-change-your-greeting)). Voice is a dropdown of 10, account-wide; "we do not support voice cloning or uploading audio files at this time."
- **(ii) Skills form + visual flow builder (Goodcall).** A table of **Skills**, each with a trigger phrase and configurable Action — "Clicking any skill… will open a form where you can change the configuration… **and see a sample of how the conversation might go**" ([Knowledge: skills and actions](https://help.goodcall.com/en/articles/8007519-knowledge-skills-and-actions)). Its greeting guidance is worth stealing: **20 words or less** ([Optimize Your Greeting](https://help.goodcall.com/en/articles/8007541-how-to-optimize-your-greeting)). On top sits **Flows → Logic** branching.
- **(iii) Free-text prompt (Frontdesk, Dialzara).** Frontdesk's **Custom Commands** has **separate voice and text prompts**, and its Greeting field **warns you above 15 words** because "75% of callers hang up when the greeting is too long" ([Greeting Phrase](https://www.myaifrontdesk.com/help/ai-receptionist/greeting-phrase)). Dialzara goes furthest: the **Training Guide "functions as the system prompt", is auto-drafted from your website to ~90% of a functional agent, uses Markdown, and refinements are "immediately live once updated"** ([Customizing your training guide](https://guide.dialzara.com/en/article/customizing-your-ai-receptionists-training-guide-1m12km2)).
- **(iv) Guided wizard (RingCentral).** Profile → description → greeting, with **voice preview per language**. The cost of the form model is documented in RingCentral's own community: an admin asks how to write "If a conversation takes more than 5 minutes, transfer to a live agent", a moderator escalates rather than answers, and another user writes "Six months since this feature launched and we don't have basic fundamental prompting capabilities" ([community.ringcentral.com](https://community.ringcentral.com/ace-air-air-pro-air-pro-ava-19/ai-receptionist-knowledge-base-uses-and-limitations-10715)).

**4. Knowledge base.** Website and/or Google Business Profile scraping is now the expected first screen (see §2.3). Rosie names two Training Sources and is unusually explicit about what a retrain **overwrites** — "Business Name, Business Address, Business Phone, Business Email, Default Business Overview, Services, **Business Hours**, Service Areas" — with FAQs capped at **20** and nothing live until you hit **Publish** ([Business Information](https://heyrosie.com/support/en/articles/13722191-business-information-setting-up-your-agent)). **Frontdesk's crawler is the most controllable**: crawl a URL, **select which pages to include**, set an **auto-sync schedule**, plus Add Text (100,000 chars) and Q&A pairs ([Knowledge Base](https://www.myaifrontdesk.com/help/ai-receptionist/knowledge-base)). Goodcall takes PDFs ≤10MB and draws the line between systems crisply — "'What are your business hours?' → Answered via **Documents**; 'Can you text me your price list?' → Action handled via **Skills**" ([Documents feature](https://help.goodcall.com/en/articles/12523771-how-to-use-the-documents-feature-in-goodcall)).

> **The genuine differentiator is the learning loop — and only three vendors close it.**
> - **Smith.ai self-healing FAQs:** an unanswerable question is logged as a knowledge gap and becomes a **suggested FAQ**, surfaced in-dashboard **and in a daily email**, showing the question, **how often it has come up**, and three actions — *Add*, *View example call*, *Dismiss* ([Set Up and Manage FAQs](https://smithaivoiceassistant.freshdesk.com/support/solutions/articles/151000199592-how-to-set-up-and-manage-frequently-asked-questions-faqs-)).
> - **RingCentral Conversational Insights:** an *Unresolved Questions* tab "ranked by how often each was asked but unanswered"; type an answer and it saves to the FAQ skill, with **assign-to-multiple-receptionists** ([link](https://support.ringcentral.com/article-v2/managing-ai-receptionist-conversational-insights-in-the-admin-portal.html)).
> - **Goodcall Teachable Topics:** "**identifying questions that stump the agent during calls**… presented as a list of these teachable moments **within the performance tab**" ([link](https://help.goodcall.com/en/articles/8570709-expanding-knowledge-with-teachable-topics)).
>
> Podium has a lighter version worth copying: hover a "Source" in an AI message to see where the answer came from, and "In the instance where a configured FAQ is incorrect or outdated, **you can click it directly to edit it**" ([Podium](https://www.podium.com/whats-new/ai-employee-sources)).

**5. Hours, holidays, timezone — the most under-built capability in the entire category.**

The reference implementation is **Smith.ai's Availability page**: business timezone, standard hours/days, "**the holidays where you and your team members are available or unavailable**", out-of-office/vacation, **per-team-member schedules that override the default**, and lunch breaks. The behavioural contract is documented — "Outside of working hours… your after-hours instructions will be followed, **and no transfers will be attempted**" — plus a lovely touch: "If your office is marked 'available' for any federal holiday, our system will send an **automated message to you a few days before the holiday**, in case you forgot" ([Availability and Work Schedule](https://docs.smith.ai/article/y2ep35f8tx-availability-and-work-schedule)).

**Goodcall solves holidays by not owning them**: "If you have your business listed on Google or Yelp, it can **import the special hours for holidays**… The data refresh is done at **1am Eastern time daily**" — with the trade-off stated honestly: "**Updating the open hours must be done in the appropriate platform, not in Goodcall**" ([Open Hours](https://help.goodcall.com/en/articles/8007536-teach-your-ai-agent-how-to-manage-open-hours)).

**Avoca treats holidays as behavioural exceptions, not a closed message** — timezone is an explicit KB field that "Controls hours, transfer windows, date reasoning", and Holidays carry **booking and transfer configuration, an emergency-only booking mode, and fee overrides** ([Configure fees and holidays](https://help.avoca.ai/How-to-set-up-Fees-and-Rulesets-2cef2b56d4d580d0965ccc9461c3a949)).

> **Frontdesk is the cautionary tale: it has no first-class business-hours object at all.** Its documented setup checklist covers Greeting, Custom Commands, Business Information, Common Questions, Languages, Voice and In-Call Actions — **hours are not on the list** ([Setup Wizard](https://www.myaifrontdesk.com/help/getting-started/setup-wizard)). Three partial substitutes exist instead: hours as KB text, **Time Control** transfer windows, and per-workflow availability. **No holiday override is documented anywhere.** Rosie sits mid-field — per-day hours and "mark specific days as closed", but **holiday overrides and an explicit timezone control are not verified**.
>
> **Even the developer platforms punt.** Of Synthflow, Retell, Vapi and Bland, **only Synthflow has a real Business Hours panel** (hours "always evaluated in the agent's own timezone, never the caller's", two windows per day, three out-of-hours fallbacks) — and it still has **no holiday feature** ([Synthflow Business Hours](https://docs.synthflow.ai/business-hours)). Retell's community answer is to build it yourself. Vapi's community shows the prompt-variable approach failing live: "**Offering Live Transfers outside of business hours**… Even when I apply hard constraints on this, it's still offering live transfers outside of Business Hours" ([Vapi community](https://vapi.ai/community/m/1450943986352259144)). **This is real, uncontested whitespace.**

**6. Transfer and routing rules.** Warm vs cold is the universal axis, and it is very often a paywall.

**Rosie names three and explains what happens on the line.** **Cold** ("Rosie is gone the moment she hands off… If your voicemail picks up, that counts as a completed transfer"); **Warm** — caller goes on hold with music while Rosie calls you and says "I have Sarah Chen on the line. They are calling about a leak under their kitchen sink. Would you like to take this call?", answered out loud, "no keypad prompt and nothing to press"; **Waterfall** — "an ordered list of up to five", 30 seconds each, checking back with the caller between attempts. Two operational details worth copying: "Rosie makes **one transfer attempt per call** — if it fails, she offers to take a message", and "Rosie dials your team from one dedicated number. **Save it in your contacts**… if anyone has *Silence Unknown Callers* turned on, an unsaved number goes straight to voicemail without ever ringing" ([Call Transfers](https://heyrosie.com/support/en/articles/16548766-call-transfers-cold-warm-and-waterfall)). Pricing maps directly: warm at $149, **waterfall requires $299**.

**Frontdesk has the richest escalation mechanics of the SMB set**: a **whisper handoff** that is *Auto-generate (AI summarizes)*, a *Custom AI Prompt*, or *None*; **Backup Numbers** dialled serially; **Blast Call Numbers** dialled in parallel where "the first person to answer is connected. The other calls are automatically canceled"; a custom ringing tone; and **Continue AI After Failed Call Transfer** — "the AI receptionist resumes the conversation with the caller instead of ending the call". Plus **Bypass To Human Numbers** for VIPs ([Call Transfer Workflows](https://www.myaifrontdesk.com/help/ai-receptionist/call-transfers), [Advanced Settings](https://www.myaifrontdesk.com/help/ai-receptionist/advanced-settings)).

**Smith.ai routes by caller type**, with two rules worth stealing: a warning — "DO NOT use a number that is or that you plan to use for forwarding to your business number. **This will cause an infinite loop**" ([link](https://smithaivoiceassistant.freshdesk.com/support/solutions/articles/151000199557-how-to-set-up-a-transfer-destination)) — and an explicit graceful-failure contract: the AI will **always** convey that the recipient is unavailable before taking a message, whatever the failure mode ([link](https://smithaivoiceassistant.freshdesk.com/support/solutions/articles/151000228642-configuring-transfer-connection-method)). Its Smart Team Directory adds a nice privacy rule: "**never confirm whether someone is on your team if their name isn't recognized**".

**Avoca sets the operator ceiling**: each destination is an object with internal name, extension, customer-facing message, transfer reasons and agent guidance, **its own schedule, timezone and holiday behaviour**, warm behaviour, **which agents may use it**, and **post-call email recipients** — plus **Pre-call Transfer Rules** that divert before the AI engages, and an **On-Call Calendar** with emergency broadcast and ServiceTitan shift sync ([Configure call transfers](https://help.avoca.ai/responder/transfers), [On-Call Calendar](https://help.avoca.ai/business-info/on-call-calendar)).

**RingCentral's distinctive addition is a rule-quality linter** — transfer rules get flagged *Needs clarity* or *Needs attention*, and the edit dialog offers a **Suggested rewrite** you can *Apply* or *Change back* ([Managing skills](https://support.ringcentral.com/article-v2/managing-skills-for-the-ai-receptionist-in-the-admin-portal.html)).

**7. Notifications.** Rosie is the minimum viable version (Account → Contact Information → toggle email/SMS). **Frontdesk defines the ceiling and is worth copying almost verbatim**: every notification is a triple — **Type × Method × Recipients** — where Type is Call, Voicemail, Text, Robocall, Chatbot, Calendar, **Scenario** (a custom plain-language scenario like "VIP Caller" or "After-Hours Emergency"), or Intake. Per-notification you toggle exactly what the payload contains — **Show Transcript, Show Call Summary, Show Intake Forms, Show Workflow, Show Call Info Link** — **preview the email or SMS before saving**, and suppress empty/short calls. There is also a **Sent Notifications History** log ([Notification Settings](https://www.myaifrontdesk.com/help/notifications/settings)).

**Smith.ai's contribution is routing by caller type** — new-lead summaries to sales, existing-client summaries to service, with a **Configuration overview table** showing every custom route ([link](https://smithaivoiceassistant.freshdesk.com/support/solutions/articles/151000199599-how-to-update-your-notification-settings)). **RingCentral caps and links sensibly**: up to **10 recipients**, and "All email recipients of usage limit alerts will also receive the **lead notifications**" ([link](https://support.ringcentral.com/article-v2/managing-spam-detection-and-usage-alert-settings-in-ai-receptionist.html)). Vertical players add **topic alerts** — Slang.ai routes "lost item or a customer complaint" straight to a manager's phone; Avoca routes **Microsoft Teams webhooks by service area**.

Notably, **the developer platforms are worse at this than SMB products**: Synthflow's Notifications page is product-updates-only, and Retell states plainly that alerting "isn't built for reacting to a single call or chat" ([Retell](https://docs.retellai.com/features/alerting-overview)).

**8. Number provisioning and forwarding.** **Frontdesk is the only vendor that has genuinely productised this.** In-app purchase ("Enter your preferred 3-digit area code, then click **Fetch Numbers**… or **Get Random Number**"), then a forwarding wizard: pick iPhone / Android / Landline / VoIP, then your carrier from ~18 mobile carriers or ~12 VoIP providers, then **Instant Setup — scan a QR code with your phone camera** or Manual. The warning is appropriately loud: "**Scanning the QR code will immediately forward all calls from the registered number on that device**". A **Make A Call** button verifies it ([Call Forwarding](https://www.myaifrontdesk.com/help/settings/call-forwarding), [Phone Numbers](https://www.myaifrontdesk.com/help/settings/phone-numbers)).

Rosie publishes the same content as an article and teaches the concept first — unconditional vs conditional (**busy / no answer / unreachable**), with "If you want Rosie to handle **more than one condition**… you'll need to set each one up **separately**", per-carrier codes, and a genuinely useful gotcha: "**iPhone Users: Turn Off Live Voicemail** — This feature can prevent Rosie from receiving forwarded calls" ([Set-up call forwarding](https://heyrosie.com/support/en/articles/11058354-get-rosie-to-answer-your-calls-set-up-call-forwarding)). Rosie numbers are **US-only**. Signpost's ~35-provider page is the volume benchmark.

**Goodcall documents the trap everyone else omits** — "Call forwarding creates a **call loop** between your phone provider and Goodcall, however **conditional** call forwarding will ring your store first" ([link](https://help.goodcall.com/en/articles/8007555-can-i-set-up-my-current-phone-to-forward-to-goodcall)) — and offers a second adoption path with a clever marketing tip: publish the Goodcall number on Google, Facebook, Yelp and Wix, using "**different Goodcall phone numbers on each platform** to track call volume based on platform".

**Porting is a real dividing line.** Goodcall: "**we do not support porting your number into Goodcall**". Dialzara: free porting, or buy US local $3 / toll-free $5. Smith.ai and RingCentral support it. Slang.ai makes it a human onboarding step.

**9. Usage, billing and analytics.** See §2.2.

**Beyond the nine — differentiators only leaders have:**
- **Native mobile app that configures, not just views.** Only **Rosie** documents "**Full Configuration — Train and customize your AI receptionist directly from your phone – no computer required.** Configure appointment scheduling, FAQ management, call transfers", plus unified inbox with swipe actions, push alerts, **Team Management with role-based permissions**, and a guided mobile Quick Start ([App Store](https://apps.apple.com/us/app/rosie-ai-business-receptionist/id6757593086)) — free on every plan.
- **Granular roles including a client-safe read-only tier.** Goodcall's **Admin / Editor / Performance Viewer** plus per-agent access control, pitched explicitly at agencies: "give your clients access to their agent's performance **without giving them access to everything 'under the hood'**" ([Team Management](https://help.goodcall.com/en/articles/9730780-how-to-use-enhanced-team-management-in-goodcall-gen-3)). Frontdesk adds **custom roles + unlimited Viewer seats once you hit the edit-seat cap** ([link](https://www.myaifrontdesk.com/help/settings/team-management)).
- **Caller memory** across calls (Dialzara, Avoca, Allo) — see §1.4.

### 2.2 Analytics, usage and billing

**Analytics has the widest quality spread of any capability, and several respected vendors have essentially nothing.** **Rosie has no analytics dashboard documented anywhere in its help centre** — treat it as call-log-and-notifications. Signpost gates it as a marketing tier without naming a single metric. Sameday lists "advanced data analytics" as Enterprise-only.

**Frontdesk has the most charts:** three tabs, four KPI cards (Total Calls, Avg Duration, Unique Callers, Text Messages), seven charts including **Peak Hours, Hourly Distribution, Duration Distribution and a yearly heatmap with drill-down**, an **Export Custom Report → branded PDF**, and a **chart builder over CRM variables** where "every field your receptionist collects… can be visualized" ([Analytics Dashboard](https://www.myaifrontdesk.com/help/analytics/dashboard), [Customer Insights](https://www.myaifrontdesk.com/help/analytics/customer-insights)).

**RingCentral has the most *useful* metrics — this is the model to beat.** Calls handled splits **Total / Resolved / Unresolved**, where resolved means "managed fully by the AI Receptionist" and unresolved means "dropped or when AIR couldn't provide an answer", with drill-down to transcripts. Then two things almost nobody has: **Resolved by transfer**, showing "whether the transfer was made by the caller requesting a specific person, or if AIR was able to transfer the call **based on the context**"; and **Top unresolved questions** — "the three most common questions AIR didn't resolve, along with how many times each was asked" — linking into Conversational Insights so you can answer them ([Intro to AI Receptionist Analytics](https://support.ringcentral.com/article-v2/intro-to-ai-receptionist-analytics.html)). Note **sentiment is not in AIR Analytics**. Goodcall's framing is the same idea headlined differently: "Track **automation rates**… while diving deep into **intent and outcomes**".

**Webex adds the interpretive layer** — it reports transfer rate *and transfer success rate*, then tells the admin what a bad number means: "a low intent-transfer rate may indicate that intents need clearer descriptions, while a low transfer success rate may indicate that transfer destinations, operating hours, or routing configuration need review" ([Webex Help](https://help.webex.com/en-us/article/4chov0/AI-Receptionist-in-Webex-Calling)). **Prescriptive beats descriptive, and it is cheap to build.**

**Avoca is the only vendor that closes the loop from analytics to revenue and to action**: a **Custom Analytics builder**, **Revenue Analytics with Avoca attribution**, Survey/CSAT, **Drop-off Analysis** ("Find where callers leave the Responder journey"), a Portfolio dashboard across brands, a Coach layer scoring booking rate and sentiment against rubrics — and crucially **missed-call recovery as a workflow, not a chart**: "Prioritize missed booking opportunities, **create follow-up tasks, assign the work, and track verified recovery outcomes**" ([help.avoca.ai](https://help.avoca.ai/llms.txt), [Coach overview](https://help.avoca.ai/coach/overview)).

**Outcome metrics beat volume metrics, and vertical outcome metrics beat generic ones.** Jobber's dashboard has an **Outcomes card** visualising "the work created by your Receptionist, including jobs, requests, and tasks" plus a **Time saved** card ([Jobber Help](https://help.getjobber.com/en/articles/receptionistpowered-by-jobber-ai)). Slang.ai reports covers, reservations, **native CSAT on every call** and a **Reservation Insights dashboard with OpenTable revenue attribution** — plus **on-site answer rate**, measuring how well the *human* team answers. Numa's own buyer's guide states the standard bluntly: an AI platform "that tells you how many calls it answered but can't tell you how many of those calls **converted to appointments**… is **a call log with a chatbot on top**" ([numa.com](https://numa.com/blog/ai-customer-operations-software-dealerships-buyers-guide)).

**Usage and billing is weak nearly everywhere, and two vendors show how to fix it.** **RingCentral puts the meter where the owner already is**: "**The exact number of minutes used can be found at the top of the Analytics page**", with a Jan-2026 summary showing "how many minutes you've used, how many are left, and where those minutes came from… **avoid surprise charges**" ([Jan 2026 blog](https://www.ringcentral.com/us/en/blog/ai-receptionist-easier-setup-smarter-conversations)). **Frontdesk runs a full credit ledger**: Free vs Purchased credits ("never expire"), per-feature progress bars with a three-state badge — **green "X left" / amber "Running low" at ≥80% / red "Used up"** — **Auto-Reload** with trigger and target, plus a **Max Usage Limit** in minutes emailing you at **50%, 75%, 100%** ([Credits & Usage](https://www.myaifrontdesk.com/help/billing/credits)).

**Goodcall's unique-customer model is a deliberate contrarian bet**: "We **DO NOT** charge any fees for number of calls, call minutes, or tokens… '**unique customers**' served… more closely aligns with the value your agent brings" — robocalls, blocked and silent callers don't count; $0.50 per overage customer. The hidden cost is **retention tied to the same tiers**, plus a dormancy rule: no calls in 60 days triggers **account deactivation** ([goodcall.com/pricing](https://www.goodcall.com/pricing), [FAQ](https://help.goodcall.com/en/collections/4196154-faq)).

> **A hard spend cap is essentially absent from the entire category.** Among every vendor reviewed, only **Bland** ships one — "Monitor your daily/hourly caps. **Hitting limits means calls get rejected rather than incurring unexpected charges**" ([Bland Billing](https://docs.bland.ai/platform/billing)) — while Synthflow states the opposite explicitly: "Billing thresholds are **triggers, not spending caps**… not a hard usage limit" ([Synthflow](https://docs.synthflow.ai/usage)). Rosie compounds this by auto-upgrading tiers with no cap (§5.2). **This is uncontested whitespace and a genuine trust feature.**

Two billing footnotes: **test calls may consume billable minutes** (RingCentral warns "test calls count towards your monthly minutes"), whereas Smith.ai meters test and simulated calls as *separate* entitlements — the better design.

### 2.3 Onboarding — the under-15-minute standard

**The dominant pattern: "give us your website URL or Google Business Profile and we build the agent."** Confirmed from vendors' own pages for at least five:

**Rosie — three steps** ([heyrosie.com](https://heyrosie.com)): "**Step 1** Add your site or Google Business Profile to train Rosie. Rosie automatically learns your business' hours, services, and basic information in seconds. **Step 2** Review and customize your information… **then give Rosie a call to test her responses and accuracy**. **Step 3** Start sending your calls to Rosie."

**RingCentral** — "Under **Add your business details**, select one of the following: **Website** — enter your company website's URL; **Google Business Profile** — enter your company's name…", with a **Set up manually** escape hatch ([setup article](https://support.ringcentral.com/article-v2/setting-up-your-ai-receptionist-in-the-admin-portal.html)).

**Dialzara** — "Create an account then add your website. **We'll tackle the hard part by automatically transforming the details you provide into a customized prompt**", then choose a voice and number, then add knowledge, then go live ([dialzara.com](https://dialzara.com)).

**Goodcall** — "as simple as connecting **Google listing, a website, or even just providing a few basic details**… **We never gate features behind lead forms and you'll never have to wait on us to make a change**" ([goodcall.com](https://www.goodcall.com)).

**Frontdesk** — "Enter your website URL or describe your business, and our AI builds your receptionist automatically", landing on a dashboard with a **completion-tracked setup checklist** ("Completed X/Y", each item badged Required / Recommended / Optional / Advanced), a **Playground**, and logs ([Setup Wizard](https://www.myaifrontdesk.com/help/getting-started/setup-wizard)).

**IONOS documents the wizard most rigorously**, including a hard gate: automated scraping ("approximately 2 to 3 minutes to crawl and map your site", with an "I don't have a website" bypass), then **Step 5: mandatory voice activation test** — *"Before your AI Receptionist can go live, you must complete a voice verification test… deployment remains locked until a test call is successfully placed."* Documented scenarios include hours/location, an appointment inquiry, an SMS summary request, and **triggering a live transfer to verify the escalation line**. It is also honest about scraper limits: it "cannot read text trapped inside flat images, PDFs (like uploaded paper menus), or highly dynamic third-party scripts" ([IONOS Help](https://www.ionos.com/help/ai/general-information/setting-up-your-ai-receptionist)).

**Test-and-simulate before go-live is now a documented standard, and Smith.ai and Avoca set the bar.**

- **Smith.ai Quality Studio** is best-in-class and the only SMB product with a numeric quality score. Three call types with published quotas: **Simulated calls** (AI-vs-AI text, 50/mo free), **Test calls** (live browser voice, 25/mo free), **Real calls** (auto-evaluated on a sample, 25/mo free). You define **Goals** and **Scenarios**, the system generates pass/fail **checks**, and every call scores into an **AQI = Goal Attainment % + Caller Experience %**, where Caller Experience is five fixed checks (greeted naturally / clear communication / smooth pacing / stayed on topic / ended appropriately). Failing checks produce "a specific instruction change to fix it". Documented honestly: "**Simulations end at the point where a transfer or scheduling handoff would occur**" ([Quality Studio](https://smithaivoiceassistant.freshdesk.com/support/solutions/articles/151000232639-getting-started-with-quality-studio), [AQI](https://smithaivoiceassistant.freshdesk.com/support/solutions/articles/151000232615-understanding-your-aqi-score)).
- **Avoca's sandbox is the best-designed testing feature found anywhere.** Register test caller numbers; "Calls from registered numbers **stay off the main Calls page** and appear in this team's **All test calls** history instead", with a "Choose whether test calls can book" control and an explicit warning that unlinking a number means future calls "can trigger ServiceTitan bookings" ([Test your agent](https://help.avoca.ai/getting-started/testing)).
- **Frontdesk's Playground** offers *Join Audio* (browser), *Receive Call* (the AI calls your phone), and a **share link so a colleague can call in** — while documenting the trap: "Browser-based calls (Join Audio) do not support SMS or call transfers. To test those features, use Receive Call" ([Testing](https://www.myaifrontdesk.com/help/getting-started/testing)).
- **Nextiva prescribes the scenario set**: a service from the website, hours/policies, a specific FAQ, **and "something the AI shouldn't know or shouldn't be discussing (to test guardrails)"** — "This takes five minutes and prevents embarrassing mistakes with real callers" ([Nextiva](https://www.nextiva.com/blog/how-to-set-up-ai-receptionist.html)).
- **Loman publishes the best pre-live checklist** (via a partner KB): confirm the greeting, a test order with correct pricing routing to the kitchen display, a reservation, and "**A complex or unusual request triggers a call transfer to a staff member**" ([Shift4 KB](https://shift4.zendesk.com/hc/en-us/articles/51910521192979-Enable-Loman-AI-in-the-Shift4-Dine-Customer-Hub)).

**Templates by vertical** accelerate the rest: Synthflow's template browser filters **by industry and call type**; Dialzara advertises **88+ industry starter prompts**; Smith.ai's Quality Studio has a **vertical template library** plus "**Generate from call history**: The system reviews your recent calls and suggests scenarios based on what callers actually asked". Goodcall's "templates" are really its pre-built skill library; Slang.ai and Loman *are* the vertical, pre-trained on restaurant call corpora.

**Published time-to-live claims — and a warning.**

| Vendor | Claim |
|---|---|
| Smith.ai | "~15 minutes"; a help article titled "in 2 minutes" |
| Frontdesk | "Go live in under 5 minutes" |
| Goodcall | "set up in 5 minutes" |
| RingCentral | "up and running in minutes" |
| Rosie | "under 30 minutes" (3 steps) |
| Dialzara | **"2 minutes" / "15 Minutes" / "under 30 minutes" / "under 3 days"** — four pages, same site |
| Sameday | **"15 minutes" / "30 minutes" / "3-7 days"** |
| Slang.ai | **"as little as 30 mins" / "up and running in days"** |
| Signpost | **"1–2 days" / "<7 Days" / "just a few minutes"** |
| Loman | "less than 24 hours" |
| Numa | **"2-3 weeks" (current) / "less than 15 minutes" (older blog)** |
| Avoca | none published |

> **Do not treat any single figure as the category norm. Four vendors publish mutually contradictory time-to-live claims on their own websites, spanning two orders of magnitude.** The defensible reading, and the one we should design and market to: **a working draft agent in under 15 minutes; "live on real calls with forwarding tested" is 30 minutes to a day; anything touching a POS, DMS or field-service system is days to weeks.**

Trillet — a vendor selling the 5-minute scrape — concedes where the real work is: "**The real work is not technical, it is the 15 minutes of reviewing what the AI scraped**, correcting your hours and services, connecting a calendar, and choosing which calls to forward. **Skip that review pass and you get a fast setup with day-one mistakes**" ([Trillet](https://trillet.ai/blogs/ai-receptionist-setup-without-technical-knowledge)). A more sober breakdown puts *minimum viable* setup at **75 minutes** ([NextPhone](https://www.getnextphone.com/blog/ai-receptionist-setup-time)).

**One onboarding step that cannot be fast, and nobody advertises:** A2P 10DLC registration for SMS. Twilio's own quickstart warns *"campaign reviews take 10–15 days"*, and from 30 June 2026 registration requires public privacy-policy and terms URLs (§3.4). **Voice can be live in 15 minutes; SMS follow-up cannot.** Signpost is the rare vendor that says so out loud, listing A2P registration (~7 days) as a documented prerequisite.

### 2.4 Table stakes vs differentiators

**TABLE STAKES — every documented vendor has these; absence reads as an unfinished product:**
1. Call log with date/time, caller ID, duration, outcome
2. Recording playback + full transcript + AI summary on every call
3. Website and/or Google Business Profile scraping to auto-build the agent, **with a human review step**
4. Editable greeting and selectable voice
5. Owner-editable FAQ pairs
6. At least one transfer destination with a rule
7. Email + SMS notification per call, with the summary
8. Vendor number + carrier-specific conditional-forwarding instructions
9. Per-day business hours (**Frontdesk's absence of an hours object is the notable outlier**)
10. Spam/robocall filtering, framed as protecting the owner's minutes
11. Google Calendar booking and Zapier
12. Multiple notification recipients; invite a teammate
13. Usage against plan, visible before the invoice
14. Basic call-volume analytics
15. Self-serve setup well under an hour, with a test-call path

**DIFFERENTIATORS — ranked by leverage for an SMB owner:**
1. **Knowledge-gap → FAQ learning loop** with frequency counts and one-click accept (Smith.ai, RingCentral, Goodcall) — the highest-leverage feature in the survey
2. **Test/simulation environment with scoring** run before go-live (Smith.ai AQI; Avoca's production-safe sandbox)
3. **Resolution analytics with the *reason*** — resolved-by-transfer vs resolved-by-knowledge-base, top-3 unresolved questions (RingCentral); prescriptive interpretation (Webex)
4. **Minutes used/remaining where the owner already looks, plus threshold alerts** (RingCentral, Frontdesk, Abby) — most vendors ship nothing; an easy win
5. **Escalation beyond a single number** — waterfall (Rosie), serial + parallel blast + AI-resumes-after-failure (Frontdesk), on-call calendar with emergency broadcast (Avoca)
6. **Transfer destinations as objects with their own schedule, timezone and holiday behaviour** (only Avoca)
7. **Holidays as behavioural exceptions** — emergency-only booking, fee overrides (Avoca); per-holiday availability with a pre-holiday reminder email (Smith.ai); daily auto-import from Google/Yelp (Goodcall)
8. **Native mobile app that configures the agent** (only Rosie)
9. **Owner-defined per-call structured extraction** (Frontdesk Smart Call Analysis)
10. **Sentiment and call scoring in the owner view** (Frontdesk, Abby, Ruby, Avoca, Smith.ai — *not* RingCentral)
11. **Booking conversion and revenue attribution** (Avoca, Slang.ai, Loman, Numa)
12. **Missed-call recovery as an assignable workflow** (only Avoca)
13. **Granular roles including a client-safe read-only tier** (Goodcall, Frontdesk, Avoca SSO)
14. **Integrations tab with Connected / Not Connected / Coming Soon badges** (Avoca, RingCentral) — Avoca is explicit that "**Coming Soon** is informational. **It is not a working connection flow**"
15. **Owner-controlled data retention** (only Dialzara)
16. **A hard spend cap that rejects calls rather than billing you** (nobody in the SMB set; only Bland)

> **Sourcing note.** Vendor help centres, docs and app-store listings were read directly and are cited per claim. For the demo-gated vendors (Slang.ai, Sameday, Loman, Numa, Nexa, Podium) every dashboard claim is marketing- or trade-press-derived and should not be treated as a verified benchmark. No screenshots were viewed; UI descriptions come from documented text. Capabilities not found in documentation are recorded as unverified rather than assumed absent.
>
> **The developer platforms are not uniformly ahead.** They decisively beat SMB products on structured extraction, per-turn debugging, live listen/take-over, versioning and custom analytics — but are *behind* on business hours (only Synthflow has one, with no holidays), on "tell a human right now" alerting (only Bland can phone a person), and on mobile (**none of the four ships an app**). Two live deprecations to note: **Vapi Workflows retired 2026-08-18** and **Synthflow removes reselling 2026-09-15**.

---

## 3. COMPLIANCE STANDARD (US-first, EU noted)

> **This is not legal advice.** It is a research summary with sources, assembled 2026-08-27, intended to tell us what to build and what to ask a lawyer about. AI law is moving fast — Colorado's effective date moved three times in eighteen months and the law was then repealed and rewritten. Every item here should be re-verified before it enters a customer contract. Items I could not verify are marked **UNVERIFIED**, and a full list of them closes this section.

### 3.1 Call recording consent

**Federal floor.** The Wiretap Act, 18 U.S.C. § 2511(2)(d), permits recording with the consent of **at least one party** — so a business that is a party to the call may record it ([Versadial](https://www.versadial.com/faqs/call-recording-laws-united-states); [Smith.ai](https://smith.ai/blog/how-to-record-calls-plus-call-recording-rules-for-every-state); [Dialzara](https://dialzara.com/blog/call-recording-laws-ai-agents-by-state) — all accessed 2026-08-27). Recording a conversation you are *not* a party to is illegal everywhere ([SIPNEX](https://www.sipnex.ca/blog/two-party-consent-states)).

**The all-party list is genuinely contested — do not hard-code it.** This is the most-misreported fact in the vendor literature. Counts of 11, 12, 13 and 15 all appear in current sources:

| Source | Count | List |
|---|---|---|
| [Rev](https://www.rev.com/blog/phone-call-recording-laws-state) | 11 | CA, DE, FL, IL, MD, MA, MT, NV, NH, PA, WA |
| [Smith.ai](https://smith.ai/blog/how-to-record-calls-plus-call-recording-rules-for-every-state) | 11 | identical to Rev |
| [CommLaw Group](https://commlawgroup.com/2025/using-ai-in-customer-service-and-telemarketing-top-7-legal-tips) | 11 | drops DE, adds CT |
| [RCFP Reporter's Recording Guide](https://www.rcfp.org/introduction-to-reporters-recording-guide) | ~11 | adds MI (third-party recordings); CT and NV all-party *for phone only*; MO and OR all-party in-person only; HI and ME all-party in private places |
| [NextPhone](https://www.getnextphone.com/blog/call-recording-laws-by-state), [Dialzara](https://dialzara.com/blog/call-recording-laws-ai-agents-by-state) | 12 | CA, CT, DE, FL, IL, MD, MA, MT, NV, NH, PA, WA |
| [Recording Law](https://www.recordinglaw.com/party-two-party-consent-states) | 12 | swaps NV out, OR in; classifies **MI as one-party** (participant exception, *Sullivan v. Gray* 1982) |
| [Outreach](https://support.outreach.io/support/solutions/articles/159000426409-call-recording-laws-and-regulations-us-and-international), [Sembly](https://www.sembly.ai/blog/call-recording-laws-one-party-vs-two-party-consent) | 15 | adds MI, OR, VT |
| [SIPNEX](https://www.sipnex.ca/blog/two-party-consent-states) | 11 clear + 4 unsettled | "treat all fifteen as all-party in practice" |
| [Synthflow](https://synthflow.ai/blog/can-a-company-record-phone-calls-without-consent) | 12 | **omits Delaware entirely** |

**Stable across nearly all sources:** California, Delaware, Florida, Illinois, Maryland, Massachusetts, Montana, New Hampshire, Pennsylvania, Washington. **Contested:** Nevada, Connecticut, Michigan, Oregon, Vermont, Hawaii, Maine, Missouri.

**Cross-border reach.** California's Supreme Court is reported to have held in 2006 that calls *into* California require all-party consent even when the caller sits in a one-party state ([World Population Review](https://worldpopulationreview.com/state-rankings/two-party-consent-states); the case is *Kearney v. Salomon Smith Barney*, per [Nimitai](https://nimitai.com/blog/one-party-vs-two-party-consent-states)). An SMB in Texas using our product **will** receive California calls.

**Penalties are criminal in places, not just civil.** Florida: illegal interception is a **third-degree felony** under Fla. Stat. § 934.03, up to five years, plus civil damages ([Teneks, updated 2026-06-09](https://www.teneks.ai/call-recording-laws/florida); [Fornaro Legal, updated 2026-07-20](https://fornarolegal.com/florida-call-recording-law-guide)). Massachusetts: illegal wiretapping is **always a felony**. California: misdemeanor first offense, felony on repeat; Penal Code § 632 penalties up to $2,500 per violation plus $5,000 civil damages per violation under § 637.2, with a private right of action ([Recording Law](https://www.recordinglaw.com/party-two-party-consent-states); [Nimitai](https://nimitai.com/blog/one-party-vs-two-party-consent-states)).

**Does "this call may be recorded" count as consent?** The practitioner view is that clear pre-call notice plus the caller continuing = implied consent, but it is not universally safe:

> "While it is the best practice to obtain affirmative consent from the consumer (such as an audible 'yes')… some states' courts have held that implied consent is established if a caller remains on the line after a disclosure is played… The notice… must be clear to establish implied consent, and the caller must have a reasonable opportunity to end the call if they object." — [CommLaw Group](https://commlawgroup.com/2025/using-ai-in-customer-service-and-telemarketing-top-7-legal-tips)

A contrarian view worth heeding: notification alone is not consent in a two-party state, and the real litigation exposure is the untested **"caller says no" branch** — agents that keep recording after a refusal ([Roark](https://roark.ai/blog/testing-call-recording-consent-voice-ai-agents) — vendor blog, treat as opinion). **Most agents have no such branch. Ours should.**

**Transcripts count too.** Twilio: *"Some jurisdictions ban the transcribing or recording of calls… Some require some or all parties in a conversation to provide informed consent"* ([Twilio — What is Call Transcription?](https://www.twilio.com/docs/glossary/what-is-call-transcription)). **An agent that keeps a transcript but no audio is not automatically outside recording law.**

**Twilio's own position** — it tells you it is your problem and to apply the strictest rule:

> "Twilio requires its customers to comply with all applicable laws. Because the consent laws vary and it can be difficult to determine the location of a call participant, **it is best practice to comply with the strictest consent laws and obtain consent from all participants before recording a call.** … It is also best practice for you to disclose to your users prior to recording that you are using a third party communication provider (e.g., Twilio) to record and store your communications with them." — [Twilio Help Center](https://help.twilio.com/articles/360011522553-Legal-Considerations-with-Recording-Voice-and-Video-Communications)

The same notice is repeated in the docs for [`<Record>`](https://www.twilio.com/docs/voice/twiml/record), the [Recordings resource](https://www.twilio.com/docs/voice/api/recording) and [Video Recordings](https://www.twilio.com/docs/video/api/recordings-resource), each naming California's Invasion of Privacy Act and adding "Twilio recommends that you consult with your legal counsel." Twilio ships **Call Recording Controls** (start/pause/resume mid-call) explicitly for consent workflows ([Twilio blog](https://www.twilio.com/en-us/blog/products/launches/twilio-call-recording-controls-is-now-generally-available)).

**What competitors actually do — from their own docs:**

| Vendor | Practice |
|---|---|
| **Goodcall** | Plays a recording-consent **whisper** before transfer to the business line. **"There is no option to disable this consent whisper."** ([Goodcall Help Center](https://help.goodcall.com/en/articles/8007564-goodcall-s-call-recording-notification)) |
| **Rosie** | Recording and transcription are **always on** ("The Services will create an audio recording of each call"). Rosie supplies **"courtesy template notices"**; the business decides whether to use them — *"You decide through your Account settings whether and how to implement such templates… You are solely responsible for your use of the Recordings."* ([Rosie ToS](https://heyrosie.com/legal/terms)); *"The Subscriber is solely responsible for providing Callers with notice and obtaining their consent"* ([Rosie Privacy Policy](https://heyrosie.com/legal/privacy)) |
| **Retell AI** | Recording **opt-out** setting; when enabled "call recordings won't be stored on Retell's systems" ([Retell community](https://community.retellai.com/t/health-care-use-case/746)) |
| **Synthflow** | Publishes a state guide, "localized disclaimers and recording settings", and a **recording opt-out toggle** in its Command Center ([Synthflow](https://synthflow.ai/blog/can-a-company-record-phone-calls-without-consent)) |
| **Smith.ai** | Recording + transcription is **opt-in** in account settings; publishes the 11-state list ([Smith.ai](https://smith.ai/blog/how-to-record-calls-plus-call-recording-rules-for-every-state)) |
| **Dialzara** | Recommends **area-code geo-detection** to trigger enhanced disclosure in all-party states, plus timestamped consent logs of the exact script used — and universal disclosure anyway ([Dialzara](https://dialzara.com/blog/call-recording-laws-ai-agents-by-state)) |
| **Thoughtly** | Claims automatic state-specific consent scripts and a "Verbatim + Uninterrupted" node so the caller must hear the full disclosure ([Thoughtly](https://thoughtly.com/blog/ai-disclosure-requirements-what-to-tell-callers) — marketing claim, unverified) |
| **Vapi** | Recording/artifact storage configurable; **Zero Data Retention** add-on turns storage off org-wide ([Vapi docs](https://docs.vapi.ai/security-and-privacy/zero-data-retention)) |

**The de facto standard: disclose on 100% of calls regardless of caller state.** NextPhone, Dialzara, Smith.ai, Synthflow and Twilio all converge on it — *"If you're not sure where your caller is, say 'this call may be recorded' on every call and you're covered everywhere"* ([NextPhone](https://www.getnextphone.com/blog/call-recording-laws-by-state)).

**The under-discussed risk: Illinois BIPA voiceprints.** A voiceprint is an enumerated **biometric identifier** under BIPA (740 ILCS 14), with statutory damages of **$1,000 per negligent and $5,000 per reckless violation, per person**, and a private right of action ([ABA](https://www.americanbar.org/groups/litigation/resources/newsletters/class-actions-derivative-suits/voiceprints-ai-bipa-new-trends-biometric-privacy-litigation); [RatedWithAI, 2026-07-02](https://ratedwithai.com/blog/bipa-voice-biometrics-call-center-2026)). There is an active litigation wave: *In re Otter.AI Privacy Litigation* (N.D. Cal., filed Aug 2025), *Cruz v. Fireflies.AI* (filed Dec 2025), and **nine coordinated class actions filed 11–14 May 2026** in N.D. Ill. against Adobe, Alphabet, Amazon, Apple, ElevenLabs, Meta, Microsoft, NVIDIA and Samsung over voiceprints extracted for AI voice-model training (ABA). **Whether ordinary STT transcription without speaker identification creates a "voiceprint" is unsettled** — flagged as unresolved. Practical guard: do not enable speaker identification/diarization or voice-embedding storage without a BIPA analysis.

### 3.2 AI disclosure — must we tell the caller it's a bot?

**Short answer for a US inbound receptionist:** no single clean federal rule requires it, California's bot law probably doesn't reach phone calls, and Colorado's general duty was repealed before it took effect — **but Utah already requires it orally for licensed occupations, Maine already requires it for voice bots that could mislead, the EU requires it as of 2 August 2026, and the FCC has proposed it federally.** Say it in the first sentence.

**California B.O.T. Act — Cal. Bus. & Prof. Code §§ 17940–17943 (SB 1001).** Enacted Stats. 2018 Ch. 892, **operative 1 July 2019** per § 17943. Operative text ([California Legislative Information](https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml?lawCode=BPC&division=7.&title=&part=3.&chapter=6.&article=); [Justia](https://law.justia.com/codes/california/code-bpc/division-7/part-3/chapter-6/section-17941)):

> "(a) It shall be unlawful for any person to use a bot to communicate or interact with another person in California **online**, with the intent to mislead the other person about its artificial identity for the purpose of knowingly deceiving the person about the content of the communication in order to **incentivize a purchase or sale of goods or services in a commercial transaction or to influence a vote in an election**. A person using a bot shall not be liable under this section if the person discloses that it is a bot.
> (b) The disclosure required by this section shall be clear, conspicuous, and reasonably designed to inform persons with whom the bot communicates or interacts that it is a bot."

- **"Bot"** is defined in § 17940(a) as *"an automated online account where all or substantially all of the actions or posts of that account are not the result of a person."*
- **Scope limit that matters most:** the duty attaches to communications "in California **online**." Davis Wright Tremaine flagged the gap on day one: *"Left unanswered is the question of whether this measure covers interactive voice recognition systems provided via telecommunications services"* ([DWT](https://www.dwt.com/blogs/artificial-intelligence-law-advisor/2019/07/is-there-anybody-behind-that-bot)). **Application to a PSTN AI receptionist is UNVERIFIED and contested.** Vendor blogs cite it for phone agents routinely; the statutory text does not obviously reach them. There is also a *further* limit — the statute requires **intent to mislead** plus a commercial-transaction or election purpose. Disclosure is a complete safe harbour.
- **Penalties — conflicting sources.** The statute contains **no internal enforcement mechanism and no private right of action**; the AG (and possibly DAs/city attorneys) can seek civil penalties up to **$2,500 per violation under the Unfair Competition Law**, and private plaintiffs may try a UCL predicate theory ([Cooley](https://cdp.cooley.com/california-regulates-online-bots); [DWT](https://www.dwt.com/blogs/artificial-intelligence-law-advisor/2019/07/is-there-anybody-behind-that-bot); [TermsFeed](https://www.termsfeed.com/blog/ca-bot-disclosure-law); [Orrick tracker](https://ai-law-center.orrick.com/us-ai-law-tracker-see-all-states)). One firm blog claims penalties include **up to six months' imprisonment** ([ADLI Law](https://adlilaw.com/no-ifs-ands-or-bots-bot-use-disclosure-now-mandatory-in-california)) — **this conflicts with every other source and with the statute's silence. Do not rely on it.**
- **AB 410 (2025)** would amend § 17941 ([LegiScan](https://legiscan.com/CA/text/AB410/id/3186971/California-2025-AB410-Amended.html)) — **enactment status and content UNVERIFIED.**

**California AB 2905 — the one that names phone calls. Effective 1 January 2025.** Signed 20 September 2024, Ch. 316 Stats. 2024 ([CalMatters](https://calmatters.digitaldemocracy.org/bills/ca_202320240ab2905); [Clark Hill](https://www.clarkhill.com/news-events/news/a-view-from-california-one-important-artificial-intelligence-bill-down-17-others-good-to-go)). It amends the Public Utilities Code rules for **automatic dialing-announcing devices**: existing law already required an unrecorded natural-voice announcement stating the nature of the call, identifying the business, and asking consent to hear the prerecorded message; AB 2905 adds that the announcement must **also inform the person called if the prerecorded message uses an artificial voice**, defined to include AI-generated or significantly altered voices ([CalMatters](https://calmatters.digitaldemocracy.org/bills/ca_202320240ab2905); [ETO AGORA](https://agora.eto.tech/instrument/1560); [EPIC](https://epic.org/california-legislative-session-roundup-which-key-privacy-and-ai-bills-were-enacted-and-which-were-vetoed)). Penalty **up to $500 per violation** ([Orrick](https://ai-law-center.orrick.com/california)). **Scope flag:** the statute is framed around automatic dialing-announcing devices, i.e. **outbound**. Two vendor pages assert it also covers inbound AI answering ([Aira](https://www.getaira.io/resources/california-ai-voice-disclosure); [NextPhone](https://www.getnextphone.com/blog/call-recording-laws-by-state)) — **both go beyond the statutory framing; treat inbound application as UNVERIFIED.**

**California AB 3030 (health care) — effective 1 January 2025**, codified at Health & Safety Code § 1339.75. Applies to health facilities, clinics, physicians' offices and group practices using generative AI to produce **written or verbal** patient communications **pertaining to patient clinical information**. Requires (1) a disclaimer that the communication was AI-generated — **for audio, at the beginning** — and (2) clear instructions on how to reach a human provider ([ArentFox Schiff](https://www.afslaw.com/perspectives/alerts/california-requires-disclaimers-health-care-providers-ai-generated-patient); [Duane Morris](https://www.duanemorris.com/alerts/california_passes_novel_law_governing_generative_ai_healthcare_1224.html); [Covington](https://www.insideprivacy.com/uncategorized/california-enacts-health-ai-bill-and-protections-for-neural-data); [ETO AGORA](https://agora.eto.tech/instrument/1552)).

> **Two exemptions that matter enormously for us.** "Patient clinical information" *"does not include administrative matters, including, but not limited to, **appointment scheduling, billing, or other clerical or business matters**"* ([Covington](https://www.insideprivacy.com/uncategorized/california-enacts-health-ai-bill-and-protections-for-neural-data)). **A pure scheduling/intake receptionist is largely outside AB 3030.** Communications reviewed by a licensed human before sending are also exempt.

No specific penalties; enforcement runs through normal licensure/disciplinary channels (CDPH, Medical Board). **SB 1120** governs AI in utilization review by health plans — not relevant to a receptionist ([Orrick](https://ai-law-center.orrick.com/california); [Healthesystems](https://healthesystems.com/regulatory/california-enacts-ai-disclaimer-bill-and-ai-utilization-review-bill)).

**California SB 243 (companion chatbots) — effective 1 January 2026.** Signed 13 October 2025 ([Troutman](https://www.troutmanprivacy.com/2026/01/analyzing-the-new-ai-companion-chatbot-laws)). Requires clear notification where a reasonable person would be misled, self-harm crisis protocols, and minor-specific measures; **private right of action at the greater of actual damages or $1,000 per violation plus fees** ([Jones Walker](https://www.joneswalker.com/en/insights/blogs/ai-law-blog/ai-regulatory-update-californias-sb-243-mandates-companion-ai-safety-and-accoun.html)). **It expressly excludes bots used only for customer service, business operational purposes, productivity, internal research or technical assistance**, and standalone voice-command devices ([LegiScan enrolled text](https://legiscan.com/CA/text/SB243/id/3269137); [Bass Berry](https://bassberry.com/news/california-companion-chatbot-bill)). **An AI receptionist is out of scope — but counsel warn the exclusion is narrower than it sounds: a bot that remembers prior conversations, adapts tone, or builds rapport across sessions may fall back in** ([Gunderson Dettmer](https://www.gunder.com/en/news-insights/insights/client-insight-california-sb-243-new-compliance-requirements-for-operators-of-ai-companion-chatbots); [Crowell & Moring](https://www.crowell.com/en/insights/client-alerts/californias-chatbot-bill-may-impose-substantial-compliance-burdens-on-many-companies-deploying-ai-assistants)). **Direct consequence for our roadmap: the "caller memory" feature identified in §1.4 as our sharpest differentiator is exactly the feature that could pull us toward SB 243 scope. Worth a legal read before shipping it.**

**Other California laws — mostly not ours:** AB 2013 (training-data transparency, eff. 1 Jan 2026) binds *developers*; SB 53 (frontier safety, eff. 1 Jan 2026) binds frontier developers; **SB 942 (California AI Transparency Act)** was delayed by AB 853 from 1 Jan 2026 to **2 August 2026** to align with EU AI Act Art. 50, with large-platform duties from 1 Jan 2027 — but it binds "covered providers" with **over 1,000,000 monthly users**, so an SMB receptionist product is almost certainly out of scope though its upstream model/TTS vendors are not ([Troutman](https://www.troutmanprivacy.com/2025/10/california-ai-transparency-act-amendments-signed-into-law); [Mayer Brown](https://www.mayerbrown.com/en/insights/publications/2025/10/new-obligations-under-the-california-ai-transparency-act-and-companion-chatbot-law-add-to-the-compliance-list); [A&O Shearman](https://www.aoshearman.com/en/insights/ao-shearman-on-tech/zooming-in-on-ai-california-evolving-ai-legal-landscape-entering-2026)). **CPPA ADMT regulations** (pre-use notices, eff. 1 Jan 2026 for new systems, enforcement from 1 Jan 2027) apply only where the agent drives a "significant decision" — booking an appointment generally is not ([Secure Privacy](https://secureprivacy.ai/blog/california-ai-transparency-law)).

**Utah AI Policy Act — this one hits our best customers.** SB 149 took effect **1 May 2024**; the 2025 amendments **SB 226 and SB 332 took effect 7 May 2025**, with SB 226 repealing the original § 13-2-12 and enacting **Utah Code Chapter 13-75** ([Davis Polk](https://www.davispolk.com/insights/client-update/utah-scales-back-reach-generative-ai-consumer-protection-law); [FPF](https://fpf.org/blog/chatbots-in-check-utahs-latest-ai-legislation); [Bradley](https://www.onlineandonpoint.com/2025/05/understanding-the-utah-ai-act-and-newly-effective-amendments-what-your-business-needs-to-know); [ETO AGORA SB 226 text](https://agora.eto.tech/instrument/4757)). Two different duties:

- **General consumer transactions — reactive.** Under § 13-75-103(1) a supplier using GenAI to interact with an individual must disclose that it is GenAI and not human **only "if the individual asks or otherwise prompts"**, and the prompt "must be a **clear and unambiguous request**" ([ETO AGORA](https://agora.eto.tech/instrument/4757); [Davis Polk](https://www.davispolk.com/insights/client-update/utah-scales-back-reach-generative-ai-consumer-protection-law)).
- **Regulated occupations — proactive.** A person providing services in a **regulated occupation** (requiring a state licence/certification) must **prominently disclose** GenAI use in **high-risk** interactions **at the beginning — orally if the interaction is verbal** ([Bradley](https://www.onlineandonpoint.com/2025/05/understanding-the-utah-ai-act-and-newly-effective-amendments-what-your-business-needs-to-know); [ETO AGORA](https://agora.eto.tech/instrument/4757)). "High-risk" covers GenAI collecting sensitive personal information plus significant decision-making — financial, legal, medical and mental-health contexts ([FPF](https://fpf.org/blog/chatbots-in-check-utahs-latest-ai-legislation)).
- **Safe harbour (§ 13-75-104):** available if the AI discloses its use **at the beginning of the interaction and throughout it** ([Bradley](https://www.onlineandonpoint.com/2025/05/understanding-the-utah-ai-act-and-newly-effective-amendments-what-your-business-needs-to-know); [DeepInspect](https://www.deepinspect.ai/blog/utah-ai-ai-compliance-checklist)).
- **Sunset extended to 1 July 2027.** Enforcement by the Utah Division of Consumer Protection; **no private right of action** ([FPF](https://fpf.org/blog/chatbots-in-check-utahs-latest-ai-legislation); [stackcyber](https://stackcyber.com/posts/ai-chatbot-laws)).

> **Read for us:** a **dentist, law firm, medical practice or accountant in Utah** — precisely our highest-value verticals — needs the AI to announce itself **orally at the start of the call**.

**Colorado — the AI Act was repealed before it ever took effect.** Most compliance write-ups get this wrong. Timeline:

1. **SB 24-205** signed 17 May 2024, to take effect 1 February 2026. § 6-1-1704(1) contained the relevant duty: a deployer of *"an artificial intelligence system that is intended to interact with consumers shall ensure the disclosure to each consumer… that the consumer is interacting with an artificial intelligence system"*, unless obvious ([ETO AGORA](https://agora.eto.tech/instrument/1376); [IRMI](https://www.irmi.com/articles/expert-commentary/colorado-artificial-intelligence-law-deployer-disclosure-requirements)).
2. **SB 25B-004**, signed 28 August 2025, delayed it to 30 June 2026 ([Greenberg Traurig](https://www.gtlaw.com/en/insights/2025/9/colorado-delays-comprehensive-ai-law-with-further-changes-anticipated); [Troutman](https://www.troutmanprivacy.com/2025/08/colorado-ai-act-effective-date-delayed)).
3. **27 April 2026** — a Colorado magistrate ordered the AG not to enforce it pending final rules, after an x.AI suit ([Littler](https://www.littler.com/news-analysis/asap/colorados-artificial-intelligence-law-could-be-chopping-block); [Norton Rose Fulbright](https://www.nortonrosefulbright.com/en-us/knowledge/publications/18733d31/colorado-enacts-revised-ai-law)).
4. **14 May 2026 — Governor Polis signed SB 26-189, which repeals and reenacts the law as an Automated Decision-Making Technology (ADMT) statute, effective 1 January 2027**, eliminating the duty of care on algorithmic discrimination, risk-management programs, impact assessments and AG reporting ([Colorado General Assembly](https://leg.colorado.gov/bills/sb26-189); [Hunton, 2026-05-22](https://www.hunton.com/privacy-and-cybersecurity-law-blog/colorado-ai-act-amended-and-effective-date-delayed); [DWT, 2026-05-21](https://www.dwt.com/blogs/privacy--security-law-blog/2026/05/colorado-ai-act-repeal-new-transparency-law); [Littler](https://www.littler.com/news-analysis/asap/colorado-amends-its-artificial-intelligence-law-substantially-reducing)).

**Does the general "you are talking to an AI" duty survive? Sources conflict.** Troutman says SB 189 *"does not contain any reference to… disclosures to consumers if they are interacting with nonobvious AI systems"* ([Troutman](https://www.troutmanprivacy.com/2026/05/colorado-legislature-passes-bill-to-repeal-and-replace-colorado-ai-act)); Crowell lists among the new duties one *"to notify users when they interact with AI"* ([Crowell](https://www.crowell.com/en/insights/client-alerts/colorado-hits-reset-on-ai-regulation-sb-26-189-repeals-and-reenacts-the-colorado-ai-act)). The legislature's own summary resolves it toward Troutman — notice is required *"at the point of interaction with a **covered ADMT**"*, i.e. tied to consequential decisions, not conversational AI generally ([Colorado General Assembly](https://leg.colorado.gov/bills/sb26-189)). **Best read: Colorado's general chatbot-disclosure duty never took effect and no longer exists; an appointment-booking receptionist is very likely out of scope from 1 Jan 2027. Verify against enacted text.** AG rulemaking due by 1 January 2027.

**Maine LD 1727 — the most directly applicable general-purpose law found, and it explicitly covers voice.** Signed by Gov. Mills 12 June 2025. **"AI chatbot"** is defined as *"software applications, web interfaces or computer programs that simulate human conversation and interaction through **textual or aural** communications"* — Verrill notes this *"appears to apply to… even **callbots** (voice assistants that can entertain human phone calls)"* ([Verrill Law](https://www.verrill-law.com/news/maine-law-now-requires-limited-disclosures-of-artificial-intelligence-technology); [Hogan Lovells](https://www.hlc.com/en/publications/ai-legislative-updates-in-maine-and-new-york)). **Duty:** clear and conspicuous notice that the consumer is not engaging with a human, where the use "may mislead or deceive a reasonable consumer." Violation = violation of the **Maine Unfair Trade Practices Act**. **Effective date reported inconsistently as 16, 23 or 24 September 2025** ([Regulations.ai](https://regulations.ai/regulations/RAI-US-ME-ETCTIXX-2025); [CompliancePoint](https://www.compliancepoint.com/marketing-compliance/maines-new-ai-transparency-law); [stackcyber](https://stackcyber.com/posts/ai-chatbot-laws)) — **conflict flagged**; penalty amount and private right of action also **UNVERIFIED**.

**The 2026 wave** — mostly companion-scoped, but watch the definitions:

| State | Law | Effective | Note |
|---|---|---|---|
| Iowa | SF 2417 | **1 July 2026** ([stackcyber](https://stackcyber.com/posts/ai-chatbot-laws)) vs **1 July 2027** ([Industry Self-Regulation](https://industryselfregulation.org/media-resource/media/blog/ai-chatbot-regulations)) — **CONFLICT** | Covers "text, audio, or visual"; persistent disclaimer or one every 3 hours ([Orrick tracker](https://ai-law-center.orrick.com/us-ai-law-tracker-see-all-states)) |
| Hawaii | SB 3001 | **14 July 2026** — already live | ([Transparency Coalition](https://www.transparencycoalition.ai/news/watershed-year-for-chatbot-safety-measures-14-new-state-laws-enacted-so-far-in-2026)) |
| Georgia | SB 540 | 1 Jan 2027 | enacted 11 May 2026 |
| Washington | HB 2225 | 1 Jan 2027 | **private right of action** ([Orrick](https://www.orrick.com/en/Insights/2026/04/2026-State-Chatbot-Laws-Key-Provisions-and-Regulatory-Trends)) |
| Oregon | SB 1546 | 1 Jan 2027 | private right of action, **$1,000 statutory damages** |
| Rhode Island | S 2195 | 1 Jan 2027 | disclosure at start **and every 3 hours**; up to **$15,000/day** |
| Idaho | S 1297 | 1 Jan 2027 vs 1 July 2027 — **CONFLICT** | no private right of action |
| Nebraska | LB 525 | 1 July 2027 | AG-only enforcement |
| Connecticut | AI companion regulation | enacted 27 May 2026 | ([White & Case](https://www.whitecase.com/insight-our-thinking/ai-watch-global-regulatory-tracker-united-states)) |
| New York | Gen. Bus. Law § 1700 (S-3008C) | 5 Nov 2025 | companion-scoped |

**AG guidance (no statute needed).** Massachusetts AG Campbell's **Advisory of 16 April 2024** applies Chapter 93A to AI and lists as unfair/deceptive: *"Misrepresent audio or video content of a person for the purpose of deceiving another to engage in a business transaction… as in the case of deepfakes, voice cloning, or chatbots used to engage in fraud"* ([Mass.gov advisory PDF](https://www.mass.gov/doc/ago-ai-advisory-41624/download); [press release](https://www.mass.gov/news/ag-campbell-issues-advisory-providing-guidance-on-how-state-consumer-protection-and-other-laws-apply-to-artificial-intelligence); [Manatt](https://www.manatt.com/insights/newsletters/client-alert/massachusetts-attorney-general-issues-advisory-on)) — deception-focused, not itself a disclosure duty. On **10 December 2025** NJ AG Platkin led a **bipartisan coalition of 42 AGs** demanding safeguards from 13 AI companies including "clear warnings to consumers" ([NJ OAG](https://www.njoag.gov/ag-platkin-leads-bipartisan-coalition-demanding-that-tech-companies-put-a-stop-to-harmful-ai-chatbots)). Illinois' real voice-AI exposure is **BIPA**, not disclosure.

**Conclusion:** ship a **configurable AI-disclosure line in the greeting, default ON**. It costs one sentence; it is already required in Utah for regulated occupations, in Maine for misleading voice bots, and in the EU; it satisfies the FCC's proposed federal rule in advance; and it removes the "intent to mislead" element that most of these statutes turn on. The market is split — some vendors "address this by making the AI voice indistinguishable from a human and disclosing AI use only when asked" ([Voksha](https://voksha.com/guide/what-is-an-ai-receptionist)), while "several reputable ones do so by default" ([Marblism](https://www.marblism.com/blog/best-ai-receptionist)). Being in the second group is nearly free.

### 3.3 FCC / TCPA — and why inbound is the safe side

**The February 2024 Declaratory Ruling.** *In the Matter of Implications of Artificial Intelligence Technologies on Protecting Consumers from Unwanted Robocalls and Robotexts*, CG Docket No. 23-362, **Declaratory Ruling FCC 24-17, adopted 2 February 2024, released 8 February 2024**, unanimous ([primary text PDF](https://www.consumerfinancialserviceslawmonitor.com/wp-content/uploads/sites/880/2024/02/February-8-FCC-Ruling.pdf); [FCC press release](https://docs.fcc.gov/public/attachments/DOC-400393A1.pdf)).

**Holding:** the TCPA's restrictions on **"artificial or prerecorded voice"** (47 U.S.C. § 227(b)(1)) encompass current AI technologies that resemble human voices or generate content using a prerecorded voice — because a live person is not speaking ([DWT, 2024-02-09](https://www.dwt.com/blogs/broadband-advisor/2024/02/fcc-rules-ai-robocalls-subject-to-tcpa-regulation); [Mayer Brown](https://www.mayerbrown.com/en/insights/publications/2024/02/fcc-declares-authority-and-intent-to-regulate-ai-generated-calls-under-the-tcpa)). Callers must therefore obtain prior express consent (prior express **written** consent for telemarketing), provide identification/disclosure of the responsible party, and offer opt-out ([Wiley, citing ¶¶ 5, 9](https://www.wiley.law/alert-FCC-Extends-Regulatory-Reach-Over-AI-Announces-TCPA-Restrictions-Cover-AI-Generated-Voices-in-Outbound-Calls)). Effective immediately on release.

**Two corrections to the common misreading:**

1. **It is not a ban.** *"While various headlines and press releases are touting that this move renders AI-generated voices in robocalls 'illegal,' the Declaratory Ruling itself states that AI-generated voice calls will be governed like other 'artificial or prerecorded voice' calls under the TCPA, which are **legal but subject to a range of restrictions**."* ([Wiley](https://www.wiley.law/alert-FCC-Extends-Regulatory-Reach-Over-AI-Announces-TCPA-Restrictions-Cover-AI-Generated-Voices-in-Outbound-Calls)). The FCC's press release used the "illegal" framing; the order did not.
2. **It reaches OUTBOUND only.** § 227(b)(1) restricts *"initiating"* a call using an artificial or prerecorded voice. Vapi's own legal documentation states flatly: **"The TCPA does not apply to inbound telephone calls."** ([Vapi](https://docs.vapi.ai/tcpa-consent)). An independent analysis agrees: the provision targets *"calls a business places, not calls a [consumer] places to your… line"* ([LetHub](https://www.lethub.co/blog/can-ai-answer-rental-calls-legally)). **Caveat: both are vendor sources. The statutory text supports them, but no court or FCC statement squarely addressing inbound AI answering was located — well-supported but not authoritatively confirmed.**

**Penalties:** $500 per violation, trebled to **$1,500 for willful/knowing** violations, private right of action, **no aggregate cap** ([Resemble](https://www.resemble.ai/laws-and-regulations/fcc-ai-robocall-declaratory-ruling); [Henson Legal](https://www.henson-legal.com/ai-voice-compliance)). A 10,000-call campaign is $15M of theoretical exposure.

**The pending NPRM.** **FCC 24-84**, NPRM and Notice of Inquiry, CG Docket 23-362 — adopted at the 7 August 2024 Open Meeting, published in the Federal Register 10 September 2024 ([FCC](https://www.fcc.gov/proposed-rulemakings); [Federal Register](https://www.federalregister.gov/documents/2024/09/10/implications-of-artificial-intelligence-technologies-on-protecting-consumers-from-unwanted-robocalls)). It proposes to (1) define **"AI-generated call"**; (2) require disclosure at the time of obtaining consent that consent may include AI-generated calls; (3) require callers using AI-generated voice to **"at the beginning of each call, clearly disclose to the called party that the call is using AI-generated technology"**; (4) exempt individuals with speech/hearing disabilities ([Wiley](https://www.wiley.law/alert-FCC-Proposes-New-Rules-for-AI-Generated-Calls-and-Texts); [Squire Patton Boggs](https://www.privacyworld.blog/2024/07/fcc-to-consider-formal-rules-for-use-of-artificial-intelligence-and-robocalls); [Wilson Sonsini](https://www.wsgrdataadvisor.com/2024/08/fcc-issues-notice-of-proposed-rulemaking-regarding-the-use-of-ai-generated-technologies-for-consumer-communications)). **Status: NOT finalized.** Comments closed October 2024; two industry sources state it remains at proposed stage as of mid-2026 ([CallSphere](https://callsphere.ai/blog/vw2d-fcc-ai-call-disclosure-rules-2026); [Thoughtly](https://thoughtly.com/blog/ai-disclosure-requirements-what-to-tell-callers)) — **both vendor blogs; "still pending" is probable but not primary-source verified.** Two new FCC NPRMs adopted 26–27 March 2026 (FCC 26-16, CG Docket 26-52; FCC 26-17, WC Docket 26-49) concern robocall mitigation and offshore call centres — **neither is the AI-disclosure rule** ([Mintz, 2026-04-15](https://www.mintz.com/insights-center/viewpoints/2776/2026-04-15-fcc-proposes-new-numbering-policies-combat-illegal)).

**One-to-one consent: dead and formally removed.** Vacated **24 January 2025** by the Eleventh Circuit in ***Insurance Marketing Coalition Ltd. v. FCC*, No. 24-10277**, three days before its effective date; the court held the FCC exceeded its statutory authority and that the new consent restrictions "impermissibly conflict with the ordinary statutory meaning of 'prior express consent'." Both the one-to-one and "logically and topically related" requirements were vacated ([Reed Smith](https://www.reedsmith.com/our-insights/blogs/technology-law-dispatch/102k2uj/eleventh-circuit-vacates-fcc-one-to-one-consent-rule); [Goodwin](https://www.goodwinlaw.com/en/insights/publications/2025/01/alerts-otherindustries-eleventh-circuit-deals-fatal-blow); [Wiley](https://www.wiley.law/alert-UPDATE-11th-Circuit-Vacates-FCCs-One-to-One-TCPA-Consent-Rule); [Venable](https://www.venable.com/insights/publications/2025/01/eleventh-circuit-overrules-fccs-one-to-one)). The FCC has since **formally repealed the vacated rule text** (47 C.F.R. § 64.1200(f)(9)) and reinstated the prior version ([Womble Bond Dickinson](https://www.womblebonddickinson.com/us/insights/tcpa-defense-force/102ndra/fcc-repeals-one-one-consent-rule-following-eleventh-circuit)). **Do not build to it.**

### 3.4 SMS follow-ups

**Consent tiers:**

| Message type | Standard |
|---|---|
| **Marketing / telemarketing** | **Prior Express Written Consent (PEWC)** — signed agreement plus clear and conspicuous disclosure that the consumer agrees to receive calls/texts using an artificial or prerecorded voice/autodialer at that number, **and that consent is not a condition of purchase** ([Vapi](https://docs.vapi.ai/tcpa-consent)) |
| **Informational / transactional** (appointment reminders, confirmations) | **Prior Express Consent (PEC)** — "may be established when a consumer provides a telephone number in connection with a transaction and the call content is closely related to that transaction" ([Retell ToS §4(b)](https://www.retellai.com/legal/terms-of-service)) |

A caller who phones a business and gives their mobile for a booking confirmation has almost certainly given PEC for that confirmation. They have **not** given PEWC for a later promotion. **Keep the two message classes strictly separate and never blend a promotion into a booking confirmation.**

**Revocation of consent — effective 11 April 2025:**
1. **Revocation by any "reasonable method"; callers may not designate an exclusive means.** Per se reasonable: an automated IVR/key-press opt-out; the words **"stop," "quit," "end," "revoke," "opt out," "cancel," "unsubscribe"** in a text reply; or a website/number designated for opt-outs. Other words count if a reasonable person would understand them as revocation, **with the burden on the caller** ([Roth Jackson](https://www.rothjackson.com/blog/2024/11/the-fcc-announces-effective-date-for-new-consent-revocation-rules); [BCLP](https://www.bclplaw.com/en-US/events-insights-news/the-tcpas-new-opt-out-rules-take-effect-on-april-11-2025-what-does-this-mean-for-businesses.html)).
2. **Honor within 10 business days** (down from 30) (same sources; [Klein Moynihan Turco](https://kleinmoynihan.com/fccs-tcpa-consent-revocation-rule-effective-april-11-2025)).
3. **Revocation crosses channels** — it "extends to both robocalls and robotexts regardless of the medium used to communicate the revocation" ([BCLP](https://www.bclplaw.com/en-US/events-insights-news/the-tcpas-new-opt-out-rules-take-effect-on-april-11-2025-what-does-this-mean-for-businesses.html)).
4. **One confirmation text is allowed**, with no marketing content; silence must be treated as revocation of all ([Klein Moynihan Turco](https://kleinmoynihan.com/fccs-tcpa-consent-revocation-rule-effective-april-11-2025)).

The broader "revoke-all" provision (47 C.F.R. § 64.1200(a)(10)) is reported delayed to **31 January 2027** by a CGB order of 6 January 2026 ([Gryphon.ai](https://gryphon.ai/how-to-comply-with-the-fccs-upcoming-consent-revocation-rule); [ActiveProspect](https://activeprospect.com/blog/tcpa-revocation-of-consent)) — **vendor sources, UNVERIFIED**. All other April 2025 obligations are in force.

> **Voice-channel implication:** a caller who says *"stop calling me"* or *"take me off your list"* during a live call is making a valid revocation. **An AI agent that cannot recognise and log a spoken opt-out is a compliance gap** ([TermsFeed](https://www.termsfeed.com/blog/tcpa-2025-any-reasonable-means-opt-out)).

**A2P 10DLC on Twilio — a real time-to-live risk.**
- **Mandatory:** *"Anyone sending SMS/MMS messages over a 10DLC number from an application to the US must register for A2P 10DLC"* ([Twilio Docs](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc)).
- **Two steps:** Brand registration with The Campaign Registry, then Campaign registration by use case. Brand types: Sole Proprietor (no EIN, ~1,000/day T-Mobile cap), Low Volume Standard (EIN, <6,000 segments/day), Standard (>6,000/day). Max **five Standard/LVS brands per Tax ID** ([Twilio Help](https://help.twilio.com/articles/1260800720410-What-is-A2P-10DLC-)).
- **Fees:** Standard **$44 one-time brand** + $15 campaign vetting + $1.50–$10/campaign/month; Low-volume standard $4 + $15 + $1.50–$10; Sole proprietor $4 + $15 + $2/month ([Twilio](https://www.twilio.com/en-us/phone-numbers/a2p-10dlc)).
- **Timing warning on Twilio's own quickstart:** *"Due to an increase in campaign submissions, campaign reviews take 10–15 days."* ([Twilio Docs](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/quickstart)). **This directly threatens the "live in under 15 minutes" standard from §2 — SMS features cannot be live on day one.**
- **New requirement, 30 June 2026:** *"Starting June 30, 2026, PrivacyPolicyUrl and TermsAndConditionsUrl will be required fields when registering a new A2P 10DLC campaign via the Twilio Messaging REST API. Campaign creation requests that don't include both fields will be rejected during campaign review."* Existing campaigns unaffected ([Twilio Changelog, 2026-04-06](https://www.twilio.com/en-us/changelog/a2p-10dlc-campaign-registration-will-require-privacy-policy-and-)). **Every SMB we onboard now needs a public privacy policy and T&Cs URL.**
- Twilio also ships a **Consent Management API** and an AI-driven **Compliance Toolkit** for quiet hours, reassigned numbers and opt-outs ([Twilio blog](https://www.twilio.com/en-us/blog/products/launches/introducing-compliance-toolkit)).

**State "mini-TCPA" overlay — often the real trap:**

| State | Statute | Key deltas |
|---|---|---|
| Florida | Fla. Stat. § 501.059 (FTSA) | quiet hours **8am–8pm** local; **max 3 messages/24h** same subject; written consent; private right of action |
| Oklahoma | 15 O.S. §§ 775C.1–775C.6 | mirrors FL; consent must **name the specific business** |
| Maryland | Md. Com. Law §§ 14-4501–14-4503 | PEWC for automated calls/texts; 3-call cap |
| Connecticut | Conn. Gen. Stat. §§ 42-284–289 | **9am**–8pm — tightest window; penalties reported to $20,000/violation |
| Texas | Bus. & Com. Code, amended Sept 2025 | 9am–9pm Mon–Sat, noon–9pm Sun; **solicitor registration**; **treble damages plus mandatory attorney's fees** for off-hours texting |
| Virginia | Va. Code § 59.1-510 (SB 1339), eff. 1 Jan 2026 | **opt-out records retained 10 years** |

([Enzo, "as of July 2026"](https://enzodialer.com/resources/compliance/state-mini-tcpa-laws); [Infobip](https://www.infobip.com/blog/tcpa-compliance-sms); [ActiveProspect](https://activeprospect.com/blog/tcpa-calling-hours) — compliance-vendor trackers, not primary law; verify citations before relying.)

### 3.5 PCI-DSS — taking card numbers by voice

**The standard.** **PCI DSS v4.0.1 has been mandatory since 31 March 2025** ([Enzo](https://enzodialer.com/resources/compliance/call-center-pci-compliance); [Portal Technologies](https://portaltechnologies.uk/pci-compliance-for-taking-payments-over-the-phone-complete-uk-guide-2026)). **Hard rule: Sensitive Authentication Data (CVV/CVC, full track data, PIN) must never be stored after authorization, in any format, including call recordings** ([DTMF Masking whitepaper](https://cdn2.hubspot.net/hubfs/2848241/Collateral/US%20Collateral/DTMF%20Masking%20for%20PCI%20DSS%20Compliance%20FINAL%208.18.pdf); [Onsoft](https://www.onsoft.de/en/blog/pci-dss-anrufaufzeichnung)).

**The PCI SSC's own words**, from Information Supplement *Protecting Telephone-Based Payment Card Data* v3.0 (November 2018):

> "Depending on the particular implementation, DTMF suppression and masking technologies may be able to prevent PAN and SAD from entering the telephone environment, further reducing the applicability of PCI DSS to that environment. … **Storing only suppressed tones rather than original DTMF tones can reduce applicability of PCI DSS requirements for call recordings.** … Some implementations of DTMF masking rely on DTMF-detection; this may introduce a delay in the masking, and the initial portion of the DTMF tones may not be masked (this is called '**DTMF bleed**')."
> — [PCI Security Standards Council (PDF)](https://www.pcisecuritystandards.org/documents/Protecting_Telephone_Based_Payment_Card_Data_v3-0_nov_2018.pdf?agreement=)

**Why pause-and-resume is the weaker answer.** It protects only the recording — "the CSR, the desktop, plus the rest of the contact center infrastructure is still in scope" ([DTMF Masking whitepaper](https://cdn2.hubspot.net/hubfs/2848241/Collateral/US%20Collateral/DTMF%20Masking%20for%20PCI%20DSS%20Compliance%20FINAL%208.18.pdf); [PCI DSS Guide](https://pcidssguide.com/what-you-should-know-about-pci-compliant-call-recording)). It is a process control depending on someone remembering: "Even at 99% reliability, on 50,000 calls a year that's 500 recordings with SAD in them" ([Paytia](https://www.paytia.com/resources/blog/pci-dss-4-0-call-centre-guide)).

**Should the AI ever hear a card number? No.** If the caller reads the PAN aloud, the digits are in the audio path — which now includes the STT engine, the LLM, the transcript store and every subprocessor, putting all of them in PCI scope exactly as a human agent's workstation would be. *(This is an inference extending PCI SSC's stated scoping principle; no PCI SSC document addressing AI voice agents specifically was found — flagged as reasoning, not a cited rule.)*

**What Twilio provides:**

| Capability | Detail |
|---|---|
| **Platform certification** | Twilio Programmable Voice holds **PCI DSS Level 1** ([Twilio](https://www.twilio.com/en-us/blog/voice-agent-assisted-pay); [Twilio](https://www.twilio.com/en-us/blog/products/launches/introducing-pay-pci-compliant-over-the-phone-payments)) |
| **`<Pay>` TwiML** | Captures card data via DTMF and passes it to a payment provider through a Pay Connector (Stripe at launch; a Generic Pay Connector now exists) |
| **Agent Assisted `<Pay>`** | The agent stays on the line but **cannot hear the DTMF** — *"Twilio sends the payment information directly to the payment connector for processing, ensuring no card information is ever divulged to the agent."* Only the **last 4 digits** return (`PaymentCardNumber=xxxx-xxxxxx-x4001`); expiry returns in clear because "the expiration date is not PCI data" ([Twilio Docs — Payments subresource](https://www.twilio.com/docs/voice/api/payment-resource)) |
| **PCI Mode** | Per-account toggle in Voice Settings; redacts sensitive payment details captured via `<Pay>` and `<Gather>`. **Once enabled it cannot be disabled for that Account.** ([Twilio Docs — PCI workflows](https://www.twilio.com/docs/voice/pci-workflows)) |
| **Recordings default** | *"Call recordings aren't Payment Card Industry (PCI) compliant by default. To use Voice Recordings in a PCI workflow, enable PCI Mode in the Twilio Console."* ([`<Record>` docs](https://www.twilio.com/docs/voice/twiml/record)) |
| **Transcription blocked** | *"Native and Marketplace transcriptions aren't available when PCI Mode is enabled"* — you must use the `<Transcription>` noun ([Twilio Docs](https://www.twilio.com/docs/voice/pci-workflows)) |
| **PCI recording retention** | Originally 72 hours. **Effective 29 September 2025, PCI Voice Recordings became part of PCI Mode and new PCI accounts inherit a one-year retention**, with automatic permanent deletion at one year; existing PCI accounts can opt in ([Twilio Changelog, 2025-09-29](https://www.twilio.com/en-us/changelog/updates-to-voice-pci-recordings-console-setting-and-retention-policy)) |
| **Responsibility split** | Twilio publishes a **customer responsibility matrix** ([Twilio Docs](https://www.twilio.com/docs/voice/pci-workflows)) |

> **Two Twilio gotchas that could break our product:** PCI Mode is **irreversible per account**, and it **disables native transcription**. For a receptionist whose core value is transcripts and summaries, enabling PCI Mode on a shared account would be catastrophic. If we ever support payments, it must be on an **isolated account/subaccount**.

**No Twilio documentation addressing PCI and `<ConversationRelay>` specifically was found. Whether `<Pay>` can be invoked mid-ConversationRelay session, and how, is UNVERIFIED** — though the general pattern of returning to the agent afterwards by programming the return route and passing a conversation ID is documented by a third party ([Shuttle](https://www.shuttleglobal.com/guides/ai-voice-agent-pci-payments)).

**Market context:** payment capture is *rare* in SMB AI receptionists (§1.6). **The defensible default is: do not take card numbers by voice.** If a customer needs it, send a payment link by SMS mid-call.

### 3.6 HIPAA — selling to medical and dental offices

**ConversationRelay is HIPAA-eligible — since 17 March 2025.** Twilio's own docs: *"Conversation Relay is a HIPAA Eligible Service when configured properly. For healthcare applications subject to HIPAA, ensure you have a signed Business Associate Agreement (BAA) with Twilio and follow HIPAA compliance guidelines."* ([Twilio ConversationRelay docs](https://www.twilio.com/docs/voice/twiml/connect/conversationrelay); [Twilio Changelog, 2025-03-21](https://www.twilio.com/en-us/changelog/conversationrelay-is-now-hipaa-eligible)). Programmable Voice, Elastic SIP Trunking and Programmable SMS have been HIPAA-eligible since **20 March 2020** ([Twilio Changelog](https://www.twilio.com/en-us/changelog/programmable-voice--sip--and-sms-are-now-hipaa-eligible)); Message Scheduling added 30 August 2022. **Recordings require at least HTTP Authentication** in HIPAA workflows ([Twilio Recordings docs](https://www.twilio.com/docs/voice/api/recording)). Using ConversationRelay at all also requires agreeing to Twilio's **Predictive and Generative AI/ML Features Addendum**.

**The commercial catch.** Twilio's HIPAA page states: *"Customers wishing to sign a BAA with Twilio must have our Security Edition or Enterprise Edition."* ([Twilio HIPAA](https://www.twilio.com/en-us/hipaa)). *(A secondary source says Enterprise Edition specifically — [Paubox](https://www.paubox.com/blog/twilio-hipaa-compliant) — treat the precise edition as needing confirmation with Twilio sales.)* A BAA is not a console toggle. Twilio frames HIPAA as "shared responsibility", and **only services listed in your executed BAA are covered.**

**Competitor HIPAA posture — the useful benchmark:**

| Vendor | BAA? | Gate | Notes |
|---|---|---|---|
| **Retell AI** | **Yes, no extra fee** — *sources conflict* | Retell's docs say **any plan** | Retell's own docs: "HIPAA and GDPR compliant and SOC 2 Type 1 and Type 2 certified… **There is no additional fee to sign these agreements**" ([docs.retellai.com](https://docs.retellai.com/general/compliance)); its blog says the BAA is **self-serve on every plan including pay-as-you-go** ([Retell blog](https://www.retellai.com/blog/hipaa-compliant-voice-ai-without-enterprise-contract)). **But Retell's own pricing page lists HIPAA/BAA, PII redaction, opt-out recording and custom retention in the Enterprise column** ([retellai.com/pricing](https://www.retellai.com/pricing)), and a third party says Enterprise-only ([Cadence](https://gocadence.ai/compare/is-retell-ai-hipaa-compliant)). **Genuine unresolved conflict.** |
| **Vapi** | Yes, gated | **Enterprise subscription OR a paid HIPAA add-on — $2,000/month** ([vapi.ai/pricing](https://vapi.ai/pricing)) | *"Vapi requires a signed BAA before you enable HIPAA mode."* You must use providers from Vapi's HIPAA list — LLM: Anthropic, Azure OpenAI, Baseten, Custom, Google, OpenAI, Together AI, xAI; TTS: Azure, Cartesia, Deepgram, ElevenLabs, Rime, Vapi, xAI; STT: Azure, Cartesia, Deepgram, Soniox, xAI. **HIPAA mode and Zero Data Retention are mutually exclusive.** ([Vapi HIPAA docs](https://docs.vapi.ai/security-and-privacy/hipaa)) |
| **ElevenLabs** | Yes, **Enterprise only** | Enterprise + Zero Retention Mode | *"Execution of a BAA… is only available for Enterprise tier subscriptions… PHI should not be submitted to the ElevenLabs Services unless a BAA is in place."* **ZRM covers API traffic only — UI/playground traffic is not covered.** ([ElevenLabs HIPAA](https://elevenlabs.io/docs/eleven-agents/legal/hipaa); [ZRM](https://elevenlabs.io/docs/eleven-api/resources/zero-retention-mode)) |
| **Anthropic** | Yes, for HIPAA-eligible services | API / Claude for Enterprise; **claude.ai consumer product not covered** | *"the BAA would not apply to use of the web search functionality"* ([privacy.claude.com](https://privacy.claude.com/en/articles/8956058-i-have-a-zero-data-retention-agreement-with-anthropic-what-products-does-it-apply-to)) |
| **OpenAI** | Yes, specific products | ZDR API endpoints, ChatGPT Enterprise/Edu; **consumer tiers ineligible** | secondary sources only ([Aptible](https://www.aptible.com/hipaa/hipaa-compliant-ai)) |
| **Synthflow** | Claims yes | **UNVERIFIED / conflicting** | Claims SOC 2, HIPAA, PCI DSS L1, ISO 27001, GDPR ([Synthflow](https://synthflow.ai/blog/hipaa-compliant-ai-agents)). Competitors say Enterprise-only or "$1,250/month Agency tier" and disagree with each other. **No Synthflow-published tier gate found.** |
| **Bland AI** | Self-declared | Enterprise | Claims SOC 2 I/II, HIPAA, PCI DSS, GDPR "as of April 2026"; self-hosted infrastructure; "does not share customer call data with third-party AI model providers" ([Bland](https://www.bland.ai/ai-information)). **No published BAA process found.** |
| **Deepgram** | Listed by Vapi as HIPAA-compliant | **UNVERIFIED** | One competitor says no BAA on self-serve plans. Verify directly. |
| **Smith.ai, Goodcall, Rosie, Dialzara** | **UNVERIFIED** | — | No BAA documentation located for any of the four. **Rosie's terms in fact contemplate using call data for training — hard to square with a BAA.** Dialzara advertises HIPAA compliance on its comparison pages but publishes no BAA process. |

> **The chain rule everyone under-weights:** a BAA with the orchestration platform does not cover the STT, TTS and LLM underneath it. *"A gap anywhere in the chain breaks the compliance posture"* ([Cadence](https://gocadence.ai/compare/is-retell-ai-hipaa-compliant)); *"Each layer that touches PHI needs its own BAA"* ([Retell](https://www.retellai.com/blog/10-best-hipaa-compliant-ai-voice-agents-for-healthcare-clinics)). Vapi encodes this contractually.

**Useful nuance:** HIPAA permits **appointment reminders without separate patient authorization** as treatment communications, subject to minimum-necessary and reasonable safeguards ([Retell](https://www.retellai.com/blog/voice-ai-hipaa-appointment-reminders) — vendor source, consistent with standard practice).

**Strategic read:** HIPAA is where this category prices its margin — Vapi charges **$24,000/year** for it. A genuine BAA offered to dental and medical practices is a strong wedge, but it is gated behind Twilio Security/Enterprise Edition *and* our own BAA with the practice *and* BAAs down the whole model chain. **We must not claim HIPAA compliance until all of that is signed.** Vendor self-assertions in this market are common and frequently unbacked — one comparison lists HIPAA status as "Verify directly" for several vendors ([guptadeepak](https://guptadeepak.com/top-5-ai-receptionist-services-for-small-businesses-in-2026-a-practical-comparison)).

### 3.7 Data retention and deletion

**Published vendor practice** — short, tier-gated, treated as an upsell rather than a compliance feature:

| Vendor | Retention posture |
|---|---|
| **Goodcall** | Plan feature: **7-day** call history on Starter, **30-day** on Growth, **unlimited** on Scale ([goodcall.com/pricing](https://www.goodcall.com/pricing)) |
| **Retell AI** | **Per-agent retention configurable from 1 day to 2 years** for transcripts, recordings and logs; per-agent privacy setting (store everything / exclude PII / basic attributes only); **signed and secure recording URLs**; documented GDPR erasure path ([docs.retellai.com](https://docs.retellai.com/general/compliance)). Retell notes it does **not** currently operate services within the EU. |
| **Vapi** | **Call history 14 days**, chat history 30 days on Build ([vapi.ai/pricing](https://vapi.ai/pricing)). **Zero Data Retention** is an org-wide $1,000/month add-on; Vapi's own warning: configure your own storage bucket and subscribe to the `end-of-call-report` webhook **before** enabling, because *"once ZDR is active, any call content you do not send to your own systems cannot be recovered."* ([Vapi ZDR docs](https://docs.vapi.ai/security-and-privacy/zero-data-retention)) |
| **Synthflow** | "Right to erasure (**within 90-day retention policy**)" — implying a ~90-day default ([Synthflow AI Transparency Statement](https://docs.synthflow.ai/ai-transparency)) |
| **My AI Front Desk** | Free tier keeps the **last 20 call logs** ([serviceagent.ai](https://serviceagent.ai/blogs/front-desk-pricing)) |
| **Twilio** | Recordings persist until deleted; REST API deletion is **permanent and unrecoverable**. Under PCI Mode, auto-delete at **one year** ([Twilio Help](https://help.twilio.com/articles/360002588893-Downloading-and-Deleting-Twilio-Call-Recordings)) |
| **Rosie** | Recording/transcript creation **not optional**; uses call data "to monitor quality, improve performance… and for training purposes", and *"**Deidentified** data from call recordings and transcripts may be used to… train our AI technology"* ([Rosie ToS](https://heyrosie.com/legal/terms); [Privacy Policy](https://heyrosie.com/legal/privacy)). No published retention period. |
| **Bland AI** | DPA §2.8 reserves broad rights: Bland may process service data "for its legitimate business purposes… and for any other lawful purposes", and **"Bland is the Controller of such data"** ([Bland DPA](https://www.bland.ai/legal/dpa)). Its ToS grants a **perpetual, worldwide, irrevocable licence** over User Content, defined to include **"call recordings, transcripts, messages"** ([Bland ToS](https://www.bland.ai/legal/terms); [Privacy Policy](https://www.bland.ai/legal/privacy)). **The most vendor-favourable data posture found in this survey.** |

A tester flagged Goodcall's 7-day Starter retention as a real problem: "very limited for reporting or going back to check on a dispute from two weeks ago" ([Lunacal](https://lunacal.ai/blogs/ai-receptionist)). General UCaaS platforms default to about **90 days** ([TeleCloud](https://telecloud.net/blog/call-recording-retention-guide)). **The standard we should hit: at least 30 days on every paid plan, ideally 90, with a documented deletion path.**

**Legal deletion obligations:**
- **GDPR Art. 17** — erasure "without undue delay" (generally read as about one month) where data is no longer necessary, consent is withdrawn with no other lawful basis, or processing was unlawful; exceptions for legal obligations and legal claims ([Art. 17 text](https://gdpr-info.eu/art-17-gdpr); [Irish DPC](http://www.dataprotection.ie/en/individuals/know-your-rights/right-erasure-articles-17-19-gdpr)). Upper fine tier: **€20 million or 4% of global turnover**.
- **GDPR storage limitation** independently forbids keeping recordings longer than necessary — archives must be actively purged ([CallCabinet](https://www.callcabinet.com/blog/us-data-privacy-laws-how-they-influence-call-recording-practices)).
- **CCPA/CPRA right to delete** reaches call recordings and derived transcripts, subject to nine statutory exemptions ([Clarip](https://www.clarip.com/data-privacy/ccpa-erasure-exemptions)). **Operationally this requires locating, exporting and deleting a specific caller's recordings on demand — impossible if audio sits in undifferentiated buckets.**
- **HIPAA sets no call-recording retention period** — the covered entity's own rules govern; HIPAA *documentation* must be kept six years ([Cadence](https://gocadence.ai/compare/is-retell-ai-hipaa-compliant); [Accountable HQ](https://www.accountablehq.com/post/hipaa-compliance-for-zoom-and-video-calls-baa-required-settings-and-best-practices)).
- **EU/UK recording** is generally lawful if you inform the party, but you must state the purpose, document a lawful basis, limit retention, honour access rights and sign a DPA with any third-party recording tool ([Heilo](https://www.heilo.io/know-how/business-call-recording-laws)); **Germany is materially stricter, requiring explicit consent from everyone** ([Exporb](https://exporb.com/blog/en/global-call-recording-laws)).

> **The conflicting-retention trap:** TCPA consent records are commonly advised to be kept **5–7 years** (Retell's ToS contractually requires **5 years**), and Virginia requires **10-year opt-out records** from 1 Jan 2026 — while call audio should be kept **short**. **These are different data classes and must have separate retention policies.** A single "delete everything after 90 days" rule would destroy consent evidence we are contractually required to hold.

**Twilio's platform-side controls:** PII redaction in Conversation Intelligence ([Twilio](https://www.twilio.com/en-us/blog/native-integration-conversational-intelligence-conversationrelay-node)), and Conversation Relay's **AI Nutrition Facts** labels state that for each STT/TTS vendor the **base model is not trained on customer data and customer data is not stored or retained in the base model**, with the customer responsible for human review ([Twilio ConversationRelay docs](https://www.twilio.com/docs/voice/conversationrelay)). That is a genuinely useful thing to be able to tell a nervous SMB owner — **and it is a point of differentiation against Rosie and Bland, both of whom reserve training rights over call content.**

### 3.8 EU AI Act Article 50 — now in force

**Article 50 applies from 2 August 2026 — confirmed by the European Commission itself:** *"Article 50 of the AI Act applies as from 2 August 2026. From that date onwards, providers and deployers of AI systems must comply with the transparency obligations laid down in that provision."* ([European Commission FAQ](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act)). **It has been live for roughly three and a half weeks as of this research date** ([Morgan Lewis](https://www.morganlewis.com/blogs/sourcingatmorganlewis/2026/08/eu-ai-acts-transparency-rules-what-went-into-effect-on-2-august); [Cooley, 2026-08-03](https://www.cooley.com/news/insight/2026/2026-08-03-eu-ai-act-transparency-obligations-take-effect-2-august-2026)).

- **Art. 50(1)** requires providers to design AI systems intended to interact directly with natural persons so that the person **is informed they are interacting with an AI system**, unless obvious to a reasonably well-informed person. The Commission adopted **guidelines on Article 50 on 20 July 2026** (Cooley). Article 50 covers four situations: direct human interaction, synthetic content generation, emotion recognition/biometric categorisation, and deepfakes ([artificialintelligenceact.eu, 2026-05-14](https://artificialintelligenceact.eu/transparency-rules-article-50)).
- **The Digital Omnibus did NOT delay Article 50 generally.** It delayed the **Annex III high-risk regime to 2 December 2027** (Annex I to 2 August 2028) and granted only a narrow grace period: the **Art. 50(2) machine-readable marking obligation**, and only for generative systems already on the market before 2 August 2026, is deferred to **2 December 2026** ([European Commission FAQ](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act); [Jones Walker, 2026-07-16](https://www.joneswalker.com/en/insights/blogs/ai-law-blog/yes-august-2-still-matters-the-eu-approved-a-high-risk-ai-delay-but-most-trans.html); [Gibson Dunn](https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes)).
- **Fines:** up to **€15 million or 3% of total worldwide annual turnover**, whichever is higher ([Cooley](https://www.cooley.com/news/insight/2026/2026-08-03-eu-ai-act-transparency-obligations-take-effect-2-august-2026)).
- **Extraterritorial:** the Act "applies globally to providers, deployers, importers and distributors of AI systems that place AI on the EU market or whose AI outputs are used within the European Union" (Cooley). **A US-only SMB receptionist is generally out of scope; the moment a customer takes EU calls, it is not.**

### 3.9 What vendors put in their terms — and where liability lands

**The uniform pattern: every vendor pushes AI disclosure, recording consent and TCPA compliance onto the customer.** Verbatim:

**Retell AI** — the most detailed and most explicitly customer-shifting ([Retell ToS](https://www.retellai.com/legal/terms-of-service)):
> **§4(c):** "**Customer is solely responsible for obtaining, documenting, and retaining evidence of valid consent before initiating calls through the Platform. Retell AI does not obtain consent on behalf of Customer. Retell AI makes no representation that Customer's consent practices comply with applicable law.**"
> **§5 AI Disclosure to Call Recipients:** "(a) At Call Initiation. Customer must configure AI voice agents to identify, at the beginning of each outbound call: (i) the name of the business… (ii) the purpose of the call. **In some jurisdictions, Customer may be required to disclose that the AI voice agent is artificially generated.** (b) Responsive Communications. Customer must configure AI voice agents to disclose the nature of the AI generated voice agent in response to communications, where AI voice agents are used to respond to consumer calls, where required by law."
> **§5(c):** "**Customer is responsible for monitoring FCC Docket No. 23-362 for updates**…" **§5(d):** "Customer is prohibited from misleading any consumer about the artificial identity of any AI voice agent."
> **§10 Call Recording and Two-Party Consent:** "**Customer must configure AI voice agents to announce recording and obtain verbal consent when calling numbers in two-party consent jurisdictions.**"
> **§12:** "Customer must retain records of consent… **for a minimum of five (5) years**… **Retell AI does not store consent records on behalf of Customer.**"

**Vapi** ([ToS, last updated 2025-02-27](https://vapi.ai/terms-of-service)) — indemnity **names the TCPA explicitly**: "you agree… to indemnify, defend, and hold harmless Vapi… for… your breach of these Terms, any rights of another party, or any applicable law or regulation, **including but not limited to the Telephone Consumer Protection Act of 1991 (TCPA)**…"

**Synthflow** ([AI Transparency Statement](https://docs.synthflow.ai/ai-transparency), written to fulfil EU AI Act Arts. 50–54) — the clearest statement of the split:
> "Synthflow provides configurable greeting and consent messages that customers can use to disclose the use of AI at the start of an interaction, for example: *'Hello, this is an AI assistant from [company name]. I'm not a human but I'm here to help you.'* **Customers deploy and operate the agents they build on Synthflow. It is the customer's responsibility to configure this disclosure in line with the legal requirements that apply to their use case and jurisdiction, including EU AI Act Article 50 and any national or state rules on AI call disclosure.**"

**Twilio** ([AUP](https://www.twilio.com/en-us/legal/aup)): "**Customer is responsible for determining whether the Services offer appropriate safeguards for Customer's use of the Services, including… any safeguards required by applicable law or regulation**… Customer is responsible for its End Users' compliance with this AUP and making its End Users aware of this AUP." [ToS §2.2](https://www.twilio.com/en-us/legal/tos): the customer will "be solely responsible for all use of the Services" and "for all acts, omissions, and activities of your End Users."

**Rosie** ([ToS §f](https://heyrosie.com/legal/terms)): "**Rosie will provide courtesy template notices**… **You decide through your Account settings whether and how to implement such templates** and, if the template is used, the contents thereof. **You are solely responsible for your use of the Recordings.**"

**Bland AI** ([ToS](https://www.bland.ai/legal/terms)): "You are solely responsible for any content you contribute, post, or transmit via the Service." Its AUP prohibits content that "Collects information about Service users without obtaining consent" and that "Impersonates any person or entity."

> **Synthesis — and the part that matters most for us.** In every agreement reviewed, infrastructure (Twilio, Vapi, Retell, Bland) and turnkey (Rosie, Synthflow) alike, the vendor supplies *configurable capability* and the customer carries *the legal duty*. **We are the "Customer" in Twilio's terms, and simultaneously the vendor to our SMB clients — who will assume we configured it correctly. The liability chain terminates on the reseller.** As one practitioner puts it: *"Platform vs. deployer liability: If you're a voice AI platform, your customers' compliance failures may become your liability. If you're deploying someone else's AI, you can't assume the platform has solved compliance for you."* ([Henson Legal](https://www.henson-legal.com/ai-voice-compliance)). We need (a) our own terms allocating recording-consent and AI-disclosure responsibility to the business owner, (b) product defaults that make the compliant path the easy one, and (c) no assumption that Twilio has solved anything for us.

**SOC 2.** Not usually a gate for SMB sales; increasingly one for mid-market and healthcare. In 2026 SOC 2 has "moved from a security badge to a procurement gate", with first-year Type 2 spend for an AI startup typically **$40k–$120k** ([SOC2Auditors](https://soc2auditors.org/insights/soc-2-for-ai-companies); [Nuplay](https://www.nuplay.ai/blogs/ai-voice-agent-compliance-enterprise-soc-2-hipaa-guide)). Sensible posture: pursue it in parallel with sales and be transparent about the roadmap ([Blaxel](https://blaxel.ai/blog/soc-2-compliance-ai-guide)).

### 3.10 Explicitly NOT verified

Carried forward so nobody mistakes these for settled: whether Cal. B&P § 17941's "online" reaches a PSTN call; the status/content of California AB 410 (2025); whether AB 2905 reaches inbound calls; the ADLI imprisonment claim under §17941; whether a general AI-interaction notice survives in Colorado SB 26-189; Maine LD 1727's exact effective date, penalty and private right of action; effective dates for Iowa SF 2417 and Idaho S 1297 (sources differ by a year); New Jersey's general bot-disclosure statute; whether the FCC's AI NPRM remains formally open; the "revoke-all" delay to 31 January 2027; the 2026 federal decision said to re-affirm Michigan's participant exception; Synthflow's actual BAA tier gate; Deepgram's own BAA documentation; HIPAA/BAA availability for Smith.ai, Goodcall, Rosie and Dialzara; whether Twilio `<Pay>`/PCI Mode interoperates with `<ConversationRelay>`; and the outcome of the Otter.ai motion-to-dismiss hearing (scheduled 20 May 2026).

---

## 4. QUALITY / LATENCY STANDARD

### 4.1 The published latency bar

The category has converged on a remarkably tight set of numbers, and they are consistent across vendor claims, independent benchmarks and the underlying human-factors research.

**The human baseline.** In natural human conversation the gap between speaker turns averages **around 200 ms** ([Famulor](https://www.famulor.io/blog/ai-voice-agent-latency-how-fast-your-phone-bot-must-reply) — accessed 2026-08-27). Response gaps under ~500 ms start to feel interruptive; gaps over ~1,500 ms feel inattentive; the natural window is roughly **500–1,200 ms** (same source).

**The production bar.**

| Threshold | Meaning | Source |
|---|---|---|
| **~600 ms end-to-end** | The number the market leader publishes and competitors benchmark against. Measured caller's-last-word to agent's-first-word. | [Retell AI](https://www.retellai.com/blog/turn-taking-voice-ai-hidden-problem) |
| **< 700 ms** | "Reads as conversational" | [Retell AI](https://www.retellai.com/blog/how-voice-ai-handles-hardest-parts-real-call) |
| **> 900 ms** | "Callers notice and disengage" | Same |
| **< 1,200 ms** | Outer bound for a natural conversation; sub-1-second is "the gold standard" | [Lorikeet](https://www.lorikeetcx.ai/articles/voice-ai-multi-step-workflows-2026) |
| **420–600 ms** | Where SMB-tier AI receptionists were reported to sit in Q1 2026 | [CallSphere](https://callsphere.ai/blog/vw9c-smb-ai-adoption-stats-q1-2026-voice-agents) |

Retell publishes ~600 ms as a *measured production figure across ~40 million monthly calls*, attributing a recent 150 ms improvement to a turn-taking model update ([Retell](https://www.retellai.com/blog/how-voice-ai-handles-hardest-parts-real-call)). A 2025 head-to-head put Retell at 180 ms time-to-first-token, 620 ms end-to-end, **140 ms barge-in response**, 45 ms jitter standard deviation ([Retell's own latency face-off](https://www.retellai.com/resources/ai-voice-agent-latency-face-off-2025) — vendor-authored, so the ranking is self-serving even if the metric definitions are useful). Goodcall is independently noted at around 600 ms ([Sonant](https://www.sonant.ai/blog/goodcall-alternative-review)).

**Tail latency matters more than median.** An agent can be fast on average and still produce a clear delay on every twentieth call; P95/P99 outliers shape caller perception because a single embarrassing pause is what sticks ([Famulor](https://www.famulor.io/blog/ai-voice-agent-latency-how-fast-your-phone-bot-must-reply)). **We should be measuring P95, not mean.**

### 4.2 The latency budget, by stage

A representative multi-vendor ("stitched") stack versus a co-located one, measured in production traffic ([Telnyx](https://telnyx.com/resources/voice-ai-agents-compared-latency) — carrier vendor, self-serving on the co-located column, but the stitched-stack budget matches other sources):

| Pipeline layer | Stitched stack | Co-located |
|---|---|---|
| Network ingress + SIP signalling | 150 ms | 45 ms |
| Speech-to-text | 225 ms | 100 ms |
| LLM inference | 650 ms | 225 ms |
| Text-to-speech | 185 ms | 80 ms |
| **Total** | **1,210 ms** | **450 ms** |

The same source reports a carrier-leg isolation test (120 outbound calls per carrier, US-East, June 6–8 2026): **Telnyx p50 71 ms / p95 118 ms; Twilio p50 89 ms / p95 161 ms; Vonage p50 94 ms / p95 152 ms**. Twilio's carrier leg is ~18 ms slower at p50 and ~43 ms slower at p95 than Telnyx. That is a real but small penalty — it is roughly 3% of a 600 ms budget, and it is *not* where a slow agent's time goes.

**Where the time actually goes.** Both Retell and independent write-ups agree: not in STT and not in TTS, but in **turn-taking decisions and LLM time-to-first-token** ([Retell](https://www.retellai.com/blog/how-real-time-voice-ai-works-stt-llm-tts)). A good 2026 LLM hits TTFT of 150–300 ms for a voice-agent prompt, then streams 50–100 tokens/sec, which is faster than people speak — so TTS can start before the model finishes thinking. **None of this works if any stage waits for the previous one to finish.** That is the single most actionable engineering statement in this section.

### 4.3 Turn-taking and interruption (barge-in) — the actual standard

Barge-in as a boolean is the classic production failure ([Hamming's interruption runbook](https://hamming.ai/resources/voice-agent-interruption-handling-runbook), last updated May 2026). The 2026 standard separates several decisions that naive implementations conflate:

- **Turn detection** decides when the system thinks speech started/ended. **Interruption handling** decides what the agent does with that signal while it is already speaking. These are different (Hamming).
- The production answer for turn detection is **a small fast neural model** consuming the audio stream, the partial transcript and conversation context, emitting a probability that the caller has finished — updated dozens of times per second, with the agent's turn starting when confidence crosses a threshold ([Retell](https://www.retellai.com/blog/how-real-time-voice-ai-works-stt-llm-tts)).
- It must handle: prosody (pitch/pace shifts signalling "I'm finishing"), syntactic/semantic completion, **adaptation to the individual caller's pace** (a fixed pause threshold fails either fast or slow talkers), barge-in pickup within tens of milliseconds, and **distinguishing backchannels** ("yeah", "okay", "uh-huh") from real end-of-turn signals ([Retell](https://www.retellai.com/blog/turn-taking-voice-ai-hidden-problem)).
- Retell publishes a **nine-test evaluation** any buyer can run: pause mid-sentence, interrupt, speak fast, speak slow, add background noise, cough, whisper (same source). **This is the acceptance test we should be running against our own agent.**

Other platforms expose the same concepts under different names, which tells us the concept set is the standard: Google Dialogflow CX has end-of-speech sensitivity, smart endpointing, no-speech timeout, barge-in and partial response cancellation; LiveKit splits detection modes, endpointing delay, adaptive interruption handling and VAD; OpenAI Realtime exposes server VAD and semantic VAD with threshold, prefix padding, silence duration and eagerness; Amazon Nova Sonic exposes sensitivity levels waiting roughly 1.5 / 1.75 / 2.0 seconds (all per [Hamming](https://hamming.ai/resources/voice-agent-interruption-handling-runbook)).

### 4.4 STT / TTS choices — what the market picks

**Speech-to-text.** Deepgram Nova-3 is "the most widely deployed STT in commercial voice AI as of 2026" — ~150 ms streaming latency, real-time diarization, strong on noisy phone audio ([Coval](https://www.coval.ai/blog/voice-ai-models-2026)). But there is a real accuracy/latency trade-off and buyers should know it: a Coval benchmark across five STT APIs at 2,400 runs each found the two fastest models on time-to-first-token (Deepgram Nova 3 and Nova 2, median 992 ms) recorded **the highest word error rate at 25.2–25.3%**, while the most accurate (Gradium STT at 2.4% WER) sat at 1,560 ms median TTFT; AssemblyAI Universal Streaming landed at 1,061 ms / 4.2% WER and ElevenLabs Scribe v2 at 2,080 ms / 3.1% WER ([Gradium's writeup of the Coval benchmark](https://gradium.ai/content/stt-api-benchmark-2026-latency-accuracy) — note Gradium is the winner it describes, so treat the ranking cautiously; the trade-off itself is the takeaway). **For a receptionist capturing names, phone numbers and addresses, a 25% WER is a production failure rate that latency savings cannot compensate for.** This is a genuine risk in any Deepgram-default stack, ours included.

**Text-to-speech.**

| Provider | Time-to-first-byte | Quality | Cost tier |
|---|---|---|---|
| ElevenLabs Eleven v3 | 200–400 ms | Top (most natural) | Premium |
| Cartesia Sonic 3 | < 100 ms | High | Mid-premium |
| OpenAI / Google Cloud TTS / Amazon Polly | 150–300 ms | Mid | Low |

([Coval](https://www.coval.ai/blog/voice-ai-models-2026).) ElevenLabs separately claims model latency "as low as 75 milliseconds" ([ElevenLabs](https://elevenlabs.io/blog/twilio-conversation-relay) — vendor claim). Retell's production tiering: platform voices and Cartesia at $0.015/min for fast and natural, ElevenLabs at $0.040/min for highest-fidelity brand voices, with time-to-first-audio in production stacks hitting **100–200 ms** ([Retell](https://www.retellai.com/blog/how-real-time-voice-ai-works-stt-llm-tts)).

Retell's summary line is worth quoting for our own positioning: *"The thing that gives voice AI away in 2026 isn't the voice anymore. It's the timing."*

### 4.5 What Twilio ConversationRelay actually gives us

Read directly from Twilio's own documentation ([twilio.com/docs/voice/twiml/connect/conversationrelay](https://www.twilio.com/docs/voice/twiml/connect/conversationrelay) — accessed 2026-08-27). It reached general availability in **May 2025** ([per the Twilio changelog, cited by Telnyx](https://telnyx.com/resources/voice-ai-orchestration-tools)).

**The model:** a TwiML verb opens a WebSocket to your server; Twilio handles STT and TTS at the edges; your code decides what the agent says.

**Attributes and defaults:**

| Attribute | Values | Default |
|---|---|---|
| `url` (required) | must begin with `wss://` | — |
| `welcomeGreeting` | opening line played on answer | — |
| `welcomeGreetingInterruptible` | `none` / `dtmf` / `speech` / `any` | `any` |
| `language` | BCP-47 | `en-US` |
| `ttsLanguage` / `transcriptionLanguage` | split TTS and STT language | — |
| `ttsProvider` | **Google, Amazon, ElevenLabs** | `ElevenLabs` |
| `voice` | provider-specific | `UgBBYS2sOqTuMpoF3BR0` (ElevenLabs), `en-US-Journey-O` (Google), `Joanna-Neural` (Amazon) |
| `transcriptionProvider` | **Google, Deepgram** | `Deepgram` |
| `speechModel` | `telephony` (Google); `nova-3-general` / `nova-2-general` / `flux` (Deepgram) | `nova-3-general` family |
| **`interruptible`** | `none` / `dtmf` / `speech` / `any` (booleans accepted for back-compat: `true`=`any`, `false`=`none`) | **`any`** |
| **`interruptSensitivity`** | `high` / `medium` / `low` | **`high`** |
| `dtmfDetection` | sends DTMF keypresses over the WebSocket | — |
| `preemptible` | lets the next talk cycle's tokens interrupt the current TTS | `false` |
| `hints` | comma-separated words/phrases to bias STT toward uncommon words, product names, domain terms | — |
| `reportInputDuringAgentSpeech` | `none` / `dtmf` / `speech` / `any` | **`none`** (changed May 2025) |
| `ignoreBackchannel` | prevents short conversational feedback interrupting | `false` |
| `elevenlabsTextNormalization` | `on` / `auto` / `off` | `off` |
| `deepgramSmartFormat` | reformats dates, times, currency, numbers, addresses into conventional written forms | `true` |
| `eotThreshold` | end-of-turn threshold (Deepgram `flux` model) | `0.8` |
| `partialPrompts` | emit partial transcripts | — |
| `speechTimeout` | ms | 600–5000 range documented |
| `intelligenceService` | Conversation Intelligence service SID | — |
| `debug` | subscribe to debugging messages | — |

**WebSocket message types:** `setup`, `prompt` (transcribed caller speech), text token messages (your reply → speech), `dtmf`, `interrupt` events, **speaker events** (`agentSpeaking` / `clientSpeaking`), `tokens-played` (what has actually been spoken aloud — critical for knowing where you were cut off), **switch-language** (live mid-session STT/TTS language change), `end session`, and handoff data carrying custom TwiML parameters out of the session.

**Critical detail Hamming flags and we should act on:** `interruptible` controls whether caller input **stops TTS playback**; `reportInputDuringAgentSpeech` controls whether **your application receives** input while the agent is talking. *"Those are different decisions. A system can listen without stopping playback, or stop playback without preserving enough application context."* ([Hamming](https://hamming.ai/resources/voice-agent-interruption-handling-runbook)). The default of `reportInputDuringAgentSpeech="none"` means that **by default you are blind to what the caller said while your agent was speaking** — if we have not changed this, we are losing context on every interrupted turn.

**Automatic language detection (`multi` mode)** requires `transcriptionProvider="Deepgram"` **and** `ttsProvider="ElevenLabs"`; any other combination throws an error and **ends the ConversationRelay session**. In `multi` mode `lang` returns only the primary tag (`en`, not `en-US`) ([Twilio docs](https://www.twilio.com/docs/voice/twiml/connect/conversationrelay); [Twilio changelog, 2025-10-07](https://www.twilio.com/en-us/changelog/conversationrelay-now-supports-a-configuration-for-automatic-lan)). This is a hard constraint on any multilingual claim we make.

Other documented additions: default language settings for **40+ languages**, SPI message validation returning error 64107 on malformed messages, Google TTS voices updated to Chirp3-HD ([Twilio changelog](https://www.twilio.com/en-us/changelog/new-features-now-available-for-conversationrelay)). ElevenLabs voice tuning is expressed by appending to the voice ID: `voice="ZF6FPAbjXT4488VcRRnw-flash_v2_5-1.2_1.0_1.0"` for model, speed, stability and similarity ([Twilio blog](https://www.twilio.com/en-us/blog/integrate-elevenlabs-voices-with-twilios-conversationrelay)).

**Recording and transcription of ConversationRelay calls — the mechanics.** Twilio's best-practices page confirms ConversationRelay calls can be recorded using the standard Recordings methods ([Twilio, ConversationRelay best practices](https://www.twilio.com/docs/voice/conversationrelay/best-practices)). The clean pattern is `<Start><Recording channels="dual">` placed *before* `<Connect><ConversationRelay>`, which records asynchronously while the agent runs, and — critically — **the recording can be stopped, paused and resumed by posting to the Recordings resource** ([Twilio launch post for `<Start><Recording>` GA](https://www.twilio.com/en-us/blog/products/launches/general-availability-start-recording)). That pause/resume capability is the mechanism for both PCI card-capture handling and any state-specific consent behaviour (§3). Note `<Record>` is the wrong verb here — it is synchronous, blocks other TwiML, and records only the caller leg.

Setting the `intelligenceService` attribute wires ConversationRelay natively into Conversation Intelligence, which transcribes the session (transcript `source` is literally `ConversationRelay`), runs Language Operators, and offers **PII redaction** plus a setting for whether your data is used to improve Twilio's products ([Twilio blog](https://www.twilio.com/en-us/blog/native-integration-conversational-intelligence-conversationrelay-node); [Transcript resource docs](https://www.twilio.com/docs/conversation-intelligence-classic/api/transcript-resource)). Use **dual-channel** recordings — Conversation Intelligence does no speaker diarization, and mono recordings reduce transcription accuracy (Transcript resource docs).

**What ConversationRelay does NOT give us — and every one of these is our job:** the LLM, the turn-taking model beyond `interruptSensitivity`/`eotThreshold`, the dashboard, the knowledge base, calendar/CRM integrations, call summaries, analytics, spam screening, the business-hours engine, transfer logic, and every compliance control in §3. Twilio supplies the pipe and the ears and mouth; the product is entirely ours. Telnyx's neutral framing: it is "the managed bridge between the Twilio carrier network and your AI application" and is best for "teams already running voice on Twilio that want to add an AI agent without replatforming" ([Telnyx](https://telnyx.com/resources/voice-ai-orchestration-tools)).

### 4.6 Quality metrics beyond latency — the published benchmark thresholds

Latency is the metric everyone quotes, but the industry has a fuller, converged set of quality thresholds. These are the numbers we should be instrumenting against.

| Metric | Target threshold | Definition |
|---|---|---|
| **Word Error Rate (WER)** | **< 10%** normal, < 15% with noise | (Substitutions + Deletions + Insertions) / total words |
| **Task Success Rate** | **> 85%** | Successful completions / attempts |
| **First Call Resolution** | **> 75%** | Single-interaction resolutions / total |
| **Containment Rate** | **> 70%** | Calls resolved without human escalation |
| **Barge-in detection** | **> 95%** | True detections / total interruptions |
| **Barge-in recovery** | > 90% | Clean recovery after interruption |
| **Reprompt rate** | **< 10%** | Clarification requests / total turns |
| **Hallucination rate** | **< 2%** general, **< 0.5% healthcare** | Hallucinated responses / total responses |
| **Tool-call success** | **> 99%** for critical tools | e.g. the calendar booking call |
| **Fallback rate** | < 5% | |
| **Error rate** | < 1% | |
| **Sentiment trajectory** | improving/stable in > 80% of calls | |
| **Latency P50 / P95** | < 1.5s / < 5s end-to-end; **TTFA < 800 ms** | |
| **TTS Mean Opinion Score** | 4.3–4.5 | Can be predicted at scale with UTMOS or NISQA instead of human panels |

([Hamming's metrics reference](https://hamming.ai/resources/how-to-evaluate-voice-agents-2026) and [formulas guide](https://hamming.ai/resources/voice-agent-evaluation-metrics-guide); corroborated by [Bluejay](https://getbluejay.ai/resources/metrics-every-voice-ai-team-should-track) — "containment rates above 70% and FCR benchmarks of 80%+" — and [Famulor](https://www.famulor.io/blog/how-to-test-and-evaluate-an-ai-voice-agent-in-2026). All accessed 2026-08-27. These are vendor-published benchmarks from testing-tool companies, i.e. firms selling the measurement; the thresholds are broadly consistent across independent sources, which is why I trust the shape if not every decimal.)

**Appointment-scheduling-specific benchmarks** are the relevant vertical for a receptionist, and Hamming publishes per-use-case targets. For e-commerce/order taking they list turn latency P95 < 700 ms and WER < 6% for product names and order numbers; for healthcare, task completion > 85%, hallucination < 0.5%, compliance score > 99%, WER < 5% ([Hamming](https://hamming.ai/resources/voice-agent-evaluation-metrics-guide)).

**Two warnings worth internalising:**

1. **Containment without resolution is a failure disguised as success.** If containment is high but FCR is low, the agent is holding people on the line without resolving anything — "going in circles" ([ElevenLabs](https://elevenlabs.io/blog/voice-agent-evaluation-framework-6-pillars-explained)). Never report containment alone.
2. **Transcript-based testing is insufficient.** "Prosody, interruptions, accents, and latency effects only surface on real audio. Text-based tests miss exactly the failures that occur live." ([Famulor](https://www.famulor.io/blog/how-to-test-and-evaluate-an-ai-voice-agent-in-2026))

**Testing is itself a standard.** The documented three-level program is: offline simulation with real audio (happy paths, edge cases, and adversarial cases — accents, background noise, interruptions, uncooperative callers), online production monitoring with threshold alerts on STT confidence/intent accuracy/latency percentiles/escalation rate, and human-in-the-loop spot checks for the ~20% that cannot be automated ([Famulor](https://www.famulor.io/blog/how-to-test-and-evaluate-an-ai-voice-agent-in-2026)). Retell ships "Simulation Testing" on its free tier ([retellai.com/pricing](https://www.retellai.com/pricing)) and Smith.ai meters "test calls" and "simulated calls" as first-class plan entitlements alongside real calls ([smith.ai](https://smith.ai/pricing/ai-receptionist)) — meaning **a simulated-call harness is now a shipped product feature, not just internal tooling.** A dedicated tool category exists to serve this (Hamming, Coval, Cekura, Braintrust and others, from ~$30/user/month to enterprise) ([Speechmatics' survey of 11 testing platforms](https://www.speechmatics.com/company/articles-and-news/de-risk-your-voice-agent-11-best-voice-agent-testing-platforms)).

---

## 5. PRICING STANDARD

### 5.1 What SMBs actually pay in 2026

Consolidating vendor-own pricing pages where available:

| Vendor | Entry price | What's included | Overage | Model |
|---|---|---|---|---|
| Dialzara | **$29/mo** | 60 min | $0.48/min | Minutes bundle |
| Rosie | **$49/mo** | 250 min | $0.25/min (not published on the pricing page) | Minutes bundle |
| Trillet | $49/mo | 150 min | $0.20/min | Minutes bundle |
| RingCentral AI Receptionist | $59/mo | 100 min | $0.50/min, 30-sec increments | Minutes bundle |
| Goodcall | **$79/mo** (Starter) → $129 → $249 | **Unlimited minutes**, capped at 100/250/500 *unique callers* | $0.50 per extra unique caller | Unique-caller cap |
| My AI Front Desk / Frontdesk | $99/mo (disputed — see §1.2) | 200 voice min | $0.25/min | Minutes bundle |
| Smith.ai (AI) | $150/mo Pro | 75 calls @ $2.00 | $2.50/call | **Per call** |
| Rosie Scale | $149/mo | 1,000 min + booking + transfers | $0.25/min | Minutes bundle |
| Loman (restaurants) | $199/mo | flat, no per-minute | — | Flat |
| Rosie Growth | $299/mo | 2,000 min | $0.25/min | Minutes bundle |
| Slang.ai (restaurants) | $399/mo per location | Core; Premium $599 | no per-call overage | Flat per location |
| Sameday (trades) | $449–$789/mo | flat, no meter | — | Flat |
| **Ruby (human benchmark)** | **$250/mo** | **50 minutes** | unpublished | Per minute |

Sources: vendor pricing pages for [Rosie](https://heyrosie.com/pricing), [Goodcall](https://www.goodcall.com/pricing), [Dialzara](https://dialzara.com/pricing), [Smith.ai](https://smith.ai/pricing/ai-receptionist); [Slang.ai via CloudTalk verified Aug 2026](https://www.cloudtalk.io/blog/slang-ai-review); [Sameday](https://sameday.ai/best-ai-receptionist-for-home-services); [Loman](https://loman.ai/blog/ai-phone-ordering-systems-restaurants); [Ruby via CloudTalk verified 2026-08-24](https://www.cloudtalk.io/blog/ruby-receptionist-review); [Trillet](https://trillet.ai/blogs/best-ai-receptionist-for-small-business-2026); [RingCentral pricing via Dialzara comparison](https://dialzara.com/compare/dialzara-vs-ringcentral).

**The consensus band.** Multiple independent aggregations put the typical SMB spend at **$49–$199/month**, with the whole category spanning roughly $25–$500 ([guptadeepak](https://guptadeepak.com/top-5-ai-receptionist-services-for-small-businesses-in-2026-a-practical-comparison): "Most SMBs spend between $49 and $199 per month"; [Layer3Labs](https://www.layer3labs.io/guides/ai-answering-service-cost): "$79 to $300 per month for small businesses"; [getaira](https://www.getaira.io/blog/ai-receptionist-pricing-guide): "$24.95 to over $325 per month at the entry level alone").

**Effective per-minute.** Bundled SMB plans land at roughly **$0.15–$0.20/min** at plan volume (Rosie's three tiers compute to $0.149–$0.196/min per [CloudTalk](https://www.cloudtalk.io/blog/rosie-ai-answering-service-pricing)), with overages at $0.20–$0.50/min. Managed per-call services run **$1.67–$3.00 per call** (Smith.ai's own published table), and human services $3.45–$5.00/min (Ruby).

### 5.2 What "included" usually means — and the traps

This is where the category is least honest, and where we can differentiate by being straight.

- **"Unlimited minutes" is never unlimited.** Goodcall's unlimited minutes are capped by **unique callers per month** (100/250/500), then $0.50 per extra unique caller ([goodcall.com/pricing](https://www.goodcall.com/pricing)). It is a genuinely clever model for high-repeat-caller businesses and a trap for businesses with many one-time callers.
- **Rounding.** Rosie rounds every call **up to the next 60 seconds** ([CloudTalk's reading of Rosie's Terms](https://www.cloudtalk.io/blog/rosie-ai-answering-service-pricing)). On a business whose calls average 40 seconds that is a ~50% effective price increase.
- **Automatic tier upgrades.** Rosie bumps you to the next plan rather than interrupting service — presented as customer-friendly, and it is, but combined with a **missing spend cap** it means the bill can move without an explicit decision (same source; Rosie's own framing at [heyrosie.com/blog/rosie-ai-vs-goodcall](https://heyrosie.com/blog/rosie-ai-vs-goodcall)).
- **Overage rates hidden from the pricing page.** Rosie's $0.25/min overage is confirmed by third parties but is not on the pricing page ([serviceagent.ai](https://serviceagent.ai/blogs/rosie-ai-pricing)).
- **The real entry tier is not the advertised one.** Rosie's $49 Professional sends an SMS booking link but **does not book during the call** and has no transfers; the functional entry price for a service business is $149 ([serviceagent.ai](https://serviceagent.ai/blogs/rosie-ai-pricing)). Dialzara reserves warm transfer for $99. Smith.ai gates custom prompting to Enterprise.
- **Per-feature add-on menus.** Smith.ai reportedly charges separately for booking, recording, SMS, bilingual and payments — each $0.25–$1.50 per call ([CloudTalk](https://www.cloudtalk.io/blog/my-ai-front-desk-pricing)). A "$150/mo" plan with four add-ons at 150 calls is a very different number.
- **Metering non-real calls.** Smith.ai's plan table meters test calls and simulated calls alongside real ones ([smith.ai](https://smith.ai/pricing/ai-receptionist)).
- **Setup fees are essentially dead.** AIRA, Dialzara, Rosie and My AI Front Desk all have zero setup cost ([getaira](https://www.getaira.io/blog/ai-receptionist-pricing-guide)). Charging one would be an outlier.
- **Free trials are standard**, 7–14 days: Voksha, Smith.ai, Dialzara, Rosie, My AI Front Desk, Goodcall and Synthflow all offer them; Ruby and PATLive do not ([Voksha](https://voksha.com/guide/best-ai-receptionists-2026)). Smith.ai goes further with a permanently free 25-real-calls/month tier ([smith.ai](https://smith.ai/pricing/ai-receptionist)).
- **No contract / cancel anytime is the norm** (Dialzara and Retell state it explicitly).

### 5.3 Builder-platform pricing — verified from vendor pricing pages

These are the platforms a competitor would build on instead of ConversationRelay, so their pricing is our direct cost comparison. All read from the vendors' own pricing pages on 2026-08-27.

**Retell AI** ([retellai.com/pricing](https://www.retellai.com/pricing)) — Pay-as-you-go **$0.07–$0.31/min** for voice agents, $0.002+/msg for chat, $10 free credits, **20 concurrent calls included**. Add-ons: phone numbers $2.00/mo, extra concurrency $8.00/concurrency/mo, knowledge bases $8.00/KB/mo (first 10 free), SMS $0.01/msg plus $20.00/mo for Retell SMS, verified phone number $10.00/mo. **Critically for §3: PII redaction, opt-out recording & transcription, custom data retention, HIPAA/BAA, SSO, RBAC, and custom MSA/DPA/BAA are all Enterprise-only** — none are available on pay-as-you-go.

**Vapi** ([vapi.ai/pricing](https://vapi.ai/pricing)) — **$0.05/min hosting** plus model provider costs "at cost ($0 if you bring your own API key)", SMS/chat $0.005/msg, **10 concurrency included + $10/line/month**. Data retention on the Build plan is **call history 14 days, chat history 30 days**. Compliance add-ons are priced brutally: **HIPAA $2,000/month** and **Zero Data Retention $1,000/month**, on *both* Build and Scale. SOC 2, PCI, SSO and RBAC come with Scale (annual contract).

**Bland AI** — bundles LLM, STT and TTS into one per-minute number with telephony separate: **Start $0.14/min** (no platform fee, 10 concurrent, 100 calls/day, 10 knowledge bases), **Build $0.12/min + $299/mo** (50 concurrent, 2,000 calls/day), **Scale $0.11/min + $499/mo** (100 concurrent, 5,000 calls/day), Enterprise custom ([omidsaffari's reading of bland.ai/pricing, 2026-08-18](https://omidsaffari.com/blog/vapi-pricing); [bland.ai/pricing](https://www.bland.ai/pricing)).

**Synthflow — important correction.** Third-party reviews still circulate Starter/Pro/Growth tiers at $29–$799/month (e.g. [tested.media](https://tested.media/synthflow-ai-review) quoting $99/$299/$799). **Those tiers no longer exist.** Synthflow's own pricing page as of 2026-08-27 shows a single option: *"Enterprise contracts start at $30,000 annually. Final pricing is scoped around call volume, concurrency, telephony setup, integrations, security needs, and launch support."* ([synthflow.ai/pricing](https://synthflow.ai/pricing)). CloudTalk documented this withdrawal — "Every self-serve tier has been withdrawn" ([CloudTalk, verified 2026-08-14](https://www.cloudtalk.io/blog/synthflow-ai-review)). **Synthflow has left the SMB self-serve market entirely and moved upmarket.** That is a meaningful opening in the segment we sell into, and any competitive analysis quoting Synthflow SMB tiers is out of date.

The pattern across all four: **the advertised headline rate is the platform fee only**, and realistic production cost lands at **$0.11–$0.31/min** once LLM, STT, TTS and telephony are added ([Retell's own docs acknowledge $0.11–$0.31](https://www.coval.ai/blog/retell-ai-review-2026-features-pricing-and-when-to-use-it); [Bland's pricing page makes the same argument about its rivals](https://www.bland.ai/pricing)).

### 5.4 The raw cost stack — our actual margin

**Twilio, read from Twilio's own US pricing pages** ([twilio.com/en-us/voice/pricing/us](https://www.twilio.com/en-us/voice/pricing/us) and [twilio.com/en-us/pricing](https://www.twilio.com/en-us/pricing), both accessed 2026-08-27; Twilio's page states "Pricing current as of August 2026"):

| Item | US price |
|---|---|
| **Conversation Relay** | **$0.07 / min** |
| Receive call, local number | $0.0085 / min |
| Receive call, toll-free | $0.0220 / min |
| Make call, US/Canada | $0.0140 / min |
| Local phone number | $1.15 / month |
| Toll-free phone number | $2.15 / month |
| Call recording | $0.0025 / min |
| Recording storage | $0.0005 / min / month |
| Streaming (real-time) transcription | $0.027 / min |
| Batch transcription | $0.024 / min |
| Answering machine detection | $0.0075 / call |
| SMS (send or receive) | from $0.0083 / message |
| Emergency calling | $0.75 / month / number |
| Pay Connectors (card payments) | from $0.150 / transaction |

Note the ConversationRelay $0.07/min **includes the STT and TTS** at the edges — that is the point of the product — so it is not additive with a separate Deepgram/ElevenLabs bill unless you bypass it.

**LLM cost.** Per-minute LLM inference for a voice agent runs roughly **$0.003 to $0.16/min** depending entirely on model choice — Retell's published component menu spans GPT-5-nano at $0.003 to a fast frontier model at $0.160 ([Cekura's breakdown of Retell's components](https://www.cekura.ai/blogs/retell-ai-pricing-per-minute)). A GPT-4o-class model at typical conversational token volumes is **$0.01–$0.03/min** ([PortaOne](https://blog.portaone.com/ai-voice-cost-per-minute)). Retell notes the swing bluntly: choosing Claude Sonnet over Gemini Flash Lite moves LLM cost **27×** ([checkthat.ai](https://checkthat.ai/brands/retell-ai/pricing), last updated 2026-08-07).

**Our cost per minute, built up:**

| Component | Low | High |
|---|---|---|
| Twilio inbound local voice | $0.0085 | $0.0085 |
| Twilio ConversationRelay (incl. STT + TTS) | $0.07 | $0.07 |
| LLM | $0.003 | $0.03 |
| Recording + storage | $0.003 | $0.003 |
| **Total per minute** | **≈ $0.085** | **≈ $0.112** |

Plus **$1.15/month** per local number, and SMS at ~$0.0083 per notification message.

**The margin picture.** At a typical SMB profile of 250 minutes/month:

- Our raw cost: **≈ $21–$28/month** plus number and SMS — call it **$23–$30 all-in**.
- Market price for that volume: **$49 (Rosie Professional)** to **$79–$129 (Goodcall)**.
- **Gross margin at $49: roughly 40–55%. At $99: roughly 70–77%. At $149: roughly 80–85%.**

That is a healthy but not extraordinary structure, and it has three implications worth stating plainly:

1. **A flat-rate plan with genuinely unlimited minutes is dangerous for us in a way it is not for Goodcall.** Goodcall can offer unlimited minutes because it caps unique callers. At $0.085–$0.112/min of hard cost, an unlimited-minutes plan at $79 breaks even at ~700–930 minutes/month. Any flat plan needs a cap on *something*.
2. **LLM choice is the single biggest margin lever we control** — a 27× spread on one line item. Model routing (cheap model for FAQ turns, expensive model for booking/edge cases) is worth real money.
3. **We cannot win on price against Goodcall/Dialzara and should not try.** Dialzara at $29 for 60 minutes is $0.48/min at the margin; Rosie at $49 for 250 is $0.196/min. The defensible position is at **$99–$199 with booking, warm transfer and vertical integration included on the entry plan** — precisely the gap the competitors have left open by tier-gating those features.

**The ROI story the whole category sells** (and which we will be expected to match): a full-time in-house receptionist costs roughly **$3,500–$4,500/month fully loaded** against a US median salary near $37,000/year ([Layer3Labs](https://www.layer3labs.io/guides/ai-answering-service-cost)); an AI receptionist is a 90–98% cost reduction. Supporting demand-side statistics commonly cited: ~62% of small-business calls go unanswered at peak, ~85% of voicemail-bound callers never leave a message, 30–40% of calls arrive after hours ([Magicline compilation](https://www.magicline.ai/blog/ai-receptionist-statistics-2026)); leads reaching an AI answering assistant are **7× more likely to engage** than leads sent to voicemail (CallRail via PR Newswire, [cited by Cira](https://www.hicira.com/missed-call-statistics)). These are marketing-sourced figures compiled by vendors — directionally sound, but I would not put a specific percentage in a customer proposal without re-verifying the primary source.

### 5.5 White-label / agency economics (relevant to how we would sell this)

There is an established reseller tier, and its pricing tells us what an agency-delivered AI receptionist is worth wholesale:

| Platform | White-label price | Included |
|---|---|---|
| Trillet | Studio $99/mo (3 workspaces); **Agency $299/mo, unlimited workspaces**, 300 minutes | Custom domains, branded client experience, client workspaces, agency billing |
| Autocalls | **$419/mo**, 3,500 minutes included | Agency branding, client management, Stripe rebilling, unlimited subaccounts |
| VoiceAI Connect | ~$199/mo | Custom domains, branded dashboards, Stripe Connect billing, no per-client platform fee |
| My AI Front Desk / Frontdesk | **from ~$500/mo**, apply-based, custom | Custom domain, Stripe rebilling, unlimited client subaccounts |
| Synthflow | **$2,000/mo add-on** (or included on Enterprise) | White-label reselling |

([Stammer's survey of white-label platforms](https://stammer.ai/post/best-white-label-ai-receptionist-platforms); [Autocalls](https://autocalls.ai/article/my-ai-front-desk-pricing); [tooliverse on Synthflow](https://tooliverse.ai/tools/synthflow) — all accessed 2026-08-27; all are vendor or competitor pages, so verify before relying on any single figure.)

**What this means for us.** Building on ConversationRelay directly, our marginal cost per client is a phone number ($1.15/mo) plus usage (~$0.085–$0.112/min) — **no per-seat platform fee at all**. An agency reselling Autocalls pays $419/mo for 3,500 minutes ($0.12/min) before their own margin; we pay ~$0.10/min with no floor. That is a structural advantage over agency competitors, and it is the strongest commercial argument for having built on Twilio rather than reselling. It only holds if the multi-tenant dashboard, per-client branding and billing separation actually exist — which is exactly what §2 measures.

**Build-vs-buy, for honesty about our own position.** A competitor's analysis puts a from-scratch Twilio ConversationRelay build at 120–180 developer hours and ~$15,000 before launch, against 40–80 hours on Vapi ([CoreiBytes](https://blog.coreibytes.com/blog/vapi-vs-twilio-conversationrelay-real-cost-service-businesses) — written to sell a packaged product, so the numbers flatter their conclusion). The relevant point for us is not the number but the structure: **our per-minute cost advantage over Retell/Vapi-based competitors is real (~$0.09 vs ~$0.13–$0.31) but it is paid for in engineering time, and it only converts into a business if the layer-2 product around it — dashboard, onboarding, integrations, compliance — is actually finished.**

---

## 6. GAP CHECKLIST — the industry-standard checklist

One numbered list. **[MUST]** = a product cannot be sold to a general business without it. **[SHOULD]** = the 2026 competitive standard; missing several of these makes us the cheap option. **[NICE]** = differentiator or vertical-specific. Each item names the section it comes from so the evidence is one jump away.

### A. Core call handling

1. **[MUST]** Answer 24/7/365 with **unlimited concurrent calls** — never a busy signal. *(§1.3)*
2. **[MUST]** Custom greeting using the business's name, plus a selectable voice and agent name. *(§1.3, §2.1)*
3. **[MUST]** Business hours with a **distinct after-hours flow**, holiday overrides and correct timezone — 30–40% of local-service calls arrive after hours. *(§1.3, §2.1)*
4. **[MUST]** Answer FAQs from a knowledge base built from **the business's own website** (owners will not hand-author an FAQ). *(§1.3, §2.3)*
5. **[MUST]** Structured message taking — name, number, reason — not an audio blob. *(§1.3)*
6. **[MUST]** **Transfer to a human**, at minimum blind transfer, always reachable. Weak escalation is the single most common caller complaint on record. *(§1.3, §1.7)*
7. **[MUST]** Keep the business's existing number via conditional call forwarding, with the dashboard offering forward-all / after-hours-only / busy-or-unanswered. *(§1.3, §2.1)*
8. **[MUST]** Spam and robocall screening. *(§1.3)*
9. **[SHOULD]** **Warm transfer** — brief the human before connecting. *(§1.4)*
10. **[SHOULD]** **In-call appointment booking into a real calendar**, not "we'll text you a link". This is the sharpest dividing line in the 2026 market. *(§1.4)*
11. **[SHOULD]** Bilingual EN/ES minimum, auto-detected. **Constraint: on ConversationRelay, `multi` language mode requires `transcriptionProvider="Deepgram"` AND `ttsProvider="ElevenLabs"` — any other combination errors and kills the session.** *(§1.4, §4.5)*
12. **[SHOULD]** SMS to the caller during/after the call (booking link, address, forms). *(§1.4)*
13. **[SHOULD]** Escalation depth — waterfall to multiple numbers, and an emergency/on-call path for trades. *(§1.4, §2.1)*
14. **[NICE]** Caller memory across calls — recognise a repeat caller and their history. The clearest available differentiator; only Avoca, Allo and Dialzara have it. **Check it against California SB 243 scope first (§3.2).** *(§1.4, §1.7)*
15. **[NICE]** Outbound calling — treat as a **separate product with a separate compliance project** (§3.3), never a toggle on the inbound plan. *(§1.6)*
16. **[NICE]** Payment capture. Default answer is **no** — see item 40. *(§1.6, §3.5)*

### B. Owner dashboard

17. **[MUST]** Call log with **audio playback + full transcript + AI summary on every call**, searchable. *(§2.1)*
18. **[MUST]** Message/lead inbox with structured fields and export. *(§2.1)*
19. **[MUST]** Self-service editor for greeting, agent identity, business info and FAQ — no support ticket required. *(§2.1)*
20. **[MUST]** Hours/holidays editor with an explicit timezone. **This is the weakest capability in the entire category and therefore uncontested whitespace** — Frontdesk has *no first-class business-hours object at all*, Rosie's holiday overrides are unverified, and of the four developer platforms only Synthflow has an hours panel (and it has no holidays). Best-in-class to aim at: per-holiday available/unavailable with a pre-holiday reminder email (Smith.ai), holidays as *behavioural exceptions* with emergency-only booking and fee overrides (Avoca), or daily auto-import of special hours from Google/Yelp (Goodcall). *(§2.1)*
21. **[MUST]** Transfer-rule editor: destinations, conditions, **timeout settings**, warm-vs-blind. *(§2.1)*
22. **[MUST]** Notification settings — email + SMS per call, **multiple recipients**, instant vs digest. Instant is the point; a 5pm digest defeats the product. *(§2.1)*
23. **[MUST]** Usage against plan and overage position, visible **before** the invoice. *(§2.2)*
24. **[MUST]** Basic analytics: call volume over time, duration, peak hours. *(§2.2)*
25. **[SHOULD]** Outcome analytics — resolution/containment rate, **transfer rate and transfer success rate**, bookings created. Report containment **only** alongside resolution; containment without resolution is a caller going in circles. *(§2.2, §4.6)*
26. **[SHOULD]** **Prescriptive analytics** — say what a bad number means and what to change (Webex's pattern). Cheap to build, rare in the market. *(§2.2)*
27. **[SHOULD]** **A hard spend cap the owner controls** — one that rejects calls rather than billing on. **Essentially absent from the whole category:** only Bland ships one; Synthflow states outright that its thresholds are "triggers, not spending caps"; Rosie auto-upgrades tiers with no cap at all. Pair it with Frontdesk's alerting pattern (email at 50% / 75% / 100% of a Max Usage Limit). Cheap to build, genuine trust feature, nobody has it. *(§2.2)*
27a. **[SHOULD]** **Close the knowledge-gap loop** — log every question the agent couldn't answer, rank by frequency, and let the owner turn it into an FAQ in one click with a link to the example call. **The highest-leverage feature found in the entire dashboard survey, and only three vendors ship it** (Smith.ai self-healing FAQs, RingCentral Unresolved Questions, Goodcall Teachable Topics). This is what makes the agent get better without the owner thinking about it. *(§2.1)*
28. **[SHOULD]** Multi-location / multi-number / multi-agent from one dashboard, each with its own hours, greeting and routing. *(§1.4, §2.1)*
29. **[SHOULD]** Team members with **role-based permissions**. *(§2.1)*
30. **[SHOULD]** Retention of call detail **≥30 days on every paid plan, ideally 90** — a 7-day floor cannot settle a two-week-old dispute. *(§2.2, §3.7)*
31. **[NICE]** Native mobile app with push alerts and **full agent configuration from the phone**. Only **Rosie** documents true configure-from-mobile; Goodcall, Avoca, Frontdesk, Dialzara, Slang.ai, Sameday, Loman and **all four developer platforms ship no app at all**. A third party sells an iOS app purely to monitor Retell/Vapi/Synthflow, which tells you how real the gap is. *(§2.1)*
32. **[NICE]** On-site answer rate — measure how well the *human* team answers, not just the AI. *(§2.2)*

### C. Onboarding

33. **[MUST]** Self-serve setup in **under 15 minutes**: website URL → auto-built knowledge base → review/correct → greeting → forward number → live. *(§2.3)*
34. **[MUST]** A **test-call path before go-live** — ideally a hard gate, as IONOS does ("deployment remains locked until a test call is successfully placed"). Prescribe the scenarios: an FAQ, hours/policy, a booking, a transfer to verify the escalation line, **and an out-of-scope question to test guardrails**. **Critically, test calls must not pollute production** — register test numbers so their calls stay out of the real call log and cannot create real bookings (Avoca's pattern, the best-designed testing feature in the survey), and meter them separately from billable minutes rather than silently consuming the customer's plan. *(§2.3)*
35. **[MUST]** An explicit **review-and-correct pass** on scraped data. Skipping it is the documented cause of day-one mistakes, and the scraper cannot read text in images, PDFs or dynamic scripts. *(§2.3)*
36. **[SHOULD]** Industry templates (HVAC after-hours, dental booking, legal intake, salon, restaurant…). Competitors ship 20–88+. *(§2.3)*
37. **[SHOULD]** **Sequence A2P 10DLC honestly.** Twilio's own quickstart warns campaign review takes **10–15 days**, and from 30 June 2026 registration requires public privacy-policy and terms URLs. Voice can be live in 15 minutes; SMS cannot. Say so in the flow rather than letting it look broken. *(§2.3, §3.4)*
38. **[NICE]** AI-assisted configuration — describe the business in prose, the system builds the agent. *(§2.1)*

### D. Compliance — the non-negotiables

39. **[MUST]** **Recording/transcription disclosure played on 100% of calls, default ON.** The all-party-consent state list is genuinely contested (sources say 11, 12, 13 or 15 and disagree on NV, CT, MI, OR, VT) — **do not hard-code a state list**. Universal disclosure satisfies all 50 states at once, and it is what Twilio itself recommends. Note **transcripts count as recording**, and California reaches interstate calls with penalties of $2,500 + $5,000 civil per violation; Florida and Massachusetts are felonies. *(§3.1)*
40. **[MUST]** Build the **"caller declines recording" branch** — an agent that keeps recording after a refusal is the untested exposure most vendors have ignored. *(§3.1)*
41. **[MUST]** **AI disclosure in the greeting, configurable, default ON** ("I'm an AI assistant for [business]"). Required now in Utah for licensed occupations **orally at the start**, in Maine for voice bots that could mislead, and under **EU AI Act Art. 50 which has been in force since 2 August 2026**; matches the FCC's proposed federal rule in advance. Costs one sentence. *(§3.2, §3.3)*
42. **[MUST]** **Do not take card numbers by voice.** If a customer needs payments, send an SMS payment link, or route the payment leg to Twilio `<Pay>` on an **isolated account** — because **PCI Mode is irreversible per account and disables native transcription**, which would destroy the core product. *(§3.5)*
43. **[MUST]** Detect and log a **spoken opt-out** ("stop calling me", "take me off your list"). Under the April 2025 FCC rules revocation may be made by any reasonable method, must be honoured within 10 business days, and crosses channels. An agent that can't hear it is a compliance gap. *(§3.4)*
44. **[MUST]** Separate **informational** SMS (booking confirmations — prior express consent) from **marketing** SMS (prior express *written* consent). Never blend a promotion into a confirmation. *(§3.4)*
45. **[MUST]** **Our own terms** allocating recording-consent, AI-disclosure and TCPA responsibility to the business owner — every vendor surveyed does this, and **the liability chain terminates on the reseller**. *(§3.9)*
46. **[MUST]** Retention policy that separates data classes: **call audio short (30–90 days), consent records long (5+ years; Retell contractually requires 5, Virginia requires 10-year opt-out records)**. A single global delete rule would destroy evidence we are required to hold. *(§3.7)*
47. **[MUST]** Ability to **locate, export and delete one specific caller's** recordings and transcripts on demand (CCPA/CPRA and GDPR Art. 17). Impossible if audio sits in undifferentiated buckets — this is an architecture decision, not a policy one. *(§3.7)*
48. **[SHOULD]** Do **not** enable speaker identification, diarization or voice-embedding storage without a **BIPA** analysis — Illinois treats a voiceprint as a biometric identifier at $1,000–$5,000 per person per violation with a private right of action, and there is an active 2025–26 litigation wave. *(§3.1)*
49. **[SHOULD]** Tell customers plainly that **their call data does not train the base models** — Twilio's AI Nutrition Facts support this, and it differentiates us from Rosie and Bland, both of whom reserve training rights over call content. *(§3.7)*
50. **[SHOULD]** For medical/dental: a real **BAA chain** — Twilio (requires Security or Enterprise Edition) **plus** every model/STT/TTS vendor **plus** our BAA with the practice. ConversationRelay has been HIPAA-eligible since 17 March 2025. **Claim nothing until all of it is signed.** Competitors charge heavily here — Vapi wants $2,000/month. *(§3.6)*
51. **[NICE]** SOC 2 Type II — not a gate for a plumber, increasingly one for mid-market and healthcare; $40k–$120k first year. Pursue in parallel with sales, be transparent about the roadmap. *(§3.9)*
52. **[NICE]** EU readiness (Art. 50 + GDPR DPA + EU hosting) only if a customer takes EU calls. *(§3.8)*

### E. Quality and latency

53. **[MUST]** **End-to-end response under 700 ms**; ~600 ms is where the market leader sits and what competitors benchmark against. Above 900 ms callers audibly disengage. *(§4.1)*
54. **[MUST]** Measure and report **P95, not just median** — one embarrassing pause per twenty calls is what a caller remembers. *(§4.1)*
55. **[MUST]** Real barge-in: caller speech stops TTS. On ConversationRelay `interruptible` defaults to `any` and `interruptSensitivity` to `high`. *(§4.3, §4.5)*
56. **[MUST]** **Set `reportInputDuringAgentSpeech` deliberately.** It defaults to `none`, which means **by default we are blind to what the caller said while our agent was speaking** — losing context on every interrupted turn. `interruptible` and `reportInputDuringAgentSpeech` are different decisions and conflating them is the classic production bug. *(§4.5)*
57. **[MUST]** Backchannel handling — "yeah", "mm-hmm", "okay" must not be treated as end-of-turn (`ignoreBackchannel`). *(§4.3, §4.5)*
58. **[MUST]** Stream every stage into the next; never let one stage wait for the previous to finish. Most latency hides in **turn-taking decisions and LLM time-to-first-token**, not STT/TTS. *(§4.2)*
59. **[MUST]** Run the **nine-test acceptance suite on real audio**: pause mid-sentence, interrupt, speak fast, speak slow, background noise, cough, whisper, accents, uncooperative caller. **Transcript-based testing does not surface these.** *(§4.3, §4.6)*
60. **[SHOULD]** Instrument against published thresholds: **WER <10%** (<15% noisy), **task success >85%**, **FCR >75%**, **containment >70%**, **barge-in detection >95%**, **reprompt <10%**, **hallucination <2%** (<0.5% healthcare), **tool-call success >99%** for booking, **TTFA <800 ms**. *(§4.6)*
61. **[SHOULD]** Watch STT accuracy on **names, phone numbers and addresses specifically** — the fastest STT models in a 2026 benchmark carried ~25% WER, which is a production failure rate for a receptionist regardless of speed. Use `hints` to bias recognition toward business-specific terms, and `deepgramSmartFormat` for numbers/dates/addresses. *(§4.4, §4.5)*
62. **[SHOULD]** Record ConversationRelay calls with **`<Start><Recording channels="dual">` before `<Connect>`** — not `<Record>`, which is synchronous and captures only the caller leg. Dual-channel matters because Conversation Intelligence does no speaker diarization. Pause/resume via the Recordings resource is the mechanism for consent and payment handling. *(§4.5)*
63. **[SHOULD]** Model routing as a margin lever — cheap model for FAQ turns, stronger model for booking and edge cases. LLM cost spans **27×** across model choice. *(§5.4)*
64. **[NICE]** Simulated-call regression testing as a shipped, customer-visible feature — Retell and Smith.ai both meter it as a plan entitlement. *(§4.6)*

### F. Commercial

65. **[MUST]** Price in the **$49–$199/month** band where most SMBs sit, with plainly stated included minutes/calls **and the overage rate on the pricing page** — hiding overage is a documented category sin. *(§5.1, §5.2)*
66. **[MUST]** No setup fee, a **7–14 day free trial**, and month-to-month with no contract. All are category norms; charging a setup fee makes us an outlier. *(§5.2)*
67. **[MUST]** Cap *something* on any flat plan. At $0.085–$0.112/min hard cost, an "unlimited minutes" plan at $79 breaks even around 700–930 minutes. Goodcall can offer unlimited minutes only because it caps unique callers. *(§5.2, §5.4)*
68. **[SHOULD]** Include recording, transcript, summary, booking and warm transfer **on the entry plan**. The competitive gap is precisely that Rosie gates booking/transfers to $149 and Dialzara gates warm transfer to $99 — that gap is the position to take at **$99–$199**. *(§5.2, §5.4)*
69. **[SHOULD]** Do not compete on price with Dialzara ($29) or Goodcall ($79). Our defensible edge is **no per-seat platform fee at all** — an agency reselling Autocalls pays $0.12/min before its own margin; we pay ~$0.10/min with no floor. *(§5.4, §5.5)*
70. **[SHOULD]** Bill honestly on the details competitors fudge: state the rounding increment, never auto-upgrade a plan without consent, and don't meter test calls as real ones. *(§5.2)*
71. **[NICE]** Vertical-native booking where the vertical has a system of record — ServiceTitan/Jobber/Housecall Pro for trades, OpenTable/SevenRooms for restaurants, Clio for legal. "Taking a message is not the same as booking a job." *(§1.4)*
72. **[NICE]** White-label / multi-tenant with per-client branding and billing separation — the agency tier runs $199–$2,000/month across the market, and our cost structure undercuts all of it. *(§5.5)*

---

### The seven things to check first

If this checklist is used as an audit rather than a roadmap, these are the items most likely to be both **missing and serious** in a ConversationRelay-based product built by a small team:

1. **#56** — `reportInputDuringAgentSpeech` defaults to `none`. Silent, invisible, and it degrades every interrupted turn.
2. **#39 / #41** — recording disclosure and AI disclosure in the greeting. Two sentences that move us from exposed to defensible.
3. **#47** — per-caller delete. An architecture decision that is very expensive to retrofit.
4. **#54 / #59** — P95 measurement and a real audio test suite. Without them we do not actually know if we meet #53.
5. **#37** — A2P 10DLC's 10–15 day review sitting inside a "15-minute setup" promise.
6. **#67** — an uncapped flat plan against a $0.085–$0.112/min cost floor.
7. **#50** — any HIPAA claim not backed by the full signed BAA chain.

### Four pieces of open whitespace

Capabilities the category has collectively failed to build, where a small team can lead rather than catch up:

1. **Hours and holidays done properly (#20).** The weakest capability in the survey. Frontdesk has no business-hours object at all; only one of four developer platforms has one, and it has no holidays; nobody outside Avoca and Smith.ai treats holidays as *behaviour* rather than a closed message.
2. **A hard spend cap (#27).** Only Bland ships one, anywhere. Every SMB vendor either alerts-and-bills or — in Rosie's case — silently auto-upgrades your plan.
3. **The knowledge-gap → FAQ loop (#27a).** Three vendors out of sixteen. It is the difference between an agent that decays and one that improves on its own.
4. **A mobile app that configures the agent (#31).** One vendor out of sixteen — and the SMB owner running this product is, by definition, the person who is not sitting at a desk.

---

## APPENDIX — how to read this report

**Source hierarchy used.** Vendor-own pages (pricing pages, docs, help centres, terms) were treated as authoritative and are cited in preference throughout. Competitor-written "review" and "pricing" blogs — CloudTalk, Retell, Dialora, Sonant, NextPhone, serviceagent.ai and others all publish comparisons of rivals they are trying to displace — were used for feature enumeration and directional pricing, and are labelled as third-party where they carry a claim alone. Law-firm client alerts were preferred for legal points, with statutory text consulted where reachable.

**Known corrections made during research**, recorded because they show how stale this category's secondary sources are:
- **Synthflow** has withdrawn every self-serve tier and now sells only from $30,000/year. Reviews still quoting $29–$799 SMB plans are wrong. *(§5.3)*
- **Twilio PCI recording retention** is now **one year**, not the 72 hours widely repeated; changed 29 September 2025. *(§3.5)*
- **EU AI Act Art. 50** is **in force** as of 2 August 2026 — not pending, and not delayed by the Digital Omnibus. *(§3.8)*
- **Colorado's AI Act** was repealed and reenacted as an ADMT statute effective 1 January 2027; its general "you're talking to an AI" duty never took effect. Most compliance write-ups still describe the 2024 version. *(§3.2)*
- **The FCC one-to-one consent rule** was vacated in January 2025 and has since been formally removed from the rules. *(§3.3)*
- **Google** exited this space entirely — Business Profile call history and chat ended 31 July 2024, the Q&A API on 3 November 2025. *(§1.5)*

**Everything explicitly unverified** is listed in §3.10 and flagged inline elsewhere. Nothing in this report should reach a customer contract or a marketing page without a fresh check — for legal items, by counsel.

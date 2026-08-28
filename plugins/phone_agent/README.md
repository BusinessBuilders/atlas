# The phone agent — an AI receptionist for a business phone line

Somebody rings your business. The phone is answered straight away, at any
hour, by an assistant that knows your business name, what you do, when you are
open and what you have told it it may say. It takes the caller's name, their
number and what they need, and that message is on your phone before they have
finished walking back to their van. If the caller asks for a person and you
have given the line a number to pass calls to, it puts them through.

One installation can answer for several businesses at once: each phone number
is pointed at one business, and each business has its own greeting, hours,
message destination and dashboard login. Nobody sees anybody else's callers.

Two things this is not, and both are deliberate:

* **It never pretends to have done something.** It cannot book, buy, send or
  cancel anything. It answers from what you wrote down, and it takes a message.
  If it ever says "you're all set", that call is flagged for you to check.
* **It never guesses.** Prices, hours, addresses, availability — if you have
  not told it, it says it cannot say and takes a message instead.

---

## Part 1 — for the person whose phone this is

### What happens on a call

The caller dials your number. The phone network (Twilio) hands the call to this
software, which answers with your greeting — with the two notices composed into
it, so the caller is told they are speaking to an AI and that the call is
transcribed before they say anything. The network turns the caller's speech
into text and sends it here; the assistant writes a reply, which the network
speaks back. When the call ends, the conversation is summarised into a note —
name, callback number, email, what they need — which is filed, pushed to your
phone, and put in your dashboard's inbox as a message. Everything the caller
said is kept as a transcript you can read, for as long as you have said to keep
it.

### The five things you have to decide

| Decision | Where it lives | What happens if you say nothing |
|---|---|---|
| Your business name, what you do, who calls people back, and your greeting | Settings → Identity and Greeting | The line will not start. These four are required. |
| Whether callers can be put through to a person, and to what number | Settings → Transfer to a person | Nobody is put through; every caller is offered a message. |
| What the assistant is allowed to state as fact | Settings → What the agent may say | It answers no questions at all and takes a message instead. |
| When you are open | Hours | The line answers the same way at 3am as at 3pm. |
| Where a message goes the second it is taken | Notifications | It is filed and shown on the dashboard, but nothing buzzes in your pocket. |

### What the caller is told, before anything else

Two sentences are switched on when the line is installed and are spoken as part
of your greeting: that they are talking to an AI assistant, and that the call
may be recorded and transcribed. If your greeting ends in a question, they are
spoken *before* the question, so the caller is not answering over the top of
them.

Both sentences are yours to reword. Neither can simply be switched off: turning
one off requires a separate setting that says, on the record, that you decided
to. Storing a transcript is recording under most states' law, and this line
stores transcripts.

The dashboard shows you the whole opening line, exactly as the caller will hear
it, from the same code that speaks it. What you read is what they hear.

### Where your messages go

Every call where the caller spoke is summarised into a note: name, callback
number, email, what they need, each marked unknown when the caller did not say.
The note goes to three places, and the line is loud when any of them fails:

1. **The dashboard.** If the caller left something to act on, the note becomes
   a **message** in your inbox, with a state (new / working on it / done), a
   tap-to-dial link and a CSV export. If they left nothing at all — a wrong
   number, somebody who hung up mid-sentence — the note is kept on the call
   instead, rather than sitting in your inbox at "new" forever and inflating
   your waiting count.
2. **A plain-text file** you can read with anything, one entry per call.
3. **Your phone**, as a push notification, if you have set a notification
   target.

If the file cannot be written, the line pushes the whole message to your phone
at urgent priority, writes a copy beside the file, and reports itself unhealthy
until you acknowledge it. A message never disappears quietly. That is the one
promise the assistant makes to callers, so it is the one the software defends
hardest.

**On a line with more than one business, give every business its own push
topic** (Notifications → Push to your phone). A business with none falls back to
the line's own address, which belongs to whoever runs the line — and every
business left on it pushes to that same topic, so one subscription hears them
all. The Notifications screen tells a business owner they are on the line's
address; it does not show them what that address is, because it is not theirs.

### The caller decides — not the AI

The assistant can ask to transfer the call or to hang up, but neither happens
unless the **caller** asked for it in their own words. A transfer needs the
caller to have said something like "operator", "a real person", or "talk to
Jo"; a hang-up needs a goodbye. A model that decides on its own to end a call
is refused and the refusal is written down. If there is no number to transfer
to, no transfer is offered at all.

### Why a stranger on the phone cannot reach anything

Anyone on Earth can dial your number, and a caller is nobody you have checked.
So the part of the system that talks to callers is deliberately small and
locked in:

* **It has no tools, ever.** The assistant answering the phone cannot look
  anything up, send anything, or touch anything else you run. It talks, and it
  takes a message. That is not a switch somebody can flip in a settings file.
* **It knows only your business.** Its instructions are built from your
  business's settings and nothing else. No personal context, no other
  business's details, nothing about the machine it runs on.
* **It cannot invent.** The instructions forbid stating a price, a time, an
  address or an availability that is not in what you wrote down, and forbid
  claiming to have done anything.
* **Every request from the phone network is checked.** Each webhook carries a
  signature made with your Twilio auth token, and one that does not verify is
  refused. The websocket the conversation runs over carries a key of its own —
  one call, two minutes, one use, once the line is set up with `WS_SECRET` (see
  step 2) — and a session claiming to belong to a different Twilio account is
  closed.
* **A number nobody has set up is a loud dead end.** A call to a number that is
  not in your settings hears a spoken configuration error and lands in the log
  at error level. It is never silently answered as some other business.

### Not done yet

See "What this line does not do yet", near the bottom. It is a real list with
real reasons, not a wish list.

---

## Part 2 — setting up a line

From here on this page is for whoever installs the line: you, or an AI session
working with you. Three words are used throughout, and this is all they mean:

* **the settings file** — `businesses.toml` in `~/.config/atlas-phone/`: your
  businesses, your numbers, your hours. No passwords in it, ever.
* **the secrets file** — `env` in the same folder, readable only by you: the
  passwords and keys, and the addresses of the parts. Systemd hands it to the
  service; it is not read by the service itself.
* **the journal** — the system's own log of what the service has been doing,
  read with `journalctl`. It never contains a caller's words.

### 1. Write the settings file

Copy `businesses.example.toml` to `~/.config/atlas-phone/businesses.toml` and
replace every value with your own. Every setting is documented in that file
next to its default. The minimum is one number and one business:

```toml
[numbers]
"+15085551234" = "acme_plumbing"      # every live number, mapped to a business

[profiles.acme_plumbing]
business_name = "Acme Plumbing"
services = "emergency plumbing, drain cleaning, and water heater work"
owner_name = "Jo"
greeting = "Hi, you've reached Acme Plumbing. How can I help you today?"
```

A different file can be used by setting `BUSINESS_CONFIG` to its path.

### 2. Write the secrets file

`~/.config/atlas-phone/env`, mode 600. The service refuses to start if any of
these is missing:

| Setting | What it is |
|---|---|
| `TWILIO_ACCOUNT_SID` | Your Twilio account id. Used to check that a call really came from your account. |
| `TWILIO_AUTH_TOKEN` | Your Twilio auth token. Every webhook is signature-checked with it; rotate it in the Twilio console and update this file, or every call is rejected. |
| `BRIDGE_PORT` | The local port the service listens on (it binds `127.0.0.1` only). |
| `PUBLIC_BASE` | The public `https://…` address Twilio reaches, including any path it is mounted at. Signatures are checked against this exact string, so it must match what Twilio calls. |
| `WS_TOKEN` | The older shared secret in the relay address. Still required; only accepted while `WS_SECRET` is unset. |
| `OLLAMA_URL` | An OpenAI-compatible model endpoint, e.g. `http://127.0.0.1:11434/v1`. |
| `MODEL` | The model name at that endpoint. It must be a **non-thinking** model: a model that reasons silently for seconds loses phone callers. |

And these are optional:

| Setting | Default | What it is |
|---|---|---|
| `WS_SECRET` | unset | Turn this on. With it, every call gets its own websocket key that expires in two minutes and works once, and the shared `WS_TOKEN` stops being accepted. **It must be at least 16 characters** — the service refuses to start on a shorter one, because a one-character secret is worse than the static token it replaces while looking like a fix. Generate one with `openssl rand -hex 32`. |
| `BUSINESS_CONFIG` | `~/.config/atlas-phone/businesses.toml` | Where the settings file is. |
| `MESSAGES_FILE` | `~/atlas-phone-messages.md` | The plain-text message file. A business can override it for itself. |
| `NTFY_URL` + `NTFY_TOPIC` | unset | Push notifications for new messages. Set **both** or neither — one alone stops the service, because half a notification setting is a notification that silently never arrives. |
| `PHONE_DATA_DIR` | `~/.local/share/atlas-phone` | Where `calls.db` lives. The folder is forced to `0700` and the database to `0600` at every start, and the service refuses to start if it cannot open them. |
| `ADMIN_TOKEN` | unset | The old single dashboard access code. It still works, and appears in the dashboard as the login **Line owner** with access to every business. Named logins are better — see below. |
| `ADMIN_PORT` | `8891` | The local port the owner dashboard listens on. |

`TWILIO_PHONE` appears in older secrets files. Nothing reads it; leave it or
delete it.

### 3. Check it before anything is running

```bash
set -a; . ~/.config/atlas-phone/env; set +a
python3 plugins/phone_agent/service.py --check
```

`--check` validates the settings file and every environment variable that file
names, prints what it found, and exits. It opens no database, no port and no
network connection, so it is safe to run beside a live line.

It talks twice. INFO and WARNING lines go to the error output **first**, and
then the summary goes to the normal output. On a config that is valid but not
finished yet, lines like these are expected, not failures:

```
… WARNING WS_SECRET is not set — the relay still accepts the shared static WS_TOKEN …
… INFO --check: validating …/businesses.toml only — no call store, no sockets
… WARNING profile acme_plumbing has no timezone; using host zone EDT …
… INFO 1 business profile(s) loaded: acme_plumbing …
… INFO active brain: default (model qwen2.5:7b-instruct at http://127.0.0.1:11434/v1)
/home/you/.config/atlas-phone/businesses.toml is valid.
  businesses: acme_plumbing
  numbers:    1
  brain:      default (qwen2.5:7b-instruct at http://127.0.0.1:11434/v1)
  logins:     none
Every environment variable this config names is set.
```

**It passed if you got the summary block and exit code 0.** The two warnings
above are the line telling you what is still worth setting: `WS_SECRET` in the
secrets file, and a `timezone` on each business. A real failure looks nothing
like this — no summary at all, one sentence saying what is wrong, exit code 1.
The same validation runs at boot and on every dashboard save, so a setting that
passes here cannot be refused later.

### 4. Install and start it

`deploy/phone/README.md` is the runbook: it builds the environment, installs
the three services (the bridge, the tunnel that gives it a public address, and
the pager that shouts when either dies), and takes a line live. It is written
step by step, with what "good" looks like after each one.

### 5. Point Twilio at it

The number's voice webhook must POST to `PUBLIC_BASE/voice/incoming`. Three
more Twilio settings matter, and `twilio_config.py` manages all four:

```bash
python3 plugins/phone_agent/twilio_config.py --show     # reads; changes nothing
```

* `voice_url` — where a call goes. **`--apply` never writes this one**; it is
  what makes the number answer at all. `--show` says loudly when it does not
  match, and changing it is `--apply-voice-url --yes` or the Twilio console.
* `voice_fallback_url` — where a call goes when the first URL fails. It should
  be a static file on the public endpoint, so an outage on this machine sends
  the caller to a person instead of Twilio's "an application error has
  occurred". `--render` writes one per number.
* `status_callback` → `/voice/status`: what the carrier says the call was,
  including what it cost. Recorded against the call.
* `sms_url` → `/sms/incoming`: a text to the number becomes a message beside
  the voice ones. **Nothing is ever sent back** — see the not-done list.

### 6. Open the dashboard

The dashboard runs whenever the line has at least one login, on
`127.0.0.1:ADMIN_PORT`. Publish it to yourself over https on your private
network only — for example `tailscale serve --bg --https=8447
http://127.0.0.1:8891` — never on the public address Twilio uses. The session
cookie is `Secure`, so an https address is what a browser needs to keep you
signed in.

### 7. Call your own number

The last check is the one only a person can do. Ring it, talk to it, hang up,
and see the message arrive.

---

## What each business can be set to

Four settings are required. Everything else has a default that is what the line
did before that setting existed, so filling this in never changes behaviour you
did not ask to change.

| Setting | Default | What it does |
|---|---|---|
| `business_name` | *required* | Who the assistant says it is answering for. |
| `services` | *required* | One plain sentence about what the business does. |
| `owner_name` | *required* | Who the caller is told will get back to them. |
| `greeting` | *required* | The first thing a caller hears, before the notices are composed in. |
| `assistant_name` | `Atlas` | What the assistant calls itself. |
| `forward_to` | none | A number callers can be put through to. Omitted, no transfer is ever offered. It may not be one of your own mapped numbers — that would be a call loop, and it is refused. |
| `facts` | none | The only specifics the assistant may state: hours, contact details, service area, pricing posture. Omitted, it answers nothing and takes a message. |
| `extra_instructions` | none | Added to this business's instructions. It can never override the safety rules. |
| `transfer_phrases` | the standard set | What a caller must say before a transfer can happen. `{owner}` stands in for the owner's first name. |
| `end_phrases` | the standard set | What a caller must say before the assistant may hang up. |
| `assistant_aliases` | the standard set for the name | Words the transcriber hears instead of the assistant's name. For `Atlas`: alice, at last, atlus, atlass. Another name has none until you list them. |
| `timezone` | the host machine's zone, with a warning | An IANA name like `America/New_York`. **Required** as soon as hours or holidays are set. |
| `hours` | none — open around the clock | A weekly table, e.g. `{ mon = "09:00-17:00" }`. A day left out is closed all day; `"18:00-02:00"` is an overnight shift belonging to the day it starts on. |
| `holidays` | none | Dates or inclusive ranges: `["2026-11-26", "2026-12-24..2026-12-26"]`. A holiday closes the whole local day. |
| `after_hours` | `message` | What a closed line does: `message` (take a message, never transfer), `transfer` (put them through), `same` (behave exactly as in hours). |
| `after_hours_greeting` | none — the normal greeting is used | The greeting for a caller who rings while you are closed. |
| `ai_disclosure` | `true` | Speak the "I'm an AI assistant" sentence. |
| `ai_disclosure_text` | `I'm the AI assistant for {business_name}.` | That sentence. `{business_name}` and `{assistant_name}` are the only fill-ins; anything else is refused rather than spoken wrong. |
| `recording_notice` | `true` | Speak the recording/transcription notice. |
| `recording_notice_text` | `This call may be recorded and transcribed.` | That sentence. |
| `ack_disclosure_waived` | `false` | Must be `true` before either notice can be switched off. Without it the line refuses to start with the reason. |
| `language` | `en-US` | The language the phone network listens and speaks in. `multi` (auto-detect) is accepted only when the two provider settings below are written out as Deepgram and ElevenLabs. |
| `tts_provider` | none | `Google`, `Amazon` or `ElevenLabs`. Left empty the setting is left out of the instructions to Twilio entirely, so its own default voice keeps answering and filling in this file changes nothing your callers already hear. |
| `voice` | none | A voice id belonging to that provider. Empty behaves the same way. |
| `transcription_provider` | none | `Google` or `Deepgram`. Empty behaves the same way. |
| `hints` | none | Words the transcriber should expect — business name, staff names, product names. No commas inside one: the phone network splits the list on commas. |
| `ignore_backchannel` | `true` | "Mm-hmm" while the assistant is talking does not interrupt it. |
| `brain` | the line's active model | Answer this business's calls on a different model backend. |
| `model` | the model backend's own | A different model name at the same backend. Must be non-thinking. |
| `messages_file` | the line-wide `MESSAGES_FILE` | This business's own message file. |
| `ntfy_url` / `ntfy_topic` | the line-wide pair | This business's own notification target. Both or neither. |
| `max_call_seconds` | `600` | How long a call may run before the assistant wraps up out loud and ends it. Between 30 and 14400. |
| `caller_turn_budget_per_hour` | `60` | How many times one caller ID may speak in an hour before it is politely refused. Between 1 and 10000. |
| `block_list` | none | Numbers that get one short sentence and a hang-up. The call is still written down, so "did that number get through last night?" has an answer. |
| `retention_days` | `90` | How long transcripts and message summaries are kept. The call and message records themselves stay forever. Between 1 and 3650. |

A setting the line does not know is **kept in the file untouched and named in a
warning at start-up**. A typo therefore does nothing — but it never does
nothing silently. (The same is not true inside the model-backend, branding and
login sections: those tables are entirely the product's, and an unknown setting
there is refused, because a setting nobody reads there is one that looked
applied and never was.)

The dashboard puts its own length caps on the boxes you type into — a greeting
of 400 characters, a fact of 240, extra instructions of 6000. Those are the
dashboard's, not the line's: the settings file itself has no such limits, and a
longer value written into the file directly is accepted and answered with. The
caps exist so nobody pastes a document into a sentence a caller has to sit
through, and the dashboard refuses with the count rather than silently
truncating.

## Who may sign in, and whose name is on it

```toml
[owners.jo]
token_env = "PHONE_OWNER_JO_TOKEN"     # the NAME of the secret, never the secret
profiles = ["acme_plumbing"]           # or ["*"] for every business on the line
```

The access code itself lives in the secrets file under that name. An owner sees
only the businesses listed; every read on every screen is scoped to that list.
The legacy `ADMIN_TOKEN` still works and behaves as an owner of everything,
shown as **Line owner**.

**If an access code leaks, change it and restart the line.** The restart is
half the fix: it signs everybody out, so a browser that was already signed in
on the old code has to sign in again on the new one. Change the code without
restarting and those sessions stay alive for another fourteen idle days. (An
owner who only wants to end their own sessions has **Sign out everywhere** in
the header of every screen, which needs no restart.)

`[branding]` puts a reseller's name, product name, logo, support email, colours
and fonts over the whole dashboard. Nothing in the templates names a colour, a
font or a company; with no branding table the dashboard uses its own neutral
dark palette and the system font, and calls itself **Atlas · Phone Agent**
until `vendor_name` and `product_name` say otherwise. If you are putting this
in front of your own customers, set those two first.

`[deleted_profiles.*]` holds a business removed on the dashboard — its settings
exactly as they were, plus the date it went. Nothing that answers a call reads
it, and Activity puts it back for thirty days.

All three sections are validated at start-up, on `--check` and on every save,
and all three survive a save byte for byte: a login written into the file by
hand cannot be lost by pressing Save on an unrelated screen.

## The models that answer — "brains"

A **brain** is a named model backend: a label, an OpenAI-compatible `base_url`,
a `model`, optionally the NAME of an environment variable holding its API key
(`api_key_env` — the key itself never goes in the settings file), and
optionally an `extra_body` JSON object merged into every request, which is
where a cloud provider's explicit "no thinking" switch lives. They are
`[brains.*]` sections, and the top-level `active_brain` names the one answering
calls.

Define none and nothing changes: `OLLAMA_URL` + `MODEL` are the single implicit
brain. Define some and the dashboard shows them as cards; switching applies to
the next call, and **calls already in progress finish on the brain they started
with**. A business's own `brain` beats the active one, and its own `model`
beats the brain's.

Validation is fail-closed at start-up and on every save: an `active_brain`
naming a brain that does not exist, an `api_key_env` naming a variable that is
unset, or an `extra_body` that is not a JSON object is refused with a plain
sentence, and neither the file nor the running line changes. `extra_body`
merges *under* the request's own keys, so a preset can never override `model`,
`messages` or `stream`.

**Privacy follows the brain.** On a local backend, no caller's words leave the
machine. Point the active brain at a hosted API and every caller turn is sent
to that vendor.

**A backend that is not licensed for real customers must say so in its label.**
Put the words `test only` in it — `label = "GLM-5.2 — test only"` — for any
model on a coding plan, a free tier or an evaluation key. Those two words are
what draw the red banner across the Overview and the Brain screen while that
backend is answering, and they are the only thing that draws it: the same model
labelled "GLM-5.2" answers real customers under a green Overview, which is
exactly the condition this line ran in, unnoticed, for weeks.

## What is written down, and for how long

Everything the line does is in one SQLite file — `$PHONE_DATA_DIR/calls.db`,
by default `~/.local/share/atlas-phone/calls.db`. Calls, every turn of every
conversation, messages and their status, operational events, every settings
change with who made it, every notification attempt, and the dashboard's
sessions. If that file cannot be opened the service refuses to start: a line
that answers calls and records nothing is worse than a line that is down.

* **The journal holds no caller's words.** It carries the call id, turn numbers
  and character counts. The words are in the store, which has a retention
  horizon and a delete path; the journal has neither.
* **Phone numbers are masked in the journal** to the last four digits.
* **Test calls are marked.** A call id beginning `CAtest` or a `+1555…` number
  is flagged and stays out of the message list until you tick "Show test
  calls".
* **Retention runs daily**: transcript turns and the free-text summary older
  than the business's `retention_days` are deleted, while the call and message
  rows — and therefore your counts and history — stay exactly as they were.
* **"Delete my data"** is a button on that caller's call page. You type the
  number back to confirm, because there is no undo, and then every row this
  store holds for it goes — calls, transcripts, messages, alert history. It
  then lists the calls whose entries in the plain-text message file still have
  to be redacted by hand, because that file is append-only text this software
  does not own. A login that owns one business cannot use it on a caller who
  also rang another: the delete is refused outright rather than half done.

**Importing an older message file.** Messages taken before the store existed
live only in the Markdown file. `migrate_pad.py` reads it (never writes to it)
and imports each entry:

```bash
python3 plugins/phone_agent/migrate_pad.py \
    --pad ~/atlas-phone-messages.md \
    --db ~/.local/share/atlas-phone/calls.db \
    --profile acme_plumbing [--dry-run]
```

It prints counts only, never caller details, and is idempotent — a call id
already in the store is skipped, so running it twice imports nothing. **Run it
with the service stopped** (or against a copy of the database): it writes each
entry in its own transaction, and the live service does its store writes on the
same thread that is answering calls with a five-second lock timeout, so a long
import competing with it can make a live call wait.

## The dashboard, screen by screen

**Sign in.** One box: the access code for one login. Five wrong codes from one
address inside fifteen minutes closes that address for a minute; twenty wrong
codes from anywhere in the same fifteen minutes closes the form for everyone
for a minute, because a per-address limit alone is only a speed limit per
address. Every failure is written down with where it came from. The page
carries the branding and, if one is configured, a support email.

**Overview.** Is my phone being answered properly, answered in five seconds on
a phone screen. A status band across the top is composed from five checks —
the service is answering; the model that answers is responding; the phone
network has been verified in the last 24 hours; your numbers point at a
business; message alerts are getting through — and the band is never green
while any of them is failing *or* merely unknown. Beneath it: an orange safety
banner when the model answering is one whose label says it is for testing only;
today's numbers; a seven-day chart; what needs attention over the last week in
plain sentences; the latest messages; and a "Mark as seen" button for a message
alert that failed, which is what clears the outside monitor. Nothing on this
screen probes anything — the health picture comes from a check that runs in the
background every minute, and the page says how old it is, so a refresh can
never start a billable model request. A panel that cannot read its data says so
and the rest of the page still draws.

*The 24-hour check reads your call log*: it is the time the newest call
started, not a separate record of Twilio requests. So a line that answered a
call in the last day shows "phone network verified", and a line that has been
quiet for a day says the connection "has not been confirmed today" — which is
honest, and is why it is drawn as unknown rather than as a fault.

**Calls.** Every call, newest first, fifty to a page, filtered by date range,
by business, by outcome (message taken, after-hours message, transferred,
couldn't help, hung up, needs attention, limited, blocked), by whether it left a
message, and by a search box that reaches the caller's number, the message
fields **and what was said** — a call whose words have aged out past its
retention window simply stops matching on those, which is exactly what the
clear-out left behind. Caller numbers are masked in this list, because a call
log gets read over the owner's shoulder in a shop. Test calls are hidden until
you ask for them, and a line whose only calls are tests is told that rather than
"no calls yet".

**One call.** The whole conversation as it happened, the message it produced,
the caller's full number (this is the page only its owner can open, and the
number is the thing they have to dial), the outcome, which model answered, how
long the caller waited for the first word each turn, any overpromise flags,
whether the message reached your phone, a note field, a "handled" mark, and the
"delete everything about this caller" action.

**Messages.** The screen the line exists for. New, working on it, done —
changed from the list without opening anything, and it is a real write the next
page load agrees with. A `tel:` link that dials with a thumb, a copy button,
whatever note you left on the call (the note itself is written on the call's own
page), and a CSV export that is a real file: a header row, quoting that survives
a comma in a caller's own words, and no cell a spreadsheet will run as a
formula.

**Settings.** One business at a time, in eight sections — Identity, Greeting,
What the agent may say, Extra instructions, Transfer to a person, Ending a
call, Name recognition, Advanced — each with its own Save. Nothing you did not
touch is submitted, so nothing you did not touch can be lost. A refusal is
drawn from **what you typed**, with the reason beside the field it belongs to.
The Greeting section previews the whole opening line the caller will hear,
built by the same code that speaks it. Switching a capability off — clearing
the transfer number, clearing the facts — is confirmed in words that say what
the caller will experience. And a form carries the version it was built from,
so a save from another device between your page load and your button press is
refused rather than silently overwriting someone's work.

**Hours.** The weekly table, the holidays, the timezone, and what an
out-of-hours caller is offered. Times are read the way people write them —
"9:00 AM", "9am" and "09:00" all mean the same — and stored the one way the
line reads. With no schedule at all, the screen says plainly that the line
answers the same way at 3am as at 3pm instead of showing seven blank rows.

**Numbers.** Every number on the line and which business it answers for, chosen
from a list of real businesses rather than typed. A number is tidied into the
form the phone network wants, the same number twice is refused by name, and
each row says when the phone network last called it — the only honest evidence
the webhook is wired up — with the exact address to paste into the Twilio
console when it never has. Numbers belong to the whole line, so an owner of one
business sees their own, read-only.

**Notifications.** Where this business's messages go, with the line-wide
default filled in and labelled as the default rather than silently inherited.
**Send test** really sends: same address, same request, same ten-second
timeout, written to the same delivery log as a caller's message, and it shows
you what actually came back including the failure. Below it, the last twenty
attempts, successes included, because "when did it stop working" is the
question that matters at two in the morning.

**Brain.** The model backends this line can answer on, each card saying where
it runs (on this machine, or in the cloud), whether its last check answered,
and whether its label marks it as test-only. Switching is confirmed, naming the
model and saying it applies to the next call. A backend whose last check failed
cannot be switched to without ticking an override. The switch goes through the
same validation, backup and audit as any other change. The screen belongs to
whoever owns the whole line — a business on a shared line does not get to
change the model the others answer on.

**Activity.** Every settings change as a sentence, with who made it and the
exact lines that changed on expand, and a button that puts the previous version
back through the same validation as any other save. Every sign-in, including
the failures and the lockouts. What the service itself reported, in your words
rather than its own. And the businesses that were removed, with the button that
brings one back. An owner of one business is shown a change only when it
touched one of their businesses.

**Removing a business.** Its own page, reached from Settings. You must type the
business's name exactly. It is a soft delete: the settings move aside with the
date, the numbers stop answering for it, and Activity restores the whole thing
for thirty days.

Everything mutating carries a per-session token and an origin check, sessions
live on the server so signing out really ends them, and every page is served
with no-store, no-sniff, no-referrer and a policy that forbids framing and
inline scripts.

## How you find out something is wrong

* **`GET PUBLIC_BASE/health`** answers `{"status": "ok"}` with a 200, or a short
  reason with a 503. It is deliberately thin: it is reachable from the whole
  internet, so it names no business, no model and no vendor, and it answers
  from memory — nothing on that path can be made to start a model request.
  It goes to 503 when a message could not be delivered, when the push channel
  is failing, or when a model backend a call could run on failed its last
  check. It does **not** know whether Twilio can reach you, whether your
  numbers are mapped, or whether anybody has called: for those, read the
  Overview. Point an uptime monitor at it — that status code is what pages you.
* **The status band** on the Overview is the fuller picture, and the one that
  knows about your numbers and the phone network.
* **Push notifications** carry every message, and an urgent one when a message
  could not be filed.
* **The service units page you.** If the bridge or its tunnel fails for good,
  systemd runs an alert unit that pushes to your phone. An alert that cannot be
  sent exits with an error and leaves that unit failed, rather than pretending
  you were told.
* **Ask the assistant.** Atlas itself has one read-only tool here,
  `phone_line_status`, which asks the bridge how it is. It is the only tool in
  this plugin, and it faces the owner, never a caller.

## What this line does not do yet

Reproduced from the design document
(`docs/superpowers/specs/2026-08-27-phone-agent-productization-design.md` §7)
as written, with the step that unblocks each. Item 1 names the first install's
owner because that is how it was recorded; the rule behind it applies to any
business.

1. **Compliant brain.** Live brain is `glm_52_test` (Z.AI coding plan —
   prohibited for production bots). Unblock: William adds Z.AI balance and
   clicks `glm_52_api`, or supplies another API key (his HARD RULE: explicit,
   attributable). Dashboard shows a red banner until then.
   *For any business: the line must answer on a model whose plan permits
   answering real customers, on a key billed to that business. The Brain screen
   shows the safety banner until the active backend's label stops saying "test
   only".*
2. **SMS sending** (booking links, owner SMS) — needs A2P 10DLC registration
   (10–15 days, privacy/terms URLs). Inbound SMS is captured; nothing is sent.
   *Unblock: register the number's campaign with the carriers through Twilio
   (a business identity, a privacy policy URL and a terms URL are required),
   wait out the review, then the outbound path can be built.*
3. **Calendar booking** (Google/Outlook/Calendly/Jobber…) — the 2026
   dividing-line feature; a separate design.
   *Unblock: pick the first calendar to support and write that design — it
   needs an OAuth app, a per-business connection, and a rule for what the
   assistant may promise before the booking is confirmed.*
4. **Website-scrape knowledge base** — the `facts` editor exists; auto-build
   from URL is a separate design.
   *Unblock: write that design. Until then, paste what the assistant may say
   into Settings → What the agent may say.*
5. **Audio recording + playback** — `record_calls` toggle +
   `<Start><Recording channels="dual">` + retention; the notice already covers
   transcripts.
   *Unblock: add the per-business toggle, the recording verb, storage for the
   audio and a retention rule for it. The spoken notice needs no change.*
6. **Spam screening beyond block list + rate limit** (STIR/SHAKEN attestation,
   known-spam lists).
   *Unblock: read Twilio's attestation on the incoming webhook and decide what
   the line does with a failing one, or subscribe to a screening list. Today:
   put a number in that business's `block_list`, and every caller is already
   capped at `caller_turn_budget_per_hour` turns an hour.*
7. **`reportInputDuringAgentSpeech`** tuning — needs real-call testing.
   *Unblock: real calls on a test number, because the turn logic is not written
   for a caller speaking over the assistant. It stays at its default until
   somebody has sat through those calls.*
8. **HIPAA/BAA, SOC 2, terms of service** — legal/commercial, William +
   counsel.
   *Unblock: a lawyer. Nothing in this software should be described to a
   customer as HIPAA-compliant or SOC 2 until then.*
9. **Multi-language auto-detect** is *configurable* (validated constraint) but
   untested with a real Spanish caller.
   *Unblock: set `language = "multi"` with Deepgram and ElevenLabs written out,
   then have a native speaker ring the number and listen to the recording of
   what happened.*
10. **P95 latency against the 700 ms bar** — instrumented (TTFT per turn) but
    no tuning done; GLM-5.2 measured 1.4–2.8 s TTFT on 2026-07-31.
    *Unblock: the per-turn figures are already on every call's page. Read them
    across a week of real calls, then tune the prompt length, the model or the
    backend — in that order.*
11. **Dashboard times are the machine's clock, not the business's.** The push
    notification and the message file are stamped in the business's own
    `timezone`; every time on the dashboard — call times, "calls today", the
    date filters, the exported spreadsheet — is stamped in the timezone of the
    machine the line runs on. On a line where they are the same zone (this
    install) nothing looks wrong and nothing is. Put the line on a machine in
    another state and the owner sees a push stamped 14:05 and a dashboard row
    for the same call at 16:05, and "calls today" rolls over at the wrong
    midnight. *Unblock: give `render.fmt_local` a zone argument taken from the
    row's business (`hours.profile_zone`), thread it through the templates that
    print a time, and bucket the "today"/"this week" counts by the business's
    zone instead of the machine's.*

## Checking the code yourself

```bash
# the whole suite (722 tests): handlers over real sockets, a real model
# backend, a real notification receiver, a real database
PYTHONPATH=<checkout>:<checkout>/src python -m pytest -q -W error \
    tests/test_phone_agent*.py
```

The websocket simulations live in `tests/test_phone_agent_hardening.py` and
`tests/test_phone_agent_runtime.py`: they open real websockets to the real
relay handler and assert what happened to the caller's message when a frame
arrives malformed, a token is replayed, the message file cannot be written or
the notification channel is dead.

To look at the dashboard without touching a live line:

```bash
# terminal 1 — the real dashboard on an invented two-business line in a
# throwaway folder; it prints its own pid and two access codes
PYTHONPATH=<checkout>:<checkout>/src \
    python tests/e2e/run_dashboard_fixture.py /tmp/dash-work 8931
# terminal 2 — walks every screen the router serves and prints PASS/FAIL
python tests/e2e/phone_dashboard_checks.py http://127.0.0.1:8931
```

The checker's list of screens comes from the dashboard's own router, so a
screen added tomorrow cannot go unchecked. It asserts owner vocabulary, that
every control has a label, colour contrast computed from the stylesheet the
browser actually resolves, no inline script or style, and that every internal
link answers 200. Photographs of every screen at both sizes, and what is
fiction in them, are in
`docs/superpowers/specs/2026-08-27-phone-agent-dashboard-screenshots/`.

## Where the code is

| File | What it is |
|---|---|
| `service.py` | The bridge: Twilio webhooks, the websocket relay, the persona, the gates, config validation, delivery, health. |
| `admin/` | The owner dashboard — one module per screen, `auth.py` for logins and tenancy, `config_edit.py` for the one save path, `render.py` for templates and branding, `status.py` for the status band. |
| `callstore.py` | The SQLite store: calls, turns, messages, events, config changes, notification log, sessions. |
| `hours.py` | Opening hours. Pure functions, no I/O, its own tests with fixed clocks. |
| `wstoken.py` | Per-call websocket keys. Pure functions, no clock, no state. |
| `twilio_config.py` | Shows and sets the four Twilio settings per number; renders the fallback answers. |
| `migrate_pad.py` | One-shot import of the old Markdown message file. |
| `plugin.py` | The one owner-facing tool, `phone_line_status`. |
| `skill.md` | What that tool is for, in the form Atlas's tool catalogue reads. |
| `businesses.example.toml` | Every setting, documented next to its default. |
| `../../deploy/phone/` | Install, cutover and rollback — the runbook. |

Design and review record for the call-control rules:
`docs/superpowers/specs/2026-07-26-phone-call-control-hardening-design.md`.
The productization design, including the audits behind it:
`docs/superpowers/specs/2026-08-27-phone-agent-productization-design.md`.

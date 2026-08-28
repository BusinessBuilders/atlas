# Running the phone line — deployment files, cutover and rollback

This folder holds everything the **live phone line** needs to run, other than
the code itself. It exists because those files used to live only on the machine
that answers the calls: one wrong keystroke and there was no copy anywhere. Now
they are in git, they are tested, and a new deployment is a checkout plus one
install command.

Written for a non-developer working with an AI session: read a step, paste the
command, read what comes back. **If a step's output does not look like what
this page says it should, stop and say so — do not improvise on a phone line
that customers are calling.**

## What is in here

| File | What it is |
|---|---|
| `install.sh` | Builds the Python environment and installs the three systemd units. Never starts or stops anything. |
| `alert.sh` | Sends the "the phone line has failed" push notification. Run by systemd, not by you. |
| `tunnel-guard.sh` | Clears a dead SSH tunnel off the public server before reconnecting. The fix for the nightly 502s. |
| `fallback.xml.template` | The answer a caller hears when this machine cannot take the call. Rendered per number (see below), served by the public web server. |
| `nginx-phone-fallback.conf` | The nginx blocks that serve that file. Paste them into the existing server block. |
| `rendered/` | Where the rendered fallback files land. Not in git — each one carries a business's transfer number. |
| `../../plugins/phone_agent/twilio_config.py` | Shows and sets the four Twilio settings for every mapped number, and renders the fallback files. |
| `../systemd/atlas-phone-bridge.service` | The bridge itself — the thing Twilio talks to. |
| `../systemd/atlas-phone-tunnel.service` | The SSH tunnel that carries the public server's port 8890 to this machine. |
| `../systemd/atlas-phone-alert@.service` | The pager. Fires automatically when either of the other two fails. |

## How the pieces fit

Three roles, whatever the hostnames are:

1. **A public HTTPS address** that Twilio can reach — this is `PUBLIC_BASE` in
   the settings. It must be reachable from the internet and it must keep
   working when the machine that answers calls does not, because it is also
   where the fallback answer is served from.
2. **A way in** from that address to the bridge, which listens on `127.0.0.1`
   only and is never exposed directly. The unit here does that with a reverse
   SSH tunnel, so the answering machine can sit behind a home router with no
   port forwarding at all.
3. **The bridge**, on the machine with the model — one systemd service running
   `plugins/phone_agent/service.py` out of a git checkout.

If either of the first two dies for good, systemd runs the **alert** unit,
which pushes a notification to the owner's phone.

Three things are deliberate:

- **A crash loop is not "running".** Each unit gets a limited number of
  restarts (bridge: 10 in 5 minutes; tunnel: 20 in 10 minutes). After that the
  unit is marked *failed* and the owner is paged. A phone line silently
  restarting every five seconds looks alive on a dashboard and answers nobody.
- **An alert that cannot be sent is itself an alarm.** If the push cannot go
  out, `alert.sh` exits with an error that lands in the journal and leaves the
  alert unit failed. It never exits quietly.
- **The installer never touches a running service.** Taking the line down is a
  decision a person makes, not a side effect of an install.

> **Example deployment (this install).** The public address is
> `https://ai.business-builder.online/phone`, served by nginx on a VPS, which
> proxies down a reverse SSH tunnel to port 8890 on the machine at home. That
> VPS address, its login and its SSH key are written into
> `../systemd/atlas-phone-tunnel.service` and into the defaults in
> `tunnel-guard.sh`. **A different business changes them there**: edit the
> unit's `ExecStart` line, and set `PHONE_TUNNEL_VPS`, `PHONE_TUNNEL_PORT` and
> `PHONE_TUNNEL_KEY` for the guard. A deployment that reaches the internet
> another way — a reverse proxy on the same machine, a Tailscale funnel — does
> not need the tunnel unit at all: install it, leave it disabled, and make sure
> the fallback file is still served from somewhere that survives this machine
> being off.

## Where things live after the cutover

| Thing | Path |
|---|---|
| Code (a git checkout of this branch) | `~/atlas-phone-deploy` |
| Its Python environment | `~/atlas-phone-deploy/.venv` |
| Secrets and settings | `~/.config/atlas-phone/env` (mode 600) |
| Business profiles | `~/.config/atlas-phone/businesses.toml` |
| Backups of that file, one per save | `~/.config/atlas-phone/businesses.toml.bak-<date>` (newest 100 kept) |
| Installed units | `~/.config/systemd/user/` |
| The call store (calls, transcripts, messages) | `~/.local/share/atlas-phone/calls.db` (folder 700, file 600; `PHONE_DATA_DIR` moves it) |
| The message file (plain text, append-only) | `~/atlas-phone-messages.md` |
| The old hand-made directory | `~/atlas-phone-bridge.archived-<date>` (kept 30 days) |

The call store is the one file here that cannot be rebuilt from the repo: it
holds what callers said and the messages they left. Back it up with the
settings, and remember it is the file a "delete my data" request has to reach.

The unit files use `%h/atlas-phone-deploy` — `%h` is systemd's shorthand for
your home directory. That is why the checkout has to be at exactly
`~/atlas-phone-deploy`; `install.sh` refuses anything else rather than install
units that point at nothing.

---

# Cutover — putting the line on this code

Do this when you are ready for a short interruption (the restart is about three
seconds; a call in progress is dropped). Best done when the line is quiet.

> Every command below refers to a file in your checkout. **If one of those
> files is not there, stop.** It means you are on a commit made before that
> part shipped — finish the branch first rather than working around it.

## Step 0 — pre-flight, while the old line keeps answering

Nothing here touches the running line.

**a. The suite**, run from the checkout you work in — the one whose Python
environment has `pytest` in it. The deployment's own environment deliberately
does not; it carries what the bridge needs to answer calls and nothing else.

```bash
cd <the checkout you work in>          # NOT ~/atlas-phone-deploy
PYTHONPATH=$PWD:$PWD/src python -m pytest -q -W error tests/test_phone_agent*.py
```

Expected: `711 passed`. This is also the websocket simulation the cutover plan
calls for — `tests/test_phone_agent_hardening.py` and
`tests/test_phone_agent_runtime.py` open real websockets to the real relay
handler and assert what happened to the caller's message through a malformed
frame, a replayed token, an unwritable message file and a dead notification
channel. A failure here is a reason not to cut over today.

**b. The settings, validated exactly as the service will validate them:**

```bash
set -a; . ~/.config/atlas-phone/env; set +a
cd ~/atlas-phone-deploy    # or your development checkout
python3 plugins/phone_agent/service.py --check
```

`--check` opens no database, no port and no network connection, so it is safe
beside the live line. Expected: `…businesses.toml is valid.`, the list of
businesses, the number count, the active model backend, the logins, and
`Every environment variable this config names is set.` Anything else is one
sentence saying what is wrong and exit code 1 — fix it before going on.

## Step 1 — install, and keep a way back

```bash
cd ~/atlas && git worktree add --detach ~/atlas-phone-deploy feat/phone-agent-product
~/atlas-phone-deploy/deploy/phone/install.sh ~/atlas-phone-deploy
cp ~/.config/systemd/user/atlas-phone-bridge.service \
   ~/atlas-phone-bridge.unit.backup-$(date +%F)
cd ~/atlas-phone-deploy && git log --oneline -1     # WRITE THIS DOWN
```

Two details in the first command matter:

- **`cd ~/atlas` first.** `git worktree add` only works from inside the repo.
- **`--detach`.** A deployment is pinned to one exact commit, not following a
  branch somebody might push to while a call is in progress. Detached also
  means it does not collide with the same branch checked out somewhere else on
  this machine (git refuses that, which is what you would hit without it).

`install.sh` creates `~/atlas-phone-deploy/.venv` (Python 3.11 or newer — older
versions cannot read the settings file's format), installs `aiohttp` and
`jinja2` into it, copies the three units into `~/.config/systemd/user/`, and
runs `systemctl --user daemon-reload`. It prints every step, and it **does
not** start, restart or enable anything: when it finishes, the phone line is
still running exactly what it was running before.

It stops with an explanation if the directory is not a git checkout of this
repo, is not at `~/atlas-phone-deploy`, if Python is too old, or if the
dependencies cannot be installed.

## Step 2 — what to add to the secrets file

`~/.config/atlas-phone/env`, mode 600. An older line is missing these:

| Add | Why |
|---|---|
| `WS_SECRET=<32 random hex characters>` | Gives every call its own websocket key, expiring in two minutes and usable once, instead of one shared key that never rotates and rides through the public web server's access log. **At least 16 characters** — the service refuses to start on a shorter one. `openssl rand -hex 32`. |
| `PHONE_OWNER_<NAME>_TOKEN=<a long random access code>` | One per dashboard login named in the settings file. Skip it only if you are staying on the single `ADMIN_TOKEN`. |
| `PHONE_DATA_DIR=…` | Optional. Only if the call store should not live in `~/.local/share/atlas-phone`. |
| `ADMIN_PORT=…` | Optional. Only if 8891 is taken. |

Check the file is still yours alone, and that both files are there:

```bash
ls -l ~/.config/atlas-phone/env ~/.config/atlas-phone/businesses.toml
```

Expected: `-rw-------` on `env`.

## Step 3 — what to add to the settings file

`~/.config/atlas-phone/businesses.toml`. Every setting is documented next to
its default in `plugins/phone_agent/businesses.example.toml`. For a line coming
from an older build, the ones that matter are:

- `timezone` for each business — **required** as soon as you set hours or
  holidays, and without it, message times and opening hours mean the machine's
  zone rather than the business's.
- `hours`, `holidays`, `after_hours`, `after_hours_greeting` if the business
  closes. Left out, the line answers the same way at 3am as at 3pm.
- `[owners.<name>]` for each dashboard login: `token_env` names the variable
  you added in step 2, and `profiles` lists what they may see (`["*"]` for
  everything).
- `[branding]` if the dashboard should carry your own name, logo and colours.
- The two notices are on by default and need nothing from you. If a business
  must have one off, it also needs `ack_disclosure_waived = true`, which is
  refused at start-up if it is missing.

Then run `--check` from step 0b again. Do not go on until it prints `is valid.`

## Step 4 — bring the old messages in

Messages taken before this build live only in the plain-text message file.
Import them, or the dashboard opens empty and a year of messages looks lost:

```bash
cd ~/atlas-phone-deploy
.venv/bin/python plugins/phone_agent/migrate_pad.py \
    --pad ~/atlas-phone-messages.md \
    --db ~/.local/share/atlas-phone/calls.db \
    --profile <the business key> --dry-run     # then again without --dry-run
```

It prints counts only, never caller details, and running it twice imports
nothing the second time.

**Run it with the bridge stopped.** On a first cutover that is automatic — the
new bridge has not been started yet and the old code does not use this database
at all. If you ever re-run it on a line that is live, stop the bridge first or
import into a copy of the database: the running service writes to it from the
same thread that is answering calls, with a five-second lock timeout, so a long
import competing with a live call can make that caller wait.

## Step 5 — the public front door and the fallback answer

Do this **before** the switch, and do the fallback file **before** you touch
Twilio: pointing Twilio at a URL that 404s is worse than leaving it unset.

**a. Read what Twilio holds now, beside what it should hold. Changes nothing:**

```bash
cd ~/atlas-phone-deploy
.venv/bin/python plugins/phone_agent/twilio_config.py --show
```

For every mapped number it prints the four settings — `voice_url`,
`voice_fallback_url`, `status_callback`, `sms_url` — each marked `ok:` or shown
as `now: … -> …`, then where that number's fallback file should be served, then
a line saying how many settings `--apply` would write. It reads the account id,
the auth token and the public address out of the secrets file itself, and it
never prints the token.

`voice_url` is read but never written by `--apply` — it is the one that makes
the number answer at all, and a wrong value there is a dead line. If it does not
match, `--show` says so loudly on the error output; change it in the Twilio
console, or with `--apply-voice-url --yes` once you are sure.

**b. Write the fallback answers and serve them from the public address:**

```bash
.venv/bin/python plugins/phone_agent/twilio_config.py --render
```

`--render` writes `deploy/phone/rendered/fallback-<digits>.xml`, one per
number: a sentence and a transfer to that business's number, or a sentence and
a hang-up when it has none. Copy it to the public server and serve it:

```bash
scp deploy/phone/rendered/fallback-<digits>.xml \
    <public server>:/var/www/atlas-phone/fallback.xml
# on that server, as root: paste deploy/phone/nginx-phone-fallback.conf into
# the server block that already proxies your /phone/ path, then
nginx -t && systemctl reload nginx
```

`nginx-phone-fallback.conf` carries its own installation notes, including the
one trap: a `location ^~ /phone/` proxy block beats the regex block, which
would send the per-number fallback files down the tunnel — exactly wrong when
the tunnel is what is broken.

**Prove it from your own machine before going near Twilio:**

```bash
curl -i "$(grep '^PUBLIC_BASE=' ~/.config/atlas-phone/env | cut -d= -f2- | tr -d '"')/fallback.xml"
```

Expected: `HTTP/1.1 200`, `Content-Type: text/xml`, and a body containing
`<Response>`. Anything else — 404, HTML, a redirect — means the fallback would
not work. Fix that first.

**c. Then, and only then, write the settings Twilio should hold:**

```bash
.venv/bin/python plugins/phone_agent/twilio_config.py --apply
```

`--apply` writes only the fields that differ, prints each one, and never
touches a setting it does not manage or the `voice_url`.

## Step 6 — switch

```bash
systemctl --user daemon-reload
systemctl --user restart atlas-phone-bridge.service
systemctl --user restart atlas-phone-tunnel.service
systemctl --user status atlas-phone-bridge.service --no-pager
```

Expected: `active (running)`. The tunnel is restarted too because its unit file
changed as well — it now runs the guard script from the checkout instead of the
old directory. (Restarting it re-runs the guard; a few seconds of the public
address being unreachable is normal.)

Then move the old directory aside so nothing can accidentally run it again:

```bash
mv ~/atlas-phone-bridge ~/atlas-phone-bridge.archived-$(date +%F)
```

## Step 7 — verify, all of it, in order

**a. The bridge answers locally.**

```bash
curl -s http://127.0.0.1:8890/health
```

Expected: exactly `{"status": "ok"}`. A 503 with a short reason means the line
is up but reporting a problem — read the reason, then the dashboard's Overview.

**b. It answers through the public address — this is what Twilio sees.**

```bash
curl -si "$(grep '^PUBLIC_BASE=' ~/.config/atlas-phone/env | cut -d= -f2- | tr -d '"')/health" | head -1
```

Expected: `HTTP/2 200` (or `HTTP/1.1 200`).

**c. A signed webhook comes back as a real answer.** This is the check that
proves the whole chain: the public address, the tunnel, the signature, the
business lookup and the greeting the caller will actually hear. Put one of your
own mapped numbers in `TO`:

```bash
cd ~/atlas-phone-deploy
TO="+15085551234" .venv/bin/python - <<'PY'
import base64, hashlib, hmac, os, urllib.parse, urllib.request

env = {}
for line in open(os.path.expanduser("~/.config/atlas-phone/env"), encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")

url = env["PUBLIC_BASE"].rstrip("/") + "/voice/incoming"
form = {"CallSid": "CAtest00000000000000000000000001",
        "From": "+15550000000", "To": os.environ["TO"],
        "AccountSid": env["TWILIO_ACCOUNT_SID"]}
payload = url + "".join(k + form[k] for k in sorted(form))
signature = base64.b64encode(hmac.new(env["TWILIO_AUTH_TOKEN"].encode(),
                                      payload.encode(), hashlib.sha1).digest()).decode()
request = urllib.request.Request(
    url, data=urllib.parse.urlencode(form).encode(),
    headers={"X-Twilio-Signature": signature,
             "Content-Type": "application/x-www-form-urlencoded"})
with urllib.request.urlopen(request, timeout=15) as response:
    print(response.status)
    print(response.read().decode())
PY
```

Expected: `200`, then one line of XML containing `<ConversationRelay …>` whose
`welcomeGreeting` is the business's greeting **with the AI disclosure and the
recording notice composed into it** — read it, it is word for word what the
next caller hears. It prints no secret. It leaves nothing behind: this request
writes no row to the call log, and the websocket key inside it expires in two
minutes with nothing opening it.

Two useful failures: `403` means the signature did not match, which is almost
always `PUBLIC_BASE` not being the exact address Twilio calls, or the auth
token in the secrets file not being the account's current one. A spoken
configuration error instead of a relay means that `TO` is not in your settings.

**d. Nothing has failed.**

```bash
systemctl --user is-active atlas-phone-bridge.service atlas-phone-tunnel.service
```

Expected: `active` twice.

**e. The dashboard.** Open the https address you publish it at, sign in with
one owner's access code, and check the Overview's status band. Expected: five
checks, and no red. "The phone network connection has not been confirmed today"
is expected until the first real call arrives — it reads the time of the newest
call in your call log.

**f. The outside monitor.** Whatever polls `PUBLIC_BASE/health` from off this
machine should be green. It only reads the status code: 200 is up, 503 is
degraded and pages. *(In this install that monitor is the `atlas-phone-line`
tripwire.)*

**g. The pager — once, deliberately. It sends a real notification.**

```bash
systemctl --user start atlas-phone-alert@manual-test.service
journalctl --user -u atlas-phone-alert@manual-test.service -n 5 --no-pager
```

Expected: `paged ntfy about failed unit 'manual-test'` in the journal and a
notification on the phone. An error about `NTFY_URL` / `NTFY_TOPIC` instead
means the pager is not configured — fix that before trusting the line
unattended, because a failure at 2am would then be silent.

**h. The one only a human can do: call the number and talk to it.** Then check
that the message arrived on your phone and is on the Messages screen, and that
the call's page shows the transcript.

---

# Rollback

## If the cutover itself went wrong

The old setup is still on disk. Put it back:

```bash
systemctl --user stop atlas-phone-bridge.service
# the old code directory (use the date in its name)
mv ~/atlas-phone-bridge.archived-<date> ~/atlas-phone-bridge
# the old unit file (the copy from step 1)
cp ~/atlas-phone-bridge.unit.backup-<date> \
   ~/.config/systemd/user/atlas-phone-bridge.service
systemctl --user daemon-reload
systemctl --user start atlas-phone-bridge.service
systemctl --user restart atlas-phone-tunnel.service
curl -s http://127.0.0.1:8890/health
```

The tunnel is restarted at the end because it only carries the port — it does
not care which copy of the code is answering — so restarting it re-runs the
guard and gives the restored line a fresh, working forward.

Two things the rollback does **not** undo, on purpose:

- **The Twilio settings.** The fallback URL, status callback and SMS URL are
  additive and safe on the old code too; `--show` prints them if you want them
  gone, and they are changed back in the Twilio console.
- **The call store.** It is the record of what callers said. Leave it.

The archived directory's contents are also committed on the
`deploy-archive/2026-08-27` branch, so nothing is lost even if the directory is
deleted. Keep the directory itself for 30 days.

## If a later update broke it

Go back to the commit you wrote down before the update:

```bash
cd ~/atlas-phone-deploy
git checkout --detach <the commit id from before the update>
./deploy/phone/install.sh ~/atlas-phone-deploy
systemctl --user restart atlas-phone-bridge.service
systemctl --user restart atlas-phone-tunnel.service
curl -s http://127.0.0.1:8890/health
```

## If a settings change broke it

Every save on the dashboard backs the settings file up first
(`businesses.toml.bak-<date>`, newest 100 kept) and writes the change to the
Activity screen, which has a button that puts the previous version back through
the same validation as any other save. That is the first thing to try, and it
needs no shell.

---

# Updating the deployed code later

The deployment is pinned to one commit and stays there until you move it:

```bash
cd ~/atlas-phone-deploy
git log --oneline -1                    # WRITE THIS DOWN — it is your way back
git fetch
git checkout --detach <an exact commit id>
./deploy/phone/install.sh ~/atlas-phone-deploy   # picks up unit/dependency changes
set -a; . ~/.config/atlas-phone/env; set +a
python3 plugins/phone_agent/service.py --check   # before the restart, not after
systemctl --user restart atlas-phone-bridge.service
systemctl --user restart atlas-phone-tunnel.service
systemctl --user is-active atlas-phone-bridge.service atlas-phone-tunnel.service
curl -s http://127.0.0.1:8890/health
```

That commit id you wrote down is the whole rollback plan.

# Day to day

```bash
# is the line up?
systemctl --user is-active atlas-phone-bridge.service atlas-phone-tunnel.service

# what has the bridge been doing?
journalctl --user -u atlas-phone-bridge.service -n 100 --no-pager

# why did the tunnel reconnect?
journalctl --user -u atlas-phone-tunnel.service -n 50 --no-pager
```

The journal carries call ids, turn numbers and counts — never what anyone said,
and never a caller's full number. What was said is in the call store, which the
dashboard reads and which has a retention horizon and a delete path.

**About the tunnel.** When the home network blips, the public server does not
notice the old connection died; it keeps the port held open, so every reconnect
fails and callers get a 502 — for hours. `tunnel-guard.sh` runs before each
reconnect and clears that dead connection, but only after checking the port is
not already serving a healthy bridge, so it can never kill a working line. Its
server address, port and SSH key can be overridden with `PHONE_TUNNEL_VPS`,
`PHONE_TUNNEL_PORT` and `PHONE_TUNNEL_KEY`.

**Changing a unit file.** Edit it in the checkout, then re-run `install.sh` and
restart the unit you changed. Editing the copy in `~/.config/systemd/user/`
directly puts you right back where this started: a change that exists on one
machine and nowhere else.

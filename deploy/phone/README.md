# Running the phone line — deployment files and cutover runbook

This folder holds everything the **live phone line** needs to run, other than
the code itself. It exists because those files used to live only on the machine
that answers the calls: one wrong keystroke and there was no copy anywhere. Now
they are in git, they are tested, and a new deployment is a checkout plus one
install command.

Written for a non-developer working with an AI session: read a step, paste the
command, read what comes back. **If a step's output does not look like what this
page says it should, stop and say so — do not improvise on the phone line.**

## What is in here

| File | What it is |
|---|---|
| `install.sh` | Builds the Python environment and installs the three systemd units. Never starts or stops anything. |
| `alert.sh` | Sends the "the phone line has failed" push notification. Run by systemd, not by you. |
| `tunnel-guard.sh` | Clears a dead SSH tunnel off the VPS before reconnecting. The fix for the nightly 502s. |
| `../systemd/atlas-phone-bridge.service` | The bridge itself — the thing Twilio talks to. |
| `../systemd/atlas-phone-tunnel.service` | The SSH tunnel that carries the VPS's port 8890 to this machine. |
| `../systemd/atlas-phone-alert@.service` | The pager. Fires automatically when either of the other two fails. |

## How the pieces fit

A caller dials the Twilio number. Twilio sends the call to the public web
address (`PUBLIC_BASE`), which is the VPS. The VPS forwards it down an **SSH
tunnel** to this machine, where the **bridge** answers, talks to the model, and
streams words back. If either the bridge or the tunnel dies for good, systemd
runs the **alert** unit, which pushes a notification to the owner's phone.

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

## Where things live after the cutover

| Thing | Path |
|---|---|
| Code (a git checkout of this branch) | `~/atlas-phone-deploy` |
| Its Python environment | `~/atlas-phone-deploy/.venv` |
| Secrets and settings | `~/.config/atlas-phone/env` (mode 600) |
| Business profiles | `~/.config/atlas-phone/businesses.toml` |
| Installed units | `~/.config/systemd/user/` |
| The call store (calls, transcripts, messages) | `~/.local/share/atlas-phone/calls.db` (mode 700; `PHONE_DATA_DIR` moves it) |
| The message pad (Markdown, append-only) | `~/atlas-phone-messages.md` |
| The old hand-made directory | `~/atlas-phone-bridge.archived-<date>` (kept 30 days) |

The call store is the one file here that cannot be rebuilt from the repo: it
holds what callers said and the messages they left. Back it up with the
config, and remember it is the file a "delete my data" request has to reach.

The unit files use `%h/atlas-phone-deploy` — `%h` is systemd's shorthand for
your home directory. That is why the checkout has to be at exactly
`~/atlas-phone-deploy`; `install.sh` refuses anything else rather than install
units that point at nothing.

## Installing

```bash
cd ~/atlas && git worktree add --detach ~/atlas-phone-deploy feat/phone-agent-product
~/atlas-phone-deploy/deploy/phone/install.sh ~/atlas-phone-deploy
```

Two details in that first command matter:

- **`cd ~/atlas` first.** `git worktree add` only works from inside the repo,
  and `~/atlas` is the main copy of it.
- **`--detach`.** A deployment is pinned to one exact commit, not following a
  branch that someone might push to while a call is in progress. Detached also
  means it does not collide with the same branch being checked out somewhere
  else on this machine (git refuses that, which is what you would hit without
  the flag).

`install.sh` creates `~/atlas-phone-deploy/.venv` (Python 3.11 or newer —
older versions cannot read the TOML config), installs `aiohttp` and `jinja2`
into it, copies the three units into `~/.config/systemd/user/`, and runs
`systemctl --user daemon-reload`. It prints every step. It does **not** start,
restart or enable anything: after it finishes, the phone line is still running
exactly whatever it was running before.

It stops with an explanation if the directory is not a git checkout of the
Atlas repo, if it is not at `~/atlas-phone-deploy`, if Python is too old, or if
the dependencies cannot be installed.

## Cutover — switching the live line onto the checkout

Do this when you are ready for a short interruption (a restart is about three
seconds; a call in progress is dropped). Best done when the line is quiet.

> Every command below refers to a file in your checkout. **If one of those
> files is not there, stop.** It means you are on a commit made before that
> part shipped — finish the branch first rather than working around it.

**1. Install, and keep a copy of what is running now.** The two commands
above, plus this — it is what you restore if the switch goes wrong:

```bash
cp ~/.config/systemd/user/atlas-phone-bridge.service \
   ~/atlas-phone-bridge.unit.backup-$(date +%F)
```

**2. Settings and data.** Confirm both config files exist and that the secrets
file is readable only by you (`-rw-------`):

```bash
ls -l ~/.config/atlas-phone/env ~/.config/atlas-phone/businesses.toml
```

If the existing phone messages have not been imported into the new store yet,
run `plugins/phone_agent/migrate_pad.py` now — otherwise the dashboard opens
empty and old messages look lost.

The bridge validates all of this when it starts and **refuses to start on a
broken config** — a failed start with a clear reason in the journal is the
config check. It is better to find that out here than mid-call.

**3. The public front door.** The Twilio number's voice webhook must point at
`PUBLIC_BASE/voice/incoming`, and the VPS must serve a fallback answer when
this machine is unreachable, so a caller hears a sentence instead of silence.
Do both **before** the switch:

- `plugins/phone_agent/twilio_config.py --show` prints what Twilio currently
  has; `--apply` sets it to match your config. Read the `--show` output before
  applying it.
- Install `deploy/phone/nginx-phone-fallback.conf` and its rendered
  `fallback.xml` on the VPS, run `nginx -t`, reload nginx, then fetch the
  fallback URL and confirm it returns TwiML (XML starting with `<Response>`).

**4. Switch.**

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

**5. Verify — all of these, in order:**

```bash
# a. the bridge answers locally
curl -s http://127.0.0.1:8890/health

# b. it answers through the VPS (this is what Twilio sees)
curl -s "$(grep '^PUBLIC_BASE=' ~/.config/atlas-phone/env | cut -d= -f2-)/health"

# c. nothing has failed
systemctl --user is-active atlas-phone-bridge.service atlas-phone-tunnel.service
```

Then the one only a human can do: **call the number and talk to it.** Check
afterwards that the message pad got the call's note and that the notification
arrived on the phone.

**6. Check the pager works** (do this once, deliberately — it sends a real
notification):

```bash
systemctl --user start atlas-phone-alert@manual-test.service
journalctl --user -u atlas-phone-alert@manual-test.service -n 5 --no-pager
```

Expected: `paged ntfy about failed unit 'manual-test'` in the journal and a
notification on the phone. If instead you see an error about `NTFY_URL` /
`NTFY_TOPIC`, the pager is not configured — fix that before trusting the line
unattended, because a failure at 2am would then be silent.

## Updating the deployed code later

The deployment is pinned to one commit and stays there until you move it. To
put newer code on the line:

```bash
cd ~/atlas-phone-deploy
git log --oneline -1                    # WRITE THIS DOWN — it is your way back
git fetch
git checkout --detach feat/phone-agent-product   # or an exact commit id
./deploy/phone/install.sh ~/atlas-phone-deploy   # picks up unit/dependency changes
systemctl --user restart atlas-phone-bridge.service
systemctl --user restart atlas-phone-tunnel.service
systemctl --user is-active atlas-phone-bridge.service atlas-phone-tunnel.service
curl -s http://127.0.0.1:8890/health
```

Write down the commit id from before the update. That one line is the whole
rollback plan.

## If something goes wrong

**If you have already been running this deployment and an update broke it** —
go back to the commit you wrote down:

```bash
cd ~/atlas-phone-deploy
git checkout --detach <the commit id from before the update>
./deploy/phone/install.sh ~/atlas-phone-deploy
systemctl --user restart atlas-phone-bridge.service
systemctl --user restart atlas-phone-tunnel.service
curl -s http://127.0.0.1:8890/health
```

**If the first cutover itself went wrong** — put the old setup back; it is
still on disk:

```bash
systemctl --user stop atlas-phone-bridge.service
# put the old code directory back (use the date in its name)
mv ~/atlas-phone-bridge.archived-2026-08-27 ~/atlas-phone-bridge
# put the old unit file back (the copy you made in step 1)
cp ~/atlas-phone-bridge.unit.backup-2026-08-27 \
   ~/.config/systemd/user/atlas-phone-bridge.service
systemctl --user daemon-reload
systemctl --user start atlas-phone-bridge.service
systemctl --user restart atlas-phone-tunnel.service
curl -s http://127.0.0.1:8890/health
```

The tunnel is restarted at the end because it only carries port 8890 — it does
not care which copy of the code is answering — so restarting it re-runs the
guard and gives the restored line a fresh, working forward.

The old directory's contents are also committed on the `deploy-archive/2026-08-27`
branch, so nothing is lost even if the directory is deleted. Keep the archived
directory itself for 30 days.

## Day-to-day

```bash
# is the line up?
systemctl --user is-active atlas-phone-bridge.service atlas-phone-tunnel.service

# what happened on the last calls?
journalctl --user -u atlas-phone-bridge.service -n 100 --no-pager

# why did the tunnel reconnect?
journalctl --user -u atlas-phone-tunnel.service -n 50 --no-pager
```

**About the tunnel.** When the home network blips, the VPS does not notice the
old connection died; it keeps the port held open, so every reconnect fails and
callers get a 502 — for hours. `tunnel-guard.sh` runs before each reconnect and
clears that dead connection, but only after checking the port is not serving a
healthy bridge, so it can never kill a working line. Its VPS address, port and
SSH key can be overridden with `PHONE_TUNNEL_VPS`, `PHONE_TUNNEL_PORT` and
`PHONE_TUNNEL_KEY`.

**Changing a unit file.** Edit it in the checkout, then re-run `install.sh` and
restart the unit you changed. Editing the copy in `~/.config/systemd/user/`
directly puts you right back where this started: a change that exists on one
machine and nowhere else.

#!/usr/bin/env bash
# Install the phone line's systemd units and build its virtualenv.
#
# What it does:  creates <checkout>/.venv with the bridge's dependencies,
#                copies the three unit files into ~/.config/systemd/user/,
#                runs `systemctl --user daemon-reload`, prints the next steps.
# What it NEVER does: start, restart or enable anything. Taking the live phone
#                line down is a deliberate human step (see README.md, "Cutover"),
#                never a side effect of running an installer.
#
# Usage: deploy/phone/install.sh ~/atlas-phone-deploy
set -euo pipefail

DEPLOY_DIR_NAME="atlas-phone-deploy"      # the path baked into the unit files
UNITS=(atlas-phone-bridge.service atlas-phone-tunnel.service atlas-phone-alert@.service)
# Pinned to the major versions this code is written and tested against. An
# unpinned re-install the day aiohttp 4 lands would take a live phone line down
# on a dependency nobody chose to upgrade.
PYDEPS=("aiohttp>=3.9,<4" "jinja2>=3.1,<4")

die() { echo "[phone-install] ERROR: $*" >&2; exit 1; }
say() { echo "[phone-install] $*"; }

# ------------------------------------------------------------- the target --

if [ $# -ne 1 ]; then
  echo "[phone-install] ERROR: wrong number of arguments." >&2
  echo "usage: $0 <checkout_dir>    (e.g. $0 \"\$HOME/$DEPLOY_DIR_NAME\")" >&2
  exit 2
fi

target="$1"
[ -d "$target" ] || die "'$target' does not exist (or is not a directory)."
target="$(cd "$target" && pwd -P)"

# Refuse anything that is not the phone agent's own git checkout: installing
# units that point at a directory without service.py would give a phone line
# that fails at every start, which is worse than not installing at all.
top="$(git -C "$target" rev-parse --show-toplevel 2>/dev/null || true)"
if [ "$top" != "$target" ] || [ ! -f "$target/plugins/phone_agent/service.py" ]; then
  die "'$target' is not a git checkout of the Atlas repo containing plugins/phone_agent/service.py. Create one first (a deploy is pinned to a commit, hence --detach): cd ~/atlas && git worktree add --detach \"\$HOME/$DEPLOY_DIR_NAME\" feat/phone-agent-product"
fi

# The unit files hardcode %h/atlas-phone-deploy (systemd expands %h to $HOME),
# so a checkout anywhere else would be installed and then never used.
expected="$HOME/$DEPLOY_DIR_NAME"
if [ "$target" != "$expected" ]; then
  die "the unit files run '$expected', but you pointed this at '$target'. Move (or re-create) the checkout at '$expected' and run this again."
fi

# ----------------------------------------------------------------- python --

# 3.11 is the floor: the config loader uses tomllib, which arrived in 3.11.
if command -v python3.11 >/dev/null 2>&1; then
  PY="$(command -v python3.11)"
else
  PY="$(command -v python3 || true)"
  [ -n "$PY" ] || die "no python3 on PATH — install Python 3.11 or newer first."
fi

pyver="$("$PY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "$PY is Python $pyver — the phone agent needs 3.11 or newer (it reads TOML config with tomllib). Install python3.11 and run this again."
say "using $PY (Python $pyver)"

# ------------------------------------------------------------------- venv --

venv="$target/.venv"
if [ -x "$venv/bin/python" ]; then
  say "reusing the existing venv at $venv"
else
  say "creating the venv at $venv"
  "$PY" -m venv "$venv" || die "could not create the venv at $venv"
fi

venvver="$("$venv/bin/python" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
"$venv/bin/python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "the venv at $venv is Python $venvver, which is older than 3.11. Delete it and run this again."

say "installing dependencies (${PYDEPS[*]}) — this needs internet"
"$venv/bin/pip" install --disable-pip-version-check --quiet "${PYDEPS[@]}" \
  || die "pip could not install ${PYDEPS[*]} into $venv — the bridge will not start without them."

# ------------------------------------------------------------------ units --

unit_dir="$HOME/.config/systemd/user"
mkdir -p "$unit_dir"
for u in "${UNITS[@]}"; do
  src="$target/deploy/systemd/$u"
  [ -f "$src" ] || die "unit file missing from the checkout: $src"
  install -m 0644 "$src" "$unit_dir/$u" || die "could not install $u into $unit_dir"
  say "installed $unit_dir/$u"
done

for s in "$target/deploy/phone/alert.sh" "$target/deploy/phone/tunnel-guard.sh"; do
  [ -x "$s" ] || die "$s is not executable — systemd cannot run it (fix: chmod +x '$s')."
done

systemctl --user daemon-reload \
  || die "'systemctl --user daemon-reload' failed — the new units are on disk but systemd has not read them."
say "systemd reloaded its unit files"

# ------------------------------------------------------------ next steps ---

cat <<EOF

[phone-install] DONE — and nothing was started, restarted or enabled.
The live phone line is still running whatever it was running before.

Next steps (full runbook: $target/deploy/phone/README.md):
  1. Check the config the units will load:
       ls -l \$HOME/.config/atlas-phone/env \$HOME/.config/atlas-phone/businesses.toml
  2. Check the venv can load what the bridge needs:
       $venv/bin/python -c "import aiohttp, jinja2; print('deps ok')"
  3. DO NOT restart the phone line yet. The Twilio webhook and the VPS
     fallback have to be in place BEFORE the switch, or a caller can hit a
     line that answers with nothing. Follow the runbook from its "Cutover"
     section, in order, all the way through the verification list:
       $target/deploy/phone/README.md
EOF

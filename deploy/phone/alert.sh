#!/usr/bin/env bash
# Page the owner when a phone-line systemd unit fails.
#
# Wired up as OnFailure=atlas-phone-alert@%n.service on the bridge and the
# tunnel: when systemd gives up restarting one of them, this pushes an urgent
# ntfy notification naming the dead unit.
#
# Rule of the house: an alert that cannot be sent must itself be LOUD. Every
# failure path here prints to stderr and exits non-zero, so a broken alerting
# path shows up in `journalctl --user -u atlas-phone-alert@…` (and leaves the
# alert unit itself in `failed`) instead of pretending the owner was told.
#
# Usage: alert.sh <unit-name>
# Env (from ~/.config/atlas-phone/env, loaded by the unit's EnvironmentFile):
#   NTFY_URL    base URL of the ntfy server, e.g. http://127.0.0.1:8092
#   NTFY_TOPIC  the topic the owner's phone subscribes to
set -euo pipefail

unit="${1:-}"
if [ -z "$unit" ]; then
  echo "[phone-alert] ERROR: no unit name given — usage: alert.sh <unit-name>" >&2
  exit 2
fi

url="${NTFY_URL:-}"
topic="${NTFY_TOPIC:-}"
if [ -z "$url" ] || [ -z "$topic" ]; then
  echo "[phone-alert] ERROR: NTFY_URL and NTFY_TOPIC must both be set in" \
       "~/.config/atlas-phone/env — CANNOT page anyone about failed unit" \
       "'$unit'. The phone line may be down and nobody has been told." >&2
  exit 1
fi
url="${url%/}"

body="systemd unit ${unit} FAILED on $(uname -n) at $(date -Is).
The phone line may be down — callers could be hearing nothing.
Check it: journalctl --user -u ${unit} -n 50 --no-pager
Restart it: systemctl --user restart ${unit}"

# curl's own diagnostics are kept separate from the status code so the error
# line below reads cleanly in the journal.
curl_err=$(mktemp)
trap 'rm -f "$curl_err"' EXIT

if ! code=$(curl -sS -m 15 -o /dev/null -w '%{http_code}' \
    -H "Title: Phone line unit FAILED: ${unit}" \
    -H "Priority: urgent" \
    --data-binary "$body" \
    "${url}/${topic}" 2>"$curl_err"); then
  echo "[phone-alert] ERROR: POST to ntfy failed for unit '$unit'" \
       "— the owner has NOT been paged. curl said: $(tr '\n' ' ' <"$curl_err")" >&2
  exit 1
fi

if [ "$code" != "200" ]; then
  echo "[phone-alert] ERROR: ntfy returned HTTP ${code} for unit '$unit'" \
       "— the owner has NOT been paged." >&2
  exit 1
fi

echo "[phone-alert] paged ntfy about failed unit '${unit}' (HTTP ${code})"

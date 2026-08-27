#!/usr/bin/env bash
# Clear a stale reverse-forward listener on the VPS before (re)opening the phone tunnel.
#
# Why this exists: when the home network blips, the ssh client dies but the VPS sshd
# never notices (sshd_config has no ClientAliveInterval), so the dead session keeps
# 127.0.0.1:8890 bound. Every reconnect then fails with "remote port forwarding failed"
# and nginx serves 502 to Twilio for HOURS. This runs as ExecStartPre and evicts the
# corpse so the very next reconnect binds.
#
# Safety rule: only evict a listener that is NOT serving a healthy bridge. A healthy
# port means a real tunnel is already up, and we must never kill that.
set -uo pipefail

VPS="${PHONE_TUNNEL_VPS:-linuxuser@66.42.116.215}"
PORT="${PHONE_TUNNEL_PORT:-8890}"
# Pin the key explicitly: without this, ssh falls back to the gnome-keyring agent,
# so a reboot before William logs in graphically would leave the phone line dead.
KEY="${PHONE_TUNNEL_KEY:-/home/magiccat/.ssh/AgentChad}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new
          -o IdentitiesOnly=yes -i "$KEY")

log() { echo "[tunnel-guard] $*"; }

if ! ssh "${SSH_OPTS[@]}" "$VPS" true 2>/dev/null; then
  log "ERROR: cannot reach $VPS over ssh — leaving port :$PORT alone"
  exit 1
fi

if ssh "${SSH_OPTS[@]}" "$VPS" "curl -sf -m 5 -o /dev/null http://127.0.0.1:$PORT/health" 2>/dev/null; then
  log "remote :$PORT already serving a healthy bridge — nothing to evict"
  exit 0
fi

holder=$(ssh "${SSH_OPTS[@]}" "$VPS" \
  "ss -tlnHp 'sport = :$PORT' 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u" 2>/dev/null)

if [ -z "$holder" ]; then
  log "remote :$PORT is free — proceeding"
  exit 0
fi

log "remote :$PORT held by pid(s) [${holder//$'\n'/ }] but NOT serving the bridge — evicting stale forward"
ssh "${SSH_OPTS[@]}" "$VPS" "kill ${holder//$'\n'/ }" 2>/dev/null || log "WARNING: kill returned non-zero"
sleep 2

if ssh "${SSH_OPTS[@]}" "$VPS" "ss -tlnH 'sport = :$PORT' 2>/dev/null | grep -q ." 2>/dev/null; then
  log "ERROR: :$PORT STILL bound after eviction — tunnel will fail to bind, phone line stays 502"
  exit 1
fi

log "remote :$PORT freed — reconnect can bind"
exit 0

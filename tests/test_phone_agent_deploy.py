# tests/test_phone_agent_deploy.py — the phone line's DEPLOYMENT files.
#
# Everything that keeps the live phone line running used to live outside the
# repo (a hand-edited unit, a guard script in a scratch directory). These tests
# pin the files now that they are in git, so a future edit cannot quietly break
# the deployment: the units must point at the deploy checkout, a failing unit
# must page instead of looping, the tunnel guard must stay byte-identical to the
# one proven on the live line, and both shell scripts must fail LOUDLY.
import configparser
import filecmp
import http.server
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
UNITS = REPO / "deploy" / "systemd"
PHONE = REPO / "deploy" / "phone"
PLUGIN = REPO / "plugins" / "phone_agent"

BRIDGE_UNIT = UNITS / "atlas-phone-bridge.service"
TUNNEL_UNIT = UNITS / "atlas-phone-tunnel.service"
ALERT_UNIT = UNITS / "atlas-phone-alert@.service"

ALERT_SH = PHONE / "alert.sh"
INSTALL_SH = PHONE / "install.sh"
GUARD_SH = PHONE / "tunnel-guard.sh"

# The guard script proven on the live line. Absent on any other machine (CI, a
# fresh clone) — those runs skip the byte-for-byte comparison rather than fail.
LIVE_GUARD = Path("/home/magiccat/atlas-phone-bridge/tunnel-guard.sh")

DEPLOY = "%h/atlas-phone-deploy"


def _unit(path: Path) -> configparser.ConfigParser:
    """Parse a systemd unit.

    strict=False: systemd allows a key to repeat (ExecStartPre=, After=).
    allow_no_value=True: `ExecStart=` with an empty value is legal (it resets).
    interpolation=None: unit values are full of %h/%i/%n specifiers, which
    configparser's default interpolation would treat as syntax errors.
    optionxform=str: systemd keys are case-sensitive.
    """
    cp = configparser.ConfigParser(
        strict=False, allow_no_value=True, interpolation=None
    )
    cp.optionxform = str  # type: ignore[method-assign]
    cp.read_string(path.read_text(encoding="utf-8"), source=str(path))
    return cp


# ------------------------------------------------------------ bridge unit --

def test_bridge_unit_runs_the_deploy_checkout():
    """The bridge must run the repo checkout's service.py from its own venv —
    not the old hand-made ~/atlas-phone-bridge directory."""
    cp = _unit(BRIDGE_UNIT)
    svc = cp["Service"]
    assert svc["ExecStart"] == (
        f"{DEPLOY}/.venv/bin/python {DEPLOY}/plugins/phone_agent/service.py"
    )
    assert svc["WorkingDirectory"] == DEPLOY
    assert svc["EnvironmentFile"] == "%h/.config/atlas-phone/env"
    assert svc["Restart"] == "always"
    assert svc["RestartSec"] == "5"


def test_bridge_unit_waits_for_the_network_and_not_for_ollama():
    """After= alone orders against a target nothing pulled in; Wants= is what
    actually makes network-online.target happen. And the model backend is
    whichever brain is active (often a cloud API), so ordering behind a local
    ollama.service is wrong — audit L-8."""
    unit = _unit(BRIDGE_UNIT)["Unit"]
    assert "network-online.target" in unit["After"]
    assert "network-online.target" in unit["Wants"]
    # No dependency directive may name ollama (the comment explaining why it is
    # gone is allowed to, so this looks at the parsed values, not the text).
    for key in ("After", "Wants", "Requires", "BindsTo"):
        assert "ollama" not in unit.get(key, "")


def test_bridge_unit_pages_instead_of_looping():
    """A crash loop must end in `failed` (which fires the alert), not spin
    forever. Both start-limit keys belong in [Unit] — systemd ignores them in
    [Service] since v230."""
    cp = _unit(BRIDGE_UNIT)
    unit = cp["Unit"]
    assert unit["StartLimitIntervalSec"] == "300"
    assert unit["StartLimitBurst"] == "10"
    assert unit["OnFailure"] == "atlas-phone-alert@%n.service"


def test_bridge_unit_has_no_watchdog_and_says_why():
    """The bridge is a plain aiohttp app: it never calls sd_notify, so a
    WatchdogSec= would kill a healthy phone line every interval. The unit has
    to explain that, or someone will 'helpfully' add one."""
    text = BRIDGE_UNIT.read_text(encoding="utf-8")
    assert "WatchdogSec" not in _unit(BRIDGE_UNIT)["Service"]
    assert "sd_notify" in text


# ------------------------------------------------------------ tunnel unit --

def test_tunnel_unit_uses_the_repo_guard_and_reverse_forward():
    cp = _unit(TUNNEL_UNIT)
    svc = cp["Service"]
    assert svc["ExecStartPre"] == f"{DEPLOY}/deploy/phone/tunnel-guard.sh"
    exec_start = svc["ExecStart"]
    assert exec_start.startswith("/usr/bin/ssh ")
    assert "-R 127.0.0.1:8890:127.0.0.1:8890" in exec_start
    assert "-o ExitOnForwardFailure=yes" in exec_start
    # IdentitiesOnly + an explicit key: the tunnel must not depend on the
    # gnome-keyring agent being unlocked, or a reboot leaves the line dead.
    assert "-o IdentitiesOnly=yes" in exec_start
    assert svc["Restart"] == "always"
    assert svc["RestartSec"] == "15"


def test_tunnel_unit_pages_instead_of_looping():
    """audit M-8: an ssh tunnel that can never bind used to retry silently
    forever."""
    unit = _unit(TUNNEL_UNIT)["Unit"]
    assert unit["StartLimitIntervalSec"] == "600"
    assert unit["StartLimitBurst"] == "20"
    assert unit["OnFailure"] == "atlas-phone-alert@%n.service"


# ------------------------------------------------------------- alert unit --

def test_alert_unit_is_a_oneshot_that_runs_alert_sh():
    cp = _unit(ALERT_UNIT)
    svc = cp["Service"]
    assert svc["Type"] == "oneshot"
    assert svc["EnvironmentFile"] == "%h/.config/atlas-phone/env"
    assert svc["ExecStart"] == f"{DEPLOY}/deploy/phone/alert.sh %i"
    # Triggered only by OnFailure=; enabling it would make no sense.
    assert "Install" not in cp


@pytest.mark.parametrize("unit", [BRIDGE_UNIT, TUNNEL_UNIT, ALERT_UNIT])
def test_units_contain_no_absolute_home_paths(unit):
    """Units use %h so the same file works for any user — an absolute
    /home/<someone> path would silently run the wrong copy."""
    assert "/home/" not in unit.read_text(encoding="utf-8")


# ----------------------------------------------------------- shell scripts --

@pytest.mark.parametrize(
    "script", sorted(PHONE.glob("*.sh")), ids=lambda p: p.name
)
def test_scripts_are_valid_bash_and_executable(script):
    proc = subprocess.run(
        ["bash", "-n", str(script)], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert os.access(script, os.X_OK), f"{script.name} is not executable"
    assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")


def test_scripts_use_strict_mode():
    for script in (ALERT_SH, INSTALL_SH):
        assert "set -euo pipefail" in script.read_text(encoding="utf-8")


def test_tunnel_guard_is_byte_identical_to_the_live_one():
    """The guard is the fix for the nightly 502s; it is proven in production.
    The repo copy must be the same bytes, not a re-typed version."""
    if not LIVE_GUARD.exists():
        pytest.skip(
            f"live guard {LIVE_GUARD} not present on this machine "
            "(expected off the deployment box) — nothing to compare against"
        )
    assert filecmp.cmp(GUARD_SH, LIVE_GUARD, shallow=False), (
        f"{GUARD_SH} has drifted from the live {LIVE_GUARD}"
    )


# -------------------------------------------------------------- install.sh --

def _run_install(arg, home):
    env = dict(os.environ, HOME=str(home))
    return subprocess.run(
        [str(INSTALL_SH), str(arg)], capture_output=True, text=True, env=env
    )


def test_install_refuses_a_directory_that_is_not_a_checkout(tmp_path):
    """Pointing the installer at the wrong directory must stop it dead, not
    install units that run a python file which does not exist."""
    target = tmp_path / "not-a-checkout"
    target.mkdir()
    proc = _run_install(target, tmp_path)
    assert proc.returncode != 0
    assert "git checkout" in proc.stderr
    assert str(target) in proc.stderr
    assert not (tmp_path / ".config").exists()


def test_install_never_tells_anyone_to_restart_the_phone_line():
    """install.sh must not restart anything, and must not print a restart
    command either: the Twilio webhook and the VPS fallback have to be in place
    BEFORE the switch, so the only safe instruction it can give is 'follow the
    runbook'. A restart command sitting in its output is an invitation to skip
    that and drop callers onto a line that answers with nothing."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "systemctl --user restart" not in text
    assert "README.md" in text          # it points at the runbook instead
    assert "Cutover" in text


def _prose(path: Path) -> str:
    """A document as one line of plain words — markdown emphasis, code ticks,
    comment hashes and line wrapping taken out — so an assertion about a
    sentence does not depend on where the sentence happened to wrap."""
    text = path.read_text(encoding="utf-8")
    for mark in ("`", "*", "#"):
        text = text.replace(mark, "")
    return re.sub(r"\s+", " ", text)


SETUP_DOCS = (PHONE / "README.md", PLUGIN / "README.md",
              PLUGIN / "businesses.example.toml")


def test_every_setup_document_says_which_label_draws_the_safety_banner():
    """The red "not licensed for business use" banner is drawn by the words
    "test only" in a backend's label, and by nothing else. A rule nobody is
    told about is a banner that never appears — which is how a live line ran
    for weeks on a coding plan under a green Overview. All three documents a
    person sets a line up from have to say it, with an example label to copy."""
    for path in SETUP_DOCS:
        prose = _prose(path)
        assert '— test only"' in prose, f"no example label to copy in {path}"
        assert "red banner" in prose.lower(), f"{path} does not say what it draws"


def test_every_setup_document_says_to_give_each_business_its_own_push_topic():
    """The line-wide push address belongs to whoever runs the line. Every
    business left on it pushes to that one topic, so one subscription reads
    everybody's messages."""
    for path in SETUP_DOCS:
        assert "give every business its own" in _prose(path).lower(), \
            f"{path} does not say to give each business its own push topic"


def test_install_pins_the_two_libraries_the_bridge_needs():
    """A re-install is run on a line that is already carrying customers. An
    unpinned dependency means the next major release of aiohttp or jinja2
    installs itself into a phone line on a day nobody chose."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if ln.startswith("PYDEPS="))
    assert line == 'PYDEPS=("aiohttp>=3.9,<4" "jinja2>=3.1,<4")'


def test_install_tells_you_how_to_make_the_checkout_correctly():
    """The refusal message is the one command a non-developer will copy, so it
    has to work: `git worktree add` must run inside a repo, and without
    --detach git refuses outright when the branch is checked out elsewhere."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "cd ~/atlas && git worktree add --detach" in text


def test_readme_worktree_command_is_detached_and_run_from_the_repo():
    text = (PHONE / "README.md").read_text(encoding="utf-8")
    line = next(
        ln for ln in text.splitlines() if "git worktree add" in ln
    )
    assert "--detach" in line
    assert "cd ~/atlas" in line
    # And the way back from a bad update: re-pin to a known commit.
    assert "git checkout --detach" in text


def test_install_accepts_a_detached_checkout(tmp_path):
    """A deployment is pinned to a commit, so its checkout has no branch. The
    'is this a checkout?' test must not quietly depend on one."""
    repo = tmp_path / "atlas-phone-deploy"
    repo.mkdir()
    git = ["git", "-C", str(repo)]
    subprocess.run(git + ["init", "-q"], check=True)
    (repo / "plugins" / "phone_agent").mkdir(parents=True)
    (repo / "plugins" / "phone_agent" / "service.py").write_text("", "utf-8")
    subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
    subprocess.run(
        git + ["-c", "user.email=t@t", "-c", "user.name=t",
               "commit", "-qm", "init"],
        check=True, capture_output=True,
    )
    head = subprocess.run(
        git + ["rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(git + ["checkout", "-q", "--detach", head], check=True)

    # Run it with a different HOME so the very next check (the path check)
    # stops it: that proves the checkout test passed on a detached HEAD
    # without spending a minute building a venv here.
    proc = _run_install(repo, tmp_path / "elsewhere")
    assert proc.returncode != 0
    assert "not a git checkout" not in proc.stderr
    assert "the unit files run" in proc.stderr


def test_install_refuses_a_missing_directory(tmp_path):
    proc = _run_install(tmp_path / "nope", tmp_path)
    assert proc.returncode != 0
    assert "does not exist" in proc.stderr


def test_install_refuses_with_no_argument(tmp_path):
    proc = subprocess.run(
        [str(INSTALL_SH)], capture_output=True, text=True,
        env=dict(os.environ, HOME=str(tmp_path)),
    )
    assert proc.returncode != 0
    assert "usage" in proc.stderr.lower()


# ---------------------------------------------------------------- alert.sh --

class _Recorder(http.server.BaseHTTPRequestHandler):
    status = 200
    seen: list = []

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", 0))
        type(self).seen.append(
            (self.path, dict(self.headers), self.rfile.read(length))
        )
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, *_args):  # keep pytest output pristine
        pass


@pytest.fixture
def ntfy():
    """A throwaway ntfy stand-in, so the alert path is tested for real."""
    class Handler(_Recorder):
        seen: list = []

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, Handler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _run_alert(unit, **env_overrides):
    env = {k: v for k, v in os.environ.items()
           if k not in ("NTFY_URL", "NTFY_TOPIC")}
    env.update({k: v for k, v in env_overrides.items() if v is not None})
    return subprocess.run(
        [str(ALERT_SH), unit], capture_output=True, text=True, env=env
    )


def test_alert_fails_loudly_when_ntfy_is_not_configured():
    """An alert that cannot be sent must itself be visible in the journal —
    never a silent exit 0 that makes a dead phone line look fine."""
    proc = _run_alert("atlas-phone-bridge.service")
    assert proc.returncode != 0
    assert "NTFY_URL" in proc.stderr and "NTFY_TOPIC" in proc.stderr
    assert "atlas-phone-bridge.service" in proc.stderr


def test_alert_fails_loudly_with_no_unit_name():
    proc = subprocess.run(
        [str(ALERT_SH)], capture_output=True, text=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("NTFY_")},
    )
    assert proc.returncode != 0
    assert "usage" in proc.stderr.lower()


@pytest.mark.skipif(shutil.which("curl") is None, reason="curl not installed")
def test_alert_posts_an_urgent_titled_push(ntfy):
    server, handler = ntfy
    url = f"http://127.0.0.1:{server.server_address[1]}"
    proc = _run_alert(
        "atlas-phone-tunnel.service", NTFY_URL=url + "/", NTFY_TOPIC="phone-x"
    )
    assert proc.returncode == 0, proc.stderr
    assert len(handler.seen) == 1
    path, headers, body = handler.seen[0]
    assert path == "/phone-x"          # trailing slash on NTFY_URL is trimmed
    assert headers["Title"] == "Phone line unit FAILED: atlas-phone-tunnel.service"
    assert headers["Priority"] == "urgent"
    assert b"atlas-phone-tunnel.service" in body


@pytest.mark.skipif(shutil.which("curl") is None, reason="curl not installed")
def test_alert_fails_loudly_when_the_push_is_rejected(ntfy):
    server, handler = ntfy
    handler.status = 500
    url = f"http://127.0.0.1:{server.server_address[1]}"
    proc = _run_alert(
        "atlas-phone-bridge.service", NTFY_URL=url, NTFY_TOPIC="phone-x"
    )
    assert proc.returncode != 0
    assert "500" in proc.stderr


@pytest.mark.skipif(shutil.which("curl") is None, reason="curl not installed")
def test_alert_fails_loudly_when_ntfy_is_unreachable():
    # Port 1 on loopback: nothing listens there, connection refused instantly.
    proc = _run_alert(
        "atlas-phone-bridge.service",
        NTFY_URL="http://127.0.0.1:1", NTFY_TOPIC="phone-x",
    )
    assert proc.returncode != 0
    assert "atlas-phone-bridge.service" in proc.stderr

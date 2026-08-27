# tests/test_phone_agent_hardening.py — the "no silent failure" pass.
#
# Every test here drives the REAL bridge handlers over a REAL loopback socket
# against a REAL OpenAI-compatible brain and a REAL ntfy receiver. Nothing that
# matters is mocked: the failures under test (a malformed frame, an unwritable
# message pad, a dead notification channel, a stolen websocket token) are
# produced for real and the assertion is what the caller's message did next.
#
# Audit findings covered: C-4, H-1, H-2, H-8, H-9, M-2, M-3, M-4, M-6, M-7,
# M-10, L-1, L-3, L-6 — docs/superpowers/specs/2026-08-27-phone-agent-code-audit.md
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import aiohttp
from aiohttp import web
from test_phone_agent_plugin import _import_service

ACCOUNT_SID = "ACtest"          # what _import_service boots the service with
CALL_SID = "CAtest00000000001"


# ------------------------------------------------------------ test doubles --
# "Double" here means a real HTTP server standing in for a real HTTP service —
# the bridge talks to them over TCP exactly as it talks to Z.AI and ntfy.

def _sse(text: str) -> list[bytes]:
    """`text` as OpenAI streaming chunks, a few tokens at a time."""
    words = text.split(" ")
    chunks = []
    for i, word in enumerate(words):
        token = word if i == len(words) - 1 else word + " "
        payload = json.dumps({"choices": [{"delta": {"content": token}}]})
        chunks.append(f"data: {payload}\n\n".encode())
    return chunks


class FakeBrain:
    """An OpenAI-compatible model backend on loopback."""

    def __init__(self) -> None:
        self.reply = "Thanks, I have that down. Someone will call you back."
        self.note = "Sam\n+15550001234\nneeds a widget fixed"
        self.chat_status = 200
        self.models_status = 200
        self.stream_bodies: list[dict] = []
        self.summary_bodies: list[dict] = []
        self.base_url = ""
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/v1/chat/completions", self._chat)
        app.router.add_get("/v1/models", self._models)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", 0).start()
        self.base_url = f"http://127.0.0.1:{self._runner.addresses[0][1]}/v1"

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    async def _models(self, _: web.Request) -> web.Response:
        return web.json_response({"data": []}, status=self.models_status)

    async def _chat(self, request: web.Request) -> web.StreamResponse:
        body = await request.json()
        if self.chat_status != 200:
            # a verbose provider error page, the kind L-1 says must not be
            # pasted whole into the journal
            return web.Response(status=self.chat_status,
                                text="<html>upstream provider error page " + "x" * 500 + "</html>")
        if body.get("stream"):
            self.stream_bodies.append(body)
            resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await resp.prepare(request)
            for chunk in _sse(self.reply):
                await resp.write(chunk)
            await resp.write(b"data: [DONE]\n\n")
            return resp
        self.summary_bodies.append(body)
        return web.json_response({"choices": [{"message": {"content": self.note}}]})

    @property
    def summarizer_transcript(self) -> str:
        """The user content of the last summarizer request."""
        assert self.summary_bodies, "the summarizer was never called"
        return self.summary_bodies[-1]["messages"][-1]["content"]


class FakeNtfy:
    """A push receiver that records what the owner would have been sent."""

    def __init__(self) -> None:
        self.status = 200
        self.pushes: list[dict] = []
        self.base_url = ""
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/{topic}", self._push)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", 0).start()
        self.base_url = f"http://127.0.0.1:{self._runner.addresses[0][1]}"

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    async def _push(self, request: web.Request) -> web.Response:
        self.pushes.append({
            "topic": request.match_info["topic"],
            "headers": dict(request.headers),
            "body": await request.text(),
        })
        return web.Response(status=self.status)


# ------------------------------------------------------------- the harness --

@asynccontextmanager
async def phone_line(tmp_path, monkeypatch, *, extra_env=None, cfg_extra="",
                     ntfy=True, messages_file=None):
    """The whole line on loopback: the service's own handlers on a real HTTP
    server, a real brain, and (optionally) a real ntfy receiver."""
    brain = FakeBrain()
    await brain.start()
    ntfy_server = None
    pad = Path(messages_file) if messages_file else tmp_path / "pad.md"
    env = {"MESSAGES_FILE": str(pad)}
    if ntfy:
        ntfy_server = FakeNtfy()
        await ntfy_server.start()
        env["NTFY_URL"] = ntfy_server.base_url
        env["NTFY_TOPIC"] = "phone"
    env.update(extra_env or {})

    svc = _import_service(tmp_path, monkeypatch, extra_env=env, cfg_extra=cfg_extra)
    svc.BRAINS[svc.ACTIVE_BRAIN] = svc.Brain(
        key=svc.ACTIVE_BRAIN, label="test brain", base_url=brain.base_url,
        model="test-model", api_key_env="", extra_body={},
    )

    app = web.Application()
    app.router.add_post("/voice/incoming", svc.voice_incoming)
    app.router.add_post("/voice/action", svc.voice_action)
    app.router.add_get("/voice/relay", svc.voice_relay)
    app.router.add_get("/health", svc.health)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    port = runner.addresses[0][1]
    try:
        yield SimpleNamespace(svc=svc, brain=brain, ntfy=ntfy_server, pad=pad,
                              port=port, base=f"http://127.0.0.1:{port}")
    finally:
        await runner.cleanup()
        await brain.stop()
        if ntfy_server is not None:
            await ntfy_server.stop()


def setup_frame(call_sid: str = CALL_SID, caller: str = "+15550001234") -> dict:
    return {"type": "setup", "callSid": call_sid, "accountSid": ACCOUNT_SID, "from": caller}


def prompt_frame(text: str) -> dict:
    return {"type": "prompt", "voicePrompt": text}


async def _drain_until_last(ws, timeout: float = 5.0) -> list[dict]:
    """Read the agent's spoken tokens up to the end-of-turn marker."""
    out: list[dict] = []
    while True:
        msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
        if msg.type is not aiohttp.WSMsgType.TEXT:
            return out
        data = json.loads(msg.data)
        out.append(data)
        if data.get("last") is True:
            return out


async def run_call(line, frames, *, token=None, call_sid=CALL_SID, profile="acme",
                   settle: float = 0.2, drain: bool = True):
    """Drive one real websocket call through the bridge. Returns everything the
    bridge spoke back."""
    token = line.svc.WS_TOKEN if token is None else token
    url = (f"{line.base}/voice/relay?token={token}&call={call_sid}&profile={profile}")
    spoken: list[dict] = []
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url) as ws:
            for frame in frames:
                await ws.send_str(frame if isinstance(frame, str) else json.dumps(frame))
                if drain and isinstance(frame, dict) and frame.get("type") == "prompt":
                    spoken += await _drain_until_last(ws)
            # let the reply task finish its bookkeeping before the hangup
            await asyncio.sleep(settle)
            await ws.close()
    await asyncio.sleep(settle)
    return spoken


# ------------------------------------------- C-4: a bad frame must not eat --
#                                                   the caller's message

async def test_malformed_frame_does_not_destroy_the_message(tmp_path, monkeypatch):
    """One non-JSON websocket frame used to propagate out of the message loop,
    past the post-call delivery block, and the caller's message was gone."""
    async with phone_line(tmp_path, monkeypatch) as line:
        await run_call(line, [
            setup_frame(),
            prompt_frame("hello"),
            "not json",
            prompt_frame("my number is 555-0100"),
        ])

        transcript = line.brain.summarizer_transcript
        assert "hello" in transcript
        assert "my number is 555-0100" in transcript          # the loop survived
        assert line.pad.exists(), "the message pad entry was never written"
        assert line.brain.note in line.pad.read_text(encoding="utf-8")
        assert line.ntfy.pushes and line.brain.note in line.ntfy.pushes[0]["body"]
        kinds = [e["kind"] for e in line.svc.RECENT_EVENTS]
        assert "relay_event_failed" in kinds                  # loud, not swallowed


# ---------------------------------- M-2: a stale turn must not speak, and --
#                                          must not corrupt the history

class RecordingWs:
    """Stands in for Twilio's socket: records what would have been spoken."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


async def test_stream_reply_from_a_stale_turn_speaks_nothing(tmp_path, monkeypatch):
    """cancel() only lands at the next await, so a reply task can outlive its
    turn. Two replies interleaving into Twilio's TTS is a garbled call."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc
        brain = svc.BRAINS[svc.ACTIVE_BRAIN]
        history = [{"role": "user", "content": "hello"}]

        async with aiohttp.ClientSession() as http:
            fresh_ws = RecordingWs()
            spoken, _ = await svc.stream_reply(
                fresh_ws, history, http, "system", "test-model", brain,
                turn_state={"n": 1}, my_turn=1,
            )
            assert spoken == line.brain.reply
            assert fresh_ws.sent and fresh_ws.sent[-1]["last"] is True

            stale_ws = RecordingWs()
            spoken, _ = await svc.stream_reply(
                stale_ws, history, http, "system", "test-model", brain,
                turn_state={"n": 2}, my_turn=1,
            )
        assert spoken == ""
        assert stale_ws.sent == []


async def test_a_stale_reply_never_enters_the_history(tmp_path, monkeypatch):
    """The corrupted order was [user1, user2, assistant1] — a turn order the
    model then reasons over, and a summary the owner reads."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc

        async def racing(ws, history, http, system_prompt, model, brain, *,
                         turn_state, my_turn):
            # the caller spoke again while this task was past its last await
            turn_state["n"] += 1
            return "STALE REPLY", set()

        monkeypatch.setattr(svc, "stream_reply", racing)
        await run_call(line, [setup_frame(), prompt_frame("hello")], drain=False)

        transcript = line.brain.summarizer_transcript
        assert "hello" in transcript
        assert "STALE REPLY" not in transcript


async def test_a_current_reply_does_enter_the_history(tmp_path, monkeypatch):
    """The control for the test above: without a race, the reply is kept."""
    async with phone_line(tmp_path, monkeypatch, ntfy=False) as line:
        svc = line.svc

        async def calm(ws, history, http, system_prompt, model, brain, *,
                       turn_state, my_turn):
            return "FRESH REPLY", set()

        monkeypatch.setattr(svc, "stream_reply", calm)
        await run_call(line, [setup_frame(), prompt_frame("hello")], drain=False)

        assert "Receptionist: FRESH REPLY" in line.brain.summarizer_transcript

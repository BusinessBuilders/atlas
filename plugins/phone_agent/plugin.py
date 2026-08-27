# plugins/phone_agent/plugin.py — phone_line_status: lets Atlas answer
# "is the business phone line up?" by asking the phone bridge (service.py,
# running as its own systemd service) for its health.
#
# The PHONE side of this plugin deliberately exposes NO tools to callers —
# see service.py and README.md. This tool faces the OWNER through Atlas's
# normal gated tool stack, and it is read-only.
import os

from plugin_loader import plugin_tool

DEFAULT_HEALTH_URL = "http://127.0.0.1:8890/health"


async def handle_phone_line_status(params):
    import aiohttp  # heavy import stays out of boot path

    url = os.getenv("ATLAS_PHONE_HEALTH_URL", DEFAULT_HEALTH_URL)
    if not url.startswith(("http://127.0.0.1", "http://localhost")):
        await params.result_callback(
            {"ok": False,
             "error": f"ATLAS_PHONE_HEALTH_URL must be loopback, got {url!r} — "
                      "the phone bridge runs on this machine"}
        )
        return
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                body = await resp.json()
    except Exception as e:
        await params.result_callback(
            {"ok": False,
             "error": "phone bridge is DOWN — callers are getting Twilio's "
                      f"application error. ({type(e).__name__}: {e}) "
                      "Check: systemctl --user status atlas-phone-bridge"}
        )
        return

    # /health used to answer with the model, the profile keys and the number
    # count; it is publicly reachable, so it now answers with a status and a
    # short reason and nothing else (audit H-9). Both shapes are read here: a
    # bridge that has not been restarted yet still sends the old one.
    if "status" in body:
        degraded = body["status"] != "ok"
        reason = str(body.get("reason") or "the bridge is reporting a problem")
    else:
        degraded = body.get("model_backend") != "ok"
        reason = "model backend unreachable, callers hear an apology line"
    result = {
        "ok": True,
        "line": f"DEGRADED — {reason}" if degraded else "up",
    }
    # only present on a pre-H-9 bridge; the detail lives on the owner dashboard
    for key, field in (("model", "model"), ("profiles", "profiles"),
                       ("numbers_mapped", "numbers")):
        if field in body:
            result[key] = body[field]
    await params.result_callback(result)


TOOLS = [
    plugin_tool(
        name="phone_line_status",
        description="Check whether the business phone line (Twilio bridge) is up "
                    "and which business profiles are answering.",
        properties={},
        required=[],
        handler=handle_phone_line_status,
    )
]

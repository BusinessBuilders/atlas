# plugins/brief_review/plugin.py — spoken review of William's daily-brief queue.
# Reads/writes the SHARED review queue (agent-fleet owns the module, the Wealth
# OS dashboard writes the same DB) so a voice answer and a dashboard click can
# never disagree. Tripwires are excluded: system pages belong to the pager.
import sys

from plugin_loader import plugin_tool

REVIEW_QUEUE_SCRIPTS = "/home/magiccat/agent-fleet/scripts"
REVIEW_SOURCES = ("brief", "followup", "todo-review", "graduation")


def _queue():
    if REVIEW_QUEUE_SCRIPTS not in sys.path:
        sys.path.insert(0, REVIEW_QUEUE_SCRIPTS)
    import review_queue
    return review_queue


async def handle_brief_review(params):
    action = (params.arguments.get("action") or "").strip()
    try:
        rq = _queue()
        if action == "next":
            items = [i for i in rq.list_open() if i["source"] in REVIEW_SOURCES]
            if not items:
                await params.result_callback(
                    {"ok": True, "item": None, "remaining": 0,
                     "message": "queue clear — nothing to review"})
                return
            it = items[0]
            await params.result_callback(
                {"ok": True, "remaining": len(items),
                 "item": {"id": it["id"], "source": it["source"], "title": it["title"],
                          "body": it["body"], "since": it["first_seen"][:10]}})
        elif action == "mark":
            iid = (params.arguments.get("id") or "").strip()
            answer = (params.arguments.get("answer") or "").strip()
            if not iid or answer not in ("done", "keep", "dismissed"):
                await params.result_callback(
                    {"ok": False,
                     "error": "mark needs id and answer: done | keep | dismissed"})
                return
            row = next((i for i in rq.list_open() if i["id"] == iid), None)
            if row is None:
                await params.result_callback(
                    {"ok": False, "error": f"no open review item {iid}"})
                return
            if row["source"] == "tripwire":
                await params.result_callback(
                    {"ok": False,
                     "error": "that's a tripwire system page — the pager owns it, not the brief review"})
                return
            if answer == "keep":
                await params.result_callback(
                    {"ok": True, "id": iid, "status": "open",
                     "message": "kept — it returns tomorrow"})
                return
            marked = rq.mark(iid, answer)
            await params.result_callback({"ok": True, "id": iid, "status": marked["status"]})
        elif action == "summary":
            counts: dict[str, int] = {}
            for i in rq.list_open():
                if i["source"] in REVIEW_SOURCES:
                    counts[i["source"]] = counts.get(i["source"], 0) + 1
            await params.result_callback(
                {"ok": True, "open": counts, "total": sum(counts.values())})
        else:
            await params.result_callback(
                {"ok": False, "error": "action must be next | mark | summary"})
    except Exception as e:  # noqa: BLE001 — the model must hear the failure
        await params.result_callback({"ok": False, "error": f"review queue error: {e}"})


TOOLS = [
    plugin_tool(
        name="brief_review",
        description=(
            "Walk William through his open daily-brief items one at a time and "
            "record his answers (done / keep for tomorrow / not doing it). Backed "
            "by the same shared review queue the Wealth OS dashboard uses."
        ),
        properties={
            "action": {"type": "string", "enum": ["next", "mark", "summary"],
                       "description": "next = fetch next open item, mark = record an answer, summary = open counts"},
            "id": {"type": "string", "description": "item id from `next` (required for mark)"},
            "answer": {"type": "string", "enum": ["done", "keep", "dismissed"],
                       "description": "done = he did it; keep = not yet, returns tomorrow; dismissed = we're not doing it, never nag again"},
        },
        required=["action"],
        handler=handle_brief_review,
        requires_fields=("action",),
    )
]

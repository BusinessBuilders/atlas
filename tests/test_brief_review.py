"""brief_review plugin — spoken review of the shared review queue.
REVIEW_QUEUE_DB is monkeypatched per test (never the real DB)."""
import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "/home/magiccat/agent-fleet/scripts")


class FakeParams:
    def __init__(self, **arguments):
        self.arguments = arguments
        self.result = None

    async def result_callback(self, payload):
        self.result = payload


@pytest.fixture()
def rq(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_QUEUE_DB", str(tmp_path / "queue.db"))
    import review_queue
    importlib.reload(review_queue)
    return review_queue


@pytest.fixture()
def handler():
    spec = importlib.util.spec_from_file_location(
        "brief_review_plugin", ROOT / "plugins" / "brief_review" / "plugin.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.handle_brief_review


def _run(handler, **arguments):
    p = FakeParams(**arguments)
    asyncio.run(handler(p))
    return p.result


def test_next_serves_oldest_reviewable_and_skips_tripwires(rq, handler):
    rq.upsert("tripwire", "nova-rig", "[critical] nova-rig down")
    rq.upsert("brief", "book zip", "Attach the book zip")
    rq.upsert("followup", "Jack Blair", "Jack Blair follow-up")
    res = _run(handler, action="next")
    assert res["ok"] and res["remaining"] == 2
    assert res["item"]["source"] in ("brief", "followup")
    assert "nova-rig" not in str(res)


def test_mark_done_and_dismissed_suppress(rq, handler):
    a = rq.upsert("brief", "book zip", "Attach the book zip")
    b = rq.upsert("brief", "old plan", "Old plan")
    assert _run(handler, action="mark", id=a["id"], answer="done")["ok"]
    assert _run(handler, action="mark", id=b["id"], answer="dismissed")["ok"]
    assert rq.is_suppressed("brief", "book zip")
    assert rq.is_suppressed("brief", "old plan")


def test_keep_leaves_item_open(rq, handler):
    it = rq.upsert("brief", "book zip", "Attach the book zip")
    res = _run(handler, action="mark", id=it["id"], answer="keep")
    assert res["ok"] and res["status"] == "open"
    assert not rq.is_suppressed("brief", "book zip")


def test_tripwire_mark_is_refused(rq, handler):
    it = rq.upsert("tripwire", "nova-rig", "[critical] nova-rig down")
    res = _run(handler, action="mark", id=it["id"], answer="done")
    assert res["ok"] is False and "tripwire" in res["error"]
    assert not rq.is_suppressed("tripwire", "nova-rig")


def test_bad_action_and_bad_answer_refused(rq, handler):
    assert _run(handler, action="explode")["ok"] is False
    it = rq.upsert("brief", "x", "x")
    assert _run(handler, action="mark", id=it["id"], answer="maybe")["ok"] is False


def test_loader_accepts_the_plugin():
    import plugin_loader
    loaded = plugin_loader.load_plugins(reserved_names=set())
    tool = next(t for t in loaded if t.name == "brief_review")
    assert tool.risk == "medium"
    assert "brief_review" not in [e[0] for e in plugin_loader.plugin_load_errors()]

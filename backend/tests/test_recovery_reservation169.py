"""169 resource repair: recovery reads hold at most 1 of 2 slots and 4 of 8 pending.

`fresh=True` is the recovery flag: its only producer is `project_recovery_quote`,
whose only caller is the stream's normal-price recovery. Ordinary reads never set it.
"""
import ast
import asyncio
import pathlib
import pytest
from app.utils import folded_live_quote as fq
from tests.test_normal_recovery_projection159 import notice, quote

APP = pathlib.Path(fq.__file__).resolve().parents[1]


def _calls(name):
    found = []
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(), str(path))):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", None)) == name:
                found.append((path.relative_to(APP).as_posix(), node))
    return found


def test_only_the_recovery_path_marks_a_projection_fresh():
    fresh = [(path, call) for path, call in _calls("project")
             if any(k.arg == "fresh" for k in call.keywords)]
    assert [path for path, _ in fresh] == ["utils/live_fanout.py"]
    tree = ast.parse((APP / "utils/live_fanout.py").read_text())
    owners = [(f.name, k.value) for f in ast.walk(tree) if isinstance(f, ast.AsyncFunctionDef)
              for n in ast.walk(f) if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "project"
              for k in n.keywords if k.arg == "fresh"]
    assert len(owners) == 1
    (owner, flag), = owners
    assert owner == "project_recovery_quote"
    assert isinstance(flag, ast.Constant) and flag.value is True
    assert [path for path, _ in _calls("project_recovery_quote")] == []  # reached by getattr only
    route = (APP / "routes/event_stream.py").read_text()
    assert route.count('"project_recovery_quote"') == 1
    assert 'getattr(hub, "project_recovery_quote", None)' in route


class Gate:
    def __init__(self):
        self.started, self.release, self.active = [], asyncio.Event(), {}

    async def load(self, eid, origin, rev):
        self.started.append(eid)
        self.active[eid] = self.active.get(eid, 0) + 1
        try:
            await self.release.wait()
            return {**quote(), "event_id": eid, "blend_fold_revision": {str(eid): rev}}
        finally:
            self.active[eid] -= 1


async def settle():
    for _ in range(20):
        await asyncio.sleep(0)


async def test_ordinary_reads_keep_a_slot_and_their_pending_share(monkeypatch):
    gate = Gate(); monkeypatch.setattr(fq, "load_folded_quote", gate.load)
    projector = fq.FoldedQuoteProjector()
    recovery = [asyncio.create_task(projector.project(eid, notice(eid), fresh=True)) for eid in range(1, 7)]
    await settle()
    # Only 4 recovery entries were admitted; the other 2 wait, holding no entry.
    assert not any(task.done() for task in recovery) and projector._recovery_waiting == 2
    assert sum(1 for key in projector._pending if key[-1]) == fq.RECOVERY_MAX_PENDING == 4
    assert gate.started == [1]  # one recovery load active, three queued behind it
    ordinary = [asyncio.create_task(projector.project(eid, notice(eid))) for eid in range(21, 25)]
    await settle()
    assert len(projector._pending) == fq.MAX_PENDING
    assert gate.started == [1, 21]  # the second slot went to an ordinary read
    gate.release.set()
    results = await asyncio.gather(*ordinary)
    assert [r["event_id"] for r in results] == [21, 22, 23, 24]
    assert [r["event_id"] for r in await asyncio.gather(*recovery)] == [1, 2, 3, 4, 5, 6]
    assert not projector._pending and projector._recovery_waiting == 0


async def test_recovery_never_holds_both_slots_even_with_no_ordinary_reader(monkeypatch):
    gate = Gate(); monkeypatch.setattr(fq, "load_folded_quote", gate.load)
    projector = fq.FoldedQuoteProjector()
    tasks = [asyncio.create_task(projector.project(eid, notice(eid), fresh=True)) for eid in range(1, 5)]
    await settle()
    assert gate.started == [1] and sum(gate.active.values()) == 1
    gate.release.set()
    assert [r["event_id"] for r in await asyncio.gather(*tasks)] == [1, 2, 3, 4]


async def test_ordinary_reads_still_use_both_slots(monkeypatch):
    gate = Gate(); monkeypatch.setattr(fq, "load_folded_quote", gate.load)
    projector = fq.FoldedQuoteProjector()
    tasks = [asyncio.create_task(projector.project(eid, notice(eid))) for eid in range(21, 24)]
    await settle()
    assert gate.started == [21, 22]
    gate.release.set()
    await asyncio.gather(*tasks)


async def test_a_cancelled_queued_recovery_frees_its_reservation(monkeypatch):
    gate = Gate(); monkeypatch.setattr(fq, "load_folded_quote", gate.load)
    projector = fq.FoldedQuoteProjector()
    first = asyncio.create_task(projector.project(1, notice(1), fresh=True))
    queued = asyncio.create_task(projector.project(2, notice(2), fresh=True))
    await settle()
    assert gate.started == [1]
    queued.cancel(); first.cancel()
    await asyncio.gather(first, queued, return_exceptions=True)
    assert not projector._pending and sum(gate.active.values()) == 0
    # Both the recovery slot and the general slots are back: a new recovery starts at once.
    again = asyncio.create_task(projector.project(3, notice(3), fresh=True))
    await settle()
    assert gate.started == [1, 3]
    gate.release.set()
    assert (await again)["event_id"] == 3


async def test_a_timed_out_queued_recovery_keeps_its_effective_load_start(monkeypatch):
    gate = Gate(); monkeypatch.setattr(fq, "load_folded_quote", gate.load)
    monkeypatch.setattr(fq, "PROJECTION_TIMEOUT_S", 0.05)
    projector = fq.FoldedQuoteProjector()
    first = asyncio.create_task(projector.project(1, notice(1), fresh=True))
    queued = asyncio.create_task(projector.project(2, notice(2), fresh=True))
    assert await first is None and await queued is None
    # The queued read never reached a slot, so it is still one failure with the
    # ordinary backoff: it neither loaded nor was counted twice.
    assert gate.started == [1]
    assert projector._recovery_retry_after[2].failures == 1
    assert not projector._recovery_retry_after[2].spent

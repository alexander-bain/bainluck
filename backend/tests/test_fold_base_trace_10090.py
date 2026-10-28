"""#10090: a traced fold's committed base is receipted, joinable by its vector.

PILLARS: TRUTH / FORMATTING. SHIP: the acceptance case can be scored on a held
page whose two rows for one game are folded: the composed fold target can be
recomputed from the base it was composed on.

* FOLD_BASE carries the base's revision vector, owners/election, hero context
  and complete source bag, and the fold's own committed composition, once per
  distinct base; identical bases on other streams are counted, not written;
* a base becoming unavailable is one FOLD_BASE_UNAVAILABLE per transition;
* on the actual stream route, the base line joins the emitted fold frames by
  (event, base_fold_revision), and disarmed / armed-elsewhere / armed streams
  yield identical chunks.
"""

import asyncio
import json
import time

import pytest

from app.utils import fold_base_trace as fbt
from tests.test_folded_preview_v2_10090 import auth, setup


@pytest.fixture(autouse=True)
def _fresh():
    fbt.reset_for_tests()
    yield
    fbt.reset_for_tests()


def armed(events, **env):
    lines = []
    trace = fbt.FoldBaseTrace.from_env(
        {"FOLD_TRACE_EVENTS": ",".join(str(e) for e in events),
         "FOLD_TRACE_EXPIRES_AT": str(time.time() + 300), "FOLD_TRACE_MAX_LINES": "64",
         **env},
        emit=lambda text: lines.append(json.loads(text)), run="f",
    )
    assert trace is not None
    return trace, lines


def stage(lines, name):
    return [line for line in lines if line["stage"] == name]


def test_a_base_is_written_once_with_its_vector_bag_and_committed_hero():
    _session, base, _kalshi, _pm, _event = setup()
    trace, lines = armed([1])
    assert lines[0]["schema"] == "fold-base-trace/1"
    for session in ("s1", "s1", "s2"):
        trace.base(1, base, fold_session=session)
    (line,) = stage(lines, "FOLD_BASE")
    assert line["revision"] == {"1": 11, "2": 22, "3": 7} and line["members"] == ["1", "2", "3"]
    assert line["owners"] == {k: v for k, v in sorted(base.owners.items())}
    assert line["election"]["kalshi"] == 3
    assert line["context"]["status"] == base.context["status"]
    assert line["sport"] == base.sport and line["fold_session"] == "s1"
    assert line["bag_hash"] == fbt._hash(base.sources)
    assert {row["source"] for row in line["bag"]} <= set(base.sources)
    assert all("weight" not in row for row in line["bag"])  # the fold's own policy
    assert "tier" not in line and "recomputed_p" not in line
    committed = base.compose({}, {})
    assert line["committed"]["p"] == committed["p"]
    # A changed bag is a new base; the hidden identical uses are counted.
    base.sources["kalshi"] = {**base.sources["kalshi"], "value": 0.55}
    trace.base(1, base, fold_session="s3")
    second = stage(lines, "FOLD_BASE")[-1]
    assert second["sessions_hidden"] == 2 and second["bag_hash"] != line["bag_hash"]
    # Untraced event: nothing.
    trace.base(9, base)
    assert len(stage(lines, "FOLD_BASE")) == 2


def test_an_unavailable_base_is_one_line_per_transition():
    _session, base, *_ = setup()
    trace, lines = armed([1])
    trace.base(1, None)  # cold start: nothing known yet, nothing lost
    trace.base(1, base)
    trace.base(1, None)
    trace.base(1, None)
    trace.base(1, base)
    assert [x["stage"] for x in lines[1:]] == [
        "FOLD_BASE", "FOLD_BASE_UNAVAILABLE", "FOLD_BASE"]


def test_bounds_and_failure_containment():
    _session, base, *_ = setup()
    assert fbt.FoldBaseTrace.from_env({}) is None
    assert armed([1, 2, 3, 4])[0] is not None
    with pytest.raises(AssertionError):
        armed([1, 2, 3, 4, 5])
    trace, lines = armed([1], FOLD_TRACE_MAX_LINES="4")
    for value in (0.1, 0.2, 0.3, 0.4, 0.5):
        base.sources["kalshi"] = {**base.sources["kalshi"], "value": value}
        trace.base(1, base)
    assert len(lines) <= 4 and lines[-1]["reason"] == "BUDGET_STOP"
    assert lines[-1]["bases"] >= 1
    trace, _ = armed([1])
    trace.base(1, object())  # not a base: swallowed
    assert fbt.fold_base_trace() is None  # disarmed environment


async def _route(monkeypatch, trace):
    """The actual route over a folded-v2 stream: chunks plus decoded frames."""
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from tests.test_folded_event_stream_invalidation_837 import Hub, Request

    fbt.reset_for_tests(trace)
    if trace is None:
        fbt._TRACE = None
    monkeypatch.setattr(route, "fold_base_trace", fbt.fold_base_trace)
    _, base, kalshi, pm, _ = setup()
    hub = Hub()
    hub.folded_preview_base = lambda eid, **kw: base
    hub.forget_folded_preview = lambda eid: None

    async def recovery(*args):
        await asyncio.Event().wait()

    hub.project_recovery_quote = recovery
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "preview_route_events", lambda: {1})
    monkeypatch.setattr(route, "latest_frames", lambda ids: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(route, "_current_reconcile", lambda *args: asyncio.sleep(0, result={
        "event_id": 1, "custody_id": "state:test", "removal_rev": base.revision}))
    request = Request()
    request.query_params = {"preview_protocol": "folded-v2"}
    stream = route._stream(1, request, [1, 2, 3])
    chunks, shown = [], []
    try:
        chunks.append(await anext(stream))
        chunks.append(await anext(stream))
        chunks.append(await asyncio.wait_for(anext(stream), 1))
        for frame in (kalshi, pm):
            hub.subscriptions[f"live:event:{frame['event_id']}"].offer(json.dumps(frame))
            chunk = await asyncio.wait_for(anext(stream), 1)
            chunks.append(chunk)
            shown.append(json.loads(chunk.split("data: ")[1]))
    finally:
        await stream.aclose()
    return chunks, shown, base


def _normal(chunks):
    """Stream chunks with the per-stream random session id masked."""
    import re

    masks = ((r'"fold_session": "[0-9a-f]{32}"', '"fold_session": "S"'),
             (r'\d{4}-\d\d-\d\dT[0-9:.+]+', "TIME"),  # each rig's own `now`
             (r'"ttl_ms": \d+', '"ttl_ms": N'))
    out = []
    for chunk in chunks:
        for pattern, repl in masks:
            chunk = re.sub(pattern, repl, chunk)
        out.append(chunk)
    return out


async def test_on_the_actual_route_the_base_joins_its_frames_and_disarmed_is_identical(
    monkeypatch,
):
    off, _, _ = await _route(monkeypatch, None)
    elsewhere_trace, elsewhere = armed([77])
    other, _, _ = await _route(monkeypatch, elsewhere_trace)
    trace, lines = armed([1])
    on, shown, base = await _route(monkeypatch, trace)
    assert _normal(off) == _normal(other) == _normal(on)
    assert [x["stage"] for x in elsewhere] == ["START"]
    (line,) = stage(lines, "FOLD_BASE")
    for frame in shown:
        assert frame["preview"]["base_fold_revision"] == line["revision"]
        assert set(auth(frame)) <= set(line["election"].values()) | set(map(str, line["election"].values()))
    assert line["fold_session"] == shown[0]["preview"]["fold_session"]
    assert line["bag_hash"] == fbt._hash(base.sources)

"""#10090: the producer's selected reading is receipted before it can be sent.

PILLARS: TRUTH / FORMATTING. SHIP: the agreed held-page case can be scored from
each reading the server accepted to the moment a reader's headline showed it.

PREVIEW (#11675) is written after the send reply, so it cannot say when a state
first became eligible. These pin the receipt that can, inside the same traces:

* SELECTED is written at the refresher's decision with its wall+monotonic
  bracket, the selected market, oriented contributing outcomes, the exact
  observed basis joined to the trace's input_seq, the eligibility record and
  the disposition (proposal / refusal / no_reading / unobserved / unchanged /
  preview_only / stamp), on both the batch and the acknowledged-unchanged route;
* its ``sel`` rides the proposal into the ledger call: a composed frame's
  PREVIEW repeats it with the read-set's Redis clock (``reply[3]``) and the
  call's bracket, and the read-set's (gen, seq) is the frame's (epoch, seq);
* a proposal that composes nothing says so (READSET: the Redis status), and one
  that never reaches the ledger, or composed but was never observed sent, is
  closed by SELECTION_UNSENT with its reason;
* identical re-selections cost no line; a proposing repeat reuses its ``sel``;
* disarmed (no trace): no hook runs, the same Redis/DB calls are made, and
  ``_preview_before_stamp`` is called exactly as before.
"""

from datetime import datetime, timedelta, timezone
import json
import re
import time
from types import SimpleNamespace

import pytest

from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils import blend_preview
from app.utils.live_push import event_channel
from tests.test_blend_preview_display_before_persist_195 import (
    STORED, _PreviewSession, _capture_previews, _event,
)
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: F401
from tests.test_dnpl_redis_authority_10090 import initial, rig  # noqa: F401
from tests.test_fresh_observation_preview_10090 import acknowledged_rig
from tests.test_live_blend_refresh import _one_event_refresher
from tests.test_preview_state_join_10090 import (
    EVENT, K_OUTCOME, base_bag, kalshi_input, kalshi_trace, propose, registry, stage, wire,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _legacy_registry(monkeypatch):
    blend_preview.reset_registry_for_tests()
    monkeypatch.setattr(blend_preview, "_REGISTRY", blend_preview.PreviewRegistry())
    monkeypatch.setattr(blend_preview, "preview_events_for",
                        lambda source: frozenset(range(1, 600)) if source == "polymarket"
                        else frozenset())
    yield
    blend_preview.reset_registry_for_tests()


def traced(event=EVENT, outcome=K_OUTCOME):
    """A real Kalshi trace that tracks ``event`` (one retained commit)."""
    from app.tasks.live_blend_refresh import InputMark

    trace, lines = kalshi_trace()
    msg = {"market_ticker": "KXNBAGAME-26OCT28BOSPHI-BOS", "yes_bid_dollars": "0.6"}
    trace.received("socket", msg)
    mark = InputMark(seq=3, event_id=event, outcome_id=outcome, probability=0.6, kind="price",
                     recv_wall=time.time(), recv_mono=time.monotonic(), venue_ts_ms=None,
                     event_ordinal=3)
    trace.decided(msg, reason="ADMITTED", market=11, outcome=outcome, event=event,
                  probability=0.6, mark=mark)
    trace.committed(mark, datetime.now(timezone.utc) - timedelta(seconds=30))
    return trace, lines


def speaker(value=0.9, *, rows=(101,), seen=None):
    """A reading as the selector returns it: market, rows and eligibility."""
    from app.utils.live_blend import BLEND_ADMISSION_RULE
    from app.utils.probability_eligibility import verified_record

    seen = seen or datetime.now(timezone.utc) - timedelta(seconds=2)
    outcomes = tuple(SimpleNamespace(id=oid, current_probability=value, last_updated=seen)
                     for oid in rows)
    market = SimpleNamespace(id=10, external_id="KXNBAGAME-26OCT28BOSPHI-BOS")
    return SimpleNamespace(
        home_probability=value, away_probability=None, draw_probability=None,
        yes_probability=value, devigged=False, named_home_quote=True, market=market,
        outcome=outcomes[0], contributing_outcomes=outcomes,
        eligibility=verified_record(rule=BLEND_ADMISSION_RULE, market_id=10,
                                    source_market_id=market.external_id),
    )


def selector(monkeypatch, reading):
    box = [reading]
    monkeypatch.setattr("app.utils.live_blend.compute_source_home_probability",
                        lambda *a, **kw: box[0])
    return box


def attach(r, trace):
    from app.tasks.live_blend_refresh import TailReceipts

    r.receipts = TailReceipts(r.source)
    r.receipts.exact_trace = trace


class FakeLedger:
    """Only what the refresher's ledger branch reads; ops are captured, not run."""

    ledger = True
    claim_lock = None

    def __init__(self, propose=True):
        self.propose_ops = propose

    def expire(self):
        return []

    def propose(self, event_id, source, **kwargs):
        if not self.propose_ops:
            return []
        return [{"ledger_op": "propose", "event_id": event_id, "source": source,
                 "local_seq": 1, "chain": 1, "mode": "open"}]

    def pending_seq(self, event_id, source):
        return None

    def committed(self, *args, **kwargs):
        return []

    def refused(self, *args, **kwargs):
        return []

    def has_pending(self, *args):
        return False

    def unclaimed(self, source):
        return False


# ── the batch route (`_refresh_batch`) ──────────────────────────────────────

async def test_batch_selection_is_receipted_at_its_decision_and_rides_the_proposal(monkeypatch):
    event, market = _event()
    session = _PreviewSession([(market, event)], None, stored=STORED, rev=10)
    r, _ = _one_event_refresher(monkeypatch, session)
    trace, lines = traced(event=1, outcome=101)
    attach(r, trace)
    selector(monkeypatch, speaker())
    monkeypatch.setattr(blend_preview, "_REGISTRY", FakeLedger())
    sent = _capture_previews(monkeypatch, r, session)

    await r.refresh([1])

    (selected,) = stage(lines, "SELECTED")
    assert (selected["event"], selected["source"], selected["route"]) == (1, "polymarket", "refresh")
    assert (selected["disposition"], selected["then"]) == ("proposal", "PROPOSE")
    assert selected["value"] == 0.9 and selected["source_home_probability"] == 0.9
    assert selected["orientation"] == "AS_READ"
    assert selected["market"] == 10 and selected["market_ticker"] == "KXNBAGAME-26OCT28BOSPHI-BOS"
    assert selected["speaker_outcome"] == 101
    assert selected["contributing"] == [{"outcome": 101, "probability": 0.9}]
    assert selected["eligibility"]["source_market_id"] == "KXNBAGAME-26OCT28BOSPHI-BOS"
    assert selected["eligibility"]["status"] == "verified"
    assert selected["eligibility"]["rule"] == "live_blend.admissible_as_blend_speaker@5031"
    assert selected["select_start_mono"] <= selected["select_end_mono"] <= selected["emitted_mono"]
    assert selected["select_start_wall"] <= selected["select_end_wall"]
    assert selected["repeats_hidden"] == 0
    # The observed basis is the reading's own row; its clock is not the
    # retained commit's, so the input is named tracked-but-unjoined.
    assert list(selected["observed_basis"]) == ["101"] and selected["observed_basis_omitted"] == 0
    assert selected["inputs"] == [{
        "outcome": 101, "input_seq": "UNAVAILABLE",
        "linkage": "TRACKED_OUTCOME_NO_RETAINED_COMMIT_AT_THIS_OBSERVATION"}]
    # The proposal op carries the sel into the ledger call; nothing else changed.
    (op,) = [f for _, f in sent if isinstance(f, dict) and f.get("ledger_op") == "propose"]
    assert op["_trace"][0] == (selected["sel"], 1) and selected["attempt"] == 1
    assert op["_trace"][1] == trace.clock and op["_trace"][2] == trace.readset
    # Captured, never executed: the publication returned with no ledger outcome.
    (unsent,) = stage(lines, "SELECTION_UNSENT")
    assert (unsent["sel"], unsent["reason"]) == (selected["sel"], "NO_LEDGER_OUTCOME")


async def test_batch_no_reading_and_identical_repeats_cost_one_line(monkeypatch):
    event, market = _event()
    session = _PreviewSession([(market, event)], None, stored=STORED, rev=10)
    r, _ = _one_event_refresher(monkeypatch, session)
    trace, lines = traced(event=1, outcome=101)
    attach(r, trace)
    box = selector(monkeypatch, None)
    registry_box = FakeLedger(propose=False)
    monkeypatch.setattr(blend_preview, "_REGISTRY", registry_box)
    _capture_previews(monkeypatch, r, session)
    for _ in range(3):
        await r.refresh([1])
        r._last_refresh_at.clear()  # each call selects (no throttle)
    assert r.stats["no_reading"] == 3
    (selected,) = stage(lines, "SELECTED")
    assert (selected["disposition"], selected["then"], selected["value"]) == (
        "no_reading", "NONE", None)
    assert "market" not in selected and stage(lines, "SELECTION_UNSENT") == []
    # A different decision is written; the registry declines to propose it,
    # so the selection ends here, named.
    box[0] = speaker()
    await r.refresh([1])
    later = stage(lines, "SELECTED")[-1]
    assert later["disposition"] == "proposal" and later["sel"] == selected["sel"] + 1
    assert later["repeats_hidden"] == 2  # the two hidden no_reading repeats
    (unsent,) = stage(lines, "SELECTION_UNSENT")
    assert (unsent["sel"], unsent["reason"], unsent["ops"]) == (later["sel"], "NOT_PROPOSED", [])


async def test_hidden_repeat_count_is_reported_on_the_next_line(monkeypatch):
    trace, lines = traced(event=1)
    for _ in range(3):
        trace.selection(trace.selection_open(1), "kalshi", "unchanged", route="refresh",
                        value=0.5, basis={"7": 1.0})
    trace.selection(trace.selection_open(1), "kalshi", "unchanged", route="refresh",
                    value=0.51, basis={"7": 2.0})
    first, second = stage(lines, "SELECTED")
    assert first["repeats_hidden"] == 0 and second["repeats_hidden"] == 2
    # A proposing repeat writes nothing but returns the original sel as its
    # NEXT attempt (its outcome joins (sel, attempt)), opened for the closer.
    sel = trace.selection(trace.selection_open(1), "kalshi", "proposal", route="refresh",
                          value=0.6, basis={"7": 3.0}, then="PROPOSE")
    trace.readset(sel, {"event": 1, "reply": ["no_base"]}, "no_base")
    again = trace.selection(trace.selection_open(1), "kalshi", "proposal", route="refresh",
                            value=0.6, basis={"7": 3.0}, then="PROPOSE")
    assert again == (sel[0], 2) and len(stage(lines, "SELECTED")) == 3
    readset = stage(lines, "READSET")[-1]
    assert (readset["sel"], readset["attempt"]) == sel and "attempt_selected_mono" not in readset
    trace.selections_closed([again])
    unsent = stage(lines, "SELECTION_UNSENT")[-1]
    assert (unsent["sel"], unsent["attempt"]) == again
    assert isinstance(unsent["attempt_selected_mono"], float)


async def test_untracked_event_writes_no_selection():
    trace, lines = traced(event=1)
    assert trace.selection_open(2) is None
    assert trace.selection(None, "kalshi", "proposal", route="refresh", then="PROPOSE") is None
    assert stage(lines, "SELECTED") == []


# ── the acknowledged unchanged route (`preview_accepted_observations`) ──────

async def test_unchanged_route_receipts_selection_and_tags_its_proposal(monkeypatch):
    r, session, frames, _, rows, _, observations, validate, now = acknowledged_rig(monkeypatch)
    trace, lines = traced(event=1, outcome=rows[0].id)
    attach(r, trace)
    monkeypatch.setattr(blend_preview, "_REGISTRY", FakeLedger())
    await r.preview_accepted_observations(observations, validate)
    (selected,) = stage(lines, "SELECTED")
    assert (selected["route"], selected["disposition"], selected["then"]) == (
        "observation", "preview_only", "PROPOSE")
    bound = (now - timedelta(seconds=1)).timestamp()
    assert selected["observed_basis"] == {str(row.id): bound for row in rows}
    assert selected["proven_home_orientation"] is True
    (op,) = [f for _, f in frames if f.get("ledger_op") == "propose"]
    assert op["_trace"][0] == (selected["sel"], 1)


async def test_unchanged_route_names_a_send_boundary_refusal(monkeypatch):
    r, session, frames, _, rows, _, observations, validate, _ = acknowledged_rig(monkeypatch)
    trace, lines = traced(event=1, outcome=rows[0].id)
    attach(r, trace)
    monkeypatch.setattr(blend_preview, "_REGISTRY", FakeLedger())
    reads = []

    async def first_only(ids):
        reads.append(ids)
        return set(ids) if len(reads) == 1 else set()

    await r.preview_accepted_observations(observations, first_only)
    (selected,) = stage(lines, "SELECTED")
    (unsent,) = stage(lines, "SELECTION_UNSENT")
    assert (unsent["sel"], unsent["reason"]) == (selected["sel"], "NOT_ALLOWED")
    assert not frames


async def test_unchanged_route_unproven_orientation_is_a_no_reading(monkeypatch):
    r, session, frames, _, rows, reading, observations, validate, _ = acknowledged_rig(monkeypatch)
    reading.named_home_quote = False
    trace, lines = traced(event=1, outcome=rows[0].id)
    attach(r, trace)
    await r.preview_accepted_observations(observations, validate)
    (selected,) = stage(lines, "SELECTED")
    assert (selected["disposition"], selected["reason"], selected["then"]) == (
        "no_reading", "unproven_orientation", "NONE")
    assert selected["proven_home_orientation"] is False


# ── the real ledger (Redis) ─────────────────────────────────────────────────

async def ledger_setup(rig):  # noqa: F811 - imported pytest fixture
    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    call = client.execute_command
    k = registry(a, now)
    await k.claim(call, "kalshi")
    listener = client.pubsub()
    await listener.subscribe(event_channel(EVENT))
    await listener.get_message(timeout=1)
    return now, call, k, listener


def refresher_for(trace):
    r = LiveBlendRefresher("kalshi")
    attach(r, trace)
    return r


async def select(trace, value, seen, *, disposition="proposal", route="refresh"):
    return trace.selection(trace.selection_open(EVENT), "kalshi", disposition, route=route,
                           value=value, basis={str(K_OUTCOME): seen.timestamp()},
                           then="PROPOSE")


async def test_published_frame_repeats_sel_with_the_readset_redis_clock(rig):  # noqa: F811
    now, call, k, listener = await ledger_setup(rig)
    kt, lines = kalshi_trace()
    seen = now - timedelta(seconds=1)
    kalshi_input(kt, 5, 0.70, seen)
    try:
        sel = await select(kt, 0.70, seen)
        ops = await propose(k, call, "kalshi", 0.70, K_OUTCOME, seen, now=now, rev=10,
                            bag=base_bag(now))
        refresher_for(kt)._trace_proposal(sel, ops, EVENT, True)
        await k.execute(ops, call, event_channel, {}, observe=kt.preview)
        frame = await wire(listener)
        (selected,) = stage(lines, "SELECTED")
        (line,) = stage(lines, "PREVIEW")
        assert (selected["sel"], 1) == sel == (line["sel"], line["attempt"])
        assert selected["inputs"] == [{"outcome": K_OUTCOME, "input_seq": 5, "receive_id": 1,
                                       "linkage": "EXACT_OUTCOME_OBSERVATION_BASIS"}]
        readset = line["readset"]
        assert (readset["gen"], readset["seq"]) == (line["epoch"], line["seq"]) == (
            frame["preview"]["epoch"], frame["preview"]["seq"])
        assert (readset["op"], readset["mode"], readset["status"]) == ("propose", "open", "ok")
        assert readset["readset_clock"] == "REDIS_TIME_MS"
        assert readset["base_rev"] == 10 and isinstance(readset["local_seq"], int)
        # Same host: Redis TIME (ms) falls inside the worker's wall bracket.
        assert (readset["call_started_wall"] * 1000 - 5 <= readset["redis_ms"]
                <= readset["call_ended_wall"] * 1000 + 5)
        assert (selected["select_end_mono"] <= readset["call_started_mono"]
                <= readset["call_ended_mono"] <= line["emitted_mono"])
        (mine,) = [c for c in readset["read_contributors"] if c["source"] == "kalshi"]
        assert mine["owner"] == k.claims["kalshi"] and mine["deadline_ms"] > readset["redis_ms"]
        assert stage(lines, "READSET") == stage(lines, "SELECTION_UNSENT") == []
        kt.selections_closed([sel])
        assert stage(lines, "SELECTION_UNSENT") == []  # resolved by its PREVIEW
        assert "_trace" not in frame and "selection" not in str(frame)
    finally:
        await listener.aclose()


async def test_unchanged_observation_proposal_joins_its_preview(rig):  # noqa: F811
    now, call, k, listener = await ledger_setup(rig)
    kt, lines = kalshi_trace()
    seen = now - timedelta(seconds=1)
    kalshi_input(kt, 5, 0.70, seen)
    try:
        sel = await select(kt, 0.70, seen, disposition="preview_only", route="observation")
        ticket, _ = await k.read_ticket(call, "kalshi")
        event = SimpleNamespace(
            status="live", sport_key="basketball_nba", commence_time=now, completed_at=None,
            preview_context_at=now, preview_read_ticket=ticket,
            espn_win_prob_home=None, opening_home_probability=None,
        )
        # Acknowledged unchanged: the stored value is the proposed one, observed later.
        ops = k.propose(EVENT, "kalshi", value=0.70, event=event,
                        row_sources=base_bag(now, kalshi=0.70), row_rev=10,
                        observed_basis={str(K_OUTCOME): seen.timestamp()},
                        stamped_at=now, observation_only=True)
        refresher_for(kt)._trace_proposal(sel, ops, EVENT, True)
        await k.execute(ops, call, event_channel, {}, observe=kt.preview)
        frame = await wire(listener)
        (line,) = stage(lines, "PREVIEW")
        assert (line["sel"], line["attempt"]) == sel
        assert line["readset"]["seq"] == frame["preview"]["seq"]
    finally:
        await listener.aclose()


async def test_ledger_refusal_is_a_readset_line_with_the_redis_status(rig):  # noqa: F811
    now, call, k, listener = await ledger_setup(rig)
    kt, lines = kalshi_trace()
    seen = now - timedelta(seconds=1)
    kalshi_input(kt, 5, 0.70, seen)
    try:
        sel = await select(kt, 0.70, seen)
        # No committed base to adopt and none in the ledger: Redis says no_base.
        ops = await propose(k, call, "kalshi", 0.70, K_OUTCOME, seen, now=now, rev=10,
                            bag=None)
        refresher_for(kt)._trace_proposal(sel, ops, EVENT, True)
        await k.execute(ops, call, event_channel, {}, observe=kt.preview)
        (line,) = stage(lines, "READSET")
        assert (line["sel"], line["event"], line["outcome"], line["status"]) == (
            sel[0], EVENT, "no_base", "no_base")
        assert line["redis_ms"] == "UNAVAILABLE" and line["read"] == "NOT_A_READSET_REPLY"
        assert line["call_started_mono"] <= line["call_ended_mono"]
        assert stage(lines, "PREVIEW") == []
        kt.selections_closed([sel])
        assert stage(lines, "SELECTION_UNSENT") == []  # READSET already closed it
    finally:
        await listener.aclose()


async def test_composed_frame_lost_before_send_is_closed_with_its_readset(rig):  # noqa: F811
    now, call, k, listener = await ledger_setup(rig)
    kt, lines = kalshi_trace()
    seen = now - timedelta(seconds=1)
    kalshi_input(kt, 5, 0.70, seen)

    async def lost(*args):
        if "publish" in args:
            raise ConnectionError("socket lost before the publish reply")
        return await call(*args)

    try:
        sel = await select(kt, 0.70, seen)
        ops = await propose(k, call, "kalshi", 0.70, K_OUTCOME, seen, now=now, rev=10,
                            bag=base_bag(now))
        refresher_for(kt)._trace_proposal(sel, ops, EVENT, True)
        with pytest.raises(ConnectionError):
            await k.execute(ops, lost, event_channel, {}, observe=kt.preview)
        assert stage(lines, "PREVIEW") == stage(lines, "READSET") == []
        kt.selections_closed([sel])
        (unsent,) = stage(lines, "SELECTION_UNSENT")
        assert (unsent["sel"], unsent["reason"], unsent["status"]) == (
            sel[0], "COMPOSED_SEND_UNOBSERVED", "ok")
        assert isinstance(unsent["redis_ms"], int) and isinstance(unsent["seq"], int)
    finally:
        await listener.aclose()


async def test_an_unanswered_ledger_call_is_closed_as_such(rig):  # noqa: F811
    now, call, k, listener = await ledger_setup(rig)
    kt, lines = kalshi_trace()
    seen = now - timedelta(seconds=1)
    kalshi_input(kt, 5, 0.70, seen)

    async def dropped(*args):
        if "propose" in args:
            raise ConnectionError("socket lost before the propose reply")
        return await call(*args)

    try:
        sel = await select(kt, 0.70, seen)
        ops = await propose(k, call, "kalshi", 0.70, K_OUTCOME, seen, now=now, rev=10,
                            bag=base_bag(now))
        refresher_for(kt)._trace_proposal(sel, ops, EVENT, True)
        with pytest.raises(ConnectionError):
            await k.execute(ops, dropped, event_channel, {}, observe=kt.preview)
        kt.selections_closed([sel])
        (unsent,) = stage(lines, "SELECTION_UNSENT")
        assert (unsent["sel"], unsent["reason"], unsent["status"]) == (
            sel[0], "LEDGER_CALL_UNANSWERED", "NO_REPLY")
        assert unsent["call_ended_mono"] == "UNAVAILABLE" and unsent["op"] == "propose"
    finally:
        await listener.aclose()


async def test_a_stale_ticket_proposes_nothing_and_the_selection_says_so(rig):  # noqa: F811
    now, call, k, listener = await ledger_setup(rig)
    kt, lines = kalshi_trace()
    seen = now - timedelta(seconds=1)
    kalshi_input(kt, 5, 0.70, seen)
    try:
        sel = await select(kt, 0.70, seen)
        event = SimpleNamespace(
            status="live", sport_key="basketball_nba", commence_time=now, completed_at=None,
            preview_context_at=now, preview_read_ticket=-1,
            espn_win_prob_home=None, opening_home_probability=None,
        )
        ops = k.propose(EVENT, "kalshi", value=0.70, event=event, row_sources=base_bag(now),
                        row_rev=10, observed_basis={str(K_OUTCOME): seen.timestamp()},
                        stamped_at=now)
        assert ops == []
        refresher_for(kt)._trace_proposal(sel, ops, EVENT, True)
        (unsent,) = stage(lines, "SELECTION_UNSENT")
        assert (unsent["sel"], unsent["reason"], unsent["ops"]) == (sel[0], "NOT_PROPOSED", [])
    finally:
        await listener.aclose()


# ── disarmed controls ────────────────────────────────────────────────────────

def _refuse(name):
    def hook(*args, **kwargs):
        raise AssertionError(f"{name} ran without a trace")
    return hook


async def test_disarmed_batch_runs_no_receipt_work_and_the_same_calls(monkeypatch):
    real_hooks = {name: getattr(LiveBlendRefresher, name)
                  for name in ("_trace_selection", "_trace_proposal")}
    reading = speaker()  # one reading for both runs

    async def run(trace, *, refuse):
        event, market = _event()
        session = _PreviewSession([(market, event)], None, stored=STORED, rev=10)
        r, _ = _one_event_refresher(monkeypatch, session)
        attach(r, trace)
        selector(monkeypatch, reading)
        sent = _capture_previews(monkeypatch, r, session)
        kwargs_seen = []
        real = r._preview_before_stamp

        async def spy(*args, **kwargs):
            kwargs_seen.append(sorted(kwargs))
            return await real(*args, **kwargs)

        monkeypatch.setattr(r, "_preview_before_stamp", spy)
        for name, real_hook in real_hooks.items():
            monkeypatch.setattr(LiveBlendRefresher, name, _refuse(name) if refuse else real_hook)
        await r.refresh([1])
        # Two runs differ only in wall-clock stamps and the local ttl countdown.
        frames = [re.sub(r'\d{4}-\d\d-\d\dT[0-9:.+]+|"ttl_ms": \d+', "T",
                         json.dumps(f, sort_keys=True)) for _, f in sent]
        return [type(s).__name__ for s in session.statements], frames, kwargs_seen, r.stats

    calls_off, frames_off, kwargs_off, stats_off = await run(None, refuse=True)
    assert kwargs_off == [["observation_only"]]  # exactly the untraced call
    blend_preview.reset_registry_for_tests()
    monkeypatch.setattr(blend_preview, "_REGISTRY", blend_preview.PreviewRegistry())
    trace, lines = traced(event=1, outcome=101)
    calls_on, frames_on, kwargs_on, stats_on = await run(trace, refuse=False)
    assert stage(lines, "SELECTED"), "the armed control did select"
    assert kwargs_on == [["observation_only", "selections"]]
    # No added database statement; the same frames; the same outcome counts.
    assert calls_on == calls_off and frames_on == frames_off and stats_on == stats_off


async def test_disarmed_unchanged_route_runs_no_receipt_work(monkeypatch):
    r, session, frames, _, _, _, observations, validate, _ = acknowledged_rig(monkeypatch)
    attach(r, None)
    monkeypatch.setattr(LiveBlendRefresher, "_trace_selection", _refuse("selection"))
    monkeypatch.setattr(LiveBlendRefresher, "_trace_proposal", _refuse("proposal"))
    await r.preview_accepted_observations(observations, validate)
    assert len(frames) == 1 and "_trace" not in frames[0][1]


async def test_disarmed_ledger_call_is_unchanged_and_runs_no_receipt_work(rig, monkeypatch):  # noqa: F811
    now, call, k, listener = await ledger_setup(rig)
    kt, lines = kalshi_trace()
    seen = now - timedelta(seconds=1)
    kalshi_input(kt, 5, 0.70, seen)
    sent = []

    async def counted(*args):
        sent.append(args)
        return await call(*args)

    try:
        for name in ("_readset_started", "_readset_replied", "observe_readset"):
            monkeypatch.setattr(blend_preview, name, _refuse(name))
        ops = await propose(k, call, "kalshi", 0.70, K_OUTCOME, seen, now=now, rev=10,
                            bag=base_bag(now))
        await k.execute(ops, counted, event_channel, {}, observe=kt.preview)
        untraced = await wire(listener)
        monkeypatch.undo()
        off = [(a[0], len(a)) for a in sent]
        sent.clear()
        seen2 = now - timedelta(seconds=0.5)
        kalshi_input(kt, 6, 0.71, seen2)
        sel = await select(kt, 0.71, seen2)
        ops = await propose(k, call, "kalshi", 0.71, K_OUTCOME, seen2, now=now, rev=10,
                            bag=base_bag(now))
        refresher_for(kt)._trace_proposal(sel, ops, EVENT, True)
        await k.execute(ops, counted, event_channel, {}, observe=kt.preview)
        traced_frame = await wire(listener)
        # No added round trip; the sel/receipt never reach Redis or the wire.
        assert [(a[0], len(a)) for a in sent] == off
        assert not any("_trace" in str(a) or "selection" in str(a) for a in sent)
        assert set(traced_frame) == set(untraced)
        assert set(traced_frame["preview"]) == set(untraced["preview"])
        assert stage(lines, "PREVIEW")[-1]["sel"] == sel[0]
    finally:
        await listener.aclose()

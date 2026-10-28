"""#10090: the selection receipt's revise round (lane1b R1-R3, Measurement M-a).

PILLARS: TRUTH / FORMATTING. SHIP: the acceptance case can be scored with no
false "delivered" line: every selection gets exactly one true terminal outcome.

* R1: a proposal excluded by the chosen committed base ends at its READSET; the
  stale-settle frame it triggers (composed WITHOUT the selected value) carries
  no ``sel``.
* R2: an attempt that exits before its preview phase (a lock-budget raise, a
  cancellation) still closes every open PROPOSE selection.
* R3: dedupe never hides a different basis; RECHECK_CHANGED, COMPOSE_ERROR and
  the observation route's error closer are each named; the select bracket is a
  real interval.
* M-a1: outcomes join ``(sel, attempt)``: a proposing repeat is a new attempt.
* M-a2: the dedupe signature includes the complete witness (reading,
  eligibility, full basis), and the SELECTED line carries it.
* M-a3: a contributor recompose keeps the selection only while the recomposed
  frame holds the selected entry; the refused send is not a terminal.
* M-a6: eligibility version/semantic_type and omitted counts are emitted.
* An outcome in the selection's basis this trace has no identity for is named.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils import blend_preview
from app.utils.kalshi_exact_trace import ExactKalshiTrace
from app.utils.live_push import event_channel
from tests.test_blend_preview_display_before_persist_195 import (
    STORED, _PreviewSession, _capture_previews, _event,
)
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: F401
from tests.test_dnpl_redis_authority_10090 import initial, rig  # noqa: F401
from tests.test_fresh_observation_preview_10090 import acknowledged_rig
from tests.test_live_blend_refresh import _one_event_refresher
from tests.test_preview_state_join_10090 import (
    EVENT, K_OUTCOME, PM_OUTCOME, TICKER, base_bag, kalshi_input, kalshi_trace, propose,
    registry, stage, wire,
)
from tests.test_selection_receipt_10090 import (  # noqa: F401
    FakeLedger, _legacy_registry, attach, refresher_for, select, selector, speaker, traced,
)

pytestmark = pytest.mark.asyncio


def terminals(lines, sel):
    """Every outcome line naming ``sel`` that IS an outcome."""
    return [line for line in lines
            if line.get("sel") == sel and (
                line["stage"] in ("READSET", "SELECTION_UNSENT")
                or (line["stage"] == "PREVIEW" and line.get("selection_terminal", True)))]


# ── R1: excluded by the chosen base ─────────────────────────────────────────

async def test_an_excluded_proposal_has_one_terminal_and_its_settle_frame_no_sel(rig):  # noqa: F811
    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    call = client.execute_command
    k, p = registry(a, now), registry(a, now)
    await k.claim(call, "kalshi")
    await p.claim(call, "polymarket")
    kt, lines = kalshi_trace()
    seen = now - timedelta(seconds=2)
    kalshi_input(kt, 5, 0.70, seen)
    sel = await select(kt, 0.70, seen)
    ops_k = await propose(k, call, "kalshi", 0.70, K_OUTCOME, seen, now=now, rev=10,
                          bag=base_bag(now))
    # Polymarket commits base rev 11 whose Kalshi observation is NEWER than the
    # selection's: the chosen base excludes the selected 0.70.
    newer = base_bag(now)
    newer["kalshi"] = {"value": 0.66, "updated_at": now.isoformat(),
                       "observed_basis": {str(K_OUTCOME): (now - timedelta(seconds=1)).timestamp()},
                       "observed_value": 0.66}
    ops_p = await propose(p, call, "polymarket", 0.40, PM_OUTCOME, seen, now=now, rev=11,
                          bag=newer)
    await p.execute(ops_p, call, event_channel, {})
    refresher_for(kt)._trace_proposal(sel, ops_k, EVENT, True)
    await k.execute(ops_k, call, event_channel, {}, observe=kt.preview)
    kt.selections_closed([sel])
    (only,) = terminals(lines, sel[0])
    assert (only["stage"], only["outcome"], only["op"]) == (
        "READSET", "EXCLUDED_BY_CHOSEN_BASE", "propose")
    # The stale settle's frame went out (its own send), carrying no selection.
    previews = stage(lines, "PREVIEW")
    assert previews and all("sel" not in line for line in previews)


# ── R2: the attempt exits before its preview phase ──────────────────────────

def batch_rig(monkeypatch, events=(1, 2)):
    rows = [_event(eid) for eid in events]
    session = _PreviewSession([(m, e) for e, m in rows], None, stored=STORED, rev=10)
    r, _ = _one_event_refresher(monkeypatch, session)
    trace, lines = traced(event=1, outcome=101)
    attach(r, trace)
    selector(monkeypatch, speaker())
    monkeypatch.setattr(blend_preview, "_REGISTRY", FakeLedger())
    return r, session, lines


@pytest.mark.parametrize("how", ["lock_budget", "cancelled"])
async def test_a_batch_aborted_in_compute_closes_the_open_selection(monkeypatch, how):
    """lane1b R2: event 1 selected PROPOSE; event 2 aborts the batch before
    the preview phase (its lock-budget setup fails, or it is cancelled)."""
    from app.utils.repair_lock_budget import (
        SET_LOCK_AND_STATEMENT_TIMEOUT_SQL, SET_LOCK_TIMEOUT_SQL,
    )

    r, session, lines = batch_rig(monkeypatch)
    original = r._oriented

    async def oriented(session_, event_id, home_prob, *, reading=None, before_fallback=None):
        if event_id == 2:
            if how == "cancelled":
                raise asyncio.CancelledError()
            await before_fallback()  # the cold read arms the budget first
        return await original(session_, event_id, home_prob, reading=reading,
                              before_fallback=before_fallback)

    monkeypatch.setattr(r, "_oriented", oriented)
    r.stamp_lock_timeout_ms = 250
    execute = session.execute

    async def refuse_budget(statement, *args, **kwargs):
        if statement in (SET_LOCK_TIMEOUT_SQL, SET_LOCK_AND_STATEMENT_TIMEOUT_SQL):
            raise RuntimeError("budget unavailable")
        return await execute(statement, *args, **kwargs)

    session.execute = refuse_budget
    with pytest.raises((asyncio.CancelledError, RuntimeError)):
        await r._refresh_batch([1, 2], 0.0)
    (selected,) = stage(lines, "SELECTED")
    assert (selected["event"], selected["then"]) == (1, "PROPOSE")
    (unsent,) = stage(lines, "SELECTION_UNSENT")
    assert (unsent["sel"], unsent["attempt"], unsent["reason"]) == (
        selected["sel"], 1, "NO_LEDGER_OUTCOME")


async def test_a_cancel_inside_the_preview_phase_closes_the_open_selection(monkeypatch):
    """The single-event production shape: `_publish_previews` catches only
    Exception, so a cancellation skips `_preview_before_stamp`'s own closer."""
    r, session, lines = batch_rig(monkeypatch, events=(1,))

    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(r, "_publish_previews", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await r._refresh_batch([1], 0.0)
    (selected,) = stage(lines, "SELECTED")
    (unsent,) = stage(lines, "SELECTION_UNSENT")
    assert (unsent["sel"], unsent["reason"]) == (selected["sel"], "NO_LEDGER_OUTCOME")


# ── R3 / M-a2: dedupe ───────────────────────────────────────────────────────

async def test_dedupe_never_hides_a_different_basis_or_witness():
    trace, lines = traced(event=1)
    first = speaker(0.6, rows=(101,))
    for _ in range(2):  # identical: one line
        trace.selection(trace.selection_open(1), "kalshi", "unchanged", route="refresh",
                        reading=first, value=0.6, basis={"101": 1.0})
    # Same disposition and value, DIFFERENT basis: a new state.
    trace.selection(trace.selection_open(1), "kalshi", "unchanged", route="refresh",
                    reading=first, value=0.6, basis={"101": 2.0})
    # Same disposition, value and basis, a different eligibility witness.
    from app.utils.probability_eligibility import verified_record

    other = speaker(0.6, rows=(101,))
    other.eligibility = verified_record(rule="other@1", market_id=10,
                                        source_market_id=TICKER)
    trace.selection(trace.selection_open(1), "kalshi", "unchanged", route="refresh",
                    reading=other, value=0.6, basis={"101": 2.0})
    # A basis that differs only BEYOND the shown slice (9 keys, 8 shown).
    wide = {str(100 + i): 1.0 for i in range(9)}
    wider = dict(wide, **{"108": 9.0})
    for basis in (wide, wider):
        trace.selection(trace.selection_open(1), "kalshi", "unchanged", route="refresh",
                        reading=other, value=0.6, basis=basis)
    lines_ = stage(lines, "SELECTED")
    assert len(lines_) == 5
    assert lines_[0]["observed_basis"] == {"101": 1.0}
    assert lines_[1]["observed_basis"] == {"101": 2.0} and lines_[1]["repeats_hidden"] == 1
    assert lines_[2]["witness"] != lines_[1]["witness"]
    assert lines_[3]["observed_basis"] == lines_[4]["observed_basis"]  # same shown slice
    assert lines_[3]["observed_basis_omitted"] == 1
    assert lines_[3]["witness"] != lines_[4]["witness"]
    assert all(len(line["witness"]) == 16 for line in lines_)


# ── R3: every unsent reason is named ────────────────────────────────────────

async def test_a_compose_error_is_named(monkeypatch):
    event, market = _event()
    session = _PreviewSession([(market, event)], None, stored=STORED, rev=10)
    r, _ = _one_event_refresher(monkeypatch, session)
    trace, lines = traced(event=1, outcome=101)
    attach(r, trace)
    selector(monkeypatch, speaker())

    class Broken(FakeLedger):
        def propose(self, event_id, source, **kwargs):
            raise RuntimeError("compose failed")

    monkeypatch.setattr(blend_preview, "_REGISTRY", Broken())
    _capture_previews(monkeypatch, r, session)
    await r.refresh([1])
    (selected,) = stage(lines, "SELECTED")
    (unsent,) = stage(lines, "SELECTION_UNSENT")
    assert (unsent["sel"], unsent["attempt"], unsent["reason"]) == (
        selected["sel"], 1, "COMPOSE_ERROR")


async def test_a_recheck_that_changed_is_named(monkeypatch):
    r, session, frames, _, rows, reading, observations, validate, now = acknowledged_rig(
        monkeypatch)
    trace, lines = traced(event=1, outcome=rows[0].id)
    attach(r, trace)
    monkeypatch.setattr(blend_preview, "_REGISTRY", FakeLedger())
    monkeypatch.setattr(r, "_current_reading_proof", lambda *a, **k: {"proof": True})
    import app.utils.live_blend as live_blend

    calls = []
    real = live_blend.compute_source_home_probability

    def selector_(group, home, away, **kwargs):
        calls.append(kwargs)
        out = real(group, home, away)
        if len(calls) > 1:  # the custody recheck at the send boundary
            out = SimpleNamespace(**{**vars(out), "home_probability": 0.42})
        return out

    monkeypatch.setattr(live_blend, "compute_source_home_probability", selector_)
    await r.preview_accepted_observations(observations, validate)
    (selected,) = stage(lines, "SELECTED")
    (unsent,) = stage(lines, "SELECTION_UNSENT")
    assert len(calls) == 2
    assert (unsent["sel"], unsent["reason"]) == (selected["sel"], "RECHECK_CHANGED")


async def test_the_observation_routes_error_closer_names_open_selections(monkeypatch):
    r, session, frames, _, rows, _, observations, validate, _ = acknowledged_rig(monkeypatch)
    trace, lines = traced(event=1, outcome=rows[0].id)
    attach(r, trace)
    monkeypatch.setattr(blend_preview, "_REGISTRY", FakeLedger())

    async def broken(initial, *, prepare_frames=None):
        await prepare_frames()
        raise RuntimeError("publication failed")

    monkeypatch.setattr(r, "_publish_previews", broken)
    assert await r.preview_accepted_observations(observations, validate) is False
    (selected,) = stage(lines, "SELECTED")
    (unsent,) = stage(lines, "SELECTION_UNSENT")
    assert (unsent["sel"], unsent["reason"]) == (selected["sel"], "NO_LEDGER_OUTCOME")


async def test_the_select_bracket_is_a_real_interval():
    clock = iter(float(i) for i in range(100, 200))
    lines = []
    trace = ExactKalshiTrace.from_env(
        {"WS_KALSHI_TRACE_TICKERS": TICKER, "WS_KALSHI_TRACE_EXPIRES_AT": "2000000000",
         "WS_KALSHI_TRACE_MAX_LINES": "64"},
        run="k", emit=lines.append, wall=lambda: 1_999_999_800.0, mono=lambda: next(clock),
    )
    trace.commits[K_OUTCOME] = {"event": EVENT, "stored_epoch": 1.0, "input_seq": 1}
    token = trace.selection_open(EVENT)
    trace.selection(token, "kalshi", "proposal", route="refresh", value=0.6,
                    basis={str(K_OUTCOME): 1.0}, then="PROPOSE")
    (line,) = stage(lines, "SELECTED")
    assert line["select_start_mono"] < line["select_end_mono"] <= line["emitted_mono"]


# ── M-a1: attempts ──────────────────────────────────────────────────────────

async def test_a_proposing_repeat_is_a_new_attempt_with_its_own_outcome():
    trace, lines = traced(event=1)
    keys = []
    for outcome in ("no_base", "no_base", "no_base"):
        key = trace.selection(trace.selection_open(1), "kalshi", "proposal", route="refresh",
                              value=0.6, basis={"7": 3.0}, then="PROPOSE")
        keys.append(key)
        trace.readset(key, {"event": 1, "reply": [outcome]}, outcome)
    assert [k[1] for k in keys] == [1, 2, 3] and len({k[0] for k in keys}) == 1
    readsets = stage(lines, "READSET")
    assert [(x["sel"], x["attempt"]) for x in readsets] == keys
    assert "attempt_selected_mono" not in readsets[0]
    assert readsets[1]["attempt_selected_mono"] <= readsets[2]["attempt_selected_mono"]
    assert len(stage(lines, "SELECTED")) == 1
    # Each attempt has exactly one terminal.
    assert len(terminals(lines, keys[0][0])) == 3


# ── M-a3: a contributor recompose ───────────────────────────────────────────

async def test_a_recompose_keeps_the_selection_only_with_its_entry(rig):  # noqa: F811
    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    call = client.execute_command
    k, p, successor = registry(a, now), registry(a, now), registry(a, now)
    await k.claim(call, "kalshi")
    await p.claim(call, "polymarket")
    listener = client.pubsub()
    await listener.subscribe(event_channel(EVENT))
    await listener.get_message(timeout=1)
    kt, lines = kalshi_trace()
    seen = now - timedelta(seconds=2)
    try:
        await p.execute(await propose(p, call, "polymarket", 0.40, PM_OUTCOME, seen, now=now,
                                      rev=10, bag=base_bag(now)), call, event_channel, {})
        await wire(listener)
        kalshi_input(kt, 5, 0.70, seen)
        sel = await select(kt, 0.70, seen)
        ops = await propose(k, call, "kalshi", 0.70, K_OUTCOME, seen, now=now, rev=10,
                            bag=base_bag(now))
        refresher_for(kt)._trace_proposal(sel, ops, EVENT, True)
        stats = {}
        frames = await k.prepare(ops, call, stats)
        assert set(frames[0]["preview"]["pending"]) == {"kalshi", "polymarket"}
        refused_at = (frames[0]["preview"]["epoch"], frames[0]["preview"]["seq"])
        await successor.claim(call, "polymarket")  # a contributor's owner changes
        await k.execute(frames, call, event_channel, stats, observe=kt.preview)
        sent = await wire(listener)
        kt.selections_closed([sel])
        assert stats["ledger_recomposed"] == 1 and sent["preview"]["pending"] == {"kalshi": 0.70}
        first, second = [x for x in stage(lines, "PREVIEW") if x.get("sel") == sel[0]]
        assert (first["publication"], first["selection_terminal"]) == ("contributor", False)
        assert (second["publication"], second["selection_terminal"]) == ("published", True)
        assert second["attempt"] == 1
        assert second["recomposed_from"] == {"epoch": refused_at[0], "seq": refused_at[1]}
        assert (second["readset"]["op"], second["readset"]["mode"]) == ("settle", "sync")
        assert (second["epoch"], second["seq"]) == (
            sent["preview"]["epoch"], sent["preview"]["seq"])
        kalshi = {row["source"]: row for row in second["sources"]}["kalshi"]
        assert (kalshi["role"], kalshi["value"]) == ("PENDING", 0.70), "it holds the selection"
        assert len(terminals(lines, sel[0])) == 1
    finally:
        await listener.aclose()


async def test_a_recompose_without_the_selected_entry_is_named_not_joined():
    trace, lines = traced(event=EVENT, outcome=K_OUTCOME)
    stamped = datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc)
    receipt = {"event": EVENT, "op": "propose", "_proposed": ("kalshi", 0.70, stamped.isoformat()),
               "reply": ["ok", "1", "3", "1"]}
    key = trace.selection(trace.selection_open(EVENT), "kalshi", "proposal", route="refresh",
                          value=0.70, basis={str(K_OUTCOME): 1.0}, then="PROPOSE")
    trace.readset(key, receipt, "COMPOSED")

    def frame(value):
        return {"event_id": EVENT, "preview": {
            "kind": "blend", "epoch": 1, "seq": 4,
            "pending_entries": {"kalshi": {"value": value, "updated_at": stamped.isoformat()}}},
            "_ledger": {"gen": 1, "seq": 4}}

    meta = {"gen": 1, "seq": 3, "selection": (key, receipt)}
    keep, drop = blend_preview.carry_selection(meta, [frame(0.70), frame(0.71)])
    assert keep["_ledger"]["selection"][0] == key
    assert keep["_ledger"]["selection"][1]["recomposed_from"] == (1, 3)
    assert drop["_ledger"]["selection_dropped"] == (key, receipt)
    assert "selection" not in drop["_ledger"]
    # Untraced: frames unchanged.
    plain = frame(0.70)
    assert blend_preview.carry_selection({"gen": 1, "seq": 3}, [plain]) == [plain]
    assert "selection" not in plain["_ledger"]
    # The dropped frame's send closes the selection as unsent, never joined.
    trace.preview({"event_id": EVENT, "preview": {"kind": "revoke", "epoch": 1, "seq": 4,
                                                  "through_seq": 3, "reason": "x"}},
                  drop["_ledger"], ["published"])
    (unsent,) = stage(lines, "SELECTION_UNSENT")
    assert (unsent["sel"], unsent["attempt"], unsent["reason"]) == (
        key[0], 1, "RECOMPOSED_WITHOUT_SELECTED_ENTRY")
    assert all("sel" not in x for x in stage(lines, "PREVIEW"))


async def test_a_contributor_refusal_never_recomposed_is_named():
    trace, lines = traced(event=EVENT, outcome=K_OUTCOME)
    key = trace.selection(trace.selection_open(EVENT), "kalshi", "proposal", route="refresh",
                          value=0.70, basis={str(K_OUTCOME): 1.0}, then="PROPOSE")
    receipt = {"event": EVENT, "op": "propose", "reply": ["ok", "1", "3", "1"]}
    trace.readset(key, receipt, "COMPOSED")
    trace.preview({"event_id": EVENT, "preview": {"kind": "revoke", "epoch": 1, "seq": 3,
                                                  "through_seq": 2, "reason": "x"}},
                  {"selection": (key, receipt)}, ["contributor"])
    trace.selections_closed([key])
    (unsent,) = stage(lines, "SELECTION_UNSENT")
    assert unsent["reason"] == "CONTRIBUTOR_NOT_RECOMPOSED"


async def test_the_legacy_registry_recompose_carries_the_selection(monkeypatch):
    reg = blend_preview.LedgerRegistry(sources=frozenset({"kalshi", "polymarket"}))
    reg.claims["kalshi"] = 7
    stamped = datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc)
    receipt = {"_proposed": ("kalshi", 0.70, stamped.isoformat())}
    replies = iter([("contributor",), ("published", 500)])

    async def eval_(call, op, *argv):
        return list(next(replies))

    fresh = {"event_id": EVENT, "source": "kalshi", "p": 0.6, "preview": {
        "kind": "blend", "epoch": 1, "seq": 5, "ttl_ms": blend_preview.LEDGER_TTL_TOKEN.strip('"'),
        "pending_entries": {"kalshi": {"value": 0.70, "updated_at": stamped.isoformat()}}},
        "_ledger": {"gen": 1, "seq": 5, "contributors": [("kalshi", 7, 1)]}}

    async def mutate(op, call, stats):
        assert (op["ledger_op"], op["mode"]) == ("settle", "sync")
        return [fresh]

    monkeypatch.setattr(reg, "_eval", eval_)
    monkeypatch.setattr(reg, "_mutate", mutate)
    seen = []
    refused = dict(fresh, preview=dict(fresh["preview"], seq=4),
                   _ledger={"gen": 1, "seq": 4, "contributors": [("kalshi", 7, 1)],
                            "selection": ((3, 1), receipt)})
    await reg._publish(refused, None, event_channel, {},
                       observe=lambda frame, meta, reply: seen.append((meta, reply)))
    assert [reply[0] for _, reply in seen] == ["contributor", "published"]
    assert seen[1][0]["selection"][0] == (3, 1)
    assert seen[1][0]["selection"][1]["recomposed_from"] == (1, 4)


# ── M-a6 and outcome coverage ───────────────────────────────────────────────

async def test_eligibility_version_semantic_type_and_omitted_counts_are_emitted():
    from app.utils.probability_eligibility import MarketRef, verified_record

    trace, lines = traced(event=1)
    reading = speaker(0.6, rows=(101,))
    refs = tuple(MarketRef(market_id=i, source_market_id=f"M{i}") for i in range(10))
    reading.eligibility = verified_record(rule="r@1", market_id=10, source_market_id=TICKER,
                                          contributors=refs)
    trace.selection(trace.selection_open(1), "kalshi", "proposal", route="refresh",
                    reading=reading, value=0.6, basis={"101": 1.0, "999": 2.0}, then="PROPOSE")
    (line,) = stage(lines, "SELECTED")
    eligibility = line["eligibility"]
    assert eligibility["version"] == reading.eligibility.version
    assert "semantic_type" in eligibility and eligibility["semantic_type"] is None
    assert len(eligibility["contributors"]) == 8 and eligibility["contributors_omitted"] == 2
    # 999 is in the selection's basis but this trace has no identity for it.
    assert {"outcome": 999, "input_seq": "UNAVAILABLE",
            "linkage": "OUTCOME_NOT_TRACED"} in line["inputs"]
    from app.utils.kalshi_exact_trace import _readset_fields

    reply = ["ok", "1", "2", "3", "10", "", ""]
    for i in range(20):
        reply += [f"s{i}", "1", "2", "{}"]
    fields = _readset_fields({"op": "propose", "reply": reply})
    assert len(fields["read_contributors"]) == 16 and fields["read_contributors_omitted"] == 4

"""#10090: an exact selected input joins to the preview state a reader adopts.

PILLARS: TRUTH / FORMATTING. SHIP: fresh correct probabilities reach held
headlines sooner, with each long gap attributable to a stage.

Real Redis, the production `AuthorityLedgerRegistry`, two registries for the two
venue processes. Each carries its own real trace (`ExactKalshiTrace`,
`PMStageTrace`) fed one input through its public API, and a subscriber decodes
the v3 wire the reader receives. The controls:

* every wire frame's ``(epoch, seq)`` is described by exactly ONE trace's
  PREVIEW line (the process that sent it); the other trace sees a gap;
* each contributor's basis key names that trace's exact ``input_seq``;
* the committed nonvenue contribution (betting, espn) is in the line with its
  value, write clock and weight, and the line's ``recomputed_p`` equals the
  wire ``p``; a nonvenue-only base change is visible as a new ``base_rev``;
* an equal value at a different observation is never linked;
* removal is a revoke line carrying the wire's ``through_seq`` and reason;
* an observer failure costs nothing, and no observer leaves delivery as it was.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import time
from types import SimpleNamespace

import pytest

from app.tasks.live_blend_refresh import InputMark
from app.utils.dnpl_authority_registry import AuthorityLedgerRegistry
from app.utils.dnpl_authority_transport import decode_preview
from app.utils.kalshi_exact_trace import ExactKalshiTrace
from app.utils.live_push import event_channel
from app.utils.pm_stage_trace import PMStageTrace
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: F401
from tests.test_dnpl_redis_authority_10090 import initial, rig  # noqa: F401

pytestmark = pytest.mark.asyncio

EVENT = 42
TICKER = "KXNBAGAME-26OCT28BOSPHI-BOS"
K_OUTCOME, PM_OUTCOME = 101, 202


def kalshi_trace():
    lines = []
    trace = ExactKalshiTrace.from_env(
        {"WS_KALSHI_TRACE_TICKERS": TICKER,
         "WS_KALSHI_TRACE_EXPIRES_AT": str(time.time() + 300),
         "WS_KALSHI_TRACE_MAX_LINES": "256"},
        run="k", emit=lines.append,
    )
    return trace, lines


def kalshi_input(trace, seq, value, observed_at):
    """One ticker frame through RECEIVED, DECISION and PRICE_COMMITTED."""
    msg = {"market_ticker": TICKER, "yes_bid_dollars": str(value - 0.01),
           "yes_ask_dollars": str(value + 0.01)}
    trace.received("socket", msg)
    mark = InputMark(seq=seq, event_id=EVENT, outcome_id=K_OUTCOME, probability=value,
                     kind="price", recv_wall=time.time(), recv_mono=time.monotonic(),
                     venue_ts_ms=None, event_ordinal=seq)
    trace.decided(msg, reason="ADMITTED", market=11, outcome=K_OUTCOME, event=EVENT,
                  probability=value, mark=mark)
    trace.committed(mark, observed_at)


def pm_trace():
    lines = []
    trace = PMStageTrace.from_env(
        {"WS_PM_TRACE_EVENT": str(EVENT), "WS_PM_TRACE_OUTCOMES": str(PM_OUTCOME),
         "WS_PM_TRACE_EXPIRES_AT": str(time.time() + 300),
         "WS_PM_TRACE_MAX_LINES": "256"},
        run="p", event_of={PM_OUTCOME: EVENT}, emit=lines.append,
    )
    return trace, lines


def pm_input(trace, seq, value, observed_at):
    """One accepted mark through ACCEPTED, CHUNK and PRICE_COMMITTED."""
    mark = InputMark(seq=seq, event_id=EVENT, outcome_id=PM_OUTCOME, probability=value,
                     kind="price", recv_wall=time.time(), recv_mono=time.monotonic(),
                     venue_ts_ms=None, event_ordinal=seq)
    trace.input_accepted(mark)
    chunk = {PM_OUTCOME: value}
    trace.flush_begin(time.monotonic(), False, {PM_OUTCOME: mark}, chunk)
    token = trace.chunk_begin(0, [PM_OUTCOME])
    trace.chunk_write(token, chunk, {PM_OUTCOME: mark})
    trace.write_stage(chunk, "COMMITTED",
                      rows=[SimpleNamespace(id=PM_OUTCOME, last_updated=observed_at)])
    trace.chunk_end(token, True)


def stage(lines, name):
    return [line for line in lines if line.get("stage") == name]


def registry(a, now):
    return AuthorityLedgerRegistry(
        authority=replace(a, state="ready"), observed_after=now - timedelta(seconds=5),
        sources=frozenset({"kalshi", "polymarket"}),
    )


def base_bag(now, *, betting=0.55, kalshi=0.5, polymarket=0.5):
    clock = (now - timedelta(seconds=3)).isoformat()
    return {
        "kalshi": {"value": kalshi, "updated_at": clock},
        "polymarket": {"value": polymarket, "updated_at": clock},
        "betting": {"value": betting, "updated_at": clock},
        "espn": {"value": 0.6, "updated_at": clock},
        "statpal_injuries": [{"player": "not a probability source"}],
    }


async def propose(reg, call, source, value, outcome, observed_at, *, now, rev, bag):
    ticket, _ = await reg.read_ticket(call, source)
    event = SimpleNamespace(
        status="live", sport_key="basketball_nba", commence_time=now, completed_at=None,
        preview_context_at=now, preview_read_ticket=ticket,
        espn_win_prob_home=None, opening_home_probability=None,
    )
    return reg.propose(
        EVENT, source, value=value, event=event, row_sources=bag, row_rev=rev,
        observed_basis={str(outcome): observed_at.timestamp()}, stamped_at=now,
    )


async def wire(listener):
    message = await listener.get_message(ignore_subscribe_messages=True, timeout=1)
    assert message is not None, "nothing was published"
    return json.loads(decode_preview(event_channel(EVENT), message["data"], 0).payload)


async def silent(listener):
    assert await listener.get_message(ignore_subscribe_messages=True, timeout=0.2) is None


async def setup(rig):  # noqa: F811 - imported pytest fixture
    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    call = client.execute_command
    k, p = registry(a, now), registry(a, now)
    await k.claim(call, "kalshi")
    await p.claim(call, "polymarket")
    listener = client.pubsub()
    await listener.subscribe(event_channel(EVENT))
    await listener.get_message(timeout=1)
    return now, call, k, p, listener


def by_source(line):
    return {row["source"]: row for row in line["sources"]}


async def test_each_sent_frame_joins_its_exact_inputs_and_whole_contribution_state(
    rig,  # noqa: F811 - imported pytest fixture
):
    now, call, k, p, listener = await setup(rig)
    kt, klines = kalshi_trace()
    pt, plines = pm_trace()
    k_seen, pm_seen = now - timedelta(seconds=1), now - timedelta(seconds=0.5)
    kalshi_input(kt, 5, 0.70, k_seen)
    pm_input(pt, 9, 0.64, pm_seen)
    stats = {}
    try:
        # 1. Kalshi's process sends a frame: its trace joins input_seq 5.
        ops = await propose(k, call, "kalshi", 0.70, K_OUTCOME, k_seen, now=now, rev=10,
                            bag=base_bag(now))
        await k.execute(ops, call, event_channel, stats, observe=kt.preview)
        first = await wire(listener)
        (line,) = stage(klines, "PREVIEW")
        assert (line["event"], line["kind"], line["epoch"], line["seq"]) == (
            EVENT, "blend", first["preview"]["epoch"], first["preview"]["seq"])
        assert line["publication"] == "published"
        assert line["ttl_ms"] == first["preview"]["ttl_ms"] > 0
        assert line["base_rev"] == first["preview"]["base_rev"] == 10
        assert line["recomputed_matches"] is True
        assert line["recomputed_p"] == line["p"] == first["p"]
        rows = by_source(line)
        assert set(rows) == {"kalshi", "polymarket", "betting", "espn"}  # no injuries row
        assert rows["kalshi"]["role"] == "PENDING"
        assert rows["kalshi"]["inputs"] == [{
            "outcome": K_OUTCOME, "input_seq": 5, "receive_id": 1,
            "linkage": "EXACT_OUTCOME_OBSERVATION_BASIS"}]
        assert rows["kalshi"]["observed_basis"] == {str(K_OUTCOME): k_seen.timestamp()}
        betting = rows["betting"]
        assert betting["role"] == "BASE" and betting["value"] == 0.55
        assert betting["updated_epoch"] == (now - timedelta(seconds=3)).timestamp()
        assert isinstance(betting["weight"], float) and betting["weight"] > 0
        assert "observed_basis" not in betting  # a committed entry with no basis
        # The input chain this line names is in the same trace, before it.
        names = [(r["stage"], r.get("input_seq")) for r in klines]
        assert names.index(("PRICE_COMMITTED", 5)) < names.index(("PREVIEW", None))

        # 2. Polymarket's process sends the next frame. Only ITS trace has it;
        #    Kalshi's trace sees a seq gap, never a second copy.
        ops = await propose(p, call, "polymarket", 0.64, PM_OUTCOME, pm_seen, now=now,
                            rev=10, bag=base_bag(now))
        await p.execute(ops, call, event_channel, stats, observe=pt.preview)
        second = await wire(listener)
        assert len(stage(klines, "PREVIEW")) == 1
        (pline,) = stage(plines, "PREVIEW")
        assert (pline["epoch"], pline["seq"]) == (
            second["preview"]["epoch"], second["preview"]["seq"])
        assert pline["recomputed_p"] == second["p"] and pline["recomputed_matches"]
        prow = by_source(pline)
        assert prow["polymarket"]["inputs"] == [{
            "outcome": PM_OUTCOME, "input_seq": 9, "receive_id": "UNAVAILABLE",
            "linkage": "EXACT_OUTCOME_OBSERVATION_BASIS"}]
        # Kalshi's pending entry is in PM's frame too, keyed by its own outcome:
        # the Kalshi trace joins it offline on the same (outcome, stored_epoch).
        assert prow["kalshi"]["observed_basis"] == {str(K_OUTCOME): k_seen.timestamp()}
        assert prow["kalshi"]["inputs"] == []

        # 3. A nonvenue-only commit moved the base (betting 0.55 -> 0.40, rev 11).
        #    Kalshi's next input composes on it: the line names the new base.
        k_seen2 = now - timedelta(seconds=0.25)
        kalshi_input(kt, 6, 0.72, k_seen2)
        ops = await propose(k, call, "kalshi", 0.72, K_OUTCOME, k_seen2, now=now, rev=11,
                            bag=base_bag(now, betting=0.40))
        await k.execute(ops, call, event_channel, stats, observe=kt.preview)
        third = await wire(listener)
        line = stage(klines, "PREVIEW")[-1]
        assert (line["seq"], line["base_rev"]) == (third["preview"]["seq"], 11)
        rows = by_source(line)
        assert rows["betting"]["value"] == 0.40 and rows["betting"]["role"] == "BASE"
        assert rows["kalshi"]["inputs"][0]["input_seq"] == 6
        assert rows["polymarket"]["role"] == "PENDING"
        assert line["recomputed_p"] == third["p"] != second["p"]

        # 4. Removal: PM withdraws (its process sends Kalshi alone), then Kalshi
        #    is refused and its process sends the revoke.
        await p.execute(p.refused(EVENT, "polymarket", "test"), call, event_channel,
                        stats, observe=pt.preview)
        alone = await wire(listener)
        assert stage(plines, "PREVIEW")[-1]["seq"] == alone["preview"]["seq"]
        await k.execute(k.refused(EVENT, "kalshi", "test"), call, event_channel, stats,
                        observe=kt.preview)
        revoke = await wire(listener)
        line = stage(klines, "PREVIEW")[-1]
        assert revoke["preview"]["kind"] == line["kind"] == "revoke"
        assert (line["epoch"], line["seq"], line["through_seq"], line["reason"]) == (
            revoke["preview"]["epoch"], revoke["preview"]["seq"],
            revoke["preview"]["through_seq"], revoke["preview"]["reason"])
        assert line["publication"] == "published"

        # Every frame on the wire is described by exactly one trace.
        sent = [(f["preview"]["epoch"], f["preview"]["seq"])
                for f in (first, second, third, alone, revoke)]
        described = [(r["epoch"], r["seq"]) for r in
                     stage(klines, "PREVIEW") + stage(plines, "PREVIEW")]
        assert sorted(described) == sorted(sent) and len(set(sent)) == len(sent)
    finally:
        await listener.aclose()


async def test_an_equal_value_at_another_observation_is_never_linked(
    rig,  # noqa: F811 - imported pytest fixture
):
    now, call, k, _p, listener = await setup(rig)
    kt, klines = kalshi_trace()
    committed_at = now - timedelta(seconds=1)
    kalshi_input(kt, 5, 0.70, committed_at)
    other = committed_at - timedelta(seconds=0.5)  # same outcome, same value, older row
    try:
        ops = await propose(k, call, "kalshi", 0.70, K_OUTCOME, other, now=now, rev=10,
                            bag=base_bag(now))
        await k.execute(ops, call, event_channel, {}, observe=kt.preview)
        await wire(listener)
        (line,) = stage(klines, "PREVIEW")
        assert by_source(line)["kalshi"]["inputs"] == [{
            "outcome": K_OUTCOME, "input_seq": "UNAVAILABLE",
            "linkage": "TRACKED_OUTCOME_NO_RETAINED_COMMIT_AT_THIS_OBSERVATION"}]
    finally:
        await listener.aclose()


async def test_untraced_event_stopped_trace_and_failing_observer_cost_nothing(
    rig,  # noqa: F811 - imported pytest fixture
):
    now, call, k, _p, listener = await setup(rig)
    seen = now - timedelta(seconds=1)
    stats = {}
    try:
        # A trace whose inputs belong to no event here writes no PREVIEW line.
        idle, idle_lines = kalshi_trace()
        ops = await propose(k, call, "kalshi", 0.70, K_OUTCOME, seen, now=now, rev=10,
                            bag=base_bag(now))
        await k.execute(ops, call, event_channel, stats, observe=idle.preview)
        await wire(listener)
        assert stage(idle_lines, "PREVIEW") == []

        def broken(frame, meta, reply):
            raise RuntimeError("observer failure")

        ops = await propose(k, call, "kalshi", 0.71, K_OUTCOME,
                            now - timedelta(seconds=0.5), now=now, rev=10,
                            bag=base_bag(now))
        await k.execute(ops, call, event_channel, stats, observe=broken)
        frame = await wire(listener)
        assert frame["source_value"] == 0.71 and "_ledger" not in frame
        assert stats["published"] == 2

        # A stopped trace keeps nothing and writes nothing more.
        kt, klines = kalshi_trace()
        kalshi_input(kt, 5, 0.72, now - timedelta(seconds=0.25))
        kt.expiry = 0  # expired: the next entry point writes STOP
        ops = await propose(k, call, "kalshi", 0.72, K_OUTCOME,
                            now - timedelta(seconds=0.25), now=now, rev=10,
                            bag=base_bag(now))
        await k.execute(ops, call, event_channel, stats, observe=kt.preview)
        await wire(listener)
        assert stage(klines, "PREVIEW") == [] and klines[-1]["stage"] == "STOP"
        assert not kt.commits
        await silent(listener)
    finally:
        await listener.aclose()


async def test_the_refresher_hands_its_trace_to_the_ledger_send(redis_kwargs, monkeypatch):  # noqa: F811
    """The production caller: `_publish_previews` passes the trace hook, or nothing."""
    from redis.asyncio import Redis

    from app.tasks.live_blend_refresh import LiveBlendRefresher, TailReceipts
    from app.utils import blend_preview

    sources = frozenset({"kalshi", "polymarket"})
    monkeypatch.setenv(blend_preview.LEDGER_SOURCES_ENV, "kalshi,polymarket")
    blend_preview.reset_registry_for_tests()
    # The retained v1 ledger class: the same `execute` -> `_publish` path the
    # authority registry extends (its observer is exercised above).
    monkeypatch.setattr(blend_preview, "_REGISTRY", blend_preview.LedgerRegistry(sources=sources))
    client = Redis(**redis_kwargs)
    listener_client = Redis(**redis_kwargs)
    listener = listener_client.pubsub()
    now = datetime.now(timezone.utc)

    def ops(value, seen):
        event = SimpleNamespace(status="live", espn_win_prob_home=None,
                                opening_home_probability=None, preview_read_ticket=0,
                                sport_key=None, preview_context_at=now, commence_time=now,
                                completed_at=None)
        return blend_preview.registry().propose(
            EVENT, "kalshi", value=value, event=event, row_sources=base_bag(now),
            row_rev=10, observed_basis={str(K_OUTCOME): seen.timestamp()}, stamped_at=now)

    try:
        await client.set(blend_preview.FENCE_EPOCH_KEY, "41")
        await listener.subscribe(event_channel(EVENT))
        await listener.get_message(timeout=0.2)
        refresher = LiveBlendRefresher("kalshi")
        monkeypatch.setattr(refresher, "_client", lambda: client)
        await refresher.claim_preview_display()

        # No trace: delivered exactly as before, nothing observed.
        await refresher._publish_previews(ops(0.70, now - timedelta(seconds=1)))
        plain = json.loads((await listener.get_message(
            ignore_subscribe_messages=True, timeout=1))["data"])
        assert plain["preview"]["kind"] == "blend"

        kt, klines = kalshi_trace()
        seen = now - timedelta(seconds=0.5)
        kalshi_input(kt, 5, 0.71, seen)
        refresher.receipts = TailReceipts("kalshi")
        refresher.receipts.exact_trace = kt
        await refresher._publish_previews(ops(0.71, seen))
        traced = json.loads((await listener.get_message(
            ignore_subscribe_messages=True, timeout=1))["data"])
        (line,) = stage(klines, "PREVIEW")
        assert (line["epoch"], line["seq"]) == (
            traced["preview"]["epoch"], traced["preview"]["seq"])
        assert line["recomputed_p"] == traced["p"]
        assert by_source(line)["kalshi"]["inputs"][0]["input_seq"] == 5
        assert refresher.preview_stats["published"] == 2
    finally:
        blend_preview.reset_registry_for_tests()
        for c in (listener, listener_client, client):
            await (c.aclose() if hasattr(c, "aclose") else c.close())


async def test_a_repeat_named_by_a_preview_materializes_its_own_chain(
    rig,  # noqa: F811 - imported pytest fixture
):
    """An identical repeat spends no lines until something names its input_seq."""
    now, call, k, _p, listener = await setup(rig)
    kt, klines = kalshi_trace()
    kalshi_input(kt, 5, 0.70, now - timedelta(seconds=1))
    repeat_seen = now - timedelta(seconds=0.5)
    kalshi_input(kt, 7, 0.70, repeat_seen)  # same frame and decision, later row clock
    assert [r.get("input_seq") for r in stage(klines, "PRICE_COMMITTED")] == [5]
    try:
        ops = await propose(k, call, "kalshi", 0.70, K_OUTCOME, repeat_seen, now=now,
                            rev=10, bag=base_bag(now))
        await k.execute(ops, call, event_channel, {}, observe=kt.preview)
        await wire(listener)
        (line,) = stage(klines, "PREVIEW")
        assert by_source(line)["kalshi"]["inputs"][0]["input_seq"] == 7
        chain = [(r["stage"], r.get("input_seq")) for r in klines]
        assert chain.index(("PRICE_COMMITTED", 7)) < chain.index(("PREVIEW", None))
        assert ("DECISION", 7) in chain
    finally:
        await listener.aclose()

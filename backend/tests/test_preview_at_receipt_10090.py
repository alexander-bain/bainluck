"""#10090 `preview_at_receipt` — a Polymarket price change is previewed from the
socket's memory the moment it arrives, before any database write.

SHIP: a Polymarket price change reaches an open game page in well under a
second. The page stops waiting for the price write (and the stamp behind it)
before it shows the new price; the write and the stamp still happen.

The seam is `HeldRowQuotes.note_input`, which both venue sockets call for every
accepted input under their buffer lock; every test here drives that real seam.
The ledger operations are read off a `LedgerRegistry` with no Redis, as the
`preview_from_commit` rig does. The CONTROL test at the top is RED on the base
(`349df8b0`) and GREEN with the change: a price previewed before its write
commits, a failed write revokes it, a withdrawal is never previewed, and
out-of-order inputs never go backwards.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as Row

import pytest

from app.tasks import live_blend_refresh as module
from app.tasks.live_blend_refresh import HeldRowQuotes, LiveBlendRefresher
from app.utils import blend_preview
from app.utils.aggregation import observation_basis
from app.utils.live_blend import MarketOutcomes
from app.utils.preview_receipt import PreviewReceipt

SOURCES = frozenset({"kalshi", "polymarket"})
EV, EV2 = 7, 8
HOME, AWAY = "Reynolds / Watt", "Behar / Paris"
CONDITION = "0x" + "20" * 32
MARKET, HOME_LEG, AWAY_LEG = 66756997, 250776126, 250776127
SWITCH_ENV = "SPEED_SWITCH_TODAY_PREVIEW_AT_RECEIPT"
VENUES_ENV = "PREVIEW_AT_RECEIPT_VENUES"
#: Rebound per test by `anchors` (gotcha #44: offsets from one clock read).
NOW = datetime.now(timezone.utc)
READ_AT = NOW - timedelta(seconds=1)
SEEN = NOW - timedelta(seconds=2)

_SEQ = itertools.count(1)


def bag(*, pm=0.46, kalshi=0.5, pm_basis=None):
    pm_entry = {"value": pm, "updated_at": (NOW - timedelta(seconds=3)).isoformat()}
    if pm_basis is not None:
        pm_entry.update(observed_value=pm, observed_basis=pm_basis)
    return {"kalshi": {"value": kalshi, "updated_at": (NOW - timedelta(seconds=5)).isoformat()},
            "polymarket": pm_entry}


def event(*, eid=EV, rev=10, ticket=0, status="live", sources=None, at=None):
    sources = bag() if sources is None else sources
    return Row(id=eid, sport_key="tennis_atp_lyon", home_team_name=HOME, away_team_name=AWAY,
               status=status, completed_at=None, commence_time=NOW - timedelta(hours=3),
               win_probability_sources={"polymarket": sources.get("polymarket")},
               espn_win_prob_home=None, opening_home_probability=None,
               preview_sources=sources, preview_rev=rev,
               preview_context_at=READ_AT if at is None else at, preview_read_ticket=ticket)


def legs(*, eid=EV, home="0.460000", away="0.540000", seen=None, ranks=(2, 1), base=0):
    seen = SEEN if seen is None else seen
    market = Row(id=MARKET + base, source="polymarket", external_id=CONDITION, event_id=eid,
                 name="Lyon Open (Doubles): Reynolds/Watt vs Behar/Paris",
                 status="open", market_metadata={})
    rows = [
        Row(id=HOME_LEG + base, market_id=MARKET + base, name="Reynolds/Watt", rank=ranks[0],
            current_probability=Decimal(home), last_updated=seen, is_winner=None,
            external_id=CONDITION, resolution_source=None),
        Row(id=AWAY_LEG + base, market_id=MARKET + base, name="Behar/Paris", rank=ranks[1],
            current_probability=Decimal(away), last_updated=seen, is_winner=None,
            external_id=CONDITION + "_side1", resolution_source=None),
    ]
    return [MarketOutcomes(market, rows, NOW - timedelta(hours=3), False)]


def read(r, ev, group, *, started=None):
    """What `_read_groups` hands the cache after a stamp's SELECT."""
    rows = {id(row) for entry in group for row in entry.outcomes}
    r._remember_preview_graphs({ev.id: (ev, group)}, rows,
                               module._mono() if started is None else started)


def mark(oid, price, *, eid=EV, seq=None):
    return Row(seq=next(_SEQ) if seq is None else seq, event_id=eid, outcome_id=oid,
               probability=price, kind="price", recv_wall=time.time(),
               recv_mono=module._mono(), venue_ts_ms=None, event_ordinal=0)


def receive(r, home, *, eid=EV, base=0, bound=None, seqs=(None, None)):
    """The socket accepting one book: the token's leg and its complement, under
    a frozen DB-clock bound taken after the read graph's rows were stored."""
    r.held_quotes._database_bound = (
        (NOW - timedelta(seconds=1)).timestamp() if bound is None else bound)
    marks = (mark(HOME_LEG + base, home, eid=eid, seq=seqs[0]),
             mark(AWAY_LEG + base, round(1 - home, 6), eid=eid, seq=seqs[1]))
    for m in marks:
        r.held_quotes.note_input(m)
    return marks


async def drained(r):
    task = getattr(r, "_receipt_task", None)
    if task is not None:
        await asyncio.wait_for(task, 5)


def ops(sent, kind):
    return [op for frames in sent for op in frames if op.get("ledger_op") == kind]


def pending(event_id=EV):
    return blend_preview.registry().pending_entry(event_id, "polymarket")


@pytest.fixture(autouse=True)
def anchors(monkeypatch):
    now = datetime.now(timezone.utc)
    module_globals = globals()
    monkeypatch.setitem(module_globals, "NOW", now)
    monkeypatch.setitem(module_globals, "READ_AT", now - timedelta(seconds=1))
    monkeypatch.setitem(module_globals, "SEEN", now - timedelta(seconds=2))
    return now


def _refresher(monkeypatch, source="polymarket"):
    refresher = LiveBlendRefresher(source)
    refresher.held_quotes = HeldRowQuotes()
    refresher.sent = []

    async def record(frames, *, prepare_frames=None, refused=None):
        frames = list(frames)
        if prepare_frames is not None:
            frames.extend(await prepare_frames())
        refresher.sent.append(frames)

    monkeypatch.setattr(refresher, "_publish_previews", record)
    return refresher


@pytest.fixture
def r(monkeypatch, anchors):
    blend_preview.reset_registry_for_tests()
    monkeypatch.setattr(blend_preview, "_REGISTRY", blend_preview.LedgerRegistry(sources=SOURCES))
    monkeypatch.setattr(blend_preview, "preview_events_for",
                        lambda source: frozenset({EV, EV2}))
    monkeypatch.setenv(SWITCH_ENV, "1")
    monkeypatch.delenv(VENUES_ENV, raising=False)
    yield _refresher(monkeypatch)
    blend_preview.reset_registry_for_tests()


# ── the control ──────────────────────────────────────────────────────────────

async def test_control_preview_before_write_failed_write_withdrawal_and_never_backwards(r):
    """RED on the base, GREEN with the change (the four clauses of the brief)."""
    # (1) A received price is previewed before its write commits: no write,
    # no `note_committed_rows`, no stamp — one proposal at the received price.
    read(r, event(), legs())
    newer = receive(r, 0.48)
    await drained(r)
    [opened] = ops(r.sent, "propose")
    assert (opened["value"], opened["mode"]) == (0.48, "open")
    assert pending().at_receipt

    # (4) Out-of-order inputs never go backwards: an older input arriving late
    # changes nothing, and a stamp that read before the price arrived cannot
    # put its older reading back on screen.
    r.sent.clear()
    receive(r, 0.40, seqs=(newer[0].seq - 1, newer[1].seq - 1))
    await drained(r)
    assert ops(r.sent, "propose") == []
    stale = blend_preview.registry().propose(
        EV, "polymarket", value=0.46, event=event(), row_sources=bag(), row_rev=10,
        observed_basis={str(HOME_LEG): SEEN.timestamp()},
    )
    assert stale == [] and pending().value == 0.48

    # (2) A failed write revokes it: the final drain's stranded price.
    await r.revoke_receipt_previews([HOME_LEG, AWAY_LEG])
    [settle] = ops(r.sent, "settle")
    assert (settle["reason"], settle["through"]) == ("write_failed", opened["local_seq"])
    assert pending() is None

    # (3) A withdrawal is never previewed, and revokes the one shown.
    r.sent.clear()
    receive(r, 0.49)
    await drained(r)
    [shown] = ops(r.sent, "propose")
    r.note_receipt_withdrawn([HOME_LEG, AWAY_LEG])
    await drained(r)
    [withdrawn] = ops(r.sent, "settle")
    assert (withdrawn["reason"], withdrawn["through"]) == ("withdrawn", shown["local_seq"])
    assert r._receipt_quotes == {}


# ── composition ──────────────────────────────────────────────────────────────

async def test_the_proposal_carries_the_read_graphs_ticket_revision_and_base(r):
    read(r, event(rev=12, ticket=3, sources=bag(pm=0.47)), legs())
    receive(r, 0.48)
    await drained(r)
    [op] = ops(r.sent, "propose")
    assert (op["read_ticket"], op["ctx_rev"], op["base_rev"]) == (3, 12, 12)
    assert json.loads(op["base"])["sources"]["polymarket"]["value"] == 0.47
    payload = json.loads(op["payload"])
    # Observed at the frozen bound (the DB clock), never the worker's wall.
    assert payload["observed_basis"] == {
        str(HOME_LEG): pytest.approx((NOW - timedelta(seconds=1)).timestamp())}


async def test_a_price_that_flips_the_favourite_is_reranked_as_its_write_will_store(r):
    read(r, event(), legs())
    receive(r, 0.56)
    # The composed rows rank as `rerank_market_fields_stmt` will store them
    # (the resolver orders a market's legs by rank), not as the graph read them.
    plan = r._receipt_preview_plan(EV, module._mono(), blend_preview.registry())
    [home] = plan[4]
    assert (home.id, home.rank, float(home.current_probability)) == (HOME_LEG, 1, 0.56)
    await drained(r)
    assert [op["value"] for op in ops(r.sent, "propose")] == [0.56]


async def test_the_switch_off_keeps_nothing_and_composes_nothing(r, monkeypatch):
    monkeypatch.delenv(SWITCH_ENV)
    read(r, event(), legs())
    receive(r, 0.48)
    await drained(r)
    assert r._preview_graphs == {} and r._receipt_quotes == {} and r.sent == []


async def test_polymarket_is_the_default_venue_and_kalshi_rides_the_same_seam(monkeypatch, r):
    kalshi = _refresher(monkeypatch, "kalshi")
    read(kalshi, event(), legs())
    receive(kalshi, 0.48)
    await drained(kalshi)
    assert kalshi.sent == [] and kalshi._receipt_quotes == {}
    monkeypatch.setenv(VENUES_ENV, "all")
    read(kalshi, event(), legs())
    receive(kalshi, 0.48)
    await drained(kalshi)
    assert [op["value"] for op in ops(kalshi.sent, "propose")] == [0.48]
    monkeypatch.setenv(VENUES_ENV, "kalshi")
    receive(r, 0.49)
    await drained(r)
    assert r.sent == []


def _skip_cases():
    return {
        "no_graph": dict(no_read=True),
        # (getattr: the base has no such constant, and the control must
        # FAIL there, not fail to collect.)
        "graph_too_old": dict(age=getattr(module, "RECEIPT_GRAPH_MAX_AGE_S", 15.0) + 0.01),
        # The stored row is at/after the quote's bound at another price: it may
        # be newer than the quote, so the whole event waits for its stamp.
        "ambiguous_stored_row": dict(bound_before_seen=True),
        "no_bound": dict(bound=None),
        "returned_to_the_stored_value": dict(last_written=0.48),
        "handover_changing": dict(route=lambda: None),
        "not_live": dict(ev=dict(status="scheduled")),
        # The received book does not move the whole-percent blend shown.
        "blend_unchanged": dict(price=0.461),
    }


@pytest.mark.parametrize("case", sorted(_skip_cases()))
async def test_nothing_is_composed_when_the_receipt_cannot_say_it(r, monkeypatch, case):
    spec = _skip_cases()[case]
    clock = [100.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    if "route" in spec:
        r.receipt_route = spec["route"]
    if "last_written" in spec:
        r._last_written_value[EV] = spec["last_written"]
    if not spec.get("no_read"):
        read(r, event(**spec.get("ev", {})), legs())
    clock[0] += spec.get("age", 0.0)
    bound = (SEEN - timedelta(seconds=1)).timestamp() if spec.get("bound_before_seen") else None
    price = spec.get("price", 0.48)
    if "bound" in spec:
        r.held_quotes._database_bound = None
        r.held_quotes.note_input(mark(HOME_LEG, price))
    else:
        receive(r, price, bound=bound)
    await drained(r)
    assert ops(r.sent, "propose") == []
    assert r.receipt_preview_stats["errors"] == 0, "a refusal is a decision, never an exception"


async def test_the_same_receipt_composes_when_no_case_applies(r, monkeypatch):
    """The skip cases' positive control: the same rig, nothing withheld."""
    clock = [100.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    read(r, event(), legs())
    clock[0] += module.RECEIPT_GRAPH_MAX_AGE_S - 0.01
    receive(r, 0.48)
    await drained(r)
    assert [op["value"] for op in ops(r.sent, "propose")] == [0.48]


async def test_a_current_book_proof_reads_the_receipt_instead_of_withholding_it(r, monkeypatch):
    """#10090 (was the `current_book_proof` skip case): a market that needs the
    current-book proof is read UNDER it at receipt and rechecked at send, as
    the observation preview does. The proof binds only the bundled Kalshi
    Challenger pair, so this Polymarket book composes even with a book that
    proves nothing, and the proof's callbacks never raise into the worker."""
    refused = []
    monkeypatch.setattr(r, "_current_reading_proof", lambda *a, **kw: {
        "require_current_book_midpoint": True,
        "current_book_midpoint": lambda ticker: None,
        "current_book_primary_price": None,
        "current_primary_input": lambda row: None,
        "current_book_refused": lambda: refused.append(True),
    })
    read(r, event(), legs())
    receive(r, 0.48)
    await drained(r)
    assert [op["value"] for op in ops(r.sent, "propose")] == [0.48]
    assert refused == [] and r.receipt_preview_stats["errors"] == 0


async def test_a_stored_row_that_already_holds_the_quote_is_read_as_stored(r):
    read(r, event(), legs(home="0.480000", away="0.520000", seen=NOW))
    receive(r, 0.48)
    await drained(r)
    assert ops(r.sent, "propose") == []  # nothing newer than the graph
    assert r.receipt_preview_stats["ambiguous"] == 0


async def test_a_graph_read_under_a_held_quote_overlay_is_kept_as_read(r):
    """`_read_groups` overlays held quotes onto the stamp's rows in place; the
    graph keeps the rows as READ (the receipt overlay carries those quotes)."""
    group = legs()
    original_rows = {id(row): row for entry in group for row in entry.outcomes}
    home = group[0].outcomes[0]
    group[0].outcomes[0] = Row(**{**vars(home), "current_probability": Decimal("0.700000")})
    r._remember_preview_graphs({EV: (event(), group)}, original_rows, module._mono())
    kept = r._preview_graphs[EV][2]
    assert kept[0].outcomes[0] is home and group[0].outcomes[0] is not home
    receive(r, 0.48)
    await drained(r)
    assert [op["value"] for op in ops(r.sent, "propose")] == [0.48]


async def test_a_routing_change_retires_quotes_taken_under_the_old_maps(r):
    generation = [1]
    r.receipt_route = lambda: generation[0]
    read(r, event(), legs())
    r.held_quotes._database_bound = (NOW - timedelta(seconds=1)).timestamp()
    r.held_quotes.note_input(mark(HOME_LEG, 0.48))
    generation[0] = 2
    await drained(r)
    assert ops(r.sent, "propose") == []


# ── cheap by construction ───────────────────────────────────────────────────

async def test_a_burst_coalesces_to_one_composition_per_interval(r, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    sleeps = []

    async def fake_wait_for(awaitable, timeout):
        awaitable.close()
        sleeps.append(timeout)
        clock[0] += timeout
        raise asyncio.TimeoutError

    monkeypatch.setattr(module.asyncio, "wait_for", fake_wait_for)
    read(r, event(), legs())
    receive(r, 0.48)
    await asyncio.sleep(0)  # the first tick of a quiet event: composed at once
    for price in (0.50, 0.52, 0.54):
        receive(r, price)
    task = r._receipt_task
    for _ in range(50):
        if task.done():
            break
        await asyncio.sleep(0)
    assert task.done()
    assert [op["value"] for op in ops(r.sent, "propose")] == [0.48, 0.54]
    assert sleeps == [pytest.approx(module.RECEIPT_PREVIEW_INTERVAL_S)]


def _with_a_prop_market():
    group = legs()
    prop = Row(id=MARKET + 1, source="polymarket", external_id="0x" + "21" * 32, event_id=EV,
               name="Lyon Open (Doubles): Total games over 20.5", status="open",
               market_metadata={})
    rows = [Row(id=PROP_OVER, market_id=MARKET + 1, name="Over", rank=1,
                current_probability=Decimal("0.550000"), last_updated=SEEN, is_winner=None,
                external_id="over", resolution_source=None),
            Row(id=PROP_OVER + 1, market_id=MARKET + 1, name="Under", rank=2,
                current_probability=Decimal("0.450000"), last_updated=SEEN, is_winner=None,
                external_id="under", resolution_source=None)]
    return group + [MarketOutcomes(prop, rows, NOW - timedelta(hours=3), False)]


PROP_OVER = 250776200


async def test_a_tick_on_a_market_that_does_not_speak_composes_nothing(r):
    read(r, event(), _with_a_prop_market())
    receive(r, 0.48)
    await drained(r)
    assert r._receipt_speaking[EV] == frozenset({HOME_LEG, AWAY_LEG})
    r.held_quotes.note_input(mark(PROP_OVER, 0.60))
    assert r._receipt_due == {} and PROP_OVER in r._receipt_quotes
    # A new read graph forgets which market spoke: the next tick re-learns it.
    read(r, event(), _with_a_prop_market())
    assert EV not in r._receipt_speaking
    r.held_quotes.note_input(mark(PROP_OVER, 0.61))
    assert EV in r._receipt_due


async def test_speed_may_set_the_interval_within_bounds(monkeypatch):
    monkeypatch.setenv(module.RECEIPT_PREVIEW_INTERVAL_ENV, "0.5")
    assert module._receipt_interval() == 0.5
    for bad in ("0", "3", "x"):
        monkeypatch.setenv(module.RECEIPT_PREVIEW_INTERVAL_ENV, bad)
        assert module._receipt_interval() == module.RECEIPT_PREVIEW_INTERVAL_S


async def test_reader_held_games_are_composed_first(r):
    r.reader_held = lambda: frozenset({EV2})
    read(r, event(), legs())
    read(r, event(eid=EV2), legs(eid=EV2, base=10))
    receive(r, 0.48)
    receive(r, 0.48, eid=EV2, base=10)
    await drained(r)
    assert [op["event_id"] for op in ops(r.sent, "propose")] == [EV2, EV]


# ── the ledger: ordering, supersession, recovery ─────────────────────────────

def _committed_bag(basis_at):
    return bag(pm=0.47, pm_basis={str(HOME_LEG): basis_at.timestamp()})


async def test_a_commit_of_an_older_observation_keeps_the_receipt_on_screen(r):
    read(r, event(), legs())
    receive(r, 0.48)
    await drained(r)
    [opened] = ops(r.sent, "propose")
    # The stamp's commit of a reading taken before the receipt.
    [settle] = blend_preview.registry().committed(
        EV, "polymarket", seq=opened["local_seq"], sources=_committed_bag(SEEN), rev=11)
    assert settle["through"] == opened["local_seq"] - 1 and settle["mode"] == "settle"
    assert pending().value == 0.48 and pending().at_receipt


async def test_a_commit_that_carries_the_receipt_retires_it(r):
    read(r, event(), legs())
    receive(r, 0.48)
    await drained(r)
    [opened] = ops(r.sent, "propose")
    [settle] = blend_preview.registry().committed(
        EV, "polymarket", seq=opened["local_seq"], sources=_committed_bag(NOW), rev=11)
    assert settle["through"] == opened["local_seq"] and pending() is None


@pytest.mark.parametrize("reason,kept", [
    ("unchanged", True), ("stale", True), ("unobserved", True), ("lock", True),
    ("no_group", False), ("error", False), ("no_row", False),
])
async def test_only_a_stamp_refusal_about_the_event_withdraws_a_receipt(r, reason, kept):
    read(r, event(), legs())
    receive(r, 0.48)
    await drained(r)
    frames = blend_preview.registry().refused(EV, "polymarket", reason)
    assert (pending() is not None) is kept
    assert bool(frames) is not kept


async def test_a_stamp_reading_as_new_as_the_receipt_replaces_it(r):
    read(r, event(), legs())
    receive(r, 0.48)
    await drained(r)
    at = (NOW - timedelta(seconds=1)).timestamp()
    [op] = blend_preview.registry().propose(
        EV, "polymarket", value=0.48, event=event(), row_sources=bag(), row_rev=10,
        observed_basis={str(HOME_LEG): at + 0.5},
    )
    assert op["mode"] == "continue" and not pending().at_receipt


async def test_a_settlement_forgets_the_receipt_and_revokes_it(r):
    read(r, event(), legs())
    receive(r, 0.48)
    await drained(r)
    [opened] = ops(r.sent, "propose")
    r.forget_preview_outcomes([HOME_LEG])
    await drained(r)
    [settle] = ops(r.sent, "settle")
    assert (settle["reason"], settle["through"]) == ("withdrawn", opened["local_seq"])


async def test_a_stamps_own_pending_preview_is_never_revoked_by_this_path(r):
    read(r, event(), legs())
    blend_preview.registry().propose(
        EV, "polymarket", value=0.47, event=event(), row_sources=bag(), row_rev=10,
        observed_basis={str(HOME_LEG): SEEN.timestamp()},
    )
    r.note_receipt_withdrawn([HOME_LEG, AWAY_LEG])
    await drained(r)
    await r.revoke_receipt_previews([HOME_LEG, AWAY_LEG])
    assert ops(r.sent, "settle") == [] and pending().value == 0.47


def test_the_base_registry_keeps_the_same_ordering():
    """The single-source registry (no ledger) obeys the same three rules."""
    reg = blend_preview.PreviewRegistry(max_uncommitted_s=60)
    reg.epoch = 1
    ev = event()
    received = {str(HOME_LEG): (NOW - timedelta(seconds=1)).timestamp()}
    [frame] = reg.propose(EV, "polymarket", value=0.48, event=ev, row_sources=bag(),
                          row_rev=10, observed_basis=received, at_receipt=True)
    assert reg.propose(EV, "polymarket", value=0.46, event=ev, row_sources=bag(), row_rev=10,
                       observed_basis={str(HOME_LEG): SEEN.timestamp()}) == []
    [recomposed] = reg.committed(EV, "polymarket", seq=frame["preview"]["seq"],
                                 sources=_committed_bag(SEEN), rev=11)
    assert recomposed["preview"]["base_rev"] == 11 and recomposed["source_value"] == 0.48
    assert reg.refused(EV, "polymarket", "unchanged") == []
    assert reg.committed(EV, "polymarket", seq=recomposed["preview"]["seq"],
                         sources=_committed_bag(NOW), rev=12) == []
    assert reg.pending_entry(EV, "polymarket") is None


# ── the receipt that judges it ───────────────────────────────────────────────

def test_the_preview_receipt_charges_the_publish_that_carried_the_input():
    clock = [1000.0]
    receipt = PreviewReceipt("polymarket", dict, mono=lambda: clock[0], wall=lambda: 60.0)
    stamped = datetime.now(timezone.utc).isoformat()
    m = Row(recv_mono=999.7, seq=5)
    receipt.carried(EV, stamped, m)
    frame = {"event_id": EV, "p": 0.49, "status": "live",
             "preview": {"kind": "blend", "pending_entries": {
                 "polymarket": {"value": 0.48, "updated_at": stamped}}}}
    receipt.published(frame, None, ("published",))
    clock[0] = 1004.0  # the write and the stamp land much later
    receipt.committed({EV: m})
    assert receipt._measured == 1
    assert receipt._samples == [(pytest.approx(0.3), EV)]
    stamp_frame = {**frame, "preview": {**frame["preview"], "pending_entries": {}}}
    receipt.published(stamp_frame, None, ("published",))
    assert receipt._measured == 1  # the stamp's later blend charges nothing


def test_a_newer_committed_input_than_the_receipt_carried_waits_as_before():
    clock = [1000.0]
    receipt = PreviewReceipt("polymarket", dict, mono=lambda: clock[0], wall=lambda: 60.0)
    stamped = datetime.now(timezone.utc).isoformat()
    receipt.carried(EV, stamped, Row(recv_mono=999.7, seq=5))
    receipt.published({"event_id": EV, "p": 0.49, "status": "live", "preview": {
        "kind": "blend", "pending_entries": {"polymarket": {"updated_at": stamped}}}},
        None, ("published",))
    receipt.committed({EV: Row(recv_mono=1001.0, seq=6)})
    assert receipt._measured == 0 and EV in receipt._awaiting


# ── wiring ───────────────────────────────────────────────────────────────────

def test_the_polymarket_socket_wires_the_withdrawal_route_and_stranded_revoke():
    import inspect

    from app.tasks import polymarket_ws

    source = inspect.getsource(polymarket_ws._run_polymarket_ws_consumer)
    wide = source.index("if _poly_book_is_untradeable(bid_f, ask_f):")
    assert source.index("note_receipt_withdrawn", wide) < source.index("prob = (bid_f + ask_f) / 2", wide)
    assert "blend_refresher.receipt_route = lambda" in source
    assert "revoke_receipt_previews" in source


def test_the_switch_is_registered_off_with_both_trial_modes():
    from app.tasks.speed_switches import SPECS

    assert SPECS["preview_at_receipt"] == {
        "modes": ("ab", "alternate"), "values": (0, 1), "today": 0}


def test_observation_basis_of_an_overlaid_row_is_its_bound():
    at = NOW - timedelta(seconds=1)
    assert observation_basis([Row(id=1, last_updated=at)]) == {"1": pytest.approx(at.timestamp())}

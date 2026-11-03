"""#11909: a proof that can never arrive must not hold a live number.

Specimen: Bax v Cadenasso (event 15340299, Nov 3). Kalshi prices the match as
one bundled Challenger market (`KXATPCHALLENGERMATCH-…`) with legs "Florent
Bax" / "Lorenzo Cadenasso", and its receipt previews need current-book proof.
The home name "Bax" is too short for the side test, so no leg names the home
side and no receipt can ever prove the reading's orientation: each input sat
15-40 s as `na_proof` until the next stamp. Alex 11/03: "bound the na_proof
wait so that when no orientation proof is possible for a match, the update
falls through to the served number with its honest age instead of waiting
for the next stamp".

So such an input resolves at once (`served_unprovable`, counted as
``unprovable=`` in the headline-clock line, never ranked as a delivery):
nothing is previewed, no confirmation clock moves, and the stamp stays urgent
so a moved price is still stamped past the 20 s receipt floor. Controls: with
"Florent Bax" as the home name the same receipt previews the proven two-leg
number as before, and a nameable home whose book proof fails still waits as
`na_proof`.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as Row

import pytest

from app.tasks import live_blend_refresh as module
from app.tasks.live_blend_refresh import HeldRowQuotes, LiveBlendRefresher
from app.utils import blend_preview
from app.utils import live_blend
from app.utils.live_blend import MarketOutcomes

SOURCES = frozenset({"kalshi", "polymarket"})
EV = 15340299
TICKER = "KXATPCHALLENGERMATCH-26NOV03BAXCAD"
MARKET, BAX_LEG, CAD_LEG = 901, 9011, 9012
SWITCH_ENV = "SPEED_SWITCH_TODAY_PREVIEW_AT_RECEIPT"
VENUES_ENV = "PREVIEW_AT_RECEIPT_VENUES"
SERVED = 0.45
NOW = datetime.now(timezone.utc)
SEEN = NOW - timedelta(seconds=2)

_SEQ = itertools.count(1)


@pytest.fixture(autouse=True)
def anchors(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setitem(globals(), "NOW", now)
    monkeypatch.setitem(globals(), "SEEN", now - timedelta(seconds=2))
    return now


def event(home="Bax", *, rev=10):
    sources = {"kalshi": {"value": SERVED,
                          "updated_at": (NOW - timedelta(seconds=30)).isoformat()}}
    return Row(id=EV, sport_key="tennis_atp_challenger", home_team_name=home,
               away_team_name="Cadenasso", status="live", completed_at=None,
               commence_time=NOW - timedelta(hours=1),
               win_probability_sources={"kalshi": sources["kalshi"]},
               espn_win_prob_home=None, opening_home_probability=None,
               preview_sources=sources, preview_rev=rev,
               preview_context_at=NOW - timedelta(seconds=1), preview_read_ticket=0)


def legs(*, bax="0.550000", cad="0.450000"):
    market = Row(id=MARKET, source="kalshi", external_id=TICKER, event_id=EV,
                 name="Bax vs Cadenasso", status="open", market_metadata={})
    rows = [
        Row(id=BAX_LEG, market_id=MARKET, name="Florent Bax", rank=1,
            current_probability=Decimal(bax), last_updated=SEEN, is_winner=None,
            external_id=TICKER + "-BAX", resolution_source=None),
        Row(id=CAD_LEG, market_id=MARKET, name="Lorenzo Cadenasso", rank=2,
            current_probability=Decimal(cad), last_updated=SEEN, is_winner=None,
            external_id=TICKER + "-CAD", resolution_source=None),
    ]
    return [MarketOutcomes(market, rows, NOW - timedelta(hours=1), False)]


def mark(oid, price):
    return Row(seq=next(_SEQ), event_id=EV, outcome_id=oid, probability=price, kind="price",
               recv_wall=time.time(), recv_mono=module._mono(), venue_ts_ms=None,
               event_ordinal=0)


def receive(r, bax, cad):
    """The socket accepting both legs under a DB-clock bound after the graph."""
    r.held_quotes._database_bound = (NOW - timedelta(seconds=1)).timestamp()
    r.book = {"BAX": bax, "CAD": cad}
    for oid, price in ((BAX_LEG, bax), (CAD_LEG, cad)):
        r.held_quotes.note_input(mark(oid, price))


async def drained(r):
    task = getattr(r, "_receipt_task", None)
    if task is not None:
        await asyncio.wait_for(task, 5)


def ops(sent, kind):
    return [op for frames in sent for op in frames if op.get("ledger_op") == kind]


def pending():
    return blend_preview.registry().pending_entry(EV, "kalshi")


@pytest.fixture
def r(monkeypatch, anchors):
    blend_preview.reset_registry_for_tests()
    monkeypatch.setattr(blend_preview, "_REGISTRY", blend_preview.LedgerRegistry(sources=SOURCES))
    monkeypatch.setattr(blend_preview, "preview_events_for", lambda source: frozenset({EV}))
    monkeypatch.setenv(SWITCH_ENV, "1")
    monkeypatch.delenv(VENUES_ENV, raising=False)
    refresher = LiveBlendRefresher("kalshi")
    refresher.held_quotes = HeldRowQuotes()
    refresher.sent = []
    refresher.book = {}
    # The WS owner's current-book proof (`kalshi_ws` switches it on for Challenger).
    refresher.require_current_book_proof = True
    refresher.current_book_midpoint = lambda ticker: (
        None if refresher.book.get(ticker.rsplit("-", 1)[-1]) is None
        else Decimal(str(refresher.book[ticker.rsplit("-", 1)[-1]])))
    refresher.current_book_primary_price = None
    refresher.current_primary_input = None
    refresher.confirmed_calls = []
    refresher.receipts = Row(confirmed=Row(
        previewed=lambda ids: refresher.confirmed_calls.append(("previewed", list(ids)))))
    refresher.preview_receipt = Row(
        carried=lambda *a: refresher.confirmed_calls.append(("carried", a)))

    async def record(frames, *, prepare_frames=None, refused=None):
        frames = list(frames)
        if prepare_frames is not None:
            frames.extend(await prepare_frames())
        refresher.sent.append(frames)

    monkeypatch.setattr(refresher, "_publish_previews", record)
    yield refresher
    blend_preview.reset_registry_for_tests()


def read(r, ev, group):
    rows = {id(row) for entry in group for row in entry.outcomes}
    r._remember_preview_graphs({ev.id: (ev, group)}, rows, module._mono())


# ── the specimen ─────────────────────────────────────────────────────────────

def test_bax_names_no_leg_and_florent_bax_names_one():
    """The structural condition: "Bax" is too short for the side test."""
    home_side_nameable = live_blend.home_side_nameable
    assert not home_side_nameable(legs(), "Bax")
    assert home_side_nameable(legs(), "Florent Bax")
    assert home_side_nameable(legs(), "Cadenasso")
    assert not home_side_nameable(legs(), "")


async def test_an_unprovable_receipt_resolves_to_the_served_number_at_once(r, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    ev = event("Bax")
    read(r, ev, legs())
    clock[0] += 0.05
    receive(r, 0.58, 0.43)  # book proof passes: every leg at its live midpoint
    clock[0] += 0.10
    await drained(r)

    # Resolved, not waiting for the stamp: the clock holds nothing for it.
    assert EV not in r._hl_pending
    assert r._receipt_class_events.get("served_unprovable") == {EV: 1}
    assert "na_proof" not in r._hl_fallback
    # Nothing previewed or published, and no confirmation clock moved: the
    # screen keeps the served number with its own age.
    assert ops(r.sent, "propose") == []
    assert pending() is None
    assert r.confirmed_calls == []
    assert ev.win_probability_sources["kalshi"]["value"] == SERVED
    assert ev.win_probability_sources["kalshi"]["updated_at"] == (
        NOW - timedelta(seconds=30)).isoformat()
    # Counted with its own label, never ranked as a delivery.
    line = r._hl_summary()
    assert line.startswith("n=0 ")
    assert line.endswith(" unprovable=1/100ms@%d,moved=1" % EV)
    assert r._hl_summary() == "n=0 late=0 settled=0 nobook=0 noreading=0"

    # The next stamp still delivers the moved price: urgent past the 20 s
    # receipt floor, as an `na_proof` mark made it, and nothing at receipt
    # stands in front of the stamp's own proposal.
    assert EV in r._urgent_stamp
    r._last_refresh_at[EV] = clock[0] - 1.0
    assert r._floor_passed(EV, clock[0], clock[0])
    stamped = blend_preview.registry().propose(
        EV, "kalshi", value=0.57, event=ev, row_sources=ev.preview_sources,
        row_rev=ev.preview_rev, observed_basis={str(CAD_LEG): NOW.timestamp()})
    assert stamped and pending().value == 0.57


async def test_an_unchanged_unprovable_repeat_resolves_too(r, monkeypatch):
    """A repeat at the stored prices on a newer bound: also not held."""
    clock = [1000.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    read(r, event("Bax"), legs())
    receive(r, 0.55, 0.45)
    clock[0] += 0.02
    await drained(r)
    assert EV not in r._hl_pending and ops(r.sent, "propose") == []
    assert r._hl_summary().endswith(" unprovable=1/20ms@%d,moved=0" % EV)


async def test_an_input_an_earlier_refusal_held_ends_at_its_age(r, monkeypatch):
    """It waited for another reason first: a real wait, ranked under it."""
    clock = [1000.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    read(r, event("Bax"), legs())
    receive(r, 0.58, 0.43)
    r._hl_pending[EV][1] = "old_graph"
    clock[0] += 1.5
    await drained(r)
    assert EV not in r._hl_pending
    line = r._hl_summary()
    assert "worst=%d:1500:old_graph>served_unprovable[" % EV in line
    assert "unprovable=" not in line


# ── controls: where a proof is possible nothing changes ─────────────────────

async def test_control_a_nameable_home_previews_the_proven_number(r, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    read(r, event("Florent Bax"), legs())
    receive(r, 0.58, 0.43)
    await drained(r)
    [op] = ops(r.sent, "propose")
    assert op["value"] == 0.575  # mean(0.58, 1 - 0.43): the two-leg proof
    assert pending().at_receipt and pending().value == 0.575
    assert ("previewed", [EV]) in r.confirmed_calls
    assert "served_unprovable" not in r._receipt_class_events
    assert "unprovable=" not in r._hl_summary()


async def test_control_a_possible_proof_not_yet_held_still_waits(r, monkeypatch):
    """Nameable home, book proof refused (the book has moved off the input):
    a later receipt can prove it, so the input waits as `na_proof` as today."""
    clock = [1000.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    read(r, event("Florent Bax"), legs())
    receive(r, 0.58, 0.43)
    r.book = {"BAX": 0.60, "CAD": 0.41}
    await drained(r)
    assert ops(r.sent, "propose") == []
    assert r._hl_pending[EV][1] == "na_proof"
    assert r._hl_fallback.get("na_proof") == 1
    assert "served_unprovable" not in r._receipt_class_events
    assert "unprovable=" not in r._hl_summary()


async def test_control_no_proof_arguments_keep_the_orientation_path(r, monkeypatch):
    """Without current-book proof (Polymarket, other Kalshi markets) the
    cached orientation verdict path is untouched: no fall-through."""
    clock = [1000.0]
    monkeypatch.setattr(module, "_mono", lambda: clock[0])
    r.require_current_book_proof = False
    read(r, event("Bax"), legs())
    receive(r, 0.58, 0.43)
    await drained(r)
    assert "served_unprovable" not in r._receipt_class_events
    assert "unprovable=" not in r._hl_summary()

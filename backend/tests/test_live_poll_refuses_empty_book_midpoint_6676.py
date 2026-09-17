"""#6676, the THIRD writer: the two-minute beat stops minting an empty book as 50%.

#6676 shipped three halves. The serve half (`test_grouped_feed_empty_book_6676.py`)
stops already-stored rows reaching a /sports card; the ingest half
(`test_polymarket_empty_book_ingest_6676.py`) stops the HOURLY Polymarket poll writing
them. Neither reaches this file's subject.

`poll_live_prediction_markets` runs every two minutes on the realtime queue and prices
its Polymarket arm with an INLINE policy — `prob = float(prices[0])`, a wide-spread
preference for `lastTradePrice`, and a name-index match. It therefore never picked up
the two midpoint predicates the ingest writer applies, and it re-minted the shape after
every release that fixed the other two.

THE SIBLING ARM IN THE SAME LOOP ALREADY STATES THE RULE. The Kalshi branch delegates
to `_kalshi_yes_probability` and says why in its own comment: "One price policy per
venue: the same spread guard the 2-hour poll uses (gotcha #19 / #181), so a wide
one-sided book cannot fabricate a ~0.50 quote here that the full poll would have
refused." The Polymarket branch made the same promise and did not keep it.

MEASURED, production 2026-09-17 16:45Z, at the LIVE bound (`EMPTY_BOOK_MAX_BID` is 0.05
since #5333): 21 legs / 16 markets / 14 events in 40 minutes. 19 of the 21 carry this
beat's fingerprint — a strict 2-minute cadence with a shared sub-second per stamp
(`…:19:22.842264`, `:23:22.844279`, `:31:22.846291`, `:33:22.842150`, `:43:22.846327`,
`:45:22.850504`) — against the hourly poll's `last_success_at` of 16:16:03Z. The other
2 (`16:15:14.937991`, `16:42:03.951022`) sit off that cadence and are a DIFFERENT
writer; this fix does not claim them and they stay open on #6676.

Reader-visible, not merely stored: `/api/futures/61246736` served outcomes 230621538 /
230492518 / 230621548 at `probability: 0.5` — three Sao Paulo Open set lines on a LIVE
match — each with a 1c bid / 99c ask behind it.

DECLINE, NOT WITHDRAW, and `TestItDeclinesRatherThanWithdrawing` pins that as behaviour
rather than leaving it to the comment. `_unpriced_leg_external_ids` excludes this exact
class from retirement by name ("a real bid — we refused it, the venue did not"), and
`is_empty_book_midpoint`'s docstring forbids mutating a stored price on its account.
Declining also preserves the stored bid/ask/probability triple, which is the only thing
that lets the read-side predicate recognise the row afterwards.

RED-FIRST, run rather than asserted. With the guard deleted from
`prediction_market_matching.py`: **6 failed, 9 passed**. The four
`TestAnEmptyBookIsNotAForecast` arms redden (the phantom leg is written at 0.5 and a
snapshot is captured for it), plus
`TestGenuinePricesSurvive::test_an_honest_leg_beside_a_phantom_is_still_priced` — it
holds a phantom beside an honest leg, so it is a ship arm wearing a survivor's name —
plus the pinned limit in `TestAKnownLimitThisFixDoesNotReach`.

The three arms that actually test what must SURVIVE — a real two-sided book, a blowout
priced off its trade, a one-sided longshot — pass in BOTH states. That asymmetry is the
point: a guard that reddens the survivors too is refusing more than this class.

Both arms of `TestItDeclinesRatherThanWithdrawing` also pass in both states, on purpose;
that class's docstring says which mutation they exist for.
"""
import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import Select, Update
from sqlalchemy.sql.elements import TextClause

from app.tasks import prediction_market_matching as pmm
from app.utils.feed_market_quality import (
    EMPTY_BOOK_MAX_BID,
    EMPTY_BOOK_MIN_ASK,
    is_empty_book_midpoint,
)

# `pytest.ini` runs asyncio in AUTO mode, so the coroutines below need no mark.


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# the harness — the shape `test_live_poll_refuses_a_settled_prekickoff_book_5896.py`
# established, CARRIED rather than imported for the reason that file gives: a test
# module importing another test module couples two files' collection order. These
# arms need their own rows anyway (a Polymarket market with an empty book, which
# that file has no reason to hold).
# --------------------------------------------------------------------------


class _Outcome:
    def __init__(self, oid, market_id, external_id, name, *, probability=None,
                 bid=None, ask=None):
        self.id = oid
        self.market_id = market_id
        self.external_id = external_id
        self.name = name
        self.rank = 1
        self.current_probability = probability
        self.current_american_odds = None
        self.current_yes_bid = bid
        self.current_yes_ask = ask
        self.probability_change_24h = None
        self.is_winner = None
        self.calibration_probability = None
        self.last_updated = None


class _Market:
    def __init__(self, mid, source, external_id, *, gamma_event_id=None):
        self.id = mid
        self.source = source
        self.external_id = external_id
        self.name = f"market {mid}"
        self.market_type = "game_prop"
        self.group_id = None
        # The #5823 cascade reads this FIRST, so a decomposed sub-market is
        # fetched by its Gamma EVENT id rather than its condition id.
        self.market_metadata = (
            None if gamma_event_id is None
            else {"polymarket_event_id": gamma_event_id}
        )


class _Event:
    def __init__(self, eid, *, status="live", commence=None, completed_at=None):
        self.id = eid
        self.status = status
        self.home_team_name = "Suzan Lamens"
        self.away_team_name = "Solana Sierra"
        # #6608's tri-state is read off this row; `None` is faithful for a match
        # in play. Carried even though these arms stop short of the blend stage,
        # because its absence is a latent AttributeError for the next arm.
        self.completed_at = completed_at
        self.commence_time = commence or (_now() - timedelta(minutes=30))


@dataclass
class _Population:
    rows: list
    outcomes: list


def _classify(stmt) -> str:
    if isinstance(stmt, TextClause):
        return "text"
    if isinstance(stmt, Select):
        names = [c.get("name") for c in stmt.column_descriptions]
        if "FuturesMarket" in names:
            return "population"
        if names == ["FuturesOutcome"]:
            return "outcomes"
        return "select:" + ",".join(str(n) for n in names)
    if isinstance(stmt, Update):
        return "update"
    return "insert"


class _Result:
    def __init__(self, rows=(), scalar_value=None):
        self._rows = list(rows)
        self._scalar = scalar_value
        self.rowcount = len(self._rows)

    def all(self):
        return list(self._rows)

    def fetchall(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return _Scalars(self._rows)

    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return self._scalar

    def __iter__(self):
        return iter(self._rows)


class _Scalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, population: _Population):
        self._population = population
        self.journal = []
        self.added = []
        # Every INSERT the beat issues, kept as the compiled statement so an arm
        # can ask what was captured. The phantom's absence from the CHART is half
        # the ship: a snapshot row is a point on the reader's graph.
        self.inserts = []

    async def execute(self, stmt, params=None):
        kind = _classify(stmt)
        self.journal.append(kind)
        if kind == "insert":
            self.inserts.append(stmt)
        if kind == "population":
            return _Result(self._population.rows)
        if kind == "outcomes":
            return _Result(self._population.outcomes)
        return _Result()

    async def commit(self):
        self.journal.append("commit")

    async def rollback(self):
        self.journal.append("rollback")

    def expunge_all(self):
        self.journal.append("expunge_all")

    def add(self, obj):
        self.added.append(obj)


# --------------------------------------------------------------------------
# the venue, in its own encoding
# --------------------------------------------------------------------------

GAMMA_EVENT_ID = "31552"
MARKET_ID = 61246736
PHANTOM_CONDITION = "0xphantom"
HONEST_CONDITION = "0xhonest"


def _gamma_market(condition_id, prices, bid, ask, last=None):
    """One raw Gamma market, stringified arrays and all — the venue's own shape."""
    return {
        "conditionId": condition_id,
        "question": "Sao Paulo Open: Set 1 O/U 9.5",
        "outcomes": json.dumps(["Over", "Under"]),
        "outcomePrices": json.dumps([str(p) for p in prices]),
        "bestBid": bid,
        "bestAsk": ask,
        "lastTradePrice": last,
    }


class _PolymarketService:
    """The venue, answered with the RAW payload the production loop parses."""

    def __init__(self, event_payload):
        self._payload = event_payload
        self.fetched = []

    async def get_event_by_id(self, event_id):
        self.fetched.append(event_id)
        return self._payload

    async def close(self):
        return None


def _beat(gamma_markets, *, stored_probability=0.42):
    """One Polymarket market on one live event, with one row per Gamma leg."""
    market = _Market(
        MARKET_ID, "polymarket", "0xparent", gamma_event_id=GAMMA_EVENT_ID
    )
    event = _Event(15313776)
    outcomes = [
        _Outcome(
            230621538 + i,
            market.id,
            gm["conditionId"],
            "Over",
            probability=stored_probability,
        )
        for i, gm in enumerate(gamma_markets)
    ]
    payload = {"id": GAMMA_EVENT_ID, "markets": list(gamma_markets)}
    return _Population([(market, event)], outcomes), outcomes, payload


async def _run(monkeypatch, session, poly):
    """Run the REAL beat against the fake session and the fake venue."""

    @asynccontextmanager
    async def _fake_session():
        yield session

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(pmm, "get_task_session", _fake_session)
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(
        "app.services.polymarket_api.PolymarketAPIService", lambda *a, **kw: poly
    )
    # The blend stage is off: these arms are aimed at the price loop, and a blend
    # that silently declined would be an invisible reason for a green arm.
    monkeypatch.setattr(pmm, "_select_primary_market", lambda group: None)
    return await pmm._poll_live_prediction_market_prices()


# --------------------------------------------------------------------------
# the premise, asserted rather than assumed
# --------------------------------------------------------------------------


class TestThePremise:
    def test_the_specimen_book_really_is_the_shape_the_predicate_names(self):
        """1c bid / 99c ask priced at 0.5 — the production specimen, not a strawman."""
        assert is_empty_book_midpoint(0.5, 0.01, 0.99) is True

    def test_the_honest_book_is_not_that_shape(self):
        """A 60/64 book at 0.62 must be invisible to the predicate, or the arm below
        proves nothing about what survives."""
        assert is_empty_book_midpoint(0.62, 0.60, 0.64) is False

    def test_the_bound_is_read_from_the_shared_constant_not_restated_here(self):
        """#5333 moved the bid bound 0.02 -> 0.05 and the serve side and the
        calibration SQL mirror read the same constant. A number pinned in this file
        would go stale silently the next time it moves."""
        assert 0.01 <= EMPTY_BOOK_MAX_BID
        assert 0.99 >= EMPTY_BOOK_MIN_ASK

    async def test_the_venue_is_actually_reached(self, monkeypatch):
        """If the fetch never happened, every 'nothing was written' arm below would
        pass for the wrong reason."""
        population, _outcomes, payload = _beat(
            [_gamma_market(HONEST_CONDITION, [0.62, 0.38], 0.60, 0.64, last=0.62)]
        )
        session = _Session(population)
        poly = _PolymarketService(payload)
        await _run(monkeypatch, session, poly)
        assert poly.fetched == [GAMMA_EVENT_ID]


# --------------------------------------------------------------------------
# the ship
# --------------------------------------------------------------------------


class TestAnEmptyBookIsNotAForecast:
    async def test_a_one_cent_book_is_not_written_as_fifty_percent(self, monkeypatch):
        """The production specimen: outcome 230621538, 1c bid / 99c ask, no trade."""
        population, outcomes, payload = _beat(
            [_gamma_market(PHANTOM_CONDITION, [0.5, 0.5], 0.01, 0.99, last=None)]
        )
        session = _Session(population)
        await _run(monkeypatch, session, _PolymarketService(payload))
        assert outcomes[0].current_probability == 0.42, (
            "the beat overwrote a stored price with an empty book's midpoint"
        )

    async def test_no_chart_point_is_captured_for_it(self, monkeypatch):
        """A `FuturesOddsSnapshot` is a point on the reader's graph. Refusing the
        price and still writing the snapshot would move the defect to the chart."""
        population, _outcomes, payload = _beat(
            [_gamma_market(PHANTOM_CONDITION, [0.5, 0.5], 0.01, 0.99, last=None)]
        )
        session = _Session(population)
        await _run(monkeypatch, session, _PolymarketService(payload))
        assert session.inserts == []

    async def test_a_zero_last_trade_does_not_rescue_it(self, monkeypatch):
        """`lastTradePrice: 0` defeats the loop's own "no trading activity" skip
        (it is not None) while carrying no information. Measured shape."""
        population, outcomes, payload = _beat(
            [_gamma_market(PHANTOM_CONDITION, [0.5, 0.5], 0.01, 0.99, last=0)]
        )
        session = _Session(population)
        await _run(monkeypatch, session, _PolymarketService(payload))
        assert outcomes[0].current_probability == 0.42

    async def test_the_three_cent_bid_5333_opened_is_covered_too(self, monkeypatch):
        """#6676 shipped while `EMPTY_BOOK_MAX_BID` was 0.02, so a 3c bid escaped.
        #5333 moved the bound to 0.05; this arm asserts the third writer inherits
        that close rather than re-opening it."""
        population, outcomes, payload = _beat(
            [_gamma_market(PHANTOM_CONDITION, [0.5, 0.5], 0.03, 0.97, last=None)]
        )
        session = _Session(population)
        await _run(monkeypatch, session, _PolymarketService(payload))
        assert outcomes[0].current_probability == 0.42


class TestItDeclinesRatherThanWithdrawing:
    """⚠️ NEITHER ARM HERE RED-FIRSTS, and that is a property of the class, not an
    oversight. Both pass with the guard removed too — without it the beat writes
    0.5, which is also "not None" and also leaves the book columns alone. They are
    aimed at a DIFFERENT mutation: somebody later deciding the honest response to a
    dead book is to null the row. That change would redden them and nothing else in
    this file. Stated rather than left for a mutation run to discover.
    """

    async def test_the_stored_price_is_left_standing_not_nulled(self, monkeypatch):
        """`_unpriced_leg_external_ids` excludes a leg with a live bid from
        retirement BY NAME. Withdrawing here would un-price live markets and would
        contradict the ingest half."""
        population, outcomes, payload = _beat(
            [_gamma_market(PHANTOM_CONDITION, [0.5, 0.5], 0.01, 0.99, last=None)],
            stored_probability=0.42,
        )
        session = _Session(population)
        await _run(monkeypatch, session, _PolymarketService(payload))
        assert outcomes[0].current_probability is not None

    async def test_the_stored_book_columns_are_not_overwritten(self, monkeypatch):
        """The stored bid/ask/probability triple is what lets the read-side
        predicate recognise the row. A guard that cleared it would blind #5247."""
        population, outcomes, payload = _beat(
            [_gamma_market(PHANTOM_CONDITION, [0.5, 0.5], 0.01, 0.99, last=None)]
        )
        outcomes[0].current_yes_bid = 0.01
        outcomes[0].current_yes_ask = 0.99
        session = _Session(population)
        await _run(monkeypatch, session, _PolymarketService(payload))
        assert (outcomes[0].current_yes_bid, outcomes[0].current_yes_ask) == (
            0.01,
            0.99,
        )


class TestGenuinePricesSurvive:
    """The half that must NOT redden. A guard that fails both halves refuses too
    much, and these are the populations this class would otherwise spend."""

    async def test_a_real_two_sided_book_is_still_written(self, monkeypatch):
        population, outcomes, payload = _beat(
            [_gamma_market(HONEST_CONDITION, [0.62, 0.38], 0.60, 0.64, last=0.62)]
        )
        session = _Session(population)
        await _run(monkeypatch, session, _PolymarketService(payload))
        assert outcomes[0].current_probability == pytest.approx(0.62)

    async def test_a_blowout_priced_off_its_last_trade_survives(self, monkeypatch):
        """Gotcha #19. A wide book during a blowout clears because everyone is on
        one side, not because nobody is there — so the venue's own `outcomePrices`
        tracks the trade and sits FAR from the book's midpoint. 0.93 against a
        1c/99c book is 0.43 away from 0.5, so neither predicate can see it."""
        population, outcomes, payload = _beat(
            [_gamma_market(HONEST_CONDITION, [0.93, 0.07], 0.01, 0.99, last=0.93)]
        )
        session = _Session(population)
        await _run(monkeypatch, session, _PolymarketService(payload))
        assert outcomes[0].current_probability == pytest.approx(0.93)

    async def test_a_longshot_on_a_one_sided_book_survives(self, monkeypatch):
        """`is_empty_book_midpoint` deliberately does NOT treat a missing side as
        the widest quote — a one-sided book still carries information, and those
        rows measured honest. A null bid must not be read as an empty book."""
        population, outcomes, payload = _beat(
            [_gamma_market(HONEST_CONDITION, [0.36, 0.64], None, 0.36, last=0.36)]
        )
        session = _Session(population)
        await _run(monkeypatch, session, _PolymarketService(payload))
        assert outcomes[0].current_probability == pytest.approx(0.36)

    async def test_an_honest_leg_beside_a_phantom_is_still_priced(self, monkeypatch):
        """The refusal is per-LEG. One dead line in an event must not cost the
        event its real prices — the `continue` skips a leg, never the loop."""
        population, outcomes, payload = _beat(
            [
                _gamma_market(PHANTOM_CONDITION, [0.5, 0.5], 0.01, 0.99, last=None),
                _gamma_market(HONEST_CONDITION, [0.62, 0.38], 0.60, 0.64, last=0.62),
            ]
        )
        session = _Session(population)
        await _run(monkeypatch, session, _PolymarketService(payload))
        assert outcomes[0].current_probability == 0.42
        assert outcomes[1].current_probability == pytest.approx(0.62)


class TestAKnownLimitThisFixDoesNotReach:
    async def test_the_name_index_match_clobbers_the_last_trade_preference(
        self, monkeypatch
    ):
        """A PINNED KNOWN LIMIT, found by this file and not fixed by it (#6676).

        I wrote in the production comment that the wide-spread `lastTradePrice`
        preference "runs ABOVE, so a leg with a real trade behind it has already
        displaced the midpoint and cannot reach this test". That is FALSE, and the
        first draft of the arm above proved it: the name-index block runs after the
        preference and unconditionally reassigns `prob = float(prices[idx])`, so for
        any leg whose outcome names are not yes/no — every Over/Under prop — the
        midpoint is put BACK and the trade is discarded.

        The honest reading of what the guard does here: before it, this leg was
        written at 0.5 with a 0.93 trade on the book; after it, nothing is written.
        Refusing is strictly better than publishing 0.5, but 0.93 is better than
        both, and recovering it means reordering a pricing policy — a change to
        legs this class never measured. Out of scope on purpose; recorded as a known limit on #6676, which stays
        open. No separate issue: it is a code finding with no production specimen
        attributed to THIS writer (the wide-book/last-trade divergences visible on
        production at 16:15Z carry the hourly poll's stamp, not this beat's).

        This arm asserts TODAY'S behaviour so the day somebody fixes the ordering,
        this test goes red and points at the comment that has to change with it.
        """
        population, outcomes, payload = _beat(
            [_gamma_market(HONEST_CONDITION, [0.5, 0.5], 0.01, 0.99, last=0.93)]
        )
        session = _Session(population)
        await _run(monkeypatch, session, _PolymarketService(payload))
        assert outcomes[0].current_probability == 0.42, (
            "the clobber is gone — recheck #6676's known-limit note and the ordering comment"
        )

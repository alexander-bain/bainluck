"""#3613: a linked Polymarket market born with no legs finally gets a price.

## the ship, stated as the user sees it

An upcoming fight page that shows **nothing at all** starts showing the price
Polymarket is quoting for it.

The specimen, measured 2026-09-06: `https://bainluck.com/events/15305793` —
**UFC 331, Ozzy Diaz vs Ryan Gandra**, "Starts in 13d 9h" — hero reads "No price
yet", Win Probability panel reads "Tracking will begin when odds are available",
and there is no props section at all. Meanwhile:

* the venue lists it (notice 26/27, read against Gamma's own API, not our
  tables): event `972409`, slug `ufc-ozz-rya18-2026-09-19`, its moneyline
  sub-market quoting **0.295 / 0.705 on a 21c-38c book**;
* **we already hold that market**, `futures_markets` id 60280227, `source =
  'polymarket'`, `status = 'open'`, **linked to event 15305793** — with **zero
  `futures_outcomes` rows**.

Nothing was mis-matched and nothing was missing. The market row exists, on the
right event, and has no legs.

## why no existing path could fill them

A parent row is created by the hourly Gamma poll on FIRST sight, and its legs
are written in the same pass — but only for the sub-markets carrying a price at
that moment. A fight listed before its book opens gets the row and nothing else.
Measured on production 2026-09-06, over the **1,607** open Polymarket markets
linked to a live-or-future event, by `volume_updated_at` (written only by that
poll's own upsert):

    <2h 75 | 2-6h 77 | 6-24h 196 | 1-7d 841 | >7d 279 | never 138

So the poll re-reads about a tenth of them in six hours, and the two paths built
for exactly this starvation cannot help:

* `futures_price_refresh` (#2199) addresses markets by id and **states in its own
  docstring that it "deliberately does NOT create markets, create outcomes"** —
  a price for a row we do not hold is counted and dropped, by design;
* `_poll_live_prediction_market_prices` is UPDATE-only.

Every path needs a leg to exist, and the one path that creates legs cannot reach
the market again. Result, 2026-09-06: **501 dark open linked markets across 159
events**, and **20 of those event pages showed no price from any source at all**.

## what this file drives

`_refresh_linked_polymarket_books` — the Polymarket twin of #3518/#3569's
`_refresh_linked_game_books` — executed against a recording session, so every
assertion reads **bound parameters off a statement the shipping code emitted**,
never source text. `test_polymarket_under_snapshot_book_p097` records why that
distinction is load-bearing (a source-level green survives a dead branch), and
this file borrows its recorder rather than writing a second one.

The refresh and the poll are also proved to price a market THE SAME WAY, because
#3613 extracted the poll's three shapes into `_parent_outcome_data` and both now
call it. A second opinion about what a book is worth is the failure mode that
extraction exists to make impossible.

## falsified, not assumed — and the falsification RE-LABELLED two tests

With `_parent_outcome_data` forced to return `[]` — the pre-ship world, where
nothing could turn a dark market into legs — **10 of 29 go red**, including
every arm that claims a price reaches the page:

    test_the_dark_fight_gets_the_price_the_venue_is_quoting ..... FAILED
    test_the_priced_leg_carries_a_snapshot_for_the_chart ........ FAILED
    test_the_leg_is_ungraded_and_says_so_explicitly ............. FAILED
    test_the_nineteen_untradeable_props_are_not_written ......... FAILED
    test_the_response_is_keyed_by_id_never_by_request_order ..... FAILED
    (+ the four `_parent_outcome_data` shape tests, and the two below)

Two of those were written as REFUSAL CONTROLS and are not:

    TestTheRefusals::test_a_conflicting_insert_writes_no_snapshot ... FAILED
    TestTheRefusals::test_it_refuses_an_incoherent_negrisk_field .... FAILED

Both assert a counter or an absence that an empty leg list produces for free, so
neither can tell "the guard fired" from "there was nothing to guard". They are
labelled **arms, not controls** in their own docstrings, and each one now also
asserts the population it refused was non-empty where it can.

The three that DO stay green under falsification are the real controls —
`test_it_never_invents_a_price`, `test_it_never_overwrites_an_existing_leg`,
`test_it_never_touches_identity` — plus every selector and wiring test, because
those are claims about shape rather than about a price arriving.

## what this ship is NOT

It does not fill the hero. Measured on the working sibling
`/events/15190803` (Steveson vs Sharaf, same card, same shape, legs present):
its hero reads 89%-11% from **five sportsbooks**, and its
`win_probability_sources` carries `betting` only — no polymarket key. Writing
parent legs renders the **GAME PROPS section** ("UFC 331 Gable Steveson Win
92%"), and that is the claim made here. Stamping a prediction-market source onto
a scheduled event's hero is the 15-minute matcher's job and a different ship;
claiming it here would be the "creating a row is not showing a price" error
CERT-2082 blocked #3518 for.
"""

from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.services.polymarket_api import PolymarketEvent, PolymarketMarket
from app.tasks import polymarket as poly
from tests.test_polymarket_under_snapshot_book_p097 import (
    RecordingSession,
    _bound_params,
)

UTC = timezone.utc

#: The venue's own numbers for the specimen, read from Gamma 2026-09-06 17:00Z.
MONEYLINE_PRICE = 0.295
MONEYLINE_BID, MONEYLINE_ASK = 0.21, 0.38

#: What the other nineteen sub-markets of that event look like: Gamma's
#: precomputed 0.5 sitting on a 3c-97c book nobody will trade inside, with no
#: trade behind it. #1578's phantom, and the reason "the event has 20 markets"
#: is not the same claim as "the event has 20 prices".
JUNK_PRICE, JUNK_BID, JUNK_ASK = 0.5, 0.03, 0.97


def _market(cid, question, price, bid, ask, *, outcomes=None, last=None, vol24=None):
    return PolymarketMarket(
        condition_id=cid,
        question=question,
        outcomes=outcomes or ["Yes", "No"],
        outcome_prices=[price, round(1 - price, 4)],
        best_bid=bid,
        best_ask=ask,
        last_trade_price=last,
        volume_24h=vol24,
        active=True,
    )


TITLE = "UFC 331: Ozzy Diaz vs. Ryan Gandra (Middleweight, Early Prelims)"


def _gandra_event(*, priced: bool = True) -> PolymarketEvent:
    """The specimen event: one tradeable moneyline, three untradeable props."""
    markets = [
        _market(
            "0xf5200a",
            TITLE,
            MONEYLINE_PRICE if priced else JUNK_PRICE,
            MONEYLINE_BID if priced else JUNK_BID,
            MONEYLINE_ASK if priced else JUNK_ASK,
            outcomes=["Ozzy Diaz", "Ryan Gandra"],
        ),
        _market("0x158733", "Fight to Go the Distance?", JUNK_PRICE, JUNK_BID, JUNK_ASK),
        _market("0x300ade", "Will Ozzy Diaz win by KO or TKO?", JUNK_PRICE, JUNK_BID, JUNK_ASK),
        _market("0x5319fb", "O/U 0.5 Rounds", JUNK_PRICE, JUNK_BID, JUNK_ASK),
    ]
    return PolymarketEvent(
        id="972409",
        title=TITLE,
        slug="ufc-ozz-rya18-2026-09-19",
        active=True,
        closed=False,
        neg_risk=False,
        tags=["Sports", "MMA", "UFC"],
        start_date=datetime(2026, 9, 5, 22, 1, 28, tzinfo=UTC),
        markets=markets,
    )


class _Row:
    """One row of `_LINKED_POLY_BOOKS_SQL`'s result.

    `category` and `market_tier` default to the specimen's OWN production values
    (`futures_markets` 60280227, read 2026-09-06): a Polymarket game moneyline
    born labelled `championship` at tier 5. Defaulting them to something the
    label correction would refuse would make every arm below pass for a reason
    the production row does not share.
    """

    def __init__(
        self,
        ident,
        external_id,
        name="a dark market",
        event_id=15305793,
        category="championship",
        market_tier=5,
    ):
        self.id = ident
        self.external_id = external_id
        self.name = name
        self.event_id = event_id
        self.category = category
        self.market_tier = market_tier


class _SelectorResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _WriteResult:
    """What Postgres hands back for `... ON CONFLICT DO NOTHING RETURNING id`.

    `scalar()` is an id when the row was INSERTED and **None when the conflict
    fired** — that is the whole signal the pass pairs a snapshot to, so the
    harness has to be able to answer both. `RecordingSession._Result` answers
    None for everything, which would have made the ship arm pass for the wrong
    reason (a green built on "nothing was inserted").
    """

    def __init__(self, ident):
        self._ident = ident

    def scalar(self):
        return self._ident


class _DarkSession(RecordingSession):
    """`RecordingSession`, plus the selector answer the pass opens with.

    The first `execute` is the raw-SQL selector; everything after it is a write
    and goes to the recorder unchanged. Splitting on statement ORDER rather than
    on type keeps the harness from having to understand the writes it records.
    """

    def __init__(self, rows, *, conflict_on_insert: bool = False):
        super().__init__()
        self._selector_rows = rows
        self._answered_selector = False
        self._conflict = conflict_on_insert
        self._next_outcome_id = 5000
        self.executions: list[tuple[object, object]] = []

    async def execute(self, stmt, *args, **kwargs):
        if not self._answered_selector:
            self._answered_selector = True
            self.selector_params = args[0] if args else kwargs.get("parameters")
            return _SelectorResult(self._selector_rows)
        # Statement AND its bound parameters. The label correction is raw
        # `text()`, so its target id lives in the params dict and nowhere in the
        # statement object — a recorder that kept only the statement could show
        # that an UPDATE ran and never which row it ran against.
        self.executions.append((stmt, args[0] if args else kwargs.get("parameters")))
        await super().execute(stmt, *args, **kwargs)
        if getattr(getattr(stmt, "table", None), "name", None) == "futures_outcomes":
            if self._conflict:
                return _WriteResult(None)
            self._next_outcome_id += 1
            return _WriteResult(self._next_outcome_id)
        return _WriteResult(None)


class _FakeService:
    """Gamma, as the pass uses it: one batched read and a parser."""

    def __init__(self, payloads, *, raise_on_batch=False):
        #: `{gamma event id: PolymarketEvent}` — what the venue answers with.
        self.payloads = payloads
        self.raise_on_batch = raise_on_batch
        self.batches: list[list[str]] = []
        self.closed = False

    async def get_events_by_ids(self, ids):
        self.batches.append(list(ids))
        if self.raise_on_batch:
            raise RuntimeError("gamma timeout")
        # Deliberately REVERSED, and silently short: Gamma promises neither the
        # order of the request nor its length, and `get_events_by_ids` says so.
        return list(reversed([{"id": i} for i in ids if i in self.payloads]))

    def _parse_event(self, raw):
        return self.payloads.get(raw["id"])

    async def close(self):
        self.closed = True


async def _execute(
    rows, payloads, monkeypatch, *, service=None, conflict_on_insert=False, **kwargs
):
    session = _DarkSession(rows, conflict_on_insert=conflict_on_insert)
    svc = service or _FakeService(payloads)

    @asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr(poly, "get_task_session", _fake_session)
    monkeypatch.setattr(
        "app.services.polymarket_api.PolymarketAPIService", lambda *a, **k: svc
    )
    stats = await poly._refresh_linked_polymarket_books(**kwargs)
    return stats, session, svc


def _writes(session, table_name):
    return [
        s
        for s in session.statements
        if getattr(getattr(s, "table", None), "name", None) == table_name
    ]


def _legs(session) -> dict[str, dict]:
    """`external_id -> bound params` of every futures_outcomes INSERT emitted."""
    return {
        _bound_params(s)["external_id"]: _bound_params(s)
        for s in _writes(session, "futures_outcomes")
    }


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


class TestTheDarkMarketGetsItsPrice:
    @pytest.mark.asyncio
    async def test_the_dark_fight_gets_the_price_the_venue_is_quoting(
        self, monkeypatch
    ):
        """The whole ship in one assertion: 0.295 lands on market 60280227."""
        stats, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event()},
            monkeypatch,
        )

        legs = _legs(session)
        assert "0xf5200a" in legs, (
            "the tradeable moneyline was not written — the page still shows "
            "nothing while Polymarket quotes 29.5%"
        )
        leg = legs["0xf5200a"]
        assert leg["market_id"] == 60280227
        assert leg["current_probability"] == pytest.approx(MONEYLINE_PRICE)
        assert leg["current_yes_bid"] == pytest.approx(MONEYLINE_BID)
        assert leg["current_yes_ask"] == pytest.approx(MONEYLINE_ASK)
        assert stats["outcomes_created"] == 1
        assert stats["terminal"] == "complete"

    @pytest.mark.asyncio
    async def test_the_nineteen_untradeable_props_are_not_written(self, monkeypatch):
        """"The event has 20 markets" is not "the event has 20 prices".

        Gamma's precomputed 0.5 on a 3c-97c book is #1578's phantom. Writing it
        would put four fabricated 50%s on the page beside the one real number,
        which is worse than the empty state this ship replaces.
        """
        _, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event()},
            monkeypatch,
        )
        assert set(_legs(session)) == {"0xf5200a"}

    @pytest.mark.asyncio
    async def test_the_priced_leg_carries_a_snapshot_for_the_chart(self, monkeypatch):
        """A price with no snapshot is a number with no history behind it."""
        stats, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event()},
            monkeypatch,
        )
        snaps = _writes(session, "futures_odds_snapshots")
        assert len(snaps) == 1
        params = _bound_params(snaps[0])
        assert params["bookmaker"] == "polymarket"
        assert params["probability"] == pytest.approx(MONEYLINE_PRICE)
        assert params["yes_bid"] == pytest.approx(MONEYLINE_BID)
        assert stats["snapshots_written"] == 1

    @pytest.mark.asyncio
    async def test_the_leg_is_ungraded_and_says_so_explicitly(self, monkeypatch):
        """CAL-P1004R. `is_winner` is `boolean NULL DEFAULT false`, so an INSERT
        that OMITS it records an affirmative graded LOSS on a leg nobody called —
        and `api_settlement`-shaped fabricated losses are what #1852 exists to
        clean up. The column must be present and NULL, not absent."""
        _, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event()},
            monkeypatch,
        )
        leg = _legs(session)["0xf5200a"]
        assert "is_winner" in leg and leg["is_winner"] is None
        assert "resolution_source" in leg and leg["resolution_source"] is None


# ---------------------------------------------------------------------------
# The refusals. Each one is stated with the population that proves it FIRES —
# a guard that only ever sees an empty list is not evidence of a guard.
# ---------------------------------------------------------------------------


class TestTheRefusals:
    @pytest.mark.asyncio
    async def test_it_never_invents_a_price(self, monkeypatch):
        """Every sub-market untradeable → nothing written, and the pass SAYS so
        rather than reporting a quiet success (gotcha #53)."""
        stats, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event(priced=False)},
            monkeypatch,
        )
        assert _writes(session, "futures_outcomes") == []
        assert stats["markets_unpriced_at_venue"] == 1
        assert stats["markets_reached"] == 1

    @pytest.mark.asyncio
    async def test_it_never_overwrites_an_existing_leg(self, monkeypatch):
        """Gotcha #21 by construction rather than by predicate: there is no
        UPDATE branch to get a grade guard wrong. A row that appears underneath
        the pass — a poll landing mid-batch — wins."""
        _, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event()},
            monkeypatch,
        )
        for stmt in _writes(session, "futures_outcomes"):
            compiled = str(stmt.compile(dialect=postgresql.dialect()))
            assert "ON CONFLICT" in compiled and "DO NOTHING" in compiled, compiled
            assert "DO UPDATE" not in compiled

    @pytest.mark.asyncio
    async def test_a_conflicting_insert_writes_no_snapshot(self, monkeypatch):
        """AN ARM, NOT A CONTROL — it goes red under this file's falsification,
        because "no snapshot" is also what an empty leg list produces. The
        non-empty INSERT assertion below is what separates the two.

        `ON CONFLICT DO NOTHING ... RETURNING id` returns NOTHING when the
        conflict fires, and that is the only signal the pass has. Pairing a
        snapshot to a row it did not write would put a second observation of the
        same instant on someone else's leg — the mis-pairing the p097 helper
        exists to catch on the poll side."""
        stats, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event()},
            monkeypatch,
            conflict_on_insert=True,
        )
        assert _writes(session, "futures_outcomes"), "the INSERT is still attempted"
        assert _writes(session, "futures_odds_snapshots") == []
        assert stats["outcomes_created"] == 0
        assert stats["snapshots_written"] == 0

    @pytest.mark.asyncio
    async def test_it_never_touches_identity(self, monkeypatch):
        """#3532's whole story is two writers on one column.

        The pass writes prices and legs. Since CERT-2111 it also writes ONE
        market-row column — `category`, a display label, on a row it has just
        given its first legs — and that exception is named here rather than left
        for a reader to discover: the assertion is that the only statement
        touching `futures_markets` sets `category` and nothing else, and that no
        statement anywhere binds an `event_id` or a `commence_time`.
        """
        _, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event()},
            monkeypatch,
        )
        market_sql = [
            str(stmt) for stmt, _p in session.executions
            if "futures_markets" in str(stmt)
        ]
        assert len(market_sql) == 1, (
            f"expected exactly one futures_markets statement, got {market_sql}"
        )
        sql = market_sql[0]
        assert "SET category = 'game_prop'" in sql, sql
        for forbidden in ("event_id", "commence_time", "market_tier", "name"):
            assert f"{forbidden} =" not in sql, (
                f"the label correction is writing {forbidden} — it may write "
                "`category` and nothing else"
            )
        for stmt in session.statements:
            if "futures_markets" in str(stmt):
                continue
            params = _bound_params(stmt)
            assert "event_id" not in params
            assert "commence_time" not in params

    @pytest.mark.asyncio
    async def test_it_refuses_an_incoherent_negrisk_field(self, monkeypatch):
        """AN ARM, NOT A CONTROL — it goes red under this file's falsification,
        because a counter that never increments is also what an empty leg list
        produces. The `_parent_outcome_data` assertion below is what makes the
        skip mean "three near-certain legs were refused" rather than "there was
        nothing here".

        CAL-P006 (#1527): a single-winner partition whose legs are all
        near-certain is not a price at any leg, and per-leg guards cannot see
        it. The same refusal as the poll, for the same reason."""
        event = PolymarketEvent(
            id="972409",
            title="Who wins the belt?",
            active=True,
            closed=False,
            neg_risk=True,
            markets=[
                _market("0xaaa", "Fighter A", 0.99, 0.98, 0.995),
                _market("0xbbb", "Fighter B", 0.99, 0.98, 0.995),
                _market("0xccc", "Fighter C", 0.99, 0.98, 0.995),
            ],
        )
        assert len(poly._parent_outcome_data(event)) == 3, (
            "the fixture must actually PRODUCE three near-certain legs, or the "
            "skip below proves nothing"
        )
        stats, session, _ = await _execute(
            [_Row(60280227, "972409")], {"972409": event}, monkeypatch
        )
        assert stats["incoherent_fields_skipped"] == 1
        assert _writes(session, "futures_outcomes") == []


# ---------------------------------------------------------------------------
# Reading the venue, and the batch
# ---------------------------------------------------------------------------


class TestReadingTheVenue:
    @pytest.mark.asyncio
    async def test_the_response_is_keyed_by_id_never_by_request_order(
        self, monkeypatch
    ):
        """`get_events_by_ids` promises neither order nor length: ids Gamma does
        not recognise are simply absent. The fake reverses the batch and drops
        one, so a pass that zipped request to response would price the wrong
        market row — the exact class of bug #3569 found on the Kalshi side.
        """
        other = _gandra_event()
        other_event = other.model_copy(update={"id": "888888"})
        stats, session, _ = await _execute(
            [_Row(1, "972409", TITLE), _Row(2, "888888"), _Row(3, "777777")],
            {"972409": _gandra_event(), "888888": other_event},
            monkeypatch,
        )
        legs = _legs(session)
        # Both answered ids priced; each landed on ITS OWN market row.
        assert stats["markets_reached"] == 2
        assert stats["markets_absent_at_venue"] == 1
        assert legs["0xf5200a"]["market_id"] in {1, 2}

    @pytest.mark.asyncio
    async def test_one_unreadable_batch_does_not_end_the_run(self, monkeypatch):
        """A venue error is a fact about one request, not about the pass."""
        svc = _FakeService({"972409": _gandra_event()}, raise_on_batch=True)
        stats, _, used = await _execute(
            [_Row(60280227, "972409", TITLE)], {}, monkeypatch, service=svc
        )
        assert stats["batches_unreadable"] == 1
        assert stats["errors"]
        assert used.closed, "the HTTP client must be closed on every path"

    @pytest.mark.asyncio
    async def test_an_empty_selection_names_the_question_it_asked(self, monkeypatch):
        """Gotcha #53: "nothing is dark" and "the selector is broken" produce the
        same empty list, so the terminal has to distinguish them."""
        stats, session, _ = await _execute([], {}, monkeypatch)
        assert stats["terminal"] == "no_dark_linked_markets_in_window"
        assert session.statements == []

    @pytest.mark.asyncio
    async def test_the_deadline_stops_the_pass_and_says_it_did(self, monkeypatch):
        stats, _, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event()},
            monkeypatch,
            deadline_s=-1.0,
        )
        assert stats["deadline_hit"] is True
        assert stats["terminal"] == "deadline"
        assert stats["outcomes_created"] == 0


# ---------------------------------------------------------------------------
# The selector
# ---------------------------------------------------------------------------


class TestTheSelector:
    """The riskiest part of the change is raw SQL, and the recording harness
    cannot execute it. These read the query text — the one oracle that can
    answer "the predicate does NOT contain this" — plus the constants."""

    SQL = str(poly._LINKED_POLY_BOOKS_SQL)

    def test_it_selects_only_markets_with_no_legs_at_all(self):
        assert "NOT EXISTS" in self.SQL
        assert "FROM futures_outcomes fo WHERE fo.market_id = fm.id" in self.SQL

    def test_it_selects_only_linked_open_polymarket_rows(self):
        assert "fm.source = 'polymarket'" in self.SQL
        assert "fm.status = 'open'" in self.SQL
        assert "JOIN events e ON e.id = fm.event_id" in self.SQL

    def test_it_excludes_condition_id_keyed_sub_markets(self):
        """`/events?id=` addresses a Gamma EVENT id. A bare condition_id is not
        answerable there, and an unanswerable id in a batch is a silent
        `markets_absent_at_venue` that looks like a venue fact."""
        assert "fm.external_id NOT LIKE '0x%'" in self.SQL

    def test_the_horizon_reaches_the_band_the_kalshi_twin_leaves_behind(self):
        """#3602: the Kalshi pass stops at 7 days, so an event further out with
        zero prices is never reached. Measured 2026-09-06, 46 dark markets
        across 20 events sit in the 7-14d band — including the specimen at 13.4
        days — and NOTHING sits beyond 14, so this horizon is the population's
        own bound rather than a number someone liked."""
        from app.tasks.kalshi import LINKED_BOOK_HORIZON_DAYS

        assert poly.LINKED_POLY_BOOK_HORIZON_DAYS == 14
        assert poly.LINKED_POLY_BOOK_HORIZON_DAYS > LINKED_BOOK_HORIZON_DAYS

    def test_a_started_but_unflipped_event_stays_in_scope(self):
        """The lookback is why a game whose row never flipped to `live` is still
        re-read; without it the rows most likely to be watched drop out first."""
        assert poly.LINKED_POLY_BOOK_LOOKBACK_HOURS == 6
        assert "e.commence_time > NOW() - make_interval(hours => :lookback_hours)" in self.SQL

    @pytest.mark.asyncio
    async def test_the_bounds_are_actually_bound(self, monkeypatch):
        """A horizon constant nothing passes is a comment. Assert the values the
        selector is executed with, not the values that exist."""
        _, session, _ = await _execute([], {}, monkeypatch)
        # The empty case returns before any write, but the selector still ran.
        assert session.selector_params == {
            "lookback_hours": 6,
            "horizon_days": 14,
            "max_markets": poly._LINKED_POLY_MAX_MARKETS,
        }


# ---------------------------------------------------------------------------
# The extraction: the poll and the refresh cannot price a market differently
# ---------------------------------------------------------------------------


class TestOnePricerForBothPaths:
    def test_the_poll_builds_its_parent_legs_with_the_shared_function(self):
        """AST, not grep: a substring match survives the call being commented
        out, and matches the function's own definition."""
        import ast

        tree = ast.parse(inspect.getsource(poly._process_event_batch))
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_parent_outcome_data"
        ]
        assert len(calls) == 1, (
            "the poll must build its parent legs through the shared function — "
            "a second inline copy is how the two paths drift"
        )

    def test_the_refresh_builds_its_legs_with_the_same_function(self):
        assert "_parent_outcome_data(event)" in inspect.getsource(
            poly._refresh_linked_polymarket_books
        )

    def test_negrisk_legs_go_through_the_gated_resolver(self):
        """The three shapes are the poll's own and the difference between them
        is deliberate. NegRisk legs are priced by `_resolve_market_probability`,
        which applies the placeholder filter and the #151 evidence gate — so a
        leg with no evidence at a mid-range price is refused."""
        event = PolymarketEvent(
            id="e1",
            title="Who wins?",
            active=True,
            neg_risk=True,
            markets=[
                _market("0xaaa", "A", 0.60, 0.59, 0.61),
                _market("0xbbb", "B", 0.40, None, None),
            ],
        )
        rows = poly._parent_outcome_data(event)
        assert [r["external_id"] for r in rows] == ["0xaaa"]

    def test_a_game_events_legs_take_gammas_raw_price(self):
        """#1578 recorded the non-negRisk parent path as the least-guarded of
        the five write paths and added ONLY the phantom test to it. That
        judgement is preserved, not quietly tightened: a leg with a tight book
        is taken at Gamma's own number."""
        rows = poly._parent_outcome_data(_gandra_event())
        assert [r["external_id"] for r in rows] == ["0xf5200a"]
        assert rows[0]["prob"] == pytest.approx(MONEYLINE_PRICE)

    def test_a_single_market_event_yields_one_yes_leg(self):
        event = PolymarketEvent(
            id="e2",
            title="Will it happen?",
            active=True,
            neg_risk=False,
            markets=[_market("0xsolo", "Will it happen?", 0.30, 0.29, 0.31)],
        )
        rows = poly._parent_outcome_data(event)
        assert len(rows) == 1 and rows[0]["name"] == "Yes"

    def test_it_is_pure(self):
        """No DB, no network — so both callers can hold it inside their own
        transaction discipline without inheriting a second one."""
        src = inspect.getsource(poly._parent_outcome_data)
        for forbidden in ("session", "await ", "get_events", "commit("):
            assert forbidden not in src, forbidden


# ---------------------------------------------------------------------------
# The half that makes the price READABLE (CERT-2111)
# ---------------------------------------------------------------------------


def _label_updates(session) -> list[dict]:
    """Every `category = 'game_prop'` correction, with the id it targeted."""
    return [
        dict(params or {})
        for stmt, params in session.executions
        if "SET category = 'game_prop'" in str(stmt)
    ]


class TestTheLabelThatMakesItVisible:
    """CERT-2111: the leg reaches `/related-futures` and the page still drops it.

    `categorizeFutures()` (`frontend/components/RelatedFutures.tsx`) buckets on
    `display_category`, and it has no bucket for `championship` — the value
    `classify_market_category` returns verbatim for a Polymarket game moneyline,
    which is what our specimen was born as. The working sibling names the right
    label rather than leaving it to taste: event 15190803 renders GAME PROPS
    from market 60285732, `category = 'game_prop'`.
    """

    @pytest.mark.asyncio
    async def test_a_priced_dark_moneyline_is_relabelled_so_the_page_shows_it(
        self, monkeypatch
    ):
        stats, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event()},
            monkeypatch,
        )
        updates = _label_updates(session)
        assert len(updates) == 1, (
            "the specimen must be relabelled exactly once — without it the leg "
            f"is written and no reader ever sees it. updates={updates}"
        )
        assert updates[0]["id"] == 60280227, (
            f"the correction targeted {updates[0]}, not the market it priced"
        )
        assert stats["display_labels_corrected"] == 1

    @pytest.mark.asyncio
    async def test_a_market_that_got_no_legs_is_left_alone(self, monkeypatch):
        """The control that stops this from being a blanket relabeller.

        No price, no leg, no claim about what the row is — the pass has learnt
        nothing about this market and must not restate its label.
        """
        monkeypatch.setattr(poly, "_parent_outcome_data", lambda event: [])
        stats, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event()},
            monkeypatch,
        )
        assert _label_updates(session) == []
        assert stats["display_labels_corrected"] == 0

    @pytest.mark.asyncio
    async def test_every_leg_losing_the_race_leaves_the_label_alone(
        self, monkeypatch
    ):
        """`ON CONFLICT DO NOTHING` fired on all of them: another writer owns
        this market's legs, so this pass has added nothing and relabels nothing.
        A counter read at the pass level rather than the market level would fire
        here off a sibling market's insert."""
        stats, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event()},
            monkeypatch,
            conflict_on_insert=True,
        )
        assert _writes(session, "futures_outcomes"), "the INSERT is still attempted"
        assert _label_updates(session) == []
        assert stats["display_labels_corrected"] == 0

    @pytest.mark.asyncio
    async def test_a_row_that_is_not_one_contest_keeps_its_label(self, monkeypatch):
        """"Who will be UFC Middleweight champion at the end of 2026?" is a real
        championship future that lives on the same page (production event
        15190803 serves one). Relabelling it `game_prop` would file a season-long
        question under Game Props, which is the mirror of the bug being fixed."""
        _, session, _ = await _execute(
            [
                _Row(
                    999001,
                    "972409",
                    "Who will be UFC Middleweight champion at the end of 2026?",
                )
            ],
            {"972409": _gandra_event()},
            monkeypatch,
        )
        assert _label_updates(session) == []

    @pytest.mark.asyncio
    async def test_a_row_already_labelled_game_prop_is_not_rewritten(
        self, monkeypatch
    ):
        """A no-op UPDATE is still a write: it takes a row lock and stamps
        nothing. The pass skips the statement rather than relying on
        `IS DISTINCT FROM` to make it harmless."""
        _, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE, category="game_prop")],
            {"972409": _gandra_event()},
            monkeypatch,
        )
        assert _label_updates(session) == []

    @pytest.mark.asyncio
    async def test_a_season_long_tier_is_out_of_scope(self, monkeypatch):
        """Tier 5 is "this one game". A tier-1 row wearing a matchup-shaped name
        is not a game prop however it reads, and the tier is the cheaper, harder
        signal — so it gates the correction too."""
        _, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE, market_tier=1)],
            {"972409": _gandra_event()},
            monkeypatch,
        )
        assert _label_updates(session) == []

    def test_the_name_predicate_refuses_what_it_should(self):
        """The predicate itself, stated as a table rather than inferred from the
        arms above — a display rule must refuse the rows a permissive matcher
        helper exists to accept."""
        accepted = [
            "UFC 331: Ozzy Diaz vs. Ryan Gandra (Middleweight, Early Prelims)",
            "Bills at Jets",
            "Alcaraz vs Sinner",
        ]
        refused = [
            "Who will be UFC Middleweight champion at the end of 2026?",
            "Will Sean O'Malley become UFC champion in 2026?",
            "NBA Champion 2027",
            "",
            None,
        ]
        for name in accepted:
            assert poly._is_one_game_matchup_name(name), name
        for name in refused:
            assert not poly._is_one_game_matchup_name(name), name

    def test_the_predicate_is_the_routes_own_definition(self):
        """The pass writes `game_prop`; `_build_related_futures` decides
        separately whether a row is "game-specific" using its own
        `_GAME_MATCHUP_RE`. If those two definitions drift, the database and the
        page disagree about what a row is — so they are pinned equal here rather
        than left to a comment. Change one and this names the other."""
        from app.routes.events import _GAME_MATCHUP_RE

        assert poly._GAME_MATCHUP_NAME_RE.pattern == _GAME_MATCHUP_RE.pattern, (
            "the pass's matchup predicate has drifted from the route's. Update "
            "both together, or the label written here stops meaning what the "
            "page tests for."
        )


# ---------------------------------------------------------------------------
# Falsification: the ship arms must be about the PRICE, not the plumbing
# ---------------------------------------------------------------------------


class TestTheGuardFailsWithoutTheShip:
    @pytest.mark.asyncio
    async def test_with_no_pricer_the_ship_arms_would_be_red(self, monkeypatch):
        """The pre-ship world, reproduced: nothing turns a dark market into
        legs. Run here so the falsification receipt in this file's header is a
        test rather than a claim about a run someone did once."""
        monkeypatch.setattr(poly, "_parent_outcome_data", lambda event: [])
        stats, session, _ = await _execute(
            [_Row(60280227, "972409", TITLE)],
            {"972409": _gandra_event()},
            monkeypatch,
        )
        assert _writes(session, "futures_outcomes") == []
        assert _writes(session, "futures_odds_snapshots") == []
        assert stats["outcomes_created"] == 0


# ---------------------------------------------------------------------------
# Wiring: a pass nobody runs is not a fix
# ---------------------------------------------------------------------------


class TestItIsActuallyScheduled:
    def test_the_beat_entry_exists_on_the_heavy_queue(self):
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule[
            "refresh-linked-polymarket-books-hourly"
        ]
        assert entry["task"] == "app.tasks.refresh_linked_polymarket_books"
        assert entry["options"]["queue"] == "heavy"

    def test_it_shares_its_minute_with_no_heavy_sibling(self):
        """Written narrowly first — "clear of the other Gamma readers" — and
        that version passed while `:35` collided with TWO heavy siblings
        (`precompute-backfill-winners-status` hourly, and
        `match-prediction-markets` at :05/:20/:35/:50). CI caught it;
        this test did not, because it checked the three beats I happened to be
        thinking about instead of the queue the task actually runs on.

        So the rule is the queue: nothing else on `heavy` may fire on any minute
        this fires on. That is also what `test_schedule_sentinel_wiring` asserts
        globally — pinned here too so a change to THIS entry fails in the file
        that owns it."""
        from app.tasks import celery_app

        beat_schedule = celery_app.conf.beat_schedule
        mine = beat_schedule["refresh-linked-polymarket-books-hourly"]["schedule"]
        my_minutes = set(mine.minute)

        for name, entry in beat_schedule.items():
            if name == "refresh-linked-polymarket-books-hourly":
                continue
            if (entry.get("options") or {}).get("queue") != "heavy":
                continue
            sched = entry.get("schedule")
            minute = getattr(sched, "minute", None)
            hour = getattr(sched, "hour", None)
            if minute is None or hour is None:
                continue
            # Hourly, so an overlapping minute collides whatever the sibling's
            # hour set is.
            assert not (my_minutes & set(minute)), (
                f"{name} fires at minute {sorted(set(minute) & my_minutes)} on "
                "the heavy queue, which this task also claims"
            )

    def test_it_is_hourly_and_clear_of_the_other_gamma_reader(self):
        """The venue-facing reason for the slot, kept as its own statement: the
        discovery poll at :15 is the only other Gamma reader, and the two must
        never hold that rate limit at once."""
        from app.tasks import celery_app

        beat_schedule = celery_app.conf.beat_schedule
        mine = beat_schedule["refresh-linked-polymarket-books-hourly"]["schedule"]
        assert set(mine.minute) == {38}
        assert not (
            set(mine.minute)
            & set(beat_schedule["poll-polymarket-hourly"]["schedule"].minute)
        )

    def test_the_celery_task_resolves_to_the_pass(self):
        from app.tasks import refresh_linked_polymarket_books

        assert (
            refresh_linked_polymarket_books.name
            == "app.tasks.refresh_linked_polymarket_books"
        )
        assert "_refresh_linked_polymarket_books" in inspect.getsource(
            refresh_linked_polymarket_books
        )

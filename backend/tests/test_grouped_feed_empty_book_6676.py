"""#6676 — the Sports strip stops printing a price no book supports.

WHAT A READER SAW. Three consecutive Game Props cards in one 390px viewport on
``/sports``, each printing "Over 50% / Under 50%" with the bar drawn at exactly
half, one card below a real 57/43. The stored rows behind them carry
``current_probability 0.500000`` beside ``current_yes_bid 0.0200 /
current_yes_ask 0.9700`` — a two-sided quote that bounds nothing, whose own
midpoint is 0.495 — with ``volume`` and ``price_changed_at`` NULL.

The specimen values in `THE_THREE_STORED_SPECIMENS` are the production rows for
outcomes 230498576 / 230496527 / 230475436 as read on 2026-09-17, not invented
ones, which is why this file asserts on 0.02/0.97 rather than on a rounder book.

WHAT THIS FILE IS FOR. `routes/events.py` (`game-markets`) has dropped these legs
since #5247; the grouped feed never got the rule. So the risk this guards is not
"is the predicate right" — that is #5247's own suite — it is:

  1. the strip asks the question AT ALL, on the real stored values (`TestTheStrip*`),
  2. it asks the SAME question the event page asks, so the two surfaces cannot
     drift into disagreeing about whether a row has a price (`TestOneRuleTwoSurfaces`),
  3. withholding does not empty the surface it is defending (`TestTheStripIsStillAStrip`) —
     a refusal rule that leaves a blank page passes every refusal assertion ever
     written, and that is the failure mode this class of fix has,
  4. and the things that must SURVIVE do (`TestGenuinePricesSurvive`): a genuine
     coin flip on a tight book, a traded price, a real longshot, a model price
     with no book at all. "No trade" is not "no quote".

RED-FIRST, against the unfixed `routes/futures.py`: 8 failed, 7 passed, exit 1.
The 7 that pass without the fix are the survival controls and the shared-rule
assertions — they are controls precisely because they must not move.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routes.futures import (
    _leg_prices_an_empty_book,
    _market_has_priced_outcome,
)
from app.utils.feed_market_quality import is_empty_book_midpoint


def outcome(prob, bid, ask, name="Over", oid=1):
    """An outcome in the shape the route reads it: a row, with Decimals.

    `current_probability` is `Numeric(7, 6)` and `current_yes_bid`/`_ask` are
    numerics too, so SQLAlchemy hands the route `Decimal`, never `float`. #2710
    is on record in this same module about what assuming `float` here costs, so
    the specimens are Decimals and the float spellings are a separate case below.
    """
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=None if prob is None else Decimal(str(prob)),
        current_yes_bid=None if bid is None else Decimal(str(bid)),
        current_yes_ask=None if ask is None else Decimal(str(ask)),
        probability=None if prob is None else Decimal(str(prob)),
        american_odds=None,
    )


#: The production rows, verbatim: prob 0.500000 on a 0.0200 / 0.9700 book.
THE_THREE_STORED_SPECIMENS = [
    ("230498576", "61254969 Jagiellonia O/U 9.5 Total Corners"),
    ("230496527", "61253744 Cavalry O/U 11.5 Total Corners"),
    ("230475436", "61246705 Cavalry O/U 13.5 Total Corners"),
]


class TestTheStripAsksTheQuestion:
    @pytest.mark.parametrize("outcome_id,what", THE_THREE_STORED_SPECIMENS)
    def test_each_named_specimen_is_withheld(self, outcome_id, what):
        """The three cards from the 390px frame, on their real stored values."""
        assert _leg_prices_an_empty_book(outcome(0.5, 0.02, 0.97)) is True, what

    def test_the_half_cent_skew_is_the_whole_point(self):
        """0.5 is NOT the midpoint of 0.02/0.97 — 0.495 is.

        The ingest guard in use (`is_fabricated_midpoint`) wants the price ON the
        midpoint within 0.0005 and so misses this by a factor of ten; #5247's
        rule carries a 0.01 tolerance and catches it. If someone ever "tidies"
        this call site onto the other predicate, this is the test that objects.
        """
        assert (0.02 + 0.97) / 2 == pytest.approx(0.495)
        from app.utils.feed_market_quality import is_fabricated_midpoint

        assert is_fabricated_midpoint(0.5, 0.02, 0.97) is False
        assert _leg_prices_an_empty_book(outcome(0.5, 0.02, 0.97)) is True

    def test_floats_are_withheld_too(self):
        """Not every caller hands the route a Decimal; the rule cannot care."""
        o = SimpleNamespace(
            current_probability=0.5, current_yes_bid=0.02, current_yes_ask=0.97
        )
        assert _leg_prices_an_empty_book(o) is True


class TestOneRuleTwoSurfaces:
    """The strip must ask what the event page asks, field for field.

    `game-markets` has dropped these legs since #5247. The defect was that the
    two surfaces draw from the same rows and disagreed. A guard that only pins
    the strip's behaviour would let them drift apart again.
    """

    @pytest.mark.parametrize(
        "prob,bid,ask",
        [
            (0.5, 0.02, 0.97),    # the specimens
            (0.5, 0.49, 0.51),    # a genuine coin flip
            (0.28, 0.25, 0.31),   # the live 0.28 control
            (0.5, 0.03, 0.98),    # #5333's cohort: in reach since #5333, must AGREE
            (0.99, 0.0, 1.0),     # a price far from an empty book's midpoint
            (0.5, None, None),    # a model price, no book at all
            (None, 0.02, 0.97),   # no price to judge
        ],
    )
    def test_the_strip_and_the_event_page_give_the_same_answer(self, prob, bid, ask):
        assert _leg_prices_an_empty_book(outcome(prob, bid, ask)) is is_empty_book_midpoint(
            outcome(prob, bid, ask).current_probability,
            outcome(prob, bid, ask).current_yes_bid,
            outcome(prob, bid, ask).current_yes_ask,
        )

    def test_the_3c_cohort_came_into_reach_with_5333(self):
        """FLIPPED, and the flip is the whole point of having written it.

        This test asserted the 3c escape OPEN so that moving `EMPTY_BOOK_MAX_BID`
        could not happen quietly: whoever moved it had to come here and re-read
        why it had not been moved. #5333 did, moved it 0.02 -> 0.05 on a fresh
        production measurement (1,119 rows on their midpoint in (0.02, 0.05],
        price range 0.490-0.525), and this is the return trip.
        """
        assert _leg_prices_an_empty_book(outcome(0.5, 0.03, 0.98)) is True

    def test_the_compensated_book_came_into_reach_with_6727(self):
        """FLIPPED AGAIN, by the same mechanism, and that is the tripwire working.

        This was re-armed by #5333 one cent past its new bid bound — `0.06/0.97`
        asserted OUT OF REACH — so that the next person to widen had to come here
        first. #6727 did, and found the premise wrong rather than the cent: a
        0.06/0.97 book is 91 cents of nothing, and refusing to call it empty
        because one SIDE missed by a cent is the arbitrariness, not a safeguard.
        The pair of bounds became one statement about the spread. This is the
        return trip.
        """
        assert _leg_prices_an_empty_book(outcome((0.06 + 0.97) / 2, 0.06, 0.97)) is True

    def test_a_book_one_cent_short_of_the_spread_is_still_out_of_reach(self):
        """The tripwire re-armed at the edge that decides now: the WIDTH.

        The price is the book's exact midpoint, so the tolerance cannot be what
        keeps it — only the spread being one cent too short.
        """
        assert _leg_prices_an_empty_book(outcome((0.06 + 0.95) / 2, 0.06, 0.95)) is False
        assert _leg_prices_an_empty_book(outcome((0.0 + 0.89) / 2, 0.0, 0.89)) is False


class TestGenuinePricesSurvive:
    def test_a_quoted_coin_flip_on_a_tight_book_is_kept(self):
        """A real 50%: 49c bid / 51c ask. The ship must not eat this."""
        assert _leg_prices_an_empty_book(outcome(0.5, 0.49, 0.51)) is False

    def test_the_live_favourite_control_is_kept(self):
        """Market 61260583: 0.28 on 25c/31c, never traded. No trade is not no quote."""
        assert _leg_prices_an_empty_book(outcome(0.28, 0.25, 0.31)) is False

    def test_a_real_line_on_a_wide_book_is_kept(self):
        """0.78 on 8c/97c — wide, but nowhere near its own midpoint."""
        assert _leg_prices_an_empty_book(outcome(0.78, 0.08, 0.97)) is False

    def test_a_model_price_with_no_book_is_kept(self):
        """DataGolf / odds_api / a derived complement: both columns NULL."""
        assert _leg_prices_an_empty_book(outcome(0.5, None, None)) is False

    def test_a_one_sided_book_is_kept(self):
        """An ask at 36c says nobody will sell below 36c. That is information."""
        assert _leg_prices_an_empty_book(outcome(0.36, None, 0.36)) is False


class _StubResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _StubSession:
    """One canned read. A second would mean the fixture grew a fold it should not have."""

    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        if self.calls > 1:
            raise AssertionError("the route made a second read; this pool has nothing to fold")
        return _StubResult(self._rows)


class _Market:
    def __init__(self, mid, name, outcomes):
        self.id = mid
        self.name = name
        self.source = "polymarket"
        self.category = "game_prop"
        self.llm_sport_category = "soccer"
        self.status = "open"
        self.group_id = None
        self.group_type = None
        self.market_type = None
        self.outcomes = outcomes


class _Request:
    scope: dict = {}


class _Response:
    def __init__(self):
        self.headers = {}


@pytest.mark.asyncio
class TestThroughTheRoute:
    """The reader's claim, driven through the real `grouped_feed` coroutine.

    Everything above tests a predicate. This tests the endpoint: does the card
    actually leave the payload. A unit test of the rule would pass on a build
    where the route never applied it — which is the #4153 lesson recorded in
    `test_grouped_feed_container_fold_route_4153`'s own docstring, one file over
    and on this same endpoint.
    """

    @staticmethod
    async def _serve(markets, limit=20):
        from app.routes.futures import grouped_feed

        return await grouped_feed(
            request=_Request(),
            response=_Response(),
            category=None,
            sport=None,
            sports_only=True,
            limit=limit,
            db=_StubSession(markets),
        )

    @staticmethod
    def _cards(payload):
        return [c for c in (payload.get("feed") or []) if c.get("type") == "market"]

    async def test_the_specimen_card_is_not_in_the_payload(self):
        """The 390px frame's shape: both legs 0.5 on a 2c/97c book."""
        phantom = _Market(
            61254969,
            "Jagiellonia Bialystok vs. Legia Warszawa: O/U 9.5 Total Corners",
            [outcome(0.5, 0.02, 0.97, name="Over", oid=230498576),
             outcome(0.5, 0.02, 0.97, name="Under", oid=230498577)],
        )
        real = _Market(
            61260583,
            "W15 Sao Luis: Dias vs Estevez",
            [outcome(0.28, 0.25, 0.31, name="Over", oid=2),
             outcome(0.72, 0.69, 0.75, name="Under", oid=3)],
        )
        cards = self._cards(await self._serve([phantom, real]))
        names = [(c.get("market") or {}).get("name") for c in cards]
        assert "Jagiellonia Bialystok vs. Legia Warszawa: O/U 9.5 Total Corners" not in names
        assert "W15 Sao Luis: Dias vs Estevez" in names

    async def test_no_card_prints_a_fifty_fifty_that_no_book_supports(self):
        """The reader's own sentence, asserted on the served payload.

        Not "the phantom market is absent" — *no surviving card anywhere prints
        the pair of numbers the reader complained about*. A fix that dropped the
        named market and left an identical one behind would pass the test above
        and fail this one.
        """
        markets = [
            _Market(61254969, "Jagiellonia O/U 9.5 Total Corners",
                    [outcome(0.5, 0.02, 0.97, name="Over", oid=10),
                     outcome(0.5, 0.02, 0.97, name="Under", oid=11)]),
            _Market(61253744, "Cavalry O/U 11.5 Total Corners",
                    [outcome(0.5, 0.02, 0.97, name="Over", oid=12),
                     outcome(0.5, 0.02, 0.97, name="Under", oid=13)]),
            _Market(61246705, "Cavalry O/U 13.5 Total Corners",
                    [outcome(0.5, 0.02, 0.97, name="Over", oid=14),
                     outcome(0.5, 0.02, 0.97, name="Under", oid=15)]),
            _Market(1, "a real one",
                    [outcome(0.57, 0.55, 0.59, name="Over", oid=16),
                     outcome(0.43, 0.41, 0.45, name="Under", oid=17)]),
        ]
        cards = self._cards(await self._serve(markets))
        served = [
            (o.get("name"), float(o["probability"]))
            for c in cards
            for o in ((c.get("market") or {}).get("outcomes") or [])
            if o.get("probability") is not None
        ]
        assert ("Over", 0.5) not in served
        assert ("Under", 0.5) not in served
        # and the surface is still a surface
        assert len(cards) == 1
        assert sorted(served) == [("Over", 0.57), ("Under", 0.43)]

    async def test_a_genuine_coin_flip_still_reaches_the_card(self):
        """The control that decides whether this ship is honest.

        49c bid / 51c ask is a real market that happens to be even. Alex's
        constraint on this ship is explicit: no blanket suppression of 50%.
        """
        tight = _Market(2, "a genuine coin flip",
                        [outcome(0.5, 0.49, 0.51, name="Over", oid=20),
                         outcome(0.5, 0.49, 0.51, name="Under", oid=21)])
        cards = self._cards(await self._serve([tight]))
        assert len(cards) == 1
        served = {
            o["name"]: float(o["probability"])
            for o in (cards[0].get("market") or {}).get("outcomes") or []
        }
        assert served == {"Over": 0.5, "Under": 0.5}


class TestTheRouteActuallyAsks:
    """The clause that stops every test above from being decoration.

    Each one builds its own outcome and calls the helper directly, so all of
    them would go green against a route that never calls it — the guard would be
    vacuous and nothing would say so. The reachability claim has to be made
    against the production call site itself, so this reads `grouped_feed`'s own
    source and pins the three facts the fix consists of: the guard is INSIDE the
    per-outcome loop, it SKIPS rather than annotates, and it runs BEFORE the
    dict that reaches the card is built.
    """

    @staticmethod
    def _loop_body():
        import ast
        import inspect
        import textwrap

        from app.routes import futures as futures_route

        tree = ast.parse(textwrap.dedent(inspect.getsource(futures_route.grouped_feed)))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.For)
                and isinstance(node.target, ast.Name)
                and node.target.id == "o"
                and isinstance(node.iter, ast.Attribute)
                and node.iter.attr == "outcomes"
            ):
                return node
        raise AssertionError("`for o in m.outcomes` is gone from grouped_feed — re-aim this guard")

    def test_the_guard_is_called_inside_the_outcome_loop(self):
        import ast

        called = {
            n.func.id
            for n in ast.walk(self._loop_body())
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "_leg_prices_an_empty_book" in called

    def test_the_guard_skips_the_leg_rather_than_annotating_it(self):
        import ast

        for stmt in self._loop_body().body:
            if not isinstance(stmt, ast.If):
                continue
            calls = {
                n.func.id
                for n in ast.walk(stmt.test)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            }
            if "_leg_prices_an_empty_book" in calls:
                assert any(isinstance(s, ast.Continue) for s in stmt.body), (
                    "the empty-book leg must be skipped; annotating it leaves a "
                    "card printing dashes, which #2710 already ruled against here"
                )
                return
        raise AssertionError("no `if _leg_prices_an_empty_book(...): continue` in the loop")

    def test_the_guard_runs_before_the_card_dict_is_built(self):
        """Order is the fix. A skip after the append is not a skip."""
        import ast

        body = self._loop_body().body
        guard_at = next(
            i for i, s in enumerate(body)
            if isinstance(s, ast.If)
            and "_leg_prices_an_empty_book" in {
                n.func.id for n in ast.walk(s.test)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            }
        )
        dict_at = next(
            i for i, s in enumerate(body)
            if isinstance(s, ast.Assign)
            and any(getattr(t, "id", None) == "o_dict" for t in s.targets)
        )
        assert guard_at < dict_at


class TestTheStripIsStillAStrip:
    """A withholding rule that empties the surface passes every refusal test.

    These are the assertions that make the refusals above mean something.
    """

    def test_a_props_market_keeps_its_real_legs(self):
        """A leg, not a market: the card survives with its priced rows."""
        legs = [
            outcome(0.5, 0.02, 0.97, name="Over", oid=1),
            outcome(0.57, 0.55, 0.59, name="Under", oid=2),
        ]
        kept = [o for o in legs if not _leg_prices_an_empty_book(o)]
        assert [o.name for o in kept] == ["Under"]
        assert _market_has_priced_outcome(
            {"outcomes": [{"probability": o.probability} for o in kept]}
        ) is True

    def test_an_all_phantom_market_loses_its_card_and_not_merely_its_numbers(self):
        """The specimen's own shape: both legs empty-book, so the card goes.

        This is the difference between the fix and a cosmetic one. Nulling the
        numbers would leave a card printing two dashes, which #2710 already
        ruled against on this exact endpoint.
        """
        legs = [outcome(0.5, 0.02, 0.97, name="Over", oid=1),
                outcome(0.5, 0.02, 0.97, name="Under", oid=2)]
        kept = [o for o in legs if not _leg_prices_an_empty_book(o)]
        assert kept == []
        assert _market_has_priced_outcome({"outcomes": []}) is False

    def test_a_pool_of_healthy_markets_is_untouched(self):
        """The refusal must not be the whole strip.

        Twenty markets, one of them phantom: nineteen cards keep every leg.
        #2710's admission gate runs BEFORE the truncation, so the vacated slot
        is backfilled from the rows already loaded — the reader is not shown 19
        cards where 20 were asked for.
        """
        pool = [
            [outcome(0.6, 0.58, 0.62, oid=i), outcome(0.4, 0.38, 0.42, oid=100 + i)]
            for i in range(19)
        ] + [[outcome(0.5, 0.02, 0.97, oid=999), outcome(0.5, 0.02, 0.97, oid=1000)]]

        surviving = [
            [o for o in legs if not _leg_prices_an_empty_book(o)] for legs in pool
        ]
        cards = [
            legs for legs in surviving
            if _market_has_priced_outcome(
                {"outcomes": [{"probability": o.probability} for o in legs]}
            )
        ]
        assert len(cards) == 19
        assert sum(len(legs) for legs in cards) == 38

"""#3721 — a partial Polymarket ladder is not drawn as a complete field.

THE SPECIMEN, read at 2026-09-18 21:00Z. `/events/15312071`, Atlético Madrid v
Real Madrid, two days out. The "1st Half Exact Score" card drew SIX rungs
summing to **41%**:

    Club Atlético de Madrid 1 - 0 Real Madrid CF      10%
    Club Atlético de Madrid 1 - 1 Real Madrid CF       9%
    Club Atlético de Madrid 1 - 2 Real Madrid CF       7%
    Club Atlético de Madrid 0 - 2 Real Madrid CF       7%
    Club Atlético de Madrid 2 - 0 Real Madrid CF       4%
    Club Atlético de Madrid 2 - 1 Real Madrid CF       4%

Polymarket serves NINE legs for that market (Gamma event 1011354, same hour).
Missing: `0 - 0`, `0 - 1`, and `Any Other Score` — the venue's largest rung at
38.5%. The card offered the reader no way to know a row was missing, and the
absent rows are the ones a derby reader would look for first.

WHY WITHHOLDING IS THE FIX RATHER THAN BACKFILLING THE ROWS. Ingest refuses
those prices deliberately: `is_fabricated_midpoint` declines a venue price
sitting exactly on the midpoint of a book wider than 20c (#151 measured ~150K
such rows resolving nowhere near their asserted number). Driving the shipped
ingest functions on that same payload writes THREE legs of nine, so "store them
anyway" would print numbers already proved not to be beliefs, and storing them
unpriced renders `0%` through `mergeOutcomes`. The honest move is Alex's own
rule: if a number cannot be shown honestly, leave the space empty.

Every control below is a row class that MUST survive, because the failure this
guard could cause — stripping ordinary cards whose `market_count` counts a
parent's siblings — is worse than the defect it fixes.
"""

from types import SimpleNamespace

import pytest

from app.routes.events import _withhold_partial_field_markets


def _market(market_id, name, *, declared=None, event_title=None, mex=True):
    """A futures market as the route sees it: id, name, mex flag, metadata."""
    meta = {}
    if event_title is not None:
        meta["event_title"] = event_title
    if declared is not None:
        meta["market_count"] = declared
    return SimpleNamespace(
        id=market_id,
        name=name,
        mutually_exclusive=mex,
        market_metadata=meta,
    )


def _rows(market_id, names):
    return [{"market_name": "m", "outcome_name": n, "_market_id": market_id} for n in names]


DERBY = "Club Atlético de Madrid vs. Real Madrid CF - 1st Half Exact Score"
DERBY_HELD = [
    "Club Atlético de Madrid 1 - 0 Real Madrid CF",
    "Club Atlético de Madrid 1 - 1 Real Madrid CF",
    "Club Atlético de Madrid 1 - 2 Real Madrid CF",
    "Club Atlético de Madrid 0 - 2 Real Madrid CF",
    "Club Atlético de Madrid 2 - 0 Real Madrid CF",
    "Club Atlético de Madrid 2 - 1 Real Madrid CF",
]


class TestTheNamedCardStopsClaimingAField:
    def test_the_derby_six_of_nine_card_is_withheld_whole(self):
        """The live defect: six rungs of nine leave the page together."""
        rows = _rows(60856911, DERBY_HELD)
        markets = [_market(60856911, DERBY, declared=9, event_title=DERBY)]

        assert _withhold_partial_field_markets(rows, markets) == []

    def test_a_partial_card_does_not_take_its_neighbours_with_it(self):
        """Only the short market's rows go; the rest of the page is untouched."""
        rows = _rows(60856911, DERBY_HELD) + _rows(
            60481417, ["Real Madrid", "Atletico", "Tie"]
        )
        markets = [
            _market(60856911, DERBY, declared=9, event_title=DERBY),
            _market(
                60481417,
                "Atletico vs Real Madrid",
                declared=3,
                event_title="Atletico vs Real Madrid",
            ),
        ]

        survivors = _withhold_partial_field_markets(rows, markets)

        assert [r["_market_id"] for r in survivors] == [60481417] * 3

    def test_one_missing_leg_is_still_a_missing_leg(self):
        """No tolerance band: 8 of 9 is not the field either."""
        rows = _rows(1, [f"leg{i}" for i in range(8)])
        markets = [_market(1, "Ladder", declared=9, event_title="Ladder")]

        assert _withhold_partial_field_markets(rows, markets) == []


class TestTheCardsThatMustSurvive:
    """Each of these is a way the guard could over-reach. None may fire."""

    def test_a_complete_field_is_kept(self):
        rows = _rows(60481417, ["Real Madrid", "Atletico", "Tie"])
        markets = [
            _market(
                60481417,
                "Atletico vs Real Madrid",
                declared=3,
                event_title="Atletico vs Real Madrid",
            )
        ]

        assert _withhold_partial_field_markets(rows, markets) == rows

    def test_a_sub_market_counting_its_parents_siblings_is_kept(self):
        """🪤 THE TRAP THIS GUARD IS SHAPED AROUND.

        A game's moneyline is ONE sub-market of a venue event carrying forty of
        them, so its `market_count` is 40 while it holds two outcomes. Judged on
        that number every ordinary Yes/No pair on the site would be withheld.
        The `event_title == name` scoping is what refuses, and this is the test
        that fails the moment someone widens it.
        """
        rows = _rows(777, ["Atletico", "Real Madrid"])
        markets = [
            _market(
                777,
                "Atletico vs Real Madrid - Moneyline",
                declared=40,
                event_title="Atletico vs Real Madrid",
            )
        ]

        assert _withhold_partial_field_markets(rows, markets) == rows

    def test_a_market_that_is_not_a_partition_is_kept(self):
        """Player props hold one leg of eighteen and claim no field at all."""
        rows = _rows(61285021, ["Goalscorer: Vinicius Junior"])
        markets = [
            _market(
                61285021,
                "Club Atlético de Madrid vs. Real Madrid CF - Player Props",
                declared=18,
                event_title="Club Atlético de Madrid vs. Real Madrid CF - Player Props",
                mex=False,
            )
        ]

        assert _withhold_partial_field_markets(rows, markets) == rows

    @pytest.mark.parametrize(
        "declared,event_title",
        [
            (None, DERBY),  # venue count absent
            ("", DERBY),  # venue count unparseable
            ("nine", DERBY),  # venue count not a number
            (0, DERBY),  # venue count nonsensical
            (9, None),  # cannot prove this row IS the ladder
            (9, "Some other event"),  # names a different venue event
        ],
    )
    def test_an_unprovable_field_is_kept(self, declared, event_title):
        """The predicate refuses far more often than it answers, and a refusal
        serves the card. Fail open: a removal must never rest on a guess."""
        rows = _rows(60856911, DERBY_HELD)
        markets = [
            _market(60856911, DERBY, declared=declared, event_title=event_title)
        ]

        assert _withhold_partial_field_markets(rows, markets) == rows

    def test_a_row_with_no_market_id_is_passed_through(self):
        rows = [{"outcome_name": "orphan"}]

        assert _withhold_partial_field_markets(rows, []) == rows

    def test_a_market_with_no_metadata_is_kept(self):
        rows = _rows(5, ["a", "b"])
        markets = [SimpleNamespace(id=5, name="x", mutually_exclusive=True, market_metadata=None)]

        assert _withhold_partial_field_markets(rows, markets) == rows

    def test_a_merged_row_survives_unless_every_market_behind_it_is_short(self):
        """Step 9b merges two venues into one row. Half a merged row is not a
        thing we can serve, so it leaves only when both parents are short.

        The derby's own six rows are here on purpose: without a row naming ONE
        market, nothing is ever judged and this test would pass through the
        early return while asserting nothing about merging.
        """
        merged = {"outcome_name": "merged", "_market_ids": [60856911, 60481417]}
        rows = _rows(60856911, DERBY_HELD) + [merged]
        markets = [
            _market(60856911, DERBY, declared=9, event_title=DERBY),
            _market(
                60481417,
                "Atletico vs Real Madrid",
                declared=3,
                event_title="Atletico vs Real Madrid",
            ),
        ]

        survivors = _withhold_partial_field_markets(rows, markets)

        assert survivors == [merged]

    def test_a_merged_row_is_not_judged_on_a_parent_the_page_never_rendered(self):
        """One parent is short and on the page; the other is absent from it
        entirely, so nothing is known about the legs it would have shown. A
        removal may not rest on that silence."""
        merged = {"outcome_name": "merged", "_market_ids": [60856911, 99999]}
        rows = _rows(60856911, DERBY_HELD) + [merged]
        markets = [
            _market(60856911, DERBY, declared=9, event_title=DERBY),
            _market(99999, "Absent ladder", declared=4, event_title="Absent ladder"),
        ]

        assert _withhold_partial_field_markets(rows, markets) == [merged]

    def test_a_market_the_page_never_rendered_is_not_consulted(self):
        """A short market with no rows on the page cannot remove anyone else's."""
        rows = _rows(60481417, ["Real Madrid", "Atletico", "Tie"])
        markets = [
            _market(60856911, DERBY, declared=9, event_title=DERBY),
            _market(
                60481417,
                "Atletico vs Real Madrid",
                declared=3,
                event_title="Atletico vs Real Madrid",
            ),
        ]

        assert _withhold_partial_field_markets(rows, markets) == rows


class TestServeAndStampAskTheSameQuestion:
    def test_the_route_and_the_classifier_share_one_predicate(self):
        """Two copies of the scoping rule would drift, and then the page and the
        `shape.exhaustive` stamp would disagree about which markets are ladders.
        """
        import importlib

        from app.utils import market_shape

        # `from app.tasks import backfill_market_shapes` resolves to the CELERY
        # TASK of that name, not the module — import it by path.
        task_module = importlib.import_module("app.tasks.backfill_market_shapes")

        assert task_module._venue_leg_count is market_shape.venue_leg_count

    def test_the_route_does_not_restate_the_scoping_rule(self):
        import inspect

        from app.routes import events

        body = inspect.getsource(events._withhold_partial_field_markets)

        assert "venue_leg_count" in body
        assert "event_title" not in body.split('"""')[-1]

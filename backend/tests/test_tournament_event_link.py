"""Which `events` row a registered matchup is — and every way it refuses (UX-P152).

The whole architectural claim of this queue is that a tournament is a container
for ordinary events, so a match card routes to `/events/{id}` like any other
game card.  That claim rests entirely on the link being right, and a link to the
WRONG match is worse than no link: it puts two real players' names over a third
match's numbers on a page whose entire posture is that identity is pinned.

So what is pinned here is the refusal table, not the happy path.  Every one of
these is a case where a name-and-date matcher would have produced a plausible
answer and this module produces none.
"""

from __future__ import annotations

import pytest

from app.utils.tournament_advancement import (
    build_advancement,
    is_monotonic,
    stage_label,
)
from app.utils.tournament_event_link import (
    UNRESOLVED_REASONS,
    _resolve_one,
    pinned_market_ids,
)


def matchup(key="mens-singles:a-vs-b:2026-08-30", *, sources=None, **extra):
    base = {
        "matchup_key": key,
        "draw": "mens-singles",
        "round": "R128",
        "players": ["player-a", "player-b"],
        "sources": sources if sources is not None else [],
    }
    base.update(extra)
    return base


def live(market_id, *, source="kalshi", kind="match"):
    return {
        "source": source,
        "kind": kind,
        "status": "live",
        "market_id": market_id,
        "outcome_id": 1,
    }


def missing(source="kalshi"):
    return {"source": source, "kind": "match", "status": "missing", "market_id": None}


class TestPinnedMarketIds:
    def test_a_missing_block_pins_nothing(self):
        """The committed register's 96 R128 blocks are all `missing`.

        They must contribute nothing rather than a `None` the caller filters —
        the distinction between "no market" and "a market whose id is null" is
        the one this whole module exists to keep.
        """
        assert pinned_market_ids(matchup(sources=[missing(), missing("polymarket")])) == []

    def test_a_bool_is_not_a_market_id(self):
        """`True` is an `int` in Python and would index row 1 of the table."""
        assert pinned_market_ids(matchup(sources=[live(True)])) == []

    def test_a_non_match_block_is_not_the_match_winner_market(self):
        """Only the match-winner market's `event_id` answers 'which event is this'."""
        assert pinned_market_ids(matchup(sources=[live(7, kind="total_games")])) == []

    def test_both_sources_contribute(self):
        assert sorted(
            pinned_market_ids(matchup(sources=[live(7), live(9, source="polymarket")]))
        ) == [7, 9]


class TestResolveOne:
    def test_no_pinned_market(self):
        assert _resolve_one(matchup(sources=[missing()]), {}) == (
            None,
            "NO_PINNED_MARKET",
        )

    def test_market_not_found(self):
        """A pinned id with no row is a register finding, not something to route around."""
        assert _resolve_one(matchup(sources=[live(7)]), {}) == (None, "MARKET_NOT_FOUND")

    def test_market_unlinked(self):
        """The matching layer has not claimed it. This module does not get to guess.

        This is the real state of all 28 registered QUALIFYING matchups today:
        their Polymarket markets exist and carry no `event_id`, because the
        qualifying draw was never ingested as events.
        """
        assert _resolve_one(matchup(sources=[live(7)]), {7: None}) == (
            None,
            "MARKET_UNLINKED",
        )

    def test_resolves_through_the_market(self):
        assert _resolve_one(matchup(sources=[live(7)]), {7: 15293845}) == (15293845, None)

    def test_two_pinned_markets_agreeing_is_one_answer(self):
        assert _resolve_one(
            matchup(sources=[live(7), live(9, source="polymarket")]),
            {7: 15293845, 9: 15293845},
        ) == (15293845, None)

    def test_two_pinned_markets_disagreeing_resolves_to_NOTHING(self):
        """THE CASE A NAME MATCHER WOULD GET 'RIGHT' AND BE WRONG ABOUT.

        Kalshi says this fixture is event 100 and Polymarket says 200. A matcher
        with two player names and a date would pick whichever scored higher and
        look correct. If the ids disagree we do not know, and the honest output
        is no link plus a counted finding.
        """
        assert _resolve_one(
            matchup(sources=[live(7), live(9, source="polymarket")]),
            {7: 100, 9: 200},
        ) == (None, "EVENT_DISAGREEMENT")

    def test_one_unlinked_sibling_does_not_veto_a_linked_one(self):
        """A source that has not been claimed is silence, not a contradiction."""
        assert _resolve_one(
            matchup(sources=[live(7), live(9, source="polymarket")]),
            {7: 100, 9: None},
        ) == (100, None)

    def test_a_register_pin_outranks_the_dereference(self):
        """A human wrote it down against the evidence. There is nothing to resolve."""
        assert _resolve_one(
            matchup(sources=[live(7)], event_id=999), {7: 100}
        ) == (999, None)

    def test_every_refusal_is_a_named_reason(self):
        for _, reason in (
            _resolve_one(matchup(sources=[missing()]), {}),
            _resolve_one(matchup(sources=[live(7)]), {}),
            _resolve_one(matchup(sources=[live(7)]), {7: None}),
            _resolve_one(
                matchup(sources=[live(7), live(9, source="polymarket")]),
                {7: 1, 9: 2},
            ),
        ):
            assert reason in UNRESOLVED_REASONS


class TestStageLabel:
    @pytest.mark.parametrize(
        "long_label,expected",
        [
            ("To reach the round of 16", "Round of 16"),
            ("To reach the quarter-finals", "Quarter-finals"),
            ("To win the title", "Title"),
        ],
    )
    def test_the_destination_without_the_preamble(self, long_label, expected):
        """One heading, then a list of destinations — not "To reach the" five times."""
        assert stage_label({"key": "x", "long_label": long_label}) == expected

    def test_falls_back_to_the_short_label_then_the_key(self):
        assert stage_label({"key": "QF", "short_label": "QF"}) == "QF"
        assert stage_label({"key": "QF"}) == "QF"


class TestMonotonicity:
    def test_a_falling_ladder_is_coherent(self):
        assert is_monotonic(
            [{"probability": p} for p in (0.31, 0.105, 0.06, 0.02, 0.008)]
        )

    def test_likelier_to_reach_the_final_than_the_semis_is_not(self):
        """Measured on the live register: J.J. Wolf, SF 2.45% under F 3.6%.

        The market's own incoherence, reported and not corrected — but SAID, at
        a magnification where two of five large rows contradicting each other
        would otherwise read as our arithmetic.
        """
        assert not is_monotonic(
            [{"probability": p} for p in (0.055, 0.046, 0.0245, 0.036)]
        )

    def test_unpriced_cells_do_not_break_the_chain(self):
        """A gap is a question nobody asked, not a fall to zero and back."""
        assert is_monotonic(
            [{"probability": 0.31}, {"probability": None}, {"probability": 0.1}]
        )


GRID = {
    "mens-singles": {
        "draw": "mens-singles",
        "label": "Men's Singles",
        "columns": [
            {"key": "R16", "short_label": "R16", "long_label": "To reach the round of 16"},
            {"key": "title", "short_label": "Title", "long_label": "To win the title"},
        ],
        "rows": [
            {
                "entity_key": "player-a",
                "display_name": "Alexander Bublik",
                "seed": 23,
                "cells": {
                    "R16": {
                        "probability": 0.31,
                        "sources": [
                            {"source": "kalshi", "probability": 0.31},
                            {"source": "polymarket", "probability": None},
                        ],
                    },
                    "title": {"probability": 0.008, "sources": []},
                },
            },
            {
                "entity_key": "player-b",
                "display_name": "J.J. Wolf",
                "cells": {"R16": {"probability": 0.055, "sources": []},
                          "title": {"probability": None, "sources": []}},
            },
        ],
    }
}


class TestBuildAdvancement:
    def test_reads_the_hub_grid_so_the_two_surfaces_cannot_disagree(self):
        out = build_advancement(
            GRID,
            matchup=matchup(),
            event_id=42,
            home_team_name="Alexander Bublik",
            away_team_name="JJ Wolf",
            tournament_title="US Open 2026",
            tournament_slug="us-open",
        )
        assert out is not None
        assert out["home_team"]["name"] == "Alexander Bublik"
        assert out["away_team"]["name"] == "J.J. Wolf"
        assert out["side_order"] == "event"
        assert [s["label"] for s in out["home_team"]["stages"]] == [
            "Round of 16",
            "Title",
        ]

    def test_a_source_that_is_not_quoting_is_not_a_source_of_this_number(self):
        """The grid lists every registered source, priced or not.

        Passing an unpriced one through would draw a dot for a supplier that
        said nothing.
        """
        out = build_advancement(
            GRID, matchup=matchup(), event_id=42,
            home_team_name="Alexander Bublik", away_team_name="JJ Wolf",
        )
        r16 = out["home_team"]["stages"][0]
        assert [s["source"] for s in r16["sources"]] == ["kalshi"]

    def test_the_seed_rides_the_record_slot(self):
        out = build_advancement(
            GRID, matchup=matchup(), event_id=42,
            home_team_name="Alexander Bublik", away_team_name="JJ Wolf",
        )
        assert out["home_team"]["record"] == "Seed 23"
        assert out["away_team"]["record"] is None

    def test_never_invents_a_24h_move(self):
        """The register pins a reading, not a history.

        A 0 here would print "no change" about a number nobody measured twice.
        """
        out = build_advancement(
            GRID, matchup=matchup(), event_id=42,
            home_team_name="A", away_team_name="B",
        )
        assert all(
            s["trend_24h"] is None
            for row in (out["home_team"], out["away_team"])
            for s in row["stages"]
        )

    def test_a_player_with_no_priced_cell_is_None_not_an_empty_card(self):
        grid = {"mens-singles": {**GRID["mens-singles"], "rows": [
            {"entity_key": "player-a", "display_name": "A",
             "cells": {"R16": {"probability": 0.3}, "title": {}}},
            {"entity_key": "player-b", "display_name": "B",
             "cells": {"R16": {}, "title": {}}},
        ]}}
        out = build_advancement(
            grid, matchup=matchup(), event_id=42,
            home_team_name="A", away_team_name="B",
        )
        assert out["home_team"] is not None
        assert out["away_team"] is None

    def test_NEITHER_side_quoted_is_no_section_at_all(self):
        """26 of 96 R128 fixtures. Two empty columns promise something absent."""
        grid = {"mens-singles": {**GRID["mens-singles"], "rows": []}}
        assert build_advancement(
            grid, matchup=matchup(), event_id=42,
            home_team_name="A", away_team_name="B",
        ) is None

    def test_a_non_decisive_name_comparison_keeps_the_register_order(self):
        """Ordering is not identity — and each card prints its own name.

        The worst case here is two correctly-labelled cards in the other order.
        It must not become a guess, and it must be reported as what it was.
        """
        out = build_advancement(
            GRID, matchup=matchup(), event_id=42,
            home_team_name="Somebody Else", away_team_name="Nobody At All",
        )
        assert out["side_order"] == "register"
        assert out["home_team"]["name"] == "Alexander Bublik"

    def test_the_event_row_can_reverse_the_register_order(self):
        out = build_advancement(
            GRID, matchup=matchup(), event_id=42,
            home_team_name="JJ Wolf", away_team_name="Alexander Bublik",
        )
        assert out["side_order"] == "event"
        assert out["home_team"]["name"] == "J.J. Wolf"

    def test_the_incoherence_verdict_rides_the_row(self):
        grid = {"mens-singles": {**GRID["mens-singles"], "rows": [
            {"entity_key": "player-a", "display_name": "A",
             "cells": {"R16": {"probability": 0.02}, "title": {"probability": 0.04}}},
        ]}}
        out = build_advancement(
            grid, matchup=matchup(), event_id=42,
            home_team_name="A", away_team_name="B",
        )
        assert out["home_team"]["monotonic"] is False

    def test_a_draw_with_no_grid_yields_nothing(self):
        assert build_advancement(
            {}, matchup=matchup(), event_id=42,
            home_team_name="A", away_team_name="B",
        ) is None

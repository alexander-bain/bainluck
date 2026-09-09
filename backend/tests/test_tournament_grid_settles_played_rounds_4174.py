"""#4174 — the grid stops forecasting rounds the tournament has already played.

THE SPECIMEN, measured off production 2026-09-09 09:52Z (quarter-final morning):

    men's singles   column   sum    slots   ratio    verdict
                    R16      23.48    16     1.47    over
                    QF        5.00     8     0.63    under
                    SF        8.55     4     2.14    over
                    Final     4.93     2     2.46    over
                    Title     1.16     1     1.16    over

Ten of ten columns out, on both draws, and two monotonicity breaks — Alcaraz
served likelier to win the title than to reach the final.  The cause was not a
blend disagreement.  Fourteen of the Final column's contributors were **already
out of the tournament** and were still being published at their pre-elimination
number, and the Title column's whole 0.16 of overround was seventeen eliminated
men carrying a 1% outright each.

The fix is one sentence: **a played round is a result, not a forecast.**  These
tests hold that sentence to its two halves — what a settled cell must and must
not carry, and what the sum check must compare against once places have been
won — and to the rule that keeps it safe: only a match we hold settles a cell.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.tournament_grid import (
    CELL_LIVE,
    CELL_NO_MARKET,
    CELL_SETTLED,
    SETTLED_OUT,
    SETTLED_REACHED,
    build_playoff_grid,
    evaluate_column_sums,
    evaluate_monotonicity,
)
from app.utils.tournament_progress import (
    VERDICT_OUT,
    VERDICT_REACHED,
    DrawProgress,
    build_progress,
)

NOW = datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)
DRAW = "mens-singles"
SIZES = {DRAW: 128}


def _match(round_name, a, b, *, winner=None, completion="final", draw=DRAW):
    return {
        "draw": draw,
        "round": round_name,
        "source_round": round_name,
        "completion": completion,
        "winner_entity_key": winner,
        "players": [
            {"entity_key": a, "is_winner": a == winner},
            {"entity_key": b, "is_winner": b == winner},
        ],
    }


# ---------------------------------------------------------------------------
# WHAT A MATCH PROVES — and, more importantly, what it does not
# ---------------------------------------------------------------------------

class TestOnlyAMatchWeHoldSettlesACell:
    def test_a_finished_match_reaches_both_and_eliminates_the_loser(self):
        [(_, prog)] = build_progress(
            [_match("Round 4", "alcaraz", "rune", winner="alcaraz")],
            draw_sizes=SIZES,
        ).items()
        assert prog.verdict("alcaraz", "R16") == VERDICT_REACHED
        assert prog.verdict("rune", "R16") == VERDICT_REACHED
        # The winner is admitted to the next round without playing it.
        assert prog.verdict("alcaraz", "QF") == VERDICT_REACHED
        assert prog.verdict("rune", "QF") == VERDICT_OUT
        assert prog.eliminated == {"rune": "R16"}

    def test_a_match_still_in_progress_eliminates_nobody(self):
        """Being in a match that has not finished is not losing it."""
        prog = build_progress(
            [_match("Quarterfinal", "zverev", "blockx", completion="in_progress")],
            draw_sizes=SIZES,
        )[DRAW]
        assert prog.verdict("zverev", "QF") == VERDICT_REACHED
        assert prog.verdict("blockx", "QF") == VERDICT_REACHED
        # Neither is out, and neither has reached the semi-final.
        assert prog.verdict("zverev", "SF") is None
        assert prog.verdict("blockx", "SF") is None
        assert prog.eliminated == {}
        assert prog.decided_matches == 0

    def test_a_retirement_and_a_walkover_both_decide(self):
        prog = build_progress(
            [
                _match("Round 3", "a", "b", winner="a", completion="retired"),
                _match("Round 3", "c", "d", winner="c", completion="walkover"),
            ],
            draw_sizes=SIZES,
        )[DRAW]
        assert prog.eliminated == {"b": "R32", "d": "R32"}
        assert prog.verdict("a", "R16") == VERDICT_REACHED

    def test_a_player_no_result_mentions_is_never_settled(self):
        """THE UNDER-CLAIM RULE, and the reason it is not negotiable.

        Our results join drops a match whose two names do not both resolve to
        registered players — 147 of 467 scored on the specimen day — so "we
        hold no match for this player" is a statement about US, never about the
        draw.  Guessing them out would erase a live player from the grid, which
        is worse than the defect being fixed.
        """
        prog = build_progress(
            [_match("Round 4", "alcaraz", "rune", winner="alcaraz")],
            draw_sizes=SIZES,
        )[DRAW]
        assert prog.verdict("sinner", "R16") is None
        assert prog.verdict("sinner", "F") is None
        assert prog.title_verdict("sinner") is None

    def test_an_eliminated_player_keeps_the_rounds_they_did_reach(self):
        prog = build_progress(
            [
                _match("Round 4", "tiafoe", "korda", winner="tiafoe"),
                _match("Quarterfinal", "tiafoe", "shelton", winner="shelton"),
            ],
            draw_sizes=SIZES,
        )[DRAW]
        assert prog.verdict("tiafoe", "R16") == VERDICT_REACHED
        assert prog.verdict("tiafoe", "QF") == VERDICT_REACHED
        assert prog.verdict("tiafoe", "SF") == VERDICT_OUT

    def test_the_final_crowns_a_champion_and_nothing_else_does(self):
        prog = build_progress(
            [_match("Final", "zverev", "shelton", winner="zverev")],
            draw_sizes=SIZES,
        )[DRAW]
        assert prog.champion == "zverev"
        assert prog.title_verdict("zverev") == VERDICT_REACHED
        assert prog.title_verdict("shelton") == VERDICT_OUT
        assert prog.open_slots("title", 1) == 0

        semi_only = build_progress(
            [_match("Semifinal", "zverev", "tiafoe", winner="zverev")],
            draw_sizes=SIZES,
        )[DRAW]
        assert semi_only.champion is None
        assert semi_only.open_slots("title", 1) == 1

    def test_a_round_that_cannot_be_named_settles_nothing(self):
        """"Round 2" is R64 in a slam and R32 in a 64-draw — no size, no round.

        Filing a match under the wrong round would settle the wrong column,
        which is the wrong-question defect the register exists to refuse.
        """
        assert build_progress([_match("Round 2", "a", "b", winner="a")], draw_sizes={}) == {}
        assert (
            build_progress([_match("Zeroth Round", "a", "b", winner="a")], draw_sizes=SIZES)
            == {}
        )
        # A register-vocabulary round needs no size at all.
        prog = build_progress([_match("R64", "a", "b", winner="a")], draw_sizes={})[DRAW]
        assert prog.verdict("b", "R64") == VERDICT_REACHED
        assert prog.verdict("b", "R32") == VERDICT_OUT

    def test_reached_counts_are_the_whole_field_and_imply_the_earlier_rounds(self):
        """The sum check's denominator is a fact about the ROUND, not the grid."""
        prog = build_progress(
            [
                _match("Round 4", "a", "b", winner="a"),
                _match("Round 4", "c", "d", winner="c"),
                _match("Quarterfinal", "a", "c", winner="a"),
            ],
            draw_sizes=SIZES,
        )[DRAW]
        assert prog.reached_counts["R16"] == 4
        assert prog.reached_counts["QF"] == 2
        assert prog.reached_counts["SF"] == 1
        # Reaching the round of 16 means having reached every round before it.
        assert prog.reached_counts["R128"] == 4
        assert prog.open_slots("R16", 16) == 12
        assert prog.open_slots("SF", 4) == 3


# ---------------------------------------------------------------------------
# THE CELL: A RESULT, WITH NO PROBABILITY BESIDE IT
# ---------------------------------------------------------------------------

def _reach_block(entity_key, round_name, outcome_id):
    return {
        "draw": DRAW,
        "entity_key": entity_key,
        "round": round_name,
        "sources": [{
            "source": "polymarket",
            "kind": "reach",
            "market_id": outcome_id,
            "outcome_id": outcome_id,
            "market_external_id": f"0x{outcome_id:04x}",
            "status": "live",
            "evidence": {"observed_at": NOW.isoformat()},
        }],
    }


def _register(reaches, players):
    return {
        "schema_version": "tournament-register/v1",
        "tournament": "us-open",
        "season": "2026",
        "version": 1,
        "generated_at": NOW.isoformat(),
        "draw_released": True,
        "players": players,
        "matchups": [],
        "reaches": reaches,
    }


def _player(entity_key, display_name):
    return {
        "entity_key": entity_key,
        "display_name": display_name,
        "draw": DRAW,
        "role": "contender",
        "sources": [],
    }


#: The specimen, in miniature. ``zheng`` is Michael Zheng, who was knocked out
#: in the second round and was still being served at 52% to reach the final.
SPECIMEN_REGISTER = _register(
    reaches=[
        _reach_block("zverev", "SF", 1),
        _reach_block("zverev", "F", 2),
        _reach_block("zheng", "SF", 3),
        _reach_block("zheng", "F", 4),
    ],
    players=[_player("zverev", "Alexander Zverev"), _player("zheng", "Michael Zheng")],
)

SPECIMEN_PRICES = {
    1: {"probability": 0.90, "observed_at": NOW},
    2: {"probability": 0.715, "observed_at": NOW},
    3: {"probability": 0.055, "observed_at": NOW},
    4: {"probability": 0.52, "observed_at": NOW},
}

SPECIMEN_BOARD = [
    {"entity_key": "zverev", "display_name": "Alexander Zverev", "seed": 1, "rank": 1,
     "state": "live", "probability": 0.44, "price_state": "live", "age_hours": 0.1,
     "sources": []},
    {"entity_key": "zheng", "display_name": "Michael Zheng", "seed": None, "rank": 2,
     "state": "live", "probability": 0.01, "price_state": "live", "age_hours": 0.1,
     "sources": []},
]

#: Zverev has won his quarter-final and is into the semi; Zheng lost in the
#: second round and was still being served at 52% to reach the final.
SPECIMEN_PROGRESS = build_progress(
    [
        _match("Round 2", "zheng", "opponent", winner="opponent"),
        _match("Quarterfinal", "zverev", "someone", winner="zverev"),
    ],
    draw_sizes=SIZES,
)[DRAW]


def _grid(progress):
    return build_playoff_grid(
        SPECIMEN_REGISTER,
        board_rows=SPECIMEN_BOARD,
        prices=SPECIMEN_PRICES,
        draw=DRAW,
        now=NOW,
        progress=progress,
    )


def _cell_of(grid, entity_key, column):
    [row] = [r for r in grid["rows"] if r["entity_key"] == entity_key]
    return row["cells"][column]


class TestASettledCellPublishesNoProbability:
    def test_the_specimen_reaches_the_settling_branch(self):
        """Reachability first: the unfixed build really does serve the defect."""
        before = _grid(None)
        assert _cell_of(before, "zheng", "F")["probability"] == 0.52
        assert _cell_of(before, "zheng", "F")["state"] == CELL_LIVE
        assert _cell_of(before, "zheng", "title")["probability"] == 0.01

    def test_an_eliminated_player_is_out_with_no_number_beside_it(self):
        cell = _cell_of(_grid(SPECIMEN_PROGRESS), "zheng", "F")
        assert cell["state"] == CELL_SETTLED
        assert cell["note"] == SETTLED_OUT
        assert cell["probability"] is None
        assert cell["probability_is_live"] is False

    def test_the_eliminated_players_title_cell_stops_carrying_the_board_quote(self):
        """Seventeen 1% outrights were the Title column's whole overround."""
        cell = _cell_of(_grid(SPECIMEN_PROGRESS), "zheng", "title")
        assert cell["state"] == CELL_SETTLED
        assert cell["note"] == SETTLED_OUT
        assert cell["probability"] is None

    def test_a_reached_round_reads_as_reached_and_not_as_a_forecast(self):
        cell = _cell_of(_grid(SPECIMEN_PROGRESS), "zverev", "SF")
        assert cell["state"] == CELL_SETTLED
        assert cell["note"] == SETTLED_REACHED
        assert cell["probability"] is None

    def test_a_dash_says_where_the_player_went_out(self):
        assert _cell_of(_grid(SPECIMEN_PROGRESS), "zheng", "F")["settled_round"] == "R64"
        assert _cell_of(_grid(SPECIMEN_PROGRESS), "zheng", "title")["settled_round"] == "R64"

    def test_an_open_question_keeps_its_price(self):
        """Zverev's final is still to be played, so it is still a number."""
        cell = _cell_of(_grid(SPECIMEN_PROGRESS), "zverev", "F")
        assert cell["state"] == CELL_LIVE
        assert cell["probability"] == 0.715

    def test_a_settled_cell_is_never_an_alarm(self):
        grid = _grid(SPECIMEN_PROGRESS)
        assert grid["alarm_cells"] == 0
        assert grid["settled_cells"] == 4
        assert grid["decided_matches"] == 2
        assert sum(grid["counts"].values()) == grid["total_cells"]

    def test_with_no_results_the_grid_is_exactly_what_it_was(self):
        """A cold results cache degrades to the old behaviour, not to an empty grid."""
        for empty in (None, DrawProgress()):
            grid = _grid(empty)
            assert _cell_of(grid, "zheng", "F")["probability"] == 0.52
            assert grid["settled_cells"] == 0
            assert grid["decided_matches"] == 0

    def test_no_row_is_dropped_and_no_cell_is_blank(self):
        grid = _grid(SPECIMEN_PROGRESS)
        assert len(grid["rows"]) == 2
        for row in grid["rows"]:
            for cell in row["cells"].values():
                assert cell["state"], row


# ---------------------------------------------------------------------------
# THE SUM CHECK: AGAINST THE PLACES THAT ARE STILL TO BE WON
# ---------------------------------------------------------------------------

class TestTheDenominatorIsWhatIsStillOpen:
    def test_the_specimen_column_becomes_coherent(self):
        """Final: 2.46x before, and the whole excess was players who were out."""
        columns = [{"key": "F", "short_label": "Final"}]
        rows = [
            {"entity_key": "zverev", "display_name": "Z",
             "cells": {"F": {"probability": 0.715, "state": CELL_LIVE}}},
            {"entity_key": "shelton", "display_name": "S",
             "cells": {"F": {"probability": 0.62, "state": CELL_LIVE}}},
            {"entity_key": "tiafoe", "display_name": "T",
             "cells": {"F": {"probability": 0.62, "state": CELL_LIVE}}},
        ] + [
            {"entity_key": f"out{i}", "display_name": f"O{i}",
             "cells": {"F": {"probability": None, "state": CELL_SETTLED}}}
            for i in range(14)
        ]
        [check] = evaluate_column_sums(columns, rows, progress=DrawProgress())
        assert check["sum"] == 1.955
        assert check["expected"] == 2
        assert check["verdict"] == "pass"
        assert check["decided_rows"] == 14
        assert check["priced_rows"] == 3

    def test_a_round_with_every_place_taken_is_settled_not_failed(self):
        """The QF column read 0.63 on a morning when all eight were known."""
        columns = [{"key": "QF", "short_label": "QF"}]
        rows = [{"entity_key": "p", "display_name": "P",
                 "cells": {"QF": {"probability": None, "state": CELL_SETTLED}}}]
        progress = DrawProgress(reached_counts={"QF": 8})
        [check] = evaluate_column_sums(columns, rows, progress=progress)
        assert check["expected"] == 0
        assert check["slots"] == 8
        assert check["verdict"] == "settled"

    def test_half_a_round_won_halves_the_target(self):
        columns = [{"key": "SF", "short_label": "SF"}]
        rows = [
            {"entity_key": "a", "display_name": "A",
             "cells": {"SF": {"probability": 0.9, "state": CELL_LIVE}}},
            {"entity_key": "b", "display_name": "B",
             "cells": {"SF": {"probability": 1.1, "state": CELL_LIVE}}},
        ]
        [check] = evaluate_column_sums(
            columns, rows, progress=DrawProgress(reached_counts={"SF": 2})
        )
        assert check["expected"] == 2
        assert check["slots"] == 4
        assert check["verdict"] == "pass"

    def test_it_still_never_rescales(self):
        columns = [{"key": "F", "short_label": "Final"}]
        rows = [
            {"entity_key": f"p{i}", "display_name": f"P{i}",
             "cells": {"F": {"probability": 0.7, "state": CELL_LIVE}}}
            for i in range(4)
        ]
        [check] = evaluate_column_sums(columns, rows, progress=DrawProgress())
        assert check["verdict"] == "over"
        assert check["sum"] == 2.8
        assert rows[0]["cells"]["F"]["probability"] == 0.7

    def test_coverage_and_decision_are_counted_apart(self):
        """An `under` from a missing market and one from a finished round are
        two different sentences, so they are two different counters."""
        columns = [{"key": "SF", "short_label": "SF"}]
        rows = [
            {"entity_key": "priced", "display_name": "P",
             "cells": {"SF": {"probability": 0.5, "state": CELL_LIVE}}},
            {"entity_key": "settled", "display_name": "S",
             "cells": {"SF": {"probability": None, "state": CELL_SETTLED}}},
            {"entity_key": "nomarket", "display_name": "N",
             "cells": {"SF": {"probability": None, "state": CELL_NO_MARKET}}},
        ]
        [check] = evaluate_column_sums(
            columns, rows, progress=DrawProgress(reached_counts={"SF": 1})
        )
        assert check["priced_rows"] == 1
        assert check["decided_rows"] == 1
        assert check["uncovered_rows"] == 1
        assert check["total_rows"] == 3

    def test_the_unfixed_call_shape_is_unchanged(self):
        """Two positional arguments, no progress: the pre-#4174 behaviour."""
        columns = [{"key": "SF", "short_label": "SF"}]
        rows = [{"entity_key": f"p{i}", "cells": {"SF": {"probability": 0.5}}}
                for i in range(8)]
        [check] = evaluate_column_sums(columns, rows)
        assert check["expected"] == 4
        assert check["verdict"] == "pass"


class TestMonotonicityStopsAccusingDeadPlayers:
    def test_the_production_violation_disappears(self):
        """Alcaraz: F 0.0, title 0.00525 — a player who was already out.

        Both draws' only remaining violation on the specimen day was of this
        shape: an eliminated player whose two dead quotes disagreed by half a
        point.  Settling the row removes the accusation without touching the
        eval's own rule.
        """
        columns = [{"key": k, "short_label": k} for k in ("F", "title")]
        before = [{
            "entity_key": "alcaraz", "display_name": "Carlos Alcaraz",
            "cells": {"F": {"probability": 0.0, "state": CELL_LIVE},
                      "title": {"probability": 0.00525, "state": CELL_LIVE}},
        }]
        assert len(evaluate_monotonicity(columns, before)) == 1

        after = [{
            "entity_key": "alcaraz", "display_name": "Carlos Alcaraz",
            "cells": {"F": {"probability": None, "state": CELL_SETTLED},
                      "title": {"probability": None, "state": CELL_SETTLED}},
        }]
        assert evaluate_monotonicity(columns, after) == []

    def test_a_live_break_between_two_open_questions_is_still_reported(self):
        """The eval is narrowed by the DRAW, never by this change's convenience."""
        columns = [{"key": k, "short_label": k} for k in ("SF", "F")]
        rows = [{
            "entity_key": "a", "display_name": "A",
            "cells": {"SF": {"probability": 0.40, "state": CELL_LIVE},
                      "F": {"probability": 0.62, "state": CELL_LIVE}},
        }]
        [violation] = evaluate_monotonicity(columns, rows)
        assert violation["earlier"] == "SF" and violation["later"] == "F"

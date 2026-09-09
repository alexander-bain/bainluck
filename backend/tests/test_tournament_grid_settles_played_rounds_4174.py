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
    SIDE_LOST,
    SIDE_PLAYED,
    SIDE_WON,
    VERDICT_OUT,
    VERDICT_REACHED,
    DrawProgress,
    build_progress,
    progress_from_sides,
)

NOW = datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)
DRAW = "mens-singles"
SIZES = {DRAW: 128}


def _espn(*matches, draw=DRAW):
    """`parse_results`' own shape: {draw: {pair_key: row}}, ESPN names and all.

    Deliberately NOT `build_results`' output. That is the whole of the
    CERT-2360 repair: the strict two-name join drops a match when one side
    does not resolve, and progress has to be read BEFORE it.
    """
    rows = {}
    for i, m in enumerate(matches):
        rows[f"pair-{i}"] = m
    return {"draws": {draw: rows}}


def _row(round_name, a, b, *, winner=None, completion="final"):
    return {
        "players": [a, b],
        "espn_round": round_name,
        "winner_name": winner,
        "winner_normalized": _norm(winner) if winner else None,
        "completion": completion,
        "score": "6-4, 6-4",
        "espn_competition_id": None,
    }


def _norm(name):
    from app.services.espn_tennis import normalize_name

    return normalize_name(name)


def _reg(*display_names, draw=DRAW):
    return {
        "schema_version": "tournament-register/v1",
        "tournament": "us-open",
        "season": "2026",
        "version": 1,
        "generated_at": NOW.isoformat(),
        "draw_released": True,
        "players": [
            {
                "entity_key": name.lower().replace(" ", "-"),
                "display_name": name,
                "draw": draw,
                "role": "contender",
                "sources": [],
            }
            for name in display_names
        ],
        "matchups": [],
        "reaches": [],
    }


def _progress(register, espn):
    return build_progress(register, espn, draw_sizes=SIZES).get(DRAW, DrawProgress())


# ---------------------------------------------------------------------------
# WHAT A MATCH PROVES — and, more importantly, what it does not
# ---------------------------------------------------------------------------

class TestOnlyAMatchWeHoldSettlesACell:
    def test_a_finished_match_reaches_both_and_eliminates_the_loser(self):
        prog = _progress(
            _reg("Carlos Alcaraz", "Holger Rune"),
            _espn(_row("Round 4", "Carlos Alcaraz", "Holger Rune", winner="Carlos Alcaraz")),
        )
        assert prog.verdict("carlos-alcaraz", "R16") == VERDICT_REACHED
        assert prog.verdict("holger-rune", "R16") == VERDICT_REACHED
        # The winner is admitted to the next round without playing it.
        assert prog.verdict("carlos-alcaraz", "QF") == VERDICT_REACHED
        assert prog.verdict("holger-rune", "QF") == VERDICT_OUT
        assert prog.eliminated == {"holger-rune": "R16"}

    def test_a_match_still_in_progress_eliminates_nobody(self):
        """Being in a match that has not finished is not losing it."""
        prog = _progress(
            _reg("Alexander Zverev", "Alexander Blockx"),
            _espn(_row("Quarterfinal", "Alexander Zverev", "Alexander Blockx",
                       completion="in_progress")),
        )
        assert prog.verdict("alexander-zverev", "QF") == VERDICT_REACHED
        assert prog.verdict("alexander-blockx", "QF") == VERDICT_REACHED
        assert prog.verdict("alexander-zverev", "SF") is None
        assert prog.verdict("alexander-blockx", "SF") is None
        assert prog.eliminated == {}
        assert prog.decided_matches == 0

    def test_a_retirement_and_a_walkover_both_decide(self):
        prog = _progress(
            _reg("A One", "B Two", "C Three", "D Four"),
            _espn(
                _row("Round 3", "A One", "B Two", winner="A One", completion="retired"),
                _row("Round 3", "C Three", "D Four", winner="C Three", completion="walkover"),
            ),
        )
        assert prog.eliminated == {"b-two": "R32", "d-four": "R32"}
        assert prog.verdict("a-one", "R16") == VERDICT_REACHED

    def test_a_player_no_result_mentions_is_never_settled(self):
        """THE UNDER-CLAIM RULE, and the reason it is not negotiable.

        A false "out" would erase a live player from the grid, which is worse
        than the defect being fixed.
        """
        prog = _progress(
            _reg("Carlos Alcaraz", "Holger Rune", "Jannik Sinner"),
            _espn(_row("Round 4", "Carlos Alcaraz", "Holger Rune", winner="Carlos Alcaraz")),
        )
        assert prog.verdict("jannik-sinner", "R16") is None
        assert prog.verdict("jannik-sinner", "F") is None
        assert prog.title_verdict("jannik-sinner") is None

    def test_an_eliminated_player_keeps_the_rounds_they_did_reach(self):
        prog = _progress(
            _reg("Frances Tiafoe", "Sebastian Korda", "Ben Shelton"),
            _espn(
                _row("Round 4", "Frances Tiafoe", "Sebastian Korda", winner="Frances Tiafoe"),
                _row("Quarterfinal", "Frances Tiafoe", "Ben Shelton", winner="Ben Shelton"),
            ),
        )
        assert prog.verdict("frances-tiafoe", "R16") == VERDICT_REACHED
        assert prog.verdict("frances-tiafoe", "QF") == VERDICT_REACHED
        assert prog.verdict("frances-tiafoe", "SF") == VERDICT_OUT

    def test_the_final_crowns_a_champion_and_nothing_else_does(self):
        register = _reg("Alexander Zverev", "Ben Shelton", "Frances Tiafoe")
        prog = _progress(
            register,
            _espn(_row("Final", "Alexander Zverev", "Ben Shelton", winner="Alexander Zverev")),
        )
        assert prog.champion == "alexander-zverev"
        assert prog.title_verdict("alexander-zverev") == VERDICT_REACHED
        assert prog.title_verdict("ben-shelton") == VERDICT_OUT
        assert prog.open_slots("title", 1) == 0

        semi_only = _progress(
            register,
            _espn(_row("Semifinal", "Alexander Zverev", "Frances Tiafoe",
                       winner="Alexander Zverev")),
        )
        assert semi_only.champion is None
        assert semi_only.open_slots("title", 1) == 1

    def test_a_round_that_cannot_be_named_settles_nothing(self):
        """"Round 2" is R64 in a slam and R32 in a 64-draw — no size, no round.

        Filing a match under the wrong round would settle the wrong column,
        which is the wrong-question defect the register exists to refuse.
        """
        register = _reg("A One", "B Two")
        espn = _espn(_row("Round 2", "A One", "B Two", winner="A One"))
        assert build_progress(register, espn, draw_sizes={}) == {}
        assert build_progress(
            register, _espn(_row("Zeroth Round", "A One", "B Two", winner="A One")),
            draw_sizes=SIZES,
        ) == {}
        # A register-vocabulary round needs no size at all.
        prog = build_progress(
            register, _espn(_row("R64", "A One", "B Two", winner="A One")), draw_sizes={},
        )[DRAW]
        assert prog.verdict("b-two", "R64") == VERDICT_REACHED
        assert prog.verdict("b-two", "R32") == VERDICT_OUT

    def test_reached_counts_are_the_whole_field_and_imply_the_earlier_rounds(self):
        """The sum check's denominator is a fact about the ROUND, not the grid."""
        prog = _progress(
            _reg("A One", "B Two", "C Three", "D Four"),
            _espn(
                _row("Round 4", "A One", "B Two", winner="A One"),
                _row("Round 4", "C Three", "D Four", winner="C Three"),
                _row("Quarterfinal", "A One", "C Three", winner="A One"),
            ),
        )
        assert prog.reached_counts["R16"] == 4
        assert prog.reached_counts["QF"] == 2
        assert prog.reached_counts["SF"] == 1
        # Reaching the round of 16 means having reached every round before it.
        assert prog.reached_counts["R128"] == 4
        assert prog.open_slots("R16", 16) == 12
        assert prog.open_slots("SF", 4) == 3


# ---------------------------------------------------------------------------
# CERT-2360: ONE UNRESOLVABLE OPPONENT MUST NOT TAKE THE OTHER PLAYER WITH IT
# ---------------------------------------------------------------------------

class TestAHalfResolvedMatchStillSettlesTheKnownPlayer:
    """The BLOCK this ship earned on its first presentation.

    `build_results` drops a match unless BOTH sides resolve — 147 of 467 scored
    competitions on 2026-09-09 — so a progress pass built on its output left
    Michael Zheng, this issue's own headline case, at a stale 52% to reach a
    final he was knocked out of in the second round. His Round 2 opponent does
    not resolve; his own name does.
    """

    #: Zheng's real shape on the specimen day: a first-round win in the served
    #: list, and a second-round loss to somebody we cannot name.
    ZHENG = _espn(
        _row("Round 1", "Michael Zheng", "Some Qualifier", winner="Michael Zheng"),
        _row("Round 2", "Michael Zheng", "Unresolvable Opponent",
             winner="Unresolvable Opponent"),
    )

    def test_the_known_loser_is_settled_out(self):
        prog = _progress(_reg("Michael Zheng"), self.ZHENG)
        assert prog.eliminated == {"michael-zheng": "R64"}
        assert prog.verdict("michael-zheng", "R16") == VERDICT_OUT
        assert prog.verdict("michael-zheng", "F") == VERDICT_OUT
        assert prog.title_verdict("michael-zheng") == VERDICT_OUT

    def test_the_known_winner_is_advanced(self):
        prog = _progress(
            _reg("Ben Shelton"),
            _espn(_row("Quarterfinal", "Ben Shelton", "Unresolvable Opponent",
                       winner="Ben Shelton")),
        )
        assert prog.verdict("ben-shelton", "SF") == VERDICT_REACHED
        assert prog.eliminated == {}

    def test_the_unresolvable_side_contributes_nothing(self):
        """It is not settled, not counted, and not invented an entity key for."""
        prog = _progress(_reg("Michael Zheng"), self.ZHENG)
        assert set(prog.reached) == {"michael-zheng"}
        assert prog.reached_counts["R64"] == 1
        assert prog.reached_counts.get("R32") is None

    def test_half_resolved_matches_are_counted_and_reported(self):
        prog = _progress(_reg("Michael Zheng"), self.ZHENG)
        assert prog.decided_matches == 2
        assert prog.partial_matches == 2
        both = _progress(
            _reg("Michael Zheng", "Unresolvable Opponent"),
            self.ZHENG,
        )
        assert both.partial_matches == 1  # only the Round 1 pair is still half

    def test_a_name_that_does_not_match_the_winner_never_falsely_eliminates(self):
        """The comparison errs safe in the one direction that matters.

        A resolved side is out only when its normalized name DIFFERS from the
        winner's, so a normalisation failure produces a MISSING elimination and
        never a false one.
        """
        prog = _progress(
            _reg("Ben Shelton"),
            # The winner IS Shelton, spelled the way the register spells him.
            _espn(_row("Quarterfinal", "Ben Shelton", "Someone Else", winner="Ben Shelton")),
        )
        assert "ben-shelton" not in prog.eliminated

    def test_progress_from_sides_is_the_arithmetic_on_its_own(self):
        """The half the reader above hands off to, driven directly."""
        prog = progress_from_sides([
            {"draw": DRAW, "round": "SF", "entity_key": "a", "outcome": SIDE_WON,
             "match_key": "m1"},
            {"draw": DRAW, "round": "SF", "entity_key": "b", "outcome": SIDE_LOST,
             "match_key": "m1"},
            {"draw": DRAW, "round": "QF", "entity_key": "c", "outcome": SIDE_PLAYED,
             "match_key": "m2"},
        ])[DRAW]
        assert prog.verdict("a", "F") == VERDICT_REACHED
        assert prog.verdict("b", "F") == VERDICT_OUT
        assert prog.verdict("c", "SF") is None
        assert prog.decided_matches == 1


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
#:
#: BOTH matches have an opponent the register cannot resolve, which is the
#: production shape and the CERT-2360 case: `build_results` publishes neither
#: of these rows, so a grid fed from its output settles nothing here.
SPECIMEN_PROGRESS = build_progress(
    SPECIMEN_REGISTER,
    _espn(
        _row("Round 2", "Michael Zheng", "Unresolvable Opponent",
             winner="Unresolvable Opponent"),
        _row("Quarterfinal", "Alexander Zverev", "Another Unresolvable",
             winner="Alexander Zverev"),
    ),
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

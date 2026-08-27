"""The playoff grid, its five cell states and its two evals (UX-P139).

Alex's amendment is the spec these tests encode:

    "a blank cell, an improperly blended cell, or a cell populated from the
    WRONG future is a linkage defect — no excuse, no interpolation ... a cell
    whose direct markets are not linked renders as an ALARM STATE naming the
    missing linkage ... wrong-future placement (a reach-QF market feeding the
    SF cell) is a named eval failure, not a data quirk."

Three obligations follow, and each has its own class below:

* **Nothing is ever blank.**  Every cell in every state carries a state name,
  and the two failure states carry a note saying what is missing.
* **Wrong-future placement fails the FILE.**  A register that mis-wires a round
  does not validate, so it cannot be served at all.
* **The evals run and report.**  Column sums against slot counts, monotonicity
  down each row — as diagnostics, never as correctors.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.tournament_grid import (
    ALARM_STATES,
    CELL_LIVE,
    CELL_NO_MARKET,
    CELL_STALE,
    CELL_UNLINKED,
    CELL_UNREGISTERED,
    PRICED_STATES,
    ROUND_SLOTS,
    build_grids,
    build_playoff_grid,
    evaluate_column_sums,
    evaluate_monotonicity,
)
from app.utils.tournament_register import (
    REGISTER_DIR,
    load_register,
    us_open_2026_contract,
    validate_register,
)

NOW = datetime(2026, 8, 27, 0, 0, tzinfo=timezone.utc)


def _reach(entity_key, round_name, *, draw="mens-singles", outcome_id=1, market_id=10,
           status="live", subject="Carlos Alcaraz", question_round=None,
           question_draw=None, kalshi_missing=True):
    blocks = [{
        "source": "polymarket",
        "kind": "reach",
        "market_id": market_id,
        "outcome_id": outcome_id,
        "market_external_id": f"0x{market_id:04x}",
        "outcome_external_id": f"0x{market_id:04x}_yes",
        "source_name": "Yes",
        "question_round": question_round or round_name,
        "question_draw": question_draw or draw,
        "question_subject": subject,
        "question": f"Will {subject} advance?",
        "status": status,
        "terminal_result": None if status != "settled" else "eliminated",
        "price_observed_at": NOW.isoformat(),
        "evidence": {"kind": "advance-ladder-census", "observed_at": NOW.isoformat()},
    }]
    if kalshi_missing:
        blocks.append({
            "source": "kalshi",
            "kind": "reach",
            "market_id": None,
            "outcome_id": None,
            "status": "missing",
            "terminal_result": None,
            "evidence": {
                "kind": "advance-ladder-census-absent",
                "observed_at": NOW.isoformat(),
                "note": "kalshi carries no round-advancement series",
            },
        })
    return {
        "draw": draw,
        "entity_key": entity_key,
        "round": round_name,
        "sources": blocks,
    }


def _register(reaches, *, players=None):
    return {
        "schema_version": "tournament-register/v1",
        "tournament": "us-open",
        "season": "2026",
        "version": 1,
        "generated_at": NOW.isoformat(),
        "draw_released": False,
        "players": players
        or [{
            "entity_key": "carlos-alcaraz",
            "display_name": "Carlos Alcaraz",
            "draw": "mens-singles",
            "role": "contender",
            "sources": [{
                "source": "kalshi",
                "market_id": 1,
                "outcome_id": 2,
                "status": "live",
                "source_name": "Carlos Alcaraz",
                "evidence": {"kind": "census", "observed_at": NOW.isoformat()},
            }],
        }],
        "matchups": [],
        "reaches": reaches,
    }


def _board_row(**overrides):
    row = {
        "entity_key": "carlos-alcaraz",
        "display_name": "Carlos Alcaraz",
        "seed": 2,
        "rank": 1,
        "state": "live",
        "probability": 0.20,
        "price_state": "live",
        "age_hours": 1.0,
        "sources": [],
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# NOTHING IS EVER BLANK
# ---------------------------------------------------------------------------

class TestNoCellIsEverBlank:
    """Alex's dealbreaker, as an assertion over every cell the builder emits."""

    def test_a_priced_cell_reads_its_own_market(self):
        grid = build_playoff_grid(
            _register([_reach("carlos-alcaraz", "SF")]),
            board_rows=[_board_row()],
            prices={1: {"probability": 0.575, "observed_at": NOW}},
            draw="mens-singles",
            now=NOW,
        )
        cell = grid["rows"][0]["cells"]["SF"]
        assert cell["state"] == CELL_LIVE
        assert cell["probability"] == 0.575
        assert cell["probability_is_live"] is True
        assert cell["is_alarm"] is False

    def test_every_cell_in_every_state_names_its_state(self):
        """The property, not a case: no cell may be stateless."""
        register = _register([
            _reach("carlos-alcaraz", "R16", outcome_id=1, market_id=10),
            # Registered live and the load returns nothing -> the ALARM.
            _reach("carlos-alcaraz", "QF", outcome_id=99, market_id=11),
        ])
        # An SF column exists in the register for a DIFFERENT player, so
        # Alcaraz's SF cell is `unregistered`.
        register["players"].append({
            "entity_key": "novak-djokovic",
            "display_name": "Novak Djokovic",
            "draw": "mens-singles",
            "role": "participant",
            "sources": [],
        })
        register["reaches"].append(
            _reach("novak-djokovic", "SF", outcome_id=3, market_id=12,
                   subject="Novak Djokovic")
        )
        grid = build_playoff_grid(
            register,
            board_rows=[_board_row()],
            prices={1: {"probability": 0.8, "observed_at": NOW}},
            draw="mens-singles",
            now=NOW,
        )
        for row in grid["rows"]:
            for key, cell in row["cells"].items():
                assert cell["state"], f"{row['entity_key']}/{key} has no state"
                if cell["state"] in ALARM_STATES:
                    assert cell["note"], f"{key} alarm with no explanation"

    def test_a_registered_but_unpriced_cell_is_an_alarm_naming_the_market(self):
        grid = build_playoff_grid(
            _register([_reach("carlos-alcaraz", "SF", outcome_id=404, market_id=77)]),
            board_rows=[_board_row()],
            prices={},
            draw="mens-singles",
            now=NOW,
        )
        cell = grid["rows"][0]["cells"]["SF"]
        assert cell["state"] == CELL_UNLINKED
        assert cell["is_alarm"] is True
        # NAMES THE MISSING LINKAGE. "the fix is linking the real markets", so
        # the cell has to say which market.
        assert "0x004d" in cell["note"]
        assert grid["alarm_cells"] == 1

    def test_a_censused_absence_is_no_market_and_is_not_an_alarm(self):
        """The state the amendment's axiom did not anticipate.

        Kalshi publishes no round-advancement series for this tournament and
        Polymarket covers 84 of 256 singles players. A cell both sources were
        asked about and neither carries is a RESULT, and it must not be filed
        beside a broken link — those need different fixes from different
        people.
        """
        reach = _reach("carlos-alcaraz", "SF")
        reach["sources"] = [b for b in reach["sources"] if b["source"] == "kalshi"]
        grid = build_playoff_grid(
            _register([reach]),
            board_rows=[_board_row()],
            prices={},
            draw="mens-singles",
            now=NOW,
        )
        cell = grid["rows"][0]["cells"]["SF"]
        assert cell["state"] == CELL_NO_MARKET
        assert cell["is_alarm"] is False
        assert "kalshi" in cell["note"]
        # And it says WHEN we looked, which is what makes it a result.
        assert cell["censused_at"] == NOW.isoformat()
        assert grid["alarm_cells"] == 0

    def test_a_column_a_player_has_no_cell_for_is_unregistered_not_blank(self):
        register = _register([_reach("carlos-alcaraz", "SF")])
        register["players"].append({
            "entity_key": "jannik-sinner",
            "display_name": "Jannik Sinner",
            "draw": "mens-singles",
            "role": "contender",
            "sources": [{
                "source": "kalshi", "market_id": 5, "outcome_id": 6, "status": "live",
                "source_name": "Jannik Sinner",
                "evidence": {"kind": "census", "observed_at": NOW.isoformat()},
            }],
        })
        grid = build_playoff_grid(
            register,
            board_rows=[
                _board_row(),
                _board_row(entity_key="jannik-sinner", display_name="Jannik Sinner", rank=2),
            ],
            prices={1: {"probability": 0.5, "observed_at": NOW}},
            draw="mens-singles",
            now=NOW,
        )
        sinner = next(r for r in grid["rows"] if r["entity_key"] == "jannik-sinner")
        assert sinner["cells"]["SF"]["state"] == CELL_UNREGISTERED
        assert sinner["cells"]["SF"]["is_alarm"] is True

    def test_the_counters_account_for_every_cell(self):
        """A grid that cannot add up its own cells is not one to trust."""
        register = _register([
            _reach("carlos-alcaraz", "R16", outcome_id=1, market_id=10),
            _reach("carlos-alcaraz", "SF", outcome_id=2, market_id=11),
        ])
        grid = build_playoff_grid(
            register,
            board_rows=[_board_row()],
            prices={1: {"probability": 0.9, "observed_at": NOW}},
            draw="mens-singles",
            now=NOW,
        )
        assert sum(grid["counts"].values()) == grid["total_cells"]


class TestFreshnessIsInherited:
    """One vocabulary. A grid cell is live/stale/dark by the page's own rule."""

    def test_a_stale_price_is_never_presented_as_live(self):
        old = NOW - timedelta(hours=27)
        grid = build_playoff_grid(
            _register([_reach("carlos-alcaraz", "SF")]),
            board_rows=[_board_row()],
            prices={1: {"probability": 0.575, "observed_at": old}},
            draw="mens-singles",
            now=NOW,
        )
        cell = grid["rows"][0]["cells"]["SF"]
        assert cell["state"] == CELL_STALE
        assert cell["probability_is_live"] is False
        assert cell["age_hours"] == pytest.approx(27.0, abs=0.05)

    def test_a_cell_is_as_fresh_as_its_oldest_leg(self):
        """The AND, inherited from the boards: both legs are inside the number."""
        reach = _reach("carlos-alcaraz", "SF")
        reach["sources"][1] = {
            "source": "kalshi",
            "kind": "reach",
            "market_id": 20,
            "outcome_id": 2,
            "market_external_id": "KX-SF",
            "source_name": "Yes",
            "question_round": "SF",
            "question_draw": "mens-singles",
            "question_subject": "Carlos Alcaraz",
            "status": "live",
            "terminal_result": None,
            "price_observed_at": NOW.isoformat(),
            "evidence": {"kind": "census", "observed_at": NOW.isoformat()},
        }
        grid = build_playoff_grid(
            _register([reach]),
            board_rows=[_board_row()],
            prices={
                1: {"probability": 0.60, "observed_at": NOW},
                2: {"probability": 0.56, "observed_at": NOW - timedelta(hours=30)},
            },
            draw="mens-singles",
            now=NOW,
        )
        cell = grid["rows"][0]["cells"]["SF"]
        assert cell["source_count"] == 2
        # The blend is the product: one number, the two-source midpoint.
        assert cell["probability"] == pytest.approx(0.58)
        assert cell["blend_rule"] == "equal_weight_midpoint"
        # And it is as old as the older leg, not the newer one.
        assert cell["state"] == CELL_STALE
        assert cell["probability_is_live"] is False


# ---------------------------------------------------------------------------
# WRONG-FUTURE PLACEMENT FAILS THE FILE
# ---------------------------------------------------------------------------

class TestWrongFutureIsANamedEvalFailure:
    """Alex: "a reach-QF market feeding the SF cell is a named eval failure"."""

    def test_a_qf_market_in_the_sf_cell_refuses_the_register(self):
        register = _register([
            _reach("carlos-alcaraz", "SF", question_round="QF")
        ])
        findings = validate_register(register, us_open_2026_contract())
        assert "REACH_ROUND_MISMATCH" in findings

    def test_a_womens_market_in_a_mens_cell_refuses_the_register(self):
        register = _register([
            _reach("carlos-alcaraz", "SF", question_draw="womens-singles")
        ])
        findings = validate_register(register, us_open_2026_contract())
        assert "REACH_DRAW_MISMATCH" in findings

    def test_another_players_market_refuses_the_register(self):
        register = _register([
            _reach("carlos-alcaraz", "SF", subject="Novak Djokovic")
        ])
        findings = validate_register(register, us_open_2026_contract())
        assert "REACH_SUBJECT_MISMATCH" in findings

    def test_one_market_backing_two_cells_refuses_the_register(self):
        register = _register([
            _reach("carlos-alcaraz", "SF", outcome_id=1, market_id=10),
            _reach("carlos-alcaraz", "QF", outcome_id=1, market_id=10,
                   question_round="QF"),
        ])
        findings = validate_register(register, us_open_2026_contract())
        assert "REACH_IDENTITY_REUSED" in findings

    def test_two_cells_for_one_player_round_refuses_the_register(self):
        register = _register([
            _reach("carlos-alcaraz", "SF", outcome_id=1, market_id=10),
            _reach("carlos-alcaraz", "SF", outcome_id=2, market_id=11),
        ])
        findings = validate_register(register, us_open_2026_contract())
        assert "DUPLICATE_REACH_CELL" in findings

    def test_an_outright_quote_may_not_back_a_reach_cell(self):
        """P(wins the title) in the "reaches the semis" column, refused."""
        register = _register([_reach("carlos-alcaraz", "SF")])
        register["reaches"][0]["sources"][0]["kind"] = "outright"
        findings = validate_register(register, us_open_2026_contract())
        assert "REACH_SOURCE_WRONG_KIND" in findings

    def test_a_cell_for_an_unregistered_player_refuses_the_register(self):
        register = _register([_reach("nobody-at-all", "SF")])
        findings = validate_register(register, us_open_2026_contract())
        assert "REACH_PLAYER_NOT_REGISTERED" in findings

    def test_a_block_that_does_not_restate_its_question_refuses(self):
        """The restatement IS the check; a block without it cannot be checked."""
        register = _register([_reach("carlos-alcaraz", "SF")])
        del register["reaches"][0]["sources"][0]["question_round"]
        findings = validate_register(register, us_open_2026_contract())
        assert "REACH_BLOCK_MISSING_QUESTION" in findings

    def test_every_wrong_future_finding_is_structural(self):
        """Not advisory. A mis-wired register is REJECTED, never served."""
        from app.utils.tournament_register import classify

        for finding in (
            "REACH_ROUND_MISMATCH",
            "REACH_DRAW_MISMATCH",
            "REACH_SUBJECT_MISMATCH",
            "REACH_IDENTITY_REUSED",
            "DUPLICATE_REACH_CELL",
            "REACH_SOURCE_WRONG_KIND",
            "REACH_PLAYER_NOT_REGISTERED",
        ):
            verdict = classify([finding])
            assert verdict["classification"] == "invalid", finding
            assert verdict["action"] == "reject_register", finding


# ---------------------------------------------------------------------------
# THE TWO EVALS
# ---------------------------------------------------------------------------

class TestColumnSums:
    """Alex's ruling 4: every column sums to the round's slot count."""

    def test_slot_counts_are_the_ones_alex_named(self):
        assert ROUND_SLOTS["QF"] == 8
        assert ROUND_SLOTS["SF"] == 4
        assert ROUND_SLOTS["F"] == 2
        assert ROUND_SLOTS["title"] == 1
        assert ROUND_SLOTS["R16"] == 16

    def test_a_coherent_column_passes(self):
        columns = [{"key": "SF", "short_label": "SF"}]
        rows = [
            {"entity_key": f"p{i}", "cells": {"SF": {"probability": 0.5}}}
            for i in range(8)
        ]
        [check] = evaluate_column_sums(columns, rows)
        assert check["sum"] == 4.0
        assert check["expected"] == 4
        assert check["verdict"] == "pass"

    def test_an_over_summing_column_is_named_over_and_not_rescaled(self):
        """The Final column measured 1.39x on 2026-08-26. Reported, never fixed.

        Rescaling would make the column add up and every number in it a
        fabrication. This page's whole claim is that its numbers are prices
        somebody quoted.
        """
        columns = [{"key": "F", "short_label": "Final"}]
        rows = [
            {"entity_key": f"p{i}", "cells": {"F": {"probability": 0.7}}}
            for i in range(4)
        ]
        [check] = evaluate_column_sums(columns, rows)
        assert check["verdict"] == "over"
        assert check["sum"] == 2.8
        assert rows[0]["cells"]["F"]["probability"] == 0.7

    def test_an_under_summing_column_is_named_under_with_its_coverage(self):
        """Under-summing is usually a COVERAGE fact, so the count travels with it."""
        columns = [{"key": "R16", "short_label": "R16"}]
        rows = [
            {"entity_key": f"p{i}", "cells": {"R16": {"probability": 0.5}}}
            for i in range(20)
        ] + [{"entity_key": "unpriced", "cells": {"R16": {"probability": None}}}]
        [check] = evaluate_column_sums(columns, rows)
        assert check["verdict"] == "under"
        assert check["priced_rows"] == 20
        assert check["total_rows"] == 21

    def test_a_column_with_no_prices_is_unchecked_not_a_pass(self):
        """gotcha #53: an empty answer is not a good one."""
        columns = [{"key": "SF", "short_label": "SF"}]
        rows = [{"entity_key": "p", "cells": {"SF": {"probability": None}}}]
        [check] = evaluate_column_sums(columns, rows)
        assert check["verdict"] == "unchecked"


class TestMonotonicity:
    """A player cannot be likelier to reach the final than the semis."""

    def test_a_monotone_row_is_clean(self):
        columns = [{"key": k, "short_label": k} for k in ("R16", "QF", "SF", "F", "title")]
        rows = [{
            "entity_key": "a", "display_name": "A",
            "cells": {
                "R16": {"probability": 0.85}, "QF": {"probability": 0.78},
                "SF": {"probability": 0.51}, "F": {"probability": 0.36},
                "title": {"probability": 0.25},
            },
        }]
        assert evaluate_monotonicity(columns, rows) == []

    def test_a_final_above_a_semi_is_a_named_violation(self):
        columns = [{"key": k, "short_label": k} for k in ("SF", "F")]
        rows = [{
            "entity_key": "cameron-norrie", "display_name": "Cameron Norrie",
            "cells": {"SF": {"probability": 0.04}, "F": {"probability": 0.05}},
        }]
        [violation] = evaluate_monotonicity(columns, rows)
        assert violation["entity_key"] == "cameron-norrie"
        assert violation["earlier"] == "SF"
        assert violation["later"] == "F"

    def test_rounding_noise_is_not_a_violation(self):
        columns = [{"key": k, "short_label": k} for k in ("SF", "F")]
        rows = [{
            "entity_key": "a", "display_name": "A",
            "cells": {"SF": {"probability": 0.400}, "F": {"probability": 0.402}},
        }]
        assert evaluate_monotonicity(columns, rows) == []

    def test_an_unpriced_cell_does_not_bridge_two_that_are(self):
        """A hole must not make its neighbours adjacent — that would compare
        R16 against the title and call a legitimate row broken."""
        columns = [{"key": k, "short_label": k} for k in ("R16", "QF", "SF")]
        rows = [{
            "entity_key": "a", "display_name": "A",
            "cells": {
                "R16": {"probability": 0.9},
                "QF": {"probability": None},
                "SF": {"probability": 0.7},
            },
        }]
        assert evaluate_monotonicity(columns, rows) == []


# ---------------------------------------------------------------------------
# THE COMMITTED REGISTER — the grid Alex will actually look at
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def committed():
    register = load_register("us-open", "2026")
    assert register is not None
    return register


class TestTheCommittedGrid:
    def test_the_register_carries_reach_cells_for_both_draws(self, committed):
        draws = {r["draw"] for r in committed["reaches"]}
        assert draws == {"mens-singles", "womens-singles"}

    def test_the_semifinal_column_exists_in_both_draws(self, committed):
        """Alex's ruling 4: "The second-week grid must include the SEMIFINAL
        column (it jumped QF->title)"."""
        from app.utils.tournament_register import TournamentRegister

        view = TournamentRegister(committed)
        for draw in ("mens-singles", "womens-singles"):
            rounds = view.reach_rounds(draw)
            assert rounds == ["R16", "QF", "SF", "F"], draw

    def test_every_reach_cell_states_both_sources(self, committed):
        """Alex's ruling 3: "Source every player x round cell from Kalshi AND
        Polymarket". Where a source carries nothing it says so, with a date."""
        for reach in committed["reaches"]:
            sources = {b["source"] for b in reach["sources"]}
            assert sources == {"kalshi", "polymarket"}, reach
            for block in reach["sources"]:
                assert block["evidence"]["observed_at"]

    def test_no_reach_cell_is_wired_to_another_rounds_market(self, committed):
        for reach in committed["reaches"]:
            for block in reach["sources"]:
                if block["status"] == "missing":
                    continue
                assert block["question_round"] == reach["round"]
                assert block["question_draw"] == reach["draw"]

    def test_the_committed_register_validates(self, committed):
        assert validate_register(committed, us_open_2026_contract()) == []

    def test_no_player_has_an_interleaved_hole(self, committed):
        """THE DEFECT ALEX NAMED, as a property of the committed file.

        "A player showing quarterfinal and title odds but a blank semifinal is
        forbidden." Within the reach columns, a player's linked cells must be a
        PREFIX-free contiguous set: they either have the whole ladder or none of
        it. Measured against Polymarket's inventory that holds for all 84 ladder
        players, and this asserts it rather than trusting it.
        """
        order = ["R16", "QF", "SF", "F"]
        linked: dict[tuple, set] = {}
        for reach in committed["reaches"]:
            has_market = any(
                b["status"] != "missing" for b in reach["sources"]
            )
            if has_market:
                linked.setdefault((reach["draw"], reach["entity_key"]), set()).add(
                    reach["round"]
                )
        assert linked, "no linked reach cells at all"
        for key, rounds in linked.items():
            assert rounds == set(order), f"{key} has a partial ladder: {sorted(rounds)}"

    def test_the_grid_builds_with_no_alarms_on_the_committed_register(self, committed):
        """The ship condition. Any alarm is a linkage defect with a named fix."""
        payload_path = (
            REGISTER_DIR.parents[1].parent / "docs" / "mocks" / "us-open"
            / "payload-2026-08-25.json"
        )
        boards = json.loads(payload_path.read_text())["boards"]

        # Price every registered reach identity, so this test measures the
        # BUILDER rather than today's database contents.
        from app.utils.tournament_register import TournamentRegister

        view = TournamentRegister(committed)
        prices = {
            oid: {"probability": 0.5, "observed_at": NOW}
            for oid in view.reach_outcome_ids()
        }
        grids = build_grids(committed, boards=boards, prices=prices, now=NOW)

        assert set(grids) == {"mens-singles", "womens-singles"}
        for draw, grid in grids.items():
            assert grid["alarm_cells"] == 0, (draw, grid["counts"])
            assert grid["priced_cells"] > 0
            assert sum(grid["counts"].values()) == grid["total_cells"]
            assert [c["key"] for c in grid["columns"]] == [
                "R16", "QF", "SF", "F", "title"
            ]

    def test_ladder_players_without_a_title_price_still_get_a_row(self, committed):
        """20 of the men's 44 priced ladder rows have no outright quote.

        A rows-from-the-board-only grid dropped every one of them — 128 priced
        markets invisible on a page whose claim is that it shows what the market
        prices.
        """
        payload_path = (
            REGISTER_DIR.parents[1].parent / "docs" / "mocks" / "us-open"
            / "payload-2026-08-25.json"
        )
        boards = json.loads(payload_path.read_text())["boards"]
        grids = build_grids(committed, boards=boards, prices={}, now=NOW)

        mens = grids["mens-singles"]
        board_keys = {r["entity_key"] for r in boards[0]["rows"]}
        extra = [r for r in mens["rows"] if r["entity_key"] not in board_keys]
        assert len(extra) == 20
        # And they sort AFTER the ranked rows, never interleaved.
        first_extra = mens["rows"].index(extra[0])
        assert all(r["on_board"] for r in mens["rows"][:first_extra])
        assert all(not r["on_board"] for r in mens["rows"][first_extra:])

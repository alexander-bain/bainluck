"""CAL-P007 (#1527): the attended repair of the three-winner cohort.

Approved by Alex 2026-08-07 under attended capped-batch discipline. CAL-P006
stopped the producers; this writes the fix for what they already made.

The authority is per-LEG, which is what makes writing permissible at all under
gotcha #21 (never bulk-reset ``is_winner`` without a source that can immediately
re-resolve). Verified live against the CLOB on market 55254886::

    Will Slavia Praha beat Anderlecht?    Yes=False
    Will Anderlecht beat Slavia Praha?    Yes=True     <- the actual winner
    Will the match ... end in a draw?     Yes=False

Our DB crowned all three. There is no mapping step here that can be wrong: each
leg IS a condition_id, so the id is the identity.

Everything below is about the ways this must REFUSE to write. A repair that
guesses is worse than the corruption it replaces, because it launders a guess as
tier-3 authority.
"""

import inspect

import pytest

import app.tasks.repair_winner_field as repair_mod
from app.routes.admin_repairs import _REPAIRS
from app.tasks.repair_winner_field import (
    APPLY_MARKET_CAP,
    IMPOSSIBLE_PRICE,
    WRITE_SOURCE,
    _is_condition_id,
    decide_market,
    foreign_authority,
    yes_winner,
)
from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES,
    is_calibration_truth_eligible,
)


def _leg(name, win, oid=None):
    return {"outcome_id": oid or abs(hash(name)) % 100000, "name": name,
            "yes_winner": win}


# ---------------------------------------------------------------------------
# Reading CLOB settlement
# ---------------------------------------------------------------------------
class TestYesWinner:
    def test_the_real_winning_leg(self):
        assert yes_winner(
            {"tokens": [{"outcome": "Yes", "winner": True},
                        {"outcome": "No", "winner": False}]}
        ) is True

    def test_the_real_losing_leg(self):
        assert yes_winner(
            {"tokens": [{"outcome": "Yes", "winner": False},
                        {"outcome": "No", "winner": True}]}
        ) is False

    def test_undecided_is_none_not_false(self):
        # The single most dangerous confusion in this module: an unresolved
        # market must never read as "this leg lost".
        assert yes_winner(
            {"tokens": [{"outcome": "Yes", "winner": None},
                        {"outcome": "No", "winner": None}]}
        ) is None

    def test_missing_market_and_missing_tokens_are_none(self):
        assert yes_winner(None) is None
        assert yes_winner({}) is None
        assert yes_winner({"tokens": []}) is None

    def test_no_yes_token_is_none(self):
        assert yes_winner({"tokens": [{"outcome": "Up", "winner": True}]}) is None

    def test_outcome_label_matching_is_forgiving_of_case_and_space(self):
        assert yes_winner({"tokens": [{"outcome": " yes ", "winner": True}]}) is True


# ---------------------------------------------------------------------------
# The decision — every branch must fail closed
# ---------------------------------------------------------------------------
class TestDecideMarket:
    def test_the_production_case_repairs_to_one_winner(self):
        d = decide_market([
            _leg("Slavia Praha", False, 205060693),
            _leg("Anderlecht", True, 205060694),
            _leg("Draw", False, 205060695),
        ])
        assert d["action"] == "repair"
        assert d["winner_outcome_id"] == 205060694
        assert d["winner_name"] == "Anderlecht"

    def test_one_unresolved_leg_blocks_the_whole_market(self):
        # Partial knowledge must not produce a partial write: if we cannot see
        # every leg, we cannot know there is exactly one winner.
        d = decide_market([
            _leg("Slavia Praha", False),
            _leg("Anderlecht", True),
            _leg("Draw", None),
        ])
        assert d["action"] == "skip"
        assert d["reason"] == "unresolved_legs"
        assert "Draw" in d["detail"]

    def test_void_fixture_is_skipped_never_forced(self):
        d = decide_market([_leg("A", False), _leg("B", False), _leg("Draw", False)])
        assert d == {"action": "skip", "reason": "no_winner_void"}

    def test_contradictory_upstream_is_refused_not_arbitrated(self):
        # If CLOB itself says two legs won, we do not get to pick one.
        d = decide_market([_leg("A", True), _leg("B", True), _leg("Draw", False)])
        assert d["action"] == "skip"
        assert d["reason"] == "multiple_clob_winners"

    def test_empty_leg_list_is_void_not_a_crash(self):
        assert decide_market([])["action"] == "skip"

    @pytest.mark.parametrize("wins", [0, 2, 3])
    def test_only_exactly_one_winner_ever_writes(self, wins):
        legs = [_leg(f"L{i}", i < wins) for i in range(3)]
        d = decide_market(legs)
        assert d["action"] == ("repair" if wins == 1 else "skip")


# ---------------------------------------------------------------------------
# Never overwrite a stronger source
# ---------------------------------------------------------------------------
class TestForeignAuthority:
    def test_api_settlement_blocks_the_repair(self):
        rows = [{"resolution_source": "api_settlement"},
                {"resolution_source": "clean_resolution"}]
        assert foreign_authority(rows) == ["api_settlement"]

    def test_our_own_source_is_not_foreign(self):
        # Idempotence: re-running over our own writes must not self-block.
        assert foreign_authority([{"resolution_source": WRITE_SOURCE}]) == []

    def test_the_corrupt_cohorts_own_source_does_not_block(self):
        # clean_resolution is tier-1 price-derived — exactly what we are here to
        # replace. If it blocked, the repair could never run at all.
        assert foreign_authority([{"resolution_source": "clean_resolution"},
                                  {"resolution_source": None}]) == []


# ---------------------------------------------------------------------------
# Routing ids to an endpoint that can accept them
# ---------------------------------------------------------------------------
class TestConditionIdGuard:
    def test_condition_ids_are_accepted(self):
        assert _is_condition_id(
            "0x982b3670c7db5d579917370017832d682a48142ff9fa71d905c30dc3c80ce889"
        )

    @pytest.mark.parametrize("bad", [None, "", "15366", "kalshi-ticker"])
    def test_non_condition_ids_are_rejected(self, bad):
        # CAL-P003's find: a 0x id sent to a numeric-id endpoint 422s, and that
        # was misread as a rate limit for months. Route by shape, up front.
        assert not _is_condition_id(bad)


# ---------------------------------------------------------------------------
# Authority registration and the cap
# ---------------------------------------------------------------------------
class TestWriteAuthorityAndCap:
    def test_source_is_registered_tier3_and_curve_eligible(self):
        # CAL-P003's lesson: sources FAIL CLOSED. An unregistered name would
        # grade the cohort and still never reach the curve — the fix would look
        # done and move nothing.
        assert WRITE_SOURCE in AUTHORITATIVE_SOURCES
        assert is_calibration_truth_eligible(WRITE_SOURCE)

    def test_source_is_distinct_so_the_cohort_is_revertible(self):
        for sibling in ("clob_authoritative", "clob_never_graded", "clob_ordinal"):
            assert WRITE_SOURCE != sibling

    def test_cap_is_a_constant_not_a_parameter(self):
        # "Capped" must not be dialled off mid-run, so the cap is deliberately
        # NOT reachable from the query string.
        assert isinstance(APPLY_MARKET_CAP, int) and 0 < APPLY_MARKET_CAP <= 200
        params = inspect.signature(repair_mod.repair).parameters
        assert "cap" not in params and "max_writes" not in params

    def test_dry_run_is_the_default(self):
        assert inspect.signature(repair_mod.repair).parameters["apply"].default is False

    def test_registered_on_the_repair_rail(self):
        assert _REPAIRS["winner-field-repair"] == (
            "app.tasks.repair_winner_field", "repair",
        )

    def test_signature_matches_the_rail_dispatcher(self):
        params = inspect.signature(repair_mod.repair).parameters
        for p in ("apply", "limit", "offset"):
            assert p in params


# ---------------------------------------------------------------------------
# Write shape
# ---------------------------------------------------------------------------
class TestWriteShape:
    def test_only_one_leg_can_be_crowned_by_construction(self):
        # The UPDATE sets is_winner = (id = :win_id) across the whole market, so
        # a second winner is not merely unlikely — it is unrepresentable.
        src = inspect.getsource(repair_mod)
        assert "is_winner = (id = :win_id)" in src

    def test_settlement_prices_are_written_alongside_the_winner(self):
        src = inspect.getsource(repair_mod)
        assert "current_probability = CASE WHEN id = :win_id" in src

    def test_impossible_captured_prices_are_nulled_not_invented(self):
        # CAL-P006 proved all 72 snapshots per leg were 1.0 from first ingest —
        # there was never a real price, so NULL is the honest state and any
        # "repaired" opening would be fabricated.
        src = inspect.getsource(repair_mod)
        for col in ("calibration_probability = NULL", "opening_probability = NULL",
                    "opening_captured_at = NULL", "opening_source = NULL"):
            assert col in src

    def test_only_impossible_prices_are_nulled(self):
        # A real sub-certain line on such a market must survive.
        src = inspect.getsource(repair_mod)
        assert "opening_probability >= :bar" in src
        assert IMPOSSIBLE_PRICE >= 0.99

    def test_nothing_writes_when_apply_is_false(self):
        src = inspect.getsource(repair_mod.repair)
        # Every UPDATE sits under the apply branch.
        assert "if apply:" in src
        body = src[src.index("if apply:"):]
        assert "UPDATE futures_outcomes" in body
        assert src.count("UPDATE futures_outcomes") == src[src.index("if apply:"):].count(
            "UPDATE futures_outcomes"
        )

    def test_scan_is_bounded_and_resumable(self):
        src = inspect.getsource(repair_mod)
        assert "SET LOCAL statement_timeout" in src
        assert "LIMIT :scan" in src
        assert "next_offset" in src

    def test_clob_errors_skip_the_market_intact(self):
        # gotcha #36: a 429 is not "no winner". The market must be retried whole,
        # not half-written.
        src = inspect.getsource(repair_mod.repair)
        assert "clob_error" in src
        assert "fetch_failed" in src

    def test_predicate_matches_the_census(self):
        # Repair and census must not drift on what a defect is.
        from app.tasks import census_winner_fields as census_mod
        for frag in ("COUNT(*) FILTER (WHERE o.is_winner) > 1",
                     "COUNT(*) FILTER (WHERE o.current_probability >= :bar) > 1"):
            assert frag in inspect.getsource(repair_mod)
            assert frag in inspect.getsource(census_mod)

"""Contract and real-boundary audit for the settlement authority ladder."""

from __future__ import annotations

import inspect

from app.tasks.backfill_winners import (
    _clear_premature_open_winners,
    _collapse_bywhen_ladder_winners,
    _resolve_winners_only,
)
from app.utils.resolution_authority import (
    can_write_winner,
    is_authoritative,
    is_downgrade,
)
from scripts.evals.settlement_authority_ladder_contract import evaluate_pack, load_pack


def test_fixture_oracle_is_complete_and_green():
    result = evaluate_pack(load_pack())
    assert result["cases"] == 8
    assert result["passed"] == result["cases"], result


def test_seeded_guess_attack_hits_real_authority_type():
    assert is_downgrade("api_settlement", "pass2_guess") is True
    assert is_downgrade("pass2_guess", "api_settlement") is False


def _production_guard_results() -> dict[str, bool]:
    collapse = inspect.getsource(_collapse_bywhen_ladder_winners)
    cleanup = inspect.getsource(_clear_premature_open_winners)
    resolver = inspect.getsource(_resolve_winners_only)
    return {
        # Price-derived settlement_sync is registered tier 3 and therefore enters
        # the collapse query's AUTHORITATIVE_SOURCES_SQL repair shield.
        "settlement_sync_not_repair_shield": not (
            is_authoritative("settlement_sync")
            and "AUTHORITATIVE_SOURCES_SQL" in collapse
        ),
        # The canonical guard exists, but the production resolver never invokes it.
        "winner_writes_centralized": "is_downgrade(" in resolver,
        # Canonical status policy rejects box_score on open. The cleanup SQL must
        # therefore include it; today it selects only NULL and guess-family rows.
        "open_deterministic_cleared": (
            not can_write_winner("open", "box_score")
            and "DETERMINISTIC_SOURCES_SQL" in cleanup
        ),
        "open_guess_cleared": (
            not can_write_winner("open", "pass2_guess")
            and "GUESS_FAMILY_SOURCES_SQL" in cleanup
        ),
    }


def test_real_boundary_deficits_are_pinned_until_repaired():
    """Audit expectation, not a waiver: each False result is a reported P1."""
    assert _production_guard_results() == {
        "settlement_sync_not_repair_shield": False,
        "winner_writes_centralized": False,
        "open_deterministic_cleared": False,
        "open_guess_cleared": True,
    }

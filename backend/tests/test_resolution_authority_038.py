"""Ruling 038 — circular authority: a grade computed from our own data is never tier-3.

`poly_total_score` graded Polymarket full-game Over/Unders from
`events.home_score + events.away_score` — OUR columns — while sitting in
`AUTHORITATIVE_SOURCES`. Its sibling `game_score` takes the same input and
produces the same shape of grade and was already tier 2, so the correction is one
string. See docs/rulings/038-circular-authority-is-never-tier-3.md.

These tests pin the ruling's THREE named consequences plus the invariant itself.
They deliberately do not duplicate tests/test_resolution_authority.py (which
guards the ladder's general shape); everything here is specific to 038.
"""

from __future__ import annotations

import inspect

from app.tasks.backfill_winners import _resolve_polymarket_total_from_scores
from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES,
    AUTHORITATIVE_SOURCES_SQL,
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES,
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
    DETERMINISTIC_SOURCES,
    KNOWN_SOURCES,
    authority_tier,
    calibration_truth_class,
    can_write_winner,
    is_authoritative,
    is_calibration_truth_eligible,
    is_downgrade,
)

# The maintained set the ruling's invariant is stated against: resolution sources
# whose grade is computed from OUR OWN `events` columns (scores / box score /
# scoring plays) rather than from an external venue's settlement.
#
# MAINTAIN THIS — in `app/utils/resolution_authority.py`, beside the tier sets it
# is a subset of. It moved there in queue 067 because production needs it: it is
# the exact set of grades that stop being true when `repair_event_final_scores`
# corrects a wrong final. Adding a source that reads `events` to produce a grade
# means adding it there, and if it is also in AUTHORITATIVE_SOURCES this suite
# goes red, which is the entire point of ruling 038.
from app.utils.resolution_authority import EVENTS_DERIVED_SOURCES  # noqa: E402


class TestPolyTotalScoreIsTier2:
    def test_it_left_tier_three_and_joined_game_score(self):
        assert "poly_total_score" not in AUTHORITATIVE_SOURCES
        assert "poly_total_score" in DETERMINISTIC_SOURCES
        assert authority_tier("poly_total_score") == 2
        # The sibling asymmetry the ruling closes: same input, same shape, same tier.
        assert authority_tier("poly_total_score") == authority_tier("game_score")
        assert not is_authoritative("poly_total_score")


class TestConsequenceA_JoinsTheRecomputeSet:
    """(a) It is now OVERWRITABLE by tier-3 — automatically, everywhere."""

    def test_authoritative_settlement_may_now_overwrite_it(self):
        for settled in ("api_settlement", "clob_authoritative", "datagolf_settlement"):
            assert not is_downgrade("poly_total_score", settled), (
                f"{settled} must be able to supersede a poly_total_score grade"
            )

    def test_it_still_outranks_guesses_and_terminal(self):
        # Demoting it must not make it clobberable by the poison class (#754).
        assert is_downgrade("poly_total_score", "pass2_guess")
        assert is_downgrade("poly_total_score", "clean_resolution")

    def test_it_drops_out_of_every_authoritative_write_shield(self):
        # The phases guard writes with
        #   COALESCE(resolution_source,'') NOT IN <AUTHORITATIVE_SOURCES_SQL>
        # so leaving the set IS joining the recompute set — no phase edits needed.
        assert "'poly_total_score'" not in AUTHORITATIVE_SOURCES_SQL
        assert "'api_settlement'" in AUTHORITATIVE_SOURCES_SQL


class TestConsequenceB_CanWriteWinnerTightens:
    """(b) It may no longer grade a market that is not resolved/closed.

    MEASURED COVERAGE DELTA: 0. Production census 2026-08-12 (admin db-query):
    7,468 futures_outcomes carry resolution_source='poly_total_score', and all
    7,468 sit on markets with status='resolved' — zero on any other status. The
    writer's own query filters `m.status = 'resolved'`, which is why the delta is
    0 by construction and not by luck; the test below pins that filter.
    """

    def test_it_can_no_longer_write_on_an_unsettled_market(self):
        assert can_write_winner("open", "poly_total_score") is False
        assert can_write_winner("suspended", "poly_total_score") is False
        assert can_write_winner(None, "poly_total_score") is False
        # …while a real settlement still is self-justifying on any status.
        assert can_write_winner("open", "api_settlement") is True

    def test_it_still_writes_on_the_only_statuses_it_ever_targets(self):
        assert can_write_winner("resolved", "poly_total_score") is True
        assert can_write_winner("closed", "poly_total_score") is True

    def test_the_writer_only_selects_resolved_markets_so_delta_is_zero(self):
        # This is the measurement's guarantee: if a later edit widens the writer
        # past `resolved`, the tightened predicate WOULD start dropping writes,
        # and this test is what makes that visible instead of silent.
        src = inspect.getsource(_resolve_polymarket_total_from_scores)
        assert "m.status = 'resolved'" in src
        assert "resolution_source = 'poly_total_score'" in src


class TestConsequenceC_CalibrationTruthIsUnchanged:
    """(c) The published calibration curve does not move by a single outcome.

    Eligibility is (AUTHORITATIVE - PRICE_DERIVED) | DETERMINISTIC | {date_passed},
    so a move BETWEEN those two tiers is invisible to it. Asserted explicitly so
    nobody re-litigates 038 as a calibration change.
    """

    # The eligible set as it stood BEFORE the move — mirrored as a literal on
    # purpose (the same discipline as scripts/probe_chunk_unit_plan.py, which
    # carries this list and whose probe-3 population must not drift).
    _ELIGIBLE_BEFORE_038 = frozenset({
        "api_settlement", "box_score", "box_score_bound", "clob_authoritative",
        "clob_field_repair", "clob_never_graded", "clob_ordinal",
        "datagolf_matchup", "datagolf_played_lost", "datagolf_settlement",
        "date_passed", "game_score", "leaderboard", "poly_total_score",
        "scoring_plays",
    })

    def test_the_eligible_set_is_byte_for_byte_what_it_was(self):
        assert CALIBRATION_TRUTH_ELIGIBLE_SOURCES == self._ELIGIBLE_BEFORE_038

    def test_poly_total_score_is_still_eligible_to_grade_a_forecast(self):
        assert is_calibration_truth_eligible("poly_total_score") is True
        assert "'poly_total_score'" in CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL

    def test_only_its_reporting_LABEL_moves_not_its_eligibility(self):
        # The one visible change: it reports under the deterministic bucket now
        # instead of the authoritative one. Same eligibility, different label —
        # any census that groups BY class will see the count shift buckets.
        assert calibration_truth_class("poly_total_score") == "deterministic_independent"
        assert calibration_truth_class("game_score") == "deterministic_independent"


class TestInvariantNoTierThreeReadsOurEvents:
    """(d) The ruling's invariant, guarded: adding a circular source to tier 3
    in future turns this suite red."""

    def test_no_authoritative_source_grades_from_our_events_columns(self):
        offenders = AUTHORITATIVE_SOURCES & EVENTS_DERIVED_SOURCES
        assert offenders == frozenset(), (
            f"ruling 038 violated: {sorted(offenders)} grade(s) from our own "
            "`events` columns while sitting in AUTHORITATIVE_SOURCES. A grade "
            "computed from our data cannot carry a venue's unoverwritable "
            "authority — move it to DETERMINISTIC_SOURCES (tier 2)."
        )

    def test_every_events_derived_source_is_exactly_tier_two(self):
        for s in EVENTS_DERIVED_SOURCES:
            assert s in KNOWN_SOURCES, f"{s} is unclassified in the ladder"
            assert authority_tier(s) == 2, (
                f"{s} reads our own events columns; tier 2 is where such a grade "
                "belongs (recomputable, overwritable by a real settlement)"
            )

    def test_the_maintained_set_stays_honest_about_backfill_writes(self):
        # A real scan, not a restatement of the constant: any function in the
        # backfill task that BOTH reads our events score/box-score columns AND
        # assigns a resolution_source must not be assigning a tier-3 one.
        #
        # NB the module MUST be reached via importlib — `from app.tasks import
        # backfill_winners` resolves to the celery TASK of the same name defined
        # in app/tasks/__init__.py, whose vars() is empty, which would make this
        # whole guard silently vacuous.
        import importlib
        import re

        bw = importlib.import_module("app.tasks.backfill_winners")

        events_read = re.compile(
            r"\be\.home_score\b|\be\.away_score\b|\bbox_score_data\b"
            r"|\brow\.home_score\b|\brow\.away_score\b"
        )
        assigns = re.compile(r"resolution_source\s*=\s*['\"]([a-z0-9_]+)['\"]")

        scanned = 0
        discovered: set[str] = set()
        circular_tier3: dict[str, list[str]] = {}
        for name, fn in vars(bw).items():
            if not inspect.isfunction(fn) or fn.__module__ != bw.__name__:
                continue
            scanned += 1
            try:
                src = inspect.getsource(fn)
            except OSError:  # pragma: no cover - source always available in repo
                continue
            if not events_read.search(src):
                continue
            written = set(assigns.findall(src))
            discovered |= written
            offending = sorted(written & AUTHORITATIVE_SOURCES)
            if offending:
                circular_tier3[name] = offending

        # Non-vacuity: a guard that scans nothing passes for the wrong reason.
        assert scanned > 20, f"only {scanned} functions scanned — guard went vacuous"
        assert discovered, "no events-derived resolution writes found — guard vacuous"

        assert circular_tier3 == {}, (
            "ruling 038 violated in backfill_winners.py — these functions read "
            f"our own events columns and write a TIER-3 source: {circular_tier3}. "
            "Either the grade is not from the venue (demote it to tier 2 and add "
            "it to EVENTS_DERIVED_SOURCES) or the events read is only for "
            "matching (split the write out of the function)."
        )

        # …and the maintained set is honest in the other direction: everything
        # the scan finds grading from events is already declared.
        assert discovered <= EVENTS_DERIVED_SOURCES, (
            f"undeclared events-derived source(s): "
            f"{sorted(discovered - EVENTS_DERIVED_SOURCES)} — add them to "
            "EVENTS_DERIVED_SOURCES so the tier-3 invariant covers them."
        )

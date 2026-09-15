"""Alex's quarantine ruling actually reaches the published curve (#6275, #1902).

Queue 363 item 4 ruled the date-disagreement outcomes out of the published
calibration curves, and its verify line names BOTH halves:

    "the published curve excludes them AND the page states the exclusion with
     its count; a silent drop fails this item."

``app/utils/market_identity.py`` was lifted out of the census script for exactly
this consumer — its docstring says so — and then the consumer never arrived.
``market_identity_disputed`` had one non-test caller in the tree and it was
still the census script, so the rows were graded into the published curves while
``frontend/app/calibration/page.tsx`` rendered a "Held out, under review"
section off a ``quarantine`` key the payload did not serve. A reader was told
nothing, and the curve was quietly wrong.

These tests are the standing guard on that. They are deliberately about WIRING
rather than about the predicate — the predicate has its own unit tests
(``test_market_identity_quarantine_q363.py``) and its SQL twin has a real-server
differential (``integration/test_market_identity_quarantine_sql_real_postgres.py``).
What was missing for months was not a correct predicate. It was a call site.
"""

from __future__ import annotations

import inspect
import re

import pytest

from app.tasks import precompute_calibration as pc
from app.utils.calibration_coverage_bridge import RUNG_KEYS
from app.utils.market_identity import (
    IDENTITY_DISPUTED_CTE,
    QUARANTINE_READER_REASON,
    QUARANTINE_REASON,
)

#: The rung key the coverage bridge and the population chain must agree on.
RUNG = "identity_disputed"


@pytest.fixture(scope="module")
def population_sql() -> str:
    """The real rendered population chain, defaults and all."""
    return pc._calibration_population_ctes()


class TestTheExclusionIsActuallyApplied:
    """Half one of the ruling: the published curve excludes them."""

    def test_the_quarantine_ctes_are_in_the_population_chain(self, population_sql):
        assert f"{IDENTITY_DISPUTED_CTE} AS (" in population_sql, (
            "the quarantine CTE is absent from the canonical population chain — "
            "this is the #6275 defect exactly: a predicate in app/ that the "
            "payload never consumes"
        )

    def test_deduped_drops_the_disputed_rows(self, population_sql):
        """The one line that makes the page's copy true.

        ``deduped`` IS the final published population. A flag that is computed
        and carried but never filtered on is the defect wearing a fix.
        """
        deduped = population_sql[population_sql.index("deduped AS ("):]
        assert "AND NOT ro.is_identity_disputed" in deduped, (
            "is_identity_disputed is computed but `deduped` does not filter on "
            "it, so the disputed rows are still published"
        )

    def test_the_flag_is_derived_from_the_quarantine_cte(self, population_sql):
        assert "(idm.market_id IS NOT NULL) AS is_identity_disputed" in population_sql
        assert (
            f"LEFT JOIN {IDENTITY_DISPUTED_CTE} idm ON idm.market_id = fo.market_id"
            in population_sql
        ), "the flag is not joined to anything, so it can only ever be false"

    def test_a_disputed_member_makes_its_field_incomplete(self, population_sql):
        """The quarantine is market-level, so a field loses EVERY member.

        Both survivor counters must name it, or a normalized field could be
        published over a survivor set the exclusion already emptied.
        """
        assert population_sql.count("AND NOT ro.is_identity_disputed") >= 3, (
            "expected the flag in `deduped` and in BOTH field_completeness "
            "survivor filters"
        )

    def test_the_predicate_is_imported_not_restated(self):
        """A second copy of the regex in the task is the drift the lift forbade."""
        src = inspect.getsource(pc)
        assert "from app.utils.market_identity import" in src
        assert not re.search(r"\[A-Z\]\{3\}", src), (
            "the calibration task has grown its own copy of the ticker-date "
            "pattern — it must render it from app.utils.market_identity"
        )


class TestTheCountIsActuallyDisclosed:
    """Half two of the ruling: the page states the exclusion with its count.

    "a silent drop fails this item" — so shipping only the class above would
    trade one dishonesty for another.
    """

    def test_the_payload_serves_the_key_the_page_reads(self):
        src = inspect.getsource(pc)
        assert '"quarantine": (' in src, (
            "frontend/app/calibration/page.tsx renders its held-out section off "
            "`data.quarantine`; without this key the section renders nothing "
            "and the exclusion is silent"
        )

    def test_the_counters_are_measured_over_the_population(self):
        """In ``liq_summary``, which the payload builder appends to the chain —
        so the count is taken over the SAME rows the exclusion acts on rather
        than by a second query that could scope itself differently (the C14
        drift lesson)."""
        src = inspect.getsource(pc)
        assert (
            "COUNT(*) FILTER (WHERE is_identity_disputed) AS identity_disputed_excluded"
            in src
        )
        assert (
            "COUNT(DISTINCT market_id) FILTER (WHERE is_identity_disputed)" in src
        )
        # and it has to survive the rollup into published_summary, or the
        # payload reads zero while the population excluded thousands.
        assert "MAX(ls.identity_disputed_excluded) AS identity_disputed_excluded" in src
        assert 'identity_disputed_excluded = _int0("identity_disputed_excluded")' in src

    def test_the_printed_reason_is_plain_words(self):
        """Notice 34: the page renders `reason` verbatim, so it is reader copy.

        The machine key rides in `note`, which the page deliberately does not
        render.
        """
        assert QUARANTINE_REASON not in QUARANTINE_READER_REASON, (
            "the machine key would print on a reader's screen"
        )
        assert "_" not in QUARANTINE_READER_REASON
        for jargon in ("ticker", "external_id", "predicate", "quarantine", "CTE"):
            assert jargon.lower() not in QUARANTINE_READER_REASON.lower(), (
                f"{jargon!r} is jargon on a reader's screen (notice 34)"
            )

    def test_the_note_carries_the_machine_key_for_probes(self):
        src = inspect.getsource(pc)
        assert '"note": f"{QUARANTINE_REASON}: {QUARANTINE_RULE_TEXT}"' in src

    def test_an_empty_quarantine_is_served_as_a_checked_zero(self):
        """gotcha #53: an absent key and an empty list are not the same claim.

        An omitted key says "we never looked"; `[]` says "we checked and there
        is nothing held". The page hides the section either way, so this costs a
        reader nothing and tells every probe the truth.
        """
        src = inspect.getsource(pc)
        block = src[src.index('"quarantine": ('):]
        block = block[: block.index("\n        ),")]
        assert "else []" in block, (
            "the quarantine key must serve [] when nothing is held, never be "
            "omitted"
        )


class TestTheCoveragePathAccountsForIt:
    """The bridge's own note: a NEW `deduped` filter silently lands in the
    catch-all unless it is given a rung. That would misreport quarantined rows
    as "not the representative row"."""

    def test_the_rung_exists_in_the_shared_contract(self):
        assert RUNG in RUNG_KEYS

    def test_the_population_chain_claims_the_rung(self):
        keys = [k for k, _pred in pc._COVERAGE_RUNG_PREDICATES]
        assert RUNG in keys
        pred = dict(pc._COVERAGE_RUNG_PREDICATES)[RUNG]
        assert "is_identity_disputed" in pred
        assert pred.startswith("COALESCE("), (
            "a NULL flag must route as not-published, exactly as `deduped` "
            "would treat it, rather than falling through to the catch-all"
        )

    def test_the_two_rung_lists_are_the_same_list_in_the_same_order(self):
        """First match wins, so order is semantics, not presentation."""
        assert [k for k, _p in pc._COVERAGE_RUNG_PREDICATES] == list(RUNG_KEYS)

    def test_the_rung_outranks_the_result_shape_rungs(self):
        """Which game's truth this row pairs with precedes whether that truth is
        well-shaped. Ordered after it, `malformed_or_unknown_truth` claims the
        rows first and the bridge reports a near-zero quarantine while the
        payload reports thousands — two numbers for one population."""
        keys = list(RUNG_KEYS)
        assert keys.index(RUNG) < keys.index("malformed_or_unknown_truth")
        assert keys.index(RUNG) < keys.index("representative_not_selected")

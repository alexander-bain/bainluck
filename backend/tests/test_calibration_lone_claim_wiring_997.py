"""CAL-P1138 (#997, D112): the lone-claim widening, WHERE IT IS AND WHERE IT IS NOT.

`98f75b9bc9` built the substrate — the predicate, the renderer that emits the
source half and the shape half as one unit, and the symmetry gate. CERT-2550
blocked it for the right reason: the served eligibility paths still used the
shape-blind constant, so the substrate changed no published row. That wiring is
what this file guards, and the thing it has to get right is not "is the helper
called" but WHICH SITES and, just as much, WHICH SITES NOT.

There are eight interpolations of the eligibility allowlist in the producer and
they do not all want the same answer:

  * ONE is the published population (`ranked_outcomes`) and MUST widen — that
    site is the entire ship;
  * ONE is a NEGATION (the coverage bridge's `truth_ineligible_source` rung) and
    must widen IN STEP, or the bridge tells a reader that a row the curve now
    grades has an ineligible truth source. This is the site a sweep skips,
    because `NOT` reads like the same predicate and is not;
  * FOUR are auxiliary population CTEs that cannot see a one-outcome market at
    all — each carries a cardinality floor (>= 2 or >= 3 members) that a lone
    claim can never clear. They stay shape-blind ON PURPOSE. Widening them would
    mean adding a shape join to aggregating CTEs for zero population effect,
    which is ruling 125's hazard taken on for nothing;
  * TWO are diagnostics over DIFFERENT shapes (the Query-11 truth census and the
    cross-venue fair-fight scan) with no per-market outcome count in scope.

The inert four are the interesting half of this file. "It is inert" is exactly
the kind of claim that rots silently: the day someone relaxes `HAVING COUNT(*)
>= 3`, the inertness ends and nothing would have said so. So the floors are
asserted here, against the SQL THE PRODUCER ACTUALLY RENDERS rather than against
its source text — a source-scan would pass just as happily on a floor that had
been commented out in a string the builder no longer emits.
"""

from __future__ import annotations

import re

import pytest

import app.tasks.precompute_calibration as pc
from app.utils.resolution_authority import (
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
    LONE_CLAIM_TRUTH_ELIGIBLE_SOURCES_SQL,
)


@pytest.fixture(scope="module")
def population_sql() -> str:
    """The real population CTE chain, rendered with production defaults."""
    return pc._calibration_population_ctes()


@pytest.fixture(scope="module")
def coverage_sql(monkeypatch_module) -> str:
    """The real coverage-bridge CTEs, rendered WITH THE CENSUS ENABLED.

    `COVERAGE_CENSUS_ENABLED` is False in production (CAL-P024 turned it off on
    a measured ~10x per-unit cost) and the builder then emits the empty string.
    That is the whole reason the `truth_ineligible_source` rung is easy to leave
    behind: it costs nothing today and is wrong the moment the census comes
    back. Rendering it here is what makes the guard real rather than a test that
    asserts things about `""`.
    """
    monkeypatch_module.setattr(pc, "COVERAGE_CENSUS_ENABLED", True)
    sql = pc._coverage_bridge_ctes()
    assert sql, "the census renders nothing even when enabled"
    return sql


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()


def _strip_sql_comments(sql: str) -> str:
    """Drop `--` comments. Not cosmetic — the paren balance depends on it.

    Found by a surviving mutation rather than by inspection, which is the only
    reason it is written down here. Relaxing `mex_field_candidates`' floor from
    3 to 2 left `test_d112_inert_cte_cardinality_floors` GREEN: the extractor
    below counts parentheses, this file's SQL is heavily commented, and the
    prose contains unbalanced ones (`-- (the structure test — ...` opens a group
    it closes two lines later, and several `#4456`-style references never close
    at all). The balance therefore never reached zero at the real end of the
    CTE and the extracted "body" ran on into later CTEs — so the assertion was
    reading a `HAVING COUNT(*) >= 3` that belonged to a different scan and
    would have passed on almost any floor. A guard that cannot fail is worse
    than no guard, because it is counted.
    """
    return "\n".join(line.split("--")[0] for line in sql.split("\n"))


def _cte_body(sql: str, name: str) -> str:
    """The text of one named CTE, from `name AS (` to the matching close.

    Written by paren-balance rather than by regex: these CTEs contain nested
    parentheses (function calls, sub-selects, tuple literals), so a
    non-greedy match to the first `)` truncates the body and would silently
    hide the very `HAVING` clause this file exists to assert.

    Comments are stripped FIRST — see `_strip_sql_comments` for the mutation
    that proved why.
    """
    sql = _strip_sql_comments(sql)
    # `AS MATERIALIZED (` is the form `ranked_outcomes` uses, and a marker that
    # only knows `AS (` raises "substring not found" on the one CTE that matters
    # most here — a failure that reads like a missing CTE rather than a missing
    # keyword.
    for marker in (f"{name} AS MATERIALIZED (", f"{name} AS ("):
        if marker in sql:
            break
    else:
        raise AssertionError(f"CTE {name!r} is not in the rendered SQL")
    start = sql.index(marker) + len(marker)
    depth = 1
    for i in range(start, len(sql)):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return sql[start:i]
    raise AssertionError(f"CTE {name!r} is not closed in the rendered SQL")


# ---------------------------------------------------------------------------
# The ship: the published population widens.
# ---------------------------------------------------------------------------


def test_the_published_population_scan_applies_the_lone_claim_shape(population_sql):
    """`ranked_outcomes` is the site D112 exists for.

    If this is the only test that survives a refactor, it is the right one to
    keep: every other assertion in this file is about not breaking something,
    and this one is about the change reaching a reader.
    """
    body = _cte_body(population_sql, "ranked_outcomes")

    assert LONE_CLAIM_TRUTH_ELIGIBLE_SOURCES_SQL in body, (
        "the published population does not admit the lone-claim pair — D112 is "
        "substrate again, exactly the state CERT-2550 blocked"
    )
    # Admitted only AT the shape, and through the shape column the ladder arm
    # already put in scope. A bare pair with no `= 1` beside it would widen into
    # multi-outcome markets, where a sibling's price really does grade the row.
    assert "COALESCE(mrs_lad.n_outcomes, 0) = 1" in body


def test_the_population_scan_still_joins_the_shape_it_reads(population_sql):
    """The predicate is worth nothing if the column is not in scope.

    A missing join does not raise here — it raises in Postgres, hours into a
    rebuild, on the one statement that publishes. And the join has to stay LEFT:
    an inner join would drop every market with no shape row from the published
    population, which is a silent narrowing dressed as a widening.
    """
    body = _cte_body(population_sql, "ranked_outcomes")
    assert "LEFT JOIN market_result_shape mrs_lad" in body


# ---------------------------------------------------------------------------
# The negation: the coverage bridge must not contradict the curve.
# ---------------------------------------------------------------------------


def test_the_coverage_bridge_negation_widens_in_step(coverage_sql):
    """The rung that states eligibility BACKWARDS.

    Widen the population and leave this alone and the bridge says a row the
    curve grades has an ineligible truth source — the two halves of one payload
    disagreeing about the same outcome.
    """
    assert LONE_CLAIM_TRUTH_ELIGIBLE_SOURCES_SQL in coverage_sql, (
        "the `truth_ineligible_source` rung still uses the shape-blind list"
    )
    assert "COALESCE(mrs_cov.n_outcomes, 0) = 1" in coverage_sql
    assert "LEFT JOIN market_result_shape mrs_cov" in coverage_sql


def test_the_negated_rung_is_null_safe_in_the_rendered_sql(coverage_sql):
    """The bug this wiring actually found, asserted where it would bite.

    `NOT (src IN (...) OR (NULL = 1 AND src IN (...)))` is NULL, not TRUE, so an
    ineligible row whose market has no shape row would stop matching its own
    rung and fall through to be mislabelled. The `COALESCE` is what makes the
    shape term two-valued. Checked on the rendered statement and not only on the
    renderer's unit test, because it is the rendered text that Postgres runs.
    """
    rung = next(
        sql for key, sql in pc._COVERAGE_RUNG_PREDICATES if key == "truth_ineligible_source"
    )
    assert rung.startswith("NOT ")
    assert "COALESCE(mrs_cov.n_outcomes, 0)" in rung
    # The unguarded form must not survive anywhere in the rendered bridge.
    assert not re.search(r"mrs_cov\.n_outcomes\s*=", coverage_sql.replace(
        "COALESCE(mrs_cov.n_outcomes, 0) =", ""
    ))


# ---------------------------------------------------------------------------
# The inert four: shape-blind on purpose, and only while the floors hold.
# ---------------------------------------------------------------------------


#: CTE -> the floor that makes a one-outcome market unreachable inside it.
#: `mex_field_divisor` has no floor of its own; it inherits one by reading only
#: markets that already cleared `mex_field_candidates`, so it is asserted
#: separately below rather than fudged into this table.
_FLOORED_CTES = {
    "bundle_price_sum": 3,
    "golf_placeholder_markets": 2,
    "mex_field_candidates": 3,
}


def test_d112_inert_cte_cardinality_floors(population_sql):
    """The four shape-blind sites are unreachable, not merely unvisited.

    Each is documented at its own site as "shape-blind on purpose", and that
    comment is only true while the floor beside it holds. A lone-claim market
    has exactly one captured outcome, so it contributes at most ONE row to any
    of these per-market scans: every floor of 2 or more excludes it by
    construction. Assert the floors and the claim keeps itself honest; drop them
    and the day a floor is relaxed is the day four sites silently disagree with
    the published population about which rows are eligible.
    """
    # `bundle_price_sum` has no HAVING of its own — its floor is enforced by its
    # only consumer, which is the same guarantee reached one hop later.
    bundle_consumer = _cte_body(population_sql, "esports_multi_bundles")
    assert "mrs.n_outcomes >= 3" in bundle_consumer, (
        "bundle_price_sum's only consumer no longer floors at 3 outcomes, so a "
        "lone-claim market can now be read out of a shape-blind sum"
    )

    for cte, floor in (("golf_placeholder_markets", 2), ("mex_field_candidates", 3)):
        body = _cte_body(population_sql, cte)
        assert f"HAVING COUNT(*) >= {floor}" in body, (
            f"{cte} no longer floors at {floor} members — it can now see a "
            f"one-outcome market, so its shape-blind eligibility predicate has "
            f"stopped matching the published population"
        )

    # `mex_field_divisor` inherits the >= 3 floor by construction: it reads only
    # markets that already qualified as candidates.
    divisor = _cte_body(population_sql, "mex_field_divisor")
    assert "JOIN mex_field_candidates mfc" in divisor, (
        "mex_field_divisor no longer reads only qualified candidates, so it no "
        "longer inherits their floor and can reach a lone-claim market"
    )


def test_the_inert_four_really_are_still_shape_blind(population_sql):
    """The other direction, so this file cannot pass by doing nothing.

    A guard that only says "the floors are there" is happy on a tree where
    somebody wired all eight sites anyway. That would not be wrong in its
    results — the floors make it inert — but it would have added shape joins to
    three aggregating CTEs for no population effect, which is the risk ruling
    125 is about. So the intended shape of the change is pinned: exactly one
    population CTE reads a shape column for eligibility.
    """
    for cte in _FLOORED_CTES:
        body = _cte_body(population_sql, cte)
        assert LONE_CLAIM_TRUTH_ELIGIBLE_SOURCES_SQL not in body, (
            f"{cte} was widened; it is provably inert, so the widening buys "
            f"nothing and costs a join in an aggregating CTE"
        )
        assert CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL in body, (
            f"{cte} no longer applies the truth allowlist at all"
        )

    divisor = _cte_body(population_sql, "mex_field_divisor")
    assert LONE_CLAIM_TRUTH_ELIGIBLE_SOURCES_SQL not in divisor


def test_exactly_one_population_cte_reads_a_shape_column_for_eligibility(
    population_sql,
):
    """A census of the intended wiring, so a NEW site cannot arrive unnoticed.

    The count is the point. If a ninth eligibility site is added later and
    wired, this fails and someone has to say which site it is and why — which is
    the conversation that did not happen when the substrate landed shape-blind.
    """
    admissions = population_sql.count(LONE_CLAIM_TRUTH_ELIGIBLE_SOURCES_SQL)
    assert admissions == 1, (
        f"expected exactly one lone-claim admission in the population chain "
        f"(ranked_outcomes), found {admissions}"
    )


# ---------------------------------------------------------------------------
# The payload's own account of itself.
# ---------------------------------------------------------------------------


def test_d112_truth_evidence_rule_states_the_shape_exception():
    """`truth_evidence.rule` claimed price-derived truth is excluded.

    After D112 a subset of it — the lone-claim rows — is PUBLISHED, so the
    unqualified sentence is false. It is an operator-facing block (nothing on
    /calibration renders it), which is why this is a one-line correction and not
    a page change, but a payload that misdescribes its own rule is how the next
    reader derives a wrong number confidently.
    """
    evidence = pc._build_truth_evidence(
        {"eligible": {"outcomes": 10, "markets": 5}},
        mex_normalized_markets=1,
        mex_published_markets=1,
        published_outcomes=10,
        published_questions=10,
    )

    rule = evidence["rule"]
    assert "lone-claim" in rule.lower(), (
        "the rule still says price-derived truth is excluded, full stop — it is "
        "now excluded EXCEPT at lone-claim shape"
    )
    assert "D112" in rule
    # The old claim must not survive beside the new one.
    assert "one captured outcome" in rule

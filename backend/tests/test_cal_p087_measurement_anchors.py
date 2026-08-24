"""CAL-P087 — the measurement scripts' anchors must stay anchored.

Both scripts this queue adds work by *substitution into*, or *import from*, code
that lives elsewhere. That is deliberate — re-deriving the population is the C14
drift lesson — but it has one failure mode, and it is the flattering one:

* ``measure_2098_mode_price_collision.py`` compares a fold against a fold with
  three strings replaced. If the chain moves and a replacement silently matches
  nothing, the two folds become IDENTICAL and the script reports **zero
  collisions** — the answer everyone hopes for, produced by an instrument that
  measured nothing (gotcha #53).
* ``gate0_split_pre_read.py`` reports Gate 0's colour by calling the real
  ``reconcile``. If ``FOLD_POPULATION_SOURCES`` were widened without widening
  the fold, in-scope misses would move into the out-of-scope bucket and the
  colour would go green for a reason that is a lie.

The scripts assert both at runtime. These tests assert them in CI, where a
change to ``precompute_calibration.py`` is actually being made.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

from app.tasks.precompute_calibration import _calibration_population_ctes
from app.utils.calibration_published_twin import FOLD_POPULATION_SOURCES

_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")


def _load(name: str):
    path = os.path.join(_SCRIPTS, name)
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def collision_script():
    return _load("measure_2098_mode_price_collision.py")


def test_every_substitution_anchor_appears_exactly_once(collision_script) -> None:
    """One occurrence each — not zero (a no-op), not two (an ambiguous edit).

    CAL-P090 made this DIRECTION-AWARE, and the reason is that the defect being
    measured got fixed. Before `program/calibration-88` the chain was the
    source-BLIND one and the script substituted forwards; after it, the chain is
    the source-SCOPED one and the script reverts. Either way the instrument only
    works if all three anchors are anchored, so what this asserts is unchanged in
    substance: the chain matches exactly ONE of the two states, on all three
    anchors CONSISTENTLY.

    The consistency clause is the load-bearing half. A mixed state — say the
    GROUP BY carrying `source` while the join does not — is a half-applied edit,
    and it is precisely the state in which one substitution matches nothing, the
    two folds collapse to identical, and the measurement reports zero collisions
    having measured nothing (gotcha #53). Asserting each anchor independently
    would have permitted it.
    """
    chain = _calibration_population_ctes()
    names = ("MODE_PRICES", "MODE_GROUPBY", "JOIN")
    blind = {n: chain.count(getattr(collision_script, f"{n}_FROM")) for n in names}
    scoped = {n: chain.count(getattr(collision_script, f"{n}_TO")) for n in names}

    is_blind = all(v == 1 for v in blind.values())
    is_scoped = all(v == 1 for v in scoped.values())
    assert is_blind != is_scoped, (
        "the population chain matches NEITHER the source-blind nor the "
        "source-scoped mode_prices shape consistently, or matches both — so at "
        "least one substitution anchor would match nothing and the #2098 "
        "measurement would compare a fold against itself and report zero "
        f"collisions having measured nothing. blind_counts={blind} "
        f"scoped_counts={scoped}"
    )


def test_the_substituted_chain_actually_differs(collision_script) -> None:
    """The whole instrument is the difference between the two chains."""
    _, prod, scoped = collision_script.build_chains()
    assert prod != scoped
    assert "mp.source = ro.source" in scoped
    assert "mp.source = ro.source" not in prod
    assert "GROUP BY vm_id, source, adj_opening_probability, eligible" in scoped


def test_seed_ranges_cover_the_domain_without_gaps(collision_script) -> None:
    """A gap is an unswept range reported as a zero."""
    ranges = collision_script.seed_ranges()
    assert ranges
    assert ranges[0][0] == collision_script.EVENT_ID_LO
    assert ranges[-1][1] == collision_script.EVENT_ID_HI
    for (_, hi), (lo, _) in zip(ranges, ranges[1:]):
        assert hi == lo, f"gap between {hi} and {lo}"


def test_chunk_sql_is_one_statement(collision_script) -> None:
    from app.utils.sql_comment_strip import count_statement_separators, strip_sql_comments

    sql = collision_script.CHUNK_SQL.format(lo=1, hi=2)
    assert count_statement_separators(strip_sql_comments(sql)) == 0


def test_gate0_pre_read_reports_the_scope_it_used() -> None:
    """The census must name the sources it counted as in-scope.

    A census that reports a percentage without naming its denominator's
    membership is the shape ruling 014 exists to forbid.
    """
    mod = _load("gate0_split_pre_read.py")
    out = mod.census(
        [
            {"source": "kalshi", "category": "nba", "bucket_idx": 3, "n": 10},
            {"source": "odds_api", "category": "nba", "bucket_idx": 3, "n": 7},
        ]
    )
    assert out["fold_population_sources"] == sorted(FOLD_POPULATION_SOURCES)
    assert out["cells_in_scope"] == 1
    assert out["cells_out_of_scope"] == 1
    assert out["outcomes_in_scope"] == 10
    assert out["outcomes_out_of_scope"] == 7
    assert out["sources_out_of_scope"] == ["odds_api"]


def test_gate0_pre_read_counts_the_price_moved_collapse() -> None:
    """``reconcile`` keys without ``price_moved``, so two payload rows per cell
    collapse to one. The census must SAY how many, because that collapse is what
    makes its outcome totals smaller than the payload's own."""
    mod = _load("gate0_split_pre_read.py")
    out = mod.census(
        [
            {"source": "kalshi", "category": "nba", "bucket_idx": 3, "n": 10, "price_moved": True},
            {"source": "kalshi", "category": "nba", "bucket_idx": 3, "n": 4, "price_moved": False},
        ]
    )
    assert out["price_moved_rows_collapsed_by_reconcile"] == 1
    assert out["bucket_keys_in_scope"] == 1
    assert out["payload_bucket_rows_in_scope"] == 2


def test_rendered_cohort_port_matches_the_frontend_rounding() -> None:
    """``aggregateBuckets`` rounds ``error`` to one decimal in pp BEFORE ECE
    weights it. Computing ECE from unrounded errors gives a different number
    than the page renders, and the apply's before must be the rendered one."""
    mod = _load("pin_apply_befores.py")
    buckets = [
        # actual 0.5 vs avg 0.5432... -> error rounds to -4.3 pp, not -4.32
        {"bucket_idx": 5, "n": 1000, "winners": 500, "sum_prob": 543.2, "sum_sq_err": 0.0},
    ]
    agg = mod.aggregate_buckets(buckets, mod.COHORT_FILTER)
    assert agg[0]["error"] == pytest.approx(-4.3, abs=1e-9)
    assert mod.ece(agg) == pytest.approx(4.3, abs=1e-9)


def test_cohort_filter_keeps_null_price_moved() -> None:
    """``price_moved !== false`` — a NULL is KEPT. Treating null as excluded
    would silently shrink the denominator the page leads with."""
    mod = _load("pin_apply_befores.py")
    assert mod.COHORT_FILTER({"price_moved": True})
    assert mod.COHORT_FILTER({"price_moved": None})
    assert mod.COHORT_FILTER({})
    assert not mod.COHORT_FILTER({"price_moved": False})

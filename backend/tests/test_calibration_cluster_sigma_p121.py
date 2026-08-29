"""CAL-P121 — guards for the cluster-aware sigma rail.

The instrument these guards protect answers ONE question and it is the question
two parked items (CAL-P114-3, CAL-P120-2) have been holding open: when a
published cell's rows are not independent forecasts, what does
``SIGMA_GATE = 2.0`` actually mean?

Three claims in the CAL-P121 write-up are load-bearing and each is pinned here
rather than described:

1. **The rail is EXTENDED, not re-implemented.** ``calibration_cluster_sigma``
   adds exactly one dimension to ``calibration_cell_exact.DIMENSIONS`` and
   changes nothing else. If a future edit rebinds one of the rail's own
   dimensions from this file, every number that cites "the producer's own
   chain" stops being true and this goes red.
2. **The bootstrap resamples CLUSTERS, not ROWS.** That is the entire
   correction. A row bootstrap would reproduce ``50/sqrt(n)`` and report the
   defect as absent. The duplicate-inflation test below is the mutation guard:
   inflating every cluster tenfold must leave the measured SE alone while the
   board's ``50/sqrt(n)`` shrinks by ``sqrt(10)``.
3. **The point estimate does not move.** This instrument re-grades, re-prices
   and re-buckets nothing. Pooling the per-market bins must return the
   published cell's own ECE to the second decimal.

The thresholds and bars are IMPORTED from ``calibration_scorecard``, never
restated (CAL-P115's rule — an equal copy drifts on the next edit), and a test
asserts the identity rather than the equality.
"""

from __future__ import annotations

import importlib.util
import math
import pathlib

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sigma_mod = _load("calibration_cluster_sigma")
cce = sigma_mod.cce
cs = sigma_mod.cs


# The published kalshi/crypto cell, copied from the live /api/calibration
# payload at 2026-08-29T00:36:47Z (population q268). These ten rows ARE the
# board's rank-6 row, so they are the right thing to pin an arithmetic claim to.
PUBLISHED_CRYPTO = {
    0: {"n": 1488, "w": 12, "sp": 60.445},
    1: {"n": 275, "w": 15, "sp": 37.415},
    2: {"n": 201, "w": 21, "sp": 48.68},
    3: {"n": 133, "w": 23, "sp": 46.625},
    4: {"n": 124, "w": 26, "sp": 55.55},
    5: {"n": 303, "w": 237, "sp": 160.745},
    6: {"n": 299, "w": 231, "sp": 187.745},
    7: {"n": 268, "w": 213, "sp": 200.915},
    8: {"n": 367, "w": 311, "sp": 313.08},
    9: {"n": 1107, "w": 990, "sp": 1051.645},
}


def _synthetic_clusters(k: int, rows_each: int = 4, seed: int = 7):
    """``k`` markets, each a handful of rows spread over the deciles.

    Deterministic and deliberately heterogeneous: a homogeneous population
    would make every bootstrap statistic zero and the guards below vacuous.
    """
    import random

    rng = random.Random(seed)
    out = []
    for i in range(k):
        bins: dict[int, dict] = {}
        for _ in range(rows_each):
            b = rng.randrange(10)
            p = (b + 0.5) / 10
            v = bins.setdefault(b, {"n": 0, "w": 0, "sp": 0.0})
            v["n"] += 1
            v["w"] += 1 if rng.random() < p * 0.8 else 0
            v["sp"] += p
        out.append(bins)
    return out


def _inflate(clusters, factor: int):
    """Every cluster's rows duplicated ``factor`` times, in place of nothing.

    This is CAL-P120's ``odds_api_bookmaker`` defect in a test tube: one real
    outcome published as ``factor`` byte-identical rows.
    """
    return [
        {
            b: {"n": v["n"] * factor, "w": v["w"] * factor, "sp": v["sp"] * factor}
            for b, v in c.items()
        }
        for c in clusters
    ]


# ---------------------------------------------------------------------------
# 1. The rail is extended, not re-implemented
# ---------------------------------------------------------------------------


def test_marketid_dimension_is_registered():
    assert "marketid" in cce.DIMENSIONS
    assert cce.DIMENSIONS["marketid"] == sigma_mod.MARKETID_DIMENSION


def test_the_cluster_key_is_the_market_and_nothing_else():
    expr, join, pre = cce.DIMENSIONS["marketid"]
    assert expr.strip() == "d.market_id::text"
    # A join or an extra CTE would mean the cluster key depends on something
    # outside ``deduped``, and a cluster that is not exactly one published
    # market is not the unit this instrument claims to count.
    assert join == ""
    assert pre == ""


@pytest.mark.parametrize(
    "dim",
    [
        "none",
        "age",
        "series",
        "shape",
        "sumband",
        "pair",
        "pairtype",
        "pairsum",
        "policy",
        "cpdrift",
        "policy2",
        "price_moved",
        "market_type",
    ],
)
def test_registration_is_additive_every_shipped_dimension_survives(dim):
    """The rail shipped with these and CAL-P114/117/118's numbers cite them."""
    assert dim in cce.DIMENSIONS


#: Every dimension the rail ships, bound to the rail's OWN named constants.
#: Comparing against these — not against a value read back out of the table
#: after import — is what makes the guard catch an IMPORT-TIME rebinding. A
#: mutation test caught the earlier version of this guard reading the corrupted
#: value and comparing it to itself.
SHIPPED_DIMENSIONS = {
    "none": ("'all'", "", ""),
    "age": ("AGE_EXPR", "AGE_JOIN", ""),
    "series": ("SERIES_EXPR", "SERIES_JOIN", ""),
    # Added to the RAIL by CAL-P127. It belongs here, not in the "added by
    # this module" set below: `calibration_cluster_sigma` still contributes
    # exactly `marketid`. CAL-P127 registered it without extending this pinned
    # copy, which turned `test_this_module_adds_exactly_one_dimension_and_no_more`
    # red on the program branch — a guard accusing the wrong file. Listing it
    # here also puts `golfround` under the rebinding guard below, which is
    # where a new rail dimension wants to be anyway.
    "golfround": ("GOLFROUND_EXPR", "GOLFROUND_JOIN", ""),
    "shape": ("SHAPE_EXPR", "SHAPE_JOIN", ""),
    "sumband": ("SUMBAND_EXPR", "SUMBAND_JOIN", "SUMBAND_PRE"),
    # Added to the RAIL by CAL-P130, for the same reason and in the same place
    # as `golfround` above — this module still contributes exactly `marketid`.
    # CAL-P127's note predicted this exact re-occurrence and it duly re-occurred:
    # registering a rail dimension without extending this pinned copy turns the
    # guard below red against the wrong file. Caught by running the SIBLING
    # suites, which is CAL-P128's lesson and the only thing that finds it.
    "slotratio": ("SLOTRATIO_EXPR", "SLOTRATIO_JOIN", "SUMBAND_PRE"),
    # Added to the RAIL by CAL-P131, third time in a row for the same reason.
    # CAL-P127 predicted it, CAL-P130 hit it anyway, and this entry is written
    # in the same commit as the registration rather than after the sibling
    # suite went red. `calibration_cluster_sigma` still contributes exactly
    # `marketid`.
    "bandratio": ("BANDRATIO_EXPR", "BANDRATIO_JOIN", "BANDRATIO_PRE"),
    # Added to the RAIL by CAL-P132, fourth time in a row. Same commit as the
    # registration, same reason as the three notes above; nothing new to say
    # except that the note is now load-bearing enough that a fifth dimension
    # should read it before touching `DIMENSIONS`.
    # `calibration_cluster_sigma` still contributes exactly `marketid`.
    "twin": ("TWIN_EXPR", "TWIN_JOIN", "TWIN_PRE"),
    "pair": ("PAIR_EXPR", "PAIR_JOIN", ""),
    "pairtype": ("PAIRTYPE_EXPR", "PAIR_JOIN", ""),
    "pairsum": ("PAIRSUM_EXPR", "PAIRSUM_JOIN", "SUMBAND_PRE"),
    "policy": ("POLICY_EXPR", "POLICY_JOIN", "SUMBAND_PRE"),
    "cpdrift": ("DRIFT_EXPR", "DRIFT_JOIN", ""),
    "policy2": ("POLICY2_EXPR", "POLICY2_JOIN", "SUMBAND_PRE"),
}


def _resolve(slot):
    """A slot is either a literal or the NAME of a constant on the rail."""
    return getattr(cce, slot) if slot and slot.isidentifier() else slot


@pytest.mark.parametrize("dim", sorted(SHIPPED_DIMENSIONS))
def test_registration_does_not_rebind_an_existing_dimension(dim):
    """``setdefault``, not ``[...] =``. Importing this file must not silently
    change what ``--by shape`` means.

    Pinned against the rail's own module-level constants, so an import-time
    rebinding by ``calibration_cluster_sigma`` is caught. Reading the table and
    comparing it to itself is NOT a guard — that version survived mutation M2.
    """
    expected = tuple(_resolve(slot) for slot in SHIPPED_DIMENSIONS[dim])
    assert cce.DIMENSIONS[dim] == expected


def test_this_module_adds_exactly_one_dimension_and_no_more():
    added = (
        set(cce.DIMENSIONS) - set(SHIPPED_DIMENSIONS) - {"price_moved", "market_type"}
    )
    assert added == {"marketid"}


def test_the_source_never_subscript_assigns_into_the_rail_s_table():
    """The mechanical form of the same rule, so it cannot be re-introduced by a
    line that happens to assign the same value today."""
    import ast

    tree = ast.parse(_read_source())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if (
                isinstance(t, ast.Subscript)
                and isinstance(t.value, ast.Attribute)
                and t.value.attr == "DIMENSIONS"
            ):
                raise AssertionError(
                    "cce.DIMENSIONS[...] = ... at line %d — use setdefault"
                    % node.lineno
                )


def test_setdefault_is_still_how_the_dimension_is_registered():
    assert "cce.DIMENSIONS.setdefault(" in _read_source()


def test_thresholds_are_the_scorecard_s_own_objects_not_copies():
    assert sigma_mod.cs.SIGMA_GATE is cs.SIGMA_GATE
    assert sigma_mod.cs.CLASS_BARS_PP is cs.CLASS_BARS_PP
    # ...and no module-level rebinding of either name. The docstring is allowed
    # to NAME them — quoting the thing you import is not copying it — so the
    # scan is over assignment statements, parsed, not over the raw text.
    import ast

    tree = ast.parse(_read_source())
    bound = {
        t.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for t in node.targets
        if isinstance(t, ast.Name)
    }
    assert "SIGMA_GATE" not in bound
    assert "CLASS_BARS_PP" not in bound
    assert "cell_se_pp" not in bound


def _read_source() -> str:
    return (_SCRIPTS / "calibration_cluster_sigma.py").read_text()


def test_the_instrument_is_read_only():
    """Ruling 134: measurement never writes. No DML reaches the database."""
    src = _read_source().upper()
    for verb in ("INSERT INTO", "UPDATE ", "DELETE FROM", "ALTER ", "DROP "):
        assert verb not in src, verb


# ---------------------------------------------------------------------------
# 2. The point estimate does not move
# ---------------------------------------------------------------------------


def test_pooling_clusters_reproduces_the_published_cell():
    """Split the published cell across markets arbitrarily; pooling must give
    the payload's own 7.60 pp / +1.84 pp back."""
    clusters = []
    for b, v in PUBLISHED_CRYPTO.items():
        half = v["n"] // 2
        clusters.append({b: {"n": half, "w": v["w"] // 2, "sp": v["sp"] / 2}})
        clusters.append(
            {b: {"n": v["n"] - half, "w": v["w"] - v["w"] // 2, "sp": v["sp"] / 2}}
        )
    pooled: dict[int, dict] = {}
    for c in clusters:
        for b, v in c.items():
            p = pooled.setdefault(b, {"n": 0, "w": 0, "sp": 0.0})
            p["n"] += v["n"]
            p["w"] += v["w"]
            p["sp"] += v["sp"]
    n, ece, gap = cce.fold(pooled)
    assert n == 4565
    assert ece == pytest.approx(7.60, abs=0.02)
    assert gap == pytest.approx(1.84, abs=0.02)


def test_cluster_bins_is_a_shape_change_not_an_aggregation():
    by_key = {
        "10": {0: {"n": 3, "w": 1, "sp": 0.15}, 5: {"n": 2, "w": 2, "sp": 1.1}},
        "11": {9: {"n": 7, "w": 6, "sp": 6.5}},
    }
    clusters = sigma_mod.cluster_bins(by_key)
    assert len(clusters) == 2
    assert sum(v["n"] for c in clusters for v in c.values()) == 12


# ---------------------------------------------------------------------------
# 3. The bootstrap resamples CLUSTERS, and that is the whole correction
# ---------------------------------------------------------------------------


def test_bootstrap_is_seeded_and_reproducible():
    clusters = _synthetic_clusters(120)
    _, se_a = sigma_mod.bootstrap_ece(clusters, boot=200, seed=1234)
    _, se_b = sigma_mod.bootstrap_ece(clusters, boot=200, seed=1234)
    assert se_a == se_b


def test_a_different_seed_moves_the_se_only_a_little():
    """If reseeding moves the SE materially at the shipped resample count, the
    verdict is a coin flip and the default ``--boot`` is too small."""
    clusters = _synthetic_clusters(200)
    _, se_a = sigma_mod.bootstrap_ece(clusters, boot=sigma_mod.DEFAULT_BOOT, seed=1)
    _, se_b = sigma_mod.bootstrap_ece(clusters, boot=sigma_mod.DEFAULT_BOOT, seed=2)
    assert abs(se_a - se_b) / max(se_a, se_b) < 0.10


def test_duplicating_every_row_within_a_cluster_does_not_shrink_the_measured_se():
    """THE MUTATION GUARD. This is CAL-P120's defect, and the board's own
    ``50/sqrt(n)`` fails it by construction.

    Ten byte-identical copies of every row carry no new information. The
    cluster bootstrap must say so; ``cell_se_pp`` cannot.
    """
    clusters = _synthetic_clusters(150)
    inflated = _inflate(clusters, 10)

    _, se_plain = sigma_mod.bootstrap_ece(clusters, boot=400, seed=99)
    _, se_inflated = sigma_mod.bootstrap_ece(inflated, boot=400, seed=99)
    assert se_inflated == pytest.approx(se_plain, rel=1e-9)

    n_plain = sum(v["n"] for c in clusters for v in c.values())
    n_inflated = sum(v["n"] for c in inflated for v in c.values())
    assert cs.cell_se_pp(n_inflated) == pytest.approx(
        cs.cell_se_pp(n_plain) / math.sqrt(10), rel=1e-9
    )


def test_a_row_bootstrap_would_have_missed_it():
    """The counterfactual, stated as arithmetic rather than as a claim.

    Splitting every cluster into one-row clusters IS a row bootstrap. On
    tenfold-inflated data it reports a shrinking SE — the exact failure this
    instrument exists to avoid.
    """
    clusters = _synthetic_clusters(150)
    rows = [
        {b: {"n": 1, "w": v["w"] / v["n"], "sp": v["sp"] / v["n"]}}
        for c in clusters
        for b, v in c.items()
    ]
    rows10 = [dict(r) for r in rows for _ in range(10)]
    _, se_rows = sigma_mod.bootstrap_ece(rows, boot=300, seed=5)
    _, se_rows10 = sigma_mod.bootstrap_ece(rows10, boot=300, seed=5)
    assert se_rows10 < se_rows * 0.5


def test_more_clusters_shrinks_the_se():
    """Sanity: the correction must still be a standard error."""
    _, se_small = sigma_mod.bootstrap_ece(_synthetic_clusters(60), boot=400, seed=3)
    _, se_big = sigma_mod.bootstrap_ece(_synthetic_clusters(600), boot=400, seed=3)
    assert se_big < se_small


def test_a_single_cluster_cannot_produce_a_verdict():
    samples, se = sigma_mod.bootstrap_ece(_synthetic_clusters(1), boot=50, seed=3)
    # One cluster resampled with replacement is always itself: zero spread.
    # The instrument must not turn that into an infinite sigma silently, which
    # is why the caller reads ``clusters`` alongside the sigma.
    assert se == pytest.approx(0.0, abs=1e-12)
    assert len(samples) == 50


def test_percentile_is_ordered_and_bounded():
    xs = [3.0, 1.0, 2.0, 5.0, 4.0]
    assert sigma_mod.percentile(xs, 0.0) == 1.0
    assert sigma_mod.percentile(xs, 1.0) == 5.0
    assert 1.0 <= sigma_mod.percentile(xs, 0.5) <= 5.0
    assert math.isnan(sigma_mod.percentile([], 0.5))


# ---------------------------------------------------------------------------
# 4. The verdict this cell's numbers produce
# ---------------------------------------------------------------------------


def test_rank_six_is_established_at_the_bar_it_is_scored_against():
    """kalshi/crypto is class C, bar 3.0, ECE 7.60 — and the CAL-P121 finding is
    that the cluster correction does NOT rescue it.

    Pinned so that a future edit to ``classify`` or ``CLASS_BARS_PP`` that would
    silently move this cell off the board has to say so here first.
    """
    assert cs.classify("kalshi", "crypto") == "C_exchange_standalone"
    assert cs.CLASS_BARS_PP["C_exchange_standalone"] == 3.0
    excess = 7.60 - 3.0
    # measured 2026-08-29, 625 markets, 2,000 resamples, seed 20260829
    assert excess / 0.645 > cs.SIGMA_GATE
    # and it clears the gate on the pessimistic market-count bound too
    assert excess / cs.cell_se_pp(625) > cs.SIGMA_GATE

"""CAL-P131 — guards for the ``bandratio`` dimension.

``bandratio`` asks whether a market's OUTCOME NAMES declare a partition of the
real line, and if they do, whether the published prices sum like one.

It exists because neither of the two sum dimensions already on the rail can
answer ``polymarket/economics``:

* ``sumband`` bands the raw published sum against 1 and splits the cell on
  ``sh.mw``, the realized win count. The cell is dominated by NESTED THRESHOLD
  LADDERS — *"Will Apple (AAPL) close above $255 / $260 / $265 ... on August
  5?"* — whose rungs are not mutually exclusive. A coherent thirteen-rung ladder
  sums to the expected number of rungs that hit, anywhere in ``[0, 13]``, so
  ``sumband`` condemns 53% of the cell for being arithmetically correct.
* ``slotratio`` (CAL-P130) fixes the same premise for golf by dividing by a slot
  count the MARKET name declares. A ladder declares no slot count anywhere in
  its market name, so ``slotratio`` is degenerate here.

What economics declares instead is a GRAMMAR in its leg names. ``<$6,400`` /
``$6,400-$6,500`` / ... / ``>$7,300`` is a market saying, in its own text, that
its outcomes are mutually exclusive and exhaustive — so those prices must sum to
1, and the real ``What will S&P 500 (SPX) close at in March?`` market that sums
to **1.96** with both open tails priced at 0.400 is a defect of the market, not
a forecast that turned out wrong.

Everything that can go wrong here is silent — a mis-read leg name does not
error, it moves a market between two well-formed arms and changes a verdict.

* **🔴 LEAKAGE IS STILL THE ONE THAT MATTERS.** CAL-P130 made this the standing
  test for any new dimension and it is why ``sumband``'s passing subsets are
  disqualified on this cell before their numbers are even read.
  :func:`test_the_expression_never_reads_a_realized_winner` is the guard to keep
  if the rest are ever trimmed.
* **Exhaustiveness must be REQUIRED, not assumed.** A run of interior bands with
  no open-ended tail is mutually exclusive but not exhaustive, and its coherent
  sum is some unknown number below 1. Banding it against 1 would be the
  dimension inventing the quantity it claims to measure — CAL-P130 separated
  ``To Make the Cut`` for exactly this reason.
* **A ladder rung must never read as a band.** ``$255`` and ``4.3%`` are the leg
  names of real nested ladders in this cell. If either matched the band grammar
  the dimension would condemn the largest legitimate class on the board.
* **The ``|full`` / ``|part`` suffix is a CROSS, not a gate.** A partition whose
  legs did not all reach the curve publishes a sum mechanically short of 1
  through no fault of its pricing. Folding those in unlabelled would let a
  liquidity artifact read as an incoherence; dropping them early would hide the
  rows most likely to be incoherent.

THE ONE THING THESE TESTS DO NOT PROVE. They model the SQL's regex literals in
Python after an explicit translation of the POSIX class ``[[:space:]]``, which
Python does not implement. :func:`_posix_to_python` performs it and
:func:`test_the_patterns_stay_inside_the_translatable_subset` fails loudly if a
future pattern uses a POSIX construct Python cannot model, rather than letting
it be mis-modelled. The shipped expression was additionally executed
SERVER-SIDE against production during CAL-P131; that run is evidence these tests
cannot supply and is recorded in
``artifacts/cal-p131/RULE-DESIGN-polymarket-economics.md``.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cce = _load("calibration_cell_exact")

#: The POSIX character classes this module knows how to model in Python.
_POSIX_TRANSLATIONS = {"[[:space:]]": r"\s"}


def _posix_to_python(pattern: str) -> str:
    for posix, py in _POSIX_TRANSLATIONS.items():
        pattern = pattern.replace(posix, py)
    return pattern


def _leg_patterns() -> dict[str, str]:
    """The four regex literals the shipped pre-pass classifies leg names with.

    Read out of ``BANDRATIO_PRE`` in source order — tail, interior, low, high —
    so the model below cannot drift from the SQL by copying it.
    """
    found = re.findall(r"~\s*'([^']+)'", cce.BANDRATIO_PRE)
    assert len(found) == 4, f"expected four leg patterns, got {found}"
    tail, interior, low, high = found
    return {"tail": tail, "interior": interior, "low": low, "high": high}


def _band_thresholds() -> list[float]:
    """The four ratio cut points, read out of the shipped expression."""
    found = re.findall(r"ms\.msum\s*<=?\s*([0-9.]+)", cce.BANDRATIO_EXPR)
    assert len(found) == 4, f"expected four band constants, got {found}"
    return [float(x) for x in found]


def _is_band(leg: str) -> bool:
    p = _leg_patterns()
    leg = leg.strip()
    return bool(
        re.search(_posix_to_python(p["tail"]), leg)
        or re.search(_posix_to_python(p["interior"]), leg)
    )


def _arm(legs: list[str], msum: float | None, pub_legs: int | None) -> str:
    """Model the shipped ``BANDRATIO_EXPR`` from its own literals."""
    p = _leg_patterns()
    n = len(legs)
    if n == 0 or n < 3:
        return "z_not_a_partition"
    if sum(1 for leg in legs if _is_band(leg)) < n:
        return "z_not_a_partition"
    low = sum(1 for leg in legs if re.search(_posix_to_python(p["low"]), leg.strip()))
    high = sum(1 for leg in legs if re.search(_posix_to_python(p["high"]), leg.strip()))
    if low == 0 or high == 0:
        return "z_not_exhaustive"
    if msum is None:
        return "z_no_sum"
    lo25, lo75, coh, hi4 = _band_thresholds()
    if msum < lo25:
        band = "a_sum_lt_0.25"
    elif msum < lo75:
        band = "b_sum_0.25_0.75"
    elif msum <= coh:
        band = "c_sum_coherent"
    elif msum <= hi4:
        band = "d_sum_1.33_4"
    else:
        band = "e_sum_gt_4"
    return band + ("|part" if pub_legs is None or pub_legs < n else "|full")


#: Every leg of the real ``What will S&P 500 (SPX) close at in March?`` market
#: (market 2383063), published prices included. It sums to 1.960 against a
#: declared partition, with both open tails at 0.400.
SPX_BANDS = [
    "<$6,400",
    "$6,400-$6,500",
    "$6,500-$6,600",
    "$6,600-$6,700",
    "$6,700-$6,800",
    "$6,800-$6,900",
    "$6,900-$7,000",
    "$7,000-$7,100",
    "$7,100-$7,200",
    "$7,200-$7,300",
    ">$7,300",
]

#: Every leg of the real median-home-value market (115424): the same grammar
#: without the currency sign and with a spaced hyphen.
HOME_BANDS = [
    "<1.02m",
    "1.02 - 1.04m",
    "1.04 - 1.06m",
    "1.06 - 1.08m",
    "1.08 - 1.1m",
    ">1.1m",
]

#: Real nested-ladder leg names from the same cell. None of these is a band and
#: the whole dimension turns on that.
LADDER_LEGS = ["$255", "$260", "$265", "$270", "$275"]
YIELD_LADDER_LEGS = ["4.3%", "4.4%", "4.5%", "4.6%", "4.8%", "5.0%"]


# --------------------------------------------------------------------------
# 🔴 the leakage guard — the reason this dimension is shippable at all
# --------------------------------------------------------------------------


def test_the_expression_never_reads_a_realized_winner():
    """A rule keyed on this dimension must be evaluable BEFORE a winner exists.

    ``shape`` and ``sumband`` branch on ``sh.mw``. If ``bandratio`` did too, an
    exclusion rule built on it would select resolved markets by their
    resolution, and every ECE it reported would be measured on a population
    defined by the answer.
    """
    for name, blob in (
        ("BANDRATIO_EXPR", cce.BANDRATIO_EXPR),
        ("BANDRATIO_JOIN", cce.BANDRATIO_JOIN),
        ("BANDRATIO_PRE", cce.BANDRATIO_PRE),
    ):
        for forbidden in (
            "is_winner",
            "sh.mw",
            "sh.mn",
            ".mw",
            "win_count",
            "resolution_source",
        ):
            assert forbidden not in blob, (
                f"{name} references {forbidden!r} — that is a realized-outcome "
                "input and makes any rule built on this dimension leak"
            )


def test_the_expression_reads_only_leg_names_the_sum_and_the_leg_counts():
    """Three inputs, all knowable at publish time, and nothing else."""
    expr = cce.BANDRATIO_EXPR
    assert "bl.bl_legs" in expr and "bl.bl_bands" in expr
    assert "ms.msum" in expr
    assert "pl.pub_legs" in expr
    assert "fo9.name" in cce.BANDRATIO_PRE, "the grammar must read the LEG name"


def test_the_join_supplies_all_three_inputs():
    join = cce.BANDRATIO_JOIN
    assert "msums ms" in join
    assert "bandlegs bl" in join
    assert "publegs pl" in join


def test_the_pre_defines_both_new_ctes_and_keeps_msums():
    pre = cce.BANDRATIO_PRE
    assert "bandlegs AS (" in pre
    assert "publegs AS (" in pre
    assert pre.startswith(cce.SUMBAND_PRE), (
        "bandratio needs the msums CTE and must EXTEND SUMBAND_PRE rather than "
        "restate it — two dimensions that sum the same quantity must sum it "
        "identically or their tables cannot be read against each other"
    )


def test_publegs_is_computed_over_the_published_population():
    """``pub_legs`` must count rows in ``deduped`` — the legs that reached the
    curve — not outcomes in the raw table. Counting the raw table would make
    every partition read ``|full`` and hide the artifact the suffix exists for.
    """
    pre = cce.BANDRATIO_PRE
    block = pre[pre.index("publegs AS ("):]
    assert "FROM deduped" in block


def test_bandlegs_is_scoped_to_the_cell():
    """The pre-pass aggregate must be restricted to ``market_info`` or it scans
    every outcome in the database inside a chunked fold."""
    pre = cce.BANDRATIO_PRE
    block = pre[pre.index("bandlegs AS ("):pre.index("publegs AS (")]
    assert "SELECT market_id FROM market_info" in block


def test_the_dimension_is_registered_with_its_own_pre():
    expr, join, pre = cce.DIMENSIONS["bandratio"]
    assert expr is cce.BANDRATIO_EXPR
    assert join is cce.BANDRATIO_JOIN
    assert pre is cce.BANDRATIO_PRE


def test_the_dimension_is_reachable_from_the_command_line():
    assert "bandratio" in cce.DIMENSIONS


def test_the_outcome_alias_does_not_collide_with_another_dimension():
    """``fo9`` is this dimension's alias. Every sibling join in the rail picks
    its own numbered alias; reusing one silently changes what a crossed
    dimension aggregates."""
    others = [
        blob
        for name, blob in vars(cce).items()
        if isinstance(blob, str)
        and name.endswith(("_JOIN", "_PRE"))
        and not name.startswith("BANDRATIO")
    ]
    assert others, "no sibling joins found — the guard would pass vacuously"
    for blob in others:
        assert "fo9" not in blob


# --------------------------------------------------------------------------
# the grammar — a ladder rung must never read as a band
# --------------------------------------------------------------------------


@pytest.mark.parametrize("leg", SPX_BANDS + HOME_BANDS)
def test_every_real_band_leg_reads_as_a_band(leg):
    assert _is_band(leg)


@pytest.mark.parametrize("leg", LADDER_LEGS + YIELD_LADDER_LEGS)
def test_a_nested_ladder_rung_is_not_a_band(leg):
    """``$255`` is a rung of *"Apple closes above ___ on March 4?"*. If a bare
    strike matched the band grammar the dimension would condemn the biggest
    legitimate class in the cell."""
    assert not _is_band(leg)


@pytest.mark.parametrize(
    "leg",
    [
        "Yes",
        "No",
        "NVIDIA",
        "Saudi Aramco",
        "Will Apple (AAPL) close above $255 on February 19",
        "March 31",
    ],
)
def test_an_ordinary_leg_name_is_not_a_band(leg):
    assert not _is_band(leg)


def test_a_spaced_hyphen_range_still_reads_as_a_band():
    """``1.02 - 1.04m`` is real. Requiring a tight hyphen would drop the whole
    home-value family into ``z_not_a_partition``."""
    assert _is_band("1.02 - 1.04m")


def test_an_en_dash_range_reads_as_a_band():
    """Providers mix ``-`` and ``–``; a grammar that knows only one silently
    reclassifies half a family."""
    assert _is_band("$6,400–$6,500")


def test_the_patterns_stay_inside_the_translatable_subset():
    """A POSIX construct this module cannot model must fail loudly here rather
    than be mis-modelled by every other test in the file."""
    for pattern in _leg_patterns().values():
        stripped = pattern
        for posix in _POSIX_TRANSLATIONS:
            stripped = stripped.replace(posix, "")
        assert "[:" not in stripped, (
            f"{pattern!r} uses a POSIX class this module cannot translate; add "
            "it to _POSIX_TRANSLATIONS or measure the pattern server-side"
        )


# --------------------------------------------------------------------------
# arm assignment
# --------------------------------------------------------------------------


def test_the_real_spx_market_is_a_full_partition_over_the_bar():
    """1.960 against a declared partition of eleven bands, all published."""
    assert _arm(SPX_BANDS, 1.960, len(SPX_BANDS)) == "d_sum_1.33_4|full"


def test_the_real_home_value_market_reads_partial_because_legs_are_missing():
    """Only two of its six legs carry a price, so its published sum of 0.745 is
    short for a reason that is not incoherence. The suffix says so."""
    assert _arm(HOME_BANDS, 0.745, 2) == "b_sum_0.25_0.75|part"


def test_a_coherent_partition_lands_in_the_coherent_arm():
    assert _arm(SPX_BANDS, 1.0, len(SPX_BANDS)) == "c_sum_coherent|full"


def test_a_nested_ladder_is_not_a_partition_at_any_sum():
    """The whole point: a thirteen-rung ladder summing to 7 is arithmetically
    correct and must not be condemned."""
    assert _arm(LADDER_LEGS, 7.0, len(LADDER_LEGS)) == "z_not_a_partition"
    assert _arm(YIELD_LADDER_LEGS, 0.147, 5) == "z_not_a_partition"


def test_interior_bands_with_no_open_tail_are_never_banded():
    """Mutually exclusive but not exhaustive: the coherent sum is unknown, so
    the dimension refuses to divide by a number it made up."""
    interior_only = ["$6,400-$6,500", "$6,500-$6,600", "$6,600-$6,700"]
    assert _arm(interior_only, 0.5, 3) == "z_not_exhaustive"


def test_a_partition_missing_only_the_low_tail_is_not_exhaustive():
    assert _arm(SPX_BANDS[1:], 1.0, 10) == "z_not_exhaustive"


def test_a_partition_missing_only_the_high_tail_is_not_exhaustive():
    assert _arm(SPX_BANDS[:-1], 1.0, 10) == "z_not_exhaustive"


def test_one_non_band_leg_disqualifies_the_whole_market():
    """A market that is a partition PLUS an ``Other`` leg has not declared a
    partition of the real line, and its coherent sum is not 1."""
    assert _arm(SPX_BANDS + ["Other"], 1.0, 12) == "z_not_a_partition"


def test_a_two_leg_market_is_never_a_partition():
    """Two legs is a binary; ``pair``/``sumband`` already own that shape and a
    Yes/No pair summing to 1 would flood the coherent arm with rows this
    dimension has nothing to say about."""
    assert _arm(["<$100", ">$100"], 1.0, 2) == "z_not_a_partition"


def test_a_market_with_no_published_sum_is_separated_not_banded():
    assert _arm(SPX_BANDS, None, len(SPX_BANDS)) == "z_no_sum"


def test_an_unpublished_leg_count_reads_partial_rather_than_full():
    """``pub_legs`` NULL means no row of the market reached ``deduped``; that is
    the extreme of partial, never full."""
    assert _arm(SPX_BANDS, 1.0, None) == "c_sum_coherent|part"


# --------------------------------------------------------------------------
# the bands themselves
# --------------------------------------------------------------------------


def test_the_bands_are_symmetric_in_log_space_around_one():
    """Lesson 13: a correction expected to run one way runs both ways, so the
    banding must be able to SEE both ways. 1/4 and 4, 3/4 and 4/3."""
    lo25, lo75, coh, hi4 = _band_thresholds()
    assert lo25 * hi4 == pytest.approx(1.0)
    assert lo75 * coh == pytest.approx(1.0, abs=1e-4)


def test_the_bands_are_the_same_four_slotratio_uses():
    """Two dimensions that band the same scale-free ratio must band it
    identically or their tables cannot be read against each other."""
    mine = _band_thresholds()
    theirs = [float(x) for x in re.findall(r"<=?\s*([0-9.]+)", cce.SLOTRATIO_EXPR)]
    assert mine == theirs


def test_the_bands_are_strictly_increasing():
    t = _band_thresholds()
    assert t == sorted(t) and len(set(t)) == len(t)


def test_every_banded_arm_carries_a_completeness_suffix_and_no_other_arm_does():
    expr = cce.BANDRATIO_EXPR
    arms = re.findall(r"'([a-z][a-z0-9_.]*)'", expr)
    banded = [a for a in arms if re.match(r"^[a-e]_sum", a)]
    assert len(banded) == 5, f"expected five banded arms, got {banded}"
    assert "'|part'" in expr and "'|full'" in expr
    # the suffix is applied to the inner CASE, so no banded literal carries it
    for a in banded:
        assert "|" not in a


def test_the_refusal_arms_are_prefixed_so_they_sort_last():
    """``z_`` arms sort to the bottom of the fold's table, which is where the
    reader expects the rows the dimension could not classify."""
    expr = cce.BANDRATIO_EXPR
    for arm in ("z_not_a_partition", "z_not_exhaustive", "z_no_sum"):
        assert f"'{arm}'" in expr

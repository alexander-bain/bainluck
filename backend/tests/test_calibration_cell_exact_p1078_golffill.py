"""CAL-P1078 — guards for the ``golffill`` dimension.

``golffill`` exists to measure ONE named mechanism on ONE cell:
ARTIFACT-M-20260909-SUBCOHORT-kalshi-golf-field's *flat near-1 fill on
per-golfer legs of round-leader / cut / top-finish markets*. On the
truth-eligible superset that is 3,579 legs priced >= 0.93 winning 40.9%, and
the artifact's own confidence line says "medium on transfer to the published
21k subset".

The published payload (generated_at 2026-09-09T19:16:15Z) already bounds the
transfer at bucket grain: bucket 9 (0.90-1.00) of the published `kalshi/golf`
cell holds 416 legs at mean 0.9693 winning 64.4%, worth 0.64 of the cell's 4.34
ECE. So the mechanism is PRESENT but the exclusion cannot be worth more than
~0.56 — and that ceiling holds only if every one of those 416 is in the named
family. Deciding which of them are is the whole job of this dimension, and each
test below makes one specific way of getting it wrong loud.

CAL-P1077's rule 2 — *confirm the mechanism's rows EXIST in the published cell
before discussing its size* — is why the price cut and the family cut are
tested separately: a dimension that reports an empty ``a_fill_ge93`` because
its family regex matched nothing is indistinguishable, in the fold output, from
a cell that genuinely has no flat fills (gotcha #53).
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


# --------------------------------------------------------------------------
# reachable at all
# --------------------------------------------------------------------------


def test_the_dimension_is_registered_and_therefore_selectable():
    """An unregistered dimension is an ``argparse`` error at the point of use,
    not a silent empty fold — but only under the name the artifacts file it
    under."""
    assert "golffill" in cce.DIMENSIONS
    assert "golffill" not in cce.PER_CHUNK_DIMENSIONS


def test_it_declares_no_pre_pass_it_does_not_have():
    """The third tuple slot is SQL prepended to the chain. ``golffill`` reads
    only columns that already exist, so a non-empty pre-pass here would mean a
    CTE was added without registering it in ``PER_CHUNK_CONTEXT``."""
    _expr, _join, pre = cce.DIMENSIONS["golffill"]
    assert pre == ""


# --------------------------------------------------------------------------
# the price cut — the trap ``pubband`` was built to avoid, at a new threshold
# --------------------------------------------------------------------------


def test_the_band_reads_the_PUBLISHED_price_not_the_admission_price():
    """The producer's admission gate demands ``opening_probability > 0 AND
    < 1``, and the curve prices on ``COALESCE(calibration_probability,
    opening_probability)``. A band computed on ``opening_probability`` alone
    would silently measure the gate instead of the cell — the exact defect
    CAL-P1077's ``pubband`` guard was written for, and the reason its hockey
    verdict of ABSENT was trustworthy."""
    expr = cce.GOLFFILL_EXPR
    assert "COALESCE(fo15.calibration_probability, fo15.opening_probability)" in expr
    bare = re.findall(r"(?<!, )fo15\.opening_probability", expr)
    assert not bare, f"opening_probability read outside the COALESCE: {bare}"


def test_the_cut_is_the_artifacts_own_093_and_not_pubbands_099():
    """``pubband``'s shoulder sits at 0.99 because `polymarket/hockey`'s legs
    were at exactly 1.0000. Golf's fill sits at 0.97-0.99, which 0.99 would
    fold into the CONTROL arm — diluting the arm under test with the thing it
    is measured against."""
    assert "0.93" in cce.GOLFFILL_EXPR
    assert "0.99" not in cce.GOLFFILL_EXPR


def test_the_shoulder_arm_exists_so_the_cut_itself_is_falsifiable():
    """``b_shoulder_90_93`` is what separates "the defect is the fill" from
    "the defect is everything above 0.90". Without it a bad cut cannot be told
    from a real mechanism."""
    assert "b_shoulder_90_93" in cce.GOLFFILL_EXPR
    assert "0.90" in cce.GOLFFILL_EXPR


def test_the_control_arm_survives():
    """Doctrine 18 grades a row-dropping fix on what the reader is LEFT with.
    ``z_ordinary`` is that arm, and CAL-P1077's rule 1 uses it as the
    byte-identical control across the two folds."""
    assert "z_ordinary" in cce.GOLFFILL_EXPR


# --------------------------------------------------------------------------
# the family cut — read off the venue's own tickers, per standing notice 26
# --------------------------------------------------------------------------

#: Prefixes measured on production 2026-09-09 (resolved kalshi/golf markets),
#: with the leg count each carried. These are the venue's own tickers, not
#: guesses — notice 26 forbids answering "does the venue list X" from our own
#: naming intuition.
LEAD_TICKERS = [
    "KXPGAR1LEAD", "KXPGAR2LEAD", "KXPGAR3LEAD", "KXLPGAR1LEAD",
    "KXLPGAR2LEAD", "KXLPGAR3LEAD", "KXDPWORLDTOURR1LEAD",
    "KXDPWORLDTOURR2LEAD", "KXDPWORLDTOURR3LEAD", "KXLIVR1LEAD",
    "KXLIVR2LEAD", "KXLIVR3LEAD", "KXCHAMPTOURR1LEAD",
]
TOPN_TICKERS = [
    "KXPGATOP5", "KXPGATOP10", "KXPGATOP20", "KXPGATOP40",
    "KXPGAR1TOP5", "KXPGAR1TOP10", "KXPGAR1TOP20", "KXPGAR2TOP5",
    "KXPGAR2TOP10", "KXPGAR3TOP5", "KXPGAR3TOP10",
    "KXDPWTTOP5", "KXDPWTTOP10", "KXDPWTTOP20",
    "KXLIVTOP5", "KXLIVTOP10", "KXPGAMAJORTOP10",
]
CUT_TICKERS = ["KXPGAMAKECUT", "KXDPWORLDTOURMAKECUT", "KXLIVMAKECUT"]
TOUR_TICKERS = [
    "KXPGATOUR", "KXLPGATOUR", "KXDPWORLDTOUR", "KXKFTOUR",
    "KXCHAMPTOUR", "KXLIVTOUR",
]
#: Golf markets that are NOT the named family. ``KXPGAAGECUT`` and
#: ``KXPGACUTLINE`` are the ones that matter: both contain the substring "CUT"
#: and neither is a "make the cut" per-golfer field market.
OTHER_TICKERS = [
    "KXPGAAGECUT", "KXPGACUTLINE", "KXPGA3BALL", "KXPGAH2H",
    "KXPGAHOLESCORE", "KXPGABOGEYFREE", "KXPGAEAGLE", "KXOWGRRANK",
    "KXPGAWINNERWITHOUT", "KXPGAROUNDSCORE", "KXPGAPLAYERCAT",
]


def _family(ticker: str) -> str:
    """Evaluate the SQL family CASE in Python, on the same input the SQL sees.

    The SQL applies ``SPLIT_PART(external_id, '-', 1)`` first, so the arms are
    matched against the ticker PREFIX. Regexes are lifted from the expression
    rather than retyped, so a change to the SQL that this file does not know
    about fails here instead of passing on a stale copy.
    """
    pairs = re.findall(r"~ '([^']+)'\s+THEN '(\w+)'", cce.GOLFFILL_EXPR)
    assert pairs, "family arms not found in GOLFFILL_EXPR — the guard is stale"
    for pattern, label in pairs:
        if re.search(pattern, ticker):
            return label
    return "other"


@pytest.mark.parametrize("ticker", LEAD_TICKERS)
def test_every_round_leader_ticker_reads_as_lead(ticker):
    assert _family(ticker) == "lead"


@pytest.mark.parametrize("ticker", TOPN_TICKERS)
def test_every_top_finish_ticker_reads_as_topn(ticker):
    assert _family(ticker) == "topn"


@pytest.mark.parametrize("ticker", CUT_TICKERS)
def test_every_make_the_cut_ticker_reads_as_cut(ticker):
    assert _family(ticker) == "cut"


@pytest.mark.parametrize("ticker", TOUR_TICKERS)
def test_every_outright_winner_ticker_reads_as_tour(ticker):
    """``tour`` is the NEGATIVE CONTROL, not a fourth target. It is the same
    large-field per-golfer shape and the artifact does NOT name it, so if the
    fill turns up here too the mechanism is "large golf fields", not
    "round-leader / cut / top-finish"."""
    assert _family(ticker) == "tour"


@pytest.mark.parametrize("ticker", OTHER_TICKERS)
def test_no_unnamed_golf_market_is_swept_into_a_named_family(ticker):
    """The exclusion is only as defensible as its predicate. ``KXPGAAGECUT``
    and ``KXPGACUTLINE`` both carry "CUT" and would be captured by a substring
    test — which is why the arm is anchored (``MAKECUT$``) rather than a
    ``LIKE '%CUT%'``."""
    assert _family(ticker) == "other"


def test_the_cut_arm_is_anchored_and_not_a_substring_test():
    """Stated structurally as well as by specimen, because the specimen list
    can only ever cover the tickers that existed on the day it was written."""
    assert "MAKECUT$" in cce.GOLFFILL_EXPR
    assert "'CUT'" not in cce.GOLFFILL_EXPR


# --------------------------------------------------------------------------
# grain and aliasing
# --------------------------------------------------------------------------


def test_it_joins_at_OUTCOME_grain_not_market_grain():
    """``deduped`` is at outcome grain. A join to ``futures_outcomes`` on
    ``market_id`` fans every multi-leg market out — and a golf field market has
    up to 165 legs, so the fold would still return well-formed arms carrying
    ~165x the rows. The market-side join is the one that is keyed on
    ``market_id``, and it must be to ``futures_markets``."""
    join = cce.GOLFFILL_JOIN
    assert "futures_outcomes fo15 ON fo15.id = d.outcome_id" in join
    assert "futures_markets fm15 ON fm15.id = d.market_id" in join
    assert "futures_outcomes fo15 ON fo15.market_id" not in join


def test_the_aliases_do_not_collide_with_any_sibling_join():
    """``fm15`` / ``fo15`` are this dimension's own. Reusing a sibling's alias
    silently changes what a crossed dimension aggregates — and this dimension
    deliberately does not borrow ``SERIES_JOIN``'s ``fm2`` the way ``golfround``
    does, so that the guard has no exception to carve out."""
    others = [
        blob
        for name, blob in vars(cce).items()
        if isinstance(blob, str)
        and name.endswith(("_JOIN", "_PRE"))
        and not name.startswith("GOLFFILL")
    ]
    assert others, "no sibling joins found — the guard would pass vacuously"
    for blob in others:
        assert "fm15" not in blob
        assert "fo15" not in blob

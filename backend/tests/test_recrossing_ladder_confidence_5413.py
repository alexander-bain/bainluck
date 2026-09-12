"""authority/146 (#5413): a ladder that refutes itself was scored as the confident one.

THE DEFECT
----------
Sunday's Texans–Bills page (`/events/14780141`, kickoff 2026-09-13 17:00Z) served::

    "Projected final: 7 – 9"

on an NFL game. The arithmetic was right and one input was wrong: the projection
took Kalshi's implied total of **16.0** at ``confidence 0.9`` over Polymarket's
**45.0** at ``0.8``.

Kalshi's pooled total ladder for that game refutes itself. Two market families
are in one pot — a junk family hovering at a coin flip from 15.5 to 23.5, and the
real game total from 23.5@0.965 down to 65.5@0.075 — so the pool prices
*above* 50% again after it has priced *below* it, five times over. The threshold
23.5 appears twice, at 0.485 and at 0.965.

``binary_to_implied_total`` walks the sorted pool and takes the FIRST adjacent
pair that straddles 50%. That pair is ``15.5@0.52 -> 16.5@0.48``, one point wide,
which the width-based formula scored ``1 - 1/10 = 0.9`` — a better score than the
clean venue beside it. The correct crossing was in the same pool all along, at
``44.5@0.505 -> 45.5@0.465``, which reads 44.6 and agrees with Polymarket.

THE RULE
--------
A pool that prices above the crossover after pricing below it is not one ladder,
so its bracket width says nothing: :func:`ladder_recrosses` is true and the
confidence becomes :data:`_CONTRADICTION_CONFIDENCE`. This extends #4035's clause
— there the two ladders collided on one line, here they sit side by side.

**Scoring, not refusal**, and that is what lets the rule carry no noise
tolerance: a demoted arm is still served, so it only ever loses a page it was
going to lose to a cleaner arm. `test_a_sole_refuting_arm_is_still_served` and
`test_two_refuting_arms_fall_back_to_the_venue_order` are that half.

WHAT IS NOT FIXED HERE
----------------------
Which of a contaminated pool's crossings is the real one. That needs to know
which market family each rung came from, and the fold that pooled them is a
matching defect — filed, not patched here (D35, #2693).

MEASURED
--------
Over the 686 scheduled/live events in the ±48h window (production, 2026-09-12),
618 arms carrying a ladder: **76 re-cross, and exactly two pages change** — both
NFL, both from a two-digit football score to a real one. 0 projections lost, 0
gained. The rows below are those pages and their controls, copied from the
served `pm_spread_data`.
"""

import pytest

from app.utils import binary_spread
from app.utils.binary_spread import (
    _CONTRADICTION_CONFIDENCE,
    _threshold_order,
    binary_to_implied_spread,
    binary_to_implied_total,
    ladder_recrosses,
    select_projected_final,
)


def _pool(rows):
    return [{"threshold": t, "probability": p} for t, p in rows]


# ── The subject: Buffalo Bills @ Houston Texans, 14780141 ────────────────────
# Kalshi's total pool. Junk family 15.5-23.5 at a coin flip, then the real
# ladder from 23.5@0.965. Served total=16.0 confidence=0.9.
KALSHI_TOTAL_TEXANS_BILLS = _pool([
    (15.5, 0.52), (16.5, 0.48), (17.5, 0.5), (18.5, 0.475), (20.5, 0.515),
    (23.5, 0.965), (23.5, 0.485), (26.5, 0.925), (29.5, 0.895), (32.5, 0.845),
    (35.5, 0.765), (38.5, 0.69), (41.5, 0.605), (42.5, 0.58), (43.5, 0.54),
    (44.5, 0.505), (45.5, 0.465), (46.5, 0.445), (47.5, 0.41), (50.5, 0.33),
    (53.5, 0.245), (56.5, 0.2), (59.5, 0.145), (62.5, 0.1), (65.5, 0.075),
])
# Polymarket's total for the same game: monotone. Served total=45.0, conf 0.8.
POLYMARKET_TOTAL_TEXANS_BILLS = _pool([
    (41.5, 0.595), (43.5, 0.55), (44.5, 0.515), (44.5, 0.515), (46.5, 0.45),
    (47.5, 0.41),
])
# Kalshi's spread for the same game, on the home-margin axis. Served 1.5 @ 0.88.
KALSHI_SPREAD_TEXANS_BILLS = _pool([
    (-16.5, 0.905), (-14.5, 0.88), (-13.5, 0.855), (-10.5, 0.825), (-9.5, 0.78),
    (-7.5, 0.735), (-6.5, 0.69), (-5.5, 0.66), (-4.5, 0.645), (-3.5, 0.605),
    (-2.5, 0.53), (-1.5, 0.505), (1.0, 0.23), (1.0, 0.205), (1.5, 0.45),
    (2.5, 0.43), (3.5, 0.355), (4.5, 0.32), (5.5, 0.3), (6.5, 0.275),
    (7.0, 0.18), (7.0, 0.175), (7.5, 0.225), (9.5, 0.185), (10.5, 0.155),
    (13.5, 0.12), (14.5, 0.095), (15.0, 0.115), (15.0, 0.095), (16.5, 0.075),
])

# ── The rung that sits EXACTLY on the crossover ──────────────────────────────
# Both pools are monotone and locate one value, but a rung prices at exactly
# 0.500. The obvious version of this test — "count adjacent pairs that straddle
# 50%" — reports TWO for each, because that rung satisfies the straddle test on
# both sides. Demoting either would have handed a reader's page to a worse arm.
POLYMARKET_TOTAL_JETS_TITANS = _pool([
    (35.5, 0.595), (37.5, 0.535), (38.5, 0.5), (39.5, 0.485), (40.5, 0.43),
    (41.5, 0.42), (42.5, 0.38), (45.5, 0.32),
])
POLYMARKET_SPREAD_BROWNS_JAGUARS = _pool([
    (3.5, 0.66), (4.5, 0.645), (6.5, 0.585), (7.5, 0.525), (8.5, 0.5),
    (10.5, 0.44),
])

# ── The control that stops the rule flipping the favourite ───────────────────
# Dallas Cowboys @ New York Giants, 14637256. Kalshi's pool carries the same
# integer-threshold contamination as every NFL spread (1.0, 7.0, 15.0 rungs
# among the half-points) and is NOT monotone — but every one of those rungs is
# below the crossover, so the pool still locates exactly one value: 3.0, Dallas
# favoured, which is the line this module's own `margin_rung_on_home_axis`
# docstring validated on this event. Polymarket's arm reads the same magnitude
# with the OPPOSITE sign (-3.0, Giants favoured); that disagreement is its own
# defect, and a rule that demoted Kalshi here would hand the page to it and
# invert who wins.
KALSHI_SPREAD_COWBOYS_GIANTS = _pool([
    (-20.5, 0.905), (-17.5, 0.875), (-16.5, 0.855), (-14.5, 0.835),
    (-13.5, 0.805), (-10.5, 0.755), (-9.5, 0.725), (-7.5, 0.685),
    (-6.5, 0.625), (-5.5, 0.595), (-4.5, 0.575), (-3.5, 0.555),
    (-2.5, 0.455), (-1.5, 0.435), (1.0, 0.215), (1.0, 0.205), (1.5, 0.385),
    (2.5, 0.365), (3.5, 0.295), (4.5, 0.265), (5.5, 0.25), (6.5, 0.225),
    (7.0, 0.24), (7.0, 0.135), (7.5, 0.18), (9.5, 0.16), (10.5, 0.135),
    (13.5, 0.105), (14.5, 0.08), (15.0, 0.18), (15.0, 0.085),
])
POLYMARKET_SPREAD_COWBOYS_GIANTS = _pool([
    (1.5, 0.56), (2.5, 0.545), (2.5, 0.545), (3.5, 0.445), (4.5, 0.415),
])

# ── The sole-arm case: Green Bay Packers @ Minnesota Vikings, 14780148 ───────
# Kalshi's spread pool DOES re-cross (…-1.5@0.570, 1.0@0.245, then 1.5@0.515…),
# and it is the only spread arm the page has. Demotion must keep serving it.
KALSHI_SPREAD_PACKERS_VIKINGS = _pool([
    (-16.5, 0.935), (-14.5, 0.91), (-13.5, 0.895), (-10.5, 0.86), (-9.5, 0.83),
    (-7.5, 0.79), (-6.5, 0.735), (-5.5, 0.72), (-4.5, 0.7), (-3.5, 0.665),
    (-2.5, 0.595), (-1.5, 0.57), (1.0, 0.245), (1.0, 0.205), (1.5, 0.515),
    (2.5, 0.485), (3.5, 0.405), (4.5, 0.355), (5.5, 0.345), (6.5, 0.315),
    (7.0, 0.22), (7.0, 0.155), (7.5, 0.265), (9.5, 0.225), (10.5, 0.195),
    (13.5, 0.145), (14.5, 0.115), (15.0, 0.1), (15.0, 0.085), (16.5, 0.1),
])
KALSHI_TOTAL_PACKERS_VIKINGS = _pool([
    (24.5, 0.965), (27.5, 0.94), (30.5, 0.9), (33.5, 0.845), (36.5, 0.785),
    (39.5, 0.69), (42.5, 0.625), (43.5, 0.59), (44.5, 0.555), (45.5, 0.515),
    (46.5, 0.485), (47.5, 0.455), (48.5, 0.425), (51.5, 0.34), (54.5, 0.27),
    (57.5, 0.205), (60.5, 0.165), (63.5, 0.1), (66.5, 0.075),
])


def _naive_straddle_count(pool, crossover=0.50):
    """The obvious test this module does NOT use: adjacent pairs straddling 50%.

    Reproduced here so the exactly-on-the-crossover cases can assert that it
    disagrees with :func:`ladder_recrosses` on real rows, rather than the
    difference living only in a comment.
    """
    rungs = sorted(pool, key=_threshold_order)
    return sum(
        1 for low, high in zip(rungs, rungs[1:])
        if low["probability"] >= crossover >= high["probability"]
    )


# ═════════════════════════════════════════════════════════════════════════════
# The ship
# ═════════════════════════════════════════════════════════════════════════════

def test_the_texans_bills_page_stops_projecting_a_seven_nine_football_final():
    """The whole point, end to end, on the real served arms."""
    spreads = {
        "kalshi": {
            "spread": binary_to_implied_spread(KALSHI_SPREAD_TEXANS_BILLS).spread,
            "confidence": binary_to_implied_spread(KALSHI_SPREAD_TEXANS_BILLS).confidence,
        },
    }
    kalshi_total = binary_to_implied_total(KALSHI_TOTAL_TEXANS_BILLS)
    poly_total = binary_to_implied_total(POLYMARKET_TOTAL_TEXANS_BILLS)
    totals = {
        "kalshi": {"total": kalshi_total.total, "confidence": kalshi_total.confidence},
        "polymarket": {"total": poly_total.total, "confidence": poly_total.confidence},
    }

    _, total_source, projection = select_projected_final(spreads, totals)

    assert total_source == "polymarket"
    assert (projection.home_score, projection.away_score) == (21.8, 23.2)
    # The scoreline a reader saw before this fix, named so a regression is
    # recognisable rather than merely a number that moved.
    assert (round(projection.home_score), round(projection.away_score)) != (7, 9)


def test_without_the_recross_rule_the_same_arms_serve_the_seven_nine(monkeypatch):
    """Red check: neutralise the rule and the defect comes back, unchanged.

    Proves the assertions above are carried by :func:`ladder_recrosses` and not
    by some other property of the fixtures.
    """
    monkeypatch.setattr(binary_spread, "ladder_recrosses", lambda *_a, **_k: False)

    kalshi_total = binary_to_implied_total(KALSHI_TOTAL_TEXANS_BILLS)
    poly_total = binary_to_implied_total(POLYMARKET_TOTAL_TEXANS_BILLS)
    assert kalshi_total.confidence == 0.9 > poly_total.confidence

    spread = binary_to_implied_spread(KALSHI_SPREAD_TEXANS_BILLS)
    _, total_source, projection = select_projected_final(
        {"kalshi": {"spread": spread.spread, "confidence": spread.confidence}},
        {
            "kalshi": {"total": kalshi_total.total, "confidence": kalshi_total.confidence},
            "polymarket": {"total": poly_total.total, "confidence": poly_total.confidence},
        },
    )
    assert total_source == "kalshi"
    assert (round(projection.home_score), round(projection.away_score)) == (7, 9)


# ═════════════════════════════════════════════════════════════════════════════
# Scoring, not refusal
# ═════════════════════════════════════════════════════════════════════════════

def test_the_refuting_arm_keeps_its_value_and_loses_only_its_standing():
    """16.0 is still served — this rule moves the ranking, never the number."""
    result = binary_to_implied_total(KALSHI_TOTAL_TEXANS_BILLS)

    assert result is not None, "a refuting pool is demoted, never refused"
    assert result.total == 16.0
    assert result.confidence == _CONTRADICTION_CONFIDENCE


def test_a_sole_refuting_arm_is_still_served():
    """Packers–Vikings has one spread arm and it re-crosses. It still projects.

    This is why the rule needs no tolerance for market noise: when it fires and
    there is nothing cleaner to fall back to, the reader's page does not move.
    """
    spread = binary_to_implied_spread(KALSHI_SPREAD_PACKERS_VIKINGS)
    total = binary_to_implied_total(KALSHI_TOTAL_PACKERS_VIKINGS)
    assert ladder_recrosses(sorted(KALSHI_SPREAD_PACKERS_VIKINGS, key=_threshold_order), 0.50)
    assert spread.confidence == _CONTRADICTION_CONFIDENCE

    spread_source, _, projection = select_projected_final(
        {"kalshi": {"spread": spread.spread, "confidence": spread.confidence}},
        {"kalshi": {"total": total.total, "confidence": total.confidence}},
    )
    assert spread_source == "kalshi"
    # The scoreline production served on 2026-09-12, unchanged by the demotion.
    assert (projection.home_score, projection.away_score) == (22.5, 23.5)


def test_two_refuting_arms_fall_back_to_the_venue_order():
    """Both demoted ⇒ PROJECTION_SOURCE_ORDER decides, which is today's answer."""
    kalshi = binary_to_implied_total(KALSHI_TOTAL_TEXANS_BILLS)
    other = binary_to_implied_total(KALSHI_TOTAL_TEXANS_BILLS)
    assert kalshi.confidence == other.confidence == _CONTRADICTION_CONFIDENCE

    _, total_source, _ = select_projected_final(
        {"kalshi": {"spread": -3.0, "confidence": 1.0}},
        {
            "polymarket": {"total": other.total, "confidence": other.confidence},
            "kalshi": {"total": kalshi.total, "confidence": kalshi.confidence},
        },
    )
    assert total_source == "kalshi"


# ═════════════════════════════════════════════════════════════════════════════
# What must NOT be demoted
# ═════════════════════════════════════════════════════════════════════════════

def test_a_clean_ladder_keeps_its_width_based_confidence():
    poly = binary_to_implied_total(POLYMARKET_TOTAL_TEXANS_BILLS)

    assert not ladder_recrosses(
        sorted(POLYMARKET_TOTAL_TEXANS_BILLS, key=_threshold_order), 0.50
    )
    assert poly.total == 45.0
    assert poly.confidence == 0.8


@pytest.mark.parametrize(
    "label, pool, expected_confidence",
    [
        ("14780146 polymarket total", POLYMARKET_TOTAL_JETS_TITANS, 0.9),
        ("14780144 polymarket spread", POLYMARKET_SPREAD_BROWNS_JAGUARS, 0.95),
    ],
)
def test_a_rung_priced_exactly_on_the_crossover_is_not_a_recross(
    label, pool, expected_confidence
):
    """The discriminator against the obvious implementation, on real rows."""
    rungs = sorted(pool, key=_threshold_order)

    assert _naive_straddle_count(pool) == 2, (
        f"{label}: fixture must be one the naive count gets wrong, or this "
        f"test proves nothing"
    )
    assert not ladder_recrosses(rungs, 0.50), label

    derive = binary_to_implied_total if "total" in label else binary_to_implied_spread
    assert derive(pool).confidence == expected_confidence


def test_the_cowboys_giants_favourite_is_not_flipped():
    """Contamination that never re-crosses leaves the pool locating one value.

    Kalshi's pool here is not monotone — it has four rises — and it must keep
    its 0.95, because the arm it would otherwise lose the page to reads the same
    magnitude with the opposite sign.
    """
    kalshi = binary_to_implied_spread(KALSHI_SPREAD_COWBOYS_GIANTS)
    poly = binary_to_implied_spread(POLYMARKET_SPREAD_COWBOYS_GIANTS)

    rungs = sorted(KALSHI_SPREAD_COWBOYS_GIANTS, key=_threshold_order)
    prices = [r["probability"] for r in rungs]
    assert any(b > a for a, b in zip(prices, prices[1:])), (
        "fixture must be non-monotone, or it cannot discriminate a re-cross "
        "rule from a monotonicity rule"
    )
    assert not ladder_recrosses(rungs, 0.50)
    assert kalshi.confidence == 0.95

    spread_source, _, _ = select_projected_final(
        {
            "kalshi": {"spread": kalshi.spread, "confidence": kalshi.confidence},
            "polymarket": {"spread": poly.spread, "confidence": poly.confidence},
        },
        {"kalshi": {"total": 44.0, "confidence": 0.9}},
    )
    assert spread_source == "kalshi"
    assert kalshi.spread > 0 > poly.spread, "the two arms disagree in sign"


def test_the_zero_width_contradiction_of_4035_is_untouched():
    """#4035's production pool does not re-cross; its own clause still scores it."""
    pool = _pool([(10.5, 1.0), (10.5, 1.0), (10.5, 0.49)])

    assert not ladder_recrosses(sorted(pool, key=_threshold_order), 0.50)
    assert binary_to_implied_total(pool).confidence == _CONTRADICTION_CONFIDENCE


# ═════════════════════════════════════════════════════════════════════════════
# The predicate itself
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "label, prices, expected",
    [
        ("monotone descending", [0.9, 0.7, 0.5, 0.3, 0.1], False),
        ("all above the crossover", [0.9, 0.8, 0.95, 0.85], False),
        ("all below the crossover", [0.4, 0.2, 0.45, 0.1], False),
        ("below then above", [0.9, 0.4, 0.6, 0.2], True),
        ("above only by a hair, after below", [0.9, 0.4, 0.5001, 0.2], True),
        ("exactly on the crossover after below", [0.9, 0.4, 0.5, 0.2], False),
        ("exactly on the crossover before below", [0.9, 0.5, 0.4, 0.2], False),
        ("a rise that never reaches the crossover", [0.9, 0.4, 0.49, 0.2], False),
        ("single rung", [0.4], False),
        ("empty", [], False),
    ],
)
def test_ladder_recrosses_reads_the_crossover_strictly(label, prices, expected):
    pool = [{"threshold": float(i), "probability": p} for i, p in enumerate(prices)]
    assert ladder_recrosses(pool, 0.50) is expected, label


def test_a_pool_that_starts_on_the_crossover_and_rises_still_locates_one_value():
    """Pins ``below`` to a STRICT ``<``, which is not the same test as ``<=``.

    ``[0.50, 0.90, 0.40]`` never prices below the crossover before pricing above
    it — it prices ON it — and the walk finds exactly one straddling pair,
    ``0.90 -> 0.40``. Reading the opening rung as "below" would demote a pool
    that locates one value.

    The two readings agree on all 618 arms carrying a ladder in the ±48h window
    (production, 2026-09-12), so only a constructed pool can tell them apart —
    which is the reason to construct one.
    """
    pool = _pool([(1.0, 0.50), (2.0, 0.90), (3.0, 0.40)])

    assert _naive_straddle_count(pool) == 1
    assert not ladder_recrosses(pool, 0.50)
    assert binary_to_implied_total(pool).confidence != _CONTRADICTION_CONFIDENCE


@pytest.mark.parametrize(
    "order",
    [
        pytest.param(lambda rungs: rungs, id="as-served"),
        pytest.param(lambda rungs: list(reversed(rungs)), id="reversed"),
        pytest.param(
            lambda rungs: sorted(rungs, key=lambda c: -c["probability"]),
            id="price-descending",
        ),
        pytest.param(
            lambda rungs: sorted(rungs, key=lambda c: c["probability"]),
            id="price-ascending",
        ),
    ],
)
def test_the_derivation_reads_the_pool_in_its_own_sort_order_not_the_rows(order):
    """The verdict cannot depend on the order the rows arrived in.

    No query guarantees that order — the finding #4035 pinned `_threshold_order`
    for. `price-descending` is the ordering that puts every above-crossover rung
    ahead of every below-crossover one, so a derivation that tested the raw list
    would read this contaminated pool as clean.
    """
    result = binary_to_implied_total(order(list(KALSHI_TOTAL_TEXANS_BILLS)))

    assert result.total == 16.0
    assert result.confidence == _CONTRADICTION_CONFIDENCE


def test_the_recross_is_read_in_the_walks_own_rung_order():
    """Two rungs share a threshold; only the walk's order says which comes first.

    `_threshold_order` puts the higher price first within a tie, so the pool
    below reads 0.9, 0.8, 0.2, 0.6 — a re-cross. Sorted by threshold alone the
    tie could land either way, which is the row-order dependence #4035 pinned.
    """
    pool = _pool([(1.0, 0.9), (2.0, 0.2), (2.0, 0.8), (3.0, 0.6)])

    assert ladder_recrosses(sorted(pool, key=_threshold_order), 0.50)


def test_the_crossover_argument_is_honoured():
    """A pool clean at 0.50 can re-cross at another crossover, and vice versa."""
    pool = _pool([(1.0, 0.9), (2.0, 0.4), (3.0, 0.45)])

    assert not ladder_recrosses(pool, 0.50)
    assert ladder_recrosses(pool, 0.42)

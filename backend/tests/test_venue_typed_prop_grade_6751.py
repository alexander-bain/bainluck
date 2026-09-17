"""CERT-3024 repair — an authoritative venue settlement types a verdict the box score cannot.

## Why this file exists

#6751's first attempt (`1b96294c0`) put the settled fantasy-points rows back
into the `/game-markets` payload and was BLOCKed, correctly. Readmitting a row
is not grading it. `KXNFLFFPTS` has no fantasy-points stat mapping, so the box
score can never resolve those legs, and the row reached the client as:

    {"actual": null, "hit": null, "is_winner": true, "resolution_source": "api_settlement"}

`frontend/lib/propGrade.ts` is the site's one settled-state authority and its
rule is **only `hit` types a verdict** (ruling 003 / UX-P040 #1638 / UX-P044
#1642). That shape renders `Resolved · grading unavailable` — by design, and the
module is right to do it. So the reader showed the card and refused to grade it,
and the certed "graded Won/Lost card" was never delivered.

That module must not be weakened. The verdict has to be typed on the server.

## The rule these tests pin

`hit` may be typed from a venue settlement only when **two independent signals
agree**: an allowlisted `resolution_source` VALUE, and the leg's own settled
price. Anything else withholds.

The second signal is the whole safety argument. `is_winner` is a non-nullable
column defaulting to `False`, so on a never-graded row it is indistinguishable
from "graded a loser" — UX-P044 measured 70 red MISSes across 358 rendered cards
built from exactly that. An allowlist keyed on a source *value* (never on "a
source exists") refuses that cohort at the first gate; the price refuses
anything that slips past it, and refuses genuine conflicts — void, retracted,
partial settlement — without needing a vocabulary for each.

Measured on the 14 `KXNFLFFPTS` specimen markets, 2026-09-17: 185 outcome rows,
sources `api_settlement` (168) and `clean_resolution` (17), **zero** price
contradictions, winners 0.97–1.00 and losers 0.00–0.03. The bounds asserted here
are deliberately looser than that observation.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.routes.events import (
    _AUTHORITATIVE_SETTLEMENT_SOURCES,
    _grade_settled_prop,
    _venue_typed_hit,
)


def _leg(
    source="api_settlement",
    won=True,
    price=1.0,
    name="Javonte Williams: Over 17.4 fantasy points",
):
    """One settled outcome row, in the shape the specimen actually carries."""
    return SimpleNamespace(
        name=name,
        is_winner=won,
        resolution_source=source,
        current_probability=price,
    )


# ---------------------------------------------------------------------------
# The pair the BLOCK names: a rendered winner and a rendered loser, no box score.
# ---------------------------------------------------------------------------


def test_a_venue_settled_winner_with_no_box_score_types_a_verdict():
    assert _venue_typed_hit(_leg(won=True, price=1.0)) is True


def test_a_venue_settled_loser_with_no_box_score_types_a_verdict():
    assert _venue_typed_hit(_leg(won=False, price=0.0)) is False


def test_the_specimen_shape_end_to_end_reaches_the_reader_as_a_typed_hit():
    """The exact wire shape CERT-3024 refused, now carrying a verdict.

    `ctx=None` is the no-box-score path — which for `KXNFLFFPTS` is not an edge
    case but the only path there is, since no stat mapping exists for it.
    """
    out = _grade_settled_prop(
        True,
        None,
        SimpleNamespace(name="Dallas vs New York G: Fantasy Points"),
        _leg(),
        None,
        False,
    )
    assert out["hit"] is True, "the reader adjudicates on `hit` and nothing else"
    assert out["is_winner"] is True
    assert out["resolution_source"] == "api_settlement"
    # `actual` is NOT invented. A venue-typed row shows a verdict with no stat
    # line; `readPropGrade` types `{state: HIT, actual: null}` from exactly this.
    assert out["actual"] is None


def test_a_venue_settled_loser_end_to_end_is_a_miss_not_a_withhold():
    out = _grade_settled_prop(
        True, None, SimpleNamespace(name="m"), _leg(won=False, price=0.0), None, False
    )
    assert out["hit"] is False
    assert out["actual"] is None


def test_clean_resolution_is_authoritative_too_at_its_measured_price():
    # The one specimen row at 0.97 (Justin Jefferson Over 17.1, `clean_resolution`).
    assert (
        _venue_typed_hit(_leg(source="clean_resolution", won=True, price=0.97)) is True
    )


# ---------------------------------------------------------------------------
# The refusals the BLOCK requires be RETAINED. Each of these is a shape that
# renders `Resolved · grading unavailable`, and must keep doing so.
# ---------------------------------------------------------------------------


def test_the_never_graded_default_false_cohort_is_still_refused():
    """The UX-P040 cohort: no source, `is_winner` defaulted False, priced out.

    THE PRICE ALONE MUST NEVER BE ENOUGH. This row's price (0.0) satisfies the
    loser bound, so if the source gate were dropped — or written as "a source
    exists" against a NULL — this row would render a red MISS on a prop nobody
    ever graded. That is the exact 70-card defect, and this is its guard.
    """
    assert _venue_typed_hit(_leg(source=None, won=False, price=0.0)) is None


def test_a_source_that_is_not_allowlisted_is_refused_however_settled_it_looks():
    """UX-P044 in one line: a source PROVES a process touched the row, not a verdict."""
    for source in ("manual", "backfill", "espn", "inferred", "", "API_SETTLEMENT"):
        assert (
            _venue_typed_hit(_leg(source=source, won=True, price=1.0)) is None
        ), source


def test_an_unknown_future_source_defaults_to_refuse():
    """The allowlist's default is REFUSE — a source nobody has taught it withholds.

    An allowlist whose default is a real value stores plausible wrong data. This
    is the property that keeps a new ingest path from silently publishing
    verdicts before anyone has checked what its `is_winner` means.
    """
    assert (
        _venue_typed_hit(_leg(source="some_new_settlement_v2", won=True, price=1.0))
        is None
    )


def test_a_conflict_between_the_venue_and_the_price_withholds_both_ways():
    """Void / retracted / partial settlement arrive here as disagreement.

    A leg the venue calls a winner while its own book says 0.02 is not a leg we
    will grade for a reader. No separate vocabulary is needed for each cause.
    """
    assert _venue_typed_hit(_leg(won=True, price=0.02)) is None
    assert _venue_typed_hit(_leg(won=False, price=0.98)) is None


def test_a_leg_still_in_play_is_refused():
    """Mid-book prices are the live case and must never type a verdict."""
    for price in (0.5, 0.45, 0.6, 0.11, 0.89):
        assert _venue_typed_hit(_leg(won=True, price=price)) is None, price
        assert _venue_typed_hit(_leg(won=False, price=price)) is None, price


def test_an_is_winner_that_is_not_a_real_boolean_is_refused():
    """`is True` / `is False`, not truthiness — a stray 0/1/"" types nothing."""
    for won in (None, 1, 0, "true", "", []):
        assert _venue_typed_hit(_leg(won=won, price=1.0)) is None, repr(won)


def test_a_missing_or_malformed_price_is_refused():
    for price in (None, "", "abc", float("nan")):
        assert _venue_typed_hit(_leg(price=price)) is None, repr(price)


def test_a_price_out_of_range_is_refused_rather_than_clamped():
    assert _venue_typed_hit(_leg(won=True, price=-0.5)) is None
    assert _venue_typed_hit(_leg(won=True, price=1000.0)) is None


def test_a_zero_to_one_hundred_price_is_normalised_not_read_vacuously():
    """97 is not "comfortably above 0.9" — it is the same 0.97 on another scale."""
    assert _venue_typed_hit(_leg(won=True, price=97)) is True
    assert _venue_typed_hit(_leg(won=False, price=3)) is False
    # and the conflict still fires after normalising
    assert _venue_typed_hit(_leg(won=True, price=2)) is None


# ---------------------------------------------------------------------------
# The box score keeps precedence, and an unfinished event is untouched.
# ---------------------------------------------------------------------------


def test_the_box_score_wins_wherever_it_typed_a_verdict():
    """The fallback is consulted ONLY while `hit` is still None.

    Red-first value: with the `hit is None` guard removed, the venue's True
    overwrites the box score's False and this test fails. No row that grades
    today may change its verdict.
    """
    ctx = {
        "norm_box": {"jane doe": {"passing_yards": 100}},
        "normalize": lambda s: s.strip().lower(),
        "stats_for_ticker": lambda *a, **k: None,
        "sum_stats": lambda stats, keys: sum(stats.get(k, 0) for k in keys),
    }
    market = SimpleNamespace(name="Jane Doe: Passing Yards", external_id="X")
    leg = _leg(won=True, price=1.0, name="Jane Doe: Over 250.5")
    with patch("app.routes.events._prop_stat_keys", return_value=["passing_yards"]):
        out = _grade_settled_prop(True, ctx, market, leg, 250.5, False)
    assert out["actual"] == 100
    # The box score says the Over missed. The venue says the leg won. The box
    # score is the answer on the page.
    assert out["hit"] is False


def test_an_unfinished_event_publishes_no_grade_keys_at_all():
    assert (
        _grade_settled_prop(False, None, SimpleNamespace(name="m"), _leg(), None, False)
        == {}
    )


def test_the_allowlist_is_a_frozenset_of_exactly_the_two_measured_values():
    """Pinned so widening it is a deliberate, reviewed edit rather than a drift.

    Adding a value here changes what the site will state as a settled verdict.
    The site-wide coverage share of these sources is parked, unmeasured, in
    PARKED-MEASUREMENTS.md — so a third value needs that census first.
    """
    assert _AUTHORITATIVE_SETTLEMENT_SOURCES == frozenset(
        {"api_settlement", "clean_resolution"}
    )

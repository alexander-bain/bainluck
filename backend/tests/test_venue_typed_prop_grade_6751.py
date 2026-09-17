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
agree**: a `resolution_source` graded at tier 2 or above on the CANONICAL
authority ladder (`app/utils/resolution_authority.py` — tier 3 the venue's own
settlement, tier 2 the box score), and the leg's own settled price. Anything
else withholds.

CERT-3025 BLOCKed the draft that used a hand-rolled
`frozenset({"api_settlement", "clean_resolution"})`. `clean_resolution` is tier
1 and PRICE-DERIVED — `backfill_winners.py:680` sets
`is_winner = (current_probability >= 0.95)` — so for those rows the two signals
collapse into one and "alignment" is guaranteed by construction. The ladder is
the house idiom for exactly this question and asking it keeps one answer in one
place.

The second signal is the whole safety argument. `is_winner` IS nullable, in the
model and in production (CERT-521 / CAL-P155), but production overwhelmingly
stores `False` rather than NULL for an ungraded row — 2,536 NULL of 3,893,126,
measured 2026-08-31 — so a stored `False` is indistinguishable from "graded a
loser". UX-P044 measured 70 red MISSes across 358 rendered cards built from
exactly that. A tier gate (never "a source exists") refuses that
cohort at the first gate; the price refuses
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
    _PRICE_IS_A_VERDICT_MIN_TIER,
    _grade_settled_prop,
    _venue_typed_hit,
)
from app.utils.resolution_authority import authority_tier


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


def test_a_tier_two_box_score_grade_also_qualifies():
    """The gate is the LADDER, not one source name: tier 2 is a real second signal."""
    assert authority_tier("game_score") >= _PRICE_IS_A_VERDICT_MIN_TIER
    assert _venue_typed_hit(_leg(source="game_score", won=True, price=1.0)) is True


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


def test_a_source_below_the_verdict_tier_is_refused_however_settled_it_looks():
    """UX-P044 in one line: a source PROVES a process touched the row, not a verdict."""
    for source in ("manual", "backfill", "espn", "inferred", "", "API_SETTLEMENT"):
        assert (
            _venue_typed_hit(_leg(source=source, won=True, price=1.0)) is None
        ), source


def test_an_unknown_future_source_defaults_to_refuse():
    """The ladder's default is REFUSE — an unclassified source scores -1.

    A gate whose default is a real value stores plausible wrong data. This
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


def test_an_out_of_domain_price_fails_closed_rather_than_being_rescaled():
    """CERT-3025 follow-up `6751-FAIL-CLOSED-ON-OUT-OF-DOMAIN-PROBABILITY`.

    The first draft divided anything above 1.0 by 100 to "normalise a percent
    write", which silently rescued malformed values: a stored `2` became 0.02
    and typed a confident MISS. This column stores a 0–1 probability (185 of 185
    specimen rows do), so a value outside it is not a scale to guess at — it is
    a row we do not understand, and those are withheld.
    """
    for price in (2, 3, 97, 100, 1.5):
        assert _venue_typed_hit(_leg(won=True, price=price)) is None, price
        assert _venue_typed_hit(_leg(won=False, price=price)) is None, price


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


def test_an_aligned_clean_resolution_row_is_withheld_because_its_two_signals_are_one():
    """CERT-3025's BLOCK, pinned. THE CIRCULARITY IS THE WHOLE POINT.

    `clean_resolution` is tier 1 — price-derived and overwritable. Its writer
    (`app/tasks/backfill_winners.py:680`) is literally:

        SET is_winner = (fo.current_probability >= 0.95),
            resolution_source = 'clean_resolution',

    so the "corroborating" price IS the input that produced `is_winner`. Such a
    row is aligned BY CONSTRUCTION and could never be caught by the conflict
    check — which is exactly why alignment proves nothing here. Typing a verdict
    off it would state a definitive HIT/MISS on our own 0.95 threshold while
    presenting it as the venue's word.

    Note the prices used: 1.0 and 0.0, perfectly aligned. This test passes only
    because the SOURCE is refused, never because the price disagreed.
    """
    assert authority_tier("clean_resolution") < _PRICE_IS_A_VERDICT_MIN_TIER
    assert (
        _venue_typed_hit(_leg(source="clean_resolution", won=True, price=1.0)) is None
    )
    assert (
        _venue_typed_hit(_leg(source="clean_resolution", won=False, price=0.0)) is None
    )


def test_the_gate_is_the_canonical_ladder_not_a_local_copy_of_it():
    """Pinned so a future edit cannot quietly re-introduce a hand-rolled set.

    A local allowlist is how `clean_resolution` got in: it looked authoritative
    by name. The ladder already answers "is a price a verdict here", tier by
    tier, and an unclassified source scores -1, so the default stays REFUSE.
    """
    assert _PRICE_IS_A_VERDICT_MIN_TIER == 2
    for source, qualifies in [
        ("api_settlement", True),  # tier 3, the venue's own settlement
        ("game_score", True),  # tier 2, deterministic
        ("clean_resolution", False),  # tier 1, price-derived
        ("pass2_guess", False),  # tier 0, guess family
        ("some_new_source_v2", False),  # unclassified -> -1, fail-safe
        (None, False),
    ]:
        got = authority_tier(source) >= _PRICE_IS_A_VERDICT_MIN_TIER
        assert got is qualifies, source

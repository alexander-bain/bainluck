"""#5619 — every "N points" sentence goes through the house formatter.

`feed_reasons` has two functions, one wrapping the other:

    _point_change(v) -> float   # the arithmetic: round(abs(v) * 100, 1)
    _points(v)       -> str     # the DISPLAY string: "37.5 points" / "1 point"

`_points` drops the trailing zero and handles the singular, and its own docstring
names "1.0 points" as the thing it exists to prevent. Eight sites interpolated the
raw `_point_change` float into a "points" sentence instead, so four of the five
movement cards on Discover page one read like this on 2026-09-12 13:27Z:

    Above 102 moved up 38.0 points today in Hims Monthly Credit Card Spend...
    Maintain current rate moved down 30.0 points today in European Central Bank...

A person does not say "38.0 points".

WHY THIS ENTERS THROUGH THE PUBLIC FUNCTIONS. `_points` was never the broken half
— it was correct the whole time and simply wasn't called. So a test that asserts
on `_points` directly passes on the defective tree and proves nothing. Every arm
below drives `generate_futures_reason` / `generate_futures_headline`, the two
functions a card actually renders through, and each arm names the site it covers.

The three-way split per arm is deliberate: a whole number must LOSE the ".0", a
one-point move must go SINGULAR (the worst reading, and reachable — `_point_change(0.01)`
is exactly 1.0), and a genuine decimal must SURVIVE untouched. A fix that rounded
to int instead of routing through the formatter would pass the first two and fail
the third.
"""

from datetime import datetime, timezone

from app.utils.feed_reasons import (
    generate_futures_headline,
    generate_futures_reason,
)

# Fixed instants: `format_baseline_date` is year-boundary sensitive and an anchor
# off the wall clock would test a different sentence every January (gotcha #44).
NOW = datetime(2026, 9, 8, 21, 7, tzinfo=timezone.utc)
OPENED_THIS_YEAR = datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc)

MARKET = "Hims Monthly Credit Card Spend in September"
# `_weak_outcome_label` is true for a month-day label, which is what routes the
# headline to its "<short title> odds ..." arm rather than its named-subject arm.
WEAK_LABEL = "June 30, 2027"
STRONG_LABEL = "Above 102"

WHOLE = 0.38  # -> "38 points", never "38.0 points"
SINGLE = 0.01  # -> "1 point",   never "1.0 points" and never "1 points"
DECIMAL = 0.235  # -> "23.5 points", which must survive


def _assert_house_format(sentence: str, *, whole: str, site: str) -> None:
    """The three things the house formatter guarantees, on a rendered sentence."""
    assert f"{whole}.0 points" not in sentence, f"{site}: trailing zero — {sentence!r}"
    assert (
        f"{whole} points" in sentence
    ), f"{site}: expected '{whole} points' — {sentence!r}"


# --- generate_futures_reason -------------------------------------------------


def test_major_movement_reason_drops_the_trailing_zero():
    """Site 1: "... moved up N today in <market>"."""
    sentence = generate_futures_reason(
        market_name=MARKET,
        highlight_reasons=["major_movement_24h"],
        top_mover_name=STRONG_LABEL,
        top_mover_change=WHOLE,
    )
    _assert_house_format(sentence, whole="38", site="reason/major_movement_24h")
    assert sentence == "Above 102 moved up 38 points today in " + MARKET


def test_moderate_movement_reason_drops_the_trailing_zero():
    """Site 2: "... odds shifted up N today in <market>"."""
    sentence = generate_futures_reason(
        market_name=MARKET,
        highlight_reasons=["moderate_movement_24h"],
        top_mover_name=STRONG_LABEL,
        top_mover_change=WHOLE,
    )
    _assert_house_format(sentence, whole="38", site="reason/moderate_movement_24h")


def test_surprise_reason_drops_the_trailing_zero():
    """Site 3: "... is up N since <date> in <market>".

    This arm is the one the issue's own census missed, and #4066's commit message
    wrongly cited this sentence family as already correct — it was only ever
    sampled with a real decimal ("22.5"), which hides the defect.
    """
    sentence = generate_futures_reason(
        market_name=MARKET,
        highlight_reasons=["major_surprise"],
        top_surprise_name=STRONG_LABEL,
        top_surprise_change=WHOLE,
        top_surprise_opened_at=OPENED_THIS_YEAR,
        now=NOW,
    )
    _assert_house_format(sentence, whole="38", site="reason/major_surprise")
    assert "since Mar 4" in sentence


# --- generate_futures_headline -----------------------------------------------


def test_major_movement_headline_named_subject_drops_the_trailing_zero():
    """Site 5: "<name> up N today"."""
    sentence = generate_futures_headline(
        highlight_reasons=["major_movement_24h"],
        top_mover_name=STRONG_LABEL,
        top_mover_change=WHOLE,
    )
    _assert_house_format(sentence, whole="38", site="headline/major named")
    assert sentence == "Above 102 up 38 points today"


def test_major_movement_headline_title_subject_drops_the_trailing_zero():
    """Site 4: "<short title> odds up N" — the weak-label arm."""
    sentence = generate_futures_headline(
        market_name=MARKET,
        highlight_reasons=["major_movement_24h"],
        top_mover_name=WEAK_LABEL,
        top_mover_change=WHOLE,
    )
    _assert_house_format(sentence, whole="38", site="headline/major title")


def test_moderate_movement_headline_both_arms_drop_the_trailing_zero():
    """Sites 6 and 7 — the moderate block repeats the major block verbatim."""
    named = generate_futures_headline(
        highlight_reasons=["moderate_movement_24h"],
        top_mover_name=STRONG_LABEL,
        top_mover_change=WHOLE,
    )
    titled = generate_futures_headline(
        market_name=MARKET,
        highlight_reasons=["moderate_movement_24h"],
        top_mover_name=WEAK_LABEL,
        top_mover_change=WHOLE,
    )
    _assert_house_format(named, whole="38", site="headline/moderate named")
    _assert_house_format(titled, whole="38", site="headline/moderate title")


def test_surprise_headline_drops_the_trailing_zero():
    """Site 8: "<name> up N since <date>"."""
    sentence = generate_futures_headline(
        highlight_reasons=["major_surprise"],
        top_surprise_name=STRONG_LABEL,
        top_surprise_change=WHOLE,
        top_surprise_opened_at=OPENED_THIS_YEAR,
        now=NOW,
    )
    _assert_house_format(sentence, whole="38", site="headline/surprise")
    assert "since Mar 4" in sentence


# --- the singular, and the decimal that must survive -------------------------


def test_a_one_point_move_is_singular_everywhere():
    """ "1.0 points" is the worst reading of this defect and it is reachable.

    `_point_change(0.01)` is exactly 1.0, so every one of these sentences printed
    "1.0 points" before the fix. "1 points" is also wrong and is what a bare
    int() cast would produce.
    """
    sentences = [
        generate_futures_reason(
            market_name=MARKET,
            highlight_reasons=["major_movement_24h"],
            top_mover_name=STRONG_LABEL,
            top_mover_change=SINGLE,
        ),
        generate_futures_reason(
            market_name=MARKET,
            highlight_reasons=["moderate_movement_24h"],
            top_mover_name=STRONG_LABEL,
            top_mover_change=SINGLE,
        ),
        generate_futures_reason(
            market_name=MARKET,
            highlight_reasons=["major_surprise"],
            top_surprise_name=STRONG_LABEL,
            top_surprise_change=SINGLE,
            top_surprise_opened_at=OPENED_THIS_YEAR,
            now=NOW,
        ),
        generate_futures_headline(
            highlight_reasons=["major_movement_24h"],
            top_mover_name=STRONG_LABEL,
            top_mover_change=SINGLE,
        ),
        generate_futures_headline(
            market_name=MARKET,
            highlight_reasons=["major_movement_24h"],
            top_mover_name=WEAK_LABEL,
            top_mover_change=SINGLE,
        ),
        generate_futures_headline(
            highlight_reasons=["moderate_movement_24h"],
            top_mover_name=STRONG_LABEL,
            top_mover_change=SINGLE,
        ),
        generate_futures_headline(
            market_name=MARKET,
            highlight_reasons=["moderate_movement_24h"],
            top_mover_name=WEAK_LABEL,
            top_mover_change=SINGLE,
        ),
        generate_futures_headline(
            highlight_reasons=["major_surprise"],
            top_surprise_name=STRONG_LABEL,
            top_surprise_change=SINGLE,
            top_surprise_opened_at=OPENED_THIS_YEAR,
            now=NOW,
        ),
    ]

    assert len(sentences) == 8, "one arm per rewritten call site"
    for sentence in sentences:
        assert "1.0 point" not in sentence, sentence
        assert "1 points" not in sentence, sentence
        assert "1 point" in sentence, sentence


def test_a_real_decimal_still_prints_its_decimal():
    """The fix must route through the formatter, not round to an integer."""
    reason = generate_futures_reason(
        market_name=MARKET,
        highlight_reasons=["major_movement_24h"],
        top_mover_name=STRONG_LABEL,
        top_mover_change=DECIMAL,
    )
    headline = generate_futures_headline(
        highlight_reasons=["major_movement_24h"],
        top_mover_name=STRONG_LABEL,
        top_mover_change=DECIMAL,
    )
    assert "23.5 points" in reason, reason
    assert "23.5 points" in headline, headline


def test_no_call_site_interpolates_the_raw_float():
    """The class guard: `_point_change` feeds `_points` and nothing else.

    A future sentence that repeats `round(abs(v) * 100, 1)` inline is how these
    two formatters drifted apart in the first place, so the invariant is stated
    on the source rather than only on the eight sentences above.
    """
    from pathlib import Path

    import app.utils.feed_reasons as fr

    source = Path(fr.__file__).read_text()
    callers = [
        line.strip()
        for line in source.splitlines()
        if "_point_change(" in line and not line.strip().startswith("#")
    ]
    # Exactly two: the definition, and the single call inside `_points`. The
    # second is matched on shape rather than byte-for-byte, so renaming a local
    # does not fail this arm — only growing a third caller does.
    assert len(callers) == 2, callers
    assert callers[0].startswith("def _point_change("), callers[0]
    assert callers[1].endswith("= _point_change(value)"), callers[1]

"""#3721 — a slice is declared a slice.

``mutually_exclusive`` is a fact about the VENUE'S field; ``exhaustive`` is
stamped on OUR outcome set. Before the Item 4 guard, every branch of
``_outcome_relation`` read the first and wrote the second, so a ladder we hold
six of nine legs from was certified a complete single-winner partition.

The specimen is real and was live on production while these tests were written:
Polymarket event ``1011354``, "Club Atlético de Madrid vs. Real Madrid CF - 1st
Half Exact Score", nine open legs at the venue (read from Gamma 2026-09-18), six
stored here, rendered on ``/events/15312071`` as a complete field summing to 41%
two days before the Madrid derby. Missing: ``0 - 0``, ``0 - 1`` and ``Any Other
Score`` — the largest rung at the venue.

The guard only ever NARROWS, and only when a caller can establish the venue's
leg count for that exact market. The refusal half of ``_venue_leg_count`` is
therefore as load-bearing as the guard: ``market_count`` on a sub-market row
counts the parent's siblings, and passing it would strip ``exhaustive`` from
ordinary Yes/No pairs — a far bigger error than the one being fixed.
"""

from app.tasks.backfill_market_shapes import _venue_leg_count
from app.utils.market_shape import (
    REL_COMPETITORS,
    REL_RANGES,
    classify_market_semantics,
    input_fingerprint,
)

# The six legs actually stored for market 60856911, verbatim.
DERBY_STORED = [
    "Club Atlético de Madrid 1 - 0 Real Madrid CF",
    "Club Atlético de Madrid 1 - 1 Real Madrid CF",
    "Club Atlético de Madrid 1 - 2 Real Madrid CF",
    "Club Atlético de Madrid 0 - 2 Real Madrid CF",
    "Club Atlético de Madrid 2 - 0 Real Madrid CF",
    "Club Atlético de Madrid 2 - 1 Real Madrid CF",
]
# The three the venue serves and we do not.
DERBY_MISSING = [
    "Club Atlético de Madrid 0 - 0 Real Madrid CF",
    "Club Atlético de Madrid 0 - 1 Real Madrid CF",
    "Any Other Score",
]
DERBY_TITLE = "Club Atlético de Madrid vs. Real Madrid CF - 1st Half Exact Score"


def classify(names, **kw):
    return classify_market_semantics(
        outcome_names=names,
        source="polymarket",
        mutually_exclusive=True,
        **kw,
    )


# ---------------------------------------------------------------- the defect


def test_the_derby_slice_is_not_stamped_exhaustive():
    """Six of nine legs is not a partition, however exclusive the venue's field."""
    result = classify(DERBY_STORED, venue_leg_count=9)

    assert result["exhaustive"] is False
    assert result["outcome_count"] == 6
    assert "partial_field:6of9" in result["evidence"]


def test_the_relation_and_confidence_are_untouched_by_the_guard():
    """We are not less sure what KIND of market this is — only that we hold a
    subset of it. Narrowing the relation as well would hide the ladder from the
    surfaces that render ladders."""
    full = classify(DERBY_STORED + DERBY_MISSING, venue_leg_count=9)
    slice_ = classify(DERBY_STORED, venue_leg_count=9)

    assert slice_["outcome_relation"] == full["outcome_relation"] == REL_RANGES
    assert slice_["confidence"] == full["confidence"]
    assert slice_["expected_winners"] == full["expected_winners"]


def test_the_complete_ladder_is_still_exhaustive():
    """The positive control: hold every leg the venue serves and nothing moves."""
    result = classify(DERBY_STORED + DERBY_MISSING, venue_leg_count=9)

    assert result["exhaustive"] is True
    assert not any(e.startswith("partial_field") for e in result["evidence"])


def test_the_guard_also_covers_the_competitors_branch():
    """`exclusive_ranges` is not the only road to ``exhaustive: true`` — the
    structured one-winner branch reaches it too, and a 1X2 missing its draw is
    the same lie about a smaller field."""
    result = classify_market_semantics(
        outcome_names=["Atletico", "Real Madrid"],
        source="polymarket",
        mutually_exclusive=True,
        expected_winners=1,
        venue_leg_count=3,
    )

    assert result["outcome_relation"] == REL_COMPETITORS
    assert result["exhaustive"] is False
    assert "partial_field:2of3" in result["evidence"]


# ------------------------------------------------------- the guard only narrows


def test_omitting_the_count_leaves_every_output_identical():
    """A caller that cannot establish the venue's leg count pays nothing. This is
    what makes the change safe for every source that has no such number."""
    before = classify(DERBY_STORED)
    after = classify(DERBY_STORED, venue_leg_count=None)

    assert before == after
    assert before["exhaustive"] is True


def test_holding_as_many_legs_as_the_venue_is_not_a_slice():
    result = classify(DERBY_STORED, venue_leg_count=6)
    assert result["exhaustive"] is True


def test_holding_more_legs_than_the_venue_declares_never_narrows():
    """A stale or wrong ``market_count`` that UNDER-states the field must not be
    able to widen the guard's reach. Only a strict shortfall counts."""
    result = classify(DERBY_STORED, venue_leg_count=3)
    assert result["exhaustive"] is True


def test_the_guard_cannot_invent_an_exhaustive_true():
    """It narrows or it does nothing — it never promotes."""
    non_mx = classify_market_semantics(
        outcome_names=["Rider A", "Rider B", "Rider C"],
        source="polymarket",
        mutually_exclusive=None,
        venue_leg_count=99,
    )
    assert non_mx["exhaustive"] is not True


def test_a_market_that_never_claimed_a_partition_is_not_stamped_partial():
    """The guard fires on ``exhaustive is True`` and nothing else.

    A cumulative ladder is ``exhaustive: False`` before the guard ever runs — its
    rungs imply one another, so it never claimed to partition anything. Loosening
    the precondition to "not None" would leave its ``exhaustive`` untouched (False
    either way) while stamping it ``partial_field``, i.e. reporting that we
    narrowed a claim nobody made. The evidence list is the only place that shows,
    which is why this asserts on evidence rather than on ``exhaustive``.
    """
    cumulative = classify_market_semantics(
        outcome_names=["at least 1", "at least 2", "at least 3"],
        source="kalshi",
        mutually_exclusive=True,
        venue_leg_count=9,
    )

    assert cumulative["exhaustive"] is False
    assert not any(e.startswith("partial_field") for e in cumulative["evidence"])


# ------------------------------------------- the refusal half of the caller


def test_a_sub_market_row_yields_no_count_so_a_yes_no_pair_is_safe():
    """🔴 The trap this whole design exists to avoid. On a game's sub-market row
    ``market_count`` is the parent's sibling count (40 markets on one fixture),
    not this row's rungs. Handing it to the classifier would strip ``exhaustive``
    from a two-outcome Yes/No pair."""
    meta = {
        "market_count": 40,
        "event_title": "Club Atlético de Madrid vs. Real Madrid CF",
    }
    assert _venue_leg_count(meta, "Club Atlético de Madrid vs. Real Madrid CF - Player Props", True) is None

    # and end to end: the pair keeps its partition
    result = classify_market_semantics(
        outcome_names=["Yes", "No"],
        source="polymarket",
        mutually_exclusive=True,
        venue_leg_count=_venue_leg_count(meta, "… - Player Props", True),
    )
    assert result["exhaustive"] is True


def test_the_ladder_that_is_its_own_event_yields_its_count():
    meta = {"market_count": 9, "event_title": DERBY_TITLE}
    assert _venue_leg_count(meta, DERBY_TITLE, True) == 9


def test_no_count_without_a_venue_exclusivity_flag():
    meta = {"market_count": 9, "event_title": DERBY_TITLE}
    assert _venue_leg_count(meta, DERBY_TITLE, False) is None
    assert _venue_leg_count(meta, DERBY_TITLE, None) is None


def test_a_missing_or_unusable_count_is_refused_not_guessed():
    assert _venue_leg_count({"event_title": DERBY_TITLE}, DERBY_TITLE, True) is None
    assert (
        _venue_leg_count(
            {"market_count": "nine", "event_title": DERBY_TITLE}, DERBY_TITLE, True
        )
        is None
    )
    assert (
        _venue_leg_count(
            {"market_count": 0, "event_title": DERBY_TITLE}, DERBY_TITLE, True
        )
        is None
    )
    assert _venue_leg_count({}, None, True) is None


# ------------------------------------------------------------- the re-stamp


def test_the_fingerprint_moves_so_the_backfill_rewrites_the_affected_rows():
    """``changed`` in the backfill does NOT compare ``exhaustive``; it compares
    the display shape, the classifier version and this fingerprint. Without the
    fingerprint moving, the corrected stamp would never be written and the fix
    would be inert on every row already in the table."""
    assert input_fingerprint(
        outcome_names=DERBY_STORED, mutually_exclusive=True, venue_leg_count=9
    ) != input_fingerprint(outcome_names=DERBY_STORED, mutually_exclusive=True)


def test_the_fingerprint_is_unchanged_for_rows_the_guard_cannot_reach():
    """The key is added conditionally so that ~15k rows with no venue leg count
    are not all re-stamped at once for a rule that cannot apply to them."""
    assert input_fingerprint(
        outcome_names=DERBY_STORED, mutually_exclusive=True, venue_leg_count=None
    ) == input_fingerprint(outcome_names=DERBY_STORED, mutually_exclusive=True)


def test_a_countless_row_keeps_the_exact_fingerprint_master_gave_it():
    """🔴 The assertion above cannot see the failure it exists to prevent: if the
    key were added unconditionally, BOTH of its calls would carry
    ``venue_leg_count: None`` and still be equal to each other — while every row
    in the table silently got a new fingerprint and the beat re-stamped ~15k rows
    in one pass.

    So the value is pinned against the one tree that settles it. These two are
    ``input_fingerprint`` computed on ``origin/master`` (commit 28a43080a, the
    branch point) for the same inputs. Byte-equality here IS the statement "this
    change costs an unreachable row nothing".
    """
    assert (
        input_fingerprint(outcome_names=DERBY_STORED, mutually_exclusive=True)
        == "703ddec4e4d2eb15f709"
    )
    assert (
        input_fingerprint(outcome_names=["Yes", "No"], mutually_exclusive=True)
        == "cdf501d10f43e3076e1d"
    )

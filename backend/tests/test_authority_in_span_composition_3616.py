"""`identity.ours_only_in_span_composition` — their hole, or our second row.

PILLAR: MATCHING. SHIP: *nothing goes blank when ESPN does* — a sport fails over
to StatPal only after clearing D50's bar, and MLB reads 31 points under that bar
for a reason nobody could see on the row.

#3519 established that a miss inside StatPal's own span is the only part of
`ours_only` that could be evidence of a hole in the site. That is true of the
bucket and false of almost everything in it. Production 2026-09-06: MLB's in-span
bucket is 79 rows, and an independent census of our own table over the same dates
finds 253 rows resolving to 174 distinct games — 79 duplicates, the same 79.
Counted once per game the two sides agree on 173 of 174. The 68.65% was measuring
#3093, not StatPal (#3616).

These guards pin the decomposition, both directions of the invariant that makes
it readable, and the two ways it must refuse to answer rather than answer zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.utils.authority_agreement import (
    GOVERNING_IDENTITY_NUMBERS,
    Join,
    Side,
    build_agreement_row,
    pair_by_normalized_key,
)
from app.utils.nfl_team_matching import normalize_team


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _side(ref, away, home, start, **kw):
    return Side(ref=str(ref), home=home, away=away, start=start, **kw)


def _build(fixtures, rows, sport_key="americanfootball_nfl", **kw):
    return build_agreement_row(
        sport_key=sport_key,
        fixtures=fixtures,
        rows=rows,
        normalize=normalize_team,
        **kw,
    )


_SPAN = _utc("2026-09-10T00:00:00")


def _mlb_shape():
    """MLB's shape, scaled down: StatPal serves three days, we hold twins.

    Two of the three games are written twice on our side — the second row of
    each pair is the `completed`/livescores-space row #3093 describes — and one
    game inside the span really is ours alone.
    """
    fixtures = [
        _side("s1", "Athletics", "Rangers", _SPAN),
        _side("s2", "White Sox", "Astros", _SPAN + timedelta(days=1)),
        _side("s3", "Mets", "Rays", _SPAN + timedelta(days=2)),
    ]
    rows = [
        _side(1, "Athletics", "Rangers", _SPAN, label="closed"),
        # 20 minutes off, written by the other endpoint. One game, two rows.
        _side(2, "Athletics", "Rangers", _SPAN + timedelta(minutes=20), label="completed"),
        _side(3, "White Sox", "Astros", _SPAN + timedelta(days=1), label="closed"),
        _side(4, "White Sox", "Astros", _SPAN + timedelta(days=1), label="completed"),
        _side(5, "Mets", "Rays", _SPAN + timedelta(days=2), label="completed"),
        # Inside the span, one row, and StatPal has nothing under it. The residue.
        _side(6, "Cubs", "Brewers", _SPAN + timedelta(days=1, hours=6), label="closed"),
        # Outside the span entirely — their horizon. Must not be decomposed at all.
        _side(7, "Padres", "Reds", _SPAN - timedelta(days=30), label="closed"),
        _side(8, "Padres", "Reds", _SPAN - timedelta(days=30), label="completed"),
    ]
    return fixtures, rows


def test_the_in_span_misses_are_named_as_ours_or_theirs():
    """The finding, in one assertion.

    Three in-span misses. Two are our own second row for a game this same pass
    matched; one is the only row we hold. Before #3616 all three read as StatPal
    missing a game, and MLB's 79 read as 79 holes in the site.
    """
    identity = _build(*_mlb_shape())["identity"]

    assert identity["ours_only_by_horizon"]["inside_statpal_span"] == 3
    assert identity["ours_only_in_span_composition"] == {
        "second_row_for_a_matched_game": 2,
        "our_only_row_for_the_game": 1,
    }


def test_the_composition_sums_to_the_bucket_it_decomposes():
    """The invariant that lets a reader trust the split without re-deriving it.

    A decomposition that does not add up is worse than none: it invites the
    reader to subtract it from a bucket it does not cover. Asserted over four
    shapes rather than one, so the sum cannot be true by the arithmetic of a
    single fixture set.
    """
    fixtures, rows = _mlb_shape()
    cases = {
        "the mlb shape": (fixtures, rows),
        "no duplicates at all": (fixtures, [r for r in rows if int(r.ref) % 2 == 1]),
        "every in-span row a duplicate": (fixtures, rows[:5]),
        "nothing of ours inside the span": (fixtures, rows[6:]),
    }
    for name, (f, r) in cases.items():
        identity = _build(f, r)["identity"]
        composition = identity["ours_only_in_span_composition"]
        assert composition is not None, name
        assert (
            composition["second_row_for_a_matched_game"]
            + composition["our_only_row_for_the_game"]
            == identity["ours_only_by_horizon"]["inside_statpal_span"]
        ), name


def test_a_series_is_not_a_duplicate():
    """Three meetings of one pair share a key by design; they are three games.

    This is the assertion that forces the kickoff tolerance. The join keys on the
    normalised `(away, home)` pair alone, so without `WITHIN` every game of a
    series would read as a duplicate of the others — and MLB, where a three-game
    series is the unit of the schedule, would report its whole in-span bucket as
    our own fault for exactly the wrong reason.
    """
    fixtures = [_side("s1", "Athletics", "Rangers", _SPAN)]
    rows = [
        _side(1, "Athletics", "Rangers", _SPAN, label="closed"),
        _side(2, "Athletics", "Rangers", _SPAN + timedelta(days=1), label="closed"),
        _side(3, "Athletics", "Rangers", _SPAN + timedelta(days=2), label="closed"),
    ]
    # Only game 1 is inside StatPal's span at all; the other two are past its
    # last fixture, so the bucket is 0 and so is every part of it.
    identity = _build(fixtures, rows)["identity"]
    assert identity["ours_only_by_horizon"]["inside_statpal_span"] == 0
    assert identity["ours_only_in_span_composition"] == {
        "second_row_for_a_matched_game": 0,
        "our_only_row_for_the_game": 0,
    }

    # Widen StatPal's span to cover all three days and StatPal serves only the
    # first: the other two are now in-span misses, and they are DIFFERENT GAMES,
    # not second rows for the one that matched.
    fixtures = fixtures + [_side("s2", "Cubs", "Brewers", _SPAN + timedelta(days=2))]
    identity = _build(fixtures, rows)["identity"]
    assert identity["ours_only_by_horizon"]["inside_statpal_span"] == 2
    assert identity["ours_only_in_span_composition"] == {
        "second_row_for_a_matched_game": 0,
        "our_only_row_for_the_game": 2,
    }


def test_the_receipts_name_both_halves_of_the_pair():
    """A count cannot be acted on: #3093's repair must know which row to keep."""
    receipts = _build(*_mlb_shape())["receipts"]["ours_only_in_span_duplicates"]

    assert len(receipts) == 2
    for receipt in receipts:
        assert receipt["event_id"] in {"2", "4"}
        assert receipt["matched_row"] in {"1", "3"}
        # The pair is two DIFFERENT rows of ours, never a row against itself.
        assert receipt["event_id"] != receipt["matched_row"]


def test_a_join_that_cannot_say_publishes_none_and_not_zeros():
    """Tennis's relation is not a key, and zeros there would lie loudest.

    `pair_by_normalized_key`'s docstring says why no key can hold tennis:
    `Garcia` and `Garcia Garcia` are both reachable from `G. Garcia` and are not
    each other. A strategy that declares no identity relation on our side gets
    `None` — *not measured* — because the sport with the largest known duplicate
    population on the row (1,811 singles pairs over 120 days) is precisely the
    one a `0` would exonerate.
    """

    def keyless(fixtures, rows, normalize):
        join = pair_by_normalized_key(fixtures, rows, normalize)
        return Join(
            fixtures=join.fixtures,
            rows=join.rows,
            paired=join.paired,
            statpal_only=join.statpal_only,
            ours_only=join.ours_only,
            unusable_fixtures=join.unusable_fixtures,
            unusable_rows=join.unusable_rows,
            denominator_is="a resolver, not a key",
        )

    row = _build(*_mlb_shape(), pair_sides=keyless)

    assert row["identity"]["ours_only_in_span_composition"] is None
    assert row["receipts"]["ours_only_in_span_duplicates"] == []
    # And the bucket it would have decomposed is still published in full: the
    # refusal withholds the split, never the finding.
    assert row["identity"]["ours_only_by_horizon"]["inside_statpal_span"] == 3


def test_the_real_tennis_strategy_declares_no_relation_on_our_side():
    """The contract, against the shipped strategy rather than a stub.

    The test above proves the machinery refuses when a strategy is silent; this
    one proves tennis IS silent, so the refusal is reached by the sport it was
    written for. If tennis ever gains a defensible same-match relation it will
    fail here, which is the right place to have that argument.
    """
    from app.utils.authority_tennis_agreement import DOUBLES, SINGLES, pair_tennis_sides

    for draw in (SINGLES, DOUBLES):
        join = pair_tennis_sides([], [], normalize_team, draw=draw)
        assert join.same_game_on_our_side is None, draw


def test_a_side_with_no_span_publishes_none_rather_than_a_split_of_nothing():
    """`_split_against_span` calls this `unplaceable`; a zero split would not.

    With no timed StatPal fixture there is no window to be inside of, so every
    miss is unplaceable and the in-span bucket does not exist. Zeros here would
    decompose a bucket that was never measured — gotcha #53, and the same reason
    `ours_covered_in_span_pct` is `None` and not a triumphant 100%.
    """
    fixtures = [_side("s1", "Athletics", "Rangers", None)]
    rows = [_side(1, "Cubs", "Brewers", _SPAN, label="closed")]
    identity = _build(fixtures, rows)["identity"]

    assert identity["ours_covered_in_span_pct"] is None
    assert identity["ours_only_in_span_composition"] is None
    assert identity["ours_only_by_horizon"]["unplaceable"] == 1


def test_the_field_cannot_move_a_running_clock():
    """Three sports have seven-day clocks running. This field touches none.

    The composition governs nothing: it is not in `GOVERNING_IDENTITY_NUMBERS`,
    it is not subtracted from the in-span denominator, and for a sport whose
    inventory sits inside StatPal's span it is all zeros anyway. Pinned because
    "published, never subtracted" is spec rule 5 and this is the third field to
    claim it.
    """
    for numbers in GOVERNING_IDENTITY_NUMBERS.values():
        assert "ours_only_in_span_composition" not in numbers

    fixtures = [
        _side("s1", "Athletics", "Rangers", _SPAN),
        _side("s2", "White Sox", "Astros", _SPAN + timedelta(days=1)),
    ]
    rows = [
        _side(1, "Athletics", "Rangers", _SPAN, label="closed"),
        _side(2, "White Sox", "Astros", _SPAN + timedelta(days=1), label="closed"),
    ]
    identity = _build(fixtures, rows, sport_key="americanfootball_nfl")["identity"]

    assert identity["ours_covered_in_span_pct"] == 100.0
    assert identity["governing"]["gate"] == "MEETS"
    assert identity["ours_only_in_span_composition"] == {
        "second_row_for_a_matched_game": 0,
        "our_only_row_for_the_game": 0,
    }

    # And the duplicate that WOULD be counted does not change the percentage it
    # sits beside — reported, never subtracted.
    with_twin = rows + [
        _side(3, "Athletics", "Rangers", _SPAN + timedelta(minutes=20), label="completed")
    ]
    identity = _build(fixtures, with_twin)["identity"]
    assert identity["ours_only_in_span_composition"] == {
        "second_row_for_a_matched_game": 1,
        "our_only_row_for_the_game": 0,
    }
    assert identity["ours_covered_in_span_pct"] == 66.67  # 2 / (2 + 1), undiscounted
    assert identity["governing"]["gate"] == "BELOW"

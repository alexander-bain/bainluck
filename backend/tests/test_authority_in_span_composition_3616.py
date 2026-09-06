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
from itertools import permutations

from app.utils.authority_agreement import (
    GOVERNING_IDENTITY_NUMBERS,
    Join,
    Side,
    _ours_only_in_span_composition,
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
        "second_row_for_an_unmatched_game": 0,
        "our_only_row_for_the_game": 1,
    }


def test_two_duplicate_rows_for_a_game_statpal_never_listed_are_one_miss():
    """CERT-2104's BLOCK, and it was right.

    The first cut compared an in-span miss only against rows that MATCHED
    StatPal. So two rows of ours for a game StatPal genuinely does not list found
    no matched twin, both fell to the residue, and the row reported **two holes**
    where there is one game and one duplicate. Our own duplication inflating the
    hole count is the exact defect this field was built to remove, in the one
    corner where it was still doing it.

    The named regression: an unrelated StatPal span, two within-tolerance rows of
    ours for an unlisted game. One unique miss, one extra row, both ids in a
    receipt.
    """
    fixtures = [
        _side("s1", "Athletics", "Rangers", _SPAN),
        _side("s2", "Mets", "Rays", _SPAN + timedelta(days=2)),
    ]
    rows = [
        _side(1, "Athletics", "Rangers", _SPAN, label="closed"),
        _side(2, "Mets", "Rays", _SPAN + timedelta(days=2), label="closed"),
        # StatPal lists no Cubs @ Brewers at all. We hold it twice.
        _side(3, "Cubs", "Brewers", _SPAN + timedelta(days=1), label="closed"),
        _side(4, "Cubs", "Brewers", _SPAN + timedelta(days=1, minutes=20), label="completed"),
    ]
    row = _build(fixtures, rows)
    identity = row["identity"]

    assert identity["ours_only_by_horizon"]["inside_statpal_span"] == 2
    assert identity["ours_only_in_span_composition"] == {
        "second_row_for_a_matched_game": 0,
        "second_row_for_an_unmatched_game": 1,
        "our_only_row_for_the_game": 1,
    }

    receipts = row["receipts"]["ours_only_in_span_duplicates"]
    assert len(receipts) == 1
    assert receipts[0]["event_id"] == "4"
    assert receipts[0]["matched_row"] == "3"
    assert receipts[0]["duplicate_of"] == "another_unmatched_row_of_ours"

    # And a THIRD copy of the same unlisted game is a third row, not a second
    # game: the representative is chosen once and every later copy joins it.
    identity = _build(
        fixtures,
        rows + [_side(5, "Cubs", "Brewers", _SPAN + timedelta(days=1, minutes=40), label="live")],
    )["identity"]
    assert identity["ours_only_in_span_composition"] == {
        "second_row_for_a_matched_game": 0,
        "second_row_for_an_unmatched_game": 2,
        "our_only_row_for_the_game": 1,
    }


def _chain_of_three():
    """A 0/50/100-minute chain of our rows for a game StatPal never lists.

    The shape that makes the clustering order matter, and it is only reachable
    because `same_game` is a TOLERANCE: 0↔50 and 50↔100 are both inside the
    hour, 0↔100 is not. Nothing pairs, so all three land in `ours_only`.

    The refs sort in the OPPOSITE order to the kickoffs on purpose (`"30"`,
    `"12"`, `"7"` sort as `"12" < "30" < "7"`). Event ids in the real table are
    allocated roughly in time order, so a fixture that let the two agree would
    pass against a sort key that had quietly lost `start` and kept only `ref` —
    a guard that cannot tell the intended key from an accident of numbering.
    """
    fixtures = [
        _side("s1", "Athletics", "Rangers", _SPAN),
        _side("s2", "Mets", "Rays", _SPAN + timedelta(days=2)),
    ]
    base = _SPAN + timedelta(days=1)
    chain = [
        _side(30, "Cubs", "Brewers", base, label="closed"),
        _side(12, "Cubs", "Brewers", base + timedelta(minutes=50), label="completed"),
        _side(7, "Cubs", "Brewers", base + timedelta(minutes=100), label="live"),
    ]
    return fixtures, chain


def test_a_chain_of_three_reads_the_same_however_the_rows_arrive():
    """#3628 — the published number may not depend on the order of a `set`.

    Greedy clustering under a tolerance is order-dependent, and the order this
    function was handed is not fixed: `pair_by_normalized_key` iterates
    `set(by_key_f) | set(by_key_r)`, and CPython randomises string hashing per
    process. Rows at 0, 50 and 100 minutes read TWO ways, both defensible:

        earliest first  ->  0 is rep; 50 joins 0; 100 joins nobody  ->  2 games, 1 extra
        middle first    ->  50 is rep; 0 joins 50; 100 joins 50     ->  1 game,  2 extras

    Publishing either one *non-deterministically* is the defect. The guard
    drives the permutation directly rather than through `build_agreement_row`,
    because permuting that function's `rows` argument does NOT reliably permute
    what the join hands over — set iteration order is dominated by the hashes,
    not by insertion — so an end-to-end permutation would pass against the bug
    it is supposed to catch.
    """
    fixtures, chain = _chain_of_three()
    join = pair_by_normalized_key(fixtures, chain, normalize_team)
    assert len(join.ours_only) == 3 and not join.paired

    seen = set()
    for order in permutations(chain):
        counts, receipts = _ours_only_in_span_composition(
            list(order),
            [],
            fixtures,
            join.same_game_on_our_side,
            join.our_side_bucket_key,
        )
        seen.add(tuple(sorted(counts.items())))
        # The EARLIEST row represents its game, so the 100-minute row — which is
        # outside tolerance of it — is a second game rather than a third copy.
        # Documented on purpose, not decided by whichever row arrived first.
        assert counts == {
            "second_row_for_a_matched_game": 0,
            "second_row_for_an_unmatched_game": 1,
            "our_only_row_for_the_game": 2,
        }
        # The receipt is a PAIR of ids and #3093's repair reads it to decide
        # which row to keep, so it has to be stable too: the 50-minute row is
        # the extra, and the 0-minute row is what it duplicates.
        assert [(r["event_id"], r["matched_row"]) for r in receipts] == [("12", "30")]

    assert len(seen) == 1, f"six orderings produced {len(seen)} different answers"


def test_two_rows_at_the_same_kickoff_break_their_tie_the_same_way():
    """`start` alone is not a canonical order, and this is where it shows.

    The standing shape of a duplicate is two rows at the SAME kickoff — 14 of
    MLB's 79 pairs are a `scheduled`/schedule-id row beside a `scheduled`/blank
    one, written minutes apart at identical times. Sort on `start` only and
    Python's stable sort falls back to the order it was handed, which is the set
    iteration order this whole fix exists to stop depending on. The counts
    cannot move here — both rows are the same game either way — so the receipt
    is the only thing that can catch it, and the receipt is what #3093's repair
    acts on. `ref` breaks the tie: `"40" < "9"` as strings, so `40` represents
    the game and `9` is the extra, whichever order they arrive in.
    """
    fixtures = [
        _side("s1", "Athletics", "Rangers", _SPAN),
        _side("s2", "Mets", "Rays", _SPAN + timedelta(days=2)),
    ]
    at = _SPAN + timedelta(days=1)
    tie = [
        _side(9, "Cubs", "Brewers", at, label="scheduled"),
        _side(40, "Cubs", "Brewers", at, label="scheduled"),
    ]
    join = pair_by_normalized_key(fixtures, tie, normalize_team)

    for order in permutations(tie):
        counts, receipts = _ours_only_in_span_composition(
            list(order),
            [],
            fixtures,
            join.same_game_on_our_side,
            join.our_side_bucket_key,
        )
        assert counts["second_row_for_an_unmatched_game"] == 1
        assert counts["our_only_row_for_the_game"] == 1
        assert [(r["event_id"], r["matched_row"]) for r in receipts] == [("9", "40")]


def test_the_clustering_is_not_a_transitive_closure():
    """The fix for #3628 is an ORDER, and it must not become a closure.

    A closure would reach the 100-minute row from the 0-minute one across the
    50-minute bridge and call all three one game — an identity `same_game` never
    asserted about that pair, and a worse answer than either ordering it
    replaces. This pins the difference: 2 distinct games, not 1.
    """
    fixtures, chain = _chain_of_three()
    join = pair_by_normalized_key(fixtures, chain, normalize_team)

    counts, _ = _ours_only_in_span_composition(
        chain, [], fixtures, join.same_game_on_our_side, join.our_side_bucket_key
    )
    assert counts["our_only_row_for_the_game"] == 2
    assert counts["second_row_for_an_unmatched_game"] == 1


def test_the_receipt_names_the_same_matched_twin_whatever_order_they_arrive():
    """The count cannot move here, but the evidence can — so it is pinned too.

    A miss with two matched twins in its bucket is one
    `second_row_for_a_matched_game` whichever twin is found first. The receipt
    is not indifferent: it names one id, #3093's repair acts on that id, and a
    ref that changes between dynos is not evidence. Earliest wins, as above.
    """
    # Two fixtures, because one gives a zero-width span and the miss below sits
    # 15 minutes inside it — `_ours_only_in_span_composition` would skip it as
    # out of span and the guard would pass by measuring nothing.
    fixtures = [
        _side("s1", "Cubs", "Brewers", _SPAN),
        _side("s2", "Mets", "Rays", _SPAN + timedelta(days=2)),
    ]
    early = _side(20, "Cubs", "Brewers", _SPAN, label="closed")
    late = _side(
        21, "Cubs", "Brewers", _SPAN + timedelta(minutes=30), label="completed"
    )
    miss = _side(22, "Cubs", "Brewers", _SPAN + timedelta(minutes=15), label="live")
    join = pair_by_normalized_key(fixtures, [early], normalize_team)

    for paired in (
        [(fixtures[0], early), (fixtures[0], late)],
        [(fixtures[0], late), (fixtures[0], early)],
    ):
        counts, receipts = _ours_only_in_span_composition(
            [miss],
            paired,
            fixtures,
            join.same_game_on_our_side,
            join.our_side_bucket_key,
        )
        assert counts["second_row_for_a_matched_game"] == 1
        assert receipts[0]["matched_row"] == "20"


def test_the_matched_and_unmatched_duplicate_buckets_are_not_interchangeable():
    """The repair must not fix the new class by blurring it into the old one.

    Both buckets are our duplication and both are lane1's, but they are different
    evidence: one says *we wrote a second row for a game we can see StatPal has*,
    the other says *we wrote a second row for a game we cannot find at all*. The
    receipt says which, so a reader is never left inferring it from the counts.
    """
    fixtures = [
        _side("s1", "Athletics", "Rangers", _SPAN),
        # A second listed fixture, late enough that StatPal's span covers the
        # unlisted Cubs @ Brewers below. Without it those rows are `beyond
        # StatPal's last` and never reach the composition at all.
        _side("s2", "Mets", "Rays", _SPAN + timedelta(days=1)),
    ]
    rows = [
        _side(1, "Athletics", "Rangers", _SPAN, label="closed"),
        _side(2, "Athletics", "Rangers", _SPAN + timedelta(minutes=20), label="completed"),
        _side(5, "Mets", "Rays", _SPAN + timedelta(days=1), label="closed"),
        _side(3, "Cubs", "Brewers", _SPAN + timedelta(hours=6), label="closed"),
        _side(4, "Cubs", "Brewers", _SPAN + timedelta(hours=6, minutes=20), label="completed"),
    ]
    row = _build(fixtures, rows)

    assert row["identity"]["ours_only_in_span_composition"] == {
        "second_row_for_a_matched_game": 1,
        "second_row_for_an_unmatched_game": 1,
        "our_only_row_for_the_game": 1,
    }
    assert {r["event_id"]: r["duplicate_of"] for r in row["receipts"]["ours_only_in_span_duplicates"]} == {
        "2": "a_row_that_matched_statpal",
        "4": "another_unmatched_row_of_ours",
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
            + composition["second_row_for_an_unmatched_game"]
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
        "second_row_for_an_unmatched_game": 0,
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
        "second_row_for_an_unmatched_game": 0,
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


def test_half_a_same_game_contract_is_refused_at_construction():
    """A predicate without a bucket key is quadratic, and a cliff ships green.

    Measured before `our_side_bucket_key` existed, on synthetic data at MLB's own
    shape: one sport's build went 11ms → **867ms at 800 games and 5.5s at
    2,000**, 99% of it the twin scan, on an endpoint that builds six sports. The
    fallback that would have absorbed this — scan everything when no bucket key
    is declared — is exactly why it is refused instead.
    """
    import pytest

    common = dict(
        fixtures=[], rows=[], paired=[], statpal_only=[], ours_only=[],
        unusable_fixtures=[], unusable_rows=[],
    )
    for half in (
        {"same_game_on_our_side": lambda a, b: True},
        {"our_side_bucket_key": lambda side: "k"},
    ):
        with pytest.raises(ValueError, match="BOTH"):
            Join(**common, **half)

    # Neither is the tennis case and must construct cleanly; both is the default.
    Join(**common)
    Join(
        **common,
        same_game_on_our_side=lambda a, b: True,
        our_side_bucket_key=lambda side: "k",
    )


def test_the_twin_search_does_not_scan_every_matched_row():
    """The guard the 5.5-second build did not have.

    A timing assertion would be flaky; a CALL COUNT is not. With the bucket key
    doing its job the predicate is asked once per (miss, row-in-its-own-bucket),
    and a bucket is one series. Without it the count is misses x every matched
    row, which this bound rejects by two orders of magnitude.
    """
    calls = {"n": 0}
    real = pair_by_normalized_key

    def counting(fixtures, rows, normalize):
        join = real(fixtures, rows, normalize)
        inner = join.same_game_on_our_side

        def counted(a, b):
            calls["n"] += 1
            return inner(a, b)

        return Join(
            fixtures=join.fixtures,
            rows=join.rows,
            paired=join.paired,
            statpal_only=join.statpal_only,
            ours_only=join.ours_only,
            unusable_fixtures=join.unusable_fixtures,
            unusable_rows=join.unusable_rows,
            same_game_on_our_side=counted,
            our_side_bucket_key=join.our_side_bucket_key,
        )

    # 120 games across 12 distinct pairs, every one of them written twice.
    pairs = [(f"Away{i}", f"Home{i}") for i in range(12)]
    fixtures, rows = [], []
    for i in range(120):
        away, home = pairs[i % len(pairs)]
        start = _SPAN + timedelta(hours=i * 6)
        fixtures.append(_side(f"s{i}", away, home, start))
        rows.append(_side(i, away, home, start, label="closed"))
        rows.append(_side(f"d{i}", away, home, start + timedelta(minutes=20), label="completed"))

    identity = _build(fixtures, rows, pair_sides=counting)["identity"]
    misses = identity["ours_only_by_horizon"]["inside_statpal_span"]

    assert identity["ours_only_in_span_composition"] == {
        "second_row_for_a_matched_game": misses,
        "second_row_for_an_unmatched_game": 0,
        "our_only_row_for_the_game": 0,
    }
    # One bucket is one pair's ten meetings, so ~10 asks per miss. The unbucketed
    # scan would be misses x 120 matched rows — over a hundred thousand.
    assert calls["n"] <= misses * 20, (calls["n"], misses)


def test_the_bucket_key_never_separates_two_rows_the_predicate_joins():
    """The contract `our_side_bucket_key` makes, checked against the real join.

    A bucket that is finer than the predicate silently drops duplicates: the twin
    is there, the lookup misses it, and the row reports our own second row as
    StatPal's hole. Nothing else in the pass would notice.
    """
    join = pair_by_normalized_key([], [], normalize_team)
    same_game, bucket = join.same_game_on_our_side, join.our_side_bucket_key

    rows = [
        _side(1, "Athletics", "Rangers", _SPAN, label="closed"),
        _side(2, "Athletics", "Rangers", _SPAN + timedelta(minutes=20), label="completed"),
        # Same clubs, different meeting of the series — same bucket, not the same
        # game. Coarse is allowed; fine is not.
        _side(3, "Athletics", "Rangers", _SPAN + timedelta(days=2), label="closed"),
        _side(4, "Cubs", "Brewers", _SPAN, label="closed"),
    ]
    joined = 0
    for a in rows:
        for b in rows:
            if a.ref != b.ref and same_game(a, b):
                joined += 1
                assert bucket(a) == bucket(b), (a.ref, b.ref)
    assert joined == 2, "rows 1 and 2 must join, in both orders, and nothing else"


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
        "second_row_for_an_unmatched_game": 0,
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
        "second_row_for_an_unmatched_game": 0,
        "our_only_row_for_the_game": 0,
    }
    assert identity["ours_covered_in_span_pct"] == 66.67  # 2 / (2 + 1), undiscounted
    assert identity["governing"]["gate"] == "BELOW"

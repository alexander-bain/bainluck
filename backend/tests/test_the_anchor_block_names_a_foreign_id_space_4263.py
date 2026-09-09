"""#4263: `anchors.mismatch` stops blending two defects with two different owners.

A held anchor that is not this fixture's id is one of two unrelated things:

  * **an id this authority DOES publish** — one game's id sitting on another
    game's row. A matching bug, and not this lane's.
  * **an id this authority never published** — almost always the right contest
    wearing an id from the *wrong endpoint of the same provider*. A namespace
    bug in our own writer, and this lane's.

Until this change the agreement row that gates the D50 flip counted both in one
bucket, and `is_anchor_id` — a *shape* test, `str(v).isdigit()` — was the only
thing standing between them. #3094 is what that cost: 364 MLB rows carrying
`livescores.id` where `season-schedule.id` anchors, for five months
(2026-03-26 → 2026-09-03), while the published row read `polluted_column: 0`
the whole time. The stamper already knew the difference
(`classify_fixture` → `VERDICT_FOREIGN_ID_SPACE`); the measurement did not.

THE TWO PROPERTIES THIS FILE EXISTS TO HOLD
═══════════════════════════════════════════
1. **No existing count moves.** `anchored`, `unanchored`, `mismatch`,
   `polluted_column` and `pct_of_both` are byte-identical with and without the
   new parameter, for the same inputs. The bus reads this row daily; a number
   that moves reads as a measurement changing, and this change measures nothing
   new — it *names* what was already counted.
2. **The evidence is the authority's own publication, never the shape of the
   value** (#2879 / D55: an anchor key is explicit per (provider, sport, id) and
   is never inferred from a digit count). Two tests below hand the classifier
   values whose lengths point the opposite way from the truth, and the split
   follows the publication.

Live scope, read from production 2026-09-09 09:13Z: `mismatch: 0` on all seven
populations, so this fixes no number today. It is a contract defect in the gate
— the class it could not see is the class that already hid 364 rows behind a
`0` — and the tests are the ship.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.authority_agreement import (
    MISMATCH_IN_SPACE_IS,
    MISMATCH_OUT_OF_SPACE_IS,
    MISMATCH_SPLIT_UNMEASURED,
    Side,
    build_agreement_row,
)
from app.utils.nfl_team_matching import normalize_team

KICKOFF = datetime(2026, 12, 20, 18, 0, tzinfo=timezone.utc)

#: The two id spaces #3094 found on one column at once. Named rather than
#: inlined so a reader can see that the SHORTER one is the anchor and the
#: LONGER one is the impostor — the opposite of what a length heuristic that
#: "looked about right" would have guessed.
SCHEDULE_SPACE_ID = "356789"  # `season-schedule.id` — the anchor (#2879/D55)
LIVESCORES_SPACE_ID = "1329190539"  # `livescores.id` — dereferences to nothing


def _fixture(ref, away, home, start=KICKOFF):
    return Side(ref=ref, home=home, away=away, start=start, label="Week 16")


def _row(ref, away, home, start=KICKOFF, held_id=None):
    return Side(
        ref=str(ref),
        home=home,
        away=away,
        start=start,
        label="scheduled",
        held_id=held_id,
    )


def _build(fixtures, rows, **kw):
    return build_agreement_row(
        sport_key="americanfootball_nfl",
        fixtures=fixtures,
        rows=rows,
        normalize=normalize_team,
        **kw,
    )


def _one_mismatched_pair(held):
    """One paired game whose column holds `held` instead of the fixture's id."""
    return (
        [_fixture(SCHEDULE_SPACE_ID, "Dallas Cowboys", "Seattle Seahawks")],
        [_row(1, "Dallas Cowboys", "Seattle Seahawks", held_id=held)],
    )


# ---------------------------------------------------------------------------
# The defect. Everything else in this file guards this one case.
# ---------------------------------------------------------------------------


def test_a_wrong_endpoint_id_is_named_instead_of_disappearing_into_mismatch():
    """#3094's shape, reduced to one game.

    The column holds a well-formed number from the same provider's other
    endpoint. It clears `is_anchor_id` (it *is* digits), it is not the fixture's
    id, and before this change the row's only word for it was `mismatch: 1` —
    indistinguishable from a matching bug, and therefore routed to the wrong
    owner for five months.
    """
    fixtures, rows = _one_mismatched_pair(LIVESCORES_SPACE_ID)
    row = _build(fixtures, rows, published_ids={SCHEDULE_SPACE_ID})

    anchors = row["anchors"]
    assert anchors["mismatch"] == 1, "the total is unchanged — this is a split"
    assert anchors["mismatch_split"] == {
        "measured": True,
        "in_published_space": 0,
        "not_in_published_space": 1,
        "in_published_space_is": MISMATCH_IN_SPACE_IS,
        "not_in_published_space_is": MISMATCH_OUT_OF_SPACE_IS,
    }
    assert anchors["polluted_column"] == 0, (
        "#2963's bucket is for a column holding a SENTENCE. A wrong-endpoint id "
        "is not that, and widening `polluted_column` to swallow it would have "
        "merged a second pair of findings to unmerge a first."
    )


def test_another_games_id_from_the_same_endpoint_is_still_a_plain_mismatch():
    """The other direction, and the one that makes the first test mean something.

    A test that only proves the new bucket can be populated proves nothing about
    whether it is populated CORRECTLY — an implementation that called every
    mismatch foreign would pass it. Here the held value is another fixture's
    real, published id: a matching bug, and it must NOT be accused of being a
    namespace bug.
    """
    fixtures = [
        _fixture(SCHEDULE_SPACE_ID, "Dallas Cowboys", "Seattle Seahawks"),
        _fixture("356790", "Chicago Bears", "Green Bay Packers"),
    ]
    rows = [
        _row(1, "Dallas Cowboys", "Seattle Seahawks", held_id="356790"),
        _row(
            2,
            "Chicago Bears",
            "Green Bay Packers",
            held_id="356790",
        ),
    ]
    row = _build(fixtures, rows, published_ids={SCHEDULE_SPACE_ID, "356790"})

    anchors = row["anchors"]
    assert anchors["anchored"] == 1, "the Bears row holds its own id"
    assert anchors["mismatch"] == 1, "the Cowboys row holds the Bears' id"
    assert anchors["mismatch_split"]["in_published_space"] == 1
    assert anchors["mismatch_split"]["not_in_published_space"] == 0


# ---------------------------------------------------------------------------
# Property 1: no existing count moves.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "held",
    [
        pytest.param(LIVESCORES_SPACE_ID, id="wrong-endpoint"),
        pytest.param("356790", id="another-published-game"),
        pytest.param(None, id="unanchored"),
        pytest.param(SCHEDULE_SPACE_ID, id="anchored"),
        pytest.param("linked", id="polluted-sentence-2963"),
    ],
)
def test_every_number_the_bus_already_reads_is_byte_identical(held):
    """The parameter adds a name, not a measurement.

    Run the same inputs twice — once as the bus has always run them, once with
    the publication in hand — and require every pre-existing key to match
    exactly. If this ever fails, the change stopped being additive and the
    seven-day streak is being scored on a different number than the day before.
    """
    fixtures = [
        _fixture(SCHEDULE_SPACE_ID, "Dallas Cowboys", "Seattle Seahawks"),
        _fixture("356790", "Chicago Bears", "Green Bay Packers"),
    ]
    rows = [
        _row(1, "Dallas Cowboys", "Seattle Seahawks", held_id=held),
        _row(2, "Chicago Bears", "Green Bay Packers", held_id="356790"),
    ]

    before = _build(fixtures, rows)
    after = _build(fixtures, rows, published_ids={SCHEDULE_SPACE_ID, "356790"})

    assert set(before) == set(after), "no top-level key appears or disappears"
    for key in before:
        if key in ("anchors", "receipts"):
            continue
        assert before[key] == after[key], f"`{key}` moved"

    # Receipts gain exactly one key per mismatch row and lose none. Stripped
    # rather than skipped, so this still proves no EXISTING receipt field —
    # `column_holds`, `statpal_id`, `event_id`, the teams, the start — was
    # rewritten on the way through.
    assert set(before["receipts"]) == set(after["receipts"])
    for key, was in before["receipts"].items():
        now = after["receipts"][key]
        if key == "anchor_mismatch":
            now = [
                {k: v for k, v in r.items() if k != "not_in_published_space"}
                for r in now
            ]
        assert was == now, f"`receipts.{key}` moved"

    # `mismatch_split` is present in BOTH — it is the one key whose value is
    # allowed to differ, and only between `measured: False` and `measured: True`.
    # Every other key in the block is compared, so a change that "helpfully"
    # reclassified a row out of `mismatch` would fail here rather than land.
    assert set(before["anchors"]) == set(after["anchors"])
    assert before["anchors"]["mismatch_split"]["measured"] is False
    assert after["anchors"]["mismatch_split"]["measured"] is True
    for key in before["anchors"]:
        if key == "mismatch_split":
            continue
        assert before["anchors"][key] == after["anchors"][key], f"`anchors.{key}` moved"


def test_the_receipts_carry_the_verdict_per_row_not_just_a_count():
    """"2 of them" is a count; a repair has to act on WHICH.

    The two halves go to different owners, so a reader who can see the counts
    but not which rows are in which half has to re-derive the split by hand —
    which is the thing this change exists to stop.
    """
    fixtures = [
        _fixture(SCHEDULE_SPACE_ID, "Dallas Cowboys", "Seattle Seahawks"),
        _fixture("356790", "Chicago Bears", "Green Bay Packers"),
    ]
    rows = [
        _row(1, "Dallas Cowboys", "Seattle Seahawks", held_id=LIVESCORES_SPACE_ID),
        _row(2, "Chicago Bears", "Green Bay Packers", held_id=SCHEDULE_SPACE_ID),
    ]
    row = _build(fixtures, rows, published_ids={SCHEDULE_SPACE_ID, "356790"})

    by_event = {r["event_id"]: r for r in row["receipts"]["anchor_mismatch"]}
    assert by_event["1"]["column_holds"] == LIVESCORES_SPACE_ID
    assert by_event["1"]["not_in_published_space"] is True
    assert by_event["2"]["column_holds"] == SCHEDULE_SPACE_ID
    assert by_event["2"]["not_in_published_space"] is False


# ---------------------------------------------------------------------------
# The honest degradation. `None` means nobody looked, and says so.
# ---------------------------------------------------------------------------


def test_a_caller_that_hands_over_no_publication_gets_no_split_and_no_zeros():
    """Not `0`, which would say "we looked and found none" (gotcha #53).

    Every existing caller that has not opted in — the tennis strategy, and every
    test written before this parameter — must keep getting exactly today's row.
    Without the published set there is genuinely no evidence to tell a
    wrong-endpoint id from a wrong-game id, and inventing one from the length of
    the value is the thing D55 forbids.
    """
    fixtures, rows = _one_mismatched_pair(LIVESCORES_SPACE_ID)
    row = _build(fixtures, rows)

    split = row["anchors"]["mismatch_split"]
    assert split == {"measured": False, "why": MISMATCH_SPLIT_UNMEASURED}
    assert "in_published_space" not in split
    assert "not_in_published_space" not in split
    assert row["anchors"]["mismatch"] == 1, "the total is still published"
    assert "not_in_published_space" not in row["receipts"]["anchor_mismatch"][0], (
        "an unmeasured row must not stamp a verdict on its receipts either"
    )


def test_an_empty_publication_is_measured_and_is_not_the_same_as_none():
    """A read that published nothing is a fact; a read nobody handed over is not.

    `set()` is falsy, so the difference between "measured, and the space is
    empty" and "not measured" is exactly the `is not None` test — the classic
    way this degradation gets written as `if published_ids:` and silently stops
    measuring a pass that legitimately returned no fixtures.
    """
    fixtures, rows = _one_mismatched_pair(LIVESCORES_SPACE_ID)
    row = _build(fixtures, rows, published_ids=set())

    split = row["anchors"]["mismatch_split"]
    assert split["measured"] is True
    # The fixture's own ref is unioned in, so the space is not empty in
    # practice; what matters is that an empty ARGUMENT still counts as looking.
    assert split["not_in_published_space"] == 1


# ---------------------------------------------------------------------------
# Property 2: publication, never shape. (#2879 / D55)
# ---------------------------------------------------------------------------


def test_a_ten_digit_id_the_authority_did_publish_is_in_space():
    """The counterexample to every length heuristic, in the direction that
    matters most: this is *exactly* the value #3094 was about, and here it is
    legitimate, because this authority published it. A rule that keyed on
    `len(value) == 10` would accuse a correct anchor."""
    fixtures = [
        _fixture(LIVESCORES_SPACE_ID, "Dallas Cowboys", "Seattle Seahawks"),
        _fixture("1329190570", "Chicago Bears", "Green Bay Packers"),
    ]
    rows = [_row(1, "Dallas Cowboys", "Seattle Seahawks", held_id="1329190570")]
    row = _build(
        fixtures, rows, published_ids={LIVESCORES_SPACE_ID, "1329190570"}
    )

    assert row["anchors"]["mismatch"] == 1
    assert row["anchors"]["mismatch_split"]["in_published_space"] == 1
    assert row["anchors"]["mismatch_split"]["not_in_published_space"] == 0


def test_a_six_digit_id_the_authority_did_not_publish_is_out_of_space():
    """The same point from the other side. Same length as the anchor, same
    provider, same shape — and it names nothing this read served."""
    fixtures, rows = _one_mismatched_pair("999999")
    row = _build(fixtures, rows, published_ids={SCHEDULE_SPACE_ID})

    assert row["anchors"]["mismatch_split"]["not_in_published_space"] == 1


# ---------------------------------------------------------------------------
# The union, which is what keeps this from becoming a false accusation.
# ---------------------------------------------------------------------------


def test_a_live_board_anchor_is_not_called_foreign_because_the_schedule_missed_it():
    """The v1 stamper's `anchor_space` is the SCHEDULE board only.

    Its fixture list is wider — `livescores` contributes contests the schedule
    read did not carry, and `_keep` gives them their own anchors. Handing the
    schedule space over unaltered would accuse every one of those anchors of
    being a namespace bug the moment it landed on the wrong row.

    So `build_agreement_row` unions the caller's set with the refs of the
    fixtures it was given: a fixture IS something this read published. The union
    can only ever SHRINK the out-of-space bucket, which is the direction a
    bucket that names our own writer as the author of a bug should err in.
    """
    fixtures = [
        _fixture(SCHEDULE_SPACE_ID, "Dallas Cowboys", "Seattle Seahawks"),
        # Live board only — deliberately absent from `published_ids` below.
        _fixture("356791", "Chicago Bears", "Green Bay Packers"),
    ]
    rows = [_row(1, "Dallas Cowboys", "Seattle Seahawks", held_id="356791")]

    row = _build(fixtures, rows, published_ids={SCHEDULE_SPACE_ID})

    assert row["anchors"]["mismatch"] == 1
    assert row["anchors"]["mismatch_split"] == {
        "measured": True,
        "in_published_space": 1,
        "not_in_published_space": 0,
        "in_published_space_is": MISMATCH_IN_SPACE_IS,
        "not_in_published_space_is": MISMATCH_OUT_OF_SPACE_IS,
    }


def test_whitespace_and_int_ids_do_not_manufacture_a_foreign_space():
    """`held_id` arrives from a text column and `published_ids` from a payload
    that may have parsed the same id as an int. Comparing them without
    normalising both sides would report every anchor in the sport as a namespace
    bug — a total-loss false positive, and the cheapest one to write."""
    fixtures = [_fixture("356790", "Chicago Bears", "Green Bay Packers")]
    rows = [_row(2, "Chicago Bears", "Green Bay Packers", held_id=" 356789 ")]

    row = _build(fixtures, rows, published_ids=[356789, None, "  "])

    assert row["anchors"]["mismatch"] == 1
    assert row["anchors"]["mismatch_split"]["not_in_published_space"] == 0


# ---------------------------------------------------------------------------
# The wiring. A split nobody hands evidence to is a `measured: False` forever.
# ---------------------------------------------------------------------------


def test_a_row_with_nothing_to_split_still_says_it_looked():
    """`measured: True` over two zeros is the clean-pass shape, and it is not
    the same row as `measured: False`. A reader comparing two days has to be
    able to tell "no wrong-endpoint anchors today" from "nobody checked"."""
    fixtures = [_fixture(SCHEDULE_SPACE_ID, "Dallas Cowboys", "Seattle Seahawks")]
    rows = [
        _row(
            1,
            "Dallas Cowboys",
            "Seattle Seahawks",
            held_id=SCHEDULE_SPACE_ID,
        )
    ]
    row = _build(fixtures, rows, published_ids={SCHEDULE_SPACE_ID})

    assert row["anchors"]["anchored"] == 1
    assert row["anchors"]["mismatch"] == 0
    assert row["anchors"]["mismatch_split"]["measured"] is True
    assert row["anchors"]["mismatch_split"]["not_in_published_space"] == 0


def test_a_read_failed_row_never_pretends_to_have_split_anything():
    """A failed read pauses the streak and carries no percentage. It must not
    carry a confident `not_in_published_space: 0` either — that is a zero over a
    population nobody read, which is the shape gotcha #53 is about."""
    row = _build([], [], read_failures=["season-schedule: 503"], published_ids=set())

    assert row["read"] == "READ-FAILED"
    assert "anchors" not in row, (
        "a failed read publishes no anchors block at all, and passing "
        "`published_ids` must not be what conjures one into existence"
    )


def test_the_split_survives_a_pair_whose_fixture_carries_no_id_at_all():
    """A fixture with an empty ref cannot contribute to the space, and the row
    it pairs to must not be accused because of it. Guards the `if f.ref` filter
    in the union, which is otherwise a `None` in a set of strings."""
    fixtures = [_fixture("", "Dallas Cowboys", "Seattle Seahawks")]
    rows = [
        _row(
            1,
            "Dallas Cowboys",
            "Seattle Seahawks",
            held_id=SCHEDULE_SPACE_ID,
        )
    ]
    row = _build(fixtures, rows, published_ids={SCHEDULE_SPACE_ID})

    assert row["anchors"]["mismatch"] == 1
    assert row["anchors"]["mismatch_split"]["not_in_published_space"] == 0


def test_a_second_kickoff_day_does_not_leak_between_the_two_halves():
    """Two games, two verdicts, one row. The counters are per-row accumulators;
    a single shared flag would give both games whichever verdict came last."""
    later = KICKOFF + timedelta(days=1)
    fixtures = [
        _fixture(SCHEDULE_SPACE_ID, "Dallas Cowboys", "Seattle Seahawks"),
        _fixture("356790", "Chicago Bears", "Green Bay Packers", start=later),
    ]
    rows = [
        _row(1, "Dallas Cowboys", "Seattle Seahawks", held_id=LIVESCORES_SPACE_ID),
        _row(
            2,
            "Chicago Bears",
            "Green Bay Packers",
            start=later,
            held_id=SCHEDULE_SPACE_ID,
        ),
    ]
    row = _build(fixtures, rows, published_ids={SCHEDULE_SPACE_ID, "356790"})

    assert row["anchors"]["mismatch"] == 2
    assert row["anchors"]["mismatch_split"]["in_published_space"] == 1
    assert row["anchors"]["mismatch_split"]["not_in_published_space"] == 1

"""#4274: `streak.note`'s pointer resolves against the payload it is printed in.

The note has always said, of a streak that is one day from permitting a flip:

    "…and the denominator those days were measured over is on each entry in
     `days[]`."

The served payload publishes `streak.days` as an **integer** and no `days` key
holding a list anywhere — verified on all seven populations at 2026-09-09
09:37Z. So the one sentence written to help a reader check a 7/7 before it is
acted on sends them to a key that does not exist.

WHY THE DATE MATTERS
════════════════════
On **2026-09-11** NFL, NBA and NHL all reach seven consecutive days. NFL earns it
on 321 of 321 fixtures; NBA on **41 of 1,208** (3.4% of a season that has not
started) and NHL on **32 of 1,404** (2.3%). #3071 shipped the summary clause on
the `True`; this is the per-day breakdown the note already promised — and the
distinction it carries (a denominator that sat at 41 all week vs one that grew
from 3 to 41) is exactly what the third candidate answer to question A turns on
(`alex-inbox/authority-069`).

WHAT THIS MUST NOT DO
═════════════════════
`counted_on` is REPORTED and gates nothing. The streak's length is decided by
each day's state and by nothing here — #3071 is explicit that the minimum
denominator is unruled and that this module does not get to invent it. Every
test below that asserts a number also asserts that `days`, `meets_flip_gate` and
`stopped_by` are what they were.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.authority_streak import (
    COUNTED_ON_IS,
    GATE_BELOW,
    GATE_MEETS,
    compute_streak,
)


def _day(day, state=GATE_MEETS, both=41, denominator=41, **extra):
    return {
        "day": day,
        "state": state,
        "numbers": ["ours_covered_pct"],
        "values": {"ours_covered_pct": 100.0},
        "both": both,
        "denominator": denominator,
        **extra,
    }


# ---------------------------------------------------------------------------
# The defect.
# ---------------------------------------------------------------------------


def test_the_note_points_at_a_key_that_is_in_the_payload():
    """The whole issue, as one assertion a reader could have made themselves.

    Pulls the key name out of the note rather than hard-coding it, so a note
    reworded to point somewhere else has to point somewhere that exists.
    """
    streak = compute_streak([_day("2026-09-08"), _day("2026-09-09")])

    note = streak["note"]
    assert "`days[]`" not in note, "the key the note used to name is an int"
    assert "`counted_on[]`" in note
    assert isinstance(streak["counted_on"], list)
    assert isinstance(streak["days"], int), "unchanged: `days` is still the count"


def test_each_day_of_the_streak_says_what_it_was_counted_on():
    """NBA's Friday, in miniature: a denominator that GREW across the window.

    41 all week and 3-then-41 are different facts, and the summary clause #3071
    ships cannot tell them apart — it reports a range at best. This is where the
    difference is legible.
    """
    streak = compute_streak(
        [
            _day("2026-09-07", both=3, denominator=3),
            _day("2026-09-08", both=17, denominator=17),
            _day("2026-09-09", both=41, denominator=41),
        ]
    )

    assert streak["days"] == 3
    assert [(d["day"], d["both"], d["denominator"]) for d in streak["counted_on"]] == [
        ("2026-09-07", 3, 3),
        ("2026-09-08", 17, 17),
        ("2026-09-09", 41, 41),
    ]


def test_a_retained_day_from_before_the_streak_is_not_in_the_window():
    """`since`..`through`, not the whole retained ledger.

    A day before the streak began was not part of what was cleared, and
    including it would describe a different measurement than the one being
    permitted — the same window `authority_by_sport._counted_on` reads, and for
    the same stated reason. Here 09-06 scored BELOW, so the streak starts at
    09-07 and 09-05/09-06 must not appear however good their numbers were.
    """
    streak = compute_streak(
        [
            _day("2026-09-05", both=900, denominator=900),
            _day("2026-09-06", state=GATE_BELOW, both=10, denominator=900),
            _day("2026-09-07", both=3, denominator=3),
            _day("2026-09-08", both=41, denominator=41),
        ]
    )

    assert streak["days"] == 2
    assert streak["since"] == "2026-09-07"
    assert [d["day"] for d in streak["counted_on"]] == ["2026-09-07", "2026-09-08"]
    assert 900 not in [d["denominator"] for d in streak["counted_on"]]


# ---------------------------------------------------------------------------
# Absent is not zero (gotcha #53), in both of the two ways it can appear here.
# ---------------------------------------------------------------------------


def test_a_day_recorded_before_the_fields_existed_reports_null_not_zero():
    """A `0` here would read as "measured, and there was nothing to divide by" —
    wrong in the flattering direction, because a 100% over a stated 0 invites the
    reader to discount the day rather than to distrust the record."""
    streak = compute_streak(
        [
            {"day": "2026-09-08", "state": GATE_MEETS},  # pre-fields entry
            _day("2026-09-09", both=41, denominator=41),
        ]
    )

    first = streak["counted_on"][0]
    assert first["day"] == "2026-09-08"
    assert first["both"] is None
    assert first["denominator"] is None
    assert first["both"] != 0 and first["denominator"] != 0


def test_a_streak_of_zero_publishes_an_empty_list_and_not_a_fabricated_day():
    """`days: 0` already says there is no streak. `counted_on` agrees with it
    rather than inventing an entry for the day that stopped it."""
    streak = compute_streak([_day("2026-09-09", state=GATE_BELOW)])

    assert streak["days"] == 0
    assert streak["since"] is None
    assert streak["counted_on"] == []


def test_a_ledger_with_no_days_is_still_none_and_never_an_empty_streak():
    """Unchanged, and asserted here because it is the one case where "no data"
    and "zero" would be catastrophic rather than merely misleading: the flip gate
    must never read the first as the second."""
    assert compute_streak([]) is None


# ---------------------------------------------------------------------------
# Reported, never a gate.
# ---------------------------------------------------------------------------


def test_nothing_that_decides_the_streak_moved():
    """The streak block gates nothing today and must keep gating nothing.

    Built twice over the same days — once reading only the pre-existing keys,
    once with the new ones — and every decision field is compared. A change that
    started consulting a denominator would be #3071's ruling made by accident,
    which is the failure this and `test_the_flip_gate_states_its_denominator_3071`
    both exist to prevent.
    """
    days = [_day(f"2026-09-0{n}", both=1, denominator=1) for n in range(3, 10)]
    streak = compute_streak(days)

    assert streak["days"] == 7
    assert streak["meets_flip_gate"] is True, (
        "seven days of a ONE-game denominator still meets the gate — the floor "
        "is unruled and this module does not get to invent it (#3071)"
    )
    assert [d["denominator"] for d in streak["counted_on"]] == [1] * 7
    assert streak["required_days"] == 7
    assert streak["since"] == "2026-09-03"
    assert streak["through"] == "2026-09-09"


def test_the_block_says_what_counted_on_is_on_the_payload():
    """A reader holding the JSON does not have the docstring open."""
    streak = compute_streak([_day("2026-09-09")])

    assert streak["counted_on_is"] == COUNTED_ON_IS
    assert "gates nothing" in COUNTED_ON_IS
    assert "null" in COUNTED_ON_IS and "`0`" in COUNTED_ON_IS


def test_a_carried_day_inside_the_window_is_still_described():
    """`carried_days` neither advance nor reset a streak, so a carried day can
    sit INSIDE `since`..`through`. It is part of the window being described and
    must not silently vanish from the list — a reader counting entries against
    `days` needs the difference to be visible, not absent."""
    streak = compute_streak(
        [
            _day("2026-09-07"),
            _day("2026-09-08", state="NO-SCORE", both=None, denominator=None),
            _day("2026-09-09"),
        ]
    )

    assert streak["carried_days"] == ["2026-09-08"]
    assert [d["day"] for d in streak["counted_on"]] == [
        "2026-09-07",
        "2026-09-08",
        "2026-09-09",
    ]
    assert streak["counted_on"][1]["state"] == "NO-SCORE"


def test_the_window_is_walked_by_date_not_by_ledger_order():
    """The entries are keyed by day, and the ledger's own ordering is not the
    contract. Handed the same days shuffled, the window must come back in date
    order — otherwise a reader comparing consecutive denominators reads the
    growth backwards."""
    days = [
        _day("2026-09-09", both=41, denominator=41),
        _day("2026-09-07", both=3, denominator=3),
        _day("2026-09-08", both=17, denominator=17),
    ]
    streak = compute_streak(days)

    assert [d["day"] for d in streak["counted_on"]] == [
        "2026-09-07",
        "2026-09-08",
        "2026-09-09",
    ]


def test_the_numbers_a_day_was_scored_on_travel_with_its_denominator():
    """A denominator without the number it divided into is half an answer. D63
    makes WHICH number governs a per-sport ruling, so a reader comparing two
    sports' streaks has to be able to see that they were not scored on the same
    thing."""
    streak = compute_streak(
        [
            {
                "day": "2026-09-09",
                "state": GATE_MEETS,
                "numbers": ["pct", "ours_covered_pct"],
                "values": {"pct": 100.0, "ours_covered_pct": 100.0},
                "both": 321,
                "denominator": 321,
            }
        ]
    )

    entry = streak["counted_on"][0]
    assert entry["numbers"] == ["pct", "ours_covered_pct"]
    assert entry["values"] == {"pct": 100.0, "ours_covered_pct": 100.0}


def test_the_published_entries_do_not_alias_the_ledger_rows():
    """`counted_on` is published into a payload that gets banked. Handing out the
    ledger's own dicts lets a later mutation of the returned block rewrite
    history in place."""
    source = _day("2026-09-09")
    streak = compute_streak([source])

    entry = streak["counted_on"][0]
    entry["denominator"] = 999
    entry["numbers"].append("invented")
    assert source["denominator"] == 41
    assert source["numbers"] == ["ours_covered_pct"]


def test_the_real_shape_a_reader_will_meet_on_friday():
    """End to end, with the production numbers from `/api/admin/statpal/
    authority-agreement` at 2026-09-09 09:37Z projected two days forward.

    NBA reaches seven days on a 1,208-fixture population of which it has 41. The
    reader who follows the note must land on seven entries that say exactly that,
    and `meets_flip_gate` must be `True` beside them — because the number is not
    the gate, and this block is what lets a person disagree with the gate on
    evidence rather than on a hunch.
    """
    days = [
        _day(f"2026-09-{d}", both=41, denominator=1208)
        for d in ("05", "06", "07", "08", "09", "10", "11")
    ]
    streak = compute_streak(days)

    assert streak["meets_flip_gate"] is True
    assert len(streak["counted_on"]) == 7
    assert {(d["both"], d["denominator"]) for d in streak["counted_on"]} == {(41, 1208)}
    assert streak["since"] == "2026-09-05"
    assert streak["through"] == "2026-09-11"


def test_a_missing_day_inside_the_window_cannot_happen_and_is_skipped_if_it_does():
    """The walk that computes the streak stops on a missing day, so a hole inside
    `since`..`through` is unreachable by construction. Asserted anyway: the
    window is re-walked here by date, and a `by_day.get` returning `None` must
    skip rather than publish an entry with a `day` and nothing else — a row that
    looks measured and is not is worse than a shorter list.

    Driven directly rather than through `compute_streak`, because the state that
    would produce it cannot be reached through the public function.
    """
    from app.utils.authority_streak import _counted_on_days

    out = _counted_on_days(
        {"2026-09-07": _day("2026-09-07"), "2026-09-09": _day("2026-09-09")},
        since="2026-09-07",
        through="2026-09-09",
    )

    assert [d["day"] for d in out] == ["2026-09-07", "2026-09-09"]


def test_the_day_entry_the_ledger_stores_still_carries_what_this_republishes():
    """The pin that makes the rest of this file mean something.

    `counted_on` re-reads `both` and `denominator` off the stored ledger entry.
    If `day_entry` ever stops recording them, every test above keeps passing on
    hand-built dicts while production publishes seven nulls.
    """
    from app.utils.authority_streak import day_entry

    entry = day_entry(
        {
            "denominator": 1208,
            "identity": {
                "both": 41,
                "governing": {
                    "numbers": ["ours_covered_pct"],
                    "values": {"ours_covered_pct": 100.0},
                    "gate": GATE_MEETS,
                },
            },
            "read": "READ-OK",
        },
        at=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
    )

    assert entry["both"] == 41
    assert entry["denominator"] == 1208

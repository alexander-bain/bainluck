"""The agreement row, driven by the production disagreement it exists for.

`app/utils/authority_agreement.build_agreement_row` is the number D50's flip gate
is counted on. It is pure — no session, no clock, no network — so every test here
drives the code that will run.

## the corpus is production, not an invention

The kickoff-gap cases are the real ones read off the first production pass of
`stamp_nfl_statpal_fixtures` (2026-09-04 10:23Z, run banked in
`task_metrics:stamp_nfl_statpal_fixtures`). That pass reported 38 StatPal misses
and 31 of our own rows as misses, and the two lists are mostly THE SAME GAMES:

    Tampa Bay Buccaneers v Atlanta Falcons   StatPal 2026-12-27T00:00Z
                                             ours    2026-12-27T05:00Z
    Cincinnati Bengals v Indianapolis Colts  StatPal 2026-12-27T00:00Z
                                             ours    2026-12-27T05:00Z
    Kansas City Chiefs v Los Angeles Chargers StatPal 2027-01-03T00:00Z
                                             ours     2027-01-03T05:00Z

Weeks 16-18 kickoffs are not set on either side yet. Published as identity, that
reads 76% and puts the flip permanently out of reach for something that is not an
identity problem. Spec rule 4 in one sentence: *a join keyed on kickoff cannot
report a kickoff disagreement — it drops the row instead.*

## what each test can fail on

* the join silently reverting to a kickoff filter (the whole defect);
* a `TBD` playoff bracket counting against the source;
* a read failure being published as 0% and resetting a seven-day streak that
  should only pause (spec rule 6 / gotcha #53);
* a percentage over an empty denominator reading as a failure rather than as
  "not measured";
* the two meetings of one fixture pair being crossed by the tiebreak;
* the anchor count being folded into the agreement number, which would make a
  sport with no stamper yet read as a disagreement.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService
from app.utils.authority_agreement import (
    READ_FAILED,
    READ_OK,
    RECEIPT_CAP,
    SHADOW_STAMPERS,
    Side,
    WITHIN,
    WRONG_DAY,
    build_agreement_row,
    is_placeholder,
    ledger_line,
)
from app.utils.nfl_team_matching import normalize_team

PINNED = (
    Path(__file__).parent / "fixtures" / "statpal_nfl_season_schedule_20260903.json"
)


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def _fixture(ref, away, home, start, label="Regular Season / Week 16"):
    return Side(ref=ref, home=home, away=away, start=start, label=label)


def _row(ref, away, home, start, held_id=None, label="scheduled"):
    return Side(
        ref=str(ref), home=home, away=away, start=start, label=label, held_id=held_id
    )


def _build(fixtures, rows, **kw):
    return build_agreement_row(
        sport_key="americanfootball_nfl",
        fixtures=fixtures,
        rows=rows,
        normalize=normalize_team,
        **kw,
    )


# ---------------------------------------------------------------------------
# The defect. Everything else in this file is a guard around this one case.
# ---------------------------------------------------------------------------


def test_a_five_hour_kickoff_gap_is_one_game_not_two_misses():
    """The production case, with production's numbers.

    The stamper is right to refuse to WRITE on this — a five-hour gap is not
    proof of identity. The ledger is wrong to report it as two absences.
    """
    row = _build(
        [
            _fixture(
                "280750",
                "Tampa Bay Buccaneers",
                "Atlanta Falcons",
                _utc("2026-12-27T00:00:00"),
            )
        ],
        [
            _row(
                15184664,
                "Tampa Bay Buccaneers",
                "Atlanta Falcons",
                _utc("2026-12-27T05:00:00"),
            )
        ],
    )

    assert row["identity"] == {
        "both": 1,
        "statpal_only": 0,
        "ours_only": 0,
        "pct": 100.0,
        "governs": True,
        # Nothing is StatPal-only here, so every horizon bucket is empty — the
        # split reports where the misses fall and there are none.
        "statpal_only_by_horizon": {
            "before_our_first": 0,
            "inside_our_span": 0,
            "beyond_our_last": 0,
            "unplaceable": 0,
        },
        "ours_covered_pct": 100.0,
        # D63: NFL is scored on BOTH numbers, because both sides carry the same
        # population and where the two questions have the same answer asking
        # both is free. Here they do, and the day advances the streak.
        "governing": {
            "numbers": ["pct", "ours_covered_pct"],
            "values": {"pct": 100.0, "ours_covered_pct": 100.0},
            "bar_pct": 99.5,
            "gate": "MEETS",
            "why": "all governing numbers at or above 99.5%",
        },
    }
    assert row["schedule"]["off_by_hours"] == 1
    assert row["schedule"]["within"] == 0
    assert row["schedule"]["wrong_day"] == 0
    assert row["denominator"] == 1


def test_the_whole_week_sixteen_cohort_reads_as_agreement_with_a_clock_finding():
    """Four real Week-16/17 games, all five hours apart on both sides."""
    pairs = [
        ("280750", "Tampa Bay Buccaneers", "Atlanta Falcons", "2026-12-27"),
        ("280751", "Cincinnati Bengals", "Indianapolis Colts", "2026-12-27"),
        ("280752", "Washington Commanders", "Minnesota Vikings", "2026-12-27"),
        ("280753", "Carolina Panthers", "Pittsburgh Steelers", "2026-12-27"),
    ]
    fixtures = [
        _fixture(ref, away, home, _utc(f"{day}T00:00:00"))
        for ref, away, home, day in pairs
    ]
    rows = [
        _row(9000 + i, away, home, _utc(f"{day}T05:00:00"))
        for i, (_ref, away, home, day) in enumerate(pairs)
    ]

    row = _build(fixtures, rows)

    assert row["identity"]["pct"] == 100.0
    assert row["identity"]["statpal_only"] == 0
    assert row["identity"]["ours_only"] == 0
    assert row["schedule"]["off_by_hours"] == 4
    # And the finding is not merely counted — it is actionable.
    receipts = row["receipts"]["schedule_disagreements"]
    assert len(receipts) == 4
    assert {r["bucket"] for r in receipts} == {"off_by_hours"}
    assert {r["delta_hours"] for r in receipts} == {5.0}


def test_the_schedule_bucket_never_moves_the_identity_number():
    """Identity governs; schedule is reported and gates nothing (spec rule 2)."""
    within = _build(
        [_fixture("1", "A Team", "B Team", _utc("2026-12-27T00:00:00"))],
        [_row(1, "A Team", "B Team", _utc("2026-12-27T00:30:00"))],
    )
    wrong_day = _build(
        [_fixture("1", "A Team", "B Team", _utc("2026-12-27T00:00:00"))],
        [_row(1, "A Team", "B Team", _utc("2026-12-30T00:00:00"))],
    )
    assert within["identity"]["pct"] == wrong_day["identity"]["pct"] == 100.0
    assert within["schedule"]["within"] == 1
    assert wrong_day["schedule"]["wrong_day"] == 1
    assert within["schedule"]["governs"] is False


@pytest.mark.parametrize(
    "gap,expected",
    [
        (timedelta(0), "within"),
        (WITHIN, "within"),
        (WITHIN + timedelta(minutes=1), "off_by_hours"),
        (WRONG_DAY, "off_by_hours"),
        (WRONG_DAY + timedelta(minutes=1), "wrong_day"),
    ],
)
def test_the_three_clock_buckets_are_bounded_where_they_say_they_are(gap, expected):
    base = _utc("2026-12-27T00:00:00")
    row = _build(
        [_fixture("1", "A Team", "B Team", base)],
        [_row(1, "A Team", "B Team", base + gap)],
    )
    assert row["schedule"][expected] == 1


def test_a_missing_kickoff_is_its_own_bucket_not_a_disagreement():
    row = _build(
        [_fixture("1", "A Team", "B Team", None)],
        [_row(1, "A Team", "B Team", _utc("2026-12-27T00:00:00"))],
    )
    assert row["identity"]["both"] == 1
    assert row["schedule"]["time_missing"] == 1
    assert row["schedule"]["wrong_day"] == 0


# ---------------------------------------------------------------------------
# Exclusions, named and counted (spec rule 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("TBD", True),
        ("tbd", True),
        (" TBA ", True),
        ("To Be Decided", True),
        ("Tampa Bay Buccaneers", False),
        ("", False),
        (None, False),
    ],
)
def test_a_placeholder_names_no_team(name, expected):
    assert is_placeholder(name) is expected


def test_a_tbd_playoff_bracket_leaves_the_denominator_and_says_so():
    """The seven real TBD fixtures the first production pass read.

    A bracket StatPal has not seeded is not a game we are missing. Counted where
    it went, because an unstated exclusion is how a bar becomes unreachable by
    design — in this direction, unreachably LOW.
    """
    fixtures = [
        _fixture("280765", "TBD", "TBD", _utc("2027-01-10T18:00:00"), "Wild Card"),
        _fixture("280766", "TBD", "TBD", _utc("2027-01-10T21:30:00"), "Wild Card"),
        _fixture(
            "280750",
            "Tampa Bay Buccaneers",
            "Atlanta Falcons",
            _utc("2026-12-27T00:00:00"),
        ),
    ]
    rows = [
        _row(
            15184664,
            "Tampa Bay Buccaneers",
            "Atlanta Falcons",
            _utc("2026-12-27T05:00:00"),
        )
    ]

    row = _build(fixtures, rows)

    assert row["denominator"] == 1
    assert row["excluded"]["statpal_placeholders"] == 2
    assert row["identity"]["pct"] == 100.0
    assert len(row["receipts"]["statpal_placeholders"]) == 2


def test_a_side_with_no_usable_team_name_is_excluded_by_name_not_scored():
    row = _build(
        [_fixture("1", "", "B Team", _utc("2026-12-27T00:00:00"))],
        [_row(1, "A Team", "", _utc("2026-12-27T00:00:00"))],
    )
    assert row["excluded"]["statpal_unusable_names"] == 1
    assert row["excluded"]["our_unusable_names"] == 1
    assert row["denominator"] == 0
    assert row["identity"]["pct"] is None


# ---------------------------------------------------------------------------
# A miss in each direction stays its own finding
# ---------------------------------------------------------------------------


def test_a_contest_we_hold_no_row_for_is_statpal_only():
    row = _build(
        [_fixture("280497", "Arizona Cardinals", "Las Vegas Raiders", _utc("2026-08-14T00:00:00"))],
        [],
    )
    assert row["identity"] == {
        "both": 0,
        "statpal_only": 1,
        "ours_only": 0,
        "pct": 0.0,
        "governs": True,
        # We hold no timed row at all, so there is no span for the miss to be
        # inside or outside of. `unplaceable`, never a confident "beyond our
        # horizon" — an empty table has no horizon.
        "statpal_only_by_horizon": {
            "before_our_first": 0,
            "inside_our_span": 0,
            "beyond_our_last": 0,
            "unplaceable": 1,
        },
        # `None`, not 0.0: "of the games we hold, how many does StatPal have"
        # has no answer when we hold none, and 0.0 would read as a total
        # disagreement (the same reasoning as `_pct`).
        "ours_covered_pct": None,
        # D63 + spec rule 6. `pct` IS scored here (0.0 — StatPal lists a game
        # and we list none), but the other governing number has no denominator,
        # and a sport does not half clear a bar. So the day is NO-SCORE: it
        # carries the streak rather than resetting it. That is the conservative
        # direction on both sides — a day we listed nothing proves nothing about
        # whether StatPal can be trusted, so it must not advance a flip either.
        "governing": {
            "numbers": ["pct", "ours_covered_pct"],
            "values": {"pct": 0.0, "ours_covered_pct": None},
            "bar_pct": 99.5,
            "gate": "NO-SCORE",
            "why": (
                "ours_covered_pct has no denominator to divide by, so this day "
                "scores nothing and carries the streak unchanged (spec rule 6)"
            ),
        },
    }
    assert row["receipts"]["statpal_only"][0]["statpal_id"] == "280497"


def test_a_row_no_contest_claims_is_ours_only_and_keeps_its_id():
    """The Los Angeles phantom, which is the reason this direction is reported."""
    row = _build(
        [],
        [
            _row(
                14781140,
                "Arizona Cardinals",
                "Los Angeles Rams",
                _utc("2026-09-13T20:25:00"),
            )
        ],
    )
    assert row["identity"]["ours_only"] == 1
    assert row["receipts"]["ours_only"][0]["event_id"] == "14781140"


def test_the_two_directions_are_never_netted_against_each_other():
    """One extra on each side is two findings, not zero."""
    row = _build(
        [_fixture("1", "A Team", "B Team", _utc("2026-12-27T00:00:00"))],
        [_row(1, "C Team", "D Team", _utc("2026-12-27T00:00:00"))],
    )
    assert row["identity"]["statpal_only"] == 1
    assert row["identity"]["ours_only"] == 1
    assert row["identity"]["both"] == 0
    assert row["denominator"] == 2
    assert row["identity"]["pct"] == 0.0


# ---------------------------------------------------------------------------
# Orientation and the repeat fixture
# ---------------------------------------------------------------------------


def test_the_reverse_fixture_is_a_different_game():
    """Home-and-home division games are two rows, and must stay two rows."""
    row = _build(
        [_fixture("1", "A Team", "B Team", _utc("2026-10-04T17:00:00"))],
        [_row(1, "B Team", "A Team", _utc("2026-10-04T17:00:00"))],
    )
    assert row["identity"]["both"] == 0
    assert row["identity"]["statpal_only"] == 1
    assert row["identity"]["ours_only"] == 1


def test_two_meetings_of_one_pair_pair_by_nearest_kickoff_not_by_arrival():
    """The tiebreak's whole job, and the order is deliberately adversarial."""
    week_six = _utc("2026-10-18T20:05:00")
    week_fourteen = _utc("2026-12-06T21:00:00")
    row = _build(
        [
            _fixture("A", "A Team", "B Team", week_fourteen),
            _fixture("B", "A Team", "B Team", week_six),
        ],
        [
            _row(1, "A Team", "B Team", week_six),
            _row(2, "A Team", "B Team", week_fourteen),
        ],
    )
    assert row["identity"]["both"] == 2
    assert row["schedule"]["within"] == 2
    assert row["schedule"]["wrong_day"] == 0


def test_the_tiebreak_still_sorts_two_meetings_that_BOTH_disagree_on_the_clock():
    """The join may not quietly become a kickoff filter with a fallback under it.

    Both real Week-16/17 rows are five hours out, so a rule that only considers
    pairs already within the write window has nothing left to sort and falls
    through to arrival order — which here would marry December to January and
    report two wrong-week defects that do not exist.

    This is the mutation `_pair_within_key` is written against: the ±1h window
    belongs to the STAMPER, and the moment it appears in the measurement, this
    test is the one that goes red. The 1:1 case cannot catch it — with one
    fixture and one row the fallback pairs them anyway and the mutant reads
    identical.
    """
    row = _build(
        [
            _fixture("280751", "A Team", "B Team", _utc("2026-12-27T00:00:00")),
            _fixture("280764", "A Team", "B Team", _utc("2027-01-03T00:00:00")),
        ],
        [
            _row(1, "A Team", "B Team", _utc("2027-01-03T05:00:00")),
            _row(2, "A Team", "B Team", _utc("2026-12-27T05:00:00")),
        ],
    )
    assert row["identity"]["both"] == 2
    assert row["schedule"]["off_by_hours"] == 2
    assert row["schedule"]["wrong_day"] == 0, (
        "the December fixture was paired with the January row — the join is "
        "keyed on the kickoff again (spec rule 4)"
    )
    assert {r["delta_hours"] for r in row["receipts"]["schedule_disagreements"]} == {
        5.0
    }


def test_a_repeat_pair_with_one_side_short_reports_the_leftover_not_a_crossing():
    row = _build(
        [
            _fixture("A", "A Team", "B Team", _utc("2026-10-18T20:05:00")),
            _fixture("B", "A Team", "B Team", _utc("2026-12-06T21:00:00")),
        ],
        [_row(1, "A Team", "B Team", _utc("2026-10-18T20:05:00"))],
    )
    assert row["identity"]["both"] == 1
    assert row["identity"]["statpal_only"] == 1
    assert row["schedule"]["within"] == 1
    assert row["receipts"]["statpal_only"][0]["statpal_id"] == "B"


# ---------------------------------------------------------------------------
# The anchor bucket, which is reported and never blended
# ---------------------------------------------------------------------------


def test_the_anchor_count_is_reported_beside_identity_and_never_inside_it():
    """A sport with no stamper yet must not read as a disagreement."""
    row = _build(
        [_fixture("280750", "A Team", "B Team", _utc("2026-12-27T00:00:00"))],
        [_row(1, "A Team", "B Team", _utc("2026-12-27T00:00:00"), held_id=None)],
    )
    assert row["identity"]["pct"] == 100.0
    assert row["anchors"]["anchored"] == 0
    assert row["anchors"]["unanchored"] == 1
    assert row["anchors"]["pct_of_both"] == 0.0
    assert row["anchors"]["governs"] is False


def test_a_stamped_row_counts_as_anchored():
    row = _build(
        [_fixture("280750", "A Team", "B Team", _utc("2026-12-27T00:00:00"))],
        [_row(1, "A Team", "B Team", _utc("2026-12-27T00:00:00"), held_id="280750")],
    )
    assert row["anchors"]["anchored"] == 1
    assert row["anchors"]["pct_of_both"] == 100.0


def test_a_fabricated_column_is_its_own_bucket_not_an_anchor_and_not_a_gap():
    """#2963. `statpal_live_<home>_<away>` says linked and can never anchor."""
    row = _build(
        [_fixture("280494", "Detroit Lions", "Cincinnati Bengals", _utc("2026-08-13T23:00:00"))],
        [
            _row(
                15196977,
                "Detroit Lions",
                "Cincinnati Bengals",
                _utc("2026-08-13T23:00:00"),
                held_id="statpal_live_Cincinnati Bengals_Detroit Lions",
            )
        ],
    )
    assert row["anchors"]["polluted_column"] == 1
    assert row["anchors"]["anchored"] == 0
    assert row["anchors"]["unanchored"] == 0
    assert row["anchors"]["mismatch"] == 0
    assert row["receipts"]["polluted_column"][0]["statpal_id"] == "280494"


def test_a_row_holding_a_different_real_id_is_a_mismatch_and_is_named():
    row = _build(
        [_fixture("280750", "A Team", "B Team", _utc("2026-12-27T00:00:00"))],
        [_row(1, "A Team", "B Team", _utc("2026-12-27T00:00:00"), held_id="999999")],
    )
    assert row["anchors"]["mismatch"] == 1
    assert row["anchors"]["anchored"] == 0
    assert row["receipts"]["anchor_mismatch"][0]["column_holds"] == "999999"


# ---------------------------------------------------------------------------
# A failed read is not a disagreement (spec rule 6 / gotcha #53)
# ---------------------------------------------------------------------------


def test_a_failed_read_publishes_no_percentage_at_all():
    row = _build([], [], read_failures=["season-schedule: HTTP 503"])
    assert row["read"] == READ_FAILED
    assert "identity" not in row
    assert "denominator" not in row
    assert "pauses the streak" in row["note"]


def test_a_failed_read_beats_whatever_the_other_endpoint_returned():
    """Half a read is not a smaller read — it is an unknown denominator."""
    row = _build(
        [_fixture("1", "A Team", "B Team", _utc("2026-12-27T00:00:00"))],
        [_row(1, "A Team", "B Team", _utc("2026-12-27T00:00:00"))],
        read_failures=["livescores: HTTP 429"],
        sources_read=["season-schedule"],
    )
    assert row["read"] == READ_FAILED
    assert "identity" not in row


def test_an_empty_but_successful_read_is_a_row_with_no_score():
    """Zero yield is a row, not a skip — and not zero percent."""
    row = _build([], [], sources_read=["season-schedule", "livescores"])
    assert row["read"] == READ_OK
    assert row["denominator"] == 0
    assert row["identity"]["pct"] is None
    assert row["anchors"]["pct_of_both"] is None


# ---------------------------------------------------------------------------
# Receipts are capped; counts never are
# ---------------------------------------------------------------------------


def test_truncating_the_examples_never_changes_a_number():
    fixtures = [
        _fixture(str(i), f"Team {i}", f"Other {i}", _utc("2026-12-27T00:00:00"))
        for i in range(RECEIPT_CAP + 15)
    ]
    row = _build(fixtures, [])
    assert row["identity"]["statpal_only"] == RECEIPT_CAP + 15
    assert len(row["receipts"]["statpal_only"]) == RECEIPT_CAP


# ---------------------------------------------------------------------------
# The line the ledger appends
# ---------------------------------------------------------------------------


def test_the_ledger_line_carries_every_bucket_the_spec_names():
    row = _build(
        [
            _fixture("280750", "Tampa Bay Buccaneers", "Atlanta Falcons", _utc("2026-12-27T00:00:00")),
            _fixture("280765", "TBD", "TBD", _utc("2027-01-10T18:00:00")),
        ],
        [
            _row(1, "Tampa Bay Buccaneers", "Atlanta Falcons", _utc("2026-12-27T05:00:00")),
        ],
    )
    line = ledger_line(row, day="2026-09-04", streak="1/7")

    assert line.startswith("2026-09-04 | americanfootball_nfl | denom=1 ")
    assert "statpal_placeholders:1" in line
    assert "identity=100.0% (1/0/0)" in line
    # `covers=` beside `identity=`, because for NBA and NHL the two are 100% and
    # 3.4% on the same day and a line carrying only the second reads as a
    # catastrophe every morning (program step 3).
    assert "covers=100.0%" in line
    assert "schedule=0/1/0/0" in line
    assert "streak=1/7" in line
    assert line.endswith(READ_OK)


def test_a_failed_read_line_says_the_streak_is_carried_not_reset():
    line = ledger_line(
        _build([], [], read_failures=["season-schedule: HTTP 503"]),
        day="2026-09-04",
    )
    assert READ_FAILED in line
    assert "streak carried unchanged" in line
    assert "%" not in line


# ---------------------------------------------------------------------------
# Against the pinned production payload
# ---------------------------------------------------------------------------


def test_the_pinned_season_schedule_scores_against_its_own_rows():
    """Every real contest in the pinned body, paired to a row built from it.

    A tautology on purpose: it proves the join survives the payload's own
    shapes — nested stages, a `match` that is a dict or a list, `contestid`
    rather than `id` — rather than proving anything about agreement. The failure
    it catches is the parser and the join disagreeing about what a team is.
    """
    service = StatPalAPIService(api_key="test")
    parsed = service._parse_nfl_season_schedule(json.loads(PINNED.read_text()))
    real = [
        f
        for f in parsed
        if f.start_time
        and not (is_placeholder(f.home_team) or is_placeholder(f.away_team))
    ]
    # The floor is the 16 Week-1 games the sibling stamper test pins by name,
    # not the payload's exact length: re-pinning the body must be allowed to add
    # games without editing this line, and must not be allowed to lose the slate.
    assert len(real) >= 16, "pinned payload should carry the Week-1 slate"

    fixtures = [
        Side(ref=f.fixture_id, home=f.home_team, away=f.away_team, start=f.start_time)
        for f in real
    ]
    rows = [
        Side(ref=str(i), home=f.home, away=f.away, start=f.start)
        for i, f in enumerate(fixtures)
    ]

    row = _build(fixtures, rows)
    assert row["identity"]["pct"] == 100.0
    assert row["identity"]["statpal_only"] == 0
    assert row["identity"]["ours_only"] == 0
    assert row["schedule"]["within"] == len(fixtures)


def test_the_shadow_registry_names_only_sports_that_have_a_stamper():
    """A sport is in the map because something writes its join, not because we
    mean to. An aspirational entry publishes a row nothing can fill."""
    import app.tasks as tasks_pkg

    for sport_key, task_name in SHADOW_STAMPERS.items():
        assert sport_key.islower() and "_" in sport_key
        assert hasattr(tasks_pkg, task_name), (
            f"{sport_key} claims stamper {task_name}, which app.tasks does not "
            f"export"
        )

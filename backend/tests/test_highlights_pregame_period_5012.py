"""Guards for #5012 — a kickoff card must not say "Overtime".

Two minutes after kickoff, at 0-0, the night's marquee NFL game (49ers @ Rams,
`tier:1`, primetime) sat at **rank 2 of Discover page one** badged **Overtime**.

The cause is not the badge layer. ESPN keeps the PRE-GAME status detail in the
`period` field until the first in-game update lands, so `period` still read
`"Thu, September 10th at 8:35 PM EDT"` when `status` flipped to `live`.
`parse_game_progress` searched that sentence for an ordinal *anywhere*, found
`"10th"`, and read it as period 10 — beyond regulation in every sport we map:

    parse_game_progress("Thu, September 10th at 8:35 PM EDT", "americanfootball_nfl")
      -> (1.0, True)

It is the DAY OF THE MONTH, so there is no day on which the reading is right:
days 5-31 claim overtime, and days 1-4 report a false progress fraction instead
(a game kicking off on the 3rd read as 62.5% elapsed). The defect window is from
the status flip to ESPN's first in-game update — precisely the minutes when a
reader who came for kickoff is looking at the card.

**Two independent layers were added and each is pinned separately here**, because
either alone stops the reported string and a later edit could quietly delete one:

1. **The date refusal** — a month name, a weekday or a wall-clock time means the
   value is not a period at all, and it is refused before *any* reader sees it.
2. **The ordinal anchor** — an ordinal only says "period" when it leads the
   token. `test_a_sentence_with_an_ordinal_and_no_date_markers_*` carries no date
   markers at all, so it can only pass on layer 2.

Same family as #3208 (a 61' EPL card badged "Overtime"), whose general lesson —
never let a free-text field reach a numeric reader unanchored — is what this
applies to the rest of the function. The #3208 guards live in
`test_highlights_period_parse_3208.py` and are deliberately not duplicated;
what is repeated below is only what this fix could plausibly have broken.
"""

import calendar
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.highlights import (
    SPORT_TOTAL_PERIODS,
    WEIGHTS,
    compute_highlight,
    get_highlight_label,
    parse_game_progress,
)

#: The served payload, verbatim, from `GET /api/feed?limit=20&offset=0` at 00:37Z
#: on 2026-09-11 for event 14632820.
REPORTED_PERIOD = "Thu, September 10th at 8:35 PM EDT"

#: Sports whose live cards reach Discover. `tennis_*` is deliberately included
#: and deliberately absent from `SPORT_TOTAL_PERIODS` — it exercises the
#: `.get(sport_key, 4)` default path, which is where an unmapped sport lands.
SWEEP_SPORTS = [
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "basketball_nba",
    "basketball_ncaab",
    "icehockey_nhl",
    "baseball_mlb",
    "soccer_epl",
    "soccer_uefa_champs_league",
    "tennis_atp_us_open",
    None,
]


# --- The reported defect, head-on ---------------------------------------


def test_the_reported_kickoff_string_is_not_overtime():
    """The exact served string that badged the marquee NFL game."""
    progress, is_overtime = parse_game_progress(REPORTED_PERIOD, "americanfootball_nfl")
    assert is_overtime is False, (
        "the 49ers @ Rams card was badged 'Overtime' 120 seconds after kickoff "
        "at 0-0 because 'September 10th' was read as period 10"
    )
    assert progress == 0.0, (
        "a game still carrying its kickoff time in `period` has at most just "
        "started; 0.5 would hand a caller the 'mid-game' guess"
    )


def test_the_reported_string_really_does_contain_an_ordinal():
    """Non-vacuity: the guard above must be doing work.

    If the specimen carried no ordinal, `test_the_reported_kickoff_string...`
    would pass against the unfixed parser and prove nothing. This asserts the
    trap is actually baited.
    """
    import re

    assert re.search(
        r"\d+(?:st|nd|rd|th)\b", REPORTED_PERIOD.lower()
    ), "specimen no longer contains an ordinal — the defect it guards cannot fire"


def test_sunday_slate_kickoff_is_not_overtime():
    """The live-fire case this was fixed for.

    Filed Fri 2026-09-11. "September 13th" -> period 13 > 4, so every game of
    Sunday's NFL slate would have inherited the badge at kickoff.
    """
    _, is_overtime = parse_game_progress(
        "Sun, September 13th at 1:00 PM EDT", "americanfootball_nfl"
    )
    assert is_overtime is False


# --- The sweep: there is no day of the month on which this is right ------


@pytest.mark.parametrize("sport_key", SWEEP_SPORTS)
def test_no_day_of_any_month_is_ever_read_as_a_period(sport_key):
    """Every day of every month, in every sport, for all four ordinal suffixes.

    Written as a sweep rather than a specimen because the defect is keyed on the
    day of the month: a specimen on the 10th passes on the 3rd while still
    reporting 62.5% elapsed.
    """
    for month in range(1, 13):
        for day in range(1, 32):
            for suffix in ("st", "nd", "rd", "th"):
                period = (
                    f"Sun, {calendar.month_name[month]} {day}{suffix} at 8:35 PM EDT"
                )
                progress, is_overtime = parse_game_progress(period, sport_key)
                assert (
                    is_overtime is False
                ), f"{period!r} ({sport_key}) claimed overtime"
                assert progress == 0.0, (
                    f"{period!r} ({sport_key}) reported {progress} elapsed for a "
                    "game that has not started"
                )


def test_the_sweeps_sports_are_really_mapped():
    """Non-vacuity: most of the sweep must exercise a real period total.

    `SPORT_TOTAL_PERIODS.get(key, 4)` silently defaults, so a sweep over keys
    that are all unmapped would test one code path and look like ten.
    """
    mapped = [s for s in SWEEP_SPORTS if s in SPORT_TOTAL_PERIODS]
    assert len(mapped) >= 6, f"only {len(mapped)} sweep sports are mapped"
    assert len({SPORT_TOTAL_PERIODS[s] for s in mapped}) > 1, (
        "every mapped sweep sport has the same period total — the sweep cannot "
        "distinguish a per-sport bug"
    )


@pytest.mark.parametrize(
    "period",
    [
        "Thu, September 10th at 8:35 PM EDT",
        "Sun, September 13th at 1:00 PM EDT",
        "Mon, December 1st at 8:15 PM EST",
        "September 10th",
        "Thu, Sep 10 - 8:35 PM EDT",
        "8:35 PM EDT",
        "Sat at 4:05 p.m.",
        "Sunday",
    ],
)
def test_scheduled_datetime_shapes_are_refused(period):
    """Layer 1, across the shapes ESPN's pre-game detail actually takes.

    Includes the dash form, which the clock-strip at the top of the function
    rewrites to just the time before any reader sees it.
    """
    progress, is_overtime = parse_game_progress(period, "americanfootball_nfl")
    assert is_overtime is False
    assert progress == 0.0


# --- Layer 2 alone: the anchor, with no date marker to lean on -----------


@pytest.mark.parametrize(
    "period",
    [
        "delayed until the 10th",
        "postponed to the 21st",
        "rescheduled 13th",
    ],
)
def test_a_sentence_with_an_ordinal_and_no_date_markers_is_not_a_period(period):
    """The ordinal anchor, isolated.

    None of these contain a month, weekday or clock time, so layer 1 cannot fire
    and this can only pass on the anchored ordinal. Delete the anchor and these
    go red while every date-shaped test above stays green — which is the point of
    testing the two layers apart.
    """
    _, is_overtime = parse_game_progress(period, "americanfootball_nfl")
    assert is_overtime is False, f"{period!r} is prose, not period 10/21/13"


@pytest.mark.parametrize("period", ["100th", "1000th", "2026th"])
def test_a_long_number_with_an_ordinal_suffix_is_not_a_period(period):
    """The digit bound on the ordinal pattern.

    No sport we map has a hundredth period, so a long run of digits wearing an
    ordinal suffix is prose or a stray identifier, not extra innings. Unbounded,
    `100th` reads as period 100 and clears every sport's total — the strongest
    claim on the card from the weakest evidence, which is the same mistake #3208
    named for bare integers.
    """
    _, is_overtime = parse_game_progress(period, "baseball_mlb")
    assert is_overtime is False, f"{period!r} is not a beyond-regulation period"


def test_the_anchor_specimens_would_trip_an_unanchored_search():
    """Non-vacuity for the test above."""
    import re

    for period in [
        "delayed until the 10th",
        "postponed to the 21st",
        "rescheduled 13th",
    ]:
        assert re.search(
            r"(\d+)(?:st|nd|rd|th)\b", period
        ), f"{period!r} carries no ordinal — it cannot exercise the anchor"


# --- What the fix must not break ----------------------------------------


@pytest.mark.parametrize(
    "period,sport_key,expected",
    [
        # Baseball extra innings — an ordinal behind a half-inning qualifier
        # still says "period" out loud and keeps the beyond-regulation reading.
        ("Top 12th", "baseball_mlb", (1.0, True)),
        ("Bot 11th", "baseball_mlb", (1.0, True)),
        ("Middle 12th", "baseball_mlb", (1.0, True)),
        ("Top 3rd", "baseball_mlb", (2.5 / 9, False)),
        ("Bot 9th", "baseball_mlb", (8.5 / 9, False)),
        # Plain ordinals and keyword forms.
        ("1st Quarter", "basketball_nba", (0.125, False)),
        ("4th Quarter", "basketball_nba", (0.875, False)),
        ("3rd Period", "icehockey_nhl", (2.5 / 3, False)),
        ("Period 5", "basketball_nba", (1.0, True)),
        ("Q4", "basketball_nba", (0.875, False)),
        # The documented clock-prefixed ESPN shape.
        ("6:55 - 1st Quarter", "basketball_nba", (0.125, False)),
        ("14:50 - 1st Quarter", "americanfootball_nfl", (0.125, False)),
        # Explicit overtime, and the bare number rule from #3208.
        ("OT", "basketball_nba", (1.0, True)),
        ("2nd OT", "basketball_nba", (1.0, True)),
        ("4", "basketball_nba", (0.875, False)),
        ("Final", "soccer_epl", (1.0, False)),
        ("garbage", "soccer_epl", (0.5, False)),
    ],
)
def test_real_period_tokens_are_unchanged(period, sport_key, expected):
    """Pinned to the values these returned BEFORE the fix, measured on master.

    Every one of them is a string the anchor or the date refusal could plausibly
    have swallowed.
    """
    progress, is_overtime = parse_game_progress(period, sport_key)
    assert (pytest.approx(progress), is_overtime) == (
        pytest.approx(expected[0]),
        expected[1],
    )


def test_the_soccer_minute_clock_is_untouched():
    """#3208's subject must not be collateral — 61' has no date marker but does
    have digits, and the date refusal runs before the minute-clock branch."""
    progress, is_overtime = parse_game_progress("61'", "soccer_epl")
    assert is_overtime is False
    assert progress == pytest.approx(61 / 90)


# --- End to end: the chip and the score a reader actually gets -----------
#
# The parse tests prove the unit. #3208's lesson is that a wrong tuple deep in a
# helper surfaces as a wrong WORD on a card and fabricated points of ranking, so
# the chain is proved too.


def _live_nfl(period, home_prob=0.52):
    """The 49ers @ Rams card as served: live, 0-0, two minutes after kickoff.

    `home_prob` is a knob for one test only — see
    `test_the_kickoff_card_collects_no_fabricated_urgency`, which needs both
    arms to sit below the score cap.
    """
    now = datetime(2026, 9, 11, 0, 37, tzinfo=timezone.utc)
    return compute_highlight(
        status="live",
        commence_time=now - timedelta(minutes=2),
        sport_key="americanfootball_nfl",
        current_home_prob=home_prob,
        current_away_prob=1 - home_prob,
        opening_home_prob=0.50,
        opening_away_prob=0.50,
        now=now,
        period=period,
    )


def test_the_kickoff_card_is_not_labelled_overtime():
    """The badge Alex would see and disbelieve."""
    result = _live_nfl(REPORTED_PERIOD)
    assert "overtime" not in result.reasons
    assert get_highlight_label(result) != "Overtime"


def test_the_kickoff_card_collects_no_fabricated_urgency():
    """The invisible half: the feed ranking.

    An overtime game earns `live_late_game + live_overtime`. A two-minute-old
    game must earn neither, and the assertion is on the DIFFERENCE against a
    genuine overtime control rather than a pinned total that would rot the next
    time a weight is retuned.

    Deliberately run on a LOPSIDED game (0.70/0.30). At the served 0.52/0.48 the
    overtime arm scores 100 — the cap — and the measured gap reads 15 rather
    than 20, so the test would be asserting the clip, not the defect.
    """
    kickoff = _live_nfl(REPORTED_PERIOD, home_prob=0.70)
    real_ot = _live_nfl("OT", home_prob=0.70)
    assert "overtime" in real_ot.reasons, "control arm must actually be overtime"
    assert "late_game" not in kickoff.reasons
    assert (
        real_ot.score < 100
    ), "control arm is at the score cap — the gap below would measure the clip"
    assert (
        real_ot.score - kickoff.score
        == WEIGHTS["live_late_game"] + WEIGHTS["live_overtime"]
    )


def test_a_real_nfl_overtime_still_says_overtime_end_to_end():
    """Guards the over-correction in the sport the defect was reported in."""
    result = _live_nfl("OT")
    assert "overtime" in result.reasons
    assert get_highlight_label(result) == "Overtime"


def test_a_genuinely_late_game_still_earns_its_late_bonus():
    """The date refusal returns 0.0 progress; it must only do so for dates.

    A real 4th-quarter card still has to read as late, or the fix would have
    bought the kickoff card's correctness with every closing minute in the feed.
    """
    late = _live_nfl("4th Quarter")
    kickoff = _live_nfl(REPORTED_PERIOD)
    assert "late_game" in late.reasons, "4th Quarter is genuinely late"
    assert "late_game" not in kickoff.reasons
    assert late.score > kickoff.score

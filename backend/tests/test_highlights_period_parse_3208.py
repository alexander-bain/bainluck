"""Guards for `parse_game_progress` — the period string is not always a period.

#3208: a live EPL card reading **61'** carried the amber reason chip "Overtime",
in a competition whose league fixtures have no overtime at all. The cause was
not the chip layer. `parse_game_progress` read soccer's clock MINUTE as a period
index, and since soccer has 2 halves, every minute after the 2nd cleared
`period_num > total` and returned `(1.0, True)`.

Two things were wrong with that, and both are guarded here:

1. **The label.** `is_overtime=True` put "Overtime" on an ordinary first-half
   match (`get_highlight_label`, and the `priority_order` display list).
2. **The score, which nobody saw.** `compute_highlight` adds
   `live_late_game + live_overtime` = +20 for an overtime game, so every live
   soccer match in the feed carried 20 points of fabricated urgency and was
   ranked as though it were about to finish.

The invariant these tests are named for is wider than soccer: **a number is only
allowed to mean "beyond regulation" when the string says it is a period.** A
bare integer is the one form carrying no such evidence, so it may not conclude
overtime. Ordinals and keyword forms ("Top 12th", "Period 5") still may, and the
MLB/NHL/NBA cases below exist to keep this fix from buying soccer's correctness
with theirs.
"""

import pytest

from app.utils.highlights import (
    SOCCER_REGULATION_MINUTES,
    SPORT_TOTAL_PERIODS,
    parse_game_progress,
)


# --- The reported defect -------------------------------------------------

@pytest.mark.parametrize("period", ["1'", "31'", "45'", "45+2'", "61'", "62'", "89'"])
@pytest.mark.parametrize(
    "sport_key",
    ["soccer_epl", "soccer_spain_la_liga", "soccer_germany_bundesliga", "soccer_italy_serie_a"],
)
def test_soccer_clock_minute_is_never_overtime(period, sport_key):
    """#3208 head-on: a minute on the clock is not a period beyond regulation."""
    progress, is_overtime = parse_game_progress(period, sport_key)
    assert is_overtime is False, (
        f"{period} in {sport_key} reported overtime; league soccer has none, "
        "and this is the exact string that badged a 61' EPL card 'Overtime'"
    )
    assert 0.0 <= progress <= 1.0


def test_soccer_minute_becomes_proportional_progress_not_a_full_game():
    """The 61' card: roughly two-thirds through, not finished.

    The old code returned 1.0 here, which is what fed the late-game bonus.
    """
    progress, is_overtime = parse_game_progress("61'", "soccer_epl")
    assert is_overtime is False
    assert progress == pytest.approx(61 / SOCCER_REGULATION_MINUTES)
    assert progress < 1.0


def test_soccer_progress_rises_with_the_clock():
    """Ordering, not magic numbers — a later minute is always further along."""
    minutes = ["5'", "20'", "31'", "44'", "60'", "75'", "88'"]
    values = [parse_game_progress(m, "soccer_epl")[0] for m in minutes]
    assert values == sorted(values)
    assert len(set(values)) == len(values), "distinct minutes must not collapse"


def test_soccer_stoppage_time_is_regulation_and_is_capped():
    """90+3' is a long regulation, not extra time.

    This function cannot tell a cup tie's extra time from three added minutes;
    the explicit "extra time" branch is the only trustworthy signal and it has
    already run by this point. Claiming overtime here would be guessing.
    """
    for period in ["90+3'", "90+7'", "45+2'"]:
        progress, is_overtime = parse_game_progress(period, "soccer_epl")
        assert is_overtime is False, f"{period} is stoppage time, not overtime"
        assert progress <= 1.0, "progress must never exceed a whole game"


def test_soccer_minute_past_regulation_is_clamped_to_one_whole_game():
    """A cup tie's extra time can arrive as a raw minute: "105'", "120'".

    `minute / 90` overflows past 1.0 there, and progress is a FRACTION of the
    game — a caller scaling a bonus by it (`compute_highlight`'s late-game
    bonus does exactly that) would be handed 1.33 and pay out more than the
    maximum. Written with minutes above 90 deliberately: the stoppage strings
    in the test above all cap at 1.0 on their own, so they cannot fail if the
    clamp is deleted, and for a while this clamp had no guard that could fail.
    """
    for period, raw in [("105'", 105 / 90), ("120'", 120 / 90)]:
        progress, is_overtime = parse_game_progress(period, "soccer_epl")
        assert raw > 1.0, "test would be vacuous if the raw value fit"
        assert progress == 1.0, f"{period} must clamp, got {progress}"
        assert is_overtime is False


def test_soccer_explicit_extra_time_words_still_report_overtime():
    """The fix must not go so far that real extra time stops registering."""
    for period in ["Extra Time", "extra time", "Penalties", "Shootout"]:
        _, is_overtime = parse_game_progress(period, "soccer_epl")
        assert is_overtime is True, f"{period} genuinely is beyond regulation"


# --- What the fix must not break ----------------------------------------

def test_baseball_extra_innings_still_detected():
    """"Top 12th" in a 9-inning sport IS beyond regulation.

    An ordinal says "period" out loud, so it keeps the inference. This is the
    test that stops the #3208 fix from being over-applied. (The *wording* of
    the resulting chip is #2757's separate complaint, not this one's.)
    """
    for period in ["Top 12th", "Bot 11th", "Middle 12th"]:
        progress, is_overtime = parse_game_progress(period, "baseball_mlb")
        assert is_overtime is True, f"{period} is extra innings"
        assert progress == 1.0


def test_baseball_regulation_innings_are_not_overtime():
    for period in ["Top 3rd", "Bot 9th", "Top 1st"]:
        _, is_overtime = parse_game_progress(period, "baseball_mlb")
        assert is_overtime is False


@pytest.mark.parametrize(
    "sport_key,period",
    [
        ("basketball_nba", "OT"),
        ("basketball_nba", "2nd OT"),
        ("basketball_nba", "Period 5"),
        ("icehockey_nhl", "Period 4"),
        ("icehockey_nhl", "OT"),
        ("americanfootball_nfl", "OT"),
    ],
)
def test_keyword_and_ordinal_overtime_survives(sport_key, period):
    _, is_overtime = parse_game_progress(period, sport_key)
    assert is_overtime is True, f"{period} in {sport_key} must still be overtime"


@pytest.mark.parametrize(
    "sport_key,period",
    [
        ("basketball_nba", "Q4"),
        ("basketball_nba", "1st Quarter"),
        ("basketball_nba", "4th Quarter"),
        ("icehockey_nhl", "3rd Period"),
        ("americanfootball_nfl", "Q1"),
        ("basketball_ncaab", "2nd Half"),
    ],
)
def test_regulation_play_is_not_overtime(sport_key, period):
    _, is_overtime = parse_game_progress(period, sport_key)
    assert is_overtime is False, f"{period} in {sport_key} is regulation"


def test_clock_prefixed_period_still_parses():
    """"6:55 - 1st Quarter" — the documented ESPN shape, stripped at the dash."""
    progress, is_overtime = parse_game_progress("6:55 - 1st Quarter", "basketball_nba")
    assert is_overtime is False
    assert progress == pytest.approx(0.125)


def test_bare_period_number_within_regulation_still_reads_as_a_period():
    """A bare "4" in a 4-quarter sport is period 4, and stays so."""
    progress, is_overtime = parse_game_progress("4", "basketball_nba")
    assert is_overtime is False
    assert progress == pytest.approx(3.5 / 4)


# --- The general invariant ----------------------------------------------

def test_unlabelled_number_beyond_total_periods_never_claims_overtime():
    """The wider rule, checked where soccer cannot reach.

    A bare integer larger than the sport has periods is far more likely a clock
    than an Nth period. The old code took it as proof of overtime — the strongest
    claim on the card, from its weakest evidence.
    """
    for sport_key in ["basketball_nba", "icehockey_nhl", "baseball_mlb"]:
        for period in ["31", "47", "88"]:
            _, is_overtime = parse_game_progress(period, sport_key)
            assert is_overtime is False, (
                f"bare {period!r} in {sport_key} is not evidence of overtime"
            )


def test_soccer_minute_without_a_sport_key_still_avoids_overtime():
    """Defence in depth: the general guard covers an unmapped/missing sport.

    `_is_minute_clock_sport` cannot fire when the key is absent, so this leans
    entirely on the bare-number rule — which is why that rule exists separately
    rather than being folded into the soccer branch.
    """
    for sport_key in [None, "", "soccer_unmapped_league_2027"]:
        _, is_overtime = parse_game_progress("61'", sport_key)
        assert is_overtime is False, f"61' with sport_key={sport_key!r}"


def test_every_soccer_league_we_map_is_treated_as_a_minute_clock():
    """Stops a league being added to the periods map but not the clock check."""
    soccer_keys = [k for k in SPORT_TOTAL_PERIODS if k.startswith("soccer_")]
    assert soccer_keys, "no soccer leagues mapped — this guard would be vacuous"
    for key in soccer_keys:
        _, is_overtime = parse_game_progress("61'", key)
        assert is_overtime is False, f"{key} reads a clock minute as overtime"


def test_degenerate_inputs_do_not_raise_or_claim_overtime():
    for period in [None, "", "   ", "garbage", "Final", "-", "'"]:
        progress, is_overtime = parse_game_progress(period, "soccer_epl")
        assert is_overtime is False
        assert 0.0 <= progress <= 1.0


# --- End to end: the chip and the score a user actually gets -------------
#
# The parse tests above prove the unit. These prove the CHAIN, because the two
# ends being right is not the same as the ship working — the whole point of
# #3208 is that a wrong tuple deep in a helper surfaced as a wrong word on a
# card and 20 points of wrong ranking.

from datetime import datetime, timedelta, timezone  # noqa: E402

from app.utils.highlights import (  # noqa: E402
    WEIGHTS,
    compute_highlight,
    get_highlight_label,
)


def _live_soccer(period, **kw):
    """A live EPL match that started 61 minutes ago, as #3208 reported it."""
    now = datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)
    return compute_highlight(
        status="live",
        commence_time=now - timedelta(minutes=61),
        sport_key="soccer_epl",
        current_home_prob=0.58,
        current_away_prob=0.42,
        opening_home_prob=0.55,
        opening_away_prob=0.45,
        now=now,
        period=period,
        **kw,
    )


def test_live_soccer_at_61_minutes_gets_no_overtime_reason():
    result = _live_soccer("61'")
    assert "overtime" not in result.reasons
    assert result.primary_reason != "Overtime"


def test_live_soccer_at_61_minutes_is_not_labelled_overtime():
    """The chip on the card — the thing Alex would see and disbelieve."""
    result = _live_soccer("61'")
    assert get_highlight_label(result) != "Overtime"


def test_live_soccer_no_longer_collects_the_overtime_score_bonus():
    """The invisible half: +20 of fabricated urgency in the feed ranking.

    Compared against a genuine overtime string rather than a bare number, so
    the assertion is about the DIFFERENCE the defect made, not a pinned total
    that would rot the next time any weight is retuned.
    """
    ordinary = _live_soccer("61'")
    real_ot = _live_soccer("Extra Time")
    assert "overtime" in real_ot.reasons, "control arm must actually be overtime"
    expected_gap = WEIGHTS["live_late_game"] + WEIGHTS["live_overtime"]
    assert real_ot.score - ordinary.score == expected_gap - _late_bonus(ordinary)


def _late_bonus(result):
    """The legitimate late-game bonus a 61' match still earns."""
    progress = 61 / SOCCER_REGULATION_MINUTES
    return int(WEIGHTS["live_late_game"] * min((progress - 0.5) * 2, 1.0))


def test_live_soccer_still_earns_its_honest_late_game_bonus():
    """The fix removes a false claim; it must not flatten real late drama."""
    early = _live_soccer("10'")
    late = _live_soccer("85'")
    assert "overtime" not in late.reasons
    assert "late_game" in late.reasons, "85' is genuinely late in the game"
    assert "late_game" not in early.reasons, "10' is not"
    assert late.score > early.score


def test_a_real_overtime_game_still_says_overtime_end_to_end():
    """Guards the over-correction: NBA OT keeps its chip and its bonus."""
    now = datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)
    result = compute_highlight(
        status="live",
        commence_time=now - timedelta(hours=2),
        sport_key="basketball_nba",
        current_home_prob=0.51,
        current_away_prob=0.49,
        opening_home_prob=0.50,
        opening_away_prob=0.50,
        now=now,
        period="OT",
    )
    assert "overtime" in result.reasons
    assert get_highlight_label(result) == "Overtime"

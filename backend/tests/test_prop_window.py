"""#1588 — a window-bounded prop must not quote a probability after its window closes.

The reported case, verbatim from Alex's 2026-08-08 live dogfood:

    "Will there be a run scored in the first inning?: Athletics vs. Boston Red Sox"
    shows 52% "No", even though a 1st inning run already happened.

Every test here is written from the fail-safe direction stated in the module:
suppression happens ONLY when the window is provably over. The bulk of these
cases therefore assert that we KEEP showing markets — because wrongly hiding a
live market would be a new product regression, while wrongly showing one is the
bug we already have.
"""

import pytest

from app.utils.prop_window import (
    parse_period_number,
    prop_window,
    prop_window_closed,
)

MLB = "baseball_mlb"
NBA = "basketball_nba"

RFI = "Will there be a run scored in the first inning?: Athletics vs. Boston Red Sox"


class TestTheReportedCase:
    def test_first_inning_prop_is_suppressed_in_the_second(self):
        # The exact defect. A run scored in the 1st; the market must not quote.
        assert prop_window_closed(RFI, None, MLB, "Top 2", "live") is True

    def test_same_prop_still_shows_during_the_first(self):
        # Both directions (gotcha #43): the window is OPEN, so it must quote.
        assert prop_window_closed(RFI, None, MLB, "Top 1", "live") is False
        assert prop_window_closed(RFI, None, MLB, "Bottom 1", "live") is False

    def test_suppressed_for_the_rest_of_the_game(self):
        for period in ("Top 3", "Bottom 5", "Top 9", "Mid 7"):
            assert prop_window_closed(RFI, None, MLB, period, "live") is True

    def test_ticker_alone_is_enough_when_the_title_hides_the_window(self):
        # Kalshi titles routinely omit what the ticker encodes (gotcha #16).
        assert prop_window_closed("Athletics vs Red Sox", "KXMLBRFI-26AUG08", MLB, "Top 4", "live") is True


class TestFailsSafe:
    """Anything unproven keeps the market visible."""

    @pytest.mark.parametrize(
        "period",
        [None, "", "   ", "unknown", "Delayed", "Rain Delay", "Pre-Game", "garbage"],
    )
    def test_unparseable_period_keeps_the_market(self, period):
        assert prop_window_closed(RFI, None, MLB, period, "live") is False

    @pytest.mark.parametrize("status", [None, "", "scheduled", "completed", "closed", "postponed"])
    def test_a_status_string_alone_never_settles_a_window(self, status):
        # The status STRING is never the finished verdict, and that is
        # deliberate: "completed"/"closed" can sit on a row whose commence_time
        # is still in the future (gotcha #32 / #46), which must not render as
        # settled. Only the caller's `finished=` verdict
        # (`_event_is_really_finished`, which also checks the start time) closes
        # a window after full time — see TestAfterFullTime.
        assert prop_window_closed(RFI, None, MLB, "Top 9", status) is False

    def test_a_full_game_market_is_never_touched(self):
        for name in (
            "Athletics vs Boston Red Sox",
            "Total Runs Over/Under 8.5",
            "Boston Red Sox to win the World Series",
            "Aaron Judge Home Runs",
        ):
            assert prop_window(name, None, MLB) is None
            assert prop_window_closed(name, None, MLB, "Top 9", "live") is False

    def test_a_quarter_window_does_not_need_the_sport_key(self):
        # Written first as "unknown sport must never be judged", which was too
        # strict and simply wrong: a 1st-quarter prop during Q3 is over
        # whichever clock sport it is. Quarters are quarters. The sport key only
        # matters where the SCALES differ (innings vs quarters), which is the
        # next test.
        assert prop_window_closed("1st Quarter Total Points", None, None, "Q3", "live") is True

    def test_inning_window_is_not_judged_against_a_clock_period(self):
        # Comparing an inning window to a quarter number is comparing scales.
        assert prop_window_closed("First inning run", None, NBA, "Q3", "live") is False


class TestOtherWindows:
    def test_first_five_innings_closes_after_the_fifth(self):
        assert prop_window_closed("First 5 Innings Total", None, MLB, "Top 5", "live") is False
        assert prop_window_closed("First 5 Innings Total", None, MLB, "Top 6", "live") is True

    def test_first_half_closes_at_halftime(self):
        # Halftime IS the first half being over — the most common moment a
        # reader would notice a stale 1H market.
        assert prop_window_closed("1st Half Total Points", None, NBA, "Halftime", "live") is True
        assert prop_window_closed("1st Half Total Points", None, NBA, "Q1", "live") is False

    def test_first_quarter_closes_in_the_second(self):
        assert prop_window_closed("1st Quarter Spread", None, NBA, "Q1", "live") is False
        assert prop_window_closed("1st Quarter Spread", None, NBA, "Q2", "live") is True

    def test_third_quarter_window(self):
        assert prop_window_closed("3rd Quarter Total", None, NBA, "Q3", "live") is False
        assert prop_window_closed("3rd Quarter Total", None, NBA, "Q4", "live") is True

    def test_overtime_closes_every_regulation_window(self):
        assert prop_window_closed("1st Half Total Points", None, NBA, "OT", "live") is True
        assert prop_window_closed(RFI, None, MLB, "Extra Innings", "live") is True


class TestAfterFullTime:
    """The finished game — the half this rule originally refused to look at.

    Fable's sighting was a "2nd Quarter 99%" card rendered live-looking after
    the final. Reproduced on production 2026-09-10:
    `/api/events/15308050/game-markets`, seven hours after full time, served
    "Tampa Bay vs Atlanta: First 5 Spread" at 0.99 with no grade.
    """

    def test_the_sighting_a_quarter_market_after_the_final(self):
        assert prop_window_closed("2nd Quarter Winner", None, NBA, "Final", "completed", finished=True) is True

    def test_the_production_specimen_a_first_five_spread_after_full_time(self):
        assert prop_window_closed(
            "Tampa Bay vs Atlanta: First 5 Spread", None, MLB, None, "completed", finished=True
        ) is True

    @pytest.mark.parametrize("period", [None, "", "Final", "FT", "unknown", "garbage"])
    def test_no_period_is_needed_once_the_game_is_over(self, period):
        # The rule must not depend on the period after full time. Production
        # stores period=NULL on the finished rows this bug lives on, so a
        # version that insisted on parsing one would be inert exactly there.
        assert prop_window_closed(RFI, None, MLB, period, "completed", finished=True) is True

    def test_a_full_game_market_is_still_never_touched_after_the_final(self):
        # The fail-safe survives the new branch: finishing a game closes
        # WINDOWS, it does not suppress the whole board.
        for name in (
            "Athletics vs Boston Red Sox",
            "Total Runs Over/Under 8.5",
            "Boston Red Sox to win the World Series",
            "Aaron Judge Home Runs",
        ):
            assert prop_window_closed(name, None, MLB, "Final", "completed", finished=True) is False

    def test_an_unclassifiable_market_survives_the_final(self):
        assert prop_window_closed(None, None, MLB, "Final", "completed", finished=True) is False
        assert prop_window_closed("", None, None, "Final", "completed", finished=True) is False

    def test_the_default_is_unchanged_so_no_caller_settles_by_accident(self):
        # `finished` defaults False: a caller that does not pass the verdict
        # gets exactly the old live-only behaviour.
        assert prop_window_closed(RFI, None, MLB, "Final", "completed") is False

    def test_a_live_game_is_unaffected_by_the_new_branch(self):
        # Both directions (gotcha #43) with finished explicitly False.
        assert prop_window_closed(RFI, None, MLB, "Top 1", "live", finished=False) is False
        assert prop_window_closed(RFI, None, MLB, "Top 2", "live", finished=False) is True


class TestScalesMustAgree:
    """A number is only comparable with a window on the same scale.

    Every case here asserts we KEEP showing the market: this guard exists
    entirely to stop the widened vocabulary becoming over-eager.
    """

    def test_a_second_half_market_survives_the_third_quarter(self):
        # The regression the scale check exists for. Q3 parses to 3, a 2nd-half
        # window closes after 2, and comparing them gives 3 > 2 — but Q3 is
        # INSIDE the second half, so the market is still live.
        assert prop_window_closed("2nd Half Total", None, NBA, "Q3", "live") is False
        assert prop_window_closed("2nd Half Total", None, NBA, "Q4", "live") is False

    def test_a_first_half_market_survives_the_first_quarter(self):
        assert prop_window_closed("1st Half Total", None, NBA, "Q1", "live") is False
        assert prop_window_closed("1st Half Total", None, NBA, "Q2", "live") is False

    def test_a_quarter_market_is_not_judged_against_a_half(self):
        assert prop_window_closed("1st Quarter Total", None, NBA, "2nd Half", "live") is False

    def test_an_inning_window_is_not_judged_against_a_clock_period(self):
        assert prop_window_closed("First inning run", None, NBA, "Q3", "live") is False

    def test_overtime_still_closes_every_scale(self):
        # The one value that compares with any window.
        assert prop_window_closed("2nd Half Total", None, NBA, "OT", "live") is True
        assert prop_window_closed("1st Quarter Total", None, NBA, "OT", "live") is True


class TestTheMeasuredVocabulary:
    """Names taken from the production census of 2026-09-10."""

    @pytest.mark.parametrize(
        "name,closes_after",
        [
            ("Tampa Bay vs Atlanta: First 5 Spread", 5),
            ("Tampa Bay vs Atlanta: First 5 Innings Total", 5),
            ("Cincinnati vs Los Angeles D: First 3 Innings", 3),
            ("Cincinnati vs Los Angeles D: First 7 Innings", 7),
            ("Tampa Bay vs Atlanta: 7th Inning Winner", 7),
            ("Tampa Bay vs Atlanta: 2nd Inning Total", 2),
            ("Tampa Bay vs Atlanta: 9th Inning Winner", 9),
        ],
    )
    def test_baseball_windows_are_recognised(self, name, closes_after):
        assert prop_window(name, None, MLB) == ("inning", closes_after)

    def test_first_five_is_not_read_as_the_fifth_inning_alone(self):
        # Ordering guard: the explicit windows run before the Nth-inning rule.
        assert prop_window("First 5 Innings Total", None, MLB) == ("inning", 5)
        assert prop_window("First 3 Innings", None, MLB) == ("inning", 3)

    @pytest.mark.parametrize(
        "name,unit,closes_after",
        [
            ("4th Quarter Winner", "quarter", 4),
            ("2nd Half O/U 1.5", "half", 2),
            ("Second Half Winner", "half", 2),
            ("Both Teams to Score in Second Half", "half", 2),
        ],
    )
    def test_clock_windows_are_recognised(self, name, unit, closes_after):
        assert prop_window(name, None, NBA) == (unit, closes_after)

    def test_a_fulltime_combined_market_is_never_a_window(self):
        # "1st Half / Fulltime Result" names a half but runs to the whistle.
        # Classifying it would suppress a full-game market at halftime.
        assert prop_window("1st Half / Fulltime Result", None, None) is None
        assert prop_window_closed("1st Half / Fulltime Result", None, None, "Halftime", "live") is False
        assert (
            prop_window_closed("1st Half / Fulltime Result", None, None, "Final", "completed", finished=True)
            is False
        )

    @pytest.mark.parametrize(
        "name,sport",
        [
            ("Tampa Bay vs Atlanta: First 5 Spread", MLB),
            ("Tampa Bay vs Atlanta: 7th Inning Winner", MLB),
            ("Tampa Bay vs Atlanta: 7th Inning Winner", None),  # "Inning" carries it alone
            ("4th Quarter Winner", None),
            ("2nd Half O/U 1.5", None),
        ],
    )
    def test_the_finished_game_closes_the_newly_recognised_windows(self, name, sport):
        assert prop_window_closed(name, None, sport, None, "completed", finished=True) is True

    @pytest.mark.parametrize(
        "name,closes_after",
        [
            ("1st 5 Innings O/U 6.5", 5),
            ("1st 5 Innings Spread -1.5", 5),
            ("1st 3 Innings Total", 3),
            ("1st 7 Innings Winner", 7),
        ],
    )
    def test_the_numeral_spelling_of_the_first_n_innings(self, name, closes_after):
        """`1st 5` is the same window as `First 5`, and it is Polymarket's.

        Only "first" was accepted, while the first-INNING pattern took both
        spellings. Censused on production 2026-09-10 over outcome names:
        `%first 5%` 28,512, `%1st 5%` 2,224, `%1st 3%` 4 — so this is a real
        population, and every sampled row is Polymarket.
        """
        assert prop_window(name, None, MLB) == ("inning", closes_after)

    def test_1st_5_innings_is_not_read_as_the_first_inning(self):
        """The ordering that makes the numeral form safe to add.

        `_NTH_INNING_RE` would read the leading "1st" and close the market after
        inning 1 — four innings early, suppressing a market that is still live.
        The explicit first-five pattern runs first, exactly as it does for
        "First 5 Innings".
        """
        assert prop_window("1st 5 Innings Spread -1.5", None, MLB) == ("inning", 5)
        assert (
            prop_window_closed("1st 5 Innings Spread -1.5", None, MLB, "Top 3", "live")
            is False
        ), "the first five innings are still being played"

    def test_the_outcome_name_identifies_the_window_when_the_title_does_not(self):
        """CERT-2486's Polymarket shape: a generic matchup title.

        The window appears ONLY in the outcome, so a rule reading the title
        alone leaves the row quoting after the final.
        """
        title = "Tampa Bay Rays vs. Atlanta Braves"
        assert prop_window(title, None, MLB) is None, "the title names no window"
        assert prop_window(title, None, MLB, "1st 5 Innings Spread -1.5") == ("inning", 5)
        assert (
            prop_window_closed(
                title, None, MLB, None, "completed", finished=True,
                outcome="1st 5 Innings Spread -1.5",
            )
            is True
        )

    def test_the_ticker_identifies_the_window_when_the_title_does_not(self):
        """CERT-2486's Kalshi shape: the `KXMLBRFI` prefix is the only signal."""
        assert prop_window("Rays at Braves", None, MLB) is None
        assert prop_window("Rays at Braves", "KXMLBRFI-26SEP09ATLTB-T0.5", MLB) == (
            "inning",
            1,
        )

    def test_a_fulltime_title_vetoes_its_own_outcomes(self):
        """The over-suppression trap that reading outcomes opens up.

        "1st Half / Fulltime Result" (76 rows) runs to the whistle, and its
        OUTCOMES name a half. Reading outcome text per-string would classify it
        as a first-half window and suppress a full-game market at halftime — the
        exact regression the veto exists to prevent. The title's veto therefore
        applies to the whole row, before any outcome is read.
        """
        assert prop_window("1st Half / Fulltime Result", None, None, "1st Half: Home") is None
        assert (
            prop_window_closed(
                "1st Half / Fulltime Result", None, None, None, "completed",
                finished=True, outcome="1st Half: Home",
            )
            is False
        )

    def test_an_outcome_naming_fulltime_is_not_a_window_either(self):
        assert prop_window("Rays at Braves", None, MLB, "1st Half / Fulltime Result") is None

    def test_the_outcome_is_only_consulted_when_the_title_says_nothing(self):
        """The title wins where it speaks, so an outcome cannot widen a window."""
        assert prop_window(
            "Tampa Bay vs Atlanta: 7th Inning Winner", None, MLB, "1st 5 Innings"
        ) == ("inning", 7)

    def test_a_bare_first_five_needs_the_sport_and_that_is_deliberate(self):
        # "First 5 Spread" with no sport key and no "innings" in the title could
        # belong to anything, so it stays visible. The call site supplies
        # "baseball_mlb" for MLB rows, which is how the real specimen is caught;
        # a row whose league is missing keeps its card, which is the fail-safe
        # direction.
        assert prop_window("Tampa Bay vs Atlanta: First 5 Spread", None, None) is None
        assert prop_window("Tampa Bay vs Atlanta: First 5 Spread", None, MLB) == ("inning", 5)


class TestPeriodParsing:
    @pytest.mark.parametrize(
        "period,expected",
        [
            ("Top 1", 1),
            ("Bottom 1", 1),
            ("Bot 3", 3),
            ("Mid 7", 7),
            ("End 8", 8),
            ("Inning 5 (Top)", 5),
            ("Bottom of the 3rd", 3),
            ("T5", 5),
            ("9", 9),
            ("Top 12", 12),
        ],
    )
    def test_baseball_innings(self, period, expected):
        assert parse_period_number(period, MLB) == expected

    @pytest.mark.parametrize("period", [None, "", "  ", "Warmup", "Postponed"])
    def test_unknown_baseball_periods_are_none_not_zero(self, period):
        # `None` must never be coerced to a falsy period number — that would
        # read as "before inning 1" and suppress everything.
        assert parse_period_number(period, MLB) is None

    def test_absurd_inning_is_rejected(self):
        assert parse_period_number("Inning 47", MLB) is None

    @pytest.mark.parametrize(
        "period,expected",
        [("Q1", 1), ("Q4", 4), ("3rd Quarter", 3), ("2H", 2), ("1st Half", 1), ("Halftime", 2)],
    )
    def test_clock_sports(self, period, expected):
        assert parse_period_number(period, NBA) == expected

    def test_overtime_is_past_everything(self):
        assert parse_period_number("OT", NBA) == 99
        assert parse_period_number("Overtime", NBA) == 99


class TestWindowClassification:
    @pytest.mark.parametrize(
        "name",
        [
            "Will there be a run scored in the first inning?",
            "Run in the 1st inning",
            "NRFI",
            "YRFI - Athletics vs Red Sox",
        ],
    )
    def test_first_inning_variants(self, name):
        assert prop_window(name, None, MLB) == ("inning", 1)

    def test_innings_wording_implies_baseball_without_a_sport_key(self):
        # A title naming innings is baseball even if the sport key is missing.
        assert prop_window("Run in the first inning", None, None) == ("inning", 1)

    def test_no_window_returns_none(self):
        assert prop_window("Moneyline", None, MLB) is None
        assert prop_window("", None, MLB) is None
        assert prop_window(None, None, MLB) is None

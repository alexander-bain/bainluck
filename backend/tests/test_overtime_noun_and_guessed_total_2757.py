"""Guards for #2757 — a baseball game badged "Overtime", for two reasons.

The issue was filed about a **noun**: `/sports` showed a live MLB game in the
`Top 12th` wearing the capsule "Overtime". Baseball has extra innings. One
hardcoded string served every sport at both label sites.

Measuring it first (production, 2026-09-12, the shipped predicate run over all
394 distinct non-`Final` `(sport_key, period)` pairs) found the noun was the
small half. Of the 282 rows `parse_game_progress` called beyond-regulation:

| sport | in the map? | rows | what the reader saw |
|---|---|---|---|
| `baseball_mlb_preseason` | **no** → guessed 4 | **188** | `Top 5th` badged Overtime |
| `baseball_ncaa` | **no** → guessed 4 | **91** | `Top 5th` badged Overtime |
| `baseball_mlb` | yes → 9 | 3 | genuine extra innings, wrong noun |

So **279 rows of a false claim against 3 of a wrong word**. The reported 12th
inning was the rare CORRECT firing; the common case was a college or preseason
game barely halfway through, because `SPORT_TOTAL_PERIODS.get(sport_key, 4)`
silently answered "4 innings" for a nine-inning sport.

Three things are guarded here, in descending order of how much they hurt:

1. **The guessed denominator** (`TestAGuessedTotalCannotAssertOvertime`) — the
   mechanism. A sport absent from the map may have its progress estimated and
   may never be called beyond regulation. This is what makes the NEXT league we
   ingest safe before anyone remembers to add it.
2. **The measured rows** (`TestTheMeasuredBaseballRows`) — the two names, and
   the reach test that does not care which mechanism saves them.
3. **The noun** (`TestTheNoun`) — baseball "Extra innings", soccer "Extra time",
   everything else "Overtime", at BOTH label sites.

The tennis hypothesis the issue raised is REFUTED and deliberately not guarded
as a live defect: tennis carries no `period` value at all on production (0 rows),
so the `default 4` path is unreachable for it and a five-set match cannot be
badged. `test_variable_round_sport_is_never_beyond_regulation` pins the
mechanism that would protect it anyway, if that ever changes.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.highlights import (
    DEFAULT_OVERTIME_NOUN,
    SPORT_TOTAL_PERIODS,
    EventFlags,
    HighlightResult,
    compute_highlight,
    get_highlight_label,
    overtime_noun,
    parse_game_progress,
)
from app.utils.sport_keys import SPORT_LEAGUE_MAP


# A sport key we do not ingest, so the map cannot contain it. The point of the
# invariant is that this is SAFE, not that this particular string is special.
UNMAPPED_SPORT = "baseball_kbo"


def _live(sport_key, period, **kw):
    """A live game two hours old, scored through the real entry point.

    Deliberately `compute_highlight` rather than a hand-built `HighlightResult`:
    the noun is carried on `EventFlags.sport_key`, which only this function
    writes, so a hand-built fixture would test the fallback and report success.
    """
    now = datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc)
    return compute_highlight(
        status="live",
        commence_time=now - timedelta(hours=2),
        sport_key=sport_key,
        current_home_prob=0.55,
        current_away_prob=0.45,
        opening_home_prob=0.52,
        opening_away_prob=0.48,
        now=now,
        period=period,
        **kw,
    )


# --- 1. The mechanism ----------------------------------------------------

class TestAGuessedTotalCannotAssertOvertime:
    """A denominator we invented may estimate progress, never assert overtime."""

    @pytest.mark.parametrize("period", ["Top 5th", "Bottom 5th", "Top 8th", "9th"])
    def test_unmapped_sport_past_the_guess_is_not_overtime(self, period):
        _, is_overtime = parse_game_progress(period, UNMAPPED_SPORT)
        assert is_overtime is False, (
            f"{period!r} in {UNMAPPED_SPORT} (absent from SPORT_TOTAL_PERIODS) "
            "was called beyond regulation off a guessed 4-period total — the "
            "mechanism that badged 279 production rows 'Overtime'"
        )

    def test_the_same_period_IS_overtime_once_the_sport_is_mapped(self):
        """The guard is about MAP MEMBERSHIP, not about the number 10.

        Without this arm the test above passes on a function that never returns
        True at all, which is the over-correction #3208's fix had to avoid.
        """
        assert "baseball_mlb" in SPORT_TOTAL_PERIODS
        assert UNMAPPED_SPORT not in SPORT_TOTAL_PERIODS
        _, mapped = parse_game_progress("Bottom 10th", "baseball_mlb")
        _, unmapped = parse_game_progress("Bottom 10th", UNMAPPED_SPORT)
        assert mapped is True, "a real 10th inning in MLB is extra innings"
        assert unmapped is False

    def test_unmapped_sport_past_the_guess_reports_dont_know_not_finished(self):
        """The invisible half: progress feeds the late-game ranking bonus.

        Answering 1.0 would report a half-played game as finished and hand it
        the full bonus — a false claim swapped for a quieter one.
        """
        progress, _ = parse_game_progress("Top 5th", UNMAPPED_SPORT)
        assert progress == 0.5, (
            "a period past a GUESSED total means the guess is too small, not "
            f"that the game is over; got {progress}"
        )

    def test_variable_round_sport_is_never_beyond_regulation(self):
        """Tennis/golf/MMA have no regulation period count to exceed.

        Refuted as a live defect (tennis serves no `period` at all), so this
        guards the mechanism, not a reproduction.
        """
        for sport_key in ("tennis_atp", "golf_pga", "mma_ufc"):
            assert sport_key not in SPORT_TOTAL_PERIODS
            _, is_overtime = parse_game_progress("5th", sport_key)
            assert is_overtime is False, f"{sport_key} cannot be past regulation"

    def test_a_bare_number_still_concludes_nothing(self):
        """#3208's rule, unchanged by this ship — the arm below the new one."""
        progress, is_overtime = parse_game_progress("31", "basketball_nba")
        assert is_overtime is False
        assert progress == 0.5


# --- 2. The measured rows ------------------------------------------------

class TestTheMeasuredBaseballRows:
    """The 279 production rows, by name and by reach."""

    @pytest.mark.parametrize(
        "sport_key", ["baseball_mlb_preseason", "baseball_ncaa"]
    )
    @pytest.mark.parametrize("period", ["Top 5th", "Bottom 5th", "Top 6th", "Top 8th"])
    def test_the_reported_rows_are_no_longer_overtime(self, sport_key, period):
        progress, is_overtime = parse_game_progress(period, sport_key)
        assert is_overtime is False, (
            f"{sport_key} {period!r} — one of the 279 measured rows"
        )
        assert progress < 1.0, "a 5th-to-8th inning is not a finished game"

    @pytest.mark.parametrize(
        "sport_key", ["baseball_mlb", "baseball_mlb_preseason", "baseball_ncaa"]
    )
    def test_real_extra_innings_still_register(self, sport_key):
        """The over-correction guard: the 3 genuine rows keep their badge."""
        _, is_overtime = parse_game_progress("Bottom 10th", sport_key)
        assert is_overtime is True

    def test_the_fifth_inning_of_nine_reads_as_the_middle(self):
        progress, _ = parse_game_progress("Top 5th", "baseball_ncaa")
        assert progress == pytest.approx(4.5 / 9)

    @pytest.mark.parametrize(
        "sport_key", sorted(k for k in SPORT_LEAGUE_MAP if k.startswith("baseball_"))
    )
    def test_no_ingested_baseball_league_badges_a_fifth_inning(self, sport_key):
        """Reach, not mechanism — this does not care HOW the row is saved.

        Passes whether the league is mapped to 9 or protected by the guessed-
        total invariant, so it keeps holding if either half is refactored. It
        fails on the shipped code before this change for two of the three keys.
        """
        _, is_overtime = parse_game_progress("Top 5th", sport_key)
        assert is_overtime is False

    def test_every_baseball_league_we_map_is_given_nine_innings(self):
        wrong = {
            k: v
            for k, v in SPORT_TOTAL_PERIODS.items()
            if k.startswith("baseball_") and v != 9
        }
        assert not wrong, f"baseball is nine innings; these disagree: {wrong}"


# --- 3. The noun ---------------------------------------------------------

class TestTheNoun:
    """What the reader actually sees, at both label sites."""

    @pytest.mark.parametrize(
        "sport_key,expected",
        [
            ("baseball_mlb", "Extra innings"),
            ("baseball_ncaa", "Extra innings"),
            ("baseball_mlb_preseason", "Extra innings"),
            ("soccer_epl", "Extra time"),
            ("soccer_usa_mls", "Extra time"),
            ("americanfootball_nfl", "Overtime"),
            ("basketball_nba", "Overtime"),
            ("icehockey_nhl", "Overtime"),
        ],
    )
    def test_the_helper_names_each_sport_in_its_own_words(self, sport_key, expected):
        assert overtime_noun(sport_key) == expected

    def test_the_reported_card_reads_extra_innings_end_to_end(self):
        """#2757 head-on: the Top 12th MLB card, through the real entry point."""
        result = _live("baseball_mlb", "Top 12th")
        assert "overtime" in result.reasons, "detection was never the problem"
        assert get_highlight_label(result) == "Extra innings"
        assert result.primary_reason == "Extra innings"

    def test_soccer_extra_time_reads_extra_time_at_both_sites(self):
        result = _live("soccer_epl", "Extra Time")
        assert "overtime" in result.reasons
        assert get_highlight_label(result) == "Extra time"
        assert result.primary_reason == "Extra time"

    def test_the_sports_that_coined_the_word_keep_it(self):
        """Over-correction guard — this is the majority of live overtime rows."""
        for sport_key in ("americanfootball_nfl", "basketball_nba", "icehockey_nhl"):
            result = _live(sport_key, "OT")
            assert "overtime" in result.reasons
            assert get_highlight_label(result) == "Overtime"
            assert result.primary_reason == "Overtime"

    def test_no_sport_is_told_it_is_in_overtime_in_another_sports_words(self):
        """Sweep every mapped sport rather than the three spelled out above."""
        for sport_key in SPORT_TOTAL_PERIODS:
            noun = overtime_noun(sport_key)
            if sport_key.startswith("baseball_"):
                assert noun == "Extra innings", sport_key
            elif sport_key.startswith("soccer_"):
                assert noun == "Extra time", sport_key
            else:
                assert noun == DEFAULT_OVERTIME_NOUN, sport_key


# --- 4. The wiring the noun depends on -----------------------------------

class TestTheSportSurvivesToTheLabelSite:
    """`get_highlight_label(result)` takes no sport argument; it reads a flag."""

    def test_compute_highlight_records_the_sport(self):
        assert _live("baseball_mlb", "Top 12th").flags.sport_key == "baseball_mlb"

    def test_a_result_with_no_sport_falls_back_to_the_old_string(self):
        """Back-compat: hand-built fixtures elsewhere must not change meaning.

        Every such fixture said "Overtime" before this ship, so an unset
        `sport_key` has to keep saying it.
        """
        result = HighlightResult(
            reasons=["overtime"], flags=EventFlags(is_live=True)
        )
        assert result.flags.sport_key is None
        assert get_highlight_label(result) == "Overtime"

    def test_the_machine_key_is_untouched_for_every_sport(self):
        """Notice 33's distinction: the reason CODE is not a reader-facing word.

        `routes/feed.py` and the scoring table match on `"overtime"`; renaming
        it to match the label would be an API change with no reader benefit —
        and would silently drop the +score for baseball.
        """
        for sport_key, period in (
            ("baseball_mlb", "Top 12th"),
            ("soccer_epl", "Extra Time"),
            ("americanfootball_nfl", "OT"),
        ):
            assert "overtime" in _live(sport_key, period).reasons, sport_key

    def test_baseball_extra_innings_still_earns_the_overtime_score(self):
        """The noun change must not cost the ranking bonus it rides with."""
        extra = _live("baseball_mlb", "Bottom 10th")
        ordinary = _live("baseball_mlb", "Top 3rd")
        assert "overtime" in extra.reasons
        assert "overtime" not in ordinary.reasons
        assert extra.score > ordinary.score

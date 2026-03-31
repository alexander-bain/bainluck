"""Tests for market label normalization, categorization, and merge grouping.

Scored against a hand-labeled truth set from multiple sports:
- NBA: Celtics/Thunder (event 11962921)
- NHL: Blue Jackets/Bruins (event 12080386)
- NCAA: Duke/UConn (event 12081341)
- MLB: Dodgers/Diamondbacks (event 12080424)

Quality metrics:
- Label Accuracy: % of markets where normalize_market_label() matches expected
- Category Accuracy: % where classify_market_category() matches expected
- Merge Group Accuracy: % where get_merge_group() matches expected
- Wrong Sport Detection: recall and precision of is_wrong_sport_leak()
"""

import json
import pathlib

import pytest

from app.utils.market_label_normalization import (
    normalize_market_label,
    classify_market_category,
    get_merge_group,
    is_wrong_sport_leak,
    compute_playoff_stage,
)


TRUTH_SET_PATH = pathlib.Path(__file__).parent / "fixtures" / "related_futures_truth_set.json"


@pytest.fixture(scope="module")
def truth_set():
    with open(TRUTH_SET_PATH) as f:
        data = json.load(f)
    # Filter out comment entries
    return [m for m in data["markets"] if "_comment" not in m]


# ── Individual function tests ─────────────────────────────────────────────


class TestNormalizeMarketLabel:
    """Test label normalization on known inputs."""

    @pytest.mark.parametrize("raw,expected", [
        # NBA
        ("Pro Basketball Champion", "NBA Champion"),
        ("2026 NBA Champion", "NBA Champion"),
        ("NBA Championship Winner", "NBA Champion"),
        ("Pro Basketball All-Defensive 2nd Team Selections", "All-Defensive 2nd Team"),
        ("NBA Points Per Game Leader", "PPG Leader"),
        ("MVP Winner", "MVP"),
        ("NBA MVP ", "MVP"),
        ("Sixth Man of the Year Winner", "6MOY"),
        ("Zion Williamson's Next Team", "Zion Williamson Trade Destination"),
        ("Who will be on the cover of NBA 2K27?", "NBA 2K Cover"),
        ("Oklahoma City at Boston: Three Pointers", "Oklahoma City at Boston: Three Pointers"),
        ("Which teams will make the NBA Playoffs?", "Make NBA Playoffs"),
        ("Boston pro basketball wins this season?", "Boston Win Total"),
        ("Pro Basketball Eastern Conference #1 Seed", "Eastern Conference #1 Seed"),
        ("Teams to Make the Eastern Conference Play-In Tournament", "Eastern Conference Play-In"),
        ("How many games will Oklahoma City win in a row this season?", "Oklahoma City Win Streak"),
        ("NBA Best Record", "Best Record"),
        ("Pro Basketball Best Regular Season Record", "Best Record"),
        ("NBA Win Totals: Over or Under?", "Win Total"),
        ("Eastern Conference Finals MVP Winner", "Eastern Conf Finals MVP"),
        ("All-Pro Basketball 1st Team Selections", "All-NBA 1st Team"),
        ("NCAAB Championship Winner", "NCAAB Champion"),
        # NHL
        ("NHL Championship Winner", "Stanley Cup Champion"),
        ("Stanley Cup\u00ae Champion?", "Stanley Cup Champion"),
        ("Stanley Cup\u00ae Playoff Qualifiers", "Make NHL Playoffs"),
        ("Which teams will make the NHL Playoffs?", "Make NHL Playoffs"),
        ("NHL Hart Memorial Trophy Winner", "Hart Trophy"),
        ("NHL Hart Memorial Trophy", "Hart Trophy"),
        ("NHL James Norris Memorial Trophy Winner", "Norris Trophy"),
        ("NHL Vezina Trophy Winner", "Vezina Trophy"),
        ("NHL Calder Memorial Trophy Winner", "Calder Trophy"),
        ("NHL Art Ross Trophy Winner", "Art Ross Trophy"),
        ("NHL Maurice 'Rocket' Richard Trophy Winner", "Rocket Richard Trophy"),
        # MLB
        ("MLB World Series Winner", "World Series Champion"),
        ("Pro Baseball Champion", "World Series Champion"),
        ("American League Champion", "AL Champion"),
        ("National League Champion", "NL Champion"),
        ("Pro Baseball Playoff Qualifiers", "Make MLB Playoffs"),
        ("Pro Baseball Best Record", "Best Record"),
        ("Pro Baseball Worst Record", "Worst Record"),
        ("Los Angeles D pro baseball wins this season?", "Los Angeles D Win Total"),
        ("Pro Baseball Championship Series Matchup", "World Series Matchup"),
        ("Longest regular season winning streak", "Longest winning Streak"),
        ("Ketel Marte's next team?", "Ketel Marte Trade Destination"),
        # NCAA
        ("NCAA Tournament: Team to make Semifinals", "Make Final Four"),
        ("NCAA Tournament: Most Outstanding Player ", "Most Outstanding Player"),
        ("College Basketball Naismith Player of the Year", "Naismith Player of the Year"),
        ("NCAAM: Naismith Defensive Player of the Year", "Naismith DPOY"),
        ("Pro Basketball #1 Overall Pick", "NBA Draft #1 Pick"),
        ("Pro Basketball Players Drafted Top 10", "NBA Draft Top 10"),
        ("Men's 1 Seed", "#1 Seed"),
        ("Team to Score the Most Points in the Semifinals", "Most Points in Semifinals"),
    ])
    def test_known_labels(self, raw, expected):
        assert normalize_market_label(raw) == expected


class TestClassifyMarketCategory:

    @pytest.mark.parametrize("label,expected_cat", [
        # NBA
        ("NBA Champion", "playoff_path"),
        ("Eastern Conference Champion", "playoff_path"),
        ("Make NBA Playoffs", "playoff_path"),
        ("Eastern Conference #1 Seed", "playoff_path"),
        ("Eastern Conference Play-In", "playoff_path"),
        ("Eastern Conference Finals Matchup", "conference"),
        ("Eastern Conf Finals MVP", "conference"),
        ("MVP", "award"),
        ("Finals MVP", "award"),
        ("DPOY", "award"),
        ("6MOY", "award"),
        ("MIP", "award"),
        ("ROY", "award"),
        ("Clutch Player", "award"),
        ("All-NBA 1st Team", "award"),
        ("All-Defensive 2nd Team", "award"),
        ("PPG Leader", "season_stat"),
        ("Best Record", "season_stat"),
        ("Win Total", "season_stat"),
        ("Atlantic Division Winner", "season_stat"),
        ("Oklahoma City at Boston: Three Pointers", "game_prop"),
        ("Zion Williamson Trade Destination", "trade"),
        ("NBA 2K Cover", "novelty"),
        ("Men's Round of 8", "ncaa"),
        # NHL
        ("Stanley Cup Champion", "playoff_path"),
        ("Make NHL Playoffs", "playoff_path"),
        ("Hart Trophy", "award"),
        ("Norris Trophy", "award"),
        ("Vezina Trophy", "award"),
        ("Art Ross Trophy", "award"),
        ("Rocket Richard Trophy", "award"),
        ("Presidents' Trophy", "season_stat"),
        # MLB
        ("World Series Champion", "playoff_path"),
        ("AL Champion", "playoff_path"),
        ("NL Champion", "playoff_path"),
        ("Make MLB Playoffs", "playoff_path"),
        ("World Series Matchup", "conference"),
        ("AL West Winner", "season_stat"),
        ("NL West Winner", "season_stat"),
        ("Longest winning Streak", "season_stat"),
        # NCAA
        ("NCAA Champion", "playoff_path"),
        ("NCAAB Champion", "playoff_path"),
        ("Make Final Four", "playoff_path"),
        ("Make Championship Game", "playoff_path"),
        ("Make Sweet Sixteen", "playoff_path"),
        ("#1 Seed", "playoff_path"),
        ("Most Outstanding Player", "award"),
        ("Naismith Player of the Year", "award"),
        ("Naismith DPOY", "award"),
        ("NBA Draft #1 Pick", "award"),
        ("NBA Draft Top 10", "award"),
        ("Most Points in Semifinals", "novelty"),
        ("UConn vs Duke: First Half Winner", "game_prop"),
    ])
    def test_known_categories(self, label, expected_cat):
        assert classify_market_category(label) == expected_cat


class TestGetMergeGroup:

    @pytest.mark.parametrize("label,expected_group", [
        # NBA
        ("NBA Champion", "nba_champion"),
        ("Eastern Conference Champion", "eastern_conf_champion"),
        ("Western Conference Champion", "western_conf_champion"),
        ("Make NBA Playoffs", "make_playoffs"),
        ("MVP", "mvp"),
        ("Finals MVP", "finals_mvp"),
        ("DPOY", "dpoy"),
        ("6MOY", "6moy"),
        ("MIP", "mip"),
        ("PPG Leader", "ppg_leader"),
        ("Best Record", "best_record"),
        ("Atlantic Division Winner", "atlantic_division"),
        ("Eastern Conference Finals Matchup", "eastern_conf_finals_matchup"),
        ("NBA Finals Matchup", "nba_finals_matchup"),
        ("Oklahoma City at Boston: Three Pointers", None),
        ("Zion Williamson Trade Destination", "zion_williamson_trade"),
        ("Jimmy Butler Trade Destination", "jimmy_butler_trade"),
        ("NBA 2K Cover", None),
        # NFL
        ("Super Bowl Champion", "nfl_champion"),
        ("AFC Champion", "afc_champion"),
        ("Super Bowl Matchup", "super_bowl_matchup"),
        ("Make NFL Playoffs", "make_nfl_playoffs"),
        # NHL
        ("Stanley Cup Champion", "stanley_cup_champion"),
        ("Stanley Cup Matchup", "stanley_cup_matchup"),
        ("Make NHL Playoffs", "make_nhl_playoffs"),
        ("Hart Trophy", "hart_trophy"),
        ("Norris Trophy", "norris_trophy"),
        ("Vezina Trophy", "vezina_trophy"),
        ("Art Ross Trophy", "art_ross_trophy"),
        ("Rocket Richard Trophy", "rocket_richard_trophy"),
        ("Presidents' Trophy", "presidents_trophy"),
        # MLB
        ("World Series Champion", "world_series_champion"),
        ("AL Champion", "al_champion"),
        ("NL Champion", "nl_champion"),
        ("Make MLB Playoffs", "make_mlb_playoffs"),
        ("AL West Winner", "al_west"),
        # NCAA
        ("NCAA Champion", "ncaa_champion"),
        ("NCAAB Champion", "ncaa_champion"),
        ("Make Final Four", "make_final_four"),
        ("Make Championship Game", "make_championship_game"),
        ("Make Sweet Sixteen", "make_sweet_sixteen"),
        ("Most Outstanding Player", "most_outstanding_player"),
        ("Naismith Player of the Year", "naismith_poty"),
        ("NBA Draft #1 Pick", "nba_draft_1"),
    ])
    def test_known_merge_groups(self, label, expected_group):
        assert get_merge_group(label) == expected_group


class TestIsWrongSportLeak:

    # NBA games
    def test_ncaa_round_for_nba_game(self):
        assert is_wrong_sport_leak(
            "Men's Round of 8 Qualifiers", "Boston College", "basketball_nba"
        ) is True

    def test_ncaab_championship_for_nba_game(self):
        assert is_wrong_sport_leak(
            "NCAAB Championship Winner", "Boston College Eagles", "basketball_nba"
        ) is True

    def test_nhl_bruins_for_nba_game(self):
        assert is_wrong_sport_leak(
            "Eastern Conference Finals Winner?", "Boston Bruins", "basketball_nba"
        ) is True

    def test_nba_champion_for_nba_game(self):
        assert is_wrong_sport_leak(
            "NBA Championship Winner", "Boston Celtics", "basketball_nba"
        ) is False

    def test_ncaa_round_for_ncaa_game(self):
        assert is_wrong_sport_leak(
            "Men's Round of 8 Qualifiers", "Boston College", "basketball_ncaab"
        ) is False

    def test_trade_market_not_wrong_sport(self):
        assert is_wrong_sport_leak(
            "LeBron James's Next Team", "Boston", "basketball_nba"
        ) is False

    # NHL games
    def test_ahl_for_nhl_game(self):
        assert is_wrong_sport_leak(
            "AHL: Springfield Thunderbirds vs. Providence Bruins",
            "Springfield Thunderbirds", "icehockey_nhl"
        ) is True

    def test_college_hockey_for_nhl_game(self):
        assert is_wrong_sport_leak(
            "College Hockey National Championship Winner",
            "Boston University", "icehockey_nhl"
        ) is True

    def test_stanley_cup_for_nhl_game(self):
        assert is_wrong_sport_leak(
            "Stanley Cup\u00ae Champion?", "Columbus Blue Jackets", "icehockey_nhl"
        ) is False

    # MLB games
    def test_college_baseball_for_mlb_game(self):
        assert is_wrong_sport_leak(
            "College Baseball D1 Champion", "Arizona Wildcats", "baseball_mlb"
        ) is True

    def test_world_series_for_mlb_game(self):
        assert is_wrong_sport_leak(
            "MLB World Series Winner", "Los Angeles Dodgers", "baseball_mlb"
        ) is False

    # NCAA games
    def test_nba_conf_finals_for_ncaa_game(self):
        assert is_wrong_sport_leak(
            "Eastern Conference Finals Winner?", "Boston Celtics", "basketball_ncaab"
        ) is True

    def test_ncaa_tournament_for_ncaa_game(self):
        assert is_wrong_sport_leak(
            "NCAA Tournament: Team to make Semifinals", "Duke", "basketball_ncaab"
        ) is False


# ── Playoff stage classification ──────────────────────────────────────────


class TestComputePlayoffStage:
    """Test the single-source-of-truth playoff stage classification.

    These encode every edge case that previously caused bugs in the
    frontend/iOS classifyPlayoffStage() functions.
    """

    @pytest.mark.parametrize("label,expected_type,expected_display,expected_order", [
        # Championship markets
        ("NBA Champion", "championship", "Championship", 5),
        ("Stanley Cup Champion", "championship", "Championship", 5),
        ("World Series Champion", "championship", "Championship", 5),
        ("Super Bowl Champion", "championship", "Championship", 5),
        ("NCAAB Champion", "championship", "Championship", 5),

        # Conference markets — THE BUG: these must NOT match championship
        ("Eastern Conference Champion", "conference", "Eastern Champ", 4),
        ("Western Conference Champion", "conference", "Western Champ", 4),
        ("AFC Champion", "conference", "AFC Champ", 4),
        ("NFC Champion", "conference", "NFC Champ", 4),
        ("AL Champion", "conference", "AL Champ", 4),
        ("NL Champion", "conference", "NL Champ", 4),
        ("Eastern Conference Finals Matchup", "conference", "Eastern Champ", 4),
        ("Western Conf Finals MVP", "conference", "Western Champ", 4),

        # Division markets
        ("Atlantic Division Winner", "division", "Atlantic Div", 3),
        ("NFC East", "conference", "NFC Champ", 4),  # NFC triggers conference

        # Play-In
        ("Eastern Conference Play-In", "conference", "Eastern Champ", 4),  # conference first
        ("Play-In Tournament", "play_in", "Play-In", 2),

        # Make Playoffs
        ("Make NBA Playoffs", "playoffs", "Playoffs", 1),
        ("NBA Playoff Qualifiers", "playoffs", "Playoffs", 1),

        # #1 Seed / Best Record
        ("#1 Seed", "top_seed", "#1 Seed", 6),
        ("Best Record", "top_seed", "#1 Seed", 6),

        # Non-playoff markets return None
        ("MVP", None, None, None),
        ("PPG Leader", None, None, None),
        ("Win Total", None, None, None),
    ])
    def test_stage_classification(self, label, expected_type, expected_display, expected_order):
        stage_type, display, order = compute_playoff_stage(label)
        assert stage_type == expected_type, f"{label!r}: expected type={expected_type!r}, got {stage_type!r}"
        assert display == expected_display, f"{label!r}: expected display={expected_display!r}, got {display!r}"
        assert order == expected_order, f"{label!r}: expected order={expected_order!r}, got {order!r}"

    def test_conference_before_championship_regression(self):
        """The exact bug that was fixed 3 times (web, iOS, web again).

        'Eastern Conference Champion' contains both 'conference' and 'champion'.
        Must classify as conference (order 4), NOT championship (order 5).
        """
        stage_type, display, order = compute_playoff_stage("Eastern Conference Champion")
        assert stage_type == "conference"
        assert order == 4
        assert "Eastern" in display

    def test_empty_input(self):
        assert compute_playoff_stage("") == (None, None, None)
        assert compute_playoff_stage("", "") == (None, None, None)


# ── Aggregate quality metrics ─────────────────────────────────────────────


class TestTruthSetQuality:
    """Score the normalization pipeline against the full truth set.

    These tests enforce minimum quality thresholds. As we improve the
    normalization, we ratchet the thresholds upward.
    """

    def test_label_accuracy(self, truth_set):
        """Percentage of markets where clean label matches expected."""
        correct = 0
        total = len(truth_set)
        failures = []
        for entry in truth_set:
            actual = normalize_market_label(entry["raw_name"])
            if actual == entry["expected_label"]:
                correct += 1
            else:
                failures.append(
                    f"  '{entry['raw_name']}'\n"
                    f"    expected: '{entry['expected_label']}'\n"
                    f"    got:      '{actual}'"
                )
        accuracy = correct / total if total else 0
        if failures:
            print(f"\nLabel accuracy: {accuracy:.1%} ({correct}/{total})")
            print("Failures:")
            for f in failures[:15]:
                print(f)
        assert accuracy >= 0.85, f"Label accuracy {accuracy:.1%} below 85% threshold"

    def test_category_accuracy(self, truth_set):
        """Percentage of markets where category matches expected."""
        correct = 0
        total = len(truth_set)
        failures = []
        for entry in truth_set:
            clean = normalize_market_label(entry["raw_name"])
            actual = classify_market_category(clean, raw_name=entry["raw_name"])
            if actual == entry["expected_category"]:
                correct += 1
            else:
                failures.append(
                    f"  '{entry['raw_name']}' -> '{clean}'\n"
                    f"    expected cat: '{entry['expected_category']}'\n"
                    f"    got cat:      '{actual}'"
                )
        accuracy = correct / total if total else 0
        if failures:
            print(f"\nCategory accuracy: {accuracy:.1%} ({correct}/{total})")
            print("Failures:")
            for f in failures[:15]:
                print(f)
        assert accuracy >= 0.85, f"Category accuracy {accuracy:.1%} below 85% threshold"

    def test_merge_group_accuracy(self, truth_set):
        """Percentage of markets where merge group matches expected."""
        correct = 0
        total = len(truth_set)
        failures = []
        for entry in truth_set:
            clean = normalize_market_label(entry["raw_name"])
            actual = get_merge_group(clean)
            expected = entry["expected_merge_group"]
            if actual == expected:
                correct += 1
            else:
                failures.append(
                    f"  '{entry['raw_name']}' -> '{clean}'\n"
                    f"    expected group: '{expected}'\n"
                    f"    got group:      '{actual}'"
                )
        accuracy = correct / total if total else 0
        if failures:
            print(f"\nMerge group accuracy: {accuracy:.1%} ({correct}/{total})")
            print("Failures:")
            for f in failures[:15]:
                print(f)
        assert accuracy >= 0.80, f"Merge group accuracy {accuracy:.1%} below 80% threshold"

    def test_wrong_sport_detection(self, truth_set):
        """Recall and precision of wrong-sport detection."""
        tp = fp = fn = tn = 0
        failures = []
        for entry in truth_set:
            outcome = entry.get("sample_outcome", "")
            sport_key = entry.get("sport_key", "basketball_nba")
            actual = is_wrong_sport_leak(
                entry["raw_name"], outcome, sport_key
            )
            expected = entry["is_wrong_sport"]
            if expected and actual:
                tp += 1
            elif expected and not actual:
                fn += 1
                failures.append(f"  MISSED: '{entry['raw_name']}' (sport={sport_key})")
            elif not expected and actual:
                fp += 1
                failures.append(f"  FALSE POS: '{entry['raw_name']}' (sport={sport_key})")
            else:
                tn += 1

        recall = tp / (tp + fn) if (tp + fn) else 1.0
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        if failures:
            print(f"\nWrong sport: tp={tp} fp={fp} fn={fn} tn={tn}")
            for f in failures:
                print(f)
        assert recall >= 0.80, f"Wrong sport recall {recall:.1%} below 80%"
        assert precision >= 0.80, f"Wrong sport precision {precision:.1%} below 80%"

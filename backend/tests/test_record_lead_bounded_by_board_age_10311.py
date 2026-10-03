"""#10311 — a 71-game lead over a board written today is last season, not lag.

Production, 2026-10-03 10:12Z, `bainluck.com/sports` at 390px: every
Canadiens card read "MTL 41-21-10 · PIT 1-0-0". The name lookup (#7132) picks
row 12651 `Montreal`, whose board StatPal wrote at 08:00Z that morning (1-0
after the opener) and whose `current_record` nothing has refreshed since last
season's 72 games. `record_text` (#5520) read any lead over a played-game board
as lag, so it printed the finished season.

The three rows below are production's, verbatim, read 2026-10-03 10:31Z.
The control is #5520's own MLB case: a one-game lead over a board 19.7h old
must still be taken, or this fix has undone the defect #5520 closed.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes.events import _compute_standings_context, _format_team_data
from app.utils.standings_shape import (
    LAG_ALLOWANCE_BASE_GAMES,
    LAG_ALLOWANCE_GAMES_PER_DAY,
    reconciled_record_and_standings,
    record_text,
)

BOARD_WRITTEN = datetime(2026, 10, 3, 8, 0, 0, 78586, tzinfo=timezone.utc)
SEEN = datetime(2026, 10, 3, 10, 12, tzinfo=timezone.utc)

MONTREAL_CURRENT_RECORD = "41-21-10"
MONTREAL_STANDINGS = {
    "pct": ".1000",
    "wins": 1,
    "losses": 0,
    "points": 2,
    "streak": "W1",
    "div_rank": 3,
    "division": "Atlantic Division",
    "goals_for": 3,
    "conference": "Eastern Conference",
    "home_record": "0-0-0",
    "road_record": "1-0-0",
    "goals_against": 2,
}

# Ottawa is armed: today the rollover arm shows its 0-0, and the first game it
# plays turns the board into a played-game board against a 81-game column.
OTTAWA_CURRENT_RECORD = "43-27-11"
OTTAWA_AFTER_ITS_OPENER = {
    "wins": 0,
    "losses": 1,
    "points": 0,
    "streak": "L1",
    "div_rank": 6,
    "division": "Atlantic Division",
    "conference": "Eastern Conference",
    "home_record": "0-1-0",
    "road_record": "0-0-0",
}

# #5520's control, as production held it 2026-09-19 03:45Z.
MLB_BOARD_WRITTEN = datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc)
MLB_SEEN = datetime(2026, 9, 19, 3, 45, tzinfo=timezone.utc)
DODGERS_STANDINGS = {"wins": 92, "losses": 60, "div_rank": 1, "division": "West"}
DODGERS_CURRENT_RECORD = "93-60"


class TestTheSpecimen:
    def test_montreal_prints_this_seasons_board_not_last_seasons_72_games(self):
        out = record_text(
            MONTREAL_CURRENT_RECORD, MONTREAL_STANDINGS, BOARD_WRITTEN, SEEN
        )
        assert out == "1-0-0"  # r2: the board keeps its overtime-loss column

    def test_without_the_stamp_the_old_answer_comes_back(self):
        # Strawman: the stamp is what carries the fix. Remove it and #5520's
        # unbounded rule prints the served string again, so the test above is
        # not passing for some other reason.
        assert record_text(MONTREAL_CURRENT_RECORD, MONTREAL_STANDINGS) == "41-21-10"

    def test_ottawa_does_not_flip_once_its_board_records_a_game(self):
        out = record_text(
            OTTAWA_CURRENT_RECORD, OTTAWA_AFTER_ITS_OPENER, BOARD_WRITTEN, SEEN
        )
        assert out == "0-1-0"


class TestTheMlbControl:
    def test_a_one_game_lead_over_a_20_hour_old_board_is_still_taken(self):
        out = record_text(
            DODGERS_CURRENT_RECORD, DODGERS_STANDINGS, MLB_BOARD_WRITTEN, MLB_SEEN
        )
        assert out == "93-60"

    def test_a_board_left_unwritten_for_a_week_still_trails_a_weeks_games(self):
        # A board StatPal stopped writing is the case where the lead is
        # legitimately large. Six games over a board six days old is lag.
        stale_week = MLB_SEEN - timedelta(days=6)
        assert record_text("98-61", DODGERS_STANDINGS, stale_week, MLB_SEEN) == "98-61"


class TestTheBound:
    def test_the_edge_of_the_allowance_is_inclusive(self):
        board = {"wins": 10, "losses": 10}
        allowed = LAG_ALLOWANCE_BASE_GAMES + LAG_ALLOWANCE_GAMES_PER_DAY * 1
        at_edge = f"{10 + allowed}-10"
        past_edge = f"{10 + allowed + 1}-10"
        written = SEEN - timedelta(days=1)
        assert record_text(at_edge, board, written, SEEN) == at_edge
        assert record_text(past_edge, board, written, SEEN) == "10-10"

    def test_a_stamp_in_the_future_counts_as_zero_days_not_negative(self):
        board = {"wins": 10, "losses": 10}
        tomorrow = SEEN + timedelta(days=1)
        lead_of_base = f"{10 + LAG_ALLOWANCE_BASE_GAMES}-10"
        assert record_text(lead_of_base, board, tomorrow, SEEN) == lead_of_base

    def test_an_unreadable_stamp_proves_nothing_and_keeps_5520s_answer(self):
        for junk in ("not a date", 12345, object()):
            assert (
                record_text(MONTREAL_CURRENT_RECORD, MONTREAL_STANDINGS, junk, SEEN)
                == "41-21-10"
            )

    def test_an_iso_string_and_a_naive_stamp_are_read_as_utc(self):
        assert (
            record_text(
                MONTREAL_CURRENT_RECORD,
                MONTREAL_STANDINGS,
                "2026-10-03T08:00:00.078586Z",
                SEEN,
            )
            == "1-0-0"
        )
        naive = BOARD_WRITTEN.replace(tzinfo=None)
        assert (
            record_text(MONTREAL_CURRENT_RECORD, MONTREAL_STANDINGS, naive, SEEN)
            == "1-0-0"
        )

    def test_the_real_clock_is_used_when_no_now_is_passed(self):
        # A board written a minute ago allows only the base; a 71-game lead
        # fails on any real clock after the stamp.
        just_now = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert (
            record_text(MONTREAL_CURRENT_RECORD, MONTREAL_STANDINGS, just_now) == "1-0-0"
        )

    def test_the_rollover_and_behind_arms_are_unchanged(self):
        anaheim = {"wins": 0, "losses": 0, "div_rank": 6, "division": "Pacific"}
        assert record_text("43-33-6", anaheim, BOARD_WRITTEN, SEEN) == "0-0"
        brooklyn = {"wins": 20, "losses": 62}
        assert record_text("18-59", brooklyn, BOARD_WRITTEN, SEEN) == "20-62"
        assert record_text("21-61", brooklyn, BOARD_WRITTEN, SEEN) == "21-61"


def _montreal_row(**overrides):
    row = SimpleNamespace(
        id=12651,
        name="Montreal",
        primary_color=None,
        secondary_color=None,
        logo_url_small=None,
        logo_url_large=None,
        abbreviation="MTL",
        current_record=MONTREAL_CURRENT_RECORD,
        standings_data=MONTREAL_STANDINGS,
        standings_updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
        season_stats=None,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


class TestTheServedSurfaces:
    """Both callers must pass the stamp, or the fix is inert where readers look."""

    def test_the_card_payload_serves_one_record_and_it_is_the_board(self):
        data = _format_team_data(_montreal_row())
        assert data["record"] == "1-0-0"
        assert data["standings"]["wins"] == 1
        assert data["standings"]["losses"] == 0

    def test_the_hero_reads_the_board(self):
        out = _compute_standings_context(_montreal_row(), None, "Canadiens", "Penguins")
        assert out["home"].startswith("1-0-0, #3 Atlantic")
        assert "41-21-10" not in out["home"]

    def test_the_reconciler_threads_the_stamp_through(self):
        record, standings = reconciled_record_and_standings(
            MONTREAL_CURRENT_RECORD, MONTREAL_STANDINGS, BOARD_WRITTEN, SEEN
        )
        assert record == "1-0-0"
        # r2: the served record has three parts and the board's blob two, so
        # the reconciler writes the third back as it does for #10252's
        # Carolina; the argument itself is never mutated.
        assert (standings["wins"], standings["losses"], standings["draws"]) == (1, 0, 0)
        assert "draws" not in MONTREAL_STANDINGS


class TestTheBoardKeepsItsOvertimeLossColumn:
    """r2. Once the board won, the Canadiens hero read "1-0" beside the
    Penguins' "1-0-0" (production, 2026-10-03 12:05Z, v5441): the NHL board
    stores no overtime-loss key. The column is recovered from the board's own
    splits only when its points confirm hockey scoring."""

    PITTSBURGH_STANDINGS = {
        **MONTREAL_STANDINGS,
        "div_rank": 2,
        "division": "Metropolitan Division",
    }

    def test_the_specimen_pair_reads_in_one_shape(self):
        pit = record_text("1-0-0", self.PITTSBURGH_STANDINGS, BOARD_WRITTEN, SEEN)
        mtl = record_text(MONTREAL_CURRENT_RECORD, MONTREAL_STANDINGS, BOARD_WRITTEN, SEEN)
        assert (pit, mtl) == ("1-0-0", "1-0-0")

    def test_an_overtime_loss_on_the_board_alone_is_recovered(self):
        board = {"wins": 2, "losses": 1, "points": 5, "home_record": "1-1-0", "road_record": "1-0-1"}
        assert record_text(None, board) == "2-1-1"

    def test_controls_the_column_is_never_invented(self):
        base = {"wins": 2, "losses": 1, "points": 5, "home_record": "1-1-0", "road_record": "1-0-1"}
        # MLB: two-part splits.
        assert record_text(None, {"wins": 2, "losses": 1, "home_record": "1-1", "road_record": "1-0"}) == "2-1"
        # Splits that do not add up to the board's wins and losses.
        assert record_text(None, {**base, "road_record": "2-0-1"}) == "2-1"
        # Points that are not 2 a win + 1 an overtime loss (soccer's 3 a win).
        assert record_text(None, {**base, "points": 7}) == "2-1"
        # No points at all (an NFL board), or an unreadable one.
        assert record_text(None, {k: v for k, v in base.items() if k != "points"}) == "2-1"
        assert record_text(None, {**base, "points": "5"}) == "2-1"
        # A sport that names its third column composes it itself.
        assert record_text(None, {**base, "ties": 0}) == "2-1"
        assert record_text(None, {**base, "draws": 3}) == "2-1-3"

    def test_the_client_composed_snapshot_is_unchanged(self):
        # The reconciler compares against what a client composes from the blob;
        # that string must stay two-part or Carolina's card loses its column.
        from app.utils.standings_shape import _snapshot_record

        assert _snapshot_record(MONTREAL_STANDINGS) == "1-0"

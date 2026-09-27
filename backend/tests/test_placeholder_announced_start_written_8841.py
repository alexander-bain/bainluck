"""#8841: once ESPN announces the time, it is written over the placeholder.

Specimen: Red Sox @ Yankees Wild Card, read 2026-09-27 19:30Z. ESPN 401907924
(Game 1) ``2026-09-30T00:00Z`` and 401907963 (Game 2) ``2026-10-01T00:00Z``,
both ``timeValid: true``; MLB 849851 / 849848 agree (``startTimeTBD: false``) —
5:00 PM PT on Sep 29 and Sep 30. Our rows 15319563 / 15319236 still held
StatPal's ``20:00Z`` placeholder and its mark, so the cards read "Sep 29 · TBD"
and "Sep 30 · TBD" with the time public. 15319236 has no ``espn_id``; nor do
Cubs @ Padres 15319853 / 15319854 (ESPN 401907974 / 401907975, 02:00Z).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks import espn_start_placeholders as task
from app.tasks.espn_start_placeholders import (
    CandidateRow,
    board_day,
    board_game_for,
    candidate_statement,
    plan_move,
)
from app.utils.start_placeholder import (
    announced_start_over_placeholder,
    espn_start_placeholder_tag,
    start_is_tbd,
    start_placeholder_tag,
)

UTC = timezone.utc
G1_PLACEHOLDER = datetime(2026, 9, 29, 20, 0, tzinfo=UTC)
G2_PLACEHOLDER = datetime(2026, 9, 30, 20, 0, tzinfo=UTC)
G1_ANNOUNCED = datetime(2026, 9, 30, 0, 0, tzinfo=UTC)   # 8 PM ET Sep 29
G2_ANNOUNCED = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)   # 8 PM ET Sep 30
CUBS_G1_ANNOUNCED = datetime(2026, 9, 30, 2, 0, tzinfo=UTC)  # 10 PM ET Sep 29
CUBS_G2_ANNOUNCED = datetime(2026, 10, 1, 2, 0, tzinfo=UTC)
G1_TAG = start_placeholder_tag(G1_PLACEHOLDER)
G2_TAG = start_placeholder_tag(G2_PLACEHOLDER)


def _team(name):
    return SimpleNamespace(display_name=name, name=name.split()[-1])


def _game(espn_id, date, away, home, *, announced=True, status="scheduled"):
    return SimpleNamespace(
        espn_id=espn_id, date=date, status=status,
        time_valid=announced, time_announced=announced,
        home_team=_team(home), away_team=_team(away),
    )


#: ESPN's MLB boards as read 2026-09-27 19:29Z, Wild Card games only.
SEP29_BOARD = [
    _game("401907965", datetime(2026, 9, 29, 18, 0, tzinfo=UTC),
          "Diamondbacks/Phillies", "Atlanta Braves"),
    _game("401907924", G1_ANNOUNCED, "Boston Red Sox", "New York Yankees"),
    _game("401907974", CUBS_G1_ANNOUNCED, "Chicago Cubs", "San Diego Padres"),
]
SEP30_BOARD = [
    _game("401907963", G2_ANNOUNCED, "Boston Red Sox", "New York Yankees"),
    _game("401907975", CUBS_G2_ANNOUNCED, "Chicago Cubs", "San Diego Padres"),
]


def _row(event_id=15319563, espn_id="401907924", commence=G1_PLACEHOLDER, tags=None,
         source="statpal", home="New York Yankees", away="Boston Red Sox"):
    return CandidateRow(
        event_id=event_id, sport_key="baseball_mlb", espn_id=espn_id,
        commence_time=commence,
        event_tags=[G1_TAG] if tags is None else tags,
        commence_time_source=source, home_team_name=home, away_team_name=away,
    )


def _announced(**kw):
    args = dict(
        event_tags=["provenance:source:odds_api", G1_TAG],
        commence_time=G1_PLACEHOLDER,
        status="scheduled",
        time_announced=True,
        espn_status="scheduled",
        espn_date=G1_ANNOUNCED,
    )
    args.update(kw)
    return announced_start_over_placeholder(**args)


# ─────────────────────────────────────────────────────────────────────────────
# 1. The rule
# ─────────────────────────────────────────────────────────────────────────────

class TestTheRule:
    def test_the_specimen_takes_the_announced_first_pitch(self):
        assert _announced() == G1_ANNOUNCED

    def test_the_write_retires_the_tbd_by_itself(self):
        tags = ["provenance:source:odds_api", G1_TAG]
        assert start_is_tbd(tags, G1_PLACEHOLDER, "scheduled")
        assert not start_is_tbd(tags, _announced(), "scheduled")

    def test_an_unmarked_start_is_never_replaced(self):
        assert _announced(event_tags=["provenance:source:statpal"]) is None

    def test_a_mark_for_another_instant_is_no_licence(self):
        assert _announced(event_tags=[G2_TAG]) is None

    def test_an_absent_flag_is_no_announcement(self):
        assert _announced(time_announced=False) is None

    def test_a_game_espn_has_started_is_not_filled_in(self):
        assert _announced(espn_status="in") is None

    def test_only_a_scheduled_row_moves(self):
        assert _announced(status="live") is None

    def test_another_eastern_date_is_a_redate_not_an_announcement(self):
        # Game 2's announced time is Sep 30 Eastern; Game 1's row is Sep 29.
        assert _announced(espn_date=G2_ANNOUNCED) is None

    def test_the_date_is_eastern_not_utc(self):
        # 00:00Z Sep 30 is 8 PM Sep 29 Eastern: the same date as the row.
        assert G1_ANNOUNCED.date() != G1_PLACEHOLDER.date()
        assert _announced() == G1_ANNOUNCED

    def test_the_same_minute_is_nothing_to_write(self):
        assert _announced(espn_date=G1_PLACEHOLDER) is None

    def test_espns_own_midnight_mark_is_filled_in_too(self):
        midnight = datetime(2026, 10, 3, 4, 0, tzinfo=UTC)
        kickoff = datetime(2026, 10, 3, 23, 30, tzinfo=UTC)
        assert _announced(
            event_tags=[espn_start_placeholder_tag(midnight)],
            commence_time=midnight, espn_date=kickoff,
        ) == kickoff

    def test_a_naive_espn_date_reads_as_utc(self):
        assert _announced(espn_date=G1_ANNOUNCED.replace(tzinfo=None)) == G1_ANNOUNCED


class TestTheRanking:
    def test_espn_outranks_statpals_placeholder(self):
        assert plan_move(_row(), SEP29_BOARD[1]) == ("move", G1_ANNOUNCED)

    def test_a_source_that_outranks_espn_keeps_its_start(self):
        assert plan_move(_row(source="mlb_schedule_repair"), SEP29_BOARD[1]) == (
            "outranked", None,
        )

    def test_nothing_to_fill_in_is_none(self):
        assert plan_move(_row(tags=[]), SEP29_BOARD[1]) == ("none", None)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Which game on the board the row is
# ─────────────────────────────────────────────────────────────────────────────

class TestTheBoardGame:
    def test_an_anchored_row_is_found_by_its_id(self):
        assert board_game_for(_row(), SEP29_BOARD) == ("by_id", SEP29_BOARD[1])

    def test_an_anchored_row_is_found_only_by_its_id(self):
        board = [_game("401999999", G1_ANNOUNCED, "Boston Red Sox", "New York Yankees")]
        assert board_game_for(_row(), board) == ("not_on_board", None)

    def test_a_row_without_an_id_is_found_by_its_teams(self):
        row = _row(event_id=15319853, espn_id=None, home="San Diego Padres",
                   away="Chicago Cubs")
        assert board_game_for(row, SEP29_BOARD) == ("by_teams", SEP29_BOARD[2])

    def test_the_teams_must_sit_in_the_rows_orientation(self):
        row = _row(espn_id=None, home="Boston Red Sox", away="New York Yankees")
        assert board_game_for(row, SEP29_BOARD) == ("not_on_board", None)

    def test_two_games_for_one_pair_is_nobodys_to_pick(self):
        board = SEP29_BOARD + [
            _game("401907999", datetime(2026, 9, 29, 17, 5, tzinfo=UTC),
                  "Boston Red Sox", "New York Yankees"),
        ]
        assert board_game_for(_row(espn_id=None), board) == ("ambiguous", None)

    def test_an_undecided_opponent_matches_nothing(self):
        row = _row(espn_id=None, home="Atlanta Braves", away="Philadelphia Phillies")
        assert board_game_for(row, SEP29_BOARD) == ("not_on_board", None)

    def test_names_compare_without_case_or_punctuation(self):
        row = _row(espn_id=None, home="new york yankees", away="Boston Red Sox.")
        assert board_game_for(row, SEP29_BOARD)[0] == "by_teams"

    def test_the_board_is_the_rows_eastern_date(self):
        assert board_day(G1_PLACEHOLDER) == "20260929"
        assert board_day(CUBS_G1_ANNOUNCED) == "20260929"
        assert board_day(G2_PLACEHOLDER) == "20260930"

    def test_the_candidate_query_nominates_every_marked_row(self):
        from sqlalchemy.dialects import postgresql

        sql = str(
            candidate_statement(datetime(2026, 9, 27, tzinfo=UTC)).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert "CAST(events.event_tags AS VARCHAR) LIKE " in sql
        assert "'provenance:start-placeholder:'" in sql
        assert " OR " in sql


# ─────────────────────────────────────────────────────────────────────────────
# 3. The pass
# ─────────────────────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    """First execute answers the candidate query, the next the held-id lookup."""

    def __init__(self, rows, held=()):
        self.answers = [rows, [(h,) for h in held]]
        self.commits = 0

    async def execute(self, stmt):
        return _Result(self.answers.pop(0) if self.answers else [])

    async def commit(self):
        self.commits += 1


class _Ctx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


def _wire(monkeypatch, *, rows, boards, held=(), write_lands=True):
    import app.services.espn_api as espn_api
    import app.tasks.base as task_base
    import app.utils.start_placeholder_write as writer

    session = _Session(rows, held)
    reads, moves, marks = [], [], []

    class _Espn:
        async def get_scoreboard(self, sport_key, date=None, groups=None):
            reads.append((sport_key, date))
            return boards.get((sport_key, date))

        async def close(self):
            pass

    async def _move(sess, event_id, placeholder, announced):
        moves.append((event_id, placeholder, announced))
        return write_lands

    async def _mark(sess, event_id, desired):
        marks.append((event_id, list(desired)))

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx(session))
    monkeypatch.setattr(espn_api, "ESPNAPIService", lambda *a, **kw: _Espn())
    monkeypatch.setattr(writer, "write_announced_start", _move)
    monkeypatch.setattr(writer, "write_espn_start_placeholder_tags", _mark)
    return session, reads, moves, marks


def _db(event_id, espn_id, commence, home, away, tags):
    return (event_id, "baseball_mlb", espn_id, commence, tags, "statpal", home, away)


WILD_CARD_ROWS = [
    _db(15319563, "401907924", G1_PLACEHOLDER, "New York Yankees", "Boston Red Sox",
        ["provenance:source:odds_api", G1_TAG]),
    _db(15319853, None, G1_PLACEHOLDER, "San Diego Padres", "Chicago Cubs", [G1_TAG]),
    _db(15319236, None, G2_PLACEHOLDER, "New York Yankees", "Boston Red Sox", [G2_TAG]),
    _db(15319854, None, G2_PLACEHOLDER, "San Diego Padres", "Chicago Cubs", [G2_TAG]),
]
BOARDS = {("baseball_mlb", "20260929"): SEP29_BOARD, ("baseball_mlb", "20260930"): SEP30_BOARD}


@pytest.mark.asyncio
async def test_all_four_wild_card_rows_take_their_first_pitch(monkeypatch):
    session, reads, moves, marks = _wire(monkeypatch, rows=WILD_CARD_ROWS, boards=BOARDS)
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert reads == [("baseball_mlb", "20260929"), ("baseball_mlb", "20260930")]
    assert moves == [
        (15319563, G1_PLACEHOLDER, G1_ANNOUNCED),
        (15319853, G1_PLACEHOLDER, CUBS_G1_ANNOUNCED),
        (15319236, G2_PLACEHOLDER, G2_ANNOUNCED),
        (15319854, G2_PLACEHOLDER, CUBS_G2_ANNOUNCED),
    ]
    assert marks == []
    assert session.commits == 1
    assert stats["move"] == 4
    assert stats["moves"][0] == {
        "event_id": 15319563, "from": "2026-09-29T20:00:00+00:00",
        "to": "2026-09-30T00:00:00+00:00", "from_source": "statpal",
    }


@pytest.mark.asyncio
async def test_a_dry_run_plans_the_moves_and_writes_nothing(monkeypatch):
    session, _, moves, _ = _wire(monkeypatch, rows=WILD_CARD_ROWS, boards=BOARDS)
    stats = await task._run_mark_espn_start_placeholders(apply=False)
    assert moves == [] and session.commits == 0
    assert [m["event_id"] for m in stats["moves"]] == [15319563, 15319853, 15319236, 15319854]


@pytest.mark.asyncio
async def test_a_game_another_row_already_carries_is_not_taken_by_name(monkeypatch):
    _, _, moves, _ = _wire(
        monkeypatch, rows=WILD_CARD_ROWS, boards=BOARDS, held=["401907963"],
    )
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert 15319236 not in [m[0] for m in moves]
    assert len(moves) == 3
    assert stats["move_id_held_elsewhere"] == 1


@pytest.mark.asyncio
async def test_a_row_moved_under_the_pass_is_counted_stale_not_moved(monkeypatch):
    _, _, moves, _ = _wire(
        monkeypatch, rows=WILD_CARD_ROWS[:1], boards=BOARDS, write_lands=False,
    )
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert len(moves) == 1
    assert stats["move"] == 0 and stats["move_stale"] == 1 and stats["moves"] == []


@pytest.mark.asyncio
async def test_before_espn_announces_nothing_moves(monkeypatch):
    tbd = {
        key: [
            SimpleNamespace(**{**vars(g), "time_valid": False, "time_announced": False})
            for g in board
        ]
        for key, board in BOARDS.items()
    }
    _, _, moves, marks = _wire(monkeypatch, rows=WILD_CARD_ROWS, boards=tbd)
    stats = await task._run_mark_espn_start_placeholders(apply=True)
    assert moves == [] and marks == []
    assert stats["move"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. The write: compare-and-write, one column and its provenance
# ─────────────────────────────────────────────────────────────────────────────

class _Capture:
    def __init__(self, rowcount):
        self.rowcount = rowcount
        self.calls = []

    async def execute(self, stmt, params=None):
        self.calls.append((" ".join(str(stmt).split()), params))
        return SimpleNamespace(rowcount=self.rowcount)


@pytest.mark.asyncio
async def test_the_write_lands_only_on_the_placeholder_it_read():
    from app.utils.start_placeholder_write import write_announced_start

    session = _Capture(rowcount=1)
    assert await write_announced_start(session, 15319563, G1_PLACEHOLDER, G1_ANNOUNCED)
    sql, params = session.calls[0]
    assert sql.startswith("UPDATE events SET commence_time = :announced, "
                          "commence_time_source = 'espn' WHERE ")
    assert "id = :eid" in sql
    assert "commence_time = :placeholder" in sql.split("WHERE", 1)[1]
    assert "status = 'scheduled'" in sql.split("WHERE", 1)[1]
    assert params == {"announced": G1_ANNOUNCED, "placeholder": G1_PLACEHOLDER,
                      "eid": 15319563}


@pytest.mark.asyncio
async def test_a_row_that_moved_on_reports_not_moved():
    from app.utils.start_placeholder_write import write_announced_start

    assert not await write_announced_start(
        _Capture(rowcount=0), 15319563, G1_PLACEHOLDER, G1_ANNOUNCED
    )

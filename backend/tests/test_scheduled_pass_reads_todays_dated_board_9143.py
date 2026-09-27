"""#9143 — Mets @ Nationals shows its real first pitch before it starts.

**SHIP: a game ESPN re-times after we first stamped it shows the new first pitch
before the game, not after ESPN's undated board happens to roll over.**
(Pillar: TRUTH.)

Production, 2026-09-27 13:08Z: `/search?q=mets` read "Today 12:05 PM" for Mets @
Nationals. Row 15319523 held `commence_time 19:05Z`, `commence_time_source='espn'`,
`espn_id 401817106`; ESPN's dated board and MLB (gamePk 822679) both said 17:05Z.
Re-read 13:39Z: the row still 19:05Z, and ESPN's undated MLB board still
`day=2026-09-26`, 13 games, 401817106 absent.

Two rails could have fixed it and neither did:
- the odds poll read 17:05Z off the dated board, but claims in odds_api's name,
  and odds_api (rank 1) may not revise an espn (rank 3) start — correctly;
- the pre-game pass (`sync_scheduled_events`) may revise it (same provider), but
  is handed the UNDATED board, which did not carry the game.

The fix hands the pre-game pass today's DATED board when one of its own
id-anchored, today-filed rows is missing from the undated one. This file pins
the decision, the fetch, the board the pass receives through the whole task, and
— so the change is not inert — that the real writer then moves the specimen.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

MLB = "baseball_mlb"
METS_NATS = "401817106"
NOW = datetime(2026, 9, 27, 13, 8, tzinfo=timezone.utc)
OUR_START = datetime(2026, 9, 27, 19, 5, tzinfo=timezone.utc)  # the row
ESPN_START = datetime(2026, 9, 27, 17, 5, tzinfo=timezone.utc)  # ESPN + MLB


class _Team(SimpleNamespace):
    """An ESPN team payload: any field not named reads as None."""

    def __getattr__(self, _name):
        return None


def _ee(espn_id, date=None, home="Washington Nationals", away="New York Mets"):
    return SimpleNamespace(
        espn_id=espn_id, date=date or ESPN_START, broadcasts=[], season_type=None,
        home_team=_Team(display_name=home, name=home),
        away_team=_Team(display_name=away, name=away),
    )


# Yesterday's board, as ESPN served it undated at 13:08Z and 13:39Z.
UNDATED = [
    _ee(f"4018170{n:02d}", datetime(2026, 9, 26, 23, 5, tzinfo=timezone.utc),
        home=f"Home Club {n}", away=f"Away Club {n}")
    for n in range(13)
]
DATED_TODAY = [_ee(METS_NATS), _ee("401817200")]


# ── 1. The decision ─────────────────────────────────────────────────────────


class TestWhichDayIsAsked:
    def test_the_specimen_asks_for_today(self):
        """THE WITNESS for the rule: id off the board, row filed under today."""
        from app.tasks.espn_sync import scheduled_dated_board_day

        assert scheduled_dated_board_day(UNDATED, [(METS_NATS, OUR_START)], NOW) == "20260927"

    def test_a_row_already_on_the_board_asks_nothing(self):
        from app.tasks.espn_sync import scheduled_dated_board_day

        board = UNDATED + [_ee(METS_NATS)]
        assert scheduled_dated_board_day(board, [(METS_NATS, OUR_START)], NOW) is None

    def test_a_row_on_a_later_day_asks_nothing(self):
        """The undated board never lists tomorrow; asking would cost every pass."""
        from app.tasks.espn_sync import scheduled_dated_board_day

        tomorrow = datetime(2026, 9, 28, 17, 5, tzinfo=timezone.utc)
        assert scheduled_dated_board_day(UNDATED, [(METS_NATS, tomorrow)], NOW) is None

    def test_the_board_day_is_eastern_not_utc(self):
        """00:30Z on the 28th is 8:30 PM ET on the 27th: today's board."""
        from app.tasks.espn_sync import scheduled_dated_board_day

        late = datetime(2026, 9, 28, 0, 30, tzinfo=timezone.utc)
        assert scheduled_dated_board_day(UNDATED, [(METS_NATS, late)], NOW) == "20260927"

    @pytest.mark.parametrize("row", [(None, OUR_START), (METS_NATS, None)], ids=["no-id", "no-start"])
    def test_a_row_without_an_anchor_asks_nothing(self, row):
        from app.tasks.espn_sync import scheduled_dated_board_day

        assert scheduled_dated_board_day(UNDATED, [row], NOW) is None


class TestTheMerge:
    def test_only_missing_games_are_added(self):
        from app.tasks.espn_sync import with_dated_board

        board = UNDATED + [_ee("401817200", date=OUR_START)]
        merged = with_dated_board(board, DATED_TODAY)
        assert [ee.espn_id for ee in merged] == [ee.espn_id for ee in board] + [METS_NATS]
        # A game on both keeps the undated board's copy.
        assert merged[len(UNDATED)].date == OUR_START

    @pytest.mark.parametrize("dated", [None, []], ids=["dark", "empty"])
    def test_nothing_to_add_is_the_board(self, dated):
        from app.tasks.espn_sync import with_dated_board

        assert with_dated_board(UNDATED, dated) == UNDATED


# ── 2. The fetch ────────────────────────────────────────────────────────────


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _RowSession:
    """Answers the one prefetch read with ``(sport_key, espn_id, commence)``."""

    def __init__(self, rows):
        self.rows, self.statements = rows, []

    async def execute(self, stmt, *a, **k):
        self.statements.append(stmt)
        return _Rows(self.rows)


class _Fetch:
    def __init__(self, answer=DATED_TODAY, raises=False):
        self.answer, self.raises, self.calls = answer, raises, []

    async def __call__(self, sport_key, day):
        self.calls.append((sport_key, day))
        if self.raises:
            raise RuntimeError("boom")
        return self.answer


async def _prefetch(rows, fetch, espn_data=None):
    espn_data = {MLB: UNDATED} if espn_data is None else espn_data
    from app.tasks.espn_sync import _prefetch_scheduled_dated_boards

    stats = {"errors": []}
    session = _RowSession(rows)
    boards = await _prefetch_scheduled_dated_boards(
        session, [MLB], espn_data, {}, fetch, NOW, stats,
    )
    return boards, stats, session


class TestThePrefetch:
    @pytest.mark.asyncio
    async def test_the_specimen_sport_gets_todays_game(self):
        fetch = _Fetch()
        boards, stats, session = await _prefetch([(MLB, METS_NATS, OUR_START)], fetch)
        assert fetch.calls == [(MLB, "20260927")]
        assert [ee.espn_id for ee in boards[MLB]][-2:] == [METS_NATS, "401817200"]
        assert stats["scheduled_dated_board_fetches"] == 1
        assert len(session.statements) == 1

    @pytest.mark.asyncio
    async def test_a_rolled_board_is_not_asked_again(self):
        fetch = _Fetch()
        boards, _, _ = await _prefetch(
            [(MLB, METS_NATS, OUR_START)], fetch, espn_data={MLB: DATED_TODAY},
        )
        assert fetch.calls == [] and boards == {}

    @pytest.mark.asyncio
    async def test_a_dark_dated_board_leaves_the_sport_absent(self):
        boards, stats, _ = await _prefetch([(MLB, METS_NATS, OUR_START)], _Fetch(answer=None))
        assert boards == {} and stats["scheduled_dated_board_dark"] == 1

    @pytest.mark.asyncio
    async def test_a_raising_fetch_is_named_and_the_sport_absent(self):
        boards, stats, _ = await _prefetch([(MLB, METS_NATS, OUR_START)], _Fetch(raises=True))
        assert boards == {}
        assert stats["errors"] == ["scheduled_dated_board_baseball_mlb_20260927: boom"]

    @pytest.mark.asyncio
    async def test_a_sport_espn_went_dark_on_is_not_read(self):
        """#3473: a dark undated board means no pass, so no prefetch either."""
        fetch = _Fetch()
        boards, _, session = await _prefetch([(MLB, METS_NATS, OUR_START)], fetch, espn_data={})
        assert boards == {} and fetch.calls == [] and session.statements == []


# ── 3. Through the whole task ───────────────────────────────────────────────


class _Espn:
    def __init__(self):
        self.calls: list[tuple] = []

    async def get_scoreboard(self, sport_key, date=None, groups=None):
        self.calls.append((sport_key, date, groups))
        return DATED_TODAY if date == "20260927" else UNDATED

    async def close(self):
        pass


def _wire(monkeypatch, espn, rows):
    import app.services.espn_api as espn_api
    import app.tasks.espn_sync as espn_sync
    import app.utils.espn_helpers as helpers

    handed: dict[str, list] = {"scheduled": [], "live": []}

    async def _nothing(*a, **k):
        return None

    async def _execute(*a, **k):
        return _Rows(rows)

    class _Ctx:
        async def __aenter__(self):
            return SimpleNamespace(
                begin_nested=_Ctx, flush=_nothing, execute=_execute,
                commit=_nothing, info={},
            )

        async def __aexit__(self, *exc):
            return False

    async def _keys(session):
        return [MLB], [MLB]

    async def _decide(*a, **k):
        return {}

    async def _scheduled(session, sport_key, espn_events, stats):
        handed["scheduled"].append((sport_key, [ee.espn_id for ee in espn_events]))

    async def _live(session, sport_key, espn_events, stats, *a, **k):
        handed["live"].append((sport_key, [ee.espn_id for ee in espn_events]))

    monkeypatch.setattr(espn_sync, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(espn_api, "ESPNAPIService", lambda: espn)
    monkeypatch.setattr(espn_sync, "_find_sport_keys_to_sync", _keys)
    for name in (
        "_settle_authority_stragglers",
        "_settle_deep_authority_stragglers",
        "_recover_unstarted_authority_fixtures",
        "_act_on_failovers",
    ):
        monkeypatch.setattr(espn_sync, name, _nothing)
    monkeypatch.setattr(espn_sync, "_decide_failovers", _decide)
    monkeypatch.setattr(espn_sync, "_process_live_sport", _live)
    monkeypatch.setattr(helpers, "sync_scheduled_events", _scheduled)
    for name in ("fetch_completed_box_scores", "fetch_live_box_scores", "backfill_missing_scores"):
        monkeypatch.setattr(helpers, name, _nothing)
    return handed


class TestThroughTheWholeTask:
    @pytest.mark.asyncio
    async def test_the_pregame_pass_is_handed_the_mets_game(self, monkeypatch):
        """THE WITNESS. On the parent the pass is handed UNDATED, without 401817106."""
        from app.tasks.espn_sync import _sync_espn_live_events

        # The task reads the clock itself; any row filed under its today works.
        today_row = datetime.now(timezone.utc).replace(microsecond=0)
        espn = _Espn()
        handed = _wire(monkeypatch, espn, [(MLB, METS_NATS, today_row)])

        stats = await _sync_espn_live_events()

        assert stats["errors"] == [], stats["errors"]
        from app.utils.event_completion import espn_board_date

        today = espn_board_date(datetime.now(timezone.utc))
        assert (MLB, today, None) in espn.calls
        assert handed["scheduled"] and METS_NATS in handed["scheduled"][0][1], (
            "the pre-game pass never saw Mets @ Nationals, so its 19:05Z start "
            "stays frozen until ESPN's undated board rolls over (#9143)"
        )

    @pytest.mark.asyncio
    async def test_the_live_pass_board_is_unchanged(self, monkeypatch):
        from app.tasks.espn_sync import _sync_espn_live_events

        today_row = datetime.now(timezone.utc).replace(microsecond=0)
        handed = _wire(monkeypatch, _Espn(), [(MLB, METS_NATS, today_row)])
        await _sync_espn_live_events()
        assert handed["live"] == [(MLB, [ee.espn_id for ee in UNDATED])]


# ── 4. Not inert: the real writer moves the specimen ────────────────────────


class _Row:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    def __getattr__(self, _name):
        return None


def _run_real_scheduled_pass(monkeypatch, board):
    from app.utils import espn_helpers

    class _Sport:
        id = 53232
        key = MLB

    event = _Row(
        id=15319523, espn_id=METS_NATS, sport=_Sport(), sport_id=_Sport.id,
        home_team_name="Washington Nationals", away_team_name="New York Mets",
        home_team_id=1, away_team_id=2, commence_time=OUR_START,
        commence_time_source="espn", status="scheduled",
    )

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    calls = {"n": 0}

    class _Session:
        async def execute(self, *_a, **_k):
            calls["n"] += 1
            return _Result([event] if calls["n"] == 1 else [])

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(espn_helpers, "upsert_team", _noop)
    monkeypatch.setattr(espn_helpers, "register_espn_team_identities", _noop)
    return event, _Session()


class TestTheWriterMovesTheSpecimen:
    @pytest.mark.asyncio
    async def test_the_widened_board_moves_1905_to_1705(self, monkeypatch):
        from app.tasks.espn_sync import with_dated_board
        from app.utils.espn_helpers import sync_scheduled_events

        board = with_dated_board(UNDATED, DATED_TODAY)
        event, session = _run_real_scheduled_pass(monkeypatch, board)
        await sync_scheduled_events(session, MLB, board, {})
        assert event.commence_time == ESPN_START
        assert event.commence_time_source == "espn"

    @pytest.mark.asyncio
    async def test_the_undated_board_alone_leaves_it_frozen(self, monkeypatch):
        """The parent's board: the control that proves the witness above can fail."""
        from app.utils.espn_helpers import sync_scheduled_events

        event, session = _run_real_scheduled_pass(monkeypatch, UNDATED)
        await sync_scheduled_events(session, MLB, UNDATED, {})
        assert event.commence_time == OUR_START

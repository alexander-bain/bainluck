"""Guards for the 20-second live tennis poller — what it writes, and when not.

live/058, #2746. The parser's own guards live in `test_tennis_linescore.py`;
these are about the TASK: the gate that keeps it off ESPN when no tennis is on,
the no-op suppression that keeps it off Postgres when nothing moved, and the
two silences it must not mistake for statements.
"""

from datetime import datetime, timedelta, timezone

NOW = datetime.now(timezone.utc)


def _competitor(name, lines, winner=None):
    comp = {"athlete": {"displayName": name}, "linescores": lines}
    if winner is not None:
        comp["winner"] = winner
    return comp


def _competition(comp_id, names, *, lines, state="in", status_name="STATUS_IN_PROGRESS"):
    return {
        "id": comp_id,
        "date": "2026-09-03T18:45Z",
        "status": {
            "period": len(lines[0]),
            "type": {
                "name": status_name,
                "state": state,
                "detail": "3rd Set",
                "shortDetail": "3rd",
            },
        },
        "competitors": [
            _competitor(name, line) for name, line in zip(names, lines)
        ],
    }


def _payload(competitions):
    return {
        "events": [{
            "name": "US Open",
            "groupings": [{
                "grouping": {"slug": "mens-singles"},
                "competitions": competitions,
            }],
        }]
    }


def _line(*sets):
    """``(games, won[, tiebreak])`` per set; ``won=None`` for the set in play."""
    out = []
    for entry in sets:
        value, won = entry[0], entry[1]
        line = {"value": float(value)}
        if won is not None:
            line["winner"] = won
        if len(entry) > 2:
            line["tiebreak"] = entry[2]
        out.append(line)
    return out


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    """Answers the one SELECT, then records every UPDATE the task issues."""

    def __init__(self, rows):
        self._rows = rows
        self._selected = False
        self.updates: list[dict] = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, statement, *a, **kw):
        if not self._selected:
            self._selected = True
            return _Result(self._rows)
        self.updates.append(dict(statement.compile().params))
        return _Result([])

    async def commit(self):
        self.committed = True


def _install(monkeypatch, *, rows, payloads=None, errors=None, fetches=None):
    from app.services import espn_tennis as svc
    from app.tasks import espn_sync

    session = _Session(rows)

    def _fetch(dates=None):
        if fetches is not None:
            fetches.append(dates)
        return (payloads if payloads is not None else []), (errors or [])

    monkeypatch.setattr(svc, "fetch_scoreboards", _fetch)
    monkeypatch.setattr(espn_sync, "get_task_session", lambda: session)
    return session


def _row(event_id, espn_id, home, away, home_score=None, away_score=None, held=None):
    """The scalar tuple the task selects — id, espn_id, names, score, linescore."""
    return (event_id, espn_id, home, away, home_score, away_score, held)


LIVE_BOARD = _payload([
    _competition(
        "182709",
        ["Alejandro Tabilo", "Alexei Popyrin"],
        lines=[
            _line((2, False), (7, True, 7), (5, None)),
            _line((6, True), (6, False, 4), (6, None)),
        ],
    )
])


class TestTheGate:
    async def test_no_live_tennis_means_no_request_to_espn(self, monkeypatch):
        """THE COST CONTROL, and it is the reason a 20-second beat is
        affordable. Off-season and overnight this is every pass: one indexed
        query and nothing else. If the fetch ever moves above the population
        query, this goes red."""
        from app.tasks.espn_sync import _poll_live_tennis_scores

        fetches: list = []
        _install(monkeypatch, rows=[], payloads=[LIVE_BOARD], fetches=fetches)

        stats = await _poll_live_tennis_scores()

        assert stats["status"] == "no_live_tennis"
        assert fetches == []

    async def test_a_live_row_does_reach_espn(self, monkeypatch):
        """The control on the gate: it must not simply never fetch."""
        from app.tasks.espn_sync import _poll_live_tennis_scores

        fetches: list = []
        _install(
            monkeypatch,
            rows=[_row(1, "182709", "Alexei Popyrin", "Alejandro Tabilo")],
            payloads=[LIVE_BOARD],
            fetches=fetches,
        )

        stats = await _poll_live_tennis_scores()

        assert fetches == [None]
        assert stats["status"] == "ok"


class TestWhatItWrites:
    async def test_the_line_and_the_set_count_land_in_one_write(self, monkeypatch):
        """THE SHIP. One UPDATE carrying both grains off one read of the board.

        Two writes could interleave with a reader and show `6-2, 6-7(4), 6-5`
        beside `0-0`; one statement cannot.
        """
        from app.tasks.espn_sync import _poll_live_tennis_scores

        session = _install(
            monkeypatch,
            rows=[_row(15300836, "182709", "Alexei Popyrin", "Alejandro Tabilo")],
            payloads=[LIVE_BOARD],
        )

        stats = await _poll_live_tennis_scores()

        assert len(session.updates) == 1
        written = session.updates[0]
        assert written["linescore"]["line"] == "6-2, 6-7(4), 6-5"
        assert written["linescore"]["current_set"] == 3
        assert (written["home_score"], written["away_score"]) == (1, 1)
        assert stats["linescore_writes"] == 1
        assert stats["score_writes"] == 1
        assert session.committed

    async def test_a_reading_that_has_not_moved_is_not_rewritten(self, monkeypatch):
        """`observed_at` moves every pass by construction. Comparing the dicts
        whole would call every pass a change and write the entire live
        population to Postgres three times a minute for nothing."""
        from app.tasks.espn_sync import _poll_live_tennis_scores
        from app.utils.tennis_linescore import authority_linescore
        from app.services.espn_tennis import scoreboard_competitions

        competition = scoreboard_competitions([LIVE_BOARD])[0]
        held = authority_linescore(
            ["Alexei Popyrin", "Alejandro Tabilo"],
            competition,
            observed_at=NOW - timedelta(minutes=5),
        )["linescore"]

        session = _install(
            monkeypatch,
            rows=[_row(
                15300836, "182709", "Alexei Popyrin", "Alejandro Tabilo",
                home_score=1, away_score=1, held=held,
            )],
            payloads=[LIVE_BOARD],
        )

        stats = await _poll_live_tennis_scores()

        assert session.updates == []
        assert stats["linescore_unchanged"] == 1
        assert stats["linescore_writes"] == 0

    async def test_a_game_won_since_the_last_pass_IS_rewritten(self, monkeypatch):
        """The control on the suppression above — the whole ship is that a GAME
        moves the card. A no-op check that rejected everything would look
        identical in the test above and ship a card that never moves."""
        from app.tasks.espn_sync import _poll_live_tennis_scores
        from app.utils.tennis_linescore import authority_linescore
        from app.services.espn_tennis import scoreboard_competitions

        one_game_ago = _payload([
            _competition(
                "182709",
                ["Alejandro Tabilo", "Alexei Popyrin"],
                lines=[
                    _line((2, False), (7, True, 7), (5, None)),
                    _line((6, True), (6, False, 4), (5, None)),
                ],
            )
        ])
        held = authority_linescore(
            ["Alexei Popyrin", "Alejandro Tabilo"],
            scoreboard_competitions([one_game_ago])[0],
            observed_at=NOW - timedelta(seconds=20),
        )["linescore"]
        assert held["line"] == "6-2, 6-7(4), 5-5"

        session = _install(
            monkeypatch,
            rows=[_row(
                15300836, "182709", "Alexei Popyrin", "Alejandro Tabilo",
                home_score=1, away_score=1, held=held,
            )],
            payloads=[LIVE_BOARD],
        )

        stats = await _poll_live_tennis_scores()

        assert stats["linescore_writes"] == 1
        assert session.updates[0]["linescore"]["line"] == "6-2, 6-7(4), 6-5"
        # The set count did not move, so it is not in the statement.
        assert "home_score" not in session.updates[0]


class TestTheSilences:
    async def test_a_dark_board_touches_nothing(self, monkeypatch):
        """Both tours failed. An empty board is a fact about the READ, never
        about the fixtures — in particular no held linescore is blanked."""
        from app.tasks.espn_sync import _poll_live_tennis_scores

        session = _install(
            monkeypatch,
            rows=[_row(1, "182709", "Alexei Popyrin", "Alejandro Tabilo")],
            payloads=[],
            errors=["atp: timeout", "wta: timeout"],
        )

        stats = await _poll_live_tennis_scores()

        assert stats["status"] == "authority_dark"
        assert session.updates == []
        assert not session.committed

    async def test_a_fixture_the_board_does_not_mention_keeps_what_it_holds(
        self, monkeypatch
    ):
        """Silence about a match is not a statement about it (gotcha #53)."""
        from app.tasks.espn_sync import _poll_live_tennis_scores

        session = _install(
            monkeypatch,
            rows=[_row(1, "999999", "Somebody Else", "Another Person")],
            payloads=[LIVE_BOARD],
        )

        stats = await _poll_live_tennis_scores()

        assert stats["not_on_board"] == 1
        assert session.updates == []

    async def test_one_unreadable_row_never_costs_the_pass_its_others(
        self, monkeypatch
    ):
        """gotcha #42. The first row's names are `None`, which blows up inside
        orientation; the second must still be written."""
        from app.tasks.espn_sync import _poll_live_tennis_scores

        session = _install(
            monkeypatch,
            rows=[
                (2, "182709", None, None, None, None, None),
                _row(15300836, "182709", "Alexei Popyrin", "Alejandro Tabilo"),
            ],
            payloads=[LIVE_BOARD],
        )

        stats = await _poll_live_tennis_scores()

        assert stats["linescore_writes"] == 1
        assert session.updates[0]["id_1"] == 15300836

    async def test_a_walkover_is_refused_by_name_rather_than_written_as_zero(
        self, monkeypatch
    ):
        from app.tasks.espn_sync import _poll_live_tennis_scores

        walkover = _payload([{
            "id": "184769",
            "date": "2026-09-03T18:45Z",
            "status": {"period": 1, "type": {
                "name": "STATUS_WALKOVER", "state": "post",
                "detail": "Walkover", "shortDetail": "Walkover",
            }},
            "competitors": [
                {"athlete": {"displayName": "Grigor Dimitrov"}, "winner": True},
                {"athlete": {"displayName": "Otto Virtanen"}, "winner": False},
            ],
        }])
        session = _install(
            monkeypatch,
            rows=[_row(1, "184769", "Grigor Dimitrov", "Otto Virtanen")],
            payloads=[walkover],
        )

        stats = await _poll_live_tennis_scores()

        assert stats["linescore_refused"] == {"no-line": 1}
        assert session.updates == []

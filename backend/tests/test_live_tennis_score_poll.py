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


def _row(event_id, espn_id, home, away, home_score=None, away_score=None, held=None,
         statpal_fixture_id=None):
    """The scalar tuple the task selects.

    live/059 addendum (D59 = A′) added `statpal_fixture_id` — the join that
    decides which source speaks for this match's line. Defaulting it to None
    keeps every case below on the ESPN arm, which is the state of every row in
    production until authority/007's linker runs, and is what makes those cases
    controls for the switch rather than casualties of it.
    """
    return (event_id, espn_id, home, away, home_score, away_score, held,
            statpal_fixture_id)


def _held_line(observed_at, names=("Alexei Popyrin", "Alejandro Tabilo")):
    """The composed linescore the task writes for `LIVE_BOARD`, at a given clock.

    live/059 addendum (D59 = A′): what lands in `events.linescore` is no longer
    `authority_linescore`'s raw payload — it is `select_line`'s composition of
    it, which names its source and carries the score's own stamp. A held-value
    fixture has to be built the same way or the comparison is between two
    different shapes.
    """
    from app.services.espn_tennis import scoreboard_competitions
    from app.utils.tennis_line_source import select_line
    from app.utils.tennis_linescore import authority_linescore

    competition = scoreboard_competitions([LIVE_BOARD])[0]
    espn = authority_linescore(
        list(names), competition, observed_at=observed_at
    )["linescore"]
    return select_line(espn=espn, statpal=None, has_statpal_anchor=False)


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

        # live/059 addendum: `held` is built through the SAME composition the
        # task writes — `select_line` over the ESPN payload with no StatPal
        # anchor. Building it from `authority_linescore` alone would compare a
        # pre-addendum shape against a post-addendum one and call every pass a
        # change, which is the very write storm this test exists to forbid.
        held = _held_line(NOW - timedelta(minutes=5))

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
                (2, "182709", None, None, None, None, None, None),
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


# ═══════════════════════════════════════════════════════════════════════════
# live/059 addendum (D59 = A′) — the per-match source selector, in the poll
# ═══════════════════════════════════════════════════════════════════════════


STATPAL_MATCH = {
    "id": "2631278", "status": "Set 3", "tb": "False",
    "player": [
        # StatPal, a minute later than the ESPN board: Popyrin has taken the
        # sixth game of set three. Every score value therefore DIFFERS from
        # LIVE_BOARD's, which is what lets these tests detect a merge.
        {"name": "A. Popyrin", "id": "1", "game_score": "40", "serve": "True",
         "s1": "6", "s2": "6", "s3": "6", "s4": "", "s5": "",
         "totalscore": "1", "winner": "False"},
        {"name": "A. Tabilo", "id": "2", "game_score": "30", "serve": "False",
         "s1": "2", "s2": "7", "s3": "5", "s4": "", "s5": "",
         "totalscore": "1", "winner": "False"},
    ],
}


def _install_statpal(monkeypatch, matches, *, fetches=None):
    """Stub StatPal's live board. Records whether it was asked at all."""
    from app.tasks import espn_sync

    async def _board(stats):
        if fetches is not None:
            fetches.append(True)
        stats["statpal_board"] = len(matches)
        return matches

    monkeypatch.setattr(espn_sync, "_fetch_statpal_tennis_board", _board)


class TestTheSourceSelectorInThePoll:
    async def test_no_anchored_row_means_statpal_is_never_asked(self, monkeypatch):
        """THE GATE, and it is the reason this addendum costs nothing today.

        Every production tennis row carries no StatPal fixture id until
        authority/007's linker runs. No anchor, no request — the pass is what it
        was before the switch existed.
        """
        from app.tasks.espn_sync import _poll_live_tennis_scores

        fetches: list = []
        _install_statpal(monkeypatch, {}, fetches=fetches)
        session = _install(
            monkeypatch,
            rows=[_row(15300836, "182709", "Alexei Popyrin", "Alejandro Tabilo")],
            payloads=[LIVE_BOARD],
        )

        stats = await _poll_live_tennis_scores()

        assert fetches == [], "StatPal was fetched for a match with no anchor"
        assert stats["statpal_anchored"] == 0
        assert session.updates[0]["linescore"]["source"] == "espn"

    async def test_a_junk_fixture_id_never_costs_a_request(self, monkeypatch):
        """The shape test's only job. A non-numeric id cannot name a StatPal
        match, so asking the board about it is a request bought for nothing."""
        from app.tasks.espn_sync import _poll_live_tennis_scores

        fetches: list = []
        _install_statpal(monkeypatch, {"2631278": STATPAL_MATCH}, fetches=fetches)
        _install(
            monkeypatch,
            rows=[_row(15300836, "182709", "Alexei Popyrin", "Alejandro Tabilo",
                       statpal_fixture_id="not-an-id")],
            payloads=[LIVE_BOARD],
        )

        stats = await _poll_live_tennis_scores()

        assert fetches == []
        assert stats["statpal_anchored"] == 0

    async def test_an_anchored_row_takes_the_WHOLE_line_from_statpal(self, monkeypatch):
        from app.tasks.espn_sync import _poll_live_tennis_scores

        _install_statpal(monkeypatch, {"2631278": STATPAL_MATCH})
        session = _install(
            monkeypatch,
            rows=[_row(15300836, "182709", "Alexei Popyrin", "Alejandro Tabilo",
                       statpal_fixture_id="2631278")],
            payloads=[LIVE_BOARD],
        )

        stats = await _poll_live_tennis_scores()

        line = session.updates[0]["linescore"]
        assert stats["statpal_anchored"] == 1
        assert stats["statpal_lines"] == 1
        assert line["source"] == "statpal"
        assert line["line"] == "6-2, 6-7, 6-5"
        assert line["points"] == {"home": "40", "away": "30"}
        assert line["serving"] == "home"

    async def test_the_written_line_is_never_mixed(self, monkeypatch):
        """🔴 THE INVARIANT, asserted on the row that reaches Postgres.

        The ESPN board says `6-2, 6-7(4), 6-5` with no points; StatPal says
        `6-2, 6-7, 6-5` with `40-30`. A merge would print ESPN's bracketed
        tiebreak beside StatPal's points — two true halves, one false line.
        """
        from app.tasks.espn_sync import _poll_live_tennis_scores
        from app.utils.tennis_line_source import SCORE_FIELDS, statpal_linescore

        _install_statpal(monkeypatch, {"2631278": STATPAL_MATCH})
        session = _install(
            monkeypatch,
            rows=[_row(15300836, "182709", "Alexei Popyrin", "Alejandro Tabilo",
                       statpal_fixture_id="2631278")],
            payloads=[LIVE_BOARD],
        )

        await _poll_live_tennis_scores()
        line = session.updates[0]["linescore"]

        expected = statpal_linescore(
            ["Alexei Popyrin", "Alejandro Tabilo"], STATPAL_MATCH,
            observed_at=datetime.fromisoformat(line["observed_at"]),
        )["linescore"]
        for field in SCORE_FIELDS:
            assert line[field] == expected[field], (
                f"score field {field!r} did not come from StatPal — the line is mixed"
            )
        # …and ESPN's tiebreak bracket, which StatPal does not publish, is
        # absent rather than borrowed.
        assert "(4)" not in line["line"]

    async def test_espn_keeps_the_state_even_on_a_statpal_line(self, monkeypatch):
        from app.tasks.espn_sync import _poll_live_tennis_scores

        _install_statpal(monkeypatch, {"2631278": STATPAL_MATCH})
        session = _install(
            monkeypatch,
            rows=[_row(15300836, "182709", "Alexei Popyrin", "Alejandro Tabilo",
                       statpal_fixture_id="2631278")],
            payloads=[LIVE_BOARD],
        )

        await _poll_live_tennis_scores()
        line = session.updates[0]["linescore"]

        assert line["state"] == "in_progress"
        assert line["state_source"] == "espn"

    async def test_a_statpal_board_that_omits_the_fixture_falls_back_whole(
        self, monkeypatch
    ):
        """Silence from the anchored source is not a reason to build half a line."""
        from app.tasks.espn_sync import _poll_live_tennis_scores

        _install_statpal(monkeypatch, {})
        session = _install(
            monkeypatch,
            rows=[_row(15300836, "182709", "Alexei Popyrin", "Alejandro Tabilo",
                       statpal_fixture_id="2631278")],
            payloads=[LIVE_BOARD],
        )

        stats = await _poll_live_tennis_scores()
        line = session.updates[0]["linescore"]

        assert stats["statpal_lines"] == 0
        assert line["source"] == "espn"
        assert line["line"] == "6-2, 6-7(4), 6-5"
        assert line["points"] is None

    async def test_a_disagreement_is_recorded_with_the_scores_own_stamp(
        self, monkeypatch
    ):
        """ESPN's state, StatPal's last score, StatPal's clock — Alex's rule."""
        from app.tasks.espn_sync import _poll_live_tennis_scores

        finished = dict(STATPAL_MATCH, status="Finished")
        _install_statpal(monkeypatch, {"2631278": finished})
        session = _install(
            monkeypatch,
            rows=[_row(15300836, "182709", "Alexei Popyrin", "Alejandro Tabilo",
                       statpal_fixture_id="2631278")],
            payloads=[LIVE_BOARD],   # ESPN still says in_progress
        )

        stats = await _poll_live_tennis_scores()
        line = session.updates[0]["linescore"]

        assert stats["state_disagreements"] == 1
        assert line["state"] == "in_progress"          # ESPN's
        assert line["source"] == "statpal"             # the linked source's score
        assert line["score_as_of"] == line["observed_at"]
        assert line["state_disagrees"] is True

    async def test_a_dark_statpal_board_is_named_and_costs_nothing(self, monkeypatch):
        """An empty board and a failed fetch mean the same thing to a reader and
        must not read the same in a verdict (gotcha #53)."""
        from app.tasks import espn_sync
        from app.tasks.espn_sync import _poll_live_tennis_scores

        async def _boom(stats):
            stats["statpal_board"] = "error:RuntimeError"
            return {}

        monkeypatch.setattr(espn_sync, "_fetch_statpal_tennis_board", _boom)
        session = _install(
            monkeypatch,
            rows=[_row(15300836, "182709", "Alexei Popyrin", "Alejandro Tabilo",
                       statpal_fixture_id="2631278")],
            payloads=[LIVE_BOARD],
        )

        stats = await _poll_live_tennis_scores()

        assert stats["statpal_board"] == "error:RuntimeError"
        assert session.updates[0]["linescore"]["source"] == "espn"

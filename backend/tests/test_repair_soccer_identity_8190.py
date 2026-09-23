"""#8190 — a correct PSG linkage must not read as ``espn_id_drifted``.

Production 2026-09-20: ev15307704, soccer_france_ligue_one, Marseille (home) vs
PSG (away), espn_id 401876449, stored 1-2. ESPN's game for that id is Paris
Saint-Germain @ Marseille, 2-1 away-home: the same fixture and the same final.
The rail's only failing axis was ``names_match("PSG", "Paris Saint-Germain")``,
so the Flow Sentinel filed a linkage drift and prescribed the attended
``event-espn-id`` repair, which would have re-pointed a correct id.

The first candidate fell back to ``soccer_team_matches``, whose subset tier also
elects ``Manchester`` -> ``Manchester United`` and ``Inter`` -> ``Inter Miami``
(Codex's falsifier, 2026-09-23). The rail's second reading is narrower: equal
after the alias tables, or an initialism. Every positive below has a control
that must still refuse (gotcha #43).
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from scripts.repair_event_final_scores import (
    ESPN_ID_DRIFTED,
    ESPN_ID_UNRESOLVABLE,
    LINK_PROVEN,
    _identity_matches,
    _soccer_same_club_by_identity,
    classify_espn_link,
    same_fixture_games,
)

UTC = timezone.utc
WHEN = datetime(2026, 9, 20, 18, 45, tzinfo=UTC)
DAY = date(2026, 9, 20)
LIGUE_1 = "soccer_france_ligue_one"


def _game(espn_id, home, away, home_score=None, away_score=None, when=WHEN):
    return SimpleNamespace(
        espn_id=espn_id, status="post", date=when,
        home_team=SimpleNamespace(display_name=home, name=home, short_name=home),
        away_team=SimpleNamespace(display_name=away, name=away, short_name=away),
        home_score=home_score, away_score=away_score,
    )


def _classify(espn_id, board, *, away="PSG", home="Marseille", sport_key=LIGUE_1):
    return classify_espn_link(
        espn_id=espn_id, commence_time=WHEN, game_date=DAY,
        home_team_name=home, away_team_name=away, board=board,
        sport_key=sport_key,
    )


class TestTheIdentityReading:
    @pytest.mark.parametrize("ours, espn", [
        ("PSG", "Paris Saint-Germain"),
        ("Paris Saint-Germain", "PSG"),
        ("PSG", "Paris Saint Germain"),
        ("Go Ahead Eagles", "GA Eagles"),        # whole-name alias table
        ("Man Utd", "Man United"),               # word alias, then equal
    ])
    def test_same_club_under_two_spellings(self, ours, espn):
        assert _soccer_same_club_by_identity(ours, espn)

    @pytest.mark.parametrize("ours, espn", [
        # Codex's falsifier: the subset tier elects these; identity must not.
        ("Manchester", "Manchester United"),
        ("Inter", "Inter Miami"),
        ("Manchester United", "Manchester City"),
        # Same city, different club.
        ("PSG", "Paris FC"),
        # A squad marker on one side only is a different team.
        ("PSG", "Paris Saint-Germain W"),
        ("Paris Saint-Germain", "Paris Saint-Germain B"),
        # A one-letter initial is not evidence (FC Porto strips to `p`).
        ("P", "FC Porto"),
        # Nothing but club-form words identifies no club.
        ("FC", "FC"),
        ("", "Paris Saint-Germain"),
        (None, "PSG"),
    ])
    def test_refuses_everything_looser(self, ours, espn):
        assert not _soccer_same_club_by_identity(ours, espn)


class TestClassifyEspnLink8190:
    def test_the_production_shape_is_proven(self):
        board = [_game("401876449", "Marseille", "Paris Saint-Germain", 1, 2)]
        verdict, target, _ = _classify("401876449", board)
        assert verdict == LINK_PROVEN
        assert target.espn_id == "401876449"

    @pytest.mark.parametrize("sport_key", [None, "baseball_mlb", "basketball_nba"])
    def test_non_soccer_keeps_the_exact_legacy_verdict(self, sport_key):
        board = [_game("401876449", "Marseille", "Paris Saint-Germain", 1, 2)]
        verdict, _, reason = _classify("401876449", board, sport_key=sport_key)
        assert verdict == ESPN_ID_DRIFTED
        assert "DIFFERENT fixture" in reason

    def test_a_real_drift_still_fires_and_now_names_the_target(self):
        board = [
            _game("401876449", "Marseille", "Paris Saint-Germain", 1, 2),
            _game("401876450", "Lyon", "Monaco", 0, 0),
        ]
        verdict, target, reason = _classify("401876450", board)
        assert verdict == ESPN_ID_DRIFTED
        assert "DIFFERENT fixture" in reason
        assert target.espn_id == "401876449"

    def test_a_same_city_impostor_is_still_drift(self):
        board = [_game("401876451", "Marseille", "Paris FC", 1, 0)]
        verdict, target, _ = _classify("401876451", board)
        assert verdict == ESPN_ID_DRIFTED
        assert target is None

    def test_the_reverse_fixture_is_not_this_game(self):
        """Orientation: PSG at home to Marseille is the OTHER leg of the season."""
        board = [_game("401876460", "Paris Saint-Germain", "Marseille", 2, 1)]
        verdict, target, _ = _classify("401876460", board)
        assert verdict == ESPN_ID_DRIFTED
        assert target is None

    def test_the_womens_side_is_not_this_game(self):
        board = [_game("401876470", "Marseille W", "Paris Saint-Germain W", 0, 3)]
        verdict, target, _ = _classify("401876470", board)
        assert verdict == ESPN_ID_DRIFTED
        assert target is None

    @pytest.mark.parametrize("short, long", [
        ("Manchester", "Manchester United"),
        ("Inter", "Inter Miami"),
    ])
    def test_codex_falsifier_elects_no_target(self, short, long):
        board = [_game("fixture", "Marseille", long)]
        assert same_fixture_games("Marseille", short, board, DAY, sport_key=LIGUE_1) == []
        verdict, target, _ = _classify("GHOST", board, away=short)
        assert verdict == ESPN_ID_UNRESOLVABLE
        assert target is None

    def test_an_absent_id_elects_the_one_identity_matched_game(self):
        board = [_game("401876449", "Marseille", "Paris Saint-Germain", 1, 2)]
        verdict, target, _ = _classify("GHOST", board)
        assert verdict == ESPN_ID_DRIFTED
        assert target.espn_id == "401876449"

    def test_two_identity_matched_games_elect_nothing(self):
        board = [
            _game("A", "Marseille", "Paris Saint-Germain", 1, 2),
            _game("B", "Marseille", "Paris Saint Germain", 0, 0),
        ]
        verdict, target, _ = _classify("GHOST", board)
        assert verdict == ESPN_ID_UNRESOLVABLE
        assert target is None

    def test_another_days_game_is_not_elected(self):
        board = [_game("401876449", "Marseille", "Paris Saint-Germain", 1, 2,
                       when=datetime(2026, 9, 27, 18, 45, tzinfo=UTC))]
        assert same_fixture_games("Marseille", "PSG", board, DAY, sport_key=LIGUE_1) == []

    def test_identity_matches_is_per_side_and_oriented(self):
        assert _identity_matches("Marseille", "PSG", "Marseille", "Paris Saint-Germain",
                                 sport_key=LIGUE_1)
        assert not _identity_matches("Marseille", "PSG", "Paris Saint-Germain", "Marseille",
                                     sport_key=LIGUE_1)
        assert not _identity_matches("Marseille", "PSG", "Marseille", "Paris Saint-Germain")


# ---------------------------------------------------------------------------
# repair() — the rail must pass its own sport_key to both readings
# ---------------------------------------------------------------------------
_GROUPS = [SimpleNamespace(sport_key=LIGUE_1, game_date=DAY, n=2)]
_EVENTS = [
    # The production row: correct id, correct score. Proven, nothing to do.
    SimpleNamespace(
        event_id=15307704, espn_id="401876449", sport_key=LIGUE_1, ev_status="completed",
        home_team_name="Marseille", away_team_name="PSG", home_score=1, away_score=2,
        commence_time=WHEN, completed_at=datetime(2026, 9, 20, 20, 45, tzinfo=UTC),
        game_date=DAY,
    ),
    # The same id link with a FROZEN score: it must reach the score comparison.
    SimpleNamespace(
        event_id=15307705, espn_id="401876480", sport_key=LIGUE_1, ev_status="completed",
        home_team_name="Lyon", away_team_name="PSG", home_score=0, away_score=0,
        commence_time=WHEN, completed_at=datetime(2026, 9, 20, 20, 45, tzinfo=UTC),
        game_date=DAY,
    ),
]
_BOARD = [
    _game("401876449", "Marseille", "Paris Saint-Germain", 1, 2),
    _game("401876480", "Lyon", "Paris Saint-Germain", 3, 1),
]


class _Result:
    def __init__(self, rows, scalar=None):
        self._rows, self._scalar = rows, scalar

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _Session:
    """Answers the dry run's reads; any write-shaped statement is a failure."""

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "bak_7147_post_final" in sql:
            return _Result([], scalar=0)
        if "FROM score_snapshots s" in sql and "JOIN events e" in sql:
            return _Result([])
        if "GROUP BY 1, 2" in sql:
            return _Result(list(_GROUPS))
        if "unnest(" in sql:
            return _Result(list(_EVENTS))
        if "GROUP BY x.event_id" in sql:
            return _Result([])
        if "COUNT(*) AS n" in sql:
            return _Result([SimpleNamespace(n=len(_EVENTS))])
        raise AssertionError(f"unexpected SQL on a dry run: {sql[:160]}")

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_repair_threads_the_sport_key_to_the_classifier():
    from scripts import repair_event_final_scores as mod

    svc = SimpleNamespace(get_scoreboard=AsyncMock(return_value=list(_BOARD)))
    with patch("app.services.espn_api.get_espn_service", return_value=svc):
        res = await mod.repair(_Session(), False)

    by_event = {e["event_id"]: e for e in res["ledger"] if "event_id" in e}
    # The correct row is not a linkage finding at all: proven, scores agree,
    # nothing to report.
    assert 15307704 not in by_event
    assert res[ESPN_ID_DRIFTED] == 0
    assert res["identity_blocked"] == 0
    # The frozen row reached the score comparison and was named a score defect.
    assert by_event[15307705]["action"] == "fix_score"
    assert res["score_defects"] == 1

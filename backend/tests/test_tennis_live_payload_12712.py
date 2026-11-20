"""A tennis headline receives one oriented score: sets, games and points."""

from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest

from app.services.statpal_api import StatPalAPIService
from app.utils.tennis_live_score import statpal_tennis_values, attach_tennis_score
from tests.integration.test_route_events_seeded import _make_event
from tests.test_event_detail_period_scores_9067 import _payload


def fixture(*, points=("A", "40"), tb="False"):
    return StatPalAPIService.__new__(StatPalAPIService)._parse_tennis_match(
        {
            "id": "2631673",
            "status": "Set 3",
            "tb": tb,
            "player": [
                {
                    "name": "B. Van De Zandschulp",
                    "totalscore": "1",
                    "s1": "6",
                    "s2": "4",
                    "s3": "2",
                    "game_score": points[0],
                    "serve": "True",
                },
                {
                    "name": "A. De Minaur",
                    "totalscore": "1",
                    "s1": "4",
                    "s2": "6",
                    "s3": "1",
                    "game_score": points[1],
                    "serve": "False",
                },
            ],
        },
        {"id": "170", "name": "ATP"},
    )


def event():
    row = _make_event(
        home_team="Alex De Minaur",
        away_team="Botic Van De Zandschulp",
        sport_key="tennis_other",
        home_score=1,
        away_score=1,
    )
    row.statpal_fixture_id = "2631673"
    row.box_score_data = {"players": []}
    row.game_clock = None
    row.period = "Set 3"
    row.score_observed_at = None
    row.score_source = None
    return row


def test_parser_keeps_current_points_and_server():
    parsed = fixture()
    assert parsed.home_game_score == "A"
    assert parsed.away_game_score == "40"
    assert parsed.home_serving is True
    assert parsed.away_serving is False
    assert parsed.tennis_tiebreak is False


@pytest.mark.asyncio
async def test_espn_games_reach_the_existing_native_fields_without_summing_to_sets():
    row = event()
    row.statpal_fixture_id = None
    row.box_score_data["tennis"] = {
        "sets": [[4, 6], [6, 4], [1, 2]],
        "home_games": 11,
        "away_games": 12,
        "source": "espn",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    served = await _payload(row)
    assert served["box_score_data"]["home_period_scores"] == [4, 6, 1]
    assert served["box_score_data"]["away_period_scores"] == [6, 4, 2]
    assert "game_clock" not in served.get("espn", {})


def install(row, values):
    for key, value in values.items():
        setattr(row, key, value)


@pytest.mark.asyncio
async def test_reversed_fixture_serves_sets_games_points_and_server_from_one_read():
    row = event()
    now = datetime.now(timezone.utc)
    values, reason = statpal_tennis_values(row, [fixture()], now)
    assert reason is None
    install(row, values)
    served = await _payload(row)
    assert (served["home_score"], served["away_score"]) == (1, 1)
    assert served["box_score_data"]["home_period_scores"] == [4, 6, 1]
    assert served["box_score_data"]["away_period_scores"] == [6, 4, 2]
    assert served["espn"]["game_clock"] == "Ad-40"  # away, home
    assert served["linescore"]["home_points"] == "40"
    assert served["linescore"]["away_points"] == "Ad"
    assert served["linescore"]["serving"] == "away"
    assert served["linescore"]["source"] == "statpal"
    assert served["score_observed_at"] == now.isoformat()
    assert "home_name" not in served["linescore"]


def test_a_second_successful_read_of_the_same_score_advances_the_read_time():
    row = event()
    first = datetime.now(timezone.utc) - timedelta(seconds=30)
    values, reason = statpal_tennis_values(row, [fixture()], first)
    assert reason is None
    install(row, values)
    second = first + timedelta(seconds=30)
    newer, reason = statpal_tennis_values(row, [fixture()], second)
    assert reason is None
    assert newer["box_score_data"]["tennis"]["observed_at"] == second.isoformat()
    assert newer["score_observed_at"] == second
    assert (
        newer["box_score_data"]["tennis"]["sets"]
        == values["box_score_data"]["tennis"]["sets"]
    )


@pytest.mark.parametrize(
    "age,status", [(121, "live"), (-1, "live"), (0, "completed"), (0, "scheduled")]
)
def test_old_future_or_nonlive_points_are_not_served(age, status):
    row = event()
    now = datetime.now(timezone.utc)
    values, _ = statpal_tennis_values(row, [fixture()], now - timedelta(seconds=age))
    install(row, values)
    response = {
        "status": status,
        "home_score": 1,
        "away_score": 1,
        "espn": {"game_clock": "Ad-40"},
    }
    attach_tennis_score(row, response, now)
    assert "home_points" not in response["linescore"]
    assert "serving" not in response["linescore"]
    assert "game_clock" not in response["espn"]
    assert response["box_score_data"]["home_period_scores"] == [4, 6, 1]


@pytest.mark.parametrize(
    "points,tb",
    [
        (("", "40"), "False"),
        (("A", "A"), "False"),
        (("7", "3"), "False"),
        (("40", "15"), ""),
    ],
)
def test_partial_or_unexplained_points_do_not_borrow_an_older_point(points, tb):
    values, reason = statpal_tennis_values(
        event(), [fixture(points=points, tb=tb)], datetime.now(timezone.utc)
    )
    assert reason is None
    assert "home_points" not in values["box_score_data"]["tennis"]


def test_numeric_tiebreak_points_stay_explicit_not_a_fake_native_clock():
    row = event()
    now = datetime.now(timezone.utc)
    values, _ = statpal_tennis_values(row, [fixture(points=("7", "3"), tb="True")], now)
    install(row, values)
    response = {"status": "live", "home_score": 1, "away_score": 1}
    attach_tennis_score(row, response, now)
    assert response["linescore"]["home_points"] == "3"
    assert response["linescore"]["away_points"] == "7"
    assert response["linescore"]["tiebreak"] is True
    assert "game_clock" not in response.get("espn", {})


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"fixture_id": "other"}, "fixture-absent"),
        ({"home_team": "C. Alcaraz"}, "orientation-unresolved"),
        ({"status": "scheduled"}, "not-live"),
        ({"home_q_scores": {"s1": 6, "s3": 2}}, "set-line-incomplete"),
        ({"home_score": 2}, "set-score-disagrees"),
        ({"away_q_scores": {"s1": 4, "s2": 6, "s3": -1}}, "set-score-disagrees"),
    ],
)
def test_an_unverified_fixture_refuses_with_a_reason(change, reason):
    assert statpal_tennis_values(
        event(), [replace(fixture(), **change)], datetime.now(timezone.utc)
    ) == ({}, reason)


def test_duplicate_anchor_no_anchor_and_later_read_are_refused():
    row = event()
    now = datetime.now(timezone.utc)
    assert (
        statpal_tennis_values(row, [fixture(), fixture()], now)[1]
        == "fixture-ambiguous"
    )
    row.statpal_fixture_id = None
    assert statpal_tennis_values(row, [fixture()], now)[1] == "no-statpal-anchor"
    row.statpal_fixture_id = "2631673"
    values, _ = statpal_tennis_values(row, [fixture()], now)
    install(row, values)
    assert (
        statpal_tennis_values(row, [fixture()], now - timedelta(seconds=1))[1]
        == "newer-observation-held"
    )


def test_a_behind_board_cannot_roll_back_games_within_the_same_set():
    row = event()
    now = datetime.now(timezone.utc)
    values, _ = statpal_tennis_values(row, [fixture()], now - timedelta(seconds=30))
    install(row, values)
    old = replace(fixture(), home_q_scores={"s1": 6, "s2": 4, "s3": 1})
    assert statpal_tennis_values(row, [old], now)[1] == "games-behind"


def test_detail_cache_does_not_extend_a_point_scores_lifetime():
    from app.routes.events import _cached_detail_payload, _event_detail_cache

    row = event()
    now = datetime.now(timezone.utc)
    values, _ = statpal_tennis_values(row, [fixture()], now - timedelta(seconds=119))
    install(row, values)
    response = {"status": "live", "home_score": 1, "away_score": 1}
    attach_tennis_score(row, response, now)
    _event_detail_cache[row.id] = (now.timestamp(), "live", response)
    try:
        assert _cached_detail_payload(row.id, now.timestamp()) is response
        assert _cached_detail_payload(row.id, now.timestamp() + 2) is None
    finally:
        _event_detail_cache.pop(row.id, None)


@pytest.mark.parametrize("change", ["anchor", "score", "names"])
def test_relinked_or_disagreeing_snapshot_cannot_reach_the_reader(change):
    row = event()
    now = datetime.now(timezone.utc)
    values, _ = statpal_tennis_values(row, [fixture()], now)
    install(row, values)
    response = {"status": "live", "home_score": 1, "away_score": 1}
    if change == "anchor":
        row.statpal_fixture_id = "other"
    elif change == "score":
        response["home_score"] = 2
    else:
        row.home_team_name = "Carlos Alcaraz"
    attach_tennis_score(row, response, now)
    assert "linescore" not in response
    assert "box_score_data" not in response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sport_key", ["tennis_other", "tennis_atp", "tennis_atp_us_open"]
)
@pytest.mark.parametrize("race", [None, "status", "box_score_data"])
async def test_scheduled_poll_uses_the_tennis_door_and_writes_one_atomic_snapshot(
    monkeypatch, sport_key, race
):
    from sqlalchemy import create_engine, event as sa_event, select, update
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
    from sqlalchemy.orm import Session
    import app.services.statpal_api as api
    import app.tasks.statpal_sync as sync
    from app.models.models import Base, Event, Sport, ScoreSnapshot

    monkeypatch.setattr(
        SQLiteTypeCompiler,
        "visit_JSONB",
        lambda self, type_, **kw: "JSON",
        raising=False,
    )
    monkeypatch.setattr(
        SQLiteTypeCompiler,
        "visit_ARRAY",
        lambda self, type_, **kw: "JSON",
        raising=False,
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Sport.__table__, Event.__table__, ScoreSnapshot.__table__]
    )
    db = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(db, "loaded_as_persistent")
    def utc(_session, instance):
        for key, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[key] = value.replace(tzinfo=timezone.utc)

    sport = Sport(key=sport_key, name="Tennis")
    db.add(sport)
    db.flush()
    row = Event(
        sport_id=sport.id,
        home_team_name="Alex De Minaur",
        away_team_name="Botic Van De Zandschulp",
        status="live",
        commence_time=datetime.now(timezone.utc) - timedelta(hours=1),
        home_score=1,
        away_score=1,
        statpal_fixture_id="2631673",
        box_score_data={"players": []},
    )
    db.add(row)
    db.commit()
    row_id = row.id
    calls = []

    class Context:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, statement):
            return db.execute(statement)

        async def flush(self):
            db.flush()

        async def commit(self):
            calls.append("commit")
            db.commit()

    class Service:
        async def get_live_fixtures(self, key):
            calls.append(key)
            return [fixture()]

        async def get_live_scores(self, key):
            pytest.fail("tennis used the parser that silently drops its board")

        async def close(self):
            calls.append("close")

    monkeypatch.setattr(sync, "get_task_session", Context)
    monkeypatch.setattr(api, "is_available", lambda: True)
    monkeypatch.setattr(api, "StatPalAPIService", Service)
    if race:
        import app.utils.live_state_write as writes

        original = writes.write_row_if_unmoved

        async def moved_first(session, event, values, **kwargs):
            change = (
                {"status": "completed"}
                if race == "status"
                else {"box_score_data": {"players": [{"name": "newer"}]}}
            )
            db.execute(
                update(Event)
                .where(Event.id == row_id)
                .values(**change)
                .execution_options(synchronize_session=False)
            )
            return await original(session, event, values, **kwargs)

        monkeypatch.setattr(writes, "write_row_if_unmoved", moved_first)
    result = await sync._sync_statpal_livescores()
    assert result["events_updated"] == (0 if race else 1)
    assert result["livescore_live_write_lost_race"] == (1 if race else 0)
    assert result["tennis_refused"] == {}
    assert calls == ["tennis", "commit", "close"]
    db.expire_all()
    saved = db.execute(select(Event).where(Event.id == row_id)).scalar_one()
    if race:
        assert "tennis" not in saved.box_score_data
        assert saved.score_observed_at is None
    else:
        assert saved.box_score_data["tennis"]["home_points"] == "40"
        assert saved.box_score_data["tennis"]["sets"] == [[4, 6], [6, 4], [1, 2]]
        assert saved.score_source == "statpal"
        assert saved.score_observed_at is not None
    db.close()
    engine.dispose()

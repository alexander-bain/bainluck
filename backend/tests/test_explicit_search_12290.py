"""Alex's named queries, the league table, and explicit-set route boundaries."""

from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config.major_team_search import MAJOR_TEAM_SEARCH_CASES
from app.config.team_aliases import curated_team_aliases, expand_club_short_forms
from app.routes import events as route
from app.utils.explicit_search import explicit_search
from app.utils.search_match_class import MC0_EXACT, match_class


def test_the_review_table_covers_every_current_major_league_franchise():
    assert Counter(row[0] for row in MAJOR_TEAM_SEARCH_CASES) == {
        "americanfootball_nfl": 32, "basketball_nba": 30,
        "baseball_mlb": 30, "icehockey_nhl": 32,
    }
    assert len({row[:2] for row in MAJOR_TEAM_SEARCH_CASES}) == 124


@pytest.mark.parametrize("sport,name,nickname,spelling", MAJOR_TEAM_SEARCH_CASES)
@pytest.mark.parametrize("typed", ["nickname", "spelling"])
def test_team_name_evidence_survives_recall_and_ranking(sport, name, nickname, spelling, typed):
    query = nickname if typed == "nickname" else spelling
    identity = expand_club_short_forms(query)
    card = {"id": 1, "name": name, "sport_key": sport,
            "_aliases": list(curated_team_aliases(sport, name))}
    assert route._query_names_team_card(card, query)
    assert match_class(identity, route._search_team_evidence(card, identity)) == MC0_EXACT
    # The team recall statement still sees a real name or a sport-scoped alias.
    sql = route._build_team_search_filter(identity)
    values = str(sql.compile().params).casefold()
    assert identity.casefold() in values or all(word in values for word in identity.casefold().split())


@pytest.mark.parametrize("query", ["capitols", "lightening", "canadians", "clots", "jest", "ai", "ipo"])
def test_unrelated_real_words_are_not_rewritten_as_a_team(query):
    assert expand_club_short_forms(query) == query


@pytest.mark.parametrize("typo,names", [
    ("gaints", {"New York Giants", "San Francisco Giants"}),
    ("jetts", {"New York Jets", "Winnipeg Jets"}),
    ("cardnals", {"Arizona Cardinals", "St. Louis Cardinals"}),
])
def test_shared_names_keep_both_franchises(typo, names):
    identity = expand_club_short_forms(typo)
    owners = {name for sport, name, nickname, spelling in MAJOR_TEAM_SEARCH_CASES
              if spelling == typo and nickname == identity}
    assert owners == names


@pytest.mark.parametrize("query,subject,count", [
    ("celtics next three games", "celtics", 3),
    ("Boston Celtics next 3 games", "Boston Celtics", 3),
    ("patroits next two games", "patroits", 2),
    ("who will win the super bowl", "super bowl", None),
    ("Who will win the Super Bowl?", "super bowl", None),
])
def test_explicit_scaffolds_preserve_subject_and_count(query, subject, count):
    parsed = explicit_search(query)
    assert parsed and parsed.subject == subject and parsed.next_games == count


@pytest.mark.parametrize("query", [
    "next three games", "celtics next thirty games", "celtics next three games tomorrow",
    "who will not win the super bowl", "who will win the super bowl in 2028",
    "celtics", "the next team", "super bowl commercial",
])
def test_unrecognised_qualifiers_do_not_get_stripped(query):
    assert explicit_search(query) is None


@pytest.mark.asyncio
async def test_next_three_route_scopes_both_fixture_sides_before_the_window(monkeypatch):
    from tests.integration.test_route_search_intent_5688 import _Recorder, _empty_result, _client_for

    recorder = _Recorder()
    team = SimpleNamespace(
        id=123, name="Boston Celtics", slug="boston-celtics", abbreviation="BOS",
        logo_url_small=None, current_record=None, sport_key="basketball_nba",
        standings_updated_at=None, alternate_names=["Celtics"], team_rank=1,
    )

    async def execute(stmt, *args, **kwargs):
        sql = recorder.record(stmt)
        result = _empty_result()
        if " teams" in sql and "SELECT" in sql.upper():
            result.all.return_value = [team]
        return result

    db = AsyncMock()
    db.execute.side_effect = execute
    monkeypatch.setattr(route, "search_response_cache_enabled", lambda: False)
    async for client in _client_for(db, monkeypatch):
        response = await client.get("/api/events/search", params={"q": "celtics next three games"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["game_set"]["selector"] == {"team_id": 123, "count": 3, "state": "scheduled"}
    assert data["game_set"]["title"] == "Boston Celtics: next 3 games"
    assert data["futures"] == [] and data["collections"] == []
    assert not data["pagination"]["has_next"]
    fixture_reads = [(sql, params) for sql, params in recorder.statements
                     if "SELECT events.id," in sql and "LIMIT" in sql]
    assert fixture_reads
    for sql, params in fixture_reads:
        assert "events.home_team_id" in sql and "events.away_team_id" in sql
        assert "events.commence_time >" in sql and "events.status =" in sql
        assert 123 in params.values() and "scheduled" in params.values()
        assert "ORDER BY events.commence_time ASC, events.id ASC" in sql
    assert not any("three" in value or "games" == value
                   for value in recorder.team_values())


@pytest.mark.asyncio
async def test_super_bowl_question_reaches_title_recall_and_keeps_the_typed_query(monkeypatch):
    from tests.integration.test_route_search_intent_5688 import _Recorder, _make_seeded_db, _client_for

    recorder = _Recorder()
    monkeypatch.setattr(route, "search_response_cache_enabled", lambda: False)
    query = "who will win the super bowl"
    async for client in _client_for(_make_seeded_db(recorder), monkeypatch):
        response = await client.get("/api/events/search", params={"q": query})
    assert response.status_code == 200, response.text
    assert response.json()["query"] == query
    values = recorder.futures_values()
    assert any("super" in value and "bowl" in value for value in values)
    assert not any(value.strip("%") in {"who", "will", "win"} for value in values)

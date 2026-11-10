"""NFL Cardinals outcomes use Arizona even when a stale category says baseball.

The task runs against real tables via the existing SQLite dialect shim. Only
the task session and cursor store are replaced; production selectors and
matching run unchanged. Stored poison is deliberately outside this prevention.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport, Team
from app.tasks import team_linking
from app.tasks.polymarket import _tags_to_category, resolve_event_category
from tests.test_team_link_drain_advances_7307 import (
    _AsyncShim, _FakeCursorStore, _make_engine,
)


@pytest.mark.parametrize("tag", ["NFL", "NFL (All)", " nfl (all) "])
def test_venue_nfl_identity_outranks_the_cardinals_title(tag):
    category, sport = _tags_to_category(["Sports", tag, "Games"])
    result = resolve_event_category(category, sport, "Rams vs. Cardinals", ["Rams vs. Cardinals"])
    assert result[:2] == ("championship", "football")


def test_baseball_and_absent_tag_controls_keep_their_meaning():
    for tags in (["Sports", "MLB", "Games"], ["Sports", "Games"]):
        category, sport = _tags_to_category(tags)
        result = resolve_event_category(category, sport, "Rams vs. Cardinals", ["Rams vs. Cardinals"])
        assert result[:2] == ("championship", "baseball")


def _seed(session, *, sport_id=1, home_id=541, away_id=544, event=True):
    session.add_all([
        Sport(id=1, key="americanfootball_nfl", name="NFL", active=True),
        Sport(id=2, key="baseball_mlb", name="MLB", active=True),
        Team(id=541, sport_id=1, name="Arizona Cardinals", alternate_names=["Cardinals"],
             roster_players=[{"name": "Kyler Murray"}]),
        Team(id=544, sport_id=1, name="Los Angeles Rams", alternate_names=["Rams"]),
        Team(id=10740, sport_id=2, name="St. Louis Cardinals", alternate_names=["Cardinals", "St. Louis"],
             roster_players=[{"name": "Nolan Arenado"}]),
        Team(id=10741, sport_id=2, name="Chicago Cubs", alternate_names=["Cubs"]),
    ])
    if event:
        session.add(Event(
            id=14781145, sport_id=sport_id,
            home_team_id=home_id, away_team_id=away_id,
            home_team_name="Arizona Cardinals" if sport_id == 1 else "St. Louis Cardinals",
            away_team_name="Los Angeles Rams" if sport_id == 1 else "Chicago Cubs",
            commence_time=datetime(2026, 11, 15, 21, tzinfo=timezone.utc),
        ))
    # The observed stale classification is retained to make tag-only fixes fail.
    session.add(FuturesMarket(
        id=67649495, source="polymarket", external_id="123456",
        name="Rams vs. Cardinals", category="championship", llm_sport_category="baseball",
        status="open", market_tier=1, event_id=14781145 if event else None,
        market_metadata={"polymarket_event_slug": "nfl-la-ari-2026-11-15"},
    ))
    session.flush()
    for oid, name, stored in [
        (1, "Cardinals", None), (2, "Cardinals O/U 19.5", None),
        (3, "Rams", None), (4, "Kyler Murray", None),
        (5, "Chicago Cubs", None), (6, "Nolan Arenado", None),
        (7, "Unknown Player", None), (8, "Cardinals", 10740),
    ]:
        session.add(FuturesOutcome(id=oid, market_id=67649495, external_id=str(oid), name=name, team_id=stored))
    session.commit()


def _run(session, *, use_llm=False):
    @asynccontextmanager
    async def task_session():
        yield _AsyncShim(session)

    with patch.object(team_linking, "get_task_session", task_session), \
            patch.object(team_linking, "_cursor_store", _FakeCursorStore):
        stats = asyncio.run(team_linking._backfill_team_links(limit=100, use_llm=use_llm))
    assert stats["errors"] == []
    assert stats["units_rolled_back"] == []
    session.flush()
    return dict(session.execute(select(FuturesOutcome.id, FuturesOutcome.team_id)).all()), stats


def test_names_and_rosters_bind_to_fixture_while_unrelated_clubs_and_stored_poison_stay_out():
    with Session(_make_engine()) as session:
        _seed(session)
        links, stats = _run(session)
    assert links == {1: 541, 2: 541, 3: 544, 4: 541, 5: None, 6: None, 7: None, 8: 10740}
    assert stats["outcomes_refused_outside_event_teams"] >= 2


def test_llm_cannot_reintroduce_an_outside_fixture_club():
    wrong_guess = AsyncMock(return_value=10740)
    with Session(_make_engine()) as session, patch.object(team_linking, "link_outcome_to_team", wrong_guess):
        _seed(session)
        links, stats = _run(session, use_llm=True)
    assert wrong_guess.await_count > 0
    assert links[7] is None
    assert links[1] == 541
    assert stats["outcomes_refused_outside_event_teams"] > 2


def test_mlb_fixture_still_selects_the_baseball_cardinals():
    with Session(_make_engine()) as session:
        _seed(session, sport_id=2, home_id=10740, away_id=10741)
        links, _ = _run(session)
    assert links == {1: 10740, 2: 10740, 3: None, 4: None, 5: 10741, 6: 10740, 7: None, 8: 10740}


def test_partial_fixture_does_not_authorize_a_different_club():
    with Session(_make_engine()) as session:
        _seed(session, away_id=None)
        links, _ = _run(session)
    assert links[1] == 541
    assert links[2] == 541
    assert links[5] is None
    assert links[6] is None


def test_wrong_sport_fixture_ids_cannot_authorize_category_fallback():
    with Session(_make_engine()) as session:
        _seed(session, sport_id=1, home_id=10740, away_id=10741)
        links, stats = _run(session)
    assert all(links[oid] is None for oid in range(1, 8))
    assert links[8] == 10740  # Already-linked data still belongs to the repair.
    assert stats["outcomes_refused_outside_event_teams"] > 0


def test_same_sport_names_resolve_fixture_without_team_foreign_keys():
    with Session(_make_engine()) as session:
        _seed(session, home_id=None, away_id=None)
        links, _ = _run(session)
    assert links[1] == 541
    assert links[2] == 541
    assert links[3] == 544
    assert links[5] is None


def test_no_fixture_keeps_the_existing_category_path():
    with Session(_make_engine()) as session:
        _seed(session, event=False)
        links, _ = _run(session)
    assert links[1] == 10740
    assert links[2] == 10740
    assert links[5] == 10741

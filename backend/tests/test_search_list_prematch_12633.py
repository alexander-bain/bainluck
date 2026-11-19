"""Finished search/list cards carry the detail page's kickoff-bounded chance."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import events as route
from app.utils import prematch_reading
from app.utils.proven_duplicates import FoldedCardNumbers
from app.utils.settled_prematch_batch import settled_prematch_odds_by_event
from tests.test_pregame_projection_routes_11296 import _event, _search_db

pytestmark = pytest.mark.usefixtures("offline_redis_no_retry_sleep")
SPECIMEN = 14639206


def game(eid=SPECIMEN, status="completed", home="Detroit Lions"):
    row = _event(eid, status=status, home=home)
    row.commence_time = datetime.now(timezone.utc) - timedelta(hours=20)
    row.completed_at = row.commence_time + timedelta(hours=3) if status == "completed" else None
    row.opening_home_probability, row.opening_away_probability = .5765, .4235
    return row


def reading(eid=SPECIMEN, source="kalshi", home=.575, *, after=False):
    return SimpleNamespace(
        event_id=eid, source=source, home_win_probability=home,
        away_win_probability=1 - home, draw_probability=None,
        after=after,
    )


class Session:
    def __init__(self, events, rows=(), fail=False):
        self.base = _search_db(events, [], [])
        self.rows, self.fail = rows, fail
        self.calls, self.timeouts, self.savepoints = [], [], []

    def __getattr__(self, name):
        return getattr(self.base, name)

    async def begin_nested(self):
        point = AsyncMock()
        self.savepoints.append(point)
        return point

    async def execute(self, statement, *args, **kwargs):
        sql = " ".join(str(statement).split())
        if sql == " ".join(prematch_reading.prematch_prior_sql().split()):
            binds = args[0]
            self.calls.append(binds)
            if self.fail:
                raise RuntimeError("statement timeout")
            # Model the SQL's <= kickoff selection, not the later live price.
            return SimpleNamespace(all=lambda: [
                r for r in self.rows if r.event_id in binds["ids"] and not r.after
            ])
        if "statement_timeout" in sql:
            self.timeouts.append(sql)
        return await self.base.execute(statement, *args, **kwargs)


@pytest.fixture
def serve(monkeypatch):
    monkeypatch.setattr(route, "_load_gei_percentiles", AsyncMock(return_value={}))
    monkeypatch.setattr(route, "_build_team_lookup", AsyncMock(return_value={}))
    monkeypatch.setattr(route, "_record_trending", MagicMock())
    rc = MagicMock()
    rc.get.return_value = None
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: rc)

    async def run(door, events, rows=(), *, fail=False, folded=None, settled=False):
        numbers = folded or {
            e.id: FoldedCardNumbers({}, (e.opening_home_probability, e.opening_away_probability))
            for e in events
        }
        monkeypatch.setattr(route, "folded_card_numbers_batch", AsyncMock(return_value=numbers))
        if settled:
            async def venue_verdict(db, events, formatted, now):
                for row in formatted:
                    row["status"] = "completed"
            monkeypatch.setattr(route, "attach_venue_settlement", venue_verdict)
        session = Session(events, rows, fail=fail)
        if door == "search":
            payload = await route.search_events(
                request=MagicMock(), response=MagicMock(), q="lions", db=session,
                sport=None, tags=None, page=1, per_page=25, days_back=30,
                include_upcoming=True, debug_timing=False, current_user=None,
            )
            cards = payload["results"]
        else:
            payload = await route.list_events(
                db=session, sport=None, status=None, days=7, past_days=7, limit=200, offset=0,
            )
            cards = payload["events"]
        return {r["id"]: r for r in cards}, session
    return run


@pytest.mark.parametrize("door", ["search", "list"])
@pytest.mark.parametrize("rows,source,home", [
    ([reading(), reading(home=.99, after=True)], "kalshi", .575),
    ([reading(source="polymarket", home=.47)], "polymarket", .47),
    ([reading(source="polymarket", home=.47), reading(home=.555)], "kalshi", .555),
    ([], "books", .5765),
])
async def test_finished_card_matches_detail_not_opening_or_live(serve, door, rows, source, home):
    event = game()
    cards, session = await serve(door, [event], rows)
    prior = cards[SPECIMEN]["prematch_odds"]
    assert prior == await route._settled_prematch_odds(Session([event], rows), event, "americanfootball_nfl")
    assert prior["source"] == source and prior["home_probability"] == home
    assert prior["home_rendered_percent"] + prior["away_rendered_percent"] == 100
    for field, probability in (("source_mark", home), ("away_source_mark", 1 - home)):
        quote, = prior[field]["sources"]
        assert quote["key"] == ("betting" if source == "books" else source)
        assert quote["probability"] == pytest.approx(probability)
        assert quote["observed_at"] is None
    assert len(session.calls) == 1
    assert session.calls[0]["cutoffs"] == [event.commence_time]


@pytest.mark.parametrize("door", ["search", "list"])
async def test_served_settlement_selects_the_prior(serve, door):
    event = game(status="suspended")
    cards, session = await serve(door, [event], [reading()], settled=True)
    assert cards[SPECIMEN]["prematch_odds"]["home_rendered_percent"] == 58
    assert session.calls[0]["ids"] == [SPECIMEN]
    assert event.status == "suspended"  # no stored-row mutation


@pytest.mark.parametrize("door", ["search", "list"])
async def test_one_bounded_read_for_all_finals_and_no_prior_on_unfinished(serve, door):
    events = [game(), game(SPECIMEN + 1, home="Chicago Bears"),
              game(SPECIMEN + 2, "scheduled", "Dallas Cowboys"),
              game(SPECIMEN + 3, "live", "Arizona Cardinals")]
    events[2].commence_time += timedelta(days=2)
    cards, session = await serve(door, events, [reading(), reading(SPECIMEN + 1, home=.35)])
    assert len(session.calls) == 1
    assert set(session.calls[0]["ids"]) == {SPECIMEN, SPECIMEN + 1}
    assert cards[SPECIMEN + 1]["prematch_odds"]["home_rendered_percent"] == 35
    assert "prematch_odds" not in cards[SPECIMEN + 2]
    assert "prematch_odds" not in cards[SPECIMEN + 3]
    assert "SET LOCAL statement_timeout = '1500ms'" in session.timeouts
    assert any(s.rollback.await_count and not s.commit.await_count for s in session.savepoints)


@pytest.mark.parametrize("door", ["search", "list"])
async def test_failed_read_preserves_cards_and_books(serve, door):
    cards, session = await serve(door, [game()], [reading()], fail=True)
    assert cards[SPECIMEN]["prematch_odds"]["source"] == "books"
    assert cards[SPECIMEN]["opening_odds"]["home_probability"] == .5765
    assert len(session.calls) == 1


@pytest.mark.parametrize("door", ["search", "list"])
async def test_unfinished_page_never_reads_prior(serve, door):
    cards, session = await serve(door, [game(status="live")], [reading()])
    assert "prematch_odds" not in cards[SPECIMEN]
    assert session.calls == []


@pytest.mark.parametrize("door", ["search", "list"])
async def test_folded_history_keeps_survivor_cutoff_and_source_precedence(serve, door):
    event = game()
    twins = [SPECIMEN + 2, SPECIMEN + 1]
    numbers = {SPECIMEN: FoldedCardNumbers({}, (.5765, .4235), tuple(twins))}
    rows = [reading(twins[0], home=.9), reading(twins[1], home=.555),
            reading(source="polymarket", home=.45)]
    cards, session = await serve(door, [event], rows, folded=numbers)
    assert cards[SPECIMEN]["prematch_odds"]["home_probability"] == .555
    assert session.calls[0]["ids"] == [SPECIMEN, *sorted(twins)]
    assert session.calls[0]["cutoffs"] == [event.commence_time] * 3
    prematch_reading._reset_prematch_cache_for_tests()
    page = await route._settled_prematch_odds(
        Session([event], rows), event, "americanfootball_nfl",
        absorbed=[SimpleNamespace(id=eid) for eid in sorted(twins)],
    )
    assert cards[SPECIMEN]["prematch_odds"] == page


async def test_exhausted_budget_uses_books_without_query():
    event = game()
    session = Session([event], [reading()])
    prior = await settled_prematch_odds_by_event(session, [event], timeout_ms=0)
    assert prior[SPECIMEN]["source"] == "books"
    assert session.calls == [] and session.savepoints == []


@pytest.mark.parametrize("door", ["search", "list"])
async def test_own_reading_wins_and_missing_books_can_come_from_proven_twin(serve, door):
    event = game()
    event.opening_home_probability = event.opening_away_probability = None
    twin = SPECIMEN + 1
    numbers = {SPECIMEN: FoldedCardNumbers({}, (.6, .4), (twin,))}
    cards, _ = await serve(door, [event], [reading(twin, home=.9), reading()], folded=numbers)
    assert cards[SPECIMEN]["prematch_odds"]["home_probability"] == .575
    prematch_reading._reset_prematch_cache_for_tests()
    cards, _ = await serve(door, [event], [], folded=numbers)
    assert cards[SPECIMEN]["prematch_odds"]["source"] == "books"
    assert cards[SPECIMEN]["prematch_odds"]["home_probability"] == .6


@pytest.mark.parametrize("door", ["search", "list"])
async def test_no_prior_is_not_a_fabricated_probability(serve, door):
    event = game()
    event.opening_home_probability = event.opening_away_probability = None
    cards, _ = await serve(door, [event])
    assert SPECIMEN in cards and "prematch_odds" not in cards[SPECIMEN]


@pytest.mark.parametrize("door", ["search", "list"])
async def test_in_page_fold_keeps_the_removed_rows_pregame_reading(serve, door):
    canonical, twin = game(), game(SPECIMEN + 1)
    canonical.espn_id = "fixture-12633"
    twin.commence_time = canonical.commence_time
    cards, session = await serve(door, [canonical, twin], [reading(twin.id, home=.61)])
    assert set(cards) == {canonical.id}
    assert cards[canonical.id]["prematch_odds"]["home_probability"] == .61
    assert session.calls[0]["ids"] == [canonical.id, twin.id]


async def test_cancellation_rolls_back_and_propagates(monkeypatch):
    session = Session([game()])
    monkeypatch.setattr(
        "app.utils.settled_prematch_batch.fetch_prematch_prior_rows",
        AsyncMock(side_effect=asyncio.CancelledError),
    )
    with pytest.raises(asyncio.CancelledError):
        await settled_prematch_odds_by_event(session, [game()], timeout_ms=100)
    session.savepoints[0].rollback.assert_awaited_once()
    session.savepoints[0].commit.assert_not_awaited()

"""#7221 / #12824: detail and cards never revive a refused current chance.

Raw snapshot metadata remains available, but historical or thin-book prices
cannot replace an absent aggregate. The real ASGI route and list formatter
must agree, and admitted sources remain unchanged.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.models.models import Event, Sport
from app.routes import events as events_route
from app.services.database import get_db, get_db_rw
from app.utils.aggregation import TIER_ESPN, TIER_OPENING, TIER_SOURCES
from app.utils.current_odds_probability import current_odds_probability

EVENT_ID = 15314578
HOME = "Uganda"
AWAY = "Kenya"
# NOT `SPORT_KEY`: gitleaks' `generic-api-key` rule fires on a high-entropy
# string assigned to a name ending in `_KEY` and reds the whole check-run
# (measured on `2eba21bdc`, finding at this line). It is a sport key, not a
# credential — renaming beats an ignore entry, which would weaken the scanner
# for a real one.
SPORT = "cricket_international_t20"

# The production reading this file was written from.
OPENING = 0.6414  # `opening_home_probability`, and what the object served
BOOK = 0.044  # fanduel, the one book the object counted and stamped
BLEND = 0.5905  # a real Tier-1 reading, from 15312047 the same minute


def _offset(hours: float) -> datetime:
    """Anchor OFFSET FIRST, never truncated after (gotcha #44)."""
    return datetime.now(timezone.utc) + timedelta(hours=hours)


# ── THE HELPER ───────────────────────────────────────────────────────────────


class TestTheHelper:
    """`current_odds_probability` — the whole decision, in one place."""

    def test_a_historical_tier_is_refused_even_with_a_snapshot(self):
        assert current_odds_probability(OPENING, TIER_OPENING, BOOK, "live") is None

    @pytest.mark.parametrize("status", ["scheduled", "completed", "closed", "suspended"])
    def test_every_status_refuses_a_historical_tier(self, status):
        """A historical line cannot answer in any state."""
        assert current_odds_probability(OPENING, TIER_OPENING, BOOK, status) is None

    @pytest.mark.parametrize("tier", [TIER_SOURCES, TIER_ESPN])
    def test_a_real_multi_source_reading_is_untouched(self, tier):
        assert current_odds_probability(BLEND, tier, BOOK, "live") == BLEND

    def test_without_a_consensus_the_opening_stays_absent(self):
        """An old number is not a current chance."""
        assert current_odds_probability(OPENING, TIER_OPENING, None, "live") is None

    def test_no_aggregate_cannot_reenter_through_raw_snapshots(self):
        """Raw snapshots cannot undo source admission."""
        assert current_odds_probability(None, None, BOOK, "live") is None

    def test_nothing_anywhere_is_none(self):
        assert current_odds_probability(None, None, None, "live") is None


# ── SITE 2: THE CARD ─────────────────────────────────────────────────────────


def _event(status: str = "live", bag: dict | None = None) -> Event:
    event = Event(
        id=EVENT_ID,
        sport_id=1,
        home_team_name=HOME,
        away_team_name=AWAY,
        commence_time=_offset(-3),
        status=status,
        win_probability_sources=(
            bag if bag is not None else {"betting_book_count": 1}
        ),
    )
    event.opening_home_probability = OPENING
    event.opening_away_probability = round(1.0 - OPENING, 4)
    event.opening_favorite = "home"
    event.opening_home_spread = None
    event.opening_over_under = None
    event.espn_win_prob_home = None
    event.home_score = None
    event.away_score = None
    event.sport = Sport(id=1, key=SPORT, name="Cricket")
    return event


def _odds_data(home_prob: float | None = BOOK) -> dict:
    """The shape `_format_event_with_aggregated_odds` reads for `current_odds`."""
    return {
        "aggregated": {
            "home_probability": home_prob,
            "away_probability": (
                round(1.0 - home_prob, 6) if home_prob is not None else None
            ),
            "home_spread": None,
            "over_under": None,
            "projected_home_score": None,
            "projected_away_score": None,
            "bookmaker_count": 1,
        },
        "captured_at": _offset(-0.001),
        "snapshots": [],
    }


class TestTheCardArm:
    """`_format_event_with_aggregated_odds` — `/api/events` and `/search`.

    This is the arm a reader meets. The detail page cross-checks `current_odds`
    against the chart's own series and overrides it past five points;
    `EventCard` has no history to cross-check against and prints this number
    flat, so on the card the defect has no escape hatch at all.
    """

    def test_a_live_card_does_not_revive_the_opening_or_refused_book(self):
        served = events_route._format_event_with_aggregated_odds(
            _event(), _odds_data()
        )["current_odds"]
        assert served["home_probability"] is None
        # The defect itself: the live figure and the pre-match figure were one
        # number. They must not be again.
        assert served["home_probability"] != OPENING

    def test_the_away_leg_is_absent_when_the_home_leg_is_absent(self):
        served = events_route._format_event_with_aggregated_odds(
            _event(), _odds_data()
        )["current_odds"]
        assert served["away_probability"] is None

    def test_the_rest_of_the_object_is_the_snapshots_as_before(self):
        served = events_route._format_event_with_aggregated_odds(
            _event(), _odds_data()
        )["current_odds"]
        assert served["bookmaker_count"] == 1
        assert served["captured_at"] is not None

    @pytest.mark.parametrize("status", ["scheduled", "completed", "suspended"])
    def test_other_states_also_refuse_the_old_opening_chance(self, status):
        served = events_route._format_event_with_aggregated_odds(
            _event(status=status), _odds_data()
        )["current_odds"]
        assert served["home_probability"] is None

    def test_a_real_blend_still_beats_the_single_book(self):
        """Ruling 051 is not loosened: this row HAS a consensus, and it wins."""
        bag = {
            "betting": {"value": BLEND, "updated_at": _offset(-0.01).isoformat()},
            "betting_book_count": 9,
        }
        served = events_route._format_event_with_aggregated_odds(
            _event(bag=bag), _odds_data()
        )["current_odds"]
        assert served["home_probability"] == BLEND

    def test_with_no_book_consensus_the_card_has_no_current_chance(self):
        served = events_route._format_event_with_aggregated_odds(
            _event(), _odds_data(home_prob=None)
        )["current_odds"]
        assert served["home_probability"] is None


class TestTheRankingDoesNotScoreAnOldOpening:
    """An opening-only event must not be ranked as if it had a current chance."""

    def test_compute_highlight_does_not_score_a_historical_current_chance(self):
        with patch.object(
            events_route, "compute_highlight", wraps=events_route.compute_highlight
        ) as spy:
            events_route._format_event_with_aggregated_odds(_event(), _odds_data())
        assert spy.call_args.kwargs["current_home_prob"] is None
        assert spy.call_args.kwargs["current_home_prob"] != BOOK

    def test_raw_snapshot_presence_does_not_change_the_score(self):
        """Only the admitted chance can affect current-price scoring."""
        with_fix = events_route._format_event_with_aggregated_odds(
            _event(), _odds_data()
        )
        no_consensus = events_route._format_event_with_aggregated_odds(
            _event(), _odds_data(home_prob=None)
        )
        assert with_fix["highlight"]["score"] == no_consensus["highlight"]["score"]


# ── SITE 1: THE DETAIL ROUTE, END TO END ─────────────────────────────────────


def _snapshot(prob: float, *, bookmaker: str = "fanduel") -> MagicMock:
    snap = MagicMock()
    snap.bookmaker = bookmaker
    snap.home_win_probability = prob
    snap.away_win_probability = round(1.0 - prob, 4)
    snap.captured_at = _offset(-0.002)
    snap.valid_until = _offset(-0.001)
    snap.home_moneyline = -110
    snap.away_moneyline = -110
    snap.home_spread = None
    snap.over_under = None
    snap.projected_home_score = None
    snap.projected_away_score = None
    return snap


def _detail_event(bag: dict | None = None) -> MagicMock:
    event = MagicMock()
    event.id = EVENT_ID
    event.external_id = f"ext-{EVENT_ID}"
    event.home_team_name = HOME
    event.away_team_name = AWAY
    event.status = "live"
    event.sport_key = SPORT
    event.sport_id = 1
    event.sport = MagicMock()
    event.sport.key = SPORT
    event.sport.name = "Cricket"
    event.commence_time = _offset(-3)
    event.completed_at = None
    event.home_score = None
    event.away_score = None
    event.win_probability_sources = (
        bag if bag is not None else {"betting_book_count": 1}
    )
    event.espn_game_id = None
    event.espn_id = None
    event.espn_data = None
    event.espn_win_prob_home = None
    event.game_clock = None
    event.period = None
    event.broadcast_info = None
    event.event_tags = []
    event.pulse_score = None
    event.pulse_label = None
    event.excite_index = None
    event.raw_ei = None
    event.ei_metadata = None
    event.home_team_id = None
    event.away_team_id = None
    event.llm_gender = None
    event.llm_level = None
    event.llm_league = None
    event.llm_importance = None
    event.opening_home_probability = OPENING
    event.opening_away_probability = round(1.0 - OPENING, 4)
    event.opening_favorite = "home"
    event.opening_home_spread = None
    event.opening_over_under = None
    event.box_score_data = None
    return event


def _detail_session(event, snapshots):
    session = AsyncMock()

    def _aggregate_of_nothing(result):
        """`.one()` on an un-configured MagicMock iterates EMPTY, not raises.

        `_pinned_live_probability` unpacks five columns out of `.one()`, so a
        result object that does not answer it fails with a bare
        `ValueError: not enough values to unpack` from inside the route rather
        than with anything about this fixture. Five Nones is what the real
        aggregate returns for an event with no `win_prob_snapshots`, and the
        route's own `if not first_seen` arm then declines to pin.
        """
        result.one.return_value = (0, 0, None, None, None)
        result.one_or_none.return_value = None
        return result

    def _list(data):
        result = MagicMock()
        result.scalars.return_value.all.return_value = data or []
        result.scalars.return_value.first.return_value = data[0] if data else None
        result.scalar_one_or_none.return_value = len(data) if data else 0
        result.scalar.return_value = len(data) if data else 0
        result.fetchall.return_value = data or []
        result.all.return_value = [(r,) for r in (data or [])]
        result.first.return_value = (data[0],) if data else None
        return _aggregate_of_nothing(result)

    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    empty.scalars.return_value.first.return_value = None
    empty.scalar_one_or_none.return_value = None
    empty.scalar.return_value = None
    empty.fetchall.return_value = []
    empty.all.return_value = []
    empty.first.return_value = None
    _aggregate_of_nothing(empty)

    async def _execute(stmt, *args, **kwargs):
        text = str(stmt).lower()
        # `odds_snapshots` BEFORE `events`: the shared latest-per-bookmaker query
        # seeds from `events`, so its SQL names both tables (LAT-P107/#1605).
        if "odds_snapshots" in text:
            return _list(snapshots)
        if "events" in text:
            result = MagicMock()
            result.scalar_one_or_none.return_value = event
            result.scalars.return_value.all.return_value = [event]
            result.scalars.return_value.first.return_value = event
            result.fetchall.return_value = []
            result.all.return_value = []
            result.first.return_value = None
            return _aggregate_of_nothing(result)
        return empty

    session.execute = AsyncMock(side_effect=_execute)
    session.begin_nested = MagicMock(return_value=AsyncMock())
    return session


@pytest.fixture
async def detail_client_factory():
    from app.main import app
    from app.routes.events import _event_detail_cache, _game_markets_cache

    clients = []

    async def _build(bag=None, book=BOOK, *, event=None, snapshots=None):
        _game_markets_cache.clear()
        _event_detail_cache.clear()
        session = _detail_session(
            event if event is not None else _detail_event(bag=bag),
            snapshots if snapshots is not None else [_snapshot(book)],
        )

        async def _mock_get_db():
            yield session

        async def _mock_user():
            return None

        app.dependency_overrides[get_db] = _mock_get_db
        app.dependency_overrides[get_db_rw] = _mock_get_db
        app.dependency_overrides[get_optional_user] = _mock_user
        ac = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(ac)
        return ac

    with patch("app.main.init_db", new_callable=AsyncMock):
        yield _build

    for ac in clients:
        await ac.aclose()
    _game_markets_cache.clear()
    _event_detail_cache.clear()
    app.dependency_overrides.clear()


class TestTheDetailArm:
    """`GET /api/events/{id}` — the served payload, not the helper."""

    async def test_the_served_payload_has_no_current_chance_from_a_refused_book(self, detail_client_factory):
        client = await detail_client_factory()
        resp = await client.get(f"/api/events/{EVENT_ID}")
        assert resp.status_code == 200
        current = resp.json()["current_odds"]
        assert current["home_probability"] is None
        assert current["home_probability"] != OPENING

    async def test_raw_book_evidence_keeps_its_own_number_and_stamp(
        self, detail_client_factory
    ):
        """Quote evidence survives without licensing the current chance."""
        client = await detail_client_factory()
        payload = (await client.get(f"/api/events/{EVENT_ID}")).json()
        current = payload["current_odds"]
        books = payload["bookmaker_odds"]
        assert len(books) == 1
        assert current["home_probability"] is None
        assert books[0]["home_probability"] == BOOK
        assert current["captured_at"] == books[0]["captured_at"]

    async def test_a_real_blend_is_still_the_detail_hero(
        self, detail_client_factory
    ):
        bag = {
            "betting": {"value": BLEND, "updated_at": _offset(-0.01).isoformat()},
            "betting_book_count": 9,
        }
        client = await detail_client_factory(bag=bag)
        payload = (await client.get(f"/api/events/{EVENT_ID}")).json()
        assert payload["current_odds"]["home_probability"] == BLEND


class TestTheTwoArmsAgree:
    """The durable one (Q441/#1495, and #6960's closing class).

    Every test above would pass again if a later edit reverted one of the two
    sites, because each asserts its own site against a constant. This asserts
    the two formatters against EACH OTHER on one row — the failure mode that
    shipped this class of defect twice.
    """

    async def test_one_row_one_number_on_both_surfaces(self, detail_client_factory):
        client = await detail_client_factory()
        detail = (await client.get(f"/api/events/{EVENT_ID}")).json()
        card = events_route._format_event_with_aggregated_odds(
            _event(), _odds_data()
        )
        assert (
            detail["current_odds"]["home_probability"]
            == card["current_odds"]["home_probability"]
        )


class TestBillsPatriotsOpening12824:
    """Two September book rows cannot become December's current chance.

    Relative dates retain the measured 68-day quote age and 19-day lead time
    through the clock sweep. The probabilities and two-book count are the
    reported Bills-at-Patriots specimen, event 15184640.
    """

    @pytest.mark.parametrize("source", [None, "espn", "kalshi"])
    async def test_detail_refuses_the_old_line_until_a_source_returns(
        self, detail_client_factory, source
    ):
        now = datetime.now(timezone.utc)
        event = _detail_event(bag={"betting_book_count": 2})
        event.id = 15184640
        event.home_team_name = "New England Patriots"
        event.away_team_name = "Buffalo Bills"
        event.sport.key = event.sport_key = "americanfootball_nfl"
        event.sport.name = "NFL"
        event.status = "scheduled"
        event.commence_time = now + timedelta(days=19)
        event.opening_home_probability = 0.5034
        event.opening_away_probability = 0.4966
        if source == "espn":
            event.espn_win_prob_home = 0.141
        elif source == "kalshi":
            event.win_probability_sources["kalshi"] = {
                "value": 0.14, "updated_at": now.isoformat(),
            }
        snapshots = [_snapshot(0.524, bookmaker="draftkings"),
                     _snapshot(0.4828, bookmaker="caesars")]
        for snap in snapshots:
            snap.captured_at = snap.valid_until = now - timedelta(days=68)
        client = await detail_client_factory(event=event, snapshots=snapshots)
        response = await client.get("/api/events/15184640")
        assert response.status_code == 200
        payload = response.json()
        expected = {None: None, "espn": 0.141, "kalshi": 0.14}[source]
        assert payload.get("hero_probability") == expected
        assert payload["current_odds"]["home_probability"] == expected
        assert payload["current_odds"]["away_probability"] == (
            None if expected is None else round(1 - expected, 6)
        )
        assert payload.get("hero_probability_source") != "opening"
        assert event.opening_home_probability == 0.5034
        assert event.opening_away_probability == 0.4966

    @pytest.mark.parametrize("status", ["scheduled", "live", "completed", "suspended"])
    def test_list_and_search_cannot_revive_raw_snapshots(self, status):
        event = _event(status=status)
        event.opening_home_probability = 0.5034
        event.opening_away_probability = 0.4966
        event.win_probability_sources = {"betting_book_count": 2}
        payload = events_route._format_event_with_aggregated_odds(
            event, _odds_data(0.5034)
        )
        assert payload.get("hero_probability") is None
        assert payload["current_odds"]["home_probability"] is None
        assert payload["current_odds"]["away_probability"] is None
        # Historical evidence remains on the stored event, including after play.
        assert event.opening_home_probability == 0.5034

    def test_a_real_zero_survives_and_a_verified_result_still_wins(self):
        event = _event(bag={"espn": {"value": 0.0}})
        payload = events_route._format_event_with_aggregated_odds(event, _odds_data())
        assert payload["current_odds"]["home_probability"] == 0.0
        assert payload["hero_probability"] == 0.0
        event.status = "completed"
        event.completed_at = _offset(-1)
        event.home_score, event.away_score = 30, 20
        payload = events_route._format_event_with_aggregated_odds(event, _odds_data())
        assert payload["hero_probability"] == 1.0
        assert payload["hero_probability_source"] == "settled"

    async def test_feed_does_not_restore_an_opening_through_historical_snapshots(self):
        from app.routes.feed import _score_events
        from app.utils.personalization import PersonalizationContext

        event = _event(status="scheduled")
        event.commence_time = _offset(2)
        event.llm_importance = "marquee"
        event.raw_ei = 90
        event.event_tags = []
        db = _detail_session(event, [])
        fallback = AsyncMock(return_value={event.id: OPENING})
        with (
            patch("app.utils.feed_snapshot_fallback.read_snapshot_fallbacks", fallback),
            patch("app.routes.feed._get_championship_probabilities", AsyncMock(return_value={})),
        ):
            absent = await _score_events(
                db, datetime.now(timezone.utc), None, PersonalizationContext(),
                my_teams_only=True, my_team_names=[HOME],
            )
            assert absent == []
            fallback.assert_not_awaited()
            event.win_probability_sources = {
                "kalshi": {"value": 0.6, "updated_at": _offset(0).isoformat()},
            }
            present = await _score_events(
                db, datetime.now(timezone.utc), None, PersonalizationContext(),
                my_teams_only=True, my_team_names=[HOME],
            )
        assert len(present) == 1
        assert present[0]["data"]["current_odds"]["home_probability"] == 0.6

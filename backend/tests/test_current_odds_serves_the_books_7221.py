"""#7221 — `current_odds` stops serving the opening line under a live stamp.

## The defect, measured on production 2026-09-19

`current_odds` is the sportsbook object: `spread`, `over_under`, the projected
scores, `bookmaker_count` and `captured_at` are all computed from the snapshot
rows the route just filtered. Its probability was not — it was
`compute_aggregate_probability`, whose Tier 3 returns `opening_home_probability`
(#6694). So on an event with no weighted source in its bag the object served the
OPENING under a stamp seconds old.

`GET /api/events/15314578` (Uganda–Kenya, cricket, live since 11:30Z), read at
14:19:20Z — one response, one microsecond:

    current_odds.home_probability   0.6414
    current_odds.captured_at        14:19:20.574177Z
    current_odds.bookmaker_count    1
    bookmaker_odds[0]               fanduel 0.044 @ 14:19:20.574177Z

    opening_odds.home_probability   0.6414     <- the same number, three hours old

`/search?q=Uganda` at 390px printed `Uganda 64% · Kenya 36%` under a green LIVE
badge with `Opened 64/36` directly beneath it. 16 live events carried the
signature at that minute; nine were more than five points from their own books'
consensus, the worst 58.19.

## What is asserted, and why in both directions

The substitution is opt-in per STATUS and per TIER, so the refusal direction is
guarded as hard as the substitution (gotcha #43). Serving a pre-game snapshot
consensus as a live price is the mirror-image defect of serving the opening:

* a **scheduled** row keeps the Tier-3 number — `Event.opening_*` is still
  rewritten on every poll until the consensus freezes (#3922), so there the
  opening IS the current price;
* a **finished** row keeps it — the card reads `opening_odds` and captions it
  "Pre-match", and settled means settled;
* a **Tier-1/Tier-2** answer is a real multi-source reading and is untouched;
* an event with **no consensus to step aside for** keeps the number it has.

`TestTheRankingDidNotMove` and `TestTheTwoArmsAgree` are the durable ones.
#6960 ruled one ship ago that this formatter's withholds happen at the serving
boundary ONLY, because `current_home_prob` feeds `compute_highlight` and moving
it would silently re-score cards; and Q441/#1495 recorded that the detail route
and the list formatter are two copies of the same lines, so a fix applied to one
of them ships half a fix.
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

    def test_a_live_tier_3_answer_steps_aside_for_the_books(self):
        assert current_odds_probability(OPENING, TIER_OPENING, BOOK, "live") == BOOK

    @pytest.mark.parametrize("status", ["scheduled", "completed", "closed", "suspended"])
    def test_every_other_status_keeps_the_number_it_has(self, status):
        """Only `live` has passed the in-play recency filter (layer 2)."""
        assert current_odds_probability(OPENING, TIER_OPENING, BOOK, status) == OPENING

    @pytest.mark.parametrize("tier", [TIER_SOURCES, TIER_ESPN])
    def test_a_real_multi_source_reading_is_untouched(self, tier):
        assert current_odds_probability(BLEND, tier, BOOK, "live") == BLEND

    def test_with_no_consensus_to_step_aside_for_the_opening_stays(self):
        """Withholding here would blank a hero; an old number beats no number."""
        assert current_odds_probability(OPENING, TIER_OPENING, None, "live") == OPENING

    def test_no_aggregate_at_all_still_falls_back_to_the_books(self):
        """The pre-existing `else` arm of the ternary, unchanged."""
        assert current_odds_probability(None, None, BOOK, "live") == BOOK

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

    def test_a_live_card_prints_the_book_not_the_opening(self):
        served = events_route._format_event_with_aggregated_odds(
            _event(), _odds_data()
        )["current_odds"]
        assert served["home_probability"] == BOOK
        # The defect itself: the live figure and the pre-match figure were one
        # number. They must not be again.
        assert served["home_probability"] != OPENING

    def test_the_away_leg_is_derived_from_the_number_actually_served(self):
        served = events_route._format_event_with_aggregated_odds(
            _event(), _odds_data()
        )["current_odds"]
        assert served["away_probability"] == round(1.0 - BOOK, 6)

    def test_the_rest_of_the_object_is_the_snapshots_as_before(self):
        served = events_route._format_event_with_aggregated_odds(
            _event(), _odds_data()
        )["current_odds"]
        assert served["bookmaker_count"] == 1
        assert served["captured_at"] is not None

    @pytest.mark.parametrize("status", ["scheduled", "completed", "suspended"])
    def test_off_the_live_state_the_payload_is_what_it_was(self, status):
        served = events_route._format_event_with_aggregated_odds(
            _event(status=status), _odds_data()
        )["current_odds"]
        assert served["home_probability"] == OPENING

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

    def test_with_no_book_consensus_the_card_keeps_its_number(self):
        served = events_route._format_event_with_aggregated_odds(
            _event(), _odds_data(home_prob=None)
        )["current_odds"]
        assert served["home_probability"] == OPENING


class TestTheRankingDidNotMove:
    """#6960's rule, applied to this ship: the serving boundary ONLY.

    `current_home_prob` feeds `compute_highlight`, which scores and orders
    cards. This is a truth fix, so the score a card carries — and therefore
    where it sits on the page — is identical before and after.
    """

    def test_compute_highlight_still_receives_the_unmoved_number(self):
        with patch.object(
            events_route, "compute_highlight", wraps=events_route.compute_highlight
        ) as spy:
            events_route._format_event_with_aggregated_odds(_event(), _odds_data())
        assert spy.call_args.kwargs["current_home_prob"] == OPENING
        assert spy.call_args.kwargs["current_home_prob"] != BOOK

    def test_the_score_itself_is_unchanged_by_the_substitution(self):
        """Belt and braces: the number the ranking sees is what it scores."""
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
    return session


@pytest.fixture
async def detail_client_factory():
    from app.main import app
    from app.routes.events import _event_detail_cache, _game_markets_cache

    clients = []

    async def _build(bag=None, book=BOOK):
        _game_markets_cache.clear()
        _event_detail_cache.clear()
        session = _detail_session(_detail_event(bag=bag), [_snapshot(book)])

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

    async def test_the_served_payload_carries_the_book(self, detail_client_factory):
        client = await detail_client_factory()
        resp = await client.get(f"/api/events/{EVENT_ID}")
        assert resp.status_code == 200
        current = resp.json()["current_odds"]
        assert current["home_probability"] == BOOK
        assert current["home_probability"] != OPENING

    async def test_the_stamp_and_the_number_now_describe_one_reading(
        self, detail_client_factory
    ):
        """The whole defect in one assertion: the object stops disagreeing with
        the book it counts and stamps."""
        client = await detail_client_factory()
        payload = (await client.get(f"/api/events/{EVENT_ID}")).json()
        current = payload["current_odds"]
        books = payload["bookmaker_odds"]
        assert len(books) == 1
        assert current["home_probability"] == books[0]["home_probability"]
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

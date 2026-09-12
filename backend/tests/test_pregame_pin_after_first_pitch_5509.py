"""#5509 — a "pregame" mark stamped after first pitch is an in-play price.

THE SPECIMEN. On 2026-09-12 the Giants–Padres page (`/events/15309667`) said THE
DIVERGENCE had these two props FALLING when both had risen:

    Samad Taylor: 1+      100% -> 84%   down 16   (really 58.5% -> 84%, up 25)
    Jackson Merrill: 2+   100% -> 85%   down 15   (really 29.5% -> 85%, up 55)

The "100%" was `market_metadata["pregame_mark"]`, pinned at 04:02:11Z for a game
that started at 02:15:00Z — 107 minutes in, by which point Taylor already had his
hit and the leg was quoted at 0.995. The correct pregame number (58.5%) was
sitting unused in `opening_probability`, because the pin takes precedence.

WHY IT IS WORTH A GATE RATHER THAN A LABEL FIX. `pregame_mark` is the RANKING
key: the consumer sets `travel = |current - pregameMark|` and orders THE
DIVERGENCE on it, so a 0.995 pinned in the sixth inning manufactures travel for a
leg that barely moved and buries the legs whose journey is the actual story.

THE POPULATION, measured on production 2026-09-12 over 7 days of pinned markets:

    pinned markets                       10,091
      pinned BEFORE commence              3,915  (38.8%)  <- keep, untouched
      pinned 0-2 min after                   30  (0.3%)   <- keep (poll jitter)
      pinned 2-5 min after                  168  (1.7%)   <- refuse
      pinned 5-60 min after               1,747
      pinned over an hour after           4,231            median lateness +43 min
    legs under a LATE pin                17,710
      carrying an opening_probability    15,244  (86.1%)  <- get a real number
      carrying none                       2,466  (13.9%)  <- render no mark

The last line is the cost and it is deliberate: a leg whose pregame price we
cannot establish shows no baseline, which is the state the page already renders
for every unpinned leg without an opening. A wrong direction is worse than a
withheld one.

The boundary decides almost nothing — 198 markets of 10,091 sit in the 0-5 min
band at all — so it is set where the WRITER's jitter is: one 120s
`poll_live_prediction_markets` cadence.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.events import (
    _PREGAME_MARK_MAX_LATENESS_S,
    _pregame_mark_is_pregame,
    _resolve_pregame_mark,
)

# The specimen event, to the second.
COMMENCE = datetime(2026, 9, 12, 2, 15, 0, tzinfo=timezone.utc)
PIN_CAPTURED = datetime(2026, 9, 12, 4, 2, 11, tzinfo=timezone.utc)  # +107 min


def _outcome(oid):
    return SimpleNamespace(id=oid)


def _market(meta):
    # __dict__.get is how the helper reads market_metadata (gotcha #26 lazy-load
    # safe); SimpleNamespace mirrors an ORM row's __dict__.
    return SimpleNamespace(market_metadata=meta)


def _pinned(prob, captured_at, outcome_id=7, commence_in_pin=COMMENCE):
    """A market carrying one pinned outcome, in the writer's exact shape."""
    mark = {
        "captured_at": captured_at.isoformat(),
        "outcomes": {str(outcome_id): prob},
    }
    if commence_in_pin is not None:
        mark["commence_time"] = commence_in_pin.isoformat()
    return _market({"pregame_mark": mark})


class TestTheSpecimen:
    def test_taylors_pin_loses_to_his_opening_line(self):
        """0.995 pinned in the sixth inning; 0.585 is what he opened at."""
        m = _pinned(0.995, PIN_CAPTURED)
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.585, COMMENCE) == 0.585

    def test_merrills_pin_loses_too_and_the_direction_comes_back(self):
        """The row's job: the reader must see this prop RISE, not fall."""
        m = _pinned(0.995, PIN_CAPTURED)
        mark = _resolve_pregame_mark(m, _outcome(7), True, False, 0.295, COMMENCE)
        current = 0.85
        assert mark == 0.295
        assert current > mark, "the leg rose; the page said it fell"

    def test_travel_stops_being_manufactured(self):
        """The ranking half of the defect, stated as the consumer computes it."""
        m = _pinned(0.995, PIN_CAPTURED)
        current = 0.84
        fake_travel = abs(current - 0.995)  # what the page ranked on: 0.155
        real_travel = abs(
            current - _resolve_pregame_mark(m, _outcome(7), True, False, 0.585, COMMENCE)
        )
        assert real_travel == pytest.approx(0.255)
        assert real_travel > fake_travel

    def test_the_late_pin_is_refused_even_with_no_opening_to_fall_back_to(self):
        """THE COST, pinned. 13.9% of late-pin legs carry no opening line.

        They render no baseline rather than a fabricated one — the same state an
        unpinned leg without an opening already renders today.
        """
        m = _pinned(0.995, PIN_CAPTURED)
        assert _resolve_pregame_mark(m, _outcome(7), True, False, None, COMMENCE) is None


class TestPinsThatMustSurvive:
    """38.8% of production's pins are genuinely pregame. None of them may move."""

    def test_a_pin_taken_before_first_pitch_still_wins(self):
        m = _pinned(0.62, COMMENCE - timedelta(minutes=12))
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.40, COMMENCE) == 0.62

    def test_a_pin_taken_exactly_at_commence_still_wins(self):
        m = _pinned(0.62, COMMENCE)
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.40, COMMENCE) == 0.62

    def test_the_under_orientation_conversion_is_untouched(self):
        m = _pinned(0.62, COMMENCE - timedelta(minutes=5))
        assert _resolve_pregame_mark(m, _outcome(7), False, True, 0.40, COMMENCE) == 0.38

    def test_a_refused_pin_still_converts_its_fallback_orientation(self):
        """The opening arrives already on the over axis; refusing must not re-flip it."""
        m = _pinned(0.995, PIN_CAPTURED)
        assert _resolve_pregame_mark(m, _outcome(7), False, True, 0.38, COMMENCE) == 0.38


class TestTheBoundary:
    """Pinned on both sides so the constant cannot drift to 0, 60 or 300."""

    def test_one_poll_cadence_late_is_still_pregame(self):
        m = _pinned(0.62, COMMENCE + timedelta(seconds=120))
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.40, COMMENCE) == 0.62

    def test_one_second_past_the_cadence_is_in_play(self):
        m = _pinned(0.62, COMMENCE + timedelta(seconds=121))
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.40, COMMENCE) == 0.40

    def test_the_censused_five_minute_band_is_refused(self):
        """#5509's census screened at +5 min; this fix refuses that band too.

        The 168 markets between two and five minutes are the only rows where the
        two boundaries disagree, and they are refused — a price five minutes into
        a game is a price from the game.
        """
        m = _pinned(0.62, COMMENCE + timedelta(minutes=5))
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.40, COMMENCE) == 0.40

    def test_the_tolerance_is_the_writers_poll_cadence(self):
        """Not a tuned number: `poll_live_prediction_markets` beats every 120s."""
        from app.tasks import celery_app

        beat = celery_app.conf.beat_schedule
        entry = next(
            e
            for e in beat.values()
            if e["task"] == "app.tasks.poll_live_prediction_markets"
        )
        assert _PREGAME_MARK_MAX_LATENESS_S == entry["schedule"]


class TestWhatCannotBeJudged:
    """Zero rows on production today; the behaviour is chosen, so it is pinned."""

    def test_a_pin_with_no_captured_at_keeps_the_pre_5509_behaviour(self):
        m = _market({"pregame_mark": {"outcomes": {"7": 0.62}}})
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.40, COMMENCE) == 0.62

    def test_an_unparseable_captured_at_keeps_it_too(self):
        m = _market(
            {"pregame_mark": {"captured_at": "sometime", "outcomes": {"7": 0.62}}}
        )
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.40, COMMENCE) == 0.62

    def test_with_no_commence_anywhere_the_pin_is_kept(self):
        m = _pinned(0.62, PIN_CAPTURED, commence_in_pin=None)
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.40, None) == 0.62

    def test_the_pins_own_commence_is_used_when_the_event_carries_none(self):
        """The writer stamps `commence_time` beside `captured_at`; use it."""
        m = _pinned(0.995, PIN_CAPTURED)
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.585, None) == 0.585

    def test_the_events_commence_outranks_the_pins_copy(self):
        """A delayed start moves first pitch; the pin's copy is only what was known.

        Pinned at 02:20Z against an 02:15Z scheduled start is five minutes late —
        but the game was pushed to 03:00Z, so the pin is forty minutes EARLY.
        """
        delayed = datetime(2026, 9, 12, 3, 0, 0, tzinfo=timezone.utc)
        m = _pinned(0.62, COMMENCE + timedelta(minutes=5))
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.40, delayed) == 0.62

    def test_a_naive_commence_is_read_as_utc_and_does_not_raise(self):
        """`DateTime(timezone=True)` rows can still arrive naive through a mock/copy."""
        m = _pinned(0.995, PIN_CAPTURED)
        naive = COMMENCE.replace(tzinfo=None)
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.585, naive) == 0.585

    def test_a_datetime_captured_at_is_accepted_as_well_as_a_string(self):
        pm = {"captured_at": PIN_CAPTURED, "outcomes": {"7": 0.995}}
        assert _pregame_mark_is_pregame(pm, COMMENCE) is False

    def test_a_non_dict_pin_is_not_pregame(self):
        assert _pregame_mark_is_pregame(None, COMMENCE) is False
        assert _pregame_mark_is_pregame("pregame", COMMENCE) is False


class TestTheServePath:
    """A correct helper nobody reaches changes nothing — so drive the route.

    Both call sites are covered: the `player_prop` branch and the `team_total`
    branch that routes player-named outcomes into `player_props` (the shape
    Kalshi actually emits for "San Francisco at San Diego: Hits").
    """

    @pytest.mark.asyncio
    async def test_neither_prop_is_served_with_an_in_play_baseline(
        self, late_pin_client
    ):
        payload = (
            await late_pin_client.get("/api/events/15309667/game-markets")
        ).json()
        marks = {
            row["outcome_name"]: row["pregame_mark"]
            for row in payload.get("player_props") or []
        }
        assert marks, f"no player props were served: {sorted(payload)}"

        # the player_prop branch
        assert marks["Samad Taylor: 1+"] == 0.585, (
            "the in-play pin is still being served as THE SCRIPT's baseline"
        )
        # the team_total branch that hides player props
        assert marks["Jackson Merrill: 2+"] == 0.295
        # the control: a pin taken before first pitch is untouched
        assert marks["Matt Chapman: 1+"] == 0.61

    @pytest.mark.asyncio
    async def test_the_served_rows_now_point_the_way_they_moved(
        self, late_pin_client
    ):
        """What the reader sees: both legs rose, and the payload says so."""
        payload = (
            await late_pin_client.get("/api/events/15309667/game-markets")
        ).json()
        rows = {r["outcome_name"]: r for r in payload.get("player_props") or []}
        for name in ("Samad Taylor: 1+", "Jackson Merrill: 2+"):
            row = rows[name]
            assert row["over_probability"] > row["pregame_mark"], name

    @pytest.mark.asyncio
    async def test_no_served_prop_carries_the_in_play_pin_value(
        self, late_pin_client
    ):
        """The property over the whole payload, not named rows."""
        payload = (
            await late_pin_client.get("/api/events/15309667/game-markets")
        ).json()
        for key in ("player_props", "totals", "other", "spreads"):
            for row in payload.get(key) or []:
                assert row.get("pregame_mark") != 0.995, row.get("outcome_name")


@pytest.fixture
async def late_pin_client():
    """The Giants–Padres page rebuilt: two late-pinned props and one on-time.

    `market_metadata` is set EXPLICITLY on every market — `_make_futures_market`
    returns a MagicMock, and an unset attribute would float to a Mock rather than
    a dict, which `isinstance(meta, dict)` then refuses. Every market would fall
    back to its opening and this file would pass for the wrong reason, including
    on the control row.
    """
    from unittest.mock import AsyncMock, patch

    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.routes.events import _game_markets_cache
    from app.services.database import get_db, get_db_rw
    from tests.integration.test_route_events_seeded import (
        _make_event,
        _make_event_detail_session,
        _make_futures_market,
        _make_outcome,
    )

    _game_markets_cache.clear()

    event = _make_event(
        id=15309667,
        home_team="San Diego Padres",
        away_team="San Francisco Giants",
        status="live",
        sport_key="baseball_mlb",
    )
    event.commence_time = COMMENCE

    def _pin(market, captured_at, outcomes):
        market.market_metadata = {
            "pregame_mark": {
                "captured_at": captured_at.isoformat(),
                "commence_time": COMMENCE.isoformat(),
                "outcomes": {str(k): v for k, v in outcomes.items()},
            }
        }
        return market

    # 1. the player_prop branch — pinned 107 minutes after first pitch
    taylor = _make_futures_market(
        id=70000001,
        name="Giants at Padres: Samad Taylor Hits",
        source="kalshi",
        sport_category="baseball",
    )
    taylor.event_id = event.id
    _pin(taylor, PIN_CAPTURED, {101: 0.995})

    # 2. the team_total branch that hides player props — same late pin
    hits = _make_futures_market(
        id=70000002,
        name="San Francisco at San Diego: Hits",
        source="kalshi",
        sport_category="baseball",
    )
    hits.event_id = event.id
    _pin(hits, PIN_CAPTURED, {102: 0.995})

    # 3. THE CONTROL — an honest pin, twelve minutes before first pitch
    chapman = _make_futures_market(
        id=70000003,
        name="Giants at Padres: Matt Chapman Hits",
        source="kalshi",
        sport_category="baseball",
    )
    chapman.event_id = event.id
    _pin(chapman, COMMENCE - timedelta(minutes=12), {103: 0.61})

    def _leg(oid, market_id, name, current, opening):
        o = _make_outcome(id=oid, market_id=market_id, name=name, probability=current)
        o.opening_probability = opening
        o.current_yes_bid = 0.80
        o.current_yes_ask = 0.88
        return o

    outcomes = [
        _leg(101, 70000001, "Samad Taylor: 1+", 0.84, 0.585),
        _leg(102, 70000002, "Jackson Merrill: 2+", 0.85, 0.295),
        _leg(103, 70000003, "Matt Chapman: 1+", 0.70, 0.55),
    ]

    mock_session = _make_event_detail_session(
        event=event, futures=[taylor, hits, chapman], outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    _game_markets_cache.clear()
    app.dependency_overrides.clear()

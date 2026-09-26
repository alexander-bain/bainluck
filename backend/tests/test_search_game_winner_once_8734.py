"""#8734 — search prints each upcoming game once, as its game card.

THE DEFECT, SEEN ON PRODUCTION (2026-09-25 23:0xZ, 390px, `/search?q=packers`).
The GAMES rail showed Buccaneers v Packers, Oct 4, Packers 52%. The ANSWERS card
lower down read

    GB Packers vs TB Buccaneers — Green Bay 53% · Oct 6

which is Kalshi `KXNFLGAME-26OCT04GBTB` (futures market 61894628), attached to
the same game (`event_id` 14782708). Same question, two numbers, and dated by
Kalshi's close time rather than the kickoff. The same shape was served for
chiefs, eagles, cowboys (Kalshi) and yankees (Polymarket).

🔴 THE CONTROLS ARE THE POINT. "The winner market is gone" is satisfied by a
search that withholds every attached market. So: the same game's spread and
total stay; a winner market whose game is NOT on the page stays; an unattached
winner market stays; a season-series "Winner" attached to a game stays; and a
bare matchup title with Over/Under legs is not read as a winner.
"""

import ast
import inspect
import textwrap
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import Event, Sport
from app.routes import events as events_module
from app.routes.events import _answers_a_served_game_card, search_events

NFL = Sport(id=1, key="americanfootball_nfl", name="NFL", group="Football", active=True)

GAME_ID = 14782708
OTHER_GAME_ID = 14780556
WINNER_ID = 61894628
WINNER_TICKER = "KXNFLGAME-26OCT04GBTB"
SPREAD_ID = 61894700
TOTAL_ID = 61894701
KICKOFF = datetime.now(timezone.utc) + timedelta(days=9)


def _outcome(oid, name, prob):
    return SimpleNamespace(
        id=oid, name=name, probability=prob, current_probability=prob,
        opening_probability=prob, is_winner=None, price=prob,
        probability_change_24h=None, american_odds=None,
        current_american_odds=None, current_yes_ask=None,
        current_yes_bid=None, rank=None, sort_order=oid,
        external_id=f"leg-{oid}", last_updated=None,
        calibration_probability=None, volume=None, price_changed_at=None,
        resolution_source=None,
    )


def _market(mid, name, external_id, *, event_id=GAME_ID, legs=(("Green Bay", 0.53), ("Tampa Bay", 0.47)),
            source="kalshi", volume=900_000.0):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=external_id,
        llm_sport_category="football",
        category="championship",
        market_tier=5,
        market_type="duel",
        sport=None,
        sport_id=None,
        source=source,
        volume=volume,
        status="open",
        resolution_date=(now + timedelta(days=11)).date(),
        updated_at=now,
        canonical_market_key=None,
        image_url=None,
        hook_description=None,
        group_id=None,
        event_id=event_id,
        mutually_exclusive=True,
        outcomes=[_outcome(mid * 10 + i, n, p) for i, (n, p) in enumerate(legs, start=1)],
    )


def _winner(**kw):
    return _market(WINNER_ID, "GB Packers vs TB Buccaneers", WINNER_TICKER, **kw)


def _spread():
    return _market(
        SPREAD_ID, "GB Packers vs TB Buccaneers: Spread", "KXNFLSPREAD-26OCT04GBTB",
        legs=(("Green Bay -2.5", 0.48), ("Tampa Bay +2.5", 0.52)), volume=500_000.0,
    )


def _total():
    return _market(
        TOTAL_ID, "GB Packers vs TB Buccaneers: Total Points", "KXNFLTOTAL-26OCT04GBTB",
        legs=(("Over 44.5", 0.5), ("Under 44.5", 0.5)), volume=400_000.0,
    )


# ── the pure predicate ──────────────────────────────────────────────────────


def test_the_packers_winner_market_answers_the_served_game_card():
    """🔴 THE SHIP: attached, a winner, and its game is on the page."""
    assert _answers_a_served_game_card(_winner(), {GAME_ID}) is True


def test_the_polymarket_winner_market_is_covered_too():
    """`q=yankees` served Polymarket's 'Baltimore Orioles vs. New York Yankees'."""
    m = _market(
        62236454, "Baltimore Orioles vs. New York Yankees", "0xa639b1d0",
        source="polymarket", legs=(("Baltimore Orioles", 0.44), ("New York Yankees", 0.56)),
    )
    assert _answers_a_served_game_card(m, {GAME_ID}) is True


def test_the_game_is_not_on_the_page_so_the_market_stays():
    """Another results page, a `type=futures` filter or a shed event stage: the
    market is then the only way to reach the game."""
    assert _answers_a_served_game_card(_winner(), {OTHER_GAME_ID}) is False
    assert _answers_a_served_game_card(_winner(), set()) is False


def test_an_unattached_winner_market_stays():
    assert _answers_a_served_game_card(_winner(event_id=None), {GAME_ID}) is False


@pytest.mark.parametrize("make", [_spread, _total])
def test_the_same_games_other_questions_stay(make):
    assert _answers_a_served_game_card(make(), {GAME_ID}) is False


def test_a_season_series_winner_is_not_one_games_question():
    """The shared classifier accepts this on its 'Winner' word."""
    m = _market(
        56722514, "NFL: Lions vs. Packers Season Series Winner", "0x56722514",
        source="polymarket", legs=(("Tie", 0.52), ("Lions", 0.26), ("Packers", 0.22)),
    )
    assert _answers_a_served_game_card(m, {GAME_ID}) is False


def test_a_matchup_title_with_over_under_legs_is_not_a_winner():
    m = _market(7, "Falcons vs. Packers", "848221", source="polymarket",
                legs=(("Over", 0.5), ("Under", 0.5)))
    assert _answers_a_served_game_card(m, {GAME_ID}) is False


# ── the route ───────────────────────────────────────────────────────────────


def _event(id, *, home="Tampa Bay Buccaneers", away="Green Bay Packers"):
    e = Event(
        id=id, sport_id=NFL.id, away_team_name=away, home_team_name=home,
        commence_time=KICKOFF, status="scheduled",
    )
    e.sport = NFL
    return e


def _mock_db(events, window):
    db = AsyncMock()

    def make_result(rows=(), *, grouped=None, scalars=None):
        r = MagicMock()
        r.scalars.return_value.all.return_value = list(scalars or rows)
        r.scalars.return_value.unique.return_value.all.return_value = list(scalars or rows)
        r.scalars.return_value.first.return_value = None
        r.fetchall.return_value = []
        r.all.return_value = grouped or []
        r.scalar.return_value = len(events)
        r.scalar_one_or_none.return_value = None
        r.first.return_value = None
        r.mappings.return_value.all.return_value = []
        return r

    async def execute(stmt, *a, **k):
        try:
            s = str(stmt)
        except Exception:  # noqa: BLE001
            return make_result()
        low = s.lower()
        if "count(" in low and "futures_markets" not in low:
            return make_result(grouped=[(NFL.key, NFL.name, len(events))] if events else [])
        if "futures_markets" in low and low.lstrip().startswith("select futures_markets.id,"):
            # the futures WINDOW selects the whole row; narrow projections
            # (container reads, id lookups) answer nothing.
            return make_result(scalars=window)
        if "futures_markets" in low or "odds_snapshots" in low or "teams" in low:
            return make_result()
        if "from events" in low:
            return make_result(events)
        return make_result()

    db.execute = AsyncMock(side_effect=execute)
    db.begin_nested = AsyncMock(return_value=AsyncMock())
    return db


async def _payload(events, window, q="packers"):
    rc = MagicMock()
    rc.get.return_value = None
    with (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch(
            "app.routes.events.folded_probability_sources_batch",
            new=AsyncMock(return_value={}),
        ),
        patch("app.routes.events._record_trending", new=MagicMock()),
    ):
        return await search_events(
            request=MagicMock(), response=MagicMock(), q=q, db=_mock_db(events, window),
            sport=None, tags=None, page=1, per_page=25, days_back=30,
            include_upcoming=True, debug_timing=False, current_user=None,
        )


def _served_market_ids(payload):
    ids = [f["id"] for f in payload.get("futures") or []]
    for fam in payload.get("futures_families") or []:
        if fam.get("headline"):
            ids.append(fam["headline"]["id"])
        ids.extend(m["id"] for m in fam["members"])  # #8851: the served key
    return set(ids)


@pytest.mark.asyncio
async def test_the_route_serves_the_game_once():
    """🔴 THE SHIP at the route: the game card stays, its winner market leaves
    BOTH reader lists, and the same game's spread and total are still served."""
    payload = await _payload([_event(GAME_ID)], [_winner(), _spread(), _total()])
    assert [r["id"] for r in payload["results"]] == [GAME_ID]
    served = _served_market_ids(payload)
    assert WINNER_ID not in served, served
    assert {SPREAD_ID, TOTAL_ID} <= served, served


@pytest.mark.asyncio
async def test_the_route_keeps_the_winner_when_its_game_is_not_served():
    """Control: the same window, the game absent from `results`."""
    payload = await _payload([_event(OTHER_GAME_ID)], [_winner(), _spread(), _total()])
    served = _served_market_ids(payload)
    assert {WINNER_ID, SPREAD_ID, TOTAL_ID} <= served, served


# ── the wiring ──────────────────────────────────────────────────────────────


def _route_source():
    return textwrap.dedent(inspect.getsource(events_module.search_events))


def test_every_reader_list_asks_the_question():
    """The flat list, the families and the post-promotion filter. A family is the
    back door a half-applied withdrawal leaves open (#6327)."""
    tree = ast.parse(_route_source())
    comps = [
        ast.unparse(n)
        for n in ast.walk(tree)
        if isinstance(n, ast.ListComp) and "_answers_a_served_game_card" in ast.unparse(n)
    ]
    iters = sorted(
        c.split(" for m in ", 1)[1].split(" ", 1)[0] for c in comps
    )
    assert iters == ["deduped_futures", "deduped_futures", "futures_markets"], comps


def test_the_served_ids_come_from_the_formatted_results():
    """Plain dicts, not ORM rows: a session rollback between the event page and
    the futures stage would expire the rows (gotcha #6)."""
    src = _route_source()
    assert '_served_event_ids = {r.get("id") for r in formatted_results}' in src
    assert src.index("formatted_results.append(") < src.index("_served_event_ids =")
    assert src.index("_served_event_ids =") < src.index("_compose_futures_families(")

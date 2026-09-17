"""#6238 — `/api/events/{id}` stops serving an away probability it cannot source.

## The defect, measured on production 2026-09-16 19:00 PDT / 2026-09-17 02:00Z

`routes/events.py` builds the away side of every probability object it serves as
`1 − home`. On a two-outcome sport that is exactly right. In soccer `1 − P(home)`
is *"the home team does not win"* — away win **or** draw — so the second slot
silently absorbs the entire draw, and the payload contradicts itself in one
response:

    15298553  Juventus v NEC Nijmegen
        current_odds            home 0.7937  away 0.2063   sum 1.0000
        bookmaker_odds[], 10 books, mean
                                home 0.7939  away 0.0740   sum 0.8679
        0 of 10 book pairs sum above 0.97 — the book rows carry a real
        three-way away price; the served pair is the fabricated one.

    15298549  PFC Levski Sofia v Salzburg   served away 0.6893 over a board
                                            pricing Salzburg 0.4203 — the
                                            served pair REVERSES the favourite.
    15298747  OFI Crete v TSG Hoffenheim    served away 0.8737, books 0.6845.

Both client halves already withhold this figure — native's #5271 (2026-09-11)
and ux's web render half (#6238, live `c40e36d0e`) — so what is left is the
server saying it, to native, My Stuff, share cards and every other API reader.
This file is the PRODUCER half of that pair (notice 46; consumer issue #6238,
accepted in `runner-inbox/latency/FROM-ux1304-0110Z-6238-…`).

## What is asserted, and why in both directions

Every site is asserted separately because each is reached by a different branch
and "fixed one" greps identically to "fixed all four": the snapshot path, the
no-snapshot fallback, `opening_odds`, and the top-level `hero_probability_away`.

The REFUSAL direction is asserted as hard as the withhold (gotcha #43, and
`away_is_the_complement`'s own argument):

* a two-way sport keeps its away number and its 100-summing pair — the rule is
  opt-in per sport and this is what proves it;
* a SOURCED soccer opening pair (0.3107 / 0.4216, sum 0.7323 — production
  tonight) keeps its away number, because deleting a real away price is the
  mirror-image defect of printing a fabricated one;
* a SETTLED hero keeps both sides, including the loser's 0.0 and a draw's
  0.5/0.5. Those sum to 1.0 and would be withheld by a purely numeric test —
  "settled means settled" outranks this issue, a result is not a price, and the
  gate is the hero's own `source` vocabulary for exactly that reason.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.draw_priced_winner import (
    DRAW_PRICED_SPORT_KEY_MATCHES,
    away_is_the_complement,
    printable_away,
    sport_prices_a_draw,
)
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
)

SOCCER = "soccer_uefa_europa_league"
TWO_WAY = "basketball_nba"

# The Juventus specimen, to the digit: the blend the page serves and the away
# number ten sportsbooks in the same payload actually quote.
JUVENTUS_HOME = 0.7937
JUVENTUS_FABRICATED_AWAY = 0.2063
JUVENTUS_BOOKS_AWAY = 0.0740

# PFC Levski Sofia's stored opening pair on production tonight. Sums to 0.7323:
# a three-way board, de-vigged across all three legs since #1011, whose away leg
# is Salzburg's real price and must survive.
LEVSKI_OPENING_HOME = 0.3107
LEVSKI_OPENING_AWAY = 0.4216


def _event(
    *,
    sport_key: str,
    home_prob: float,
    event_id: int,
    opening_home: float | None = 0.58,
    opening_away: float | None = 0.42,
    status: str = "live",
    home_score: int | None = 1,
    away_score: int | None = 0,
    completed_at: datetime | None = None,
):
    """An event whose blend is EXACTLY `home_prob`.

    One betting source, so `compute_aggregate_probability` returns the specimen
    value rather than a blend of it with the fixture's default ESPN reading —
    the same trick `test_event_detail_duel_percents_2085.py` uses, for the same
    reason: an assertion about a withheld away number is worthless if the home
    number it is paired with is an accident of the fixture.
    """
    event = _make_event(
        id=event_id,
        sport_key=sport_key,
        home_prob=home_prob,
        status=status,
        home_score=home_score,
        away_score=away_score,
    )
    event.win_probability_sources = {
        "betting": {"value": home_prob, "home_probability": home_prob}
    }
    event.current_home_probability = home_prob
    event.current_away_probability = round(1.0 - home_prob, 6)
    event.opening_home_probability = opening_home
    event.opening_away_probability = opening_away
    event.completed_at = completed_at
    # `opening_consensus_has_frozen` publishes `opening_odds` only once the
    # writer has stopped; every specimen here is already under way.
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=1)
    return event


def _snapshot(home_prob: float, away_prob: float, bookmaker: str = "draftkings"):
    """One odds snapshot — enough to take the snapshot branch of `current_odds`.

    `away_prob` is passed separately rather than derived: since #1011 a soccer
    book row carries the de-vigged THREE-WAY away price, and a fixture that
    derives it would quietly make the book rows agree with the defect this file
    is about.
    """
    snap = MagicMock()
    snap.bookmaker = bookmaker
    snap.home_win_probability = home_prob
    snap.away_win_probability = away_prob
    snap.home_moneyline = -150
    snap.away_moneyline = 900
    snap.home_spread = -1.5
    snap.away_spread = 1.5
    snap.over_under = 2.5
    snap.projected_home_score = 2
    snap.projected_away_score = 1
    snap.captured_at = datetime.now(timezone.utc)
    snap.valid_until = None
    snap.event_id = 1
    return snap


async def _payload(event, snapshots=None):
    from app.main import app
    from app.routes.events import _event_detail_cache

    _event_detail_cache.clear()
    session = _make_event_detail_session(event=event, snapshots=snapshots)

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(f"/api/events/{event.id}")
        return response.json()
    finally:
        app.dependency_overrides.clear()


# ── Site 1: `current_odds`, the snapshot path ───────────────────────────────


@pytest.mark.asyncio
async def test_snapshot_path_withholds_the_fabricated_away_on_soccer():
    payload = await _payload(
        _event(sport_key=SOCCER, home_prob=JUVENTUS_HOME, event_id=6238001),
        snapshots=[_snapshot(JUVENTUS_HOME, JUVENTUS_BOOKS_AWAY)],
    )
    odds = payload["current_odds"]
    assert "captured_at" in odds, f"not the snapshot branch: {odds}"
    assert "away_probability" in odds, (
        "the key is SERVED AS NULL, not dropped: a client that tests for the "
        "key's presence must be able to tell 'withheld' from 'this payload "
        "shape is older than the field'"
    )
    assert odds["away_probability"] is None, (
        f"served {odds['away_probability']} — the books in this same payload "
        f"price the away side at {JUVENTUS_BOOKS_AWAY}"
    )
    assert odds["away_rendered_percent"] is None


@pytest.mark.asyncio
async def test_the_home_number_is_untouched_and_still_renders_whole():
    """The home leg is not the defect — since #1011 it agrees with the books.

    Withholding happens BEFORE `rendered_duel_percents`, so the home percent
    must be the same whole number the page has always printed. A fix applied
    after the rounding would leave a home percent derived from a pair that no
    longer exists.
    """
    payload = await _payload(
        _event(sport_key=SOCCER, home_prob=JUVENTUS_HOME, event_id=6238002),
        snapshots=[_snapshot(JUVENTUS_HOME, JUVENTUS_BOOKS_AWAY)],
    )
    odds = payload["current_odds"]
    assert odds["home_probability"] == pytest.approx(JUVENTUS_HOME)
    assert odds["home_rendered_percent"] == 79


@pytest.mark.asyncio
async def test_the_book_rows_keep_their_own_three_way_away_price():
    """Only the fabricated slot goes.

    `bookmaker_odds[]` is where a reader (and the calibration rails) can see
    what a venue actually quoted, and those away numbers are sourced. A withhold
    that swept them up would delete the evidence that the served pair was wrong.
    """
    payload = await _payload(
        _event(sport_key=SOCCER, home_prob=JUVENTUS_HOME, event_id=6238003),
        snapshots=[_snapshot(JUVENTUS_HOME, JUVENTUS_BOOKS_AWAY)],
    )
    rows = payload["bookmaker_odds"]
    assert rows, "no book rows — this specimen proves nothing"
    assert rows[0]["away_probability"] == pytest.approx(JUVENTUS_BOOKS_AWAY)


@pytest.mark.asyncio
async def test_a_two_way_sport_keeps_its_away_number_and_its_hundred():
    """The refusal direction, gotcha #43. An undeclared sport is untouched."""
    payload = await _payload(
        _event(sport_key=TWO_WAY, home_prob=0.675, event_id=6238004),
        snapshots=[_snapshot(0.675, 0.325)],
    )
    odds = payload["current_odds"]
    assert odds["away_probability"] == pytest.approx(0.325)
    assert odds["away_rendered_percent"] + odds["home_rendered_percent"] == 100


# ── Site 2: `current_odds`, the no-snapshot fallback ────────────────────────


@pytest.mark.asyncio
async def test_the_no_snapshot_fallback_withholds_too():
    """The arm with no book rows at all, so nothing else contradicts the lie."""
    payload = await _payload(
        _event(sport_key=SOCCER, home_prob=JUVENTUS_HOME, event_id=6238005)
    )
    odds = payload["current_odds"]
    assert odds.get("source") == "aggregate", f"not the fallback branch: {odds}"
    assert odds["away_probability"] is None
    assert odds["away_rendered_percent"] is None
    assert odds["home_probability"] == pytest.approx(JUVENTUS_HOME)


@pytest.mark.asyncio
async def test_the_no_snapshot_fallback_is_untouched_on_a_two_way_sport():
    payload = await _payload(_event(sport_key=TWO_WAY, home_prob=0.675, event_id=6238006))
    odds = payload["current_odds"]
    assert odds.get("source") == "aggregate"
    assert odds["away_probability"] == pytest.approx(0.325)


# ── Site 3: `opening_odds` — the object that mostly KEEPS its away ──────────


@pytest.mark.asyncio
async def test_a_sourced_three_way_opening_pair_survives():
    """0.3107 / 0.4216 sums to 0.7323 — the shortfall IS the draw, and the away
    leg is Salzburg's real price. Deleting it is the mirror-image defect."""
    payload = await _payload(
        _event(
            sport_key=SOCCER,
            home_prob=JUVENTUS_HOME,
            event_id=6238007,
            opening_home=LEVSKI_OPENING_HOME,
            opening_away=LEVSKI_OPENING_AWAY,
        )
    )
    opening = payload["opening_odds"]
    assert opening["away_probability"] == pytest.approx(LEVSKI_OPENING_AWAY)
    assert opening["home_probability"] == pytest.approx(LEVSKI_OPENING_HOME)


@pytest.mark.asyncio
async def test_a_stored_opening_pair_that_is_a_complement_is_withheld():
    """A pre-#1011 row: 0.58 / 0.42 sums to 1.0, so its away leg holds the draw."""
    payload = await _payload(
        _event(
            sport_key=SOCCER,
            home_prob=JUVENTUS_HOME,
            event_id=6238008,
            opening_home=0.58,
            opening_away=0.42,
        )
    )
    assert payload["opening_odds"]["away_probability"] is None


@pytest.mark.asyncio
async def test_the_derived_opening_away_is_withheld_when_the_column_is_null():
    """The `round(1 - home, 4)` arm — the same fabrication, inside a fallback."""
    payload = await _payload(
        _event(
            sport_key=SOCCER,
            home_prob=JUVENTUS_HOME,
            event_id=6238009,
            opening_home=0.58,
            opening_away=None,
        )
    )
    assert payload["opening_odds"]["away_probability"] is None


@pytest.mark.asyncio
async def test_a_two_way_opening_pair_is_untouched():
    payload = await _payload(
        _event(sport_key=TWO_WAY, home_prob=0.675, event_id=6238010)
    )
    assert payload["opening_odds"]["away_probability"] == pytest.approx(0.42)


# ── Site 4: the top-level hero pair, and the settled exemption ──────────────


@pytest.mark.asyncio
async def test_the_hero_away_is_withheld_on_a_live_soccer_match():
    payload = await _payload(
        _event(sport_key=SOCCER, home_prob=JUVENTUS_HOME, event_id=6238011),
        snapshots=[_snapshot(JUVENTUS_HOME, JUVENTUS_BOOKS_AWAY)],
    )
    assert payload["hero_probability_source"] == "blend"
    assert payload["hero_probability"] == pytest.approx(JUVENTUS_HOME)
    assert payload["hero_probability_away"] is None, (
        "the hero carries its own copy of the same derivation "
        f"({JUVENTUS_FABRICATED_AWAY} on the production specimen)"
    )


@pytest.mark.asyncio
async def test_the_hero_away_survives_on_a_two_way_sport():
    payload = await _payload(
        _event(sport_key=TWO_WAY, home_prob=0.675, event_id=6238012),
        snapshots=[_snapshot(0.675, 0.325)],
    )
    assert payload["hero_probability_away"] == pytest.approx(0.325)


@pytest.mark.asyncio
async def test_a_settled_soccer_result_keeps_the_losing_side():
    """1.0 / 0.0 sums to 1.0 and is NOT a complement pair in the sense this
    issue means. Withholding here would erase the loser from a finished match."""
    payload = await _payload(
        _event(
            sport_key=SOCCER,
            home_prob=JUVENTUS_HOME,
            event_id=6238013,
            status="completed",
            home_score=2,
            away_score=1,
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
    )
    assert payload["hero_probability_source"] == "settled"
    assert payload["hero_probability"] == pytest.approx(1.0)
    assert payload["hero_probability_away"] == pytest.approx(0.0)
    assert payload["hero_settled_result"] == "home"


@pytest.mark.asyncio
async def test_a_settled_soccer_draw_keeps_both_halves():
    """The case this issue is ABOUT, once it is over: 2-2 resolves 0.5/0.5 with
    `result="draw"`, which is the one shape that tells a reader nobody won."""
    payload = await _payload(
        _event(
            sport_key=SOCCER,
            home_prob=JUVENTUS_HOME,
            event_id=6238014,
            status="completed",
            home_score=2,
            away_score=2,
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
    )
    assert payload["hero_probability_source"] == "settled"
    assert payload["hero_probability"] == pytest.approx(0.5)
    assert payload["hero_probability_away"] == pytest.approx(0.5)
    assert payload["hero_settled_result"] == "draw"


# ── The rule itself ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "key",
    [
        "soccer_uefa_europa_league",
        "soccer_mexico_ligamx",
        "soccer_korea_kleague1",
        "SOCCER_EPL",
        "soccer_usa_mls",
        "soccer_fifa_world_cup",
    ],
)
def test_declared_sports_price_a_draw(key):
    assert sport_prices_a_draw(key) is True


@pytest.mark.parametrize(
    "key",
    ["basketball_nba", "tennis_atp", "icehockey_nhl", "baseball_mlb", "", None, 7],
)
def test_undeclared_sports_keep_their_two_sided_reading(key):
    assert sport_prices_a_draw(key) is False


def test_the_predicate_asks_about_the_pair_and_not_only_the_sport():
    # derived complement on a draw-priced sport → withhold
    assert away_is_the_complement(0.2063, 0.7937, SOCCER) is True
    # sourced three-way pair on the same sport → keep
    assert away_is_the_complement(LEVSKI_OPENING_AWAY, LEVSKI_OPENING_HOME, SOCCER) is False
    # absent away on a draw-priced sport → withheld, so the caller keeps a slot
    assert away_is_the_complement(None, 0.7937, SOCCER) is True
    # absent away on a two-way sport → NOT withheld; the existing "one side has
    # no reading" paths are untouched
    assert away_is_the_complement(None, 0.7937, TWO_WAY) is False
    # a complement on a two-way sport → the whole point of the sport gate
    assert away_is_the_complement(0.325, 0.675, TWO_WAY) is False


def test_printable_away_only_ever_removes():
    assert printable_away(0.4216, LEVSKI_OPENING_HOME, SOCCER) == 0.4216
    assert printable_away(0.2063, 0.7937, SOCCER) is None
    assert printable_away(0.325, 0.675, TWO_WAY) == 0.325


def test_the_declaration_matches_the_web_vocab_byte_for_byte():
    """THE THREE RUNTIMES ANSWER ONE QUESTION, SO THEY READ ONE LIST.

    `frontend/__tests__/ios/aDrawIsNotTheAwayTeam5271.test.ts` pins the web to
    the Swift by scanning the Swift source; this pins the server to the web the
    same way. Without it the declaration drifts silently — which is exactly the
    failure that let the web print the complement for five days after native
    stopped, and it would reappear the first time somebody widens the rule to a
    second sport in one runtime.
    """
    vocab = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "lib"
        / "marketMapUtils.ts"
    )
    if not vocab.exists():  # pragma: no cover - backend-only checkouts
        pytest.skip("frontend/ not present in this checkout")
    source = vocab.read_text()

    rows = re.findall(
        r"match:\s*\[([^\]]*)\][^}]*?winnerMarketPricesADraw:\s*(true|false)",
        source,
        re.DOTALL,
    )
    declared = [
        tuple(re.findall(r'"([^"]+)"', match)) for match, flag in rows if flag == "true"
    ]
    assert len(declared) == 1, (
        f"the web vocab declares {len(declared)} draw-priced rows; this module "
        "carries one list and cannot mirror two"
    )
    assert declared[0] == DRAW_PRICED_SPORT_KEY_MATCHES, (
        f"web says {declared[0]}, server says {DRAW_PRICED_SPORT_KEY_MATCHES} — "
        "widen both, or one surface withholds where the other prints"
    )

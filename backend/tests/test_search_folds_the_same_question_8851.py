"""#8851 — search shows each question once when two venues ask it.

THE DEFECT, SEEN ON PRODUCTION (2026-09-26 15:48Z, 390px, `/search?q=oscars`).
The ANSWERS card listed Best Picture twice, with two numbers:

    Oscar Winner: Best Picture          The Odyssey 53%   (Kalshi 6173044)
    Oscars 2027: Best Picture Winner    The Odyssey 49%   (Polymarket 57313556)

and the flat list did the same for Best Actor and Best Actress. Discover folds
exactly this pair since #8387; search never asked. The fixtures below are the
six production rows as read at 16:5xZ the same day (names, closes, top five).

🔴 THE CONTROLS ARE THE POINT. "The twin is gone" is satisfied by a search that
drops every Polymarket row. So: Best Picture, Best Actor and Best Actress stay
three questions; two same-venue rows are never folded; the men's and women's
US Open stay apart; a row whose facts cannot be built is kept and the pass goes
on; and the better-ranked row is the one that survives, whichever venue it is.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.events import _search_same_question_folded_ids, search_events

KALSHI_CLOSE = datetime(2027, 12, 31, 15, 0, tzinfo=timezone.utc)
POLY_CLOSE = datetime(2027, 7, 1, 3, 59, tzinfo=timezone.utc)

K_PICTURE, P_PICTURE = 6173044, 57313556
K_ACTOR, P_ACTOR = 5869749, 57368169
K_ACTRESS, P_ACTRESS = 5869748, 57366460


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


def _market(mid, name, source, close, legs, *, volume=500_000.0):
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=f"ext-{mid}",
        llm_sport_category=None,
        category="entertainment",
        market_tier=2,
        market_type="championship",
        sport=None,
        sport_id=None,
        source=source,
        volume=volume,
        status="open",
        resolution_date=close,
        updated_at=datetime.now(timezone.utc),
        canonical_market_key=None,
        image_url=None,
        hook_description=None,
        group_id=None,
        event_id=None,
        mutually_exclusive=True,
        outcomes=[_outcome(mid * 10 + i, n, p) for i, (n, p) in enumerate(legs, start=1)],
    )


def k_picture():
    return _market(K_PICTURE, "Oscar Winner: Best Picture", "kalshi", KALSHI_CLOSE, (
        ("The Odyssey", 0.525), ("The Black Ball", 0.265), ("Dune: Part Three", 0.105),
        ("Wild Horse Nine", 0.035), ("The Debut", 0.025),
    ), volume=900_000.0)


def p_picture():
    return _market(P_PICTURE, "Oscars 2027: Best Picture Winner", "polymarket", POLY_CLOSE, (
        ("The Odyssey", 0.49), ("La Bola Negra", 0.245), ("Dune: Part Three", 0.105),
        ("Wild Horse Nine", 0.036), ("The Debut", 0.02),
    ), volume=800_000.0)


def k_actor():
    return _market(K_ACTOR, "Oscar Winner: Best Actor", "kalshi", KALSHI_CLOSE, (
        ("John Malkovich", 0.295), ("Matt Damon", 0.255), ("Andrew Scott", 0.185),
        ("Tom Cruise", 0.125), ("Robert Pattison", 0.105),
    ), volume=700_000.0)


def p_actor():
    return _market(P_ACTOR, "Oscars 2027: Best Actor Winner", "polymarket", POLY_CLOSE, (
        ("John Malkovich", 0.374), ("Matt Damon", 0.22), ("Andrew Scott", 0.185),
        ("Tom Cruise", 0.10), ("Robert Pattinson", 0.056),
    ), volume=600_000.0)


def k_actress():
    return _market(K_ACTRESS, "Oscar winner: Best Actress", "kalshi", KALSHI_CLOSE, (
        ("Julianne Moore", 0.605), ("Inde Navarrette", 0.17), ("Sandra Hüller", 0.045),
        ("Renate Reinsve", 0.025), ("Joan Collins", 0.02),
    ), volume=550_000.0)


def p_actress():
    return _market(P_ACTRESS, "Oscars 2027: Best Actress Winner", "polymarket", POLY_CLOSE, (
        ("Julianne Moore", 0.665), ("Inde Navarrette", 0.145), ("Sandra Hüller", 0.059),
        ("Renate Reinsve", 0.027), ("Virginie Efira", 0.016),
    ), volume=500_000.0)


def _folded(markets):
    return _search_same_question_folded_ids(markets, {})


# ── the helper ──────────────────────────────────────────────────────────────


def test_best_picture_is_one_question_on_two_venues():
    """🔴 THE SHIP: the Polymarket copy of the Kalshi row folds."""
    assert _folded([k_picture(), p_picture()]) == {P_PICTURE}


def test_the_better_ranked_row_survives_whichever_venue_it_is():
    assert _folded([p_picture(), k_picture()]) == {K_PICTURE}


def test_three_categories_of_one_ceremony_stay_three_questions():
    """Control: all six rows. Picture, Actor and Actress share a ceremony, a
    close date and a title shape; only each category's second venue folds."""
    rows = [k_picture(), k_actor(), k_actress(), p_picture(), p_actor(), p_actress()]
    assert _folded(rows) == {P_PICTURE, P_ACTOR, P_ACTRESS}


def test_two_rows_from_one_venue_are_never_folded():
    """Control: the venue gate. Same title, same legs, both Kalshi."""
    twin = k_picture()
    twin.id = 7000001
    assert _folded([k_picture(), twin]) == set()


def test_the_mens_and_womens_us_open_stay_apart():
    """Control: the pair #4479 measured scoring ABOVE a real duplicate."""
    close = datetime(2026, 9, 14, tzinfo=timezone.utc)
    men = _market(1, "US Open Men's Singles Winner", "kalshi", close,
                  (("Jannik Sinner", 0.4), ("Carlos Alcaraz", 0.35), ("Novak Djokovic", 0.1)))
    women = _market(2, "US Open Women's Singles Winner", "polymarket", close,
                    (("Aryna Sabalenka", 0.3), ("Iga Swiatek", 0.25), ("Coco Gauff", 0.1)))
    assert _folded([men, women]) == set()


def test_a_refused_price_does_not_vote_for_a_pairing():
    """The facts are the card's own top five with #6993's refusals out: refuse
    the Polymarket leader and the two rows no longer share one, so they stay two
    (each still prints its own answer)."""
    poly = p_picture()
    refused_leader = poly.outcomes[0].id
    assert _search_same_question_folded_ids(
        [k_picture(), poly], {P_PICTURE: {refused_leader}}
    ) == set()


def test_one_bad_row_does_not_wipe_the_pass():
    """Gotcha 42: a row whose facts raise is kept, and its neighbours still fold."""
    broken = k_actor()
    broken.outcomes = None  # iterating it raises
    assert _folded([broken, k_picture(), p_picture()]) == {P_PICTURE}


# ── the route ───────────────────────────────────────────────────────────────


def _mock_db(window):
    db = AsyncMock()

    def make_result(rows=(), *, scalars=None):
        r = MagicMock()
        r.scalars.return_value.all.return_value = list(scalars or rows)
        r.scalars.return_value.unique.return_value.all.return_value = list(scalars or rows)
        r.scalars.return_value.first.return_value = None
        r.fetchall.return_value = []
        r.all.return_value = []
        r.scalar.return_value = 0
        r.scalar_one_or_none.return_value = None
        r.first.return_value = None
        r.mappings.return_value.all.return_value = []
        return r

    async def execute(stmt, *a, **k):
        try:
            low = str(stmt).lower()
        except Exception:  # noqa: BLE001
            return make_result()
        if "futures_markets" in low and low.lstrip().startswith("select futures_markets.id,"):
            return make_result(scalars=window)
        return make_result()

    db.execute = AsyncMock(side_effect=execute)
    db.begin_nested = AsyncMock(return_value=AsyncMock())
    return db


async def _payload(window, q="oscars"):
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
            request=MagicMock(), response=MagicMock(), q=q, db=_mock_db(window),
            sport=None, tags=None, page=1, per_page=25, days_back=30,
            include_upcoming=True, debug_timing=False, current_user=None,
        )


def _flat_ids(payload):
    return [f["id"] for f in payload.get("futures") or []]


def _family_ids(payload):
    """A family serves its rows as `headline` + `members` (not `markets`)."""
    ids = set()
    for fam in payload.get("futures_families") or []:
        if fam.get("headline"):
            ids.add(fam["headline"]["id"])
        ids.update(m["id"] for m in fam["members"])
    return ids


@pytest.mark.asyncio
async def test_the_route_serves_each_oscar_category_once():
    """🔴 THE SHIP at the route: neither reader list carries a Polymarket twin,
    and all three Kalshi categories are still served."""
    window = [k_picture(), p_picture(), k_actor(), p_actor(), k_actress(), p_actress()]
    payload = await _payload(window)
    flat = _flat_ids(payload)
    assert sorted(flat) == sorted([K_PICTURE, K_ACTOR, K_ACTRESS]), flat
    families = _family_ids(payload)
    # The family formed (Awards Season), so the next line can testify.
    assert {K_PICTURE, K_ACTOR, K_ACTRESS} <= families, families
    assert not {P_PICTURE, P_ACTOR, P_ACTRESS} & families, families


@pytest.mark.asyncio
async def test_the_route_keeps_a_lone_polymarket_row():
    """Control: with no Kalshi twin on the page the Polymarket row is the answer."""
    payload = await _payload([p_picture(), k_actor()])
    assert sorted(_flat_ids(payload)) == sorted([P_PICTURE, K_ACTOR])

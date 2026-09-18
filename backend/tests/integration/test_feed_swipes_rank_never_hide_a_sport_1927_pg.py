"""#1927, wide half — a "Nah" on a sport RANKS its cards; it never hides them.

Alex's ruling (2026-09-17): "a nah swipe should NOT hide the whole sport. I hate
the Yankees baseball team, and would be likely to swipe away any game card from
the Yankees, but wouldn't intend that to mean that I don't like baseball at
all. Swiping needs to be a ranking signal, not a death certificate."

This file is the ROUTE-LEVEL oracle, on a real PostgreSQL through the real
FastAPI dependencies: real ``GET /api/feed``, real ``POST /api/feed/interactions``,
real ``_load_personalization_context`` reading rows the interactions route wrote.
Every principal is SYNTHETIC — accounts, preferences and swipes are seeded here
and only here; nothing is copied from any real account.

The red it reproduces on the pinned base (``f9b8585f``): a signed-in reader whose
stored ``sport_affinities`` carry ``baseball_mlb: 0.0`` receives ZERO of the MLB
games the anonymous reader receives on ``mode=sports``, because the event gate
in ``routes/feed.py`` ``continue``s on the ``sport_nah`` reason string and, one
clause down, the admission floor reads a score that carries the same penalty.
The futures gate has the identical shape for the World Series card.

Signal provenance, traced rather than assumed (BRIEF-24): ``sport_affinities``
is written by exactly two routes — ``POST /api/user/onboarding`` and
``PUT /api/user/preferences/sport-affinities`` (``routes/user.py``). The
interactions route writes ``discover_interactions`` rows and nothing else, and
``_load_personalization_context`` reads sport affinities from ``user_preferences``
only. A swipe therefore never produces a ``sport_nah``; what it produces is the
bounded category / feature / semantic terms of CERT-2676/2681, which were already
rank-only. Whether a stored Nah came from onboarding or from a later edit cannot
be told from the row, and this file does not claim to know.

Opt-in on ``SEARCH_TEST_DATABASE_URL``, like the other real-Postgres contracts.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #1927 swipes-rank-never-hide "
            "route contract on a real Postgres (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

#: The sport the ruling was written about, and the value onboarding stores for
#: "Nah" (`followed_sport_categories` docstring: 1.0 love / 0.3 sometimes /
#: 0.1 if wild / 0.0 nah).
NAH_SPORT = "baseball_mlb"
NAH = 0.0
IF_WILD = 0.1
LOVE = 1.0

#: `x-session-id` values — the interactions route keys anonymous swipes on it,
#: and the feed's personalization context reads them back by the same header.
SESSION_A = "brief24-session-a"
SESSION_B = "brief24-session-b"

#: Every MLB game the seed makes eligible, as `_matchup` prints it.
MLB_SLATE = [
    "Marlins @ Rockies",
    "Red Sox @ Rangers",
    "Royals @ Astros",
    "Yankees @ Rays",
    "Yankees @ Twins",
]
#: The slate minus the routine scheduled game, which the "if it's wild" bar
#: refuses.
LIVE_SLATE = [m for m in MLB_SLATE if m != "Marlins @ Rockies"]


# ---------------------------------------------------------------------------
# Schema + seed
# ---------------------------------------------------------------------------


@pytest.fixture
async def pg():
    """Real Postgres, whole schema, function-scoped (loop-scope rule, see the
    static-tag gate)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield maker
    finally:
        await engine.dispose()


class Seed:
    """Row ids the tests address, filled by `_seed`."""

    sport_ids: dict[str, int]
    team_ids: dict[str, int]
    event_ids: dict[str, int]
    market_ids: dict[str, int]
    users: dict[str, "object"]


async def _seed(maker) -> Seed:
    import app.models.models as m

    now = datetime.now(timezone.utc)
    seed = Seed()
    seed.sport_ids, seed.team_ids, seed.event_ids, seed.market_ids, seed.users = (
        {},
        {},
        {},
        {},
        {},
    )
    async with maker() as s:
        for key, name in (("baseball_mlb", "MLB"), ("basketball_nba", "NBA")):
            sp = m.Sport(key=key, name=name, active=True)
            s.add(sp)
            await s.flush()
            seed.sport_ids[key] = sp.id

        mlb, nba = seed.sport_ids["baseball_mlb"], seed.sport_ids["basketball_nba"]
        for name, sid in (
            ("Yankees", mlb),
            ("Red Sox", mlb),
            ("Twins", mlb),
            ("Rangers", mlb),
            ("Royals", mlb),
            ("Astros", mlb),
            ("Rays", mlb),
            ("Rockies", mlb),
            ("Marlins", mlb),
            ("Celtics", nba),
            ("Knicks", nba),
        ):
            # Media on every team, as every MLB/NBA team has on production:
            # Discover's noise filter keeps a live game only with team media
            # (`has_team_media`), and `_build_team_lookup` admits a team on
            # `primary_color` / `logo_url_small`.
            t = m.Team(
                sport_id=sid,
                name=name,
                logo_url=f"https://img.test/{name}.png",
                logo_url_small=f"https://img.test/{name}-s.png",
                primary_color="#0C2340",
            )
            s.add(t)
            await s.flush()
            seed.team_ids[name] = t.id

        def _game(key, sid, home, away, status, hours, hs=None, as_=None):
            e = m.Event(
                sport_id=sid,
                external_id=f"brief24-{key}",
                home_team_id=seed.team_ids[home],
                away_team_id=seed.team_ids[away],
                home_team_name=home,
                away_team_name=away,
                commence_time=now + timedelta(hours=hours),
                status=status,
                home_score=hs,
                away_score=as_,
                opening_home_probability=0.55,
                opening_away_probability=0.45,
                win_probability_sources={
                    "betting": {"value": 0.55, "updated_at": now.isoformat()}
                },
                llm_importance="regular",
                event_tags=[],
                raw_ei=0.9,
            )
            if status == "live":
                e.period = "5th"
                e.game_clock = None
            if status == "completed":
                e.completed_at = now + timedelta(hours=hours) + timedelta(hours=3)
            s.add(e)
            return e

        games = {
            # Three live MLB games with media, so the Discover live arm and the
            # Sports tab both have MLB supply. Yankees is the team the ruling
            # names; Red Sox is the standing-relationship control; Royals/Astros
            # is the "unrelated MLB" control.
            "yankees_twins": _game("yt", mlb, "Twins", "Yankees", "live", -1, 3, 2),
            "redsox_rangers": _game("rr", mlb, "Rangers", "Red Sox", "live", -1, 1, 4),
            "royals_astros": _game("ra", mlb, "Astros", "Royals", "live", -1, 2, 2),
            # A SECOND Yankees game, so a swipe on one Yankees card can be
            # measured against the other Yankees card rather than only against
            # other teams.
            "yankees_rays": _game("yr", mlb, "Rays", "Yankees", "live", -1, 0, 1),
            # And an NBA game, the sport the same reader LOVES, for the rank
            # comparison.
            "celtics_knicks": _game("ck", nba, "Knicks", "Celtics", "live", -1, 50, 48),
            # CONTROLS that must stay refused for their real reasons, for every
            # principal: a game that finished outside the served window, and a
            # game with no price at all.
            "stale_final": _game("sf", mlb, "Twins", "Rangers", "completed", -40, 4, 1),
            # A ROUTINE scheduled game: served to the anonymous reader, refused
            # by the "if it's wild" bar — the control that a real eligibility
            # rule which also reads a score is untouched.
            "routine": _game("rt", mlb, "Rockies", "Marlins", "scheduled", 5),
            "unpriced": _game("up", mlb, "Astros", "Rays", "scheduled", 3),
        }
        games["routine"].raw_ei = None
        games["unpriced"].opening_home_probability = None
        games["unpriced"].opening_away_probability = None
        games["unpriced"].win_probability_sources = None
        await s.flush()
        for k, e in games.items():
            seed.event_ids[k] = e.id

        def _market(key, name, sid, category, outcomes):
            mk = m.FuturesMarket(
                source="kalshi",
                external_id=f"brief24-{key}",
                sport_id=sid,
                name=name,
                category="championship",
                llm_sport_category=category,
                market_tier=1,
                mutually_exclusive=True,
                status="open",
                resolution_date=now + timedelta(days=45),
                volume_24h=5000.0,
                market_metadata={},
                created_at=now - timedelta(days=3),
            )
            s.add(mk)
            for rank, (oname, prob, move) in enumerate(outcomes, start=1):
                s.add(
                    m.FuturesOutcome(
                        market=mk,
                        external_id=f"brief24-{key}-{rank}",
                        name=oname,
                        team_id=seed.team_ids.get(oname),
                        current_probability=prob,
                        opening_probability=max(0.01, prob - 0.03),
                        probability_change_24h=move,
                        rank=rank,
                        last_updated=now,
                    )
                )
            return mk

        markets = {
            "world_series": _market(
                "ws",
                "World Series Winner",
                mlb,
                "baseball",
                [("Yankees", 0.30, 0.04), ("Red Sox", 0.22, -0.02), ("Astros", 0.15, 0.01)],
            ),
            "nba_champ": _market(
                "nba",
                "NBA Championship Winner",
                nba,
                "basketball",
                [("Celtics", 0.35, 0.03), ("Knicks", 0.20, -0.01), ("Nuggets", 0.12, 0.0)],
            ),
            # CONTROL: a settled market stays refused for its real reason.
            "settled": _market(
                "settled",
                "2025 World Series Winner",
                mlb,
                "baseball",
                [("Dodgers", 1.0, 0.0), ("Yankees", 0.0, 0.0)],
            ),
        }
        markets["settled"].status = "settled"
        markets["settled"].settled_at = now - timedelta(days=200)
        markets["settled"].resolution_date = now - timedelta(days=200)
        await s.flush()
        for k, mk in markets.items():
            seed.market_ids[k] = mk.id

        def _user(tag, affinities, favorites=()):
            u = m.User(firebase_uid=f"brief24-{tag}", email=f"{tag}@brief24.test")
            s.add(u)
            return u, affinities, favorites

        specs = {
            # Stored explicit Nah on baseball, Love on basketball — the shape the
            # issue measured, with SYNTHETIC values.
            "nah": _user("nah", {NAH_SPORT: NAH, "basketball_nba": LOVE}),
            # Baseball simply absent — "missing preference is not an explicit
            # rejection" (BRIEF-24) — tested as its own state.
            "unset": _user("unset", {"basketball_nba": LOVE}),
            # "If it's wild" — the separate explicit control, kept as it was.
            "wild": _user("wild", {NAH_SPORT: IF_WILD, "basketball_nba": LOVE}),
            # Explicit positive interest.
            "love": _user("love", {NAH_SPORT: LOVE, "basketball_nba": LOVE}),
            # Nah on baseball PLUS a standing `local` relationship with the Red
            # Sox — the narrow #1927 fix's own specimen.
            "local": _user(
                "local", {NAH_SPORT: NAH, "basketball_nba": LOVE}, (("Red Sox", "local"),)
            ),
            # Nah on baseball PLUS a `rival` relationship — rivals are inferred,
            # not performed, and must not become a favourite.
            "rival": _user(
                "rival", {NAH_SPORT: NAH, "basketball_nba": LOVE}, (("Yankees", "rival"),)
            ),
            # Signed in, never onboarded: no preference row at all.
            "blank": _user("blank", None),
        }
        await s.flush()
        for tag, (u, affinities, favorites) in specs.items():
            if affinities is not None:
                s.add(
                    m.UserPreference(
                        user_id=u.id,
                        sport_affinities=affinities,
                        onboarding_completed=True,
                    )
                )
            for team_name, relation in favorites:
                s.add(
                    m.UserFavorite(
                        user_id=u.id,
                        team_id=seed.team_ids[team_name],
                        relation_type=relation,
                        source="onboarding",
                        weight=1.0,
                    )
                )
            seed.users[tag] = u
        await s.commit()
    return seed


@pytest.fixture
async def seed(pg):
    return await _seed(pg)


# ---------------------------------------------------------------------------
# The app, on the real dependencies, against that database
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _client(maker, user, session_id: str | None = None):
    """httpx client on the real app: real DB dependency, the given principal.

    Redis is failed deliberately so no response/shared cache can carry one
    principal's page to another — the isolation this file asserts is the
    route's own, not the cache's. Golf is stubbed empty (its base lives in
    Redis); tournaments are covered by the unit-level file beside this one.
    """
    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    async def _db():
        async with maker() as session:
            yield session

    async def _principal():
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _principal
    headers = {"x-session-id": session_id} if session_id else {}
    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch(
                "app.tasks.redis_state.get_async_redis_client",
                side_effect=RuntimeError("redis disabled: brief24 pg contract"),
            ),
            patch(
                "app.utils.request_cache.get_shared_async_redis",
                side_effect=RuntimeError("redis disabled: brief24 pg contract"),
            ),
            patch(
                "app.routes.feed._score_golf_tournaments",
                new=AsyncMock(return_value=[]),
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test", headers=headers
            ) as ac:
                yield ac
    finally:
        app.dependency_overrides.clear()


def _forget_process_caches():
    """Every request in this file is a COLD build on purpose.

    With Redis failed, the route serves a process-local last-good payload for
    a repeated key (Queue 271) — which is correct in production and would make
    the second request of a test read the first one's page. The suite's
    autouse fixture resets these stores per TEST; this file resets them per
    REQUEST, because its whole subject is what changes between two requests by
    the same principal.
    """
    from app.routes import events as _ev
    from app.utils import candidate_base as _cb
    from app.utils import request_cache as _rc
    from app.utils.principal_independent_cache import clear_shared_builds

    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _cb._reset_l0_for_tests()
    clear_shared_builds()
    # Brief24A: the team lookup (`routes/events._team_cache`, keyed by team
    # NAME, 5-min TTL) is process-global too. The sibling 1927a file seeds a
    # media-less "Rockies"/"Marlins"; whichever file ran first would otherwise
    # decide `has_team_media` for both.
    _ev._team_cache = {}
    _ev._team_cache_time = 0


async def _feed(maker, user, *, session_id=None, **params) -> list[dict]:
    _forget_process_caches()
    q = {"limit": 50, "offset": 0, **params}
    async with _client(maker, user, session_id) as ac:
        resp = await ac.get("/api/feed", params=q)
    assert resp.status_code == 200, resp.text[:500]
    return resp.json()["items"]


def _events(items):
    return [it for it in items if it["type"] == "event"]


def _futures(items):
    return [it for it in items if it["type"] == "futures"]


def _sport_of(item) -> str | None:
    d = item.get("data") or {}
    return d.get("sport_key") or d.get("sport")


def _matchup(item) -> str:
    d = item["data"]
    return f"{d.get('away_team')} @ {d.get('home_team')}"


def _mlb_events(items):
    return [e for e in _events(items) if _sport_of(e) == NAH_SPORT]


async def _swipe(maker, user, session_id, cards: list[dict]):
    """Drive the REAL interactions route — the only writer of swipe rows."""
    async with _client(maker, user, session_id) as ac:
        resp = await ac.post(
            "/api/feed/interactions",
            json={
                "interactions": [
                    {
                        "action": "dismiss",
                        "item_type": c["type"],
                        "item_id": str(c["id"]),
                        "category": c["category"],
                        "item_name": c["name"],
                        "surface": "native",
                    }
                    for c in cards
                ]
            },
        )
    assert resp.status_code == 200, resp.text[:500]
    assert resp.json()["recorded"] == len(cards)


# ---------------------------------------------------------------------------
# The red on base, and the ship
# ---------------------------------------------------------------------------


async def test_the_anonymous_reader_is_served_the_mlb_games(seed, pg):
    """The premise every arm below stands on: the seed IS served to someone.

    If this is empty the harness is dropping the games for a reason of its own
    and no signed-in assertion in this file means anything."""
    items = await _feed(pg, None, mode="sports")
    got = sorted(_matchup(e) for e in _mlb_events(items))
    assert got == MLB_SLATE, got


async def test_a_stored_nah_on_baseball_no_longer_deletes_the_mlb_games(seed, pg):
    """THE SHIP, at the actual route. RED on the pinned base: `[]`.

    The reader stores `baseball_mlb: 0.0`. Before: the event gate `continue`d on
    the `sport_nah` reason and every MLB game vanished from the Sports tab.
    After: the same three games are served, ranked below the basketball the
    reader loves."""
    items = await _feed(pg, seed.users["nah"], mode="sports")
    got = sorted(_matchup(e) for e in _mlb_events(items))
    assert got == MLB_SLATE, (
        f"a stored Nah on {NAH_SPORT} deleted the sport's games: served {got}"
    )


async def test_the_nah_is_still_a_ranking_signal_at_the_route(seed, pg):
    """Not inert: the loved sport's game outranks every Nah-sport game, and the
    Nah-sport games' served scores sit below the anonymous reader's."""
    anon = {_matchup(e): e["score"] for e in _events(await _feed(pg, None, mode="sports"))}
    items = await _feed(pg, seed.users["nah"], mode="sports")
    order = [_matchup(e) for e in _events(items)]
    assert order[0] == "Celtics @ Knicks", order
    assert len(_mlb_events(items)) == len(MLB_SLATE), "vacuous: no MLB served"
    for e in _mlb_events(items):
        assert e["score"] < anon[_matchup(e)], (
            f"{_matchup(e)}: Nah reader scored {e['score']}, anonymous {anon[_matchup(e)]}"
        )


async def _prefs_of(pg, user) -> dict:
    from sqlalchemy import select

    import app.models.models as m

    async with pg() as s:
        row = (
            await s.execute(select(m.UserPreference).where(m.UserPreference.user_id == user.id))
        ).scalar_one_or_none()
        return dict(row.sport_affinities or {}) if row else {}


# ---------------------------------------------------------------------------
# Control 1 — Yankees swipes, through the real interactions route
# ---------------------------------------------------------------------------


async def test_a_yankees_swipe_hides_that_card_keeps_baseball_and_writes_no_preference(
    seed, pg
):
    """Alex's own scenario, on the real write path.

    The reader (stored Nah on baseball, so the same reader the ship is for)
    dismisses the Yankees @ Twins card. Afterwards: that exact card obeys its
    scoped dismissal; the OTHER Yankees game, the Red Sox game and the
    unrelated MLB game are all still served; and `user_preferences` is
    byte-for-byte what it was — a swipe is not a sport-level declaration.
    """
    user = seed.users["nah"]
    before = await _prefs_of(pg, user)
    page = await _feed(pg, user, session_id=SESSION_A, mode="sports")
    target = next(e for e in _mlb_events(page) if _matchup(e) == "Yankees @ Twins")

    await _swipe(
        pg,
        user,
        SESSION_A,
        [
            {
                "type": "event",
                "id": target["data"]["id"],
                "category": "baseball",
                "name": "Yankees vs Twins",
            }
        ],
    )

    after = await _feed(pg, user, session_id=SESSION_A, mode="sports")
    got = sorted(_matchup(e) for e in _mlb_events(after))
    assert got == [m for m in MLB_SLATE if m != "Yankees @ Twins"], got
    assert await _prefs_of(pg, user) == before, "a swipe rewrote sport_affinities"


async def test_what_a_yankees_swipe_actually_learns_is_bounded_and_not_team_targeted(
    seed, pg
):
    """Measured, not claimed (BRIEF-24: "do not overclaim targeted team learning
    if it doesn't exist").

    One dismissed Yankees card leaves a bounded feature dislike behind
    (`FEATURE_DISLIKE_MAX_PENALTY`, -0.25) — and because the card's tokens are
    mostly GENERIC (`category:baseball`, `type:event`, `format:matchup`, the
    archetype), the other Yankees game and the Red Sox game receive the SAME
    bounded term. The only Yankees-specific learner is the semantic-resemblance
    penalty, which fires on a near-identical matchup, not on "any Yankees card".
    This test pins that honestly: every remaining MLB card ranks below where it
    ranked before the swipe, by a bounded amount, and none is removed.
    """
    from app.utils.personalization import FEATURE_DISLIKE_MAX_PENALTY

    user = seed.users["nah"]
    before = {
        _matchup(e): e for e in _mlb_events(await _feed(pg, user, session_id=SESSION_A, mode="sports"))
    }
    await _swipe(
        pg,
        user,
        SESSION_A,
        [
            {
                "type": "event",
                "id": before["Yankees @ Twins"]["data"]["id"],
                "category": "baseball",
                "name": "Yankees vs Twins",
            }
        ],
    )
    after = {
        _matchup(e): e for e in _mlb_events(await _feed(pg, user, session_id=SESSION_A, mode="sports"))
    }
    for name in ("Yankees @ Rays", "Red Sox @ Rangers", "Royals @ Astros"):
        assert name in after, f"{name} was removed by a swipe on another card"
        reasons = after[name].get("personalization_reasons", [])
        assert any(r.startswith("discover_feature_dislike") for r in reasons), reasons
        assert after[name]["score"] <= before[name]["score"]
        # bounded: the multiplier moved by no more than the feature cap (plus
        # the category term's first rung, which a single swipe cannot reach).
        assert after[name]["multiplier"] >= before[name]["multiplier"] + FEATURE_DISLIKE_MAX_PENALTY - 0.01


async def test_anonymous_session_swipes_are_scoped_to_that_session(seed, pg):
    """The session-only principal: the swipe is keyed on `x-session-id`, the
    dismissed card is hidden for THAT session, baseball stays, and a different
    session sees the untouched slate."""
    page = await _feed(pg, None, session_id=SESSION_A, mode="sports")
    target = next(e for e in _mlb_events(page) if _matchup(e) == "Yankees @ Twins")
    await _swipe(
        pg,
        None,
        SESSION_A,
        [{"type": "event", "id": target["data"]["id"], "category": "baseball", "name": "Yankees vs Twins"}],
    )
    a = sorted(_matchup(e) for e in _mlb_events(await _feed(pg, None, session_id=SESSION_A, mode="sports")))
    b = sorted(_matchup(e) for e in _mlb_events(await _feed(pg, None, session_id=SESSION_B, mode="sports")))
    assert a == [m for m in MLB_SLATE if m != "Yankees @ Twins"], a
    assert b == MLB_SLATE, b


# ---------------------------------------------------------------------------
# Control 2 — repeated dislikes cannot become a whole-sport exclusion
# ---------------------------------------------------------------------------


async def test_eight_baseball_dismisses_plus_a_stored_nah_still_serve_baseball(seed, pg):
    """The escalated category floor (-0.80 at eight negative swipes, #5453)
    stacked on the sport Nah (-0.60) clamps the multiplier to its minimum —
    and the cards are STILL eligible. Eligibility, order and page inclusion
    are read separately: eligibility from the unpaged `total`, order from the
    served list, inclusion from a deliberately small page.
    """
    user = seed.users["nah"]
    # Eight dismissals of baseball cards that are NOT on the slate, so the
    # scoped per-card dismissal cannot be what removes anything.
    await _swipe(
        pg,
        user,
        SESSION_A,
        [
            {"type": "event", "id": 900000 + i, "category": "baseball", "name": f"Team{i} vs Team{i + 1}"}
            for i in range(8)
        ],
    )
    full = await _feed(pg, user, session_id=SESSION_A, mode="sports", limit=50)
    mlb = _mlb_events(full)
    assert sorted(_matchup(e) for e in mlb) == MLB_SLATE, "eligibility: a card was excluded"
    reasons = mlb[0]["personalization_reasons"]
    assert any(r.startswith("discover_dismiss") for r in reasons), reasons
    assert any(r.startswith("sport_nah") for r in reasons), reasons
    # order: every MLB card sits below the loved sport's game and its future
    order = [(it["type"], _sport_of(it)) for it in full]
    first_mlb = next(i for i, (t, sk) in enumerate(order) if t == "event" and sk == NAH_SPORT)
    assert first_mlb > order.index(("event", "basketball_nba")), order
    # page inclusion: a two-card page does not reach them, and that is a finite
    # page, not an exclusion — the next pages do.
    page1 = await _feed(pg, user, session_id=SESSION_A, mode="sports", limit=2)
    assert not _mlb_events(page1)
    seen = []
    for offset in range(0, len(full) + 2, 2):
        seen += [_matchup(e) for e in _mlb_events(await _feed(pg, user, session_id=SESSION_A, mode="sports", limit=2, offset=offset))]
    assert sorted(seen) == MLB_SLATE, seen


# ---------------------------------------------------------------------------
# Control 3 — the distinct states, at the route
# ---------------------------------------------------------------------------


async def test_the_four_preference_states_are_distinct_at_the_route(seed, pg):
    anon = {_matchup(e): e["score"] for e in _mlb_events(await _feed(pg, None, mode="sports"))}
    pages = {
        tag: {_matchup(e): e for e in _mlb_events(await _feed(pg, seed.users[tag], mode="sports"))}
        for tag in ("nah", "unset", "wild", "love", "blank")
    }
    for tag in ("nah", "unset", "love", "blank"):
        assert sorted(pages[tag]) == MLB_SLATE, f"{tag}: {sorted(pages[tag])}"
    assert sorted(pages["wild"]) == LIVE_SLATE  # the bar, see the next test
    for name in LIVE_SLATE:
        # Nah and missing rank down; "if it's wild" ranks down less; love ranks
        # up (capped at the display ceiling); a never-onboarded reader is the
        # anonymous reader.
        assert pages["nah"][name]["score"] < pages["wild"][name]["score"] <= anon[name]
        assert pages["unset"][name]["score"] < pages["wild"][name]["score"]
        assert pages["love"][name]["score"] >= anon[name]
        assert pages["blank"][name]["score"] == anon[name]
        assert "personalized" not in pages["blank"][name]


async def test_if_its_wild_keeps_its_bar_at_the_route(seed, pg):
    """The seed's live MLB games clear the 55 bar for the "if it's wild" reader
    (67 = 97 * 0.7); the routine scheduled game does not, and is refused — the
    bar is a real rule and this ship did not touch it. The Nah reader, by
    contrast, gets the routine game: ranked at the bottom, not refused."""
    wild = {_matchup(e) for e in _mlb_events(await _feed(pg, seed.users["wild"], mode="sports"))}
    anon = {_matchup(e) for e in _mlb_events(await _feed(pg, None, mode="sports"))}
    nah = {_matchup(e) for e in _mlb_events(await _feed(pg, seed.users["nah"], mode="sports"))}
    assert "Marlins @ Rockies" in anon, "the control game left the anonymous slate — it is testing nothing"
    assert "Marlins @ Rockies" not in wild, "the 'if it's wild' bar stopped biting"
    assert wild == set(LIVE_SLATE), wild
    assert "Marlins @ Rockies" in nah


async def test_standing_and_rival_relationships_in_a_nah_sport(seed, pg):
    local = {_matchup(e): e for e in _mlb_events(await _feed(pg, seed.users["local"], mode="sports"))}
    rival = {_matchup(e): e for e in _mlb_events(await _feed(pg, seed.users["rival"], mode="sports"))}
    assert sorted(local) == MLB_SLATE and sorted(rival) == MLB_SLATE
    # the narrow #1927 fix, preserved: the local team's game outranks the rest
    assert local["Red Sox @ Rangers"]["score"] > local["Royals @ Astros"]["score"]
    assert any(r.startswith("local_team") for r in local["Red Sox @ Rangers"]["personalization_reasons"])
    # a rival is not a favourite: its term is the rival term, never a standing one
    for name in ("Yankees @ Twins", "Yankees @ Rays"):
        reasons = rival[name]["personalization_reasons"]
        assert any(r.startswith("rival_") for r in reasons), reasons
        assert not any(r.startswith(("your_team", "local_team", "alma_mater")) for r in reasons)


# ---------------------------------------------------------------------------
# Control 4 — futures and the real refusals
# ---------------------------------------------------------------------------


async def test_the_world_series_card_is_served_to_the_nah_reader_on_discover(seed, pg):
    """RED on base in Discover mode: the futures gate `continue`d on
    `sport_nah`. (On `mode=sports` it was already served at 38 — that path had
    only the 15 floor, which 95 * 0.4 clears.)"""
    for params in ({}, {"mode": "sports"}):
        items = await _feed(pg, seed.users["nah"], **params)
        ws = [f for f in _futures(items) if f["data"]["name"] == "World Series Winner"]
        assert len(ws) == 1, f"{params}: {[f['data']['name'] for f in _futures(items)]}"
        assert any(r.startswith("sport_nah") for r in ws[0]["personalization_reasons"])
        nba = next(f for f in _futures(items) if f["data"]["name"] == "NBA Championship Winner")
        assert ws[0]["score"] < nba["score"]


async def test_the_real_refusals_still_refuse_for_everyone(seed, pg):
    """A settled market, a stale final and an unpriced game are refused for
    their own reasons — for the anonymous reader and for the Nah reader alike.
    Lifting the Nah filter did not lift anything else."""
    for user in (None, seed.users["nah"], seed.users["love"]):
        for params in ({}, {"mode": "sports"}):
            items = await _feed(pg, user, **params)
            names = {f["data"]["name"] for f in _futures(items)}
            assert "2025 World Series Winner" not in names, names
            matchups = {_matchup(e) for e in _events(items)}
            assert "Rangers @ Twins" not in matchups, matchups  # stale final
            assert "Rays @ Astros" not in matchups, matchups  # unpriced


async def test_the_anonymous_reader_is_unchanged_on_discover_too(seed, pg):
    items = await _feed(pg, None)
    assert sorted(_matchup(e) for e in _mlb_events(items)) == MLB_SLATE
    assert all("personalized" not in it for it in items)


# ---------------------------------------------------------------------------
# Control 5 — pagination and principal isolation
# ---------------------------------------------------------------------------


async def test_pages_over_one_pool_have_no_duplicates_and_no_loss(seed, pg):
    user = seed.users["nah"]
    full = await _feed(pg, user, mode="sports", limit=50)
    keys = [(it["type"], it["data"].get("id") or it["data"].get("key")) for it in full]
    assert len(keys) == len(set(keys)), "duplicate on the unpaged list"
    paged = []
    for offset in range(0, len(full) + 3, 3):
        page = await _feed(pg, user, mode="sports", limit=3, offset=offset)
        paged += [(it["type"], it["data"].get("id") or it["data"].get("key")) for it in page]
    assert paged == keys, "paging reordered, duplicated or lost a card"


async def test_one_principal_s_page_never_leaks_into_another_s(seed, pg):
    """Nah, then love, then anonymous, then Nah again — each must read as
    itself. With the response cache failed deliberately this is the route's
    own isolation; with it live, the cache key carries the principal
    (`feed_response_cache_key(user_id=…)`)."""
    nah1 = [e["score"] for e in _mlb_events(await _feed(pg, seed.users["nah"], mode="sports"))]
    love = [e["score"] for e in _mlb_events(await _feed(pg, seed.users["love"], mode="sports"))]
    anon = [e["score"] for e in _mlb_events(await _feed(pg, None, mode="sports"))]
    nah2 = [e["score"] for e in _mlb_events(await _feed(pg, seed.users["nah"], mode="sports"))]
    assert nah1 == nah2
    assert max(nah1) < min(anon) <= min(love)

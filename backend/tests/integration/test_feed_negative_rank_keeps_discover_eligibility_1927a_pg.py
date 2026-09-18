"""#1927, Brief24A — a negative rank term never becomes a Discover exclusion.

Brief24 retired the two direct ``sport_nah`` filters and separated admission
from ranking at the event and futures gates. Its own report then reproduced one
more exclusion, one layer down: Discover's editorial chain decides whether a
live game is "exceptional" by reading the item's PERSONALIZED score
(``_discover_event_excitement_score`` → ``item["score"]``). For a reader whose
only negative signal is a stored Nah, or eight dismissed baseball cards, a
97-point live game arrives at that predicate as 38 (or 19), is judged "not
exceptional", is capped to 35, and — when its teams carry no media — is DELETED
by ``_filter_discover_event_noise`` while the identical anonymous candidate is
kept through the excitement exception. That is the "equivalent exclusion
through a downstream admission/quality floor fed the same negative signal"
Alex's ruling names.

This file is the route-level oracle for the completion: real ``GET /api/feed``
on a real PostgreSQL through the real dependencies, real
``POST /api/feed/interactions`` for the swipe arm, every principal SYNTHETIC.
Golf is seeded at its I/O boundary (``get_golf_base``, the provider-cache read
the route already treats as its source of truth) and UFC from open
``futures_markets`` rows, so both keyed card types travel the real scorer,
dismissal pass, affinity pass and display chain.

RED on Brief24 (base ``ad7bacef`` + its ``proposed.diff``): the four
``*_is_served_on_discover`` arms and the two positive-behaviour keyed arms.
Green on revision-a. Opt-in on ``SEARCH_TEST_DATABASE_URL`` like the other
real-Postgres contracts.
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
            "set SEARCH_TEST_DATABASE_URL to run the #1927 Brief24A eligibility "
            "route contract on a real Postgres (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

NAH_SPORT = "baseball_mlb"
NAH, IF_WILD, SOMETIMES, LOVE = 0.0, 0.1, 0.3, 1.0
SESSION_A = "brief24a-session-a"
SESSION_B = "brief24a-session-b"

#: THE SUBJECT — a live, close MLB game whose teams carry no media.
SUBJECT = "Marlins @ Rockies"
#: Live MLB game with team media — kept by the live-arm for everyone; a control.
MEDIA_LIVE = "Yankees @ Twins"
#: The loved sport's live game.
NBA_LIVE = "Celtics @ Knicks"
#: Genuinely ineligible no-media games: a live blowout that is not exceptional
#: for anyone, and a routine scheduled game. Both must stay OFF Discover for the
#: neutral AND the negative reader.
BLOWOUT = "Reds @ Pirates"
ROUTINE = "Tigers @ Guardians"

UFC_NAME_PREFIX = "UFC 330"
PGA_KEY = "golf:brief24a-pga"
LPGA_KEY = "golf:brief24a-lpga"
UNKNOWN_TOUR_KEY = "golf:brief24a-unknown"


# ---------------------------------------------------------------------------
# Schema + seed
# ---------------------------------------------------------------------------


@pytest.fixture
async def pg():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401
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
    sport_ids: dict[str, int]
    team_ids: dict[str, int]
    event_ids: dict[str, int]
    users: dict[str, object]


async def _seed(maker) -> Seed:
    import app.models.models as m

    now = datetime.now(timezone.utc)
    seed = Seed()
    seed.sport_ids, seed.team_ids, seed.event_ids, seed.users = {}, {}, {}, {}
    async with maker() as s:
        for key, name in (
            ("baseball_mlb", "MLB"),
            ("basketball_nba", "NBA"),
            ("mma_mixed_martial_arts", "MMA"),
        ):
            sp = m.Sport(key=key, name=name, active=True)
            s.add(sp)
            await s.flush()
            seed.sport_ids[key] = sp.id
        mlb, nba, mma = (
            seed.sport_ids["baseball_mlb"],
            seed.sport_ids["basketball_nba"],
            seed.sport_ids["mma_mixed_martial_arts"],
        )

        def _team(name, sid, media: bool):
            t = m.Team(
                sport_id=sid,
                name=name,
                logo_url=f"https://img.test/{name}.png" if media else None,
                logo_url_small=f"https://img.test/{name}-s.png" if media else None,
                primary_color="#0C2340" if media else None,
            )
            s.add(t)
            return t

        teams = {
            # WITH media
            "Yankees": _team("Yankees", mlb, True),
            "Twins": _team("Twins", mlb, True),
            "Celtics": _team("Celtics", nba, True),
            "Knicks": _team("Knicks", nba, True),
            # WITHOUT media — `_build_team_lookup` admits a team on
            # `primary_color` / `logo_url_small`; these have neither, so
            # `has_team_media` is False for their games.
            "Marlins": _team("Marlins", mlb, False),
            "Rockies": _team("Rockies", mlb, False),
            "Reds": _team("Reds", mlb, False),
            "Pirates": _team("Pirates", mlb, False),
            "Tigers": _team("Tigers", mlb, False),
            "Guardians": _team("Guardians", mlb, False),
        }
        await s.flush()
        for name, t in teams.items():
            seed.team_ids[name] = t.id

        def _game(key, sid, home, away, status, hours, hs=None, as_=None, ei=0.9, prob=0.55):
            e = m.Event(
                sport_id=sid,
                external_id=f"brief24a-{key}",
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
                    "betting": {"value": prob, "updated_at": now.isoformat()}
                },
                llm_importance="regular",
                event_tags=[],
                raw_ei=ei,
            )
            if status == "live":
                e.period = "5th"
                e.game_clock = None
            s.add(e)
            return e

        games = {
            "subject": _game("subject", mlb, "Rockies", "Marlins", "live", -1, 3, 2),
            "media_live": _game("ml", mlb, "Twins", "Yankees", "live", -1, 3, 2),
            "nba_live": _game("nba", nba, "Knicks", "Celtics", "live", -1, 50, 48),
            "blowout": _game("bo", mlb, "Pirates", "Reds", "live", -1, 11, 0, ei=0.2, prob=0.97),
            "routine": _game("rt", mlb, "Guardians", "Tigers", "scheduled", 30, ei=None, prob=0.8),
        }
        await s.flush()
        for k, e in games.items():
            seed.event_ids[k] = e.id

        # UFC card: three open Kalshi fight markets sharing one card date-token
        # — the real `list_ufc_card_concepts` groups them into ONE concept and
        # `_attach_headline_bouts` reads the main event's two priced sides.
        token = (now + timedelta(days=2)).strftime("%y%b%d").upper()
        bouts = (("Kape", "Van", 0.62), ("Pantoja", "Moreno", 0.55), ("Holloway", "Oliveira", 0.51))
        for i, (a, b, pa) in enumerate(bouts):
            mk = m.FuturesMarket(
                source="kalshi",
                external_id=f"kalshi:KXUFCFIGHT-{token}{a[:3].upper()}{b[:3].upper()}",
                sport_id=mma,
                name=f"{a} vs {b}",
                category="fight",
                llm_sport_category="mma",
                market_tier=2,
                mutually_exclusive=True,
                status="open",
                resolution_date=now + timedelta(days=2),
                commence_time=now + timedelta(days=2, hours=i),
                volume_24h=3000.0,
                market_metadata={"event_title": UFC_NAME_PREFIX},
                created_at=now - timedelta(days=3),
            )
            s.add(mk)
            for rank, (n, p) in enumerate(((a, pa), (b, round(1 - pa, 2))), start=1):
                s.add(
                    m.FuturesOutcome(
                        market=mk,
                        external_id=f"{mk.external_id}-{rank}",
                        name=n,
                        current_probability=p,
                        opening_probability=p,
                        probability_change_24h=0.0,
                        rank=rank,
                        last_updated=now,
                    )
                )

        def _user(tag, affinities):
            u = m.User(firebase_uid=f"brief24a-{tag}", email=f"{tag}@brief24a.test")
            s.add(u)
            return u, affinities

        specs = {
            # Stored Nah on baseball, MMA and the PGA Tour; loves the NBA and
            # the LPGA — SYNTHETIC values in the shape onboarding stores.
            "nah": _user(
                "nah",
                {
                    NAH_SPORT: NAH,
                    "basketball_nba": LOVE,
                    "mma_mixed_martial_arts": NAH,
                    "golf_pga": NAH,
                    "golf_lpga": LOVE,
                },
            ),
            # Every other sport simply absent — "missing preference is not an
            # explicit rejection", tested as its own state.
            "unset": _user("unset", {"basketball_nba": LOVE}),
            # Explicit positive interest everywhere.
            "love": _user(
                "love",
                {
                    NAH_SPORT: LOVE,
                    "basketball_nba": LOVE,
                    "mma_mixed_martial_arts": LOVE,
                    "golf_pga": LOVE,
                    "golf_lpga": LOVE,
                },
            ),
            # "If it's wild": the separate explicit control.
            "wild": _user("wild", {NAH_SPORT: IF_WILD, "basketball_nba": LOVE}),
            # NEUTRAL sport dial (0.3 = "sometimes", between both thresholds):
            # the reader whose ONLY negative signal will be swipes.
            "swiper": _user("swiper", {NAH_SPORT: SOMETIMES, "basketball_nba": SOMETIMES}),
            # Signed in, never onboarded.
            "blank": _user("blank", None),
        }
        await s.flush()
        for tag, (u, affinities) in specs.items():
            if affinities is not None:
                s.add(
                    m.UserPreference(
                        user_id=u.id, sport_affinities=affinities, onboarding_completed=True
                    )
                )
            seed.users[tag] = u
        await s.commit()
    return seed


@pytest.fixture
async def seed(pg):
    return await _seed(pg)


def _golf_base(now: datetime) -> list[dict]:
    """Synthetic golf base in the shape `get_golf_base` publishes (Queue 278):
    a live PGA Tour event, a live LPGA event, and one whose tour the base could
    not evidence (`tour: None`, UX-P185)."""

    def _t(key, name, tour, tour_label):
        start = now - timedelta(days=1)
        end = now + timedelta(days=2)
        return {
            "key": key,
            "name": name,
            "slug": key.split(":")[-1],
            "tour": tour,
            "tour_label": tour_label,
            "is_major": False,
            "is_tour_event": True,
            "venue": "Test Course",
            "location": "Nowhere, CA",
            "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat(),
            "schedule_status": "in-progress",
            "commence_time": start.isoformat(),
            "resolution_date": end.isoformat(),
            "golfers": [
                {"name": "A. Golfer", "probability": 0.18, "rank": 1, "movement_24h": 0.01},
                {"name": "B. Golfer", "probability": 0.12, "rank": 2, "movement_24h": -0.01},
                {"name": "C. Golfer", "probability": 0.09, "rank": 3, "movement_24h": 0.0},
            ],
            "market_ids": [],
            "market_names": [f"{name} Winner"],
            "market_sources": ["kalshi"],
        }

    return [
        _t(PGA_KEY, "Brief24A Open", "pga", "PGA Tour"),
        _t(LPGA_KEY, "Brief24A LPGA Classic", "lpga", "LPGA Tour"),
        _t(UNKNOWN_TOUR_KEY, "Brief24A Invitational", None, None),
    ]


# ---------------------------------------------------------------------------
# The app, on the real dependencies, against that database
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _client(maker, user, session_id: str | None = None):
    """Real app, real DB dependency, the given principal; Redis failed so no
    cache can carry one principal's page to another. Golf is SEEDED at its I/O
    boundary — `get_golf_base` is the provider-cache read `_score_golf_tournaments`
    already trusts — so the real tournament scorer, dismissal pass, affinity
    pass and display chain all run."""
    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    async def _db():
        async with maker() as session:
            yield session

    async def _principal():
        return user

    now = datetime.now(timezone.utc)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_db_rw] = _db
    app.dependency_overrides[get_optional_user] = _principal
    headers = {"x-session-id": session_id} if session_id else {}
    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch(
                "app.tasks.redis_state.get_async_redis_client",
                side_effect=RuntimeError("redis disabled: brief24a pg contract"),
            ),
            patch(
                "app.utils.request_cache.get_shared_async_redis",
                side_effect=RuntimeError("redis disabled: brief24a pg contract"),
            ),
            patch(
                "app.utils.golf_base.get_golf_base",
                new=AsyncMock(return_value=(_golf_base(now), "fresh")),
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test", headers=headers
            ) as ac:
                yield ac
    finally:
        app.dependency_overrides.clear()


def _forget_process_caches():
    """Every request is a COLD build (see the Brief24 sibling file).

    Plus the team lookup: `routes/events._team_cache` is a 5-minute process
    cache keyed by team NAME, and this file's whole subject is a team with NO
    media that shares its name with a media-bearing team in the sibling file.
    Left alone, whichever file ran first would decide `has_team_media` for both."""
    from app.routes import events as _ev
    from app.utils import candidate_base as _cb
    from app.utils import request_cache as _rc
    from app.utils.principal_independent_cache import clear_shared_builds

    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _cb._reset_l0_for_tests()
    clear_shared_builds()
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


def _matchup(item) -> str:
    d = item["data"]
    return f"{d.get('away_team')} @ {d.get('home_team')}"


def _by_matchup(items) -> dict[str, dict]:
    return {_matchup(e): e for e in _events(items)}


def _concept(items) -> dict | None:
    return next((it for it in items if it["type"] == "concept"), None)


def _tournaments(items) -> dict[str, dict]:
    return {it["data"]["key"]: it for it in items if it["type"] == "tournament"}


async def _swipe(maker, user, session_id, cards: list[dict]):
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


EIGHT_BASEBALL_DISMISSES = [
    {"type": "event", "id": 900000 + i, "category": "baseball", "name": f"Team{i} vs Team{i + 1}"}
    for i in range(8)
]


# ---------------------------------------------------------------------------
# Premise
# ---------------------------------------------------------------------------


async def test_the_anonymous_reader_keeps_the_no_media_live_game_on_discover(seed, pg):
    """The premise: for the neutral reader the subject clears Discover's
    excitement exception (score >= 80 with major-league context) and survives
    the noise filter WITHOUT team media. If this fails nothing below means anything."""
    got = _by_matchup(await _feed(pg, None))
    assert SUBJECT in got, sorted(got)
    assert got[SUBJECT]["score"] >= 80, got[SUBJECT]["score"]
    assert not (got[SUBJECT]["data"].get("home_team_data") or got[SUBJECT]["data"].get("away_team_data"))
    assert MEDIA_LIVE in got and NBA_LIVE in got
    # the genuinely ineligible no-media games are NOT on Discover for anyone
    assert BLOWOUT not in got and ROUTINE not in got, sorted(got)


# ---------------------------------------------------------------------------
# The reds on Brief24: negative RANK terms became a Discover EXCLUSION
# ---------------------------------------------------------------------------


async def test_a_stored_nah_reader_s_no_media_live_game_is_served_on_discover(seed, pg):
    """RED on Brief24: the Nah reader's subject arrives at the demotion
    predicate as 38, is capped to 35, and is deleted for lacking media.
    Eligibility must match the anonymous reader; the rank must not."""
    anon = _by_matchup(await _feed(pg, None))
    nah = _by_matchup(await _feed(pg, seed.users["nah"]))
    assert SUBJECT in nah, f"the Nah reader lost the no-media live game: {sorted(nah)}"
    assert nah[SUBJECT]["score"] < anon[SUBJECT]["score"], "the Nah stopped ranking"
    assert any(r.startswith("sport_nah") for r in nah[SUBJECT]["personalization_reasons"])
    assert MEDIA_LIVE in nah and NBA_LIVE in nah
    assert nah[NBA_LIVE]["score"] > nah[SUBJECT]["score"]


async def test_a_missing_preference_reader_s_no_media_live_game_is_served_on_discover(seed, pg):
    anon = _by_matchup(await _feed(pg, None))
    unset = _by_matchup(await _feed(pg, seed.users["unset"]))
    assert SUBJECT in unset, sorted(unset)
    assert unset[SUBJECT]["score"] < anon[SUBJECT]["score"]


async def test_persisted_swipe_feedback_alone_cannot_exclude_the_no_media_live_game(seed, pg):
    """RED on Brief24, the SWIPE arm, separately from the stored Nah: a reader
    with a NEUTRAL sport dial dismisses eight baseball cards not on the slate
    through the real interactions route. The escalated category term (-0.80)
    puts the subject at 19 → "not exceptional" → capped → deleted. It must
    instead be served, at the bottom, with the swipe term visible in its rank."""
    user = seed.users["swiper"]
    before = _by_matchup(await _feed(pg, user, session_id=SESSION_A))
    assert SUBJECT in before and "personalized" not in before[SUBJECT], "neutral premise broken"
    await _swipe(pg, user, SESSION_A, EIGHT_BASEBALL_DISMISSES)
    after = _by_matchup(await _feed(pg, user, session_id=SESSION_A))
    assert SUBJECT in after, f"eight swipes deleted the no-media live game: {sorted(after)}"
    reasons = after[SUBJECT]["personalization_reasons"]
    assert any(r.startswith("discover_dismiss") for r in reasons), reasons
    assert after[SUBJECT]["score"] < before[SUBJECT]["score"]
    assert after[NBA_LIVE]["score"] > after[SUBJECT]["score"]
    # a swipe never wrote a sport preference
    assert not any(r.startswith("sport_nah") for r in reasons), reasons


async def test_repeat_negative_feedback_on_top_of_a_stored_nah_still_serves_it(seed, pg):
    """Both negative signals at once: multiplier clamped at its minimum, card
    still eligible on Discover, ranked last among the games, reached by paging."""
    user = seed.users["nah"]
    await _swipe(pg, user, SESSION_A, EIGHT_BASEBALL_DISMISSES)
    full = await _feed(pg, user, session_id=SESSION_A, limit=50)
    got = _by_matchup(full)
    assert SUBJECT in got, sorted(got)
    reasons = got[SUBJECT]["personalization_reasons"]
    assert any(r.startswith("discover_dismiss") for r in reasons)
    assert any(r.startswith("sport_nah") for r in reasons)
    order = [_matchup(e) for e in _events(full)]
    assert order[-1] == SUBJECT or got[SUBJECT]["score"] <= min(e["score"] for e in _events(full)), order
    seen: list[str] = []
    for offset in range(0, len(full) + 3, 3):
        page = await _feed(pg, user, session_id=SESSION_A, limit=3, offset=offset)
        seen += [_matchup(e) for e in _events(page)]
    assert SUBJECT in seen, "a finite page is not an exclusion — paging must reach it"


# ---------------------------------------------------------------------------
# Controls that must hold on BOTH trees
# ---------------------------------------------------------------------------


async def test_genuinely_ineligible_no_media_games_still_fail_for_every_reader(seed, pg):
    """No generic no-media exemption: the live blowout and the routine scheduled
    game are not exceptional for the neutral reader, and lifting the negative
    reader's exclusion must not admit them for anyone."""
    for tag in (None, "nah", "unset", "love", "swiper", "blank"):
        user = seed.users[tag] if tag else None
        got = _by_matchup(await _feed(pg, user))
        assert BLOWOUT not in got, f"{tag}: {sorted(got)}"
        assert ROUTINE not in got, f"{tag}: {sorted(got)}"


async def test_the_positive_eligibility_exceptions_are_preserved(seed, pg):
    """A loved sport's boost still lifts a game INTO the exception (base_score
    was never substituted): the love reader keeps the subject at or above the
    anonymous score, and the never-onboarded reader IS the anonymous reader."""
    anon = _by_matchup(await _feed(pg, None))
    love = _by_matchup(await _feed(pg, seed.users["love"]))
    blank = _by_matchup(await _feed(pg, seed.users["blank"]))
    assert SUBJECT in love and love[SUBJECT]["score"] >= anon[SUBJECT]["score"]
    assert any(r.startswith("sport_boost") for r in love[SUBJECT]["personalization_reasons"])
    assert sorted(blank) == sorted(anon)
    assert blank[SUBJECT]["score"] == anon[SUBJECT]["score"]
    assert "personalized" not in blank[SUBJECT]


async def test_if_its_wild_keeps_its_own_higher_bar_on_discover(seed, pg):
    """The explicit "only if it's wild" control is NOT a rank-only term: its
    penalty stays inside the admission number, so the subject (97 × 0.7 = 67)
    does not clear Discover's 80/85 excitement bar for that reader. Pre-existing,
    unchanged by this revision, and pinned so the repair cannot be mistaken for
    a blanket no-media exemption. The media game survives via the live arm."""
    wild = _by_matchup(await _feed(pg, seed.users["wild"]))
    assert SUBJECT not in wild, sorted(wild)
    assert MEDIA_LIVE in wild and NBA_LIVE in wild


async def test_the_dismissed_exact_card_stays_dismissed_and_nothing_else_does(seed, pg):
    user = seed.users["nah"]
    page = _by_matchup(await _feed(pg, user, session_id=SESSION_A))
    await _swipe(
        pg,
        user,
        SESSION_A,
        [{"type": "event", "id": page[SUBJECT]["data"]["id"], "category": "baseball", "name": "Marlins vs Rockies"}],
    )
    after = _by_matchup(await _feed(pg, user, session_id=SESSION_A))
    assert SUBJECT not in after, "scoped per-card dismissal stopped working"
    assert MEDIA_LIVE in after and NBA_LIVE in after
    # a signed-in dismissal follows the ACCOUNT (any session) — and never
    # another reader
    same_account = _by_matchup(await _feed(pg, user, session_id=SESSION_B))
    assert SUBJECT not in same_account
    other = _by_matchup(await _feed(pg, seed.users["unset"], session_id=SESSION_B))
    assert SUBJECT in other, "one reader's dismissal leaked into another reader's page"


async def test_no_private_metadata_reaches_the_api(seed, pg):
    for user in (None, seed.users["nah"], seed.users["love"]):
        for params in ({}, {"mode": "sports"}):
            for it in await _feed(pg, user, **params):
                leaked = [k for k in it if k.startswith("_")]
                assert not leaked, (it["type"], leaked)
                assert "_admission_score" not in (it.get("data") or {})


# ---------------------------------------------------------------------------
# Keyed cards through the REAL route: UFC concept and golf tournaments
# ---------------------------------------------------------------------------


async def test_ufc_and_golf_reach_the_anonymous_page_through_the_real_chain(seed, pg):
    """Premise for the keyed arms: the seeded UFC card and all three tournaments
    are served to the neutral reader by the real scorers and display chain."""
    items = await _feed(pg, None)
    c = _concept(items)
    assert c is not None and c["data"]["name"].startswith(UFC_NAME_PREFIX), [it["type"] for it in items]
    assert c["data"]["domain"] == "ufc"
    t = _tournaments(items)
    assert {PGA_KEY, LPGA_KEY, UNKNOWN_TOUR_KEY} <= set(t), sorted(t)
    assert "personalized" not in c and all("personalized" not in x for x in t.values())


async def test_negative_keyed_cards_rank_down_and_are_never_removed(seed, pg):
    """Nah on MMA and on the PGA Tour, love on the LPGA: the UFC card and the PGA
    event are SERVED, ranked below their anonymous score; the LPGA event is
    served at its anonymous score (no positive boost — see the next test)."""
    anon = await _feed(pg, None)
    nah = await _feed(pg, seed.users["nah"])
    c_anon, c_nah = _concept(anon), _concept(nah)
    assert c_nah is not None, "the Nah reader lost the UFC card"
    assert c_nah["score"] < c_anon["score"]
    assert any(r.startswith("sport_nah") for r in c_nah["personalization_reasons"])
    t_anon, t_nah = _tournaments(anon), _tournaments(nah)
    assert PGA_KEY in t_nah, "the Nah reader lost the PGA tournament"
    assert t_nah[PGA_KEY]["score"] < t_anon[PGA_KEY]["score"]
    assert any(r.startswith("sport_nah") for r in t_nah[PGA_KEY]["personalization_reasons"])


async def test_positive_keyed_behaviour_is_pre_brief24_neutral_not_a_new_boost(seed, pg):
    """RED on Brief24, which multiplied loved keyed cards by 1.5. Before Brief24
    a loved tour was simply kept at its own score and a UFC card carried no
    preference term at all; that positive behaviour is restored — the repair is
    to the NEGATIVE rank-vs-eligibility path only. Events/futures keep their
    existing `sport_boost` (see the loved-reader event test above)."""
    anon = await _feed(pg, None)
    love = await _feed(pg, seed.users["love"])
    nah = await _feed(pg, seed.users["nah"])
    assert _concept(love)["score"] == _concept(anon)["score"], (
        _concept(love)["score"], _concept(anon)["score"])
    assert "personalized" not in _concept(love)
    t_anon, t_love, t_nah = _tournaments(anon), _tournaments(love), _tournaments(nah)
    for key in (PGA_KEY, LPGA_KEY):
        assert t_love[key]["score"] == t_anon[key]["score"], key
        assert "personalized" not in t_love[key], key
    # the Nah reader LOVES the LPGA: same neutral treatment
    assert t_nah[LPGA_KEY]["score"] == t_anon[LPGA_KEY]["score"]
    assert "personalized" not in t_nah[LPGA_KEY]


async def test_an_unknown_tour_is_neutral_for_every_reader(seed, pg):
    anon = _tournaments(await _feed(pg, None))
    for tag in ("nah", "unset", "love", "blank"):
        t = _tournaments(await _feed(pg, seed.users[tag]))
        assert UNKNOWN_TOUR_KEY in t, (tag, sorted(t))
        assert t[UNKNOWN_TOUR_KEY]["score"] == anon[UNKNOWN_TOUR_KEY]["score"], tag
        assert "personalized" not in t[UNKNOWN_TOUR_KEY], tag


async def test_keyed_cards_page_without_loss_and_principals_do_not_leak(seed, pg):
    user = seed.users["nah"]
    full = await _feed(pg, user, limit=50)
    keys = [(it["type"], it["data"].get("id") or it["data"].get("key")) for it in full]
    assert len(keys) == len(set(keys)), "duplicate on the unpaged list"
    paged: list = []
    for offset in range(0, len(full) + 3, 3):
        page = await _feed(pg, user, limit=3, offset=offset)
        paged += [(it["type"], it["data"].get("id") or it["data"].get("key")) for it in page]
    assert paged == keys, "paging reordered, duplicated or lost a card"
    assert any(t == "concept" for t, _ in paged) and any(t == "tournament" for t, _ in paged)
    # nah → love → anonymous → nah: each reads as itself
    nah1 = _concept(await _feed(pg, user))["score"]
    love = _concept(await _feed(pg, seed.users["love"]))["score"]
    anon = _concept(await _feed(pg, None))["score"]
    nah2 = _concept(await _feed(pg, user))["score"]
    assert nah1 == nah2 < anon == love

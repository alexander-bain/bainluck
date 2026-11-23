"""#12288 — Real PostgreSQL integration contract for `_load_snapshot_from_db` and preview error logging.

PILLAR: DISCOVER · FORMATTING · MATCHING · TRUTH
SHIP: Alex's grouping preview loads every candidate definition in
`backend/data/groupings/candidates/` against real PostgreSQL without failing on
relationship joins (`Sport.key`, `Team` eager loads), executes every SQL statement
in `_load_snapshot_from_db` (events, paired-stage markets, open markets,
verified-title member markets, and history window snapshots), and logs one
warning line naming the `slug` and `exception_class` whenever a grouping becomes
an error item.

Run locally with:
    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://localhost/bl_searchtest \\
        python3 -m pytest tests/integration/test_container_machinery_snapshot_12288_pg.py -v
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event as sa_event, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Event,
    FuturesMarket,
    FuturesOddsSnapshot,
    FuturesOutcome,
    Sport,
    Team,
    Venue,
)
from app.utils import container_machinery as cm
from app.utils.container_machinery import (
    _load_snapshot_from_db,
    discover_machinery_candidate_paths,
    evaluate_machinery_candidates_preview,
    load_machinery_definition,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="SEARCH_TEST_DATABASE_URL required for the #12288 container machinery PostgreSQL gate",
    ),
    pytest.mark.asyncio,
]

_TABLES = [
    Sport.__table__,
    Team.__table__,
    Venue.__table__,
    Event.__table__,
    FuturesMarket.__table__,
    FuturesOutcome.__table__,
    FuturesOddsSnapshot.__table__,
]


def _validated_url():
    url = make_url(DB_URL)
    assert url.get_backend_name() == "postgresql", "PostgreSQL gate requires PostgreSQL"
    assert url.database == "bl_searchtest", "Only the disposable bl_searchtest database is permitted"
    return url


async def _seed_all_candidates(session, now_dt: datetime) -> None:
    """Seed real PostgreSQL rows covering every candidate definition in
    `backend/data/groupings/candidates/` (NFL, Oscars, 2028 Presidential, Fed/Macro,
    and NBA) so every SQL statement in `_load_snapshot_from_db` executes and returns
    real rows.
    """
    fresh_iso = (now_dt - timedelta(minutes=5)).isoformat()
    recent_obs = now_dt - timedelta(minutes=5)
    res_future = now_dt + timedelta(days=120)

    nfl = Sport(key="americanfootball_nfl", name="NFL", group="American Football", active=True)
    ncaaf = Sport(key="americanfootball_ncaaf", name="NCAAF", group="American Football", active=True)
    nba = Sport(key="basketball_nba", name="NBA", group="Basketball", active=True)
    ncaab = Sport(key="basketball_ncaab", name="NCAAB", group="Basketball", active=True)
    nhl = Sport(key="icehockey_nhl", name="NHL", group="Ice Hockey", active=True)
    epl = Sport(key="soccer_epl", name="EPL", group="Soccer", active=True)
    la_liga = Sport(key="soccer_spain_la_liga", name="La Liga", group="Soccer", active=True)
    serie_a = Sport(key="soccer_italy_serie_a", name="Serie A", group="Soccer", active=True)
    bundesliga = Sport(key="soccer_germany_bundesliga", name="Bundesliga", group="Soccer", active=True)
    ligue_1 = Sport(key="soccer_france_ligue_one", name="Ligue 1", group="Soccer", active=True)
    session.add_all([nfl, ncaaf, nba, ncaab, nhl, epl, la_liga, serie_a, bundesliga, ligue_1])
    await session.flush()

    bills = Team(
        sport_id=nfl.id,
        name="Buffalo Bills",
        abbreviation="BUF",
        primary_color="#00338D",
        secondary_color="#C60C30",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/buf.png",
    )
    chiefs = Team(
        sport_id=nfl.id,
        name="Kansas City Chiefs",
        abbreviation="KC",
        primary_color="#E31837",
        secondary_color="#FFB81C",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/kc.png",
    )
    lions = Team(
        sport_id=nfl.id,
        name="Detroit Lions",
        abbreviation="DET",
        primary_color="#0076B6",
        secondary_color="#B0B7BC",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/det.png",
    )
    packers = Team(
        sport_id=nfl.id,
        name="Green Bay Packers",
        abbreviation="GB",
        primary_color="#203731",
        secondary_color="#FFB612",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/gb.png",
    )
    celtics = Team(
        sport_id=nba.id,
        name="Boston Celtics",
        abbreviation="BOS",
        primary_color="#007A33",
        secondary_color="#BA9653",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nba/500/bos.png",
    )
    cavs = Team(
        sport_id=nba.id,
        name="Cleveland Cavaliers",
        abbreviation="CLE",
        primary_color="#860038",
        secondary_color="#FDBB30",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nba/500/cle.png",
    )
    thunder = Team(
        sport_id=nba.id,
        name="Oklahoma City Thunder",
        abbreviation="OKC",
        primary_color="#007AC1",
        secondary_color="#EF3B24",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nba/500/okc.png",
    )
    nuggets = Team(
        sport_id=nba.id,
        name="Denver Nuggets",
        abbreviation="DEN",
        primary_color="#0E2240",
        secondary_color="#FEC524",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nba/500/den.png",
    )
    houston = Team(
        sport_id=ncaab.id,
        name="Houston Cougars",
        abbreviation="HOU",
        primary_color="#C8102E",
        secondary_color="#FFFFFF",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/248.png",
    )
    duke = Team(
        sport_id=ncaab.id,
        name="Duke Blue Devils",
        abbreviation="DUKE",
        primary_color="#003087",
        secondary_color="#FFFFFF",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/150.png",
    )
    florida = Team(
        sport_id=ncaab.id,
        name="Florida Gators",
        abbreviation="FLA",
        primary_color="#0021A5",
        secondary_color="#FA4616",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/57.png",
    )
    kansas = Team(
        sport_id=ncaab.id,
        name="Kansas Jayhawks",
        abbreviation="KU",
        primary_color="#0051BA",
        secondary_color="#E8000D",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/2305.png",
    )
    ducks_nhl = Team(
        sport_id=nhl.id,
        name="Anaheim Ducks",
        abbreviation="ANA",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/ana.png",
    )
    kraken = Team(
        sport_id=nhl.id,
        name="Seattle Kraken",
        abbreviation="SEA",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/sea.png",
    )
    mammoth = Team(
        sport_id=nhl.id,
        name="Utah Mammoth",
        abbreviation="UTA",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/utah.png",
    )
    jets = Team(
        sport_id=nhl.id,
        name="Winnipeg Jets",
        abbreviation="WPG",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/wpg.png",
    )
    georgia = Team(
        sport_id=ncaaf.id,
        name="Georgia Bulldogs",
        abbreviation="UGA",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/61.png",
    )
    notre_dame = Team(
        sport_id=ncaaf.id,
        name="Notre Dame Fighting Irish",
        abbreviation="ND",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/87.png",
    )
    texas_fb = Team(
        sport_id=ncaaf.id,
        name="Texas Longhorns",
        abbreviation="TEX",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/251.png",
    )
    alabama = Team(
        sport_id=ncaaf.id,
        name="Alabama Crimson Tide",
        abbreviation="ALA",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/333.png",
    )
    oregon = Team(
        sport_id=ncaaf.id,
        name="Oregon Ducks",
        abbreviation="ORE",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/2483.png",
    )
    utah_fb = Team(
        sport_id=ncaaf.id,
        name="Utah Utes",
        abbreviation="UTAH",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/254.png",
    )
    boise = Team(
        sport_id=ncaaf.id,
        name="Boise State Broncos",
        abbreviation="BOIS",
        logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/68.png",
    )
    broncos = Team(
        sport_id=nfl.id,
        name="Denver Broncos",
        abbreviation="DEN",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/den.png",
    )
    vikings = Team(
        sport_id=nfl.id,
        name="Minnesota Vikings",
        abbreviation="MIN",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/min.png",
    )
    panthers = Team(
        sport_id=nfl.id,
        name="Carolina Panthers",
        abbreviation="CAR",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/car.png",
    )
    niners = Team(
        sport_id=nfl.id,
        name="San Francisco 49ers",
        abbreviation="SF",
        logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/sf.png",
    )
    arsenal = Team(
        sport_id=epl.id,
        name="Arsenal",
        abbreviation="ARS",
        logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/359.png",
    )
    liverpool = Team(
        sport_id=epl.id,
        name="Liverpool",
        abbreviation="LIV",
        logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/364.png",
    )
    barcelona = Team(
        sport_id=la_liga.id,
        name="Barcelona",
        abbreviation="BAR",
        logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/83.png",
    )
    real_madrid = Team(
        sport_id=la_liga.id,
        name="Real Madrid",
        abbreviation="RMA",
        logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/86.png",
    )
    inter_milan = Team(
        sport_id=serie_a.id,
        name="Inter Milan",
        abbreviation="INT",
        logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/110.png",
    )
    como = Team(
        sport_id=serie_a.id,
        name="Como",
        abbreviation="COM",
        logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/2572.png",
    )
    bayern = Team(
        sport_id=bundesliga.id,
        name="Bayern Munich",
        abbreviation="FCB",
        logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/132.png",
    )
    dortmund = Team(
        sport_id=bundesliga.id,
        name="Borussia Dortmund",
        abbreviation="BVB",
        logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/124.png",
    )
    psg = Team(
        sport_id=ligue_1.id,
        name="Paris Saint-Germain",
        abbreviation="PSG",
        logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/160.png",
    )
    lille = Team(
        sport_id=ligue_1.id,
        name="Lille",
        abbreviation="LIL",
        logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/166.png",
    )
    session.add_all(
        [
            bills,
            chiefs,
            lions,
            packers,
            celtics,
            cavs,
            thunder,
            nuggets,
            houston,
            duke,
            florida,
            kansas,
            ducks_nhl,
            kraken,
            mammoth,
            jets,
            georgia,
            notre_dame,
            texas_fb,
            alabama,
            oregon,
            utah_fb,
            boise,
            broncos,
            vikings,
            panthers,
            niners,
            arsenal,
            liverpool,
            barcelona,
            real_madrid,
            inter_milan,
            como,
            bayern,
            dortmund,
            psg,
            lille,
        ]
    )
    await session.flush()

    def _wps(home_prob: float) -> dict:
        return {
            "betting": {
                "value": home_prob,
                "bookmaker_count": 5,
                "updated_at": fresh_iso,
            },
            "kalshi": {
                "value": home_prob,
                "updated_at": fresh_iso,
            },
        }

    session.add_all(
        [
            Event(
                sport_id=nfl.id,
                external_id="pg-nfl-1",
                home_team_id=chiefs.id,
                away_team_id=bills.id,
                home_team_name="Kansas City Chiefs",
                away_team_name="Buffalo Bills",
                commence_time=now_dt + timedelta(hours=18),
                status="scheduled",
                win_probability_sources=_wps(0.52),
            ),
            Event(
                sport_id=nfl.id,
                external_id="pg-nfl-2",
                home_team_id=packers.id,
                away_team_id=lions.id,
                home_team_name="Green Bay Packers",
                away_team_name="Detroit Lions",
                commence_time=now_dt + timedelta(hours=24),
                status="scheduled",
                win_probability_sources=_wps(0.47),
            ),
            Event(
                sport_id=nfl.id,
                external_id="pg-nfl-3",
                home_team_id=bills.id,
                away_team_id=lions.id,
                home_team_name="Buffalo Bills",
                away_team_name="Detroit Lions",
                commence_time=now_dt + timedelta(hours=36),
                status="scheduled",
                win_probability_sources=_wps(0.71),
            ),
            Event(
                sport_id=nfl.id,
                external_id="pg-nfl-4",
                home_team_id=chiefs.id,
                away_team_id=packers.id,
                home_team_name="Kansas City Chiefs",
                away_team_name="Green Bay Packers",
                commence_time=now_dt + timedelta(hours=42),
                status="scheduled",
                win_probability_sources=_wps(0.74),
            ),
            Event(
                sport_id=nba.id,
                external_id="pg-nba-1",
                home_team_id=celtics.id,
                away_team_id=cavs.id,
                home_team_name="Boston Celtics",
                away_team_name="Cleveland Cavaliers",
                commence_time=now_dt + timedelta(hours=12),
                status="scheduled",
                win_probability_sources=_wps(0.54),
            ),
            Event(
                sport_id=nba.id,
                external_id="pg-nba-2",
                home_team_id=thunder.id,
                away_team_id=nuggets.id,
                home_team_name="Oklahoma City Thunder",
                away_team_name="Denver Nuggets",
                commence_time=now_dt + timedelta(hours=15),
                status="scheduled",
                win_probability_sources=_wps(0.51),
            ),
            Event(
                sport_id=nba.id,
                external_id="pg-nba-3",
                home_team_id=cavs.id,
                away_team_id=nuggets.id,
                home_team_name="Cleveland Cavaliers",
                away_team_name="Denver Nuggets",
                commence_time=now_dt + timedelta(hours=30),
                status="scheduled",
                win_probability_sources=_wps(0.72),
            ),
            Event(
                sport_id=nba.id,
                external_id="pg-nba-4",
                home_team_id=celtics.id,
                away_team_id=thunder.id,
                home_team_name="Boston Celtics",
                away_team_name="Oklahoma City Thunder",
                commence_time=now_dt + timedelta(hours=34),
                status="scheduled",
                win_probability_sources=_wps(0.69),
            ),
            Event(
                sport_id=nhl.id,
                external_id="pg-nhl-1",
                home_team_id=kraken.id,
                away_team_id=ducks_nhl.id,
                home_team_name="Seattle Kraken",
                away_team_name="Anaheim Ducks",
                commence_time=now_dt + timedelta(hours=10),
                status="scheduled",
                win_probability_sources=_wps(0.51),
            ),
            Event(
                sport_id=nhl.id,
                external_id="pg-nhl-2",
                home_team_id=jets.id,
                away_team_id=mammoth.id,
                home_team_name="Winnipeg Jets",
                away_team_name="Utah Mammoth",
                commence_time=now_dt + timedelta(hours=14),
                status="scheduled",
                win_probability_sources=_wps(0.49),
            ),
            Event(
                sport_id=nhl.id,
                external_id="pg-nhl-3",
                home_team_id=kraken.id,
                away_team_id=jets.id,
                home_team_name="Seattle Kraken",
                away_team_name="Winnipeg Jets",
                commence_time=now_dt + timedelta(hours=30),
                status="scheduled",
                win_probability_sources=_wps(0.62),
            ),
            Event(
                sport_id=nhl.id,
                external_id="pg-nhl-4",
                home_team_id=jets.id,
                away_team_id=ducks_nhl.id,
                home_team_name="Winnipeg Jets",
                away_team_name="Anaheim Ducks",
                commence_time=now_dt + timedelta(hours=36),
                status="scheduled",
                win_probability_sources=_wps(0.66),
            ),
            Event(
                sport_id=nhl.id,
                external_id="pg-nhl-5",
                home_team_id=kraken.id,
                away_team_id=mammoth.id,
                home_team_name="Seattle Kraken",
                away_team_name="Utah Mammoth",
                commence_time=now_dt + timedelta(hours=44),
                status="scheduled",
                win_probability_sources=_wps(0.68),
            ),
            Event(
                sport_id=ncaab.id,
                external_id="pg-ncaab-1",
                home_team_id=houston.id,
                away_team_id=duke.id,
                home_team_name="Houston Cougars",
                away_team_name="Duke Blue Devils",
                commence_time=now_dt + timedelta(hours=12),
                status="scheduled",
                win_probability_sources=_wps(0.54),
            ),
            Event(
                sport_id=ncaab.id,
                external_id="pg-ncaab-2",
                home_team_id=kansas.id,
                away_team_id=florida.id,
                home_team_name="Kansas Jayhawks",
                away_team_name="Florida Gators",
                commence_time=now_dt + timedelta(hours=18),
                status="scheduled",
                win_probability_sources=_wps(0.63),
            ),
            Event(
                sport_id=ncaab.id,
                external_id="pg-ncaab-3",
                home_team_id=duke.id,
                away_team_id=florida.id,
                home_team_name="Duke Blue Devils",
                away_team_name="Florida Gators",
                commence_time=now_dt + timedelta(hours=28),
                status="scheduled",
                win_probability_sources=_wps(0.71),
            ),
        ]
    )
    await session.flush()

    async def _add_market(
        *,
        external_id: str,
        name: str,
        category: str,
        outcomes: list[tuple[str, float, float | None]],
        market_id: int | None = None,
        source: str = "kalshi",
        sport_id: int | None = None,
        with_history: bool = False,
    ) -> FuturesMarket:
        kw = {"id": market_id} if market_id is not None else {}
        fm = FuturesMarket(
            **kw,
            source=source,
            external_id=external_id,
            sport_id=sport_id,
            name=name,
            category=category,
            llm_sport_category=category,
            market_tier=1,
            mutually_exclusive=True,
            status="open",
            volume=250_000,
            resolution_date=res_future,
        )
        session.add(fm)
        await session.flush()
        for idx, (o_name, prob, hist_start) in enumerate(outcomes):
            fo = FuturesOutcome(
                market_id=fm.id,
                external_id=f"{external_id}-O{idx}",
                name=o_name,
                current_probability=prob,
                opening_probability=hist_start if hist_start is not None else prob,
                current_yes_bid=max(0.01, round(prob - 0.01, 4)),
                current_yes_ask=min(0.99, round(prob + 0.01, 4)),
                volume=5_000,
                volume_24h=500.0,
                volume_24h_at=recent_obs,
                last_updated=recent_obs,
                price_changed_at=recent_obs,
            )
            session.add(fo)
            await session.flush()
            if with_history:
                start_p = hist_start if hist_start is not None else max(0.05, prob - 0.06)
                mid_p = round((start_p + prob) / 2.0, 4)
                for hours_ago, snap_p in ((120, start_p), (48, mid_p), (2, prob)):
                    session.add(
                        FuturesOddsSnapshot(
                            outcome_id=fo.id,
                            bookmaker=source,
                            probability=snap_p,
                            yes_bid=max(0.01, round(snap_p - 0.01, 4)),
                            yes_ask=min(0.99, round(snap_p + 0.01, 4)),
                            captured_at=now_dt - timedelta(hours=hours_ago),
                            reading_count=1,
                        )
                    )
        return fm

    # 1. Oscars paired-stage register markets (5165726, 27988771, 6173044) + companion markets
    films_s1 = [
        ("The Odyssey", 0.96, 0.92),
        ("You Can See Everything", 0.84, 0.80),
        ("The Black Ball", 0.78, 0.74),
        ("Dune: Part Three", 0.72, 0.70),
    ]
    await _add_market(
        market_id=5165726,
        external_id="KXOSCARNOM-BP-27",
        name="Oscar Nominees: Best Picture",
        category="entertainment",
        outcomes=films_s1,
    )
    await _add_market(
        market_id=27988771,
        source="polymarket",
        external_id="PM-OSCARNOM-BP-27",
        name="Oscars Best Picture Nominees",
        category="entertainment",
        outcomes=films_s1,
    )
    await _add_market(
        market_id=6173044,
        external_id="KXOSCARWIN-BP-27",
        name="Oscar Winner: Best Picture",
        category="entertainment",
        outcomes=[
            ("The Odyssey", 0.42, 0.36),
            ("You Can See Everything", 0.24, 0.26),
            ("The Black Ball", 0.19, 0.21),
            ("Dune: Part Three", 0.15, 0.17),
        ],
        with_history=True,
    )
    await _add_market(
        external_id="KXOSCAR-SUPPACT-27",
        name="Oscar Winner: Best Supporting Actress",
        category="entertainment",
        outcomes=[("Zendaya", 0.38, 0.29), ("Saoirse Ronan", 0.33, 0.37), ("Emily Blunt", 0.29, 0.34)],
        with_history=True,
    )
    await _add_market(
        external_id="KXOSCAR-DIR-27",
        name="Oscar Winner: Best Director",
        category="entertainment",
        outcomes=[
            ("Christopher Nolan", 0.44, 0.40),
            ("Paul Thomas Anderson", 0.31, 0.34),
            ("Denis Villeneuve", 0.25, 0.26),
        ],
    )
    await _add_market(
        external_id="KXOSCAR-ACTOR-27",
        name="Oscar Winner: Best Actor",
        category="entertainment",
        outcomes=[("Matt Damon", 0.41, 0.39), ("Leonardo DiCaprio", 0.34, 0.35), ("Cillian Murphy", 0.25, 0.26)],
    )
    await _add_market(
        external_id="KXOSCAR-ACTRESS-27",
        name="Oscar Winner: Best Actress",
        category="entertainment",
        outcomes=[("Jessie Buckley", 0.43, 0.41), ("Anne Hathaway", 0.32, 0.33), (" Emma Stone", 0.25, 0.26)],
    )

    # 2. NFL markets
    await _add_market(
        external_id="KXNFL-PASSTD-26",
        name="NFL Passing Touchdowns Leader",
        category="football",
        sport_id=nfl.id,
        outcomes=[("Joe Burrow", 0.36, 0.31), ("Josh Allen", 0.34, 0.36), ("Lamar Jackson", 0.30, 0.33)],
    )
    await _add_market(
        external_id="KXNFL-RUSHTD-26",
        name="NFL Rushing Touchdowns Leader",
        category="football",
        sport_id=nfl.id,
        outcomes=[("Derrick Henry", 0.39, 0.35), ("Saquon Barkley", 0.33, 0.35), ("Jahmyr Gibbs", 0.28, 0.30)],
    )
    await _add_market(
        external_id="KXNFL-MVP-26",
        name="NFL MVP Winner",
        category="football",
        sport_id=nfl.id,
        outcomes=[
            ("Josh Allen", 0.38, 0.32),
            ("Lamar Jackson", 0.29, 0.33),
            ("Patrick Mahomes", 0.19, 0.21),
            ("Jared Goff", 0.14, 0.14),
        ],
        with_history=True,
    )
    await _add_market(
        external_id="KXNFL-NFCN-26",
        name="NFC North Champion",
        category="football",
        sport_id=nfl.id,
        outcomes=[("Detroit Lions", 0.51, 0.48), ("Green Bay Packers", 0.33, 0.35), ("Minnesota Vikings", 0.16, 0.17)],
    )
    await _add_market(
        external_id="KXNFL-AFCW-26",
        name="AFC West Champion",
        category="football",
        sport_id=nfl.id,
        outcomes=[("Kansas City Chiefs", 0.53, 0.55), ("Los Angeles Chargers", 0.31, 0.29), ("Denver Broncos", 0.16, 0.16)],
    )

    # 3. NBA markets (supports `machinery-nba-night` as well)
    await _add_market(
        external_id="KXNBA-PPG-26",
        name="NBA Points Per Game Leader",
        category="basketball",
        sport_id=nba.id,
        outcomes=[
            ("Shai Gilgeous-Alexander", 0.41, 0.37),
            ("Luka Doncic", 0.33, 0.35),
            ("Giannis Antetokounmpo", 0.26, 0.28),
        ],
    )
    await _add_market(
        external_id="KXNBA-APG-26",
        name="NBA Assists Per Game Leader",
        category="basketball",
        sport_id=nba.id,
        outcomes=[("Trae Young", 0.42, 0.39), ("Nikola Jokic", 0.33, 0.35), ("Tyrese Haliburton", 0.25, 0.26)],
    )
    await _add_market(
        external_id="KXNBA-MVP-26",
        name="NBA MVP Winner",
        category="basketball",
        sport_id=nba.id,
        outcomes=[
            ("Shai Gilgeous-Alexander", 0.39, 0.34),
            ("Nikola Jokic", 0.32, 0.35),
            ("Victor Wembanyama", 0.17, 0.19),
            ("Jayson Tatum", 0.12, 0.12),
        ],
        with_history=True,
    )
    await _add_market(
        external_id="KXNBA-6MOY-26",
        name="NBA Sixth Man of the Year Winner",
        category="basketball",
        sport_id=nba.id,
        outcomes=[("Payton Pritchard", 0.44, 0.40), ("Malik Monk", 0.31, 0.33), ("Naz Reid", 0.25, 0.27)],
    )
    await _add_market(
        external_id="KXNBA-DPOY-26",
        name="NBA Defensive Player of the Year Winner",
        category="basketball",
        sport_id=nba.id,
        outcomes=[("Victor Wembanyama", 0.48, 0.45), ("Chet Holmgren", 0.29, 0.31), ("Evan Mobley", 0.23, 0.24)],
    )

    # 4. 2028 Presidential markets + history
    await _add_market(
        external_id="KXPRES-PARTY-28",
        name="2028 Presidential Election Winning Party",
        category="politics",
        outcomes=[("Democratic Party", 0.51, 0.48), ("Republican Party", 0.49, 0.52)],
    )
    await _add_market(
        external_id="KXPRES-WIN-28",
        name="2028 Presidential Election Winner",
        category="politics",
        outcomes=[
            ("JD Vance", 0.31, 0.27),
            ("Gavin Newsom", 0.24, 0.26),
            ("Josh Shapiro", 0.23, 0.24),
            ("Marco Rubio", 0.22, 0.23),
        ],
        with_history=True,
    )
    await _add_market(
        external_id="KXPRES-DEMPRIM-28",
        name="2028 Democratic Presidential Primary Winner",
        category="politics",
        outcomes=[("Gavin Newsom", 0.36, 0.29), ("Josh Shapiro", 0.34, 0.39), ("Pete Buttigieg", 0.30, 0.32)],
        with_history=True,
    )
    await _add_market(
        external_id="KXPRES-DEMNOM-28",
        name="2028 Democratic Presidential Nominee",
        category="politics",
        outcomes=[("Gavin Newsom", 0.37, 0.35), ("Josh Shapiro", 0.35, 0.36), ("Gretchen Whitmer", 0.28, 0.29)],
    )
    await _add_market(
        external_id="KXPRES-REPNOM-28",
        name="2028 Republican Presidential Nominee",
        category="politics",
        outcomes=[("JD Vance", 0.49, 0.46), ("Marco Rubio", 0.28, 0.30), ("Ron DeSantis", 0.23, 0.24)],
    )

    # 5. Fed & U.S. Macro markets + history
    await _add_market(
        external_id="KXFED-JAN27",
        name="Fed Decision in Jan 2027",
        category="economics",
        outcomes=[
            ("Cut 50 bps", 0.12, 0.10),
            ("Cut 25 bps", 0.46, 0.39),
            ("No change", 0.34, 0.42),
            ("Hike 25 bps", 0.08, 0.09),
        ],
        with_history=True,
    )
    await _add_market(
        external_id="KXFED-MAR27",
        name="Fed Decision in Mar 2027",
        category="economics",
        outcomes=[("Cut 25 bps", 0.48, 0.39), ("No change", 0.39, 0.47), ("Hike 25 bps", 0.13, 0.14)],
        with_history=True,
    )
    await _add_market(
        external_id="KXFED-END26",
        name="What will the Fed rate be at the end of 2026?",
        category="economics",
        outcomes=[("3.50% - 3.75%", 0.38, 0.36), ("3.75% - 4.00%", 0.37, 0.39), ("4.00% - 4.25%", 0.25, 0.25)],
    )
    await _add_market(
        external_id="KXFED-HIKES26",
        name="How many Fed rate hikes in 2026?",
        category="economics",
        outcomes=[("0 hikes", 0.52, 0.50), ("1 hike", 0.33, 0.35), ("2 hikes", 0.15, 0.15)],
    )
    await _add_market(
        external_id="KXRECESSION-27",
        name="US Recession in 2027?",
        category="economics",
        outcomes=[("Yes", 0.29, 0.26), ("No", 0.71, 0.74)],
    )
    await _add_market(
        external_id="KXGDP-26",
        name="US GDP growth in 2026",
        category="economics",
        outcomes=[("1.0% to 1.5%", 0.24, 0.31), ("1.5% to 2.5%", 0.47, 0.41), ("2.5% to 3.5%", 0.29, 0.28)],
        with_history=True,
    )

    # 6. White Christmas (#13097 Batch 1)
    for city, prob in (("Pittsburgh", 0.44), ("Milwaukee", 0.41), ("Denver", 0.30), ("Seattle", 0.11)):
        await _add_market(
            external_id=f"KXSNOW-XMAS-{city.upper()}",
            name=f"Will it snow in {city} on Christmas?",
            category="weather",
            outcomes=[("Above 0 inches", prob, prob)],
        )

    # 7. The Next James Bond Film (#13097 Batch 1)
    await _add_market(
        external_id="KXBOND-THEME",
        name="Next James Bond film: Artist performing the James Bond Theme",
        category="entertainment",
        outcomes=[("Raye", 0.43, 0.41), ("Olivia Dean", 0.28, 0.29), ("Dua Lipa", 0.14, 0.15)],
    )
    await _add_market(
        external_id="KXBOND-GIRL",
        name="Next James Bond film: Actress cast as Bond girl",
        category="entertainment",
        outcomes=[("Zendaya", 0.25, 0.24), ("Florence Pugh", 0.24, 0.24), ("Margaret Qualley", 0.23, 0.23)],
    )
    await _add_market(
        external_id="KXBOND-VILLAIN",
        name="Next James Bond film: Actor cast as the villain",
        category="entertainment",
        outcomes=[("Cillian Murphy", 0.18, 0.18), ("Callum Turner", 0.14, 0.14), ("Aaron Taylor-Johnson", 0.12, 0.12)],
    )

    # 8. Who Gets Engaged? (#13097 Batch 1, Ruling 273: B)
    await _add_market(
        external_id="PMENG-SWEENEY",
        name="Scooter Braun and Sydney Sweeney engaged in 2026?",
        category="entertainment",
        outcomes=[("Yes", 0.36, 0.36)],
    )
    await _add_market(
        external_id="KXENG-SWEENEY",
        name="Sydney Sweeney and Scooter Braun: Engaged this year?",
        category="entertainment",
        outcomes=[("Yes", 0.35, 0.35)],
    )
    await _add_market(
        external_id="KXENG-CHALAMET",
        name="Timothée Chalamet and Kylie Jenner: Engaged in 2026?",
        category="entertainment",
        outcomes=[("Yes", 0.13, 0.13)],
    )
    await _add_market(
        external_id="KXENG-TIGER",
        name="Tiger Woods and Vanessa Trump: Engaged in 2026?",
        category="politics",
        outcomes=[("Yes", 0.06, 0.06)],
    )

    # 9. #13097 Batch 2 fun preview groupings (Taylor Swift, Long Shots, Long-Awaited, Space & Mars)
    for mid, ext, name, cat, outs in (
        (109309, "KXTS-DEBUTTV", "Will Taylor Swift (Taylor's Version) be announced this year?", "entertainment", [("Yes", 0.42, 0.42)]),
        (109310, "KXTS-REPTV", "Will Reputation (Taylor's Version) be announced this year?", "entertainment", [("Yes", 0.08, 0.08)]),
        (109295, "KXTS-POPE", "Will Taylor Swift meet with Pope Leo XIV before 2027?", "entertainment", [("Yes", 0.04, 0.04)]),
        (109291, "KXTS-BLAKE", "Blake Lively and Taylor Swift seen together in public this year?", "politics", [("Yes", 0.035, 0.035)]),
        (109435, "KXLS-ALIENS", "Will the U.S. confirm that aliens exist?", "tech", [("Before Jan 20, 2029", 0.155, 0.155), ("Before Jan 1, 2028", 0.115, 0.115)]),
        (108218, "KXLS-MARS", "Will Elon Musk visit Mars in his lifetime?", "culture", [("Yes", 0.115, 0.115)]),
        (113504, "KXLS-RETURN", "Will Jesus Christ return before 2027?", "entertainment", [("Yes", 0.015, 0.015)]),
        (113343, "KXLA-HL3", "Will Half-Life 3 be announced before 2027?", "entertainment", [("Yes", 0.075, 0.075)]),
        (109247, "KXLA-WINDS", "The Winds of Winter: Release date announced this year?", "entertainment", [("Yes", 0.055, 0.055)]),
        (108494, "KXLA-TES6", "When will Elder Scrolls VI be released?", "entertainment", [("Before 2028", 0.12, 0.12), ("Before 2027", 0.025, 0.025)]),
        (109540, "KXLA-PS6", "PS6 announced this year?", "entertainment", [("Yes", 0.025, 0.025)]),
        (108300, "KXSP-BLUE", "Will Blue Origin land on the moon before SpaceX?", "tech", [("Yes", 0.68, 0.68)]),
        (108236, "KXSP-ROBOT", "Will a humanoid robot walk on Mars before a human does?", "tech", [("Yes", 0.514, 0.514)]),
        (108273, "KXSP-SPX", "Will SpaceX land anything successfully on Mars before 2030?", "tech", [("Yes", 0.24, 0.24)]),
        # 10. #12288 Batch 3 preview groupings (2026 Summed Up, Cast/Delayed/Cancelled, Stage & Cover, Musk Side Quests)
        (109517, "KXB3-SPOTART", "Top artist on Spotify in 2026?", "entertainment", [("Bad Bunny", 0.96, 0.96), ("Drake", 0.03, 0.03)]),
        (109614, "KXB3-GOTY", "The Game Awards: Game of the Year", "entertainment", [("Grand Theft Auto VI", 0.92, 0.92), ("Resident Evil Requiem", 0.03, 0.03)]),
        (109527, "KXB3-WRAPPED", "When will Spotify release 2026 Wrapped?", "entertainment", [("Before Dec 5, 2026", 0.88, 0.88), ("Before Dec 4, 2026", 0.87, 0.87)]),
        (109214, "KXB3-AVENGERS", "Avengers: Doomsday: Cast", "entertainment", [("Hugh Jackman as Wolverine?", 0.97, 0.97), ("Ryan Reynolds as Deadpool?", 0.96, 0.96)]),
        (59172754, "KXB3-DUNEAV", "Dune vs Avengers: Highest Rotten Tomatoes Score", "entertainment", [("Dune: Part Three", 0.84, 0.84), ("Avengers: Doomsday", 0.25, 0.25)]),
        (108275, "KXB3-SIMPSONS", "Will there be an announcement that The Simpsons is ending?", "entertainment", [("Yes", 0.67, 0.67)]),
        (108505, "KXB3-COACH", "Who will headline Coachella 2027?", "entertainment", [("Tame Impala", 0.99, 0.99), ("SZA", 0.98, 0.98)]),
        (62368061, "KXB3-SNL", "Who will host Saturday Night Live Season 52?", "entertainment", [("Timothée Chalamet", 0.87, 0.87), ("Pedro Pascal", 0.41, 0.41)]),
        (56775621, "KXB3-VOGUE", "Vogue (US) 2026: Cover Models", "entertainment", [("Taylor Swift", 0.60, 0.60), ("Alex Consani", 0.41, 0.41)]),
        (109412, "KXB3-RYANAIR", "Will Elon purchase Ryanair?", "politics", [("Yes", 0.05, 0.05)]),
        (109633, "KXB3-SUPERMAN", "Next Superman film: Will Elon Musk be cast?", "entertainment", [("Yes", 0.05, 0.05)]),
        # 11. #12288 Batch 4 preview groupings (Game Awards, 2026-27 Championships, Unsolved Big Problems, AI & Big Tech)
        (58399979, "PMB4-TGADIR", "The Game Awards: Best Game Direction", "entertainment", [("Grand Theft Auto VI", 0.84, 0.84), ("Control Resonant", 0.10, 0.10)]),
        (58399941, "PMB4-TGANAR", "The Game Awards: Best Narrative", "entertainment", [("Grand Theft Auto VI", 0.79, 0.79), ("The Blood of Dawnwalker", 0.08, 0.08)]),
        (58399980, "PMB4-TGAAUD", "The Game Awards: Best Audio Design", "entertainment", [("Grand Theft Auto VI", 0.72, 0.72), ("Ace Combat 8", 0.08, 0.08)]),
        (57792807, "PMB4-HEISMAN", "NCAA Football: 2026 Heisman Award Winner", "football", [("Jeremiah Smith", 0.63, 0.63), ("Darian Mensah", 0.17, 0.17)]),
        (66031970, "PMB4-NBAMVP", "NBA: 2026-27 MVP", "basketball", [("Victor Wembanyama", 0.39, 0.39), ("Luka Doncic", 0.38, 0.38)]),
        (70732924, "PMB4-UCL27", "UEFA Champions League: 2027 Champion", "soccer", [("Barcelona", 0.22, 0.22), ("Paris Saint-Germain", 0.18, 0.18)]),
        (53049401, "KXB4-RIEMANN", "When will the Riemann hypothesis win the Millennium Prize?", "tech", [("Before 2035", 0.91, 0.91), ("Before 2032", 0.80, 0.80)]),
        (112792, "KXB4-MILLEN", "When will the next Millennium Prize be awarded?", "tech", [("Before 2035", 0.86, 0.86), ("Before 2030", 0.64, 0.64)]),
        (60626095, "PMB4-AIMATH", "Which math problems will AI solve in 2026?", "tech", [("Riemann Hypothesis", 0.76, 0.76), ("Ramsey Number R(5,5)", 0.24, 0.24)]),
        (113318, "PMB4-LARGEST", "Largest Company end of December 2026?", "economics", [("Apple", 0.94, 0.94), ("NVIDIA", 0.03, 0.03)]),
        (68806125, "PMB4-SECOND", "2nd Largest Company end of November 2026?", "tech", [("Microsoft", 0.80, 0.80), ("Alphabet", 0.12, 0.12)]),
        (23449601, "PMB4-ANTHOAI", "Anthropic vs OpenAI - higher valuation on December 31?", "economics", [("Anthropic", 0.67, 0.67), ("OpenAI", 0.33, 0.33)]),
    ):
        await _add_market(
            market_id=mid,
            external_id=ext,
            name=name,
            category=cat,
            outcomes=outs,
        )

    # 12. #12288 Batch 5 preview groupings (March Madness 2027, AI Model Leaderboard, Big Tech Deals & Hardware, NHL 100-Point Club)
    for mid, ext, name, cat, sid, outs in (
        (52755955, "PMB5-APPOLL", "AP Poll #1 team on December 7", "basketball", ncaab.id, [("Houston", 0.54, 0.50), ("Duke", 0.25, 0.27)]),
        (68954772, "PMB5-DUKEFF", "Will Duke reach the 2027 Final Four?", "basketball", ncaab.id, [("Yes", 0.37, 0.35)]),
        (68954773, "PMB5-FLAFF", "Will Florida reach the 2027 Final Four?", "basketball", ncaab.id, [("Yes", 0.32, 0.30)]),
        (109596, "KXB5-BESTAI", "Best AI model at year-end?", "tech", None, [("Gemini", 0.83, 0.80), ("Claude", 0.10, 0.12)]),
        (62134324, "KXB5-OPUS", "Next Claude Opus released by?", "tech", None, [("Dec 31", 0.79, 0.75)]),
        (109623, "KXB5-CODEAI", "Best coding AI model at year-end?", "tech", None, [("Anthropic", 0.49, 0.46), ("OpenAI", 0.31, 0.33)]),
        (115374, "KXB5-TSLASP", "Tesla and SpaceX merger announced by?", "tech", None, [("Dec 31, 2027", 0.86, 0.82)]),
        (109349, "KXB5-IPH18", "Apple releases the iPhone 18 before?", "tech", None, [("Apr 2027", 0.84, 0.80)]),
        (113435, "KXB5-BUBBLE", "The AI bubble bursts by?", "tech", None, [("June 30, 2027", 0.65, 0.61)]),
        (63105212, "PMB5-MCDAVID", "Connor McDavid 100 points this season?", "hockey", nhl.id, [("Yes", 0.94, 0.90)]),
        (63218794, "PMB5-DRAI", "Leon Draisaitl 100 points this season?", "hockey", nhl.id, [("Yes", 0.89, 0.85)]),
        (63105213, "PMB5-MACK", "Nathan MacKinnon 100 points this season?", "hockey", nhl.id, [("Yes", 0.79, 0.76)]),
    ):
        await _add_market(
            market_id=mid,
            external_id=ext,
            name=name,
            category=cat,
            sport_id=sid,
            outcomes=outs,
        )

    # 13. #12288 Batch 6 preview groupings (Google's 2026 Year in Search, Pop Culture Oddities, 2026 Box Office Showdown, The 2027 Golden Globes)
    for mid, ext, name, cat, outs in (
        (70733266, "PMB6-GACTOR1", "#1 Searched Actor on Google 2026?", "tech", [("Inde Navarrette", 0.47, 0.44), ("Robert Pattinson", 0.15, 0.16)]),
        (57792616, "PMB6-GATH1", "#1 Searched Athlete on Google 2026?", "tech", [("Erling Braut Haaland", 0.44, 0.41), ("Alysa Liu", 0.09, 0.10)]),
        (57792681, "PMB6-GMOV1", "#1 Searched Movie on Google 2026?", "entertainment", [("Obsession", 0.38, 0.36), ("The Odyssey", 0.32, 0.33)]),
        (60634621, "PMB6-GMOV5", "Top 5 Most Searched Movies on Google 2026", "tech", [("The Odyssey", 0.94, 0.91)]),
        (60634619, "PMB6-GATH5", "Top 5 Most Searched Athletes on Google 2026", "tech", [("Erling Braut Haaland", 0.90, 0.87)]),
        (67804475, "PMB6-MICHELIN", "Which New York City restaurants earn a Michelin star in 2026?", "entertainment", [("Kabawa", 0.32, 0.30)]),
        (67804457, "PMB6-AIWFCIY", '"All I Want for Christmas Is You" Hot 100 rank', "entertainment", [("Rank 1 to 2", 0.80, 0.77)]),
        (108306, "KXB6-BEYGENRE", "What genre will Beyoncé's next album be?", "entertainment", [("Rock", 0.64, 0.61)]),
        (108254, "KXB6-TIMEPER", "Time's Person of the Decade", "entertainment", [("Elon Musk", 0.35, 0.34)]),
        (114149, "KXB6-DUNEAV", "Will Dune 3 or Avengers: Doomsday gross more on opening weekend?", "entertainment", [("Avengers: Doomsday", 0.98, 0.96), ("Dune 3", 0.02, 0.04)]),
        (113355, "KXB6-TOP2026", "Highest grossing movie in 2026?", "entertainment", [("Spider-Man: Brand New Day", 0.91, 0.89)]),
        (113356, "KXB6-OPEN2026", "Which movie has biggest opening weekend in 2026?", "entertainment", [("Avengers: Doomsday", 0.90, 0.88)]),
        (70160313, "PMB6-GGACTF", "Golden Globe Winner: Best Actress - Musical or Comedy", "entertainment", [("Julianne Moore", 0.77, 0.75)]),
        (70160296, "PMB6-GGACTRLS", "Golden Globe Winner: Best Actress in a Limited Series", "entertainment", [("Florence Pugh", 0.72, 0.70)]),
        (70160294, "PMB6-GGSUPATV", "Golden Globe Winner: Best Supporting Actress on TV", "entertainment", [("Kate O'Flynn", 0.71, 0.68)]),
    ):
        await _add_market(
            market_id=mid,
            external_id=ext,
            name=name,
            category=cat,
            outcomes=outs,
        )

    # 14. #12288 Batch 7 preview groupings (8 forms across Oscars, CFB, NFL, NHL, NCAAB, Euro Soccer, Tech & Space, Weather)
    actor_outcomes = [
        ("John Malkovich", 0.94, 0.92),
        ("Andrew Scott", 0.92, 0.90),
        ("Matt Damon", 0.93, 0.91),
        ("Anthony Ippolito", 0.54, 0.50),
        ("Tom Cruise", 0.42, 0.40),
        ("Ryan Gosling", 0.37, 0.35),
    ]
    await _add_market(
        market_id=5388752,
        external_id="KXOSCARNOM-BA-27",
        name="Oscar nominees: Best Actor",
        category="entertainment",
        outcomes=actor_outcomes,
    )
    await _add_market(
        market_id=5869749,
        external_id="KXOSCARWIN-BA-27",
        name="Oscar Winner: Best Actor",
        category="entertainment",
        outcomes=[
            ("John Malkovich", 0.47, 0.42),
            ("Andrew Scott", 0.25, 0.22),
            ("Matt Damon", 0.15, 0.17),
            ("Anthony Ippolito", 0.06, 0.07),
            ("Tom Cruise", 0.04, 0.05),
            ("Ryan Gosling", 0.03, 0.03),
        ],
    )
    for mid, ext, name, cat, sid, hist, outs in (
        (5869747, "KXB7-OSCAR-DIR", "Oscar Winner: Best Director", "entertainment", None, False, [("Christopher Nolan", 0.61, 0.61), ("Denis Villeneuve", 0.17, 0.17)]),
        (58492239, "PMB7-OSCAR-ANIM", "Oscars 2027: Best Animated Feature Film Winner", "entertainment", None, False, [("Wildwood", 0.87, 0.87), ("Toy Story 5", 0.07, 0.07)]),
        (58492240, "PMB7-OSCAR-SUPA", "Oscars 2027: Best Supporting Actress Winner", "entertainment", None, False, [("Anne Hathaway", 0.63, 0.63), ("Amanda Seyfried", 0.21, 0.21)]),
        (58492236, "PMB7-OSCAR-ORIG", "Oscars 2027: Best Original Screenplay Winner", "entertainment", None, False, [("Wild Horse Nine", 0.61, 0.61), ("Club Kid", 0.13, 0.13)]),
        (181, "KXB7-CFP", "College Football National Championship Winner", "football", ncaaf.id, False, [("Georgia", 0.35, 0.35), ("Notre Dame", 0.17, 0.17), ("Texas", 0.11, 0.11), ("Alabama", 0.09, 0.09)]),
        (232, "KXB7-BIG10", "College Football Big Ten Championship Winner", "football", ncaaf.id, False, [("Oregon", 0.50, 0.50), ("Indiana", 0.20, 0.20), ("Iowa", 0.15, 0.15)]),
        (234, "KXB7-BIG12", "College Football Big 12 Championship Winner", "football", ncaaf.id, False, [("Utah", 0.56, 0.56), ("Texas Tech", 0.38, 0.38), ("BYU", 0.06, 0.06)]),
        (4121125, "KXB7-PAC12", "College Football Pac-12 Championship Winner", "football", ncaaf.id, False, [("Boise St.", 0.87, 0.87), ("San Diego St.", 0.12, 0.12), ("Fresno St.", 0.01, 0.01)]),
        (233, "KXB7-SEC", "College Football SEC Championship Winner", "football", ncaaf.id, False, [("Georgia", 0.69, 0.69), ("Texas", 0.26, 0.26), ("Alabama", 0.05, 0.05)]),
        (53675, "KXB7-AFCW", "AFC West Division Winner", "football", nfl.id, False, [("Denver", 0.55, 0.55), ("Kansas City", 0.43, 0.43), ("Las Vegas", 0.02, 0.02)]),
        (53673, "KXB7-NFCN", "NFC North Division Winner", "football", nfl.id, False, [("Minnesota", 0.37, 0.37), ("Chicago", 0.31, 0.31), ("Detroit", 0.30, 0.30)]),
        (53672, "KXB7-NFCS", "NFC South Division Winner", "football", nfl.id, False, [("Carolina", 0.51, 0.51), ("Tampa Bay", 0.27, 0.27), ("Atlanta", 0.11, 0.11)]),
        (53671, "KXB7-NFCW", "NFC West Division Winner", "football", nfl.id, False, [("San Francisco", 0.87, 0.87), ("Seattle", 0.09, 0.09), ("Los Angeles R", 0.04, 0.04)]),
        (70732920, "PMB7-EPL", "EPL: 2027 Champion", "soccer", epl.id, False, [("Arsenal", 0.73, 0.73), ("Liverpool", 0.14, 0.14), ("Brighton", 0.06, 0.06)]),
        (70732921, "PMB7-LALIGA", "LALIGA: 2027 Champion", "soccer", la_liga.id, False, [("Barcelona", 0.67, 0.67), ("Real Madrid", 0.31, 0.31), ("Atlético Madrid", 0.02, 0.02)]),
        (70732919, "PMB7-SERIEA", "Serie A: 2027 Champion", "soccer", serie_a.id, False, [("Inter Milan", 0.57, 0.57), ("Como", 0.08, 0.08), ("Lazio", 0.06, 0.06)]),
        (70732968, "PMB7-BUNDES", "Bundesliga: 2027 Champion", "soccer", bundesliga.id, False, [("Bayern Munich", 0.76, 0.76), ("Borussia Dortmund", 0.16, 0.16), ("RB Leipzig", 0.04, 0.04)]),
        (70732922, "PMB7-LIGUE1", "Ligue 1: 2027 Champion", "soccer", ligue_1.id, False, [("Paris Saint-Germain", 0.90, 0.90), ("Lille", 0.02, 0.02), ("Monaco", 0.02, 0.02)]),
        (24647105, "PMB7-OAI-IPO", "What will OpenAI's IPO valuation be?", "tech", None, True, [("<$1T", 0.33, 0.18), ("$1.0T–$1.25T", 0.22, 0.25), ("$1.25T–$1.5T", 0.21, 0.33)]),
        (68836748, "PMB7-SPX-MCAP", "SpaceX’s Market Cap end of December 2026?", "tech", None, True, [("$1.70-$2.00T", 0.30, 0.15), ("$1.10-$1.40T", 0.25, 0.20), ("$1.40-$1.70T", 0.24, 0.24)]),
        (70088624, "PMB7-JH-SPX", "Will Jensen Huang join SpaceX by...?", "tech", None, True, [("December 31, 2027", 0.24, 0.12), ("March 31, 2027", 0.10, 0.12), ("December 31, 2026", 0.04, 0.05)]),
        (52755607, "PMB7-SPX-TEL", "Will SpaceX acquire any major U.S. telecom business before 2028?", "tech", None, True, [("Yes", 0.38, 0.26)]),
        (115378, "KXB7-SPX-OAI", "SpaceX or OpenAI higher IPO Market Cap?", "tech", None, True, [("SpaceX", 0.78, 0.66), ("OpenAI", 0.22, 0.34)]),
        (109529, "KXB7-SPX26", "How many launches will SpaceX have in 2026?", "tech", None, True, [("Above 140", 0.72, 0.58), ("Above 145", 0.04, 0.15)]),
        (109358, "KXB7-HOTTEST", "Will 2026 be the hottest year ever?", "weather", None, False, [("Yes", 0.91, 0.91)]),
        (108220, "KXB7-WARM2C", "Will the world pass 2 degrees Celsius over pre-industrial levels before 2050?", "weather", None, False, [("Yes", 0.69, 0.69)]),
        (61054994, "PMB7-ELNINO", "Will the 2026–27 El Niño be the strongest on record?", "weather", None, False, [("Yes", 0.58, 0.58)]),
        (108294, "KXB7-JPQUAKE", "8.0 magnitude earthquake in Japan before 2030?", "weather", None, False, [("Yes", 0.33, 0.33)]),
        (108222, "KXB7-SUPVOL", "Will a supervolcano erupt before 2050?", "weather", None, False, [("Yes", 0.31, 0.31)]),
        (114086, "PMB7-CAT4HUR", "Will any Category 4 hurricane make landfall in the US before 2027?", "weather", None, False, [("Yes", 0.04, 0.04)]),
        (109398, "KXB7-CAQUAKE", "Will there be an 8 magnitude earthquake in California before 2027?", "weather", None, False, [("Yes", 0.03, 0.03)]),
        (114135, "PMB7-CAT5HUR", "Will any Category 5 hurricane make landfall in the US before 2027?", "weather", None, False, [("Yes", 0.02, 0.02)]),
    ):
        await _add_market(
            market_id=mid,
            external_id=ext,
            name=name,
            category=cat,
            sport_id=sid,
            outcomes=outs,
            with_history=hist,
        )
    await session.commit()


@pytest.fixture
async def pg_machinery(monkeypatch):
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "0")
    url = _validated_url()
    schema = "machinery_12288_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_async_engine(
        url,
        connect_args={"server_settings": {"search_path": f'"{schema}", public'}},
    )
    async with engine.begin() as conn:
        for tbl in _TABLES:
            await conn.run_sync(tbl.create)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    now_dt = datetime.now(timezone.utc)
    async with maker() as seed_session:
        await _seed_all_candidates(seed_session, now_dt)

    yield {"maker": maker, "engine": engine, "now_dt": now_dt}

    await engine.dispose()
    async with admin.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()


async def test_load_snapshot_from_db_executes_every_query_for_every_candidate_definition(
    pg_machinery,
):
    """Ask 1 + Ask 2: run `_load_snapshot_from_db` against real PostgreSQL for every
    definition in `backend/data/groupings/candidates/` and verify that every SQL
    statement family (events via `Sport.key`, paired-stage register markets, open
    markets, verified-title member markets, and `futures_odds_snapshots` window
    history) executes and returns properly serialized primitives.
    """
    maker = pg_machinery["maker"]
    engine = pg_machinery["engine"]
    now_dt = pg_machinery["now_dt"]

    paths = discover_machinery_candidate_paths()
    assert len(paths) >= 4

    executed_sql: list[str] = []

    def _record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        executed_sql.append(statement)

    sa_event.listen(engine.sync_engine, "before_cursor_execute", _record_sql)
    try:
        snapshots_by_slug: dict[str, dict] = {}
        async with maker() as session:
            for path in paths:
                defn = load_machinery_definition(path)
                snap = await _load_snapshot_from_db(session, defn, now_dt=now_dt)
                snapshots_by_slug[defn["slug"]] = snap
    finally:
        sa_event.remove(engine.sync_engine, "before_cursor_execute", _record_sql)

    # Verify events query filtered through Sport.key and serialized plain strings + team data
    nfl_snap = snapshots_by_slug["machinery-nfl-week"]
    assert len(nfl_snap["events"]) >= 2
    ev0 = nfl_snap["events"][0]
    assert ev0["sport"] == "americanfootball_nfl"
    assert ev0["sport_name"] == "NFL"
    assert isinstance(ev0["home_team"], str) and ev0["home_team"]
    assert isinstance(ev0["away_team"], str) and ev0["away_team"]
    assert isinstance(ev0.get("home_team_data"), dict)
    assert ev0["home_team_data"]["logo_small"].startswith("https://")

    # Verify paired_stage, markets, and market_histories queries returned real rows
    oscars_snap = snapshots_by_slug["machinery-oscars-best-picture"]
    assert "oscars-2027-best-picture" in oscars_snap["paired_sets"]
    assert len(oscars_snap["markets"]) >= 4
    assert len(oscars_snap["market_histories"]) >= 1

    pres_snap = snapshots_by_slug["machinery-2028-presidential"]
    assert len(pres_snap["markets"]) >= 4
    assert len(pres_snap["market_histories"]) >= 1

    fed_snap = snapshots_by_slug["machinery-fed-and-macro"]
    assert len(fed_snap["markets"]) >= 5
    assert len(fed_snap["market_histories"]) >= 1

    # Verify every SQL statement family actually ran on PostgreSQL
    joined_sql = "\n".join(executed_sql).lower()
    assert "join sports on events.sport_id = sports.id" in joined_sql
    assert "sports.key in" in joined_sql
    assert "from futures_markets" in joined_sql
    assert "from futures_odds_snapshots" in joined_sql
    assert "row_number() over (partition by futures_odds_snapshots.outcome_id" in joined_sql


async def test_paired_discover_card_and_set_match_the_market_pages_allocation(pg_machinery):
    from app.routes.futures import get_futures_market
    from app.utils.roundup_containers import RoundupMembers

    defn = next(
        candidate for path in discover_machinery_candidate_paths()
        if (candidate := load_machinery_definition(path))["slug"] == "machinery-oscars-best-picture"
    )
    async with pg_machinery["maker"]() as db:
        await db.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.market_id == 6173044, FuturesOutcome.name == "The Odyssey")
            .values(current_probability=0.41)
        )
        await db.commit()
    async with pg_machinery["maker"]() as db:
        detail = await get_futures_market(6173044, db=db, representation="verified_title")
        build = await cm.produce_container_machinery(db, defn, now=pg_machinery["now_dt"])

    assert isinstance(build, RoundupMembers)
    page_row = next(row for row in detail["outcomes"] if row["name"] == "The Odyssey")
    card_row = next(row for row in build.rows if row["label"] == "The Odyssey")
    set_table = next(
        section["visual_block"]["paired_metric_set"] for section in build.sections
        if section["visual_block"]["form_id"] == "paired_stage_bars"
    )
    set_row = next(row for row in set_table["entries"] if row["subject"] == "The Odyssey")
    assert page_row["rendered_percent"] == 42
    assert card_row["probability"] == set_row["stage_2_probability"] == page_row["probability"]
    assert card_row["rendered_percent"] == set_row["stage_2_rendered_percent"] == page_row["rendered_percent"]


async def test_evaluate_machinery_candidates_preview_returns_all_ok_with_zero_error_logs(
    pg_machinery, monkeypatch, caplog
):
    """Ask 4 local proof on real PostgreSQL: every candidate definition in
    `backend/data/groupings/candidates/` evaluates to `status: 'ok'` with published
    container sections, passing member-number parity, zero `machinery_preview_error`
    log lines, and 60s preview cache reuse on repeat single-slug calls.
    """
    from app.utils.roundup_containers import reset_roundup_cache_for_tests

    maker = pg_machinery["maker"]
    now_dt = pg_machinery["now_dt"]
    expected_count = len(discover_machinery_candidate_paths())

    caplog.set_level(logging.WARNING, logger=cm.__name__)
    async with maker() as session:
        items = await evaluate_machinery_candidates_preview(session, now=now_dt)

    assert len(items) == expected_count
    for item in items:
        assert item["status"] == "ok", f"{item['slug']} failed with {item}"
        assert item["container"]["state"] == "published"
        assert item["diversity_report"]["member_number_parity"]["passes"] is True

    error_logs = [r.getMessage() for r in caplog.records if "machinery_preview_error" in r.getMessage()]
    assert error_logs == []

    # Repeat single-slug preview reads reuse the 60s cache without hitting DB again.
    cm.reset_machinery_preview_cache_for_tests()
    reset_roundup_cache_for_tests()
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    call_count = 0
    real_load = cm._load_snapshot_from_db

    async def _counting_load(db, defn, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await real_load(db, defn, *args, **kwargs)

    monkeypatch.setattr(cm, "_load_snapshot_from_db", _counting_load)
    caplog.set_level(logging.INFO, logger=cm.__name__)
    async with maker() as session:
        first = await cm.serve_machinery_candidate_preview(
            "machinery-nfl-week", session, allow_error_envelope=True
        )
        second = await cm.serve_machinery_candidate_preview(
            "machinery-nfl-week", session, allow_error_envelope=True
        )
    assert first is not None and first["status"] == "ok"
    assert second is not None and second["status"] == "ok"
    assert call_count == 1
    built_logs = [r.getMessage() for r in caplog.records if "machinery_preview_built" in r.getMessage()]
    assert any("cache_hit=miss" in msg for msg in built_logs)
    assert any("cache_hit=local" in msg for msg in built_logs)
    cm.reset_machinery_preview_cache_for_tests()
    reset_roundup_cache_for_tests()


async def test_error_item_logs_slug_and_exception_class_and_keeps_session_usable(
    pg_machinery, monkeypatch, caplog
):
    """Ask 3: when a grouping becomes an error item on a real PostgreSQL session
    (including after an aborted SQL statement), `serve_machinery_candidate_preview`
    logs one line with its `slug` and exception class, rolls back the aborted
    transaction, and still serves the remaining candidate groupings with `status: 'ok'`.
    """
    maker = pg_machinery["maker"]
    now_dt = pg_machinery["now_dt"]
    real_load = cm._load_snapshot_from_db

    async def _explode_on_nfl(db, defn, *args, **kwargs):
        if defn.get("slug") == "machinery-nfl-week":
            # Force a real PostgreSQL statement error so the transaction enters aborted state
            await db.execute(text("SELECT * FROM nonexistent_machinery_table_12288"))
        return await real_load(db, defn, *args, **kwargs)

    monkeypatch.setattr(cm, "_load_snapshot_from_db", _explode_on_nfl)
    caplog.set_level(logging.WARNING, logger=cm.__name__)

    async with maker() as session:
        items = await evaluate_machinery_candidates_preview(session, now=now_dt)

    by_slug = {it["slug"]: it for it in items}
    assert by_slug["machinery-nfl-week"]["status"] == "error"
    for slug, item in by_slug.items():
        if slug != "machinery-nfl-week":
            assert item["status"] == "ok", f"sibling {slug} poisoned by aborted tx: {item}"

    error_logs = [r.getMessage() for r in caplog.records if "machinery_preview_error" in r.getMessage()]
    assert len(error_logs) == 1
    assert "slug=machinery-nfl-week" in error_logs[0]
    assert "ProgrammingError" in error_logs[0]

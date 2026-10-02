"""#10208 — the /sports props strip leads with the current major-game slate.

THE DEFECT. ``/api/futures/grouped-feed?limit=20&sports_only=true``, 2026-10-02
~16:08Z, opened on three golf placement grids, then a St Kitts–Cuba exact-score
ladder and sixteen lower-league soccer/tennis sub-markets. The pool is
``limit * 5`` markets by ``updated_at`` alone, so it never reached the games
being played: production that morning held 3,676 open markets linked to 58
upcoming NFL games, 289 to NHL games, and the Braves–Dodgers postseason game's
own props — supply present, selection blind.

THE SLATE (read on production 16:58Z with the shipped statement, 94 ms): the
three earliest MLB postseason games (team-total and game-total ladders, "extra
innings?", "run in the first inning?"), WNBA Game 3 (player points lines) and
Rangers–Red Wings (totals). Those game ids and market ids are the fixtures here.

TWO RULES. (1) One extra read, ``grouped_feed_slate``, returns up to ``limit``
slate markets (≤4 per game, ≤3 games per league), and the pool read loads them
beside the recency pool. (2) ``lead_with_slate`` moves the FIRST card of each
slate game to the front, one per game, ≤6 — a stable partition, nothing dropped.
"""

import re
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routes.futures import (
    SLATE_EVENTS_PER_LEAGUE,
    SLATE_LEAD_CAP,
    SLATE_MARKETS_PER_EVENT,
    grouped_feed_slate,
    lead_with_slate,
)
from tests._grouped_feed_slate import is_slate_read

# Production ids, 2026-10-02.
CWS_CLE = 15322462  # ALCS-round MLB postseason
ATL_LAD = 15323083
WINGS_VALKYRIES = 15322555  # WNBA Game 3
RANGERS_RED_WINGS = 15168046


def _market_card(mid, name="m"):
    return {"type": "market", "market": {"id": mid, "name": name, "outcomes": []}}


def _ladder(title, *outcome_ids):
    return {
        "type": "threshold",
        "kind": "threshold",
        "title": title,
        "points": [{"id": oid} for oid in outcome_ids],
    }


def _grid(title):
    return {"type": "placement_grid", "title": title, "rows": []}


def _titles(items):
    return [i.get("title") or i["market"]["name"] for i in items]


class TestLeadWithSlate:
    def _strip(self):
        # Assembly order as the route builds it: grids, then ladders, then markets.
        return [
            _grid("Alfred Dunhill Links Championship"),
            _grid("Bank of Utah Championship"),
            _grid("Compliance Solutions Championship"),
            _ladder("St. Kitts and Nevis vs. Cuba - Exact Score", 1, 2),
            _ladder("Cleveland Guardians Team Total: O/U", 11, 12),
            _market_card(63812910, "Will the game go to extra innings?: Braves vs. Dodgers"),
            _market_card(63818534, "Dallas Wings vs. Golden State Valkyries: O/U 158.5"),
            _market_card(500, "Gainsborough Trinity FC vs. Anstey Nomads FC: O/U 4.5"),
        ]

    def _slate(self):
        ids = [63736450, 63785953, 63812910, 63818534]
        market_event = {
            63736450: CWS_CLE,
            63785953: CWS_CLE,
            63812910: ATL_LAD,
            63818534: WINGS_VALKYRIES,
        }
        outcome_market = {11: 63736450, 12: 63785953, 1: 900, 2: 900}
        return ids, market_event, outcome_market

    def test_slate_games_lead_one_card_each_in_slate_order(self):
        ids, market_event, outcome_market = self._slate()
        out = lead_with_slate(self._strip(), ids, market_event, outcome_market)
        assert _titles(out)[:3] == [
            "Cleveland Guardians Team Total: O/U",
            "Will the game go to extra innings?: Braves vs. Dodgers",
            "Dallas Wings vs. Golden State Valkyries: O/U 158.5",
        ]

    def test_the_rest_keep_their_assembled_order_and_nothing_is_lost(self):
        ids, market_event, outcome_market = self._slate()
        strip = self._strip()
        out = lead_with_slate(strip, ids, market_event, outcome_market)
        assert len(out) == len(strip)
        assert sorted(map(id, out)) == sorted(map(id, strip))
        assert _titles(out)[3:] == [
            "Alfred Dunhill Links Championship",
            "Bank of Utah Championship",
            "Compliance Solutions Championship",
            "St. Kitts and Nevis vs. Cuba - Exact Score",
            "Gainsborough Trinity FC vs. Anstey Nomads FC: O/U 4.5",
        ]

    def test_THE_CONTROL_without_a_slate_the_strip_opens_on_three_golf_grids(self):
        strip = self._strip()
        out = lead_with_slate(strip, [], {}, {})
        assert out is strip
        assert [i["type"] for i in out[:3]] == ["placement_grid"] * 3

    def test_one_card_per_game_even_when_a_game_built_several(self):
        strip = [
            _market_card(1, "CWS–CLE extra innings"),
            _market_card(2, "CWS–CLE first inning run"),
            _grid("golf"),
            _market_card(3, "ATL–LAD extra innings"),
        ]
        out = lead_with_slate(strip, [1, 2, 3], {1: CWS_CLE, 2: CWS_CLE, 3: ATL_LAD}, {})
        assert _titles(out) == [
            "CWS–CLE extra innings",
            "ATL–LAD extra innings",
            "CWS–CLE first inning run",
            "golf",
        ]

    def test_the_lead_is_capped(self):
        n = SLATE_LEAD_CAP + 3
        strip = [_market_card(i, f"game {i}") for i in range(n)] + [_grid("golf")]
        out = lead_with_slate(strip, list(range(n)), {i: 1000 + i for i in range(n)}, {})
        assert _titles(out)[:SLATE_LEAD_CAP] == [f"game {i}" for i in range(SLATE_LEAD_CAP)]
        assert len(out) == len(strip)

    def test_a_slate_game_with_no_card_on_the_strip_is_skipped_not_invented(self):
        strip = [_grid("golf"), _market_card(3, "ATL–LAD extra innings")]
        # Game CWS_CLE's market 1 built no card (unpriced, decided, withheld).
        out = lead_with_slate(strip, [1, 3], {1: CWS_CLE, 3: ATL_LAD}, {})
        assert _titles(out) == ["ATL–LAD extra innings", "golf"]


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _SlateSession:
    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _Rows(self._rows)


def _sql(stmt):
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
class TestTheSlateRead:
    async def test_it_returns_ids_in_slate_order_with_their_games(self):
        session = _SlateSession([(63736450, CWS_CLE), (63812910, ATL_LAD)])
        ids, market_event = await grouped_feed_slate(session, [], 20)
        assert ids == [63736450, 63812910]
        assert market_event == {63736450: CWS_CLE, 63812910: ATL_LAD}

    async def test_the_statement_is_the_one_the_route_tests_stub(self):
        session = _SlateSession([])
        await grouped_feed_slate(session, [], 20)
        assert is_slate_read(session.statements[0])

    async def test_it_ranks_postseason_then_tier_then_kickoff_and_caps_per_game_and_league(self):
        session = _SlateSession([])
        await grouped_feed_slate(session, [], 20)
        sql = _sql(session.statements[0])
        assert "llm_importance IN ('playoff', 'championship')" in sql
        assert f"rn <= {SLATE_MARKETS_PER_EVENT}" in sql
        assert f"league_rank <= {SLATE_EVENTS_PER_LEAGUE}" in sql
        assert re.search(r"ORDER BY anon_1\.postseason, anon_1\.tier, anon_1\.commence_time", sql)
        assert sql.rstrip().endswith("LIMIT 20")

    async def test_only_unfinished_tier_1_and_2_games_and_never_the_game_card_question(self):
        session = _SlateSession([])
        await grouped_feed_slate(session, [], 20)
        sql = _sql(session.statements[0])
        assert "status IN ('scheduled', 'live')" in sql
        assert "'baseball_mlb'" in sql and "'americanfootball_nfl'" in sql
        # A Grand Slam is tier 2 under its tour spelling (#2552)...
        assert "'tennis_atp_us_open'" in sql
        # ...and a tour stop is not in the slate.
        assert "'tennis_atp_china_open'" not in sql
        # The Kalshi game-winner market and the Polymarket game wrapper are out.
        assert re.search(r"NOT \(futures_markets\.group_type = 'kalshi_event' AND futures_markets\.market_type = 'duel'\)", sql)
        assert "futures_markets.group_type != 'polymarket_event'" in sql

    async def test_the_pool_filters_ride_the_slate_read(self):
        from app.models import FuturesMarket

        session = _SlateSession([])
        await grouped_feed_slate(session, [FuturesMarket.status.in_(["active", "open"])], 20)
        assert "futures_markets.status IN ('active', 'open')" in _sql(session.statements[0])


# ── Through the route ────────────────────────────────────────────────────────


def _leg(prob, name, oid):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=Decimal(str(prob)),
        current_yes_bid=None,
        current_yes_ask=None,
        probability=Decimal(str(prob)),
        american_odds=None,
    )


class _Market:
    def __init__(self, mid, name, legs, sport="baseball", event_id=None):
        self.id = mid
        self.name = name
        self.source = "polymarket"
        self.category = "game_prop"
        self.llm_sport_category = sport
        self.status = "open"
        self.group_id = None
        self.group_type = None
        self.market_type = None
        self.event_id = event_id
        self.outcomes = legs


class _PoolResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _RouteSession:
    """Answers the slate read with ``slate_rows`` and the pool read with ``pool``."""

    def __init__(self, slate_rows, pool):
        self._slate_rows = slate_rows
        self._pool = pool
        self.pool_statements = []
        self.slate_reads = 0

    async def execute(self, stmt):
        if is_slate_read(stmt):
            self.slate_reads += 1
            return _Rows(self._slate_rows)
        self.pool_statements.append(stmt)
        if len(self.pool_statements) > 1:
            raise AssertionError("second pool read: this pool has nothing to fold")
        return _PoolResult(self._pool)


class _Request:
    scope: dict = {}


class _Response:
    def __init__(self):
        self.headers = {}


async def _serve(session, **kw):
    from app.routes.futures import grouped_feed

    args = dict(category=None, sport=None, sports_only=True, limit=20)
    args.update(kw)
    return await grouped_feed(request=_Request(), response=_Response(), db=session, **args)


def _pool():
    # Recency order: the lower-league rows the venue touched last come first.
    return [
        _Market(500, "Gainsborough Trinity FC vs. Anstey Nomads FC: O/U 4.5",
                [_leg(0.4, "Over", 5001), _leg(0.6, "Under", 5002)], sport="soccer"),
        _Market(501, "Spread: Chertsey Town FC (-5.5)",
                [_leg(0.3, "Chertsey Town FC", 5011), _leg(0.7, "Opponent", 5012)], sport="soccer"),
        _Market(63812910, "Will the game go to extra innings?: Atlanta Braves vs. Los Angeles Dodgers",
                [_leg(0.09, "Yes", 6001), _leg(0.91, "No", 6002)], event_id=ATL_LAD),
    ]


def _names(payload):
    return [
        (row.get("market") or {}).get("name") or row.get("title")
        for row in payload["feed"]
    ]


@pytest.mark.asyncio
class TestThroughTheRoute:
    async def test_the_slate_game_leads_the_served_strip(self):
        session = _RouteSession([(63812910, ATL_LAD)], _pool())
        payload = await _serve(session)
        assert session.slate_reads == 1
        assert _names(payload)[0] == (
            "Will the game go to extra innings?: Atlanta Braves vs. Los Angeles Dodgers"
        )
        # Nothing else moved, nothing was dropped.
        assert _names(payload)[1:] == [
            "Gainsborough Trinity FC vs. Anstey Nomads FC: O/U 4.5",
            "Spread: Chertsey Town FC (-5.5)",
        ]

    async def test_the_pool_read_loads_the_slate_beside_the_recency_pool(self):
        session = _RouteSession([(63812910, ATL_LAD)], _pool())
        await _serve(session)
        sql = _sql(session.pool_statements[0])
        assert "futures_markets.id IN (63812910)" in sql
        assert re.search(r"futures_markets\.id IN \(SELECT futures_markets\.id\s", sql)
        assert "LIMIT 100" in sql

    async def test_THE_CONTROL_no_slate_means_the_old_pool_statement_and_the_old_order(self):
        session = _RouteSession([], _pool())
        payload = await _serve(session)
        sql = _sql(session.pool_statements[0])
        assert "futures_markets.id IN (" not in sql
        assert sql.rstrip().endswith("LIMIT 100")
        assert _names(payload)[0] == "Gainsborough Trinity FC vs. Anstey Nomads FC: O/U 4.5"

    async def test_a_narrower_filter_never_reads_the_slate(self):
        session = _RouteSession([(63812910, ATL_LAD)], _pool())
        await _serve(session, sport="baseball")
        assert session.slate_reads == 0
        session = _RouteSession([(63812910, ATL_LAD)], _pool())
        await _serve(session, sports_only=False)
        assert session.slate_reads == 0


def _ladder_market():
    # A non-slate threshold ladder, built before any plain market card — the
    # #10064 specimen's rungs verbatim.
    return _Market(
        63153133,
        "Roman Safiullin vs Flavio Cobolli: Total Games",
        [_leg(0.605, "Over 18.5 games", 238112739),
         _leg(0.465, "Over 23.5 games", 238112740),
         _leg(0.36, "Over 28.5 games", 238112741)],
        sport="tennis",
    )


@pytest.mark.asyncio
class TestEachHalfBitesAlone:
    async def test_the_LEAD_moves_a_slate_card_above_a_ladder_assembled_first(self):
        pool = [_ladder_market()] + _pool()
        control = await _serve(_RouteSession([], pool))
        assert _names(control)[0] == "Roman Safiullin vs Flavio Cobolli: Total Games"

        payload = await _serve(_RouteSession([(63812910, ATL_LAD)], pool))
        assert _names(payload)[:2] == [
            "Will the game go to extra innings?: Atlanta Braves vs. Los Angeles Dodgers",
            "Roman Safiullin vs Flavio Cobolli: Total Games",
        ]

    async def test_the_SLATE_FIRST_POOL_keeps_a_slate_row_inside_the_ungrouped_cut(self):
        # limit=2: the ungrouped pass keeps two rows. In recency order the slate
        # row is third and would be cut before the lead could see it.
        payload = await _serve(_RouteSession([(63812910, ATL_LAD)], _pool()), limit=2)
        assert _names(payload)[0] == (
            "Will the game go to extra innings?: Atlanta Braves vs. Los Angeles Dodgers"
        )

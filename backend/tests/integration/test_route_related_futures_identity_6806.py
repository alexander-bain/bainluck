"""#6806 — a club's season context names THAT club, through the real route.

WHAT A READER SAW. `GET /api/events/15298552/related-futures` (Crystal Palace vs
Lech Poznań, Europa League), production 2026-09-17 20:52Z at 390px: the away
card's only CHAMPIONSHIP PATH row was `Belgian Pro League Champion — 6%`, which
is Anderlecht's price (market 59164822). A fresh public read of the same route
on 2026-09-18 02:43Z (`artifacts/other-model-related-futures-identity-execution/
inputs/current-15298552-related-futures.json`) no longer serves the Belgian row
but DOES serve `Ekstraklasa Champion — Lechia Gdansk 1%` (market 402, outcome
4369) beside the legitimate `Lech Poznan 99%` (market 402, outcome 4367).

WHY. `_team_name_patterns("Lech Poznań")` emits the short token `Lech`, and the
route's `_matches_any` classified an outcome by bare substring:
`'lech' in 'anderlecht'` and `'lech' in 'lechia gdansk'` are both True. The SQL
candidate net (`FuturesOutcome.name ILIKE '%Lech%'`) is what lets those rows in;
the Python classification is the seam that ASSIGNS them to a side, and it is the
seam this file exercises — the mock session below hands the route exactly the
candidate rows production's ILIKE net demonstrably returned (issue #6806 measured
Anderlecht; the saved 2026-09-18 response shows Lechia Gdansk).

═══ SYNTHETIC ROWS, LABELLED ═══

Every `events` / `futures_markets` / `futures_outcomes` row here is SYNTHETIC
(MagicMock, the same harness `test_route_related_futures.py` uses). Market and
outcome IDS, NAMES and PROBABILITIES for the Ekstraklasa rows (402 / 4367 / 4369)
and the FA Cup row (405 / 4412) are quoted from the saved public response; the
Belgian rows (59164822 / Anderlecht 0.060 / Royal Charleroi 0.055) are quoted from
issue #6806's table. Outcome ids for the Belgian rows are invented. Nothing here
is a reconstruction of stored team links: every synthetic outcome has
`team_id=None`, which is what the issue measured (0 `teams` rows for `%Pozna%`),
so the name fallback is the path under test.

═══ WHAT IS NOT CLAIMED ═══

No pricing, ranking, dedup, merge-group, series or settlement behaviour moves:
the retained rows are asserted by market/outcome id and by the probabilities the
saved response quotes. Structured `team_id` links are asserted to keep their
existing precedence (an id is read before any name, and a name never overrides
a known id); the candidate does not narrow or widen the id path.
"""

import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

from tests.integration.test_route_related_futures import (
    _make_event,
    _make_market,
    _make_outcome,
    _MockResult,
)

# A fresh event id per route call: the route memoises bodies per event id
# (`_related_futures_cache`), so a reused id would hand one test another
# test's body.
_EVENT_IDS = itertools.count(6806001)


def _fresh_event_id() -> int:
    return next(_EVENT_IDS)


HOME_TEAM_ID = 68061
AWAY_TEAM_ID = 68062
OTHER_TEAM_ID = 68063


def _soccer_event(
    id: int, home: str, away: str, *, sport_key="soccer_uefa_europa_league"
):
    ev = _make_event(
        id=id,
        home_team=home,
        away_team=away,
        status="scheduled",
        sport_key=sport_key,
    )
    ev.sport.name = "Soccer"
    ev.sport_id = 7
    return ev


def _outcome(id, market, name, probability, *, team_id=None):
    o = _make_outcome(
        id=id,
        market=market,
        name=name,
        probability=probability,
        probability_change_24h=0.0,
    )
    o.team_id = team_id
    return o


def _session(event, outcomes, *, team_rows=None):
    """Mock DB session: the route's own queries, answered by statement text.

    `outcomes` is the CANDIDATE set — what the route's step-5 `ILIKE` net would
    return. `team_rows` answers the `teams` lookup (`Team.id, alternate_names,
    roster_players`) per team name; absent means no `teams` row, as measured.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    team_rows = team_rows or {}
    market_ids = sorted({o.market.id for o in outcomes})

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower()
        params = {}
        try:
            params = stmt.compile().params
        except Exception:  # pragma: no cover — text() or non-compilable
            params = {}

        if "from events" in stmt_str:
            return _MockResult(scalar=event)
        if "select sports.id" in stmt_str:
            return _MockResult(rows=[SimpleNamespace(id=7)])
        if "from teams" in stmt_str and "roster_players" in stmt_str:
            # The route filters on Team.name == <event side name>.
            wanted = next((v for k, v in params.items() if k.startswith("name")), None)
            row = team_rows.get(wanted)
            return _MockResult(rows=[row] if row else [], first=row)
        if "from teams" in stmt_str:
            return _MockResult(rows=[])
        if "from futures_outcomes" in stmt_str:
            return _MockResult(scalar_rows=list(outcomes))
        if "from futures_odds_snapshots" in stmt_str:
            return _MockResult(rows=[])
        if "from line_movement_analyses" in stmt_str:
            return _MockResult(scalar=None)
        if "select futures_markets.id" in stmt_str:
            if "order by futures_markets.market_tier" in stmt_str:
                # Season-market discovery (tiers 1-4): the candidate markets.
                return _MockResult(
                    rows=[SimpleNamespace(id=m, market_tier=1) for m in market_ids]
                )
            # Game props (`event_id = :id`, tier 5) and series markets
            # (`ILIKE '%series%'` — a bind param, so not visible in the SQL
            # text): none in these fixtures.
            return _MockResult(rows=[])
        return _MockResult()

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


async def _client_for(monkeypatch, session):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    return app


def _ids(rows):
    return sorted((r["market_id"], r["outcome_id"]) for r in rows)


class _Route:
    """One route call per test, with the patches the populated fixture uses."""

    @staticmethod
    async def get(monkeypatch, session, event_id):
        app = await _client_for(monkeypatch, session)
        try:
            with (
                patch("app.main.init_db", new_callable=AsyncMock),
                patch(
                    "app.services.league_context.enrich_event_with_context",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(f"/api/events/{event_id}/related-futures")
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200, resp.text
        return resp.json()


# ═══════════════════════════════════════════════════════════════════════════
# The specimen: Crystal Palace vs Lech Poznań
# ═══════════════════════════════════════════════════════════════════════════


def _lech_candidates():
    ekstraklasa = _make_market(id=402, name="Ekstraklasa Champion", source="kalshi")
    belgian = _make_market(
        id=59164822, name="Belgian Pro League Champion", source="kalshi"
    )
    fa_cup = _make_market(id=405, name="FA Cup Winner", source="kalshi")
    return [
        # Saved response 2026-09-18: the legitimate club and its false sibling.
        _outcome(4367, ekstraklasa, "Lech Poznan", 0.99),
        _outcome(4369, ekstraklasa, "Lechia Gdansk", 0.01),
        # Issue #6806, production 2026-09-17: the Belgian row (ids invented).
        _outcome(68060001, belgian, "Anderlecht", 0.060),
        # Control: a Belgian outcome no pattern reaches — refused before AND
        # after, so the gate, not the candidate net, is what this file proves.
        _outcome(68060002, belgian, "Royal Charleroi", 0.055),
        # Saved response: the home club's own row.
        _outcome(4412, fa_cup, "Crystal Palace", 0.01),
    ]


async def _lech_body(monkeypatch, rows=None, team_rows=None):
    eid = _fresh_event_id()
    event = _soccer_event(eid, "Crystal Palace", "Lech Poznań")
    session = _session(
        event, rows if rows is not None else _lech_candidates(), team_rows=team_rows
    )
    return await _Route.get(monkeypatch, session, eid)


class TestLechPoznanNamesItself:
    async def test_the_away_card_holds_only_lech_poznan(self, monkeypatch):
        """RED ON BASE: away served (402, 4369) Lechia and (59164822, …) Anderlecht
        beside (402, 4367)."""
        body = await _lech_body(monkeypatch)
        assert _ids(body["away_team_futures"]) == [(402, 4367)]
        (lech,) = body["away_team_futures"]
        assert lech["outcome_name"] == "Lech Poznan"
        assert lech["probability"] == 0.99

    async def test_anderlecht_is_refused_by_name(self, monkeypatch):
        """`Lech` inside `Anderlecht` is an interior fragment, not the club."""
        body = await _lech_body(monkeypatch)
        served = body["home_team_futures"] + body["away_team_futures"]
        assert all(r["market_id"] != 59164822 for r in served)

    async def test_lechia_gdansk_is_refused_by_name(self, monkeypatch):
        """`Lech` is a PREFIX of `Lechia`; a prefix is still not the club."""
        body = await _lech_body(monkeypatch)
        served = body["home_team_futures"] + body["away_team_futures"]
        assert (402, 4369) not in _ids(served)

    async def test_the_home_card_is_untouched(self, monkeypatch):
        body = await _lech_body(monkeypatch)
        assert _ids(body["home_team_futures"]) == [(405, 4412)]
        assert body["total_count"] == 2
        assert body["series_markets"] == []

    async def test_every_spelling_of_the_club_itself_is_kept(self, monkeypatch):
        """Kalshi writes `Lech Poznan`; the event says `Lech Poznań`. Each label
        is reached through the `Lech` token at a word boundary — the same token
        that reached it before — so the accent costs nothing here."""
        ekstraklasa = _make_market(id=402, name="Ekstraklasa Champion", source="kalshi")
        rows = [
            _outcome(4367, ekstraklasa, "Lech Poznan", 0.99),
            _outcome(68060010, ekstraklasa, "Lech Poznań", 0.99),  # accented
            _outcome(
                68060011, ekstraklasa, "KKS Lech Poznań", 0.99
            ),  # club-type prefix
            _outcome(68060012, ekstraklasa, "Poznań", 0.99),  # bare city label
        ]
        body = await _lech_body(monkeypatch, rows)
        assert _ids(body["away_team_futures"]) == [
            (402, 4367),
            (402, 68060010),
            (402, 68060011),
            (402, 68060012),
        ]


# ═══════════════════════════════════════════════════════════════════════════
# Controls: legitimate suffix / city labels survive; interior fragments do not
# ═══════════════════════════════════════════════════════════════════════════


class TestLegitimateLabelsSurvive:
    async def test_celtics_and_boston_and_76ers_still_classify(self, monkeypatch):
        eid = _fresh_event_id()
        event = _make_event(
            id=eid,
            home_team="Boston Celtics",
            away_team="Philadelphia 76ers",
            status="scheduled",
        )
        champ = _make_market(id=101, name="2026 NBA Champion", source="kalshi")
        # A market with NO merge group, so the label variants are not folded
        # into one row by `dedup_by_merge_group` / `merge_relabel_collisions`
        # (both unchanged) and each id can be asserted on its own.
        wins = _make_market(id=104, name="Most Regular Season Wins", source="kalshi")
        rows = [
            _outcome(201, champ, "Boston Celtics", 0.42),  # full name
            _outcome(204, wins, "Celtics", 0.40),  # mascot suffix
            _outcome(205, wins, "Boston", 0.40),  # Kalshi city label
            _outcome(203, champ, "Philadelphia 76ers", 0.08),
            _outcome(206, wins, "76ers", 0.07),  # digit-led mascot
            _outcome(207, wins, "Philadelphia", 0.07),
            # Interior fragments of a legitimate token are refused:
            _outcome(208, wins, "Bostonians", 0.01),  # 'Boston' + 'ians'
            _outcome(209, wins, "Celticsville", 0.01),  # 'Celtics' + 'ville'
        ]
        body = await _Route.get(monkeypatch, _session(event, rows), eid)
        assert _ids(body["home_team_futures"]) == [(101, 201), (104, 204), (104, 205)]
        assert _ids(body["away_team_futures"]) == [(101, 203), (104, 206), (104, 207)]

    async def test_hyphen_apostrophe_and_diacritic_labels(self, monkeypatch):
        eid = _fresh_event_id()
        event = _soccer_event(
            eid, "Saint-Étienne", "Oakland A's", sport_key="soccer_test"
        )
        m = _make_market(id=301, name="Test Cup Winner", source="kalshi")
        rows = [
            _outcome(401, m, "AS Saint-Étienne", 0.3),  # hyphen + diacritic, prefixed
            _outcome(402, m, "Saint-Étienne", 0.3),
            _outcome(403, m, "Oakland A's", 0.2),  # apostrophe inside the pattern
            _outcome(404, m, "Oakland", 0.2),  # city label
            _outcome(405, m, "Oaklandia FC", 0.0),  # interior: refused
            # `A's` is 3 characters: `_team_name_patterns` never emitted it
            # (len >= 4 gate), so it is unreachable before and after alike.
            _outcome(406, m, "A's", 0.2),
        ]
        body = await _Route.get(monkeypatch, _session(event, rows), eid)
        assert _ids(body["home_team_futures"]) == [(301, 401), (301, 402)]
        assert _ids(body["away_team_futures"]) == [(301, 403), (301, 404)]

    async def test_like_metacharacters_in_a_club_name_round_trip(self, monkeypatch):
        """`_escape_like` writes `\\%`, `\\_`, `\\\\`; the boundary test must read
        them back as the literal characters before matching."""
        eid = _fresh_event_id()
        # One-token home name: its only pattern is the escaped full name, so
        # nothing generic like `Club` can reach a label by a second route.
        event = _soccer_event(eid, "100%ers", "Under_Score FC", sport_key="soccer_test")
        m = _make_market(id=302, name="Test Cup Winner", source="kalshi")
        rows = [
            _outcome(501, m, "100%ers", 0.3),
            _outcome(502, m, "Under_Score FC", 0.3),
            _outcome(503, m, "Under_Score", 0.3),  # city half of the away name
            _outcome(504, m, "Underscore FC", 0.0),  # `_` is literal, not a wildcard
            _outcome(505, m, "100Xers", 0.0),  # `%` is literal, not a wildcard
            _outcome(506, m, "1100%ers", 0.0),  # interior: refused
        ]
        body = await _Route.get(monkeypatch, _session(event, rows), eid)
        assert _ids(body["home_team_futures"]) == [(302, 501)]
        assert _ids(body["away_team_futures"]) == [(302, 502), (302, 503)]

    async def test_a_short_alternate_name_no_longer_reaches_another_city(
        self, monkeypatch
    ):
        """`alternate_names` are patterns too. A stored `LA` alias used to claim
        every `Atlanta` outcome (`'la' in 'atlanta'`); at a token boundary it
        claims `LA Clippers` and nothing else. (Alias content is SYNTHETIC.)"""
        eid = _fresh_event_id()
        event = _make_event(
            id=eid,
            home_team="Los Angeles Clippers",
            away_team="Atlanta Hawks",
            status="scheduled",
        )
        wins = _make_market(id=111, name="Most Regular Season Wins", source="kalshi")
        rows = [
            _outcome(601, wins, "LA Clippers", 0.05),
            _outcome(602, wins, "Atlanta Hawks", 0.02),
            _outcome(603, wins, "Atlanta", 0.02),
        ]
        team_rows = {
            "Los Angeles Clippers": SimpleNamespace(
                id=HOME_TEAM_ID, alternate_names=["LA", "Clippers"], roster_players=None
            ),
        }
        body = await _Route.get(
            monkeypatch, _session(event, rows, team_rows=team_rows), eid
        )
        assert _ids(body["home_team_futures"]) == [(111, 601)]
        assert _ids(body["away_team_futures"]) == [(111, 602), (111, 603)]


# ═══════════════════════════════════════════════════════════════════════════
# Structured team ids keep their precedence
# ═══════════════════════════════════════════════════════════════════════════


def _linked_team_rows():
    return {
        "Lech Poznań": SimpleNamespace(
            id=AWAY_TEAM_ID, alternate_names=None, roster_players=None
        ),
        "Crystal Palace": SimpleNamespace(
            id=HOME_TEAM_ID, alternate_names=None, roster_players=None
        ),
    }


class TestStructuredLinksKeepPrecedence:
    async def test_a_matching_team_id_is_kept_whatever_the_label_says(
        self, monkeypatch
    ):
        """A stored link to the away club wins even under a label the name
        fallback would refuse — the id path is not being narrowed."""
        m = _make_market(id=402, name="Ekstraklasa Champion", source="kalshi")
        rows = [_outcome(4367, m, "KKS LP", 0.99, team_id=AWAY_TEAM_ID)]
        body = await _lech_body(monkeypatch, rows, team_rows=_linked_team_rows())
        assert _ids(body["away_team_futures"]) == [(402, 4367)]
        assert body["home_team_futures"] == []

    async def test_a_known_id_is_read_before_any_name(self, monkeypatch):
        """Id first, name second — pinned. An outcome whose stored link says
        HOME sits on the home card even under a label that names the away club;
        the name fallback never contradicts a known id. An outcome linked to a
        THIRD id still reaches the name fallback exactly as before — narrowing
        that is a recall question this candidate does not answer (REPORT.md)."""
        m = _make_market(id=402, name="Ekstraklasa Champion", source="kalshi")
        rows = [
            _outcome(4367, m, "Lech Poznan", 0.99, team_id=AWAY_TEAM_ID),
            _outcome(68060020, m, "Lech Poznan", 0.00, team_id=HOME_TEAM_ID),
            _outcome(68060021, m, "Lech Poznan", 0.00, team_id=OTHER_TEAM_ID),
        ]
        body = await _lech_body(monkeypatch, rows, team_rows=_linked_team_rows())
        assert _ids(body["home_team_futures"]) == [(402, 68060020)]
        assert _ids(body["away_team_futures"]) == [(402, 4367), (402, 68060021)]

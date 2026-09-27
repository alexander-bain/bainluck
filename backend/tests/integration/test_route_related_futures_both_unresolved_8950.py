"""#8950 — England's Bigger Picture stops listing New England Revolution's MLS
odds and the women's World Cup.

WHAT A READER SAW (production, 2026-09-26 22:05Z, 390px; re-read 2026-09-27
03:1xZ on `/api/events/15316107/related-futures`): Croatia v England (Oct 3,
World Cup qualifier). The England card listed "MLS Cup Winner 2026" (New
England Revolution, 1707581), "MLS Cup Champion" and "MLS Eastern Conference
Champion" (outcome "New England", 383343 / 383321) and "2027 FIFA Women's World
Cup Champion" (outcome "England", 210850498).

Two causes, one per half:

* The event is `soccer_other` with BOTH team ids NULL, so the family roster
  was never read and #8920's name-only identity was never built. `England` is
  a whole token of `New England`, and nothing refused it.
* `soccer_other` arms no gender filter, although the event row carries
  `llm_gender = 'men'`.

Harness: `test_route_related_futures_team_paths_7867.py`. Production ids.
"""

from tests.integration.test_route_related_futures import _make_market
from tests.integration.test_route_related_futures_team_paths_7867 import (
    _MockResult,
    _event,
    _get,
    _ids,
    _outcome,
    _session,
)

from app.routes.events import _is_mens_fixture_by_event

SOCCER_OTHER, WC, UNL, MLS = 889501, 889502, 889503, 889504

SOCCER = [
    (1908, WC, "England", None, None, None),
    (17788, UNL, "England", "ENG", "England", None),
    (20, MLS, "New England Revolution", "NE", "New England Revolution",
     ["revs", "New England", "New England Revolution"]),
]


def _outcomes():
    mls_poly = _make_market(id=128718, name="MLS Cup Winner 2026", source="polymarket")
    mls_cup = _make_market(id=23502, name="MLS Cup Champion", source="kalshi")
    mls_east = _make_market(id=23501, name="MLS Eastern Conference Champion", source="kalshi")
    wwc = _make_market(id=56775503, name="2027 FIFA Women's World Cup Champion", source="polymarket")
    euros = _make_market(id=55674162, name="2028 UEFA Euros Champion", source="polymarket")
    return [
        _outcome(1707581, mls_poly, "New England Revolution", 0.0335),
        _outcome(383343, mls_cup, "New England", 0.025),
        _outcome(383321, mls_east, "New England", 0.05),
        _outcome(210850498, wwc, "England", 0.0785),
        _outcome(225950001, euros, "England", 0.14),      # constructed id — England's own
        _outcome(225950002, euros, "Croatia", 0.02),      # constructed id — Croatia's own
    ]


MLS_ROWS = {1707581, 383343, 383321}
WOMENS_ROW = 210850498


def _session_with_gender_filter(event, outcomes, **kw):
    """The shared session answers every `select futures_markets.id` with no
    rows, which the route reads as "the men's filter would empty the pool,
    keep everything", and serves every outcome whatever market ids the
    outcome read asks for. Answer the filter the way its statement asks — the
    markets whose name carries none of its refused words — and then serve only
    those markets' outcomes."""
    session = _session(event, outcomes, **kw)
    inner = session.execute.side_effect
    markets = {o.market.id: o.market.name for o in outcomes}
    kept: dict = {}

    async def execute(stmt, *args, **kwargs):
        s = str(stmt).lower()
        if s.startswith("select futures_markets.id") and "not like" in s:
            kept["ids"] = {
                m for m, name in markets.items()
                if not any(w in name.lower() for w in ("women", "wnba", "wncaa"))
            }
            return _MockResult(rows=[type("R", (), {"id": m})() for m in kept["ids"]])
        if "from futures_outcomes" in s and "ids" in kept:
            return _MockResult(scalar_rows=[o for o in outcomes if o.market.id in kept["ids"]])
        return await inner(stmt, *args, **kwargs)

    session.execute.side_effect = execute
    return session


def _croatia_england(llm_gender="men"):
    event = _event("Croatia", "England", sport_key="soccer_other", sport_id=SOCCER_OTHER)
    event.llm_gender = llm_gender
    return event


async def test_england_loses_new_englands_mls_rows_and_the_womens_world_cup(monkeypatch):
    event = _croatia_england()
    body = await _get(
        monkeypatch,
        _session_with_gender_filter(event, _outcomes(), roster=SOCCER, home_team_id=None,
                                    away_team_id=None, sport_ids=[SOCCER_OTHER, WC, UNL, MLS]),
        event.id,
    )
    assert not (MLS_ROWS | {WOMENS_ROW}) & _ids(body)
    assert 225950001 in _ids(body, "away_team_futures")
    assert 225950002 in _ids(body, "home_team_futures")


async def test_an_unsure_gender_keeps_the_womens_row(monkeypatch):
    """CONTROL for the gender half: the same fixture classified `mixed` arms
    nothing, so the women's row is served exactly as before. The MLS rows
    still go — that half does not read the gender."""
    event = _croatia_england(llm_gender="mixed")
    body = await _get(
        monkeypatch,
        _session_with_gender_filter(event, _outcomes(), roster=SOCCER, home_team_id=None,
                                    away_team_id=None, sport_ids=[SOCCER_OTHER, WC, UNL, MLS]),
        event.id,
    )
    assert WOMENS_ROW in _ids(body, "away_team_futures")
    assert not MLS_ROWS & _ids(body)


async def test_new_englands_own_page_keeps_its_mls_rows(monkeypatch):
    """CONTROL for the name half, the other direction: a both-unresolved
    `New England` fixture keeps every row that extends its own name."""
    event = _event("New England", "Toronto", sport_key="soccer_other", sport_id=SOCCER_OTHER)
    event.llm_gender = "mixed"
    body = await _get(
        monkeypatch,
        _session_with_gender_filter(event, _outcomes()[:3], roster=SOCCER, home_team_id=None,
                                    away_team_id=None, sport_ids=[SOCCER_OTHER, MLS]),
        event.id,
    )
    assert MLS_ROWS <= _ids(body, "home_team_futures")


def test_the_mens_arm_needs_a_no_league_key_and_exactly_men():
    assert _is_mens_fixture_by_event("soccer_other", "men", "Croatia", "England")
    assert not _is_mens_fixture_by_event("soccer_uefa_nations_league", "men", "Croatia", "England")
    for gender in ("mixed", "unknown", "women", None):
        assert not _is_mens_fixture_by_event("soccer_other", gender, "Croatia", "England")


def test_a_side_named_as_a_womens_team_vetoes_the_mens_arm():
    """Production 30-day read: three `_other` events classified `men` are
    women's fixtures that say so in a name."""
    assert not _is_mens_fixture_by_event(
        "soccer_other", "men", "Real Madrid CF Femenino", "Paris Saint-Germain FC")
    assert not _is_mens_fixture_by_event(
        "soccer_other", "men", "Manchester City WFC", "Real Madrid CF Femenino")
    assert not _is_mens_fixture_by_event("soccer_other", "men", "Barcelona W", "Chelsea")
    # a word that merely CONTAINS a marker is not one
    assert _is_mens_fixture_by_event("soccer_other", "men", "Wolves", "Fembridge Town")

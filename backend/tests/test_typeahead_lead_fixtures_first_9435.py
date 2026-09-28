"""#9435 — typing `giants` shows the New York Giants' own game under their card.

Production 2026-09-28 18:2xZ, `GET /api/events/typeahead?q=giants`: the New York
Giants card, then four Yomiuri/Lotte Giants games and no New York Giants game.
The upcoming-games fetch (8 rows, soonest first) held the Giants' Oct 4 game as
row 8. Because it was fetched, #5201's rescue arm stayed off and #4615 marked it
as the team's own — then the four-slot cut dropped it before anything was scored.

The eight rows below are the ids, names and order production held (db-query,
same minute). The route wiring is proven against real Postgres in
`tests/integration/test_typeahead_lead_fixture_survives_the_cut_pg_9435.py`.
"""

import ast
import pathlib
from datetime import datetime, timedelta, timezone

from app.models.models import Event
from app.routes.events import _EVENT_POOL_SIZE, _typeahead_lead_fixtures_first

T0 = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)
NYG_GAME = 14780551

_PRODUCTION_FETCH = [
    (15320894, "Hiroshima Toyo Carp", "Yomiuri Giants", 0),
    (15320890, "Kiwoom Heroes", "Lotte Giants", 0.5),
    (15318295, "Yomiuri Giants", "Hanshin Tigers", 48),
    (15318694, "Yomiuri Giants", "Tokyo Yakult Swallows", 72),
    (15320406, "Essendon Bombers", "GWS GIANTS", 90),
    (15319386, "Yokohama BayStars", "Yomiuri Giants", 96),
    (15317884, "Chiba Lotte Marines", "Tohoku Rakuten Golden Eagles", 97),
    (NYG_GAME, "Arizona Cardinals", "New York Giants", 128),
]


def _rows():
    return [
        Event(id=i, away_team_name=a, home_team_name=h,
              commence_time=T0 + timedelta(hours=hrs), status="scheduled")
        for i, a, h, hrs in _PRODUCTION_FETCH
    ]


def _ids(rows):
    return [r.id for r in rows]


def test_the_strawman_reproduces_production():
    """The cut alone, on the fetched order: the Giants' own game is gone."""
    assert NYG_GAME not in _ids(_rows()[:_EVENT_POOL_SIZE])


def test_the_lead_teams_game_survives_the_cut_and_leads():
    kept = _typeahead_lead_fixtures_first(_rows(), {NYG_GAME})[:_EVENT_POOL_SIZE]
    assert _ids(kept) == [NYG_GAME, 15320894, 15320890, 15318295]


def test_lead_rows_keep_their_order_and_so_do_the_others():
    """Stable on both sides: a team's next game still precedes its later ones."""
    rows = _rows()
    lead = {15318694, NYG_GAME, 15320890}
    out = _ids(_typeahead_lead_fixtures_first(rows, lead))
    assert out == [15320890, 15318694, NYG_GAME, 15320894, 15318295, 15320406,
                   15319386, 15317884]


def test_no_lead_team_leaves_the_pool_untouched():
    rows = _rows()
    assert _typeahead_lead_fixtures_first(rows, set()) is rows


def test_a_pool_already_led_by_the_team_is_unchanged():
    """The `dodgers` shape: every fetched row is the team's own."""
    rows = _rows()
    assert _ids(_typeahead_lead_fixtures_first(rows, set(_ids(rows)))) == _ids(rows)


def _typeahead_ast():
    source = pathlib.Path("app/routes/events.py")
    if not source.exists():  # pytest may run from the repo root
        source = pathlib.Path("backend/app/routes/events.py")
    for node in ast.parse(source.read_text()).body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "typeahead_search":
            return node
    raise AssertionError("typeahead_search is gone from routes/events.py")


def _lines(fn, predicate):
    return [n.lineno for n in ast.walk(fn) if predicate(n)]


def _calls(name):
    return lambda n: (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                      and n.func.id == name)


def test_the_route_orders_the_pool_after_every_filter_and_before_the_cut():
    fn = _typeahead_ast()
    lead_first = _lines(fn, _calls("_typeahead_lead_fixtures_first"))
    filters = (_lines(fn, _calls("_typeahead_fold_twins"))
               + _lines(fn, _calls("_typeahead_stem_only_event")))
    cut = _lines(fn, lambda n: (
        isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice)
        and isinstance(n.slice.upper, ast.Name) and n.slice.upper.id == "_EVENT_POOL_SIZE"
    ))
    assert len(lead_first) == 1, "typeahead_search no longer orders the lead team first (#9435)"
    assert filters and cut
    assert max(filters) < lead_first[0] < min(cut), (
        "the lead team's rows must be ordered after the fold and the stem filter "
        "(which can hand or drop promotions) and before the four-slot cut"
    )

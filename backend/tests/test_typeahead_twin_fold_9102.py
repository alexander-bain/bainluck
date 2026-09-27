"""#9102 — the search dropdown stops offering one game twice.

Not a regression of #8100: that fold is live on `/search`; `/typeahead` never
called it. Production 2026-09-27 08:47Z, `GET /api/events/typeahead?q=illawarra`
served tonight's live NBL game as two rows —

    15319209 basketball_nbl live 08:00Z  Illawarra Hawks at Sydney Kings
    15316536 basketball_nbl live 08:00Z  Illawarra Hawks at Sydney Kings

— while `/search?q=illawarra` drew it once (15319209, LIVE 57–41, 96%).

The two rows below carry the stored values production held for them (db-query,
same minute): `15319209` is the Odds-API row with the score and one sportsbook
count; `15316536` is Polymarket-born, id-less, holding the Kalshi and Polymarket
prices. Real `Event` objects, not MagicMock, because the fold keys on attributes a
MagicMock would answer with truthy auto-attributes.
"""

import ast
import pathlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.models.models import Event, Sport
from app.routes import events as events_route
from app.routes.events import _typeahead_fold_twins
from app.utils.search_fixture_dedup import collapse_duplicate_fixtures

NBL = Sport(id=11, key="basketball_nbl", name="NBL", group="Basketball", active=True)
TIP = datetime(2026, 9, 27, 8, 0, tzinfo=timezone.utc)


def _event(id, *, commence=TIP, external_id=None, source=None, scores=(None, None),
           sources=None, away="Illawarra Hawks", home="Sydney Kings"):
    e = Event(
        id=id,
        sport_id=NBL.id,
        away_team_name=away,
        home_team_name=home,
        commence_time=commence,
        status="live",
        external_id=external_id,
        espn_id=None,
        commence_time_source=source,
        home_score=scores[0],
        away_score=scores[1],
        win_probability_sources=sources,
    )
    e.sport = NBL
    return e


def _odds_api_row():
    return _event(
        15319209,
        external_id="e3d95f03d2e5d29e2d04bea6d66a4acb",
        source="odds_api",
        scores=(63, 45),
        sources={"betting_book_count": 1},
    )


def _polymarket_row():
    return _event(
        15316536,
        source="polymarket_venue",
        sources={"kalshi": {"value": 0.965}, "polymarket": {"value": 0.96}},
    )


def _upcoming(id, days):
    return _event(id, commence=TIP + timedelta(days=days), away="Adelaide 36ers",
                  home="Illawarra Hawks")


class TestTheSpecimen:
    def test_the_collapse_alone_keeps_both_rows(self):
        """Strawman: the dropdown's only dedup before #9102 lets the pair through."""
        kept, dropped = collapse_duplicate_fixtures([_odds_api_row(), _polymarket_row()])
        assert [e.id for e in kept] == [15319209, 15316536]
        assert dropped == 0

    def test_the_dropdown_offers_the_game_once_and_it_is_the_search_row(self):
        rows = [_odds_api_row(), _polymarket_row(), _upcoming(15319239, 5)]
        kept = _typeahead_fold_twins(rows, set())
        assert [e.id for e in kept] == [15319209, 15319239]

    def test_page_order_does_not_change_the_survivor(self):
        rows = [_polymarket_row(), _upcoming(15319239, 5), _odds_api_row()]
        kept = _typeahead_fold_twins(rows, set())
        assert [e.id for e in kept] == [15319239, 15319209]


class TestControls:
    def test_the_same_clubs_on_another_night_keep_both_rows(self):
        rows = [_odds_api_row(), _event(15399999, commence=TIP + timedelta(days=3))]
        assert [e.id for e in _typeahead_fold_twins(rows, set())] == [15319209, 15399999]

    def test_a_lone_row_and_an_empty_pool_are_untouched(self):
        assert _typeahead_fold_twins([], set()) == []
        lone = [_odds_api_row()]
        assert _typeahead_fold_twins(lone, set()) is lone

    def test_a_fold_failure_serves_the_collapsed_rows(self):
        rows = [_odds_api_row(), _polymarket_row()]
        with patch.object(events_route, "fold_twin_events", side_effect=RuntimeError("boom")):
            assert _typeahead_fold_twins(rows, set()) is rows


class TestPromotionFollowsTheSurvivor:
    def test_a_promoted_twin_hands_its_slot_to_the_row_that_absorbed_it(self):
        promoted = {15316536}
        _typeahead_fold_twins([_odds_api_row(), _polymarket_row()], promoted)
        assert promoted == {15316536, 15319209}

    def test_nothing_is_promoted_that_was_not_promoted_before(self):
        promoted = {15319239}
        _typeahead_fold_twins([_odds_api_row(), _polymarket_row(), _upcoming(15319239, 5)],
                              promoted)
        assert promoted == {15319239}


def _typeahead_ast():
    source = pathlib.Path("app/routes/events.py")
    if not source.exists():  # pytest may run from the repo root
        source = pathlib.Path("backend/app/routes/events.py")
    tree = ast.parse(source.read_text())
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "typeahead_search":
            return node
    raise AssertionError("typeahead_search is gone from routes/events.py")


def _first_line(node, predicate):
    lines = [child.lineno for child in ast.walk(node) if predicate(child)]
    return min(lines) if lines else None


def _calls(name):
    return lambda n: (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                      and n.func.id == name)


def test_the_dropdown_folds_after_the_collapse_and_before_the_pool_cut():
    fn = _typeahead_ast()
    collapse = _first_line(fn, _calls("collapse_duplicate_fixtures"))
    fold = _first_line(fn, _calls("_typeahead_fold_twins"))
    cut = _first_line(fn, lambda n: (
        isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice)
        and isinstance(n.slice.upper, ast.Name) and n.slice.upper.id == "_EVENT_POOL_SIZE"
    ))
    assert fold is not None, "typeahead_search no longer runs the twin fold (#9102)"
    assert collapse is not None and cut is not None
    assert collapse < fold < cut, (
        "the fold must run on the collapsed rows and before the four-slot cut, "
        "or a twin spends a dropdown slot again"
    )

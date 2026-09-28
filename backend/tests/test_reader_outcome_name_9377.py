"""#9377 — a best-of-3 series-length market reads "Over 2.5 total games", not "Yes".

Seen on production 2026-09-28 13:12Z at 390px: typing ``wild card`` in the header
dropdown printed ``Series Total Games: Boston vs New York Y — Yes 47%``. The
market is Kalshi ``KXMLBSERIESGAMES-26BOSNYYWC`` (futures_markets 62455756); its
one stored outcome is ``Yes`` on ticker ``…-3``. The event page's series card had
already learned to read that rung (#9139, ``series_games_rung_label``); the search
card, the typeahead dropdown and the ``/futures/{id}`` page the dropdown opens
asked only the club-name engine, so all three printed a bare ``Yes``.

The served-name sites now share ``series_card_labels.reader_outcome_name``. The
last test pins that as a set: no route may call the club engine on its own.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


def _outcome(oid, ticker, name, prob):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=ticker,
        current_probability=prob,
        current_american_odds=110,
        rank=1,
        current_yes_bid=None,
        current_yes_ask=None,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=None,
    )


def _market(market_id, ticker, name, rungs, *, market_type="unshaped"):
    return SimpleNamespace(
        id=market_id,
        external_id=ticker,
        name=name,
        description=None,
        sport=None,
        sport_name=None,
        category=None,
        llm_sport_category="baseball",
        status="open",
        source="kalshi",
        market_type=market_type,
        mutually_exclusive=False,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        category_tags=None,
        image_url=None,
        outcomes=[_outcome(*r) for r in rungs],
    )


# The production specimen, stored values verbatim (db-query 2026-09-28 13:3xZ).
SPECIMEN = (
    62455756,
    "KXMLBSERIESGAMES-26BOSNYYWC",
    "Series Total Games: Boston vs New York Y",
    [(1, "KXMLBSERIESGAMES-26BOSNYYWC-3", "Yes", 0.47)],
)
# The WNBA sibling family carries the identical shape.
WNBA = (
    62383748,
    "KXWNBASERIESGAMES-26NYMINR1",
    "Series Total Games: New York vs Minnesota",
    [(2, "KXWNBASERIESGAMES-26NYMINR1-3", "Yes", 0.52)],
)
# CONTROL: a bare "Yes" whose ticker is not a series-games rung has no question
# to name, and must keep printing "Yes".
PLAIN_BINARY = (
    60600192,
    "KXINDUS-27JAN01",
    "Will India resume the Indus Waters Treaty?",
    [(3, "KXINDUS-27JAN01-YES", "Yes", 0.12)],
)
# CONTROL: the club engine still fires through the shared helper (#6479).
FIELD = (
    40533,
    "KXSB-27",
    "2027 Pro Football Champion",
    [
        (4, "KXSB-27-LAR", "Los Angeles R", 0.11),
        (5, "KXSB-27-BUF", "Buffalo", 0.10),
    ],
)


def _search_names(spec, *, lean):
    from app.routes.events import _build_search_top_outcomes

    return [o["name"] for o in _build_search_top_outcomes(_market(*spec), lean=lean)]


def _detail_names(spec):
    from app.routes.futures import _format_market_detail

    return [o["name"] for o in _format_market_detail(_market(*spec))["outcomes"]]


@pytest.mark.parametrize("spec", [SPECIMEN, WNBA], ids=["mlb", "wnba"])
@pytest.mark.parametrize("lean", [True, False], ids=["typeahead", "search_card"])
def test_search_prints_the_rung_not_yes_9377(spec, lean):
    assert _search_names(spec, lean=lean) == ["Over 2.5 total games"]


@pytest.mark.parametrize("spec", [SPECIMEN, WNBA], ids=["mlb", "wnba"])
def test_the_page_the_dropdown_opens_prints_the_rung_9377(spec):
    assert _detail_names(spec) == ["Over 2.5 total games"]


@pytest.mark.parametrize("lean", [True, False], ids=["typeahead", "search_card"])
def test_a_plain_binary_yes_is_left_alone_9377(lean):
    assert _search_names(PLAIN_BINARY, lean=lean) == ["Yes"]
    assert _detail_names(PLAIN_BINARY) == ["Yes"]


@pytest.mark.parametrize("lean", [True, False], ids=["typeahead", "search_card"])
def test_the_club_repair_still_rides_the_shared_helper_9377(lean):
    assert _search_names(FIELD, lean=lean) == ["Los Angeles Rams", "Buffalo"]
    assert sorted(_detail_names(FIELD)) == ["Buffalo", "Los Angeles Rams"]


def test_reader_outcome_name_order_9377():
    from app.utils.series_card_labels import reader_outcome_name

    assert reader_outcome_name("KXMLBSERIESGAMES-26BOSNYYWC-3", "Yes") == (
        "Over 2.5 total games"
    )
    assert reader_outcome_name("KXSB-27-LAR", "Los Angeles R") == "Los Angeles Rams"
    assert reader_outcome_name("KXINDUS-27JAN01-YES", "Yes") is None
    assert reader_outcome_name(None, "Yes") is None


# The files allowed to name the club engine: its definition, and the one helper
# that composes it with the rung. Every served-name site goes through the helper.
_ENGINE_OWNERS = {
    "app/utils/game_market_club_names.py",
    "app/utils/series_card_labels.py",
}


def test_no_served_name_site_calls_the_club_engine_alone_9377():
    backend = Path(__file__).resolve().parents[1]
    offenders = []
    callers = set()
    for path in sorted((backend / "app").rglob("*.py")):
        rel = path.relative_to(backend).as_posix()
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
            if name == "repair_field_outcome_name" and rel not in _ENGINE_OWNERS:
                offenders.append(f"{rel}:{node.lineno}")
            if name == "reader_outcome_name":
                callers.add(rel)
    assert offenders == [], offenders
    # The set this ship routed, so a site deleted by a refactor is noticed too.
    assert {
        "app/routes/events.py",
        "app/routes/feed.py",
        "app/routes/futures.py",
        "app/routes/user.py",
    } <= callers, callers

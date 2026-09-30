"""#9383 — a single-leg Kalshi threshold market carries its threshold, not a bare "Yes".

Production 2026-09-28 ~13:40Z: every single-market Kalshi event is stored as one
outcome named ``Yes`` (``_kalshi_outcome_name`` rule 1). On a threshold market the
number the question is about lives only in the venue's leg label, so cards read
"Yakult's Brothers vs. Team Liquid: Total Maps — Yes 52%".

The stored name stays ``Yes`` (29 consumers key on it). The label rides in
``market_metadata.threshold_label``; these arms pin the predicate on the venue
specimens, the parser that feeds it, and the two metadata writers that store it.
"""

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.kalshi_api import KalshiAPIService
from app.utils.kalshi_threshold_label import (
    THRESHOLD_LABEL_KEY,
    THRESHOLD_STRIKE_TYPES,
    single_leg_threshold_label,
)


def _leg(yes_sub_title, strike_type=None, floor_strike=None, cap_strike=None):
    return SimpleNamespace(
        yes_sub_title=yes_sub_title,
        strike_type=strike_type,
        floor_strike=floor_strike,
        cap_strike=cap_strike,
    )


#: Venue reads 2026-09-28 (issue table + KXINXU 13:5xZ). The label is the venue's.
THRESHOLD_SPECIMENS = [
    ("Over 2.5 maps", "greater", 2.5, None),  # 62481272 Total Maps
    ("Above 7743.51", "greater", 7743.51, None),  # 62399155 S&P Up/Down
    ("Above 4.00 pp", "greater", 4.0, None),  # 61461638 minimum wage
    ("Above $1237.81", "greater", 1237.81, None),  # 60481264 Pokemon
    ("1+ overtime periods", "greater_or_equal", 0.5, None),  # 62581504 Overtime
    ("7,845 or above", "greater_or_equal", 7845.0, None),  # KXINXU leg
    ("Below 40", "less", None, 40.0),
    ("Between 3 and 4", "between", 3.0, 4.0),
]


@pytest.mark.parametrize("label,strike_type,floor,cap", THRESHOLD_SPECIMENS)
def test_a_lone_threshold_leg_returns_the_venues_label_verbatim(
    label, strike_type, floor, cap
):
    leg = _leg(label, strike_type, floor, cap)
    assert single_leg_threshold_label([leg]) == label


def test_the_label_is_trimmed_but_not_retypeset():
    leg = _leg("  7,845 or above ", "greater_or_equal", 7845.0)
    assert single_leg_threshold_label([leg]) == "7,845 or above"


# ── each clause refuses a real plain binary (venue reads in the issue) ─────


def test_CONTROL_no_strike_type_is_a_plain_question():
    # KXCANADACUP-30: strike None, strike_type None.
    assert single_leg_threshold_label([_leg("Canada")]) is None


def test_CONTROL_a_threshold_strike_type_whose_label_is_Yes_stays_Yes():
    # KXMIDTERMHAPPEN-2026-T50: greater_or_equal, but yes_sub_title='Yes'.
    for answer in ("Yes", "yes", " YES ", "No"):
        leg = _leg(answer, "greater_or_equal", 50.0)
        assert single_leg_threshold_label([leg]) is None


def test_CONTROL_a_strike_type_with_no_numeric_strike_is_refused():
    # KXINDUS-27JAN01-YES shape: a type but strike None on both sides.
    leg = _leg("Over something", "greater")
    assert single_leg_threshold_label([leg]) is None


def test_CONTROL_a_cap_alone_is_a_strike():
    leg = _leg("Below 40", "less", None, 40.0)
    assert single_leg_threshold_label([leg]) == "Below 40"


def test_CONTROL_an_unknown_strike_type_is_refused():
    for strike_type in ("custom", "structured", "functional", ""):
        leg = _leg("Over 2.5 maps", strike_type, 2.5)
        assert single_leg_threshold_label([leg]) is None


@pytest.mark.parametrize("label", [None, "", "   "])
def test_CONTROL_an_empty_label_is_refused(label):
    assert single_leg_threshold_label([_leg(label, "greater", 2.5)]) is None


def test_CONTROL_a_multi_market_event_is_left_to_the_ladder():
    legs = [_leg("Over 2.5 maps", "greater", 2.5), _leg("Over 3.5 maps", "greater", 3.5)]
    assert single_leg_threshold_label(legs) is None
    assert single_leg_threshold_label([]) is None


def test_the_metadata_key_is_the_one_the_issue_names():
    assert THRESHOLD_LABEL_KEY == "threshold_label"


def test_the_strike_type_set_is_the_venues_threshold_vocabulary():
    assert THRESHOLD_STRIKE_TYPES == {
        "greater",
        "greater_or_equal",
        "less",
        "less_or_equal",
        "between",
    }


# ── the parser feeds the predicate ─────────────────────────────────────────


def _payload(**extra):
    base = {
        "ticker": "KXINXU-26SEP28H1000-T7844.9999",
        "event_ticker": "KXINXU-26SEP28H1000",
        "title": "S&P 500",
        "yes_sub_title": "7,845 or above",
        "status": "active",
    }
    base.update(extra)
    return base


def test_parse_market_carries_the_strike_fields():
    market = KalshiAPIService()._parse_market(
        _payload(strike_type="greater_or_equal", floor_strike=7845, cap_strike=None)
    )
    assert market is not None
    assert market.strike_type == "greater_or_equal"
    assert market.floor_strike == 7845.0
    assert market.cap_strike is None
    assert single_leg_threshold_label([market]) == "7,845 or above"


@pytest.mark.parametrize("odd", ["", "n/a", True, [], {}])
def test_an_odd_strike_never_drops_the_market(odd):
    market = KalshiAPIService()._parse_market(
        _payload(strike_type="greater", floor_strike=odd)
    )
    assert market is not None
    assert market.floor_strike is None


def test_parse_market_without_strike_fields_leaves_them_none():
    market = KalshiAPIService()._parse_market(_payload())
    assert market is not None
    assert (market.strike_type, market.floor_strike, market.cap_strike) == (
        None,
        None,
        None,
    )
    assert single_leg_threshold_label([market]) is None


# ── both metadata writers store it ─────────────────────────────────────────


def _writer_functions():
    from app.tasks import kalshi

    tree = ast.parse(Path(inspect.getsourcefile(kalshi)).read_text())
    hits = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls = {
            n.func.id
            for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        keys = {
            n.slice.id
            for n in ast.walk(node)
            if isinstance(n, ast.Subscript)
            and isinstance(n.ctx, ast.Store)
            and isinstance(n.slice, ast.Name)
            and n.slice.id == "THRESHOLD_LABEL_KEY"
        }
        if "single_leg_threshold_label" in calls:
            hits[node.name] = bool(keys)
    return hits


def test_the_poller_and_the_gap_create_writer_both_store_the_label():
    hits = _writer_functions()
    assert hits.get("_poll_kalshi_markets") is True, hits
    assert any(
        name != "_poll_kalshi_markets" and stored for name, stored in hits.items()
    ), hits


# ── serve half: the served-name sites print the label in place of "Yes" ──────


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


def _market(market_id, ticker, name, rungs, metadata):
    return SimpleNamespace(
        id=market_id,
        external_id=ticker,
        name=name,
        description=None,
        sport=None,
        sport_name=None,
        category=None,
        llm_sport_category="esports",
        status="open",
        source="kalshi",
        market_type="unshaped",
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
        market_metadata=metadata,
        outcomes=[_outcome(*r) for r in rungs],
    )


#: 62481272 as stored, plus the key the ingest half now writes.
TOTAL_MAPS = (
    62481272,
    "KXVALORANTMAP-26SEP28YBTL",
    "Yakult's Brothers vs. Team Liquid: Total Maps",
    [(1, "KXVALORANTMAP-26SEP28YBTL-2", "Yes", 0.52)],
    {"kalshi_event_ticker": "KXVALORANTMAP-26SEP28YBTL", "threshold_label": "Over 2.5 maps"},
)
#: CONTROL: the same row BEFORE the next poll stamps the key — unchanged.
TOTAL_MAPS_UNSTAMPED = TOTAL_MAPS[:4] + ({"kalshi_event_ticker": "KXVALORANTMAP-26SEP28YBTL"},)
#: CONTROL: a plain binary carries no key and keeps "Yes".
PLAIN_BINARY = (
    60600192,
    "KXINDUS-27JAN01",
    "Will India resume the Indus Waters Treaty?",
    [(3, "KXINDUS-27JAN01-YES", "Yes", 0.12)],
    {"kalshi_event_ticker": "KXINDUS-27JAN01"},
)


def _search_names(spec, *, lean):
    from app.routes.events import _build_search_top_outcomes

    return [o["name"] for o in _build_search_top_outcomes(_market(*spec), lean=lean)]


def _detail_names(spec):
    from app.routes.futures import _format_market_detail

    return [o["name"] for o in _format_market_detail(_market(*spec))["outcomes"]]


@pytest.mark.parametrize("lean", [True, False], ids=["typeahead", "search_card"])
def test_search_prints_the_threshold_not_yes(lean):
    assert _search_names(TOTAL_MAPS, lean=lean) == ["Over 2.5 maps"]


def test_the_page_the_dropdown_opens_prints_the_threshold():
    assert _detail_names(TOTAL_MAPS) == ["Over 2.5 maps"]


@pytest.mark.parametrize("lean", [True, False], ids=["typeahead", "search_card"])
@pytest.mark.parametrize(
    "spec", [TOTAL_MAPS_UNSTAMPED, PLAIN_BINARY], ids=["unstamped", "plain_binary"]
)
def test_CONTROL_no_label_keeps_printing_yes(spec, lean):
    assert _search_names(spec, lean=lean) == ["Yes"]
    assert _detail_names(spec) == ["Yes"]


def test_reader_outcome_name_replaces_only_a_bare_yes():
    from app.utils.series_card_labels import reader_outcome_name

    assert reader_outcome_name("KX-2", "Yes", "Over 2.5 maps") == "Over 2.5 maps"
    assert reader_outcome_name("KX-2", " yes ", "Over 2.5 maps") == "Over 2.5 maps"
    # A label never renames a real leg, and "No" is not "Yes".
    assert reader_outcome_name("KX-2", "Team Liquid", "Over 2.5 maps") is None
    assert reader_outcome_name("KX-2", "No", "Over 2.5 maps") is None
    # Absent label: the #9377 order is unchanged.
    assert reader_outcome_name("KXMLBSERIESGAMES-26BOSNYYWC-3", "Yes", None) == (
        "Over 2.5 total games"
    )
    assert reader_outcome_name("KXINDUS-27JAN01-YES", "Yes", None) is None


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({"threshold_label": "Over 2.5 maps"}, "Over 2.5 maps"),
        ({"threshold_label": "  Above 7743.51 "}, "Above 7743.51"),
        ({"threshold_label": "   "}, None),
        ({"threshold_label": 2.5}, None),
        ({}, None),
        (None, None),
        ("not-a-dict", None),
    ],
)
def test_market_threshold_label_tolerates_every_stored_shape(metadata, expected):
    from app.utils.kalshi_threshold_label import market_threshold_label

    assert market_threshold_label(SimpleNamespace(market_metadata=metadata)) == expected
    assert market_threshold_label(SimpleNamespace()) is None


def test_every_served_name_site_passes_the_markets_label():
    """Each ``reader_outcome_name`` call outside feed.py carries a third argument.

    feed.py's card helper is deliberately left on two: the feed renders a lone
    ``Yes`` as a binary card headed by the market's own question, not as a
    ``Yes`` row, and its printed names double as lookup keys (#6552).
    """
    backend = Path(__file__).resolve().parents[1]
    missing = []
    seen = set()
    for rel in ("app/routes/events.py", "app/routes/futures.py", "app/routes/user.py"):
        tree = ast.parse((backend / rel).read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "reader_outcome_name"
            ):
                seen.add(rel)
                if len(node.args) < 3:
                    missing.append(f"{rel}:{node.lineno}")
    assert missing == [], missing
    assert seen == {"app/routes/events.py", "app/routes/futures.py", "app/routes/user.py"}

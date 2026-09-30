"""#9531 — a ladder's market page heroes the rung its /weather card quotes.

WHAT A READER SAW. `/weather` → tap "Hurricane Polo category?" → `/futures/59699693`
at 390px, 2026-09-29 02:49Z:

    Hurricane Polo category?   100%  Category 1 or above

The card they tapped read "Category 5 or above" (#9283). All five rungs are priced
at 99.5% and the page heroed the first of the tie. The detail payload now names
the median rung as `lead_outcome_id`, which the web page, its unfurl and the
iPhone already hero (#8892), so the page and the card ask one rule.

Every ladder below is `/api/futures/<id>` as served at 06:0xZ 9/29, in serve
order; the expected rung is asserted by equality.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.futures import _format_market_detail
from app.routes.weather import _card_outcome
from app.utils.ladder_headline import ladder_headline_outcome_id

STAMP = datetime(2026, 9, 29, 6, 0, tzinfo=timezone.utc)

POLO = (
    "Hurricane Polo category?",
    [
        ("Category 1 or above", 0.995),
        ("Category 2 or above", 0.995),
        ("Category 5 or above", 0.995),
        ("Category 3 or above", 0.995),
        ("Category 4 or above", 0.995),
    ],
)
ODALYS = (
    "Hurricane Odalys category?",
    [
        ("Category 1 or above", 0.995),
        ("Category 3 or above", 0.995),
        ("Category 4 or above", 0.995),
        ("Category 2 or above", 0.995),
        ("Category 5 or above", 0.01),
    ],
)
NOLO = (
    "Hurricane Nolo category?",
    [
        ("Category 1 or above", 0.995),
        ("Category 3 or above", 0.985),
        ("Category 2 or above", 0.985),
        ("Category 4 or above", 0.835),
        ("Category 5 or above", 0.24),
    ],
)
# Incoherent: Cat 3+ is dearer than Cat 1+, so the price leader is Cat 3+.
LALA = (
    "Hurricane Lala category?",
    [
        ("Category 3 or above", 0.895),
        ("Category 1 or above", 0.88),
        ("Category 2 or above", 0.86),
        ("Category 4 or above", 0.835),
        ("Category 5 or above", 0.015),
    ],
)
# The median IS the leader: the hero was already right and must not move.
ISAIAS = (
    "Hurricane Isaias category?",
    [
        ("Category 1 or above", 0.98),
        ("Category 4 or above", 0.06),
        ("Category 5 or above", 0.04),
        ("Category 2 or above", None),
        ("Category 3 or above", None),
    ],
)
# Loosest priced rung under 50%: no median, the leader stands.
ZEKE = (
    "Hurricane Zeke category?",
    [
        ("Category 1 or above", 0.44),
        ("Category 3 or above", 0.4),
        ("Category 2 or above", 0.28),
        ("Category 4 or above", 0.05),
        ("Category 5 or above", 0.04),
    ],
)
# A date ladder: the /weather card reads "Before Nov 15, 2026" (60%).
NEXT_HURRICANE = (
    "When will the next Atlantic hurricane form?",
    [
        ("Before Dec 1, 2026", 0.675),
        ("Before Nov 15, 2026", 0.605),
        ("Before Nov 1, 2026", 0.485),
        ("Before Oct 15, 2026", 0.365),
        ("Before Oct 1, 2026", 0.02),
    ],
)


def _outcome(oid, name, prob):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"x{oid}",
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=STAMP,
        price_changed_at=STAMP,
        team_id=None,
    )


def _market(spec, status="open"):
    name, legs = spec
    return SimpleNamespace(
        id=59699693,
        name=name,
        description=None,
        category="weather",
        source="kalshi",
        external_id="KXHURCAT",
        status=status,
        sport=None,
        sport_id=None,
        event_id=None,
        market_type="field",
        market_tier=3,
        llm_sport_category="weather",
        mutually_exclusive=False,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=[_outcome(i + 1, n, p) for i, (n, p) in enumerate(legs)],
    )


def _lead_name(market):
    payload = _format_market_detail(market, [], set())
    lead_id = payload["lead_outcome_id"]
    if lead_id is None:
        return None
    return next(o["name"] for o in payload["outcomes"] if o["id"] == lead_id)


@pytest.mark.parametrize(
    "spec, rung",
    [
        (POLO, "Category 5 or above"),
        (ODALYS, "Category 4 or above"),
        (NOLO, "Category 4 or above"),
        (LALA, "Category 4 or above"),
        (NEXT_HURRICANE, "Before Nov 15, 2026"),
    ],
)
def test_the_page_leads_with_the_median_rung(spec, rung):
    assert _lead_name(_market(spec)) == rung


@pytest.mark.parametrize("spec", [ISAIAS, ZEKE])
def test_a_board_whose_leader_is_already_the_answer_serves_null(spec):
    """Byte-identical page: no lead means the client's own leader, unchanged."""
    assert _lead_name(_market(spec)) is None


def test_a_settled_ladder_is_decided_by_its_grade_not_this_rule():
    assert _lead_name(_market(POLO, status="resolved")) is None


def test_a_board_that_is_not_one_ladder_is_never_read():
    """Mixed shapes are not a ladder; the price leader stands."""
    board = _market(
        (
            "Hurricane Polo category?",
            [
                ("Category 1 or above", 0.995),
                ("Category 5 or above", 0.995),
                ("Makes landfall in Mexico", 0.8),
            ],
        )
    )
    assert _lead_name(board) is None


@pytest.mark.parametrize(
    "spec", [POLO, ODALYS, NOLO, LALA, ISAIAS, ZEKE, NEXT_HURRICANE]
)
def test_the_page_heroes_the_row_the_weather_card_quotes(spec):
    """The ship: the card and the page it links to name the same rung.

    With no lead the page heroes its price leader — the first row at the top
    price — so that is what the card must match on those boards.
    """
    market = _market(spec)
    page = _lead_name(market)
    if page is None:
        served = _format_market_detail(market, [], set())["outcomes"]
        page = max(served, key=lambda o: o["probability"] or 0.0)["name"]
    assert page == _card_outcome(market).name


def test_the_leader_tie_break_is_serve_order_as_the_clients_sort():
    """The first row at the top price is the leader, so a median that IS that
    row serves null, and one tied beside it but later does not."""
    rows = [
        {"id": 1, "name": "Category 1 or above", "probability": 0.9},
        {"id": 2, "name": "Category 2 or above", "probability": 0.9},
    ]
    assert ladder_headline_outcome_id(rows, "Hurricane X category?") == 2
    assert ladder_headline_outcome_id(rows[::-1], "Hurricane X category?") is None

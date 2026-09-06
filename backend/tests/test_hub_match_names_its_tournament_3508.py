"""#3508 — a hub match card names the tournament it belongs to.

On `/hub/tennis` a US Open match and a third-tier Challenger rendered as
*identical* bare "Player vs Player" cards: 0 of 81 Kalshi rows on the rail named
their tournament. The reason a previous pass ruled this unbuildable is preserved
in the fixtures below — Kalshi's event `title` and `sub_title` really do carry
only the two players, and the series (`KXWTADOUBLES` = "WTA Doubles Tennis
Match") is a generic year-round series that names no tournament either.

The tournament IS there, in `product_metadata.competition`, on every family. All
event payloads in this file are VERBATIM from Kalshi's own API (notice 26:
series discovery against the venue, 2026-09-06), trimmed only of `markets`.

The damaging regression is a Slam wearing a Challenger's label, so that is
pinned in BOTH directions rather than only asserting the happy path.

Module-level imports are deliberately limited to symbols that exist on the
parent commit; the new symbols are imported inside the arms that need them, so
`test_control_*` genuinely passes on both sides of this change instead of being
a dead control that fails everywhere.
"""

import pytest

from app.services.kalshi_api import KalshiAPIService


# --- Verbatim Kalshi event payloads (markets stripped) ----------------------

US_OPEN_MEN_SINGLES = {
    "category": "Sports",
    "event_ticker": "KXATPMATCH-26SEP06CERBLO",
    "mutually_exclusive": True,
    "product_metadata": {
        "competition": "US Open Men Singles",
        "competition_scope": "Game",
    },
    "series_ticker": "KXATPMATCH",
    "sub_title": "Cerundolo vs Blockx (Sep 6)",
    "title": "Cerundolo vs Blockx",
}

US_OPEN_WOMEN_DOUBLES = {
    "category": "Sports",
    "event_ticker": "KXWTADOUBLES-26SEP06DARLUMBUCMEL",
    "mutually_exclusive": True,
    "product_metadata": {
        "competition": "US Open Women Doubles",
        "competition_scope": "Game",
    },
    "series_ticker": "KXWTADOUBLES",
    "sub_title": "Dart / Lumsden vs Bucsa / Melichar-Martinez (Sep 6)",
    "title": "Dart / Lumsden vs Bucsa / Melichar-Martinez",
}

ATP_CHALLENGER = {
    "category": "Sports",
    "event_ticker": "KXATPCHALLENGERMATCH-26SEP06HOALOM",
    "mutually_exclusive": True,
    "product_metadata": {
        "competition": "ATP Challenger Phan Thiet 3",
        "competition_scope": "Game",
    },
    "series_ticker": "KXATPCHALLENGERMATCH",
    "sub_title": "Hoang vs Lomakin (Sep 6)",
    "title": "Hoang vs Lomakin",
}


class _StubMarket:
    """The attributes `_market_competition` reads off a FuturesMarket."""

    def __init__(self, market_metadata, name="Dart / Lumsden vs Bucsa / Melichar-Martinez"):
        self.market_metadata = market_metadata
        self.name = name


#: (card name, competition) pairs measured on production 2026-09-06 for the
#: OTHER hubs this shared card path also feeds. On every one of them Kalshi's
#: competition merely restates the card, so drawing it literally would put a
#: "MMA" eyebrow over a name already starting "MMA:".
ECHOING_ROWS = [
    ("MMA: Loud vs Natividad", "MMA"),
    ("MMA: Kwon vs Gomes", "MMA"),
    ("331: Chikadze vs Brito", "331"),
    ("331: O'Neill vs Moura", "331"),
    ("Canelo Alvarez vs Christian Mbilli", "Alvarez vs Mbilli"),
    ("Ryan Garcia vs Conor Benn", "Garcia vs Benn"),
]

#: The tennis rows the ship exists for — the label is new information here.
INFORMATIVE_ROWS = [
    ("Dart / Lumsden vs Bucsa / Melichar-Martinez", "US Open Women Doubles"),
    ("Cerundolo vs Blockx", "US Open Men Singles"),
    ("Kim vs Tamm", "ATP Challenger Phan Thiet 3"),
    ("Iannaccone vs Weis", "ATP Challenger Seville"),
    ("Dencheva vs Lachinova", "WTA 125K Montreux"),
]


# --- The venue names the tournament -----------------------------------------


@pytest.mark.parametrize(
    "event_data,expected",
    [
        (US_OPEN_MEN_SINGLES, "US Open Men Singles"),
        (US_OPEN_WOMEN_DOUBLES, "US Open Women Doubles"),
        (ATP_CHALLENGER, "ATP Challenger Phan Thiet 3"),
    ],
    ids=["us-open-singles", "us-open-doubles", "challenger"],
)
def test_competition_is_read_from_the_venues_own_field(event_data, expected):
    from app.services.kalshi_api import _event_competition

    assert _event_competition(event_data) == expected


def test_a_slam_is_never_labelled_a_challenger_and_a_challenger_always_is():
    """The regression that would actually mislead a reader, pinned both ways.

    Asserting only "the Challenger says Challenger" would still pass if every
    card were labelled Challenger, which is the damaging direction.
    """
    from app.services.kalshi_api import _event_competition

    slam = _event_competition(US_OPEN_MEN_SINGLES)
    challenger = _event_competition(ATP_CHALLENGER)

    assert "Challenger" not in slam
    assert "US Open" in slam
    assert "Challenger" in challenger
    assert "US Open" not in challenger
    assert slam != challenger


def test_the_tournament_is_not_recoverable_from_title_or_series():
    """Why this needed the venue field — the case the previous pass measured.

    If this ever fails, Kalshi started naming the tournament somewhere cheaper
    and the ingest capture can be reconsidered.
    """
    for event_data in (US_OPEN_MEN_SINGLES, US_OPEN_WOMEN_DOUBLES, ATP_CHALLENGER):
        assert "Open" not in event_data["title"]
        assert "Challenger" not in event_data["title"]
        # sub_title adds only a date.
        assert event_data["sub_title"].startswith(event_data["title"])


# --- Silence is an answer, never a guess ------------------------------------


@pytest.mark.parametrize(
    "product_metadata",
    [None, {}, {"competition_scope": "Game"}, {"competition": None},
     {"competition": 7}, {"competition": "   "}],
    ids=["null", "empty", "scope-only", "null-value", "non-string", "blank"],
)
def test_no_competition_yields_none_rather_than_a_guess(product_metadata):
    from app.services.kalshi_api import _event_competition

    event_data = dict(ATP_CHALLENGER, product_metadata=product_metadata)
    assert _event_competition(event_data) is None


def test_competition_is_never_derived_from_the_ticker():
    """A Challenger ticker with no venue statement must still yield None.

    The ticker families separate Challenger from main tour, so deriving a label
    from `KXATPCHALLENGERMATCH` is tempting — but the main-tour families are
    generic year-round series carrying US Open and non-US-Open events alike, so
    a ticker-derived label would invent the very fact the reader wants.
    """
    from app.services.kalshi_api import _event_competition

    stripped = {k: v for k, v in ATP_CHALLENGER.items() if k != "product_metadata"}
    assert "CHALLENGER" in stripped["event_ticker"]
    assert _event_competition(stripped) is None


def test_parse_event_carries_the_competition_through():
    service = KalshiAPIService()
    event = service._parse_event(dict(US_OPEN_WOMEN_DOUBLES, markets=[]))

    assert event is not None
    assert event.competition == "US Open Women Doubles"
    # The fields the rest of the pipeline already relied on are untouched.
    assert event.event_ticker == "KXWTADOUBLES-26SEP06DARLUMBUCMEL"
    assert event.title == "Dart / Lumsden vs Bucsa / Melichar-Martinez"


def test_parse_event_without_competition_leaves_it_none():
    service = KalshiAPIService()
    stripped = {k: v for k, v in US_OPEN_MEN_SINGLES.items()
                if k != "product_metadata"}
    event = service._parse_event(dict(stripped, markets=[]))

    assert event is not None
    assert event.competition is None


# --- The card reads what was stored -----------------------------------------


def test_card_competition_comes_from_stored_metadata():
    from app.routes.league_futures import _market_competition

    market = _StubMarket({
        "kalshi_event_ticker": "KXATPMATCH-26SEP06CERBLO",
        "event_title": "Cerundolo vs Blockx",
        "competition": "US Open Men Singles",
    })
    assert _market_competition(market) == "US Open Men Singles"


@pytest.mark.parametrize(
    "metadata",
    [None, {}, {"event_title": "Andreeva vs Potapova"}, {"competition": ""},
     {"competition": None}, "not-a-dict"],
    ids=["null", "empty", "polymarket-shaped", "blank", "null-value", "not-a-dict"],
)
def test_card_competition_is_none_when_nobody_said(metadata):
    """A card that cannot name a tournament prints nothing.

    Polymarket rows carry no competition key — their own name already leads with
    the tournament — so `None` here is the ordinary case, not an error path.
    """
    from app.routes.league_futures import _market_competition

    assert _market_competition(_StubMarket(metadata)) is None


@pytest.mark.parametrize("name,competition", ECHOING_ROWS,
                         ids=[f"{n[:18]}" for n, _ in ECHOING_ROWS])
def test_a_label_that_restates_the_card_is_not_drawn(name, competition):
    """The regression this shared card path would otherwise ship to /hub/mma.

    `_market_competition` reaches EVERY hub, not just tennis. Measured on
    production, the competition on the MMA and boxing rails is the card's own
    name or its prefix, so drawing it re-creates UX-P239 / #3491 — a card
    printing its own question back at itself — on another surface.
    """
    from app.routes.league_futures import _market_competition

    market = _StubMarket({"competition": competition}, name=name)
    assert _market_competition(market) is None


@pytest.mark.parametrize("name,competition", INFORMATIVE_ROWS,
                         ids=[c[:16] for _, c in INFORMATIVE_ROWS])
def test_a_label_that_adds_information_survives_the_echo_check(name, competition):
    """The other direction, and the one that makes the arm above non-trivial.

    A suppressor that dropped everything would satisfy the echo arms perfectly
    and kill the entire ship, so the tennis rows are pinned against exactly the
    same code path.
    """
    from app.routes.league_futures import _market_competition

    market = _StubMarket({"competition": competition}, name=name)
    assert _market_competition(market) == competition


def test_the_echo_check_is_about_information_not_string_prefixes():
    """Boxing is neither an equality nor a prefix match — hence tokens.

    "Alvarez vs Mbilli" is the surnames of "Canelo Alvarez vs Christian Mbilli",
    interleaved with words that are not in the label. An `==` or `startswith`
    suppressor passes every MMA arm above and still ships the boxing echo.
    """
    from app.routes.league_futures import _competition_echoes_name

    name = "Canelo Alvarez vs Christian Mbilli"
    assert not name.startswith("Alvarez vs Mbilli")
    assert name != "Alvarez vs Mbilli"
    assert _competition_echoes_name("Alvarez vs Mbilli", name) is True
    # One genuinely new word is enough to make a label worth drawing.
    assert _competition_echoes_name("WBC Alvarez vs Mbilli", name) is False


def test_the_echo_check_tolerates_a_missing_name():
    from app.routes.league_futures import _competition_echoes_name

    assert _competition_echoes_name("US Open Men Singles", None) is False
    assert _competition_echoes_name("...", "anything") is True


def test_control_serialize_outcomes_shape_is_unchanged():
    """Control: passes on BOTH sides of this change, by design.

    Imports no new symbol, so it holds on the parent commit too — it exists to
    prove the suite is actually running rather than erroring out wholesale.
    """
    from app.routes.league_futures import _serialize_outcomes

    class _O:
        id = 1
        name = "Cerundolo"
        current_probability = 0.6
        opening_probability = 0.55
        rank = 1
        probability_change_24h = None
        team_id = None

    rows = _serialize_outcomes([_O()])
    assert rows == [{
        "id": 1,
        "name": "Cerundolo",
        "probability": 0.6,
        "opening_probability": 0.55,
        "rank": 1,
        "movement_24h": None,
        "team_id": None,
    }]

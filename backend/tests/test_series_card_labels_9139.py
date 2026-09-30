"""#9139 — the event page's SERIES card names its question and its clubs.

Specimen, production 2026-09-27 (``/events/15319563``, Red Sox @ Yankees, AL
Wild Card Game 1), ``GET /api/events/15319563/related-futures`` →
``series_markets``, with the outcome tickers read from ``futures_outcomes``:

    62383730 Series Winner: Boston vs New York Y
        235705604 New York Y  0.575  KXMLBSERIES-26BOSNYYWC-NYY
        235705605 Boston      0.400  KXMLBSERIES-26BOSNYYWC-BOS
    62455755 Series Exact Score: Boston vs New York Y
        236000923 NYY wins 2-0 0.325 KXMLBSERIESSCORE-26BOSNYYWC-NYY20
    62455756 Series Total Games: Boston vs New York Y
        236000927 Yes         0.485  KXMLBSERIESGAMES-26BOSNYYWC-3

The ladder wording is the venue's own, read off resolved NBA/NHL series:
``…-5`` → ``Over 4.5 total games``, ``…-6`` → ``Over 5.5 total games``, and the
top rung ``KXNBASERIESGAMES-26MINSASR2-7`` stored as bare ``Yes``.
"""

from __future__ import annotations

import copy
import inspect
import re

import pytest

from app.utils.series_card_labels import relabel_series_card, series_games_rung_label


def _specimen() -> tuple[list[dict], dict[int, str]]:
    markets = [
        {
            "market_id": 62383730,
            "market_name": "Series Winner: Boston vs New York Y",
            "source": "kalshi",
            "outcomes": [
                {"outcome_id": 235705604, "name": "New York Y", "probability": 0.575},
                {"outcome_id": 235705605, "name": "Boston", "probability": 0.4},
            ],
        },
        {
            "market_id": 62455755,
            "market_name": "Series Exact Score: Boston vs New York Y",
            "source": "kalshi",
            "outcomes": [
                {"outcome_id": 236000923, "name": "NYY wins 2-0", "probability": 0.325},
            ],
        },
        {
            "market_id": 62455756,
            "market_name": "Series Total Games: Boston vs New York Y",
            "source": "kalshi",
            "outcomes": [
                {"outcome_id": 236000927, "name": "Yes", "probability": 0.485},
            ],
        },
    ]
    tickers = {
        235705604: "KXMLBSERIES-26BOSNYYWC-NYY",
        235705605: "KXMLBSERIES-26BOSNYYWC-BOS",
        236000923: "KXMLBSERIESSCORE-26BOSNYYWC-NYY20",
        236000927: "KXMLBSERIESGAMES-26BOSNYYWC-3",
    }
    return markets, tickers


def _labels(markets: list[dict]) -> list[str]:
    return [
        text
        for m in markets
        for text in [m["market_name"], *(o["name"] for o in m["outcomes"])]
    ]


class TestTheSpecimenCard:
    def test_the_bare_yes_names_the_games_it_asks_about(self):
        markets, tickers = _specimen()
        relabel_series_card(markets, tickers)
        assert markets[2]["outcomes"][0]["name"] == "Over 2.5 total games"

    def test_no_label_on_the_card_names_a_club_that_does_not_exist(self):
        markets, tickers = _specimen()
        relabel_series_card(markets, tickers)
        assert not [t for t in _labels(markets) if re.search(r"New York Y(?![a-z])", t)]
        assert markets[0]["outcomes"][0]["name"] == "New York Yankees"
        # The titles carry the truncation with no outcome of their own; every
        # one of them takes the repair the Winner outcome proved.
        assert [m["market_name"] for m in markets] == [
            "Series Winner: Boston vs New York Yankees",
            "Series Exact Score: Boston vs New York Yankees",
            "Series Total Games: Boston vs New York Yankees",
        ]

    def test_correct_labels_and_every_price_are_untouched(self):
        markets, tickers = _specimen()
        before = copy.deepcopy(markets)
        relabel_series_card(markets, tickers)
        assert markets[0]["outcomes"][1]["name"] == "Boston"
        assert markets[1]["outcomes"][0]["name"] == "NYY wins 2-0"
        strip = lambda ms: [  # noqa: E731
            (m["market_id"], [(o["outcome_id"], o["probability"]) for o in m["outcomes"]])
            for m in ms
        ]
        assert strip(markets) == strip(before)

    def test_it_counts_what_it_changed_and_is_idempotent(self):
        markets, tickers = _specimen()
        # 1 rung + 1 outcome club + 3 titles
        assert relabel_series_card(markets, tickers) == 5
        once = copy.deepcopy(markets)
        assert relabel_series_card(markets, tickers) == 0
        assert markets == once


class TestTheRungLabel:
    @pytest.mark.parametrize(
        "ticker, expected",
        [
            ("KXMLBSERIESGAMES-26BOSNYYWC-3", "Over 2.5 total games"),
            ("KXWNBASERIESGAMES-26NYMINR1-3", "Over 2.5 total games"),
            ("KXNBASERIESGAMES-26MINSASR2-7", "Over 6.5 total games"),
            ("KXNHLSERIESGAMES-26VGKANAR2-7", "Over 6.5 total games"),
        ],
    )
    def test_matches_its_siblings_wording(self, ticker, expected):
        assert series_games_rung_label(ticker, "Yes") == expected

    @pytest.mark.parametrize(
        "ticker, name",
        [
            # Already worded — the lower rungs arrive readable.
            ("KXNBASERIESGAMES-26MINSASR2-6", "Over 5.5 total games"),
            # A Yes from any other family has no games count to name.
            ("KXMLBSERIES-26BOSNYYWC-NYY", "Yes"),
            ("KXNFLGAME-26SEP27NYJDET-NYJ", "Yes"),
            # No ticker, no question.
            (None, "Yes"),
            ("", "Yes"),
            # A "No" leg is a different claim; this does not guess it.
            ("KXMLBSERIESGAMES-26BOSNYYWC-3", "No"),
        ],
    )
    def test_ships_unchanged_without_both_signals(self, ticker, name):
        assert series_games_rung_label(ticker, name) is None


class TestRefusals:
    def test_a_card_with_no_tickers_ships_what_the_venue_sent(self):
        markets, _ = _specimen()
        before = copy.deepcopy(markets)
        assert relabel_series_card(markets, {}) == 0
        assert markets == before

    def test_a_name_two_outcomes_expand_differently_is_left_short(self, monkeypatch):
        from app.utils import series_card_labels as mod

        answers = iter(["New York Yankees", "New York Yetis"])
        monkeypatch.setattr(
            mod, "repair_field_outcome_name", lambda t, n: next(answers) if n == "New York Y" else None
        )
        markets = [
            {"market_id": 1, "market_name": "A: Boston vs New York Y",
             "outcomes": [{"outcome_id": 10, "name": "New York Y"}]},
            {"market_id": 2, "market_name": "B: Boston vs New York Y",
             "outcomes": [{"outcome_id": 20, "name": "New York Y"}]},
        ]
        relabel_series_card(markets, {10: "T-NYY", 20: "T-NYY"})
        assert [m["market_name"] for m in markets] == [
            "A: Boston vs New York Y",
            "B: Boston vs New York Y",
        ]


def test_the_related_futures_route_relabels_the_card_it_serves():
    """Call-site guard: the serializer passes every series outcome's ticker,
    after the card is capped and before the response is composed."""
    from app.routes import events as events_route

    src = inspect.getsource(events_route)
    start = src.index("formatted_series: list[dict] = []")
    end = src.index('"series_markets": formatted_series', start)
    block = src[start:end]
    call = block.index("relabel_series_card(")
    assert block.index("formatted_series = formatted_series[:10]") < call
    assert re.search(
        r"relabel_series_card\(\s*formatted_series,\s*\{so\.id: so\.external_id for so in series_outcomes\}",
        block[call:],
    )

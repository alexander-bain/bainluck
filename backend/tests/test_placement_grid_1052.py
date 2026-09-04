"""UX-1052 item 3 — one tournament's placement markets become ONE grid.

THE DEFECT, VERBATIM. Alex, shopping /sports at 1:00pm PT on 2026-09-03:

    "Five near-identical golf cards for one tournament (Omega European Masters:
     Top 5 / Top 10 / Top 20 / Make the Cut / Winner). Group them into a
     beautiful grid. One card per tournament: players down, markets across
     (Winner · Top 5 · Top 10 · Top 20 · Cut), the way the US Open bracket grid
     works. Same for any tournament with ≥3 placement markets."

MEASURED, from ``GET /api/futures/grouped-feed?sports_only=true&limit=60`` on
2026-09-03: five ``type: "market"`` rows, ids 59863411–59863415, all
``source: datagolf``, all named ``"Omega European Masters - <question>"``, each
rendering its own `FuturesCard` listing the same golfers.

THE ARM THAT DECIDES WHETHER THIS SHIPS OR BREAKS THE STRIP is the REFUSAL, not
the grouping. The naming shape being matched — ``"<something> - <something>"`` —
is also the shape of every Polymarket row on that same payload
("AC Milan vs. Sport Lisboa e Benfica - Exact Score", "FC Emmen vs. FC Volendam
- Halftime Result", "… - First Team to Score"). A loose suffix match would
swallow all of them into nonsense grids. So the suffix vocabulary is closed, and
``TestNonPlacementMarketsAreRefused`` feeds it the real names from that payload.
"""

import pytest

from app.utils.market_grouping import (
    PLACEMENT_GRID_MIN_COLUMNS,
    detect_placement_groups,
    parse_placement_market,
)


def _market(mid, name, outcomes, source="datagolf"):
    return {
        "id": mid,
        "name": name,
        "source": source,
        "sport": "golf",
        "outcomes": [
            {"id": mid * 100 + i, "name": n, "probability": p}
            for i, (n, p) in enumerate(outcomes)
        ],
    }


def _omega():
    """The five real markets, with a plausible field."""
    return [
        _market(59863411, "Omega European Masters - Winner",
                [("Angel Ayora", 0.12), ("Eugenio Chacarra", 0.09), ("Marco Penge", 0.06)]),
        _market(59863412, "Omega European Masters - Top 5 Finish",
                [("Angel Ayora", 0.38), ("Eugenio Chacarra", 0.31), ("Marco Penge", 0.24)]),
        _market(59863413, "Omega European Masters - Top 10 Finish",
                [("Angel Ayora", 0.55), ("Eugenio Chacarra", 0.48), ("Marco Penge", 0.4)]),
        _market(59863414, "Omega European Masters - Top 20 Finish",
                [("Angel Ayora", 0.74), ("Eugenio Chacarra", 0.7), ("Marco Penge", 0.62)]),
        _market(59863415, "Omega European Masters - Make the Cut",
                [("Angel Ayora", 0.91), ("Eugenio Chacarra", 0.88), ("Marco Penge", 0.83)]),
    ]


class TestOneTournamentOneGrid:
    def test_five_cards_become_one(self):
        groups = detect_placement_groups(_omega())
        assert list(groups) == ["omega european masters"]

    def test_columns_are_the_markets_in_reading_order(self):
        grid = detect_placement_groups(_omega())["omega european masters"]
        assert [c["key"] for c in grid["columns"]] == [
            "winner", "top_5", "top_10", "top_20", "make_cut",
        ]
        assert [c["label"] for c in grid["columns"]] == [
            "Winner", "Top 5", "Top 10", "Top 20", "Make cut",
        ]

    def test_players_are_the_rows_with_one_cell_per_column(self):
        grid = detect_placement_groups(_omega())["omega european masters"]
        assert [r["name"] for r in grid["rows"]] == [
            "Angel Ayora", "Eugenio Chacarra", "Marco Penge",
        ]
        assert grid["rows"][0]["values"] == {
            "winner": 0.12, "top_5": 0.38, "top_10": 0.55,
            "top_20": 0.74, "make_cut": 0.91,
        }

    def test_every_source_market_is_consumed_so_the_cards_cannot_come_back(self):
        grid = detect_placement_groups(_omega())["omega european masters"]
        assert sorted(grid["market_ids"]) == [
            59863411, 59863412, 59863413, 59863414, 59863415,
        ]

    def test_a_missing_cell_is_None_not_zero_and_not_borrowed(self):
        # A golfer with no Top 5 book has no Top 5 number. Filling it from the
        # adjacent column would be a worse lie than an empty cell.
        markets = _omega()
        markets[1]["outcomes"] = [o for o in markets[1]["outcomes"]
                                  if o["name"] != "Marco Penge"]
        grid = detect_placement_groups(markets)["omega european masters"]
        penge = next(r for r in grid["rows"] if r["name"] == "Marco Penge")
        assert penge["values"]["top_5"] is None
        assert penge["values"]["top_10"] == 0.4

    def test_rows_lead_with_the_favourite(self):
        markets = _omega()
        # Make Penge the outright favourite; he must move to the top.
        markets[0]["outcomes"][2]["probability"] = 0.5
        grid = detect_placement_groups(markets)["omega european masters"]
        assert grid["rows"][0]["name"] == "Marco Penge"

    def test_row_total_states_the_real_field_depth(self):
        grid = detect_placement_groups(_omega())["omega european masters"]
        assert grid["row_total"] == 3


class TestTheThreeColumnFloor:
    def test_two_placement_markets_are_not_a_grid(self):
        # Alex set the bar at three. A two-column grid is a table with one
        # column of names — worse than the two cards it would replace.
        assert PLACEMENT_GRID_MIN_COLUMNS == 3
        assert detect_placement_groups(_omega()[:2]) == {}

    def test_three_placement_markets_are(self):
        assert detect_placement_groups(_omega()[:3])

    def test_a_repeated_question_from_a_second_source_is_not_a_second_column(self):
        markets = _omega()[:3]
        markets.append(
            _market(999, "Omega European Masters - Winner",
                    [("Angel Ayora", 0.13)], source="kalshi"),
        )
        grid = detect_placement_groups(markets)["omega european masters"]
        assert [c["key"] for c in grid["columns"]] == ["winner", "top_5", "top_10"]

    def test_two_tournaments_get_two_grids(self):
        other = [
            _market(70000 + i, f"BMW Championship - {q}", [("Scottie Scheffler", 0.2)])
            for i, q in enumerate(["Winner", "Top 5 Finish", "Top 10 Finish"])
        ]
        groups = detect_placement_groups(_omega() + other)
        assert set(groups) == {"omega european masters", "bmw championship"}


class TestNonPlacementMarketsAreRefused:
    """The control, and the arm that matters most. Every name below is real,
    from the same 2026-09-03 payload, and every one of them has the
    ``"<a> - <b>"`` shape the parser keys on."""

    @pytest.mark.parametrize("name", [
        "AC Milan vs. Sport Lisboa e Benfica - Exact Score",
        "FC Emmen vs. FC Volendam - Halftime Result",
        "Al Diraiyah Saudi Club vs. Abha Saudi Club - First Team to Score",
        "FC Emmen vs. FC Volendam - More Markets",
        "RKC Waalwijk vs. NAC Breda - Exact Score",
        "Iva Jovic vs Magdalena Frech: Set 2 Winner",  # colon, and a SET winner
        "Omega European Masters",                        # no suffix at all
        " - Winner",                                     # no tournament
    ])
    def test_refused(self, name):
        assert parse_placement_market(name) is None, f"{name!r} was taken for a placement market"

    def test_the_whole_soccer_strip_forms_no_grid(self):
        soccer = [
            _market(i, n, [("Yes", 0.5), ("No", 0.5)], source="polymarket")
            for i, n in enumerate([
                "AC Milan vs. Sport Lisboa e Benfica - Exact Score",
                "FC Emmen vs. FC Volendam - Halftime Result",
                "FC Emmen vs. FC Volendam - First Team to Score",
                "RKC Waalwijk vs. NAC Breda - Exact Score",
            ])
        ]
        assert detect_placement_groups(soccer) == {}

    @pytest.mark.parametrize("name,expected", [
        ("Omega European Masters - Winner", ("Omega European Masters", "winner")),
        ("The Open - Top 5 Finish", ("The Open", "top_5")),
        ("The Open - Top 20", ("The Open", "top_20")),
        ("The Open - Make the Cut", ("The Open", "make_cut")),
        ("The Open - Make Cut", ("The Open", "make_cut")),
        ("The Open - Outright Winner", ("The Open", "winner")),
    ])
    def test_accepted(self, name, expected):
        assert parse_placement_market(name) == expected

    def test_an_unlisted_cutoff_is_refused_rather_than_invented(self):
        # "Top 7" is not a column the design has a header for. A grid that
        # grows a column nobody named is how the five cards come back.
        assert parse_placement_market("The Open - Top 7 Finish") is None

    def test_a_grid_with_no_priced_player_is_not_emitted(self):
        markets = [
            _market(1, "Ghost Open - Winner", []),
            _market(2, "Ghost Open - Top 5 Finish", []),
            _market(3, "Ghost Open - Top 10 Finish", []),
        ]
        assert detect_placement_groups(markets) == {}

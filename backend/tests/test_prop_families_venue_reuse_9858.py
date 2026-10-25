"""Recovered venue-identity behavior, with explicit-season consumer contracts.

Retains all eleven original scenarios from the recovered October 24 candidate.
The three mixed-season fixtures now require separate named NBA MVP cards, as
#9858/#11619 require different editions to remain distinct. Original tests and
failed composition evidence remain unchanged in the review packet.

This preserves the recovered representative/lag behavior. Different venue
IDs are a negative boundary; equal IDs or cross-venue membership do not prove
settlement equivalence. Broader rule-backed admission remains #11619 work.
Fixture observations are historical, not a fresh production read.
"""

from datetime import datetime, timedelta, timezone

from app.utils.prop_families import group_prop_families

NOW = datetime.now(timezone.utc)


def _at(days: float) -> str:
    return (NOW + timedelta(days=days)).isoformat()


def _market(market_id, name, source, group_id, status, resolves_in_days, outcomes):
    return {
        "market_id": market_id,
        "name": name,
        "source": source,
        "group_id": group_id,
        "status": status,
        "resolution_date": _at(resolves_in_days),
        "sport": "basketball",
        "outcomes": [
            {
                "outcome_id": market_id * 1000 + i,
                "name": n,
                "probability": p,
                "is_winner": w,
            }
            for i, (n, p, w) in enumerate(outcomes)
        ],
    }


# Kalshi KXNBAMVP-26: the 2025-26 MVP, resolved; stored resolution 2027-04-12
# (+170 days at observation) although it was decided in spring 2026.
MVP_2026 = _market(
    411,
    "MVP Winner",
    "kalshi",
    "kalshi:KXNBAMVP-26",
    "resolved",
    170,
    [
        ("Shai Gilgeous-Alexander", 0.995, True),
        ("Chet Holmgren", 0.0, False),
        ("Jalen Williams", 0.0, False),
        ("Alex Caruso", 0.0, False),
        ("Isaiah Hartenstein", 0.0, False),
    ],
)
# Kalshi KXNBAMVP-27: this season's MVP, open.
MVP_2027_KALSHI = _market(
    52755650,
    "Pro Basketball MVP Winner",
    "kalshi",
    "kalshi:KXNBAMVP-27",
    "open",
    280,
    [
        ("Shai Gilgeous-Alexander", 0.145, False),
        ("Chet Holmgren", 0.01, False),
        ("Jalen Williams", 0.01, False),
    ],
)
# Polymarket event 1196500, "NBA: 2026-27 MVP": the same open market.
MVP_2027_POLY = _market(
    66031970,
    "NBA: 2026-27 MVP",
    "polymarket",
    "polymarket:1196500",
    "open",
    250,
    [("Shai Gilgeous-Alexander", 0.1398, None)],
)

# Kalshi KXNBAWFINMVP-27: this season's Western Conference Finals MVP, open.
WFINMVP_2027 = _market(
    60629713,
    "Pro Basketball Western Conference Finals MVP Winner",
    "kalshi",
    "kalshi:KXNBAWFINMVP-27",
    "open",
    287,
    [("Shai Gilgeous-Alexander", 0.325, None), ("Victor Wembanyama", 0.325, None)],
)
# Kalshi KXNBAFINMVP-26 and KXNBAWFINMVP-26: last season, resolved, padded dates.
FINMVP_2026 = _market(
    413,
    "Finals MVP Winner",
    "kalshi",
    "kalshi:KXNBAFINMVP-26",
    "resolved",
    170,
    [
        ("Jalen Brunson", 0.99, True),
        ("Shai Gilgeous-Alexander", 0.0, False),
        ("Jalen Williams", 0.0, False),
    ],
)
WFINMVP_2026 = _market(
    408,
    "Western Conference Finals MVP Winner",
    "kalshi",
    "kalshi:KXNBAWFINMVP-26",
    "resolved",
    170,
    [
        ("Victor Wembanyama", 0.99, True),
        ("Shai Gilgeous-Alexander", 0.0, False),
        ("Jalen Williams", 0.0, False),
    ],
)


def _rows(families, entity):
    return [
        (f["family_key"], r)
        for f in families
        for r in f["rows"]
        if r["entity"] == entity
    ]


def _family(families, key):
    found = [f for f in families if f["family_key"] == key]
    assert len(found) == 1, [f["family_key"] for f in families]
    return found[0]


# One player priced by Kalshi and by two different Polymarket events.
ORDER_KALSHI = _market(
    10,
    "Pro Basketball MVP Winner",
    "kalshi",
    "kalshi:KXNBAMVP-27",
    "open",
    280,
    [("Shai Gilgeous-Alexander", 0.145, None), ("Nikola Jokic", 0.12, None)],
)
ORDER_POLY_A = _market(
    11,
    "NBA: 2026-27 MVP",
    "polymarket",
    "polymarket:111",
    "open",
    250,
    [("Shai Gilgeous-Alexander", 0.14, None)],
)
ORDER_POLY_B = _market(
    12,
    "NBA MVP 2026-27",
    "polymarket",
    "polymarket:222",
    "open",
    250,
    [("Shai Gilgeous-Alexander", 0.16, None)],
)


def _order_card(markets):
    mvp = _family(group_prop_families(list(markets)), "mvp")
    return sorted(
        (
            r["entity"],
            r["probability"],
            r["status"],
            tuple(sorted(r["sources"])),
            tuple(sorted(r.get("merged_market_ids") or [r["market_id"]])),
        )
        for r in mvp["rows"]
    )


# --------------------------------------------------------------------------
# Must FAIL at 9cf993fa, PASS after.
# --------------------------------------------------------------------------


def test_an_open_mvp_race_is_not_answered_by_last_seasons_award():
    families = group_prop_families([MVP_2026, MVP_2027_KALSHI, MVP_2027_POLY])
    mvp = _family(families, "mvp:season:2026-2027")
    [sga] = [r for r in mvp["rows"] if r["entity"] == "Shai Gilgeous-Alexander"]
    assert sga["settled"] is False
    assert sga["result"] is None
    assert sga["status"] == "open"
    assert sga["probability"] == 0.145
    assert sorted(sga["merged_market_ids"]) == [52755650, 66031970]


def test_last_seasons_board_does_not_sit_in_this_seasons_race():
    families = group_prop_families([MVP_2026, MVP_2027_KALSHI, MVP_2027_POLY])
    mvp = _family(families, "mvp:season:2026-2027")
    assert all(not r["settled"] for r in mvp["rows"]), mvp["rows"]
    assert {r["market_id"] for r in mvp["rows"]} <= {52755650, 66031970}
    # Caruso and Hartenstein appear only on the 2025-26 board.
    assert {r["entity"] for r in mvp["rows"]} == {
        "Shai Gilgeous-Alexander",
        "Chet Holmgren",
        "Jalen Williams",
    }


def test_an_open_conference_finals_race_is_not_answered_by_a_different_award():
    families = group_prop_families([WFINMVP_2027, FINMVP_2026, WFINMVP_2026])
    rows = _rows(families, "Shai Gilgeous-Alexander")
    open_rows = [r for _k, r in rows if not r["settled"]]
    assert len(open_rows) == 1, rows
    assert open_rows[0]["market_id"] == 60629713
    assert open_rows[0]["probability"] == 0.325
    for _key, r in rows:
        assert 60629713 not in (r.get("merged_market_ids") or []) or not r["settled"]


def test_a_season_ladder_line_is_not_answered_by_last_seasons_ladder():
    """The same line on two markets of ONE venue: last season's and this season's.

    `_one_rung_per_entity` merges one line across venues before anything else.
    A 2025-26 ladder stored with a future `resolution_date` used to fold into
    this season's open 874.5 line and print last season's "won".
    """
    old = _market(
        50,
        "Will Travis Kelce have 874.5+ receiving yards in the 2025-26 NFL regular season?",
        "polymarket",
        "polymarket:700",
        "resolved",
        30,
        [("Yes", 1.0, True), ("No", 0.0, False)],
    )
    new = _market(
        51,
        "Will Travis Kelce have 874.5+ receiving yards in the 2026-27 NFL regular season?",
        "polymarket",
        "polymarket:701",
        "open",
        200,
        [("Yes", 0.40, None), ("No", 0.60, None)],
    )
    other = _market(
        52,
        "Will Xavier Worthy have 700+ receiving yards in the 2026-27 NFL regular season?",
        "polymarket",
        "polymarket:701",
        "open",
        200,
        [("Yes", 0.45, None), ("No", 0.55, None)],
    )
    for m in (old, new, other):
        m["sport"] = "football"
    families = group_prop_families([old, new, other])
    [kelce] = [r for _k, r in _rows(families, "Travis Kelce")]
    assert kelce["settled"] is False
    assert kelce["probability"] == 0.40


def test_each_venue_speaks_for_a_player_with_one_market():
    """Two Polymarket events are two markets by the venue's word: never one row."""
    [sga] = [
        row
        for row in _order_card([ORDER_KALSHI, ORDER_POLY_A, ORDER_POLY_B])
        if row[0] == "Shai Gilgeous-Alexander"
    ]
    assert "kalshi" in sga[3]
    assert len([m for m in sga[4] if m in (11, 12)]) == 1


# --------------------------------------------------------------------------
# Controls: PASS before and after.
# --------------------------------------------------------------------------


def test_control_a_venue_that_graded_first_still_settles_the_same_market():
    """Cross-venue lag: Polymarket graded the 2026-27 market, Kalshi still trades it.

    Same market, two venues, so the settled ruling still wins (the merge's
    real case, `find_cross_source_markets` convention).
    """
    poly_graded = _market(
        66031970,
        "NBA: 2026-27 MVP",
        "polymarket",
        "polymarket:1196500",
        "resolved",
        -2,
        [("Shai Gilgeous-Alexander", 1.0, True), ("Chet Holmgren", 0.0, False)],
    )
    families = group_prop_families([poly_graded, MVP_2027_KALSHI])
    mvp = _family(families, "mvp")
    [sga] = [r for r in mvp["rows"] if r["entity"] == "Shai Gilgeous-Alexander"]
    assert sga["settled"] is True and sga["result"] == "won"
    assert sorted(sga["merged_market_ids"]) == [52755650, 66031970]


def test_control_one_venue_one_board_is_untouched():
    families = group_prop_families([MVP_2027_KALSHI])
    # A single market is a family only with two entities; values unchanged.
    mvp = _family(families, "mvp")
    by_entity = {r["entity"]: r for r in mvp["rows"]}
    assert by_entity["Shai Gilgeous-Alexander"]["probability"] == 0.145
    assert "merged_market_ids" not in by_entity["Shai Gilgeous-Alexander"]


# --------------------------------------------------------------------------
# Review regressions: baseline behaviour the patch must keep (PASS before and
# after). Found by an independent review of the first draft of this patch.
# --------------------------------------------------------------------------


def test_players_in_a_per_player_series_are_not_editions_of_each_other():
    """Kalshi lists one Next Team event per player, with a year token in front."""
    hendrickson = _market(
        1,
        "Trey Hendrickson Next Team",
        "kalshi",
        "kalshi:KXNEXTTEAMNFL-26THENDRICKSON",
        "open",
        40,
        [("Cincinnati", 0.55, None), ("New York J", 0.20, None)],
    )
    chase = _market(
        2,
        "Ja'Marr Chase Next Team",
        "kalshi",
        "kalshi:KXNEXTTEAMNFL-26JCHASE",
        "open",
        400,
        [("Cincinnati", 0.85, None), ("Dallas", 0.05, None)],
    )
    burrow = _market(
        3,
        "Joe Burrow Next Team",
        "kalshi",
        "kalshi:KXNEXTTEAMNFL-27JBURROW",
        "open",
        500,
        [("Cincinnati", 0.92, None)],
    )
    for m in (hendrickson, chase, burrow):
        m["sport"] = "football"
    families = group_prop_families([hendrickson, chase, burrow])
    [card] = [f for f in families if f["family_key"] == "next team"]
    assert {r["entity"] for r in card["rows"]} == {
        "Trey Hendrickson",
        "Ja'Marr Chase",
        "Joe Burrow",
    }


def test_an_earlier_edition_still_being_traded_keeps_its_players():
    """KXNBAMVP-26 still open when KXNBAMVP-27 lists: a live race is not a past result."""
    open26 = _market(
        20,
        "Pro Basketball MVP Winner",
        "kalshi",
        "kalshi:KXNBAMVP-26",
        "open",
        20,
        [
            ("Shai Gilgeous-Alexander", 0.80, None),
            ("Nikola Jokic", 0.15, None),
            ("Cade Cunningham", 0.03, None),
        ],
    )
    open27 = _market(
        21,
        "Pro Basketball MVP Winner",
        "kalshi",
        "kalshi:KXNBAMVP-27",
        "open",
        380,
        [("Shai Gilgeous-Alexander", 0.22, None), ("Victor Wembanyama", 0.18, None)],
    )
    families = group_prop_families([open26, open27])
    earlier = _family(families, "mvp:season:2025-2026")
    later = _family(families, "mvp:season:2026-2027")
    assert {r["entity"] for r in earlier["rows"]} == {
        "Shai Gilgeous-Alexander",
        "Nikola Jokic",
        "Cade Cunningham",
    }
    assert {r["entity"] for r in later["rows"]} == {
        "Shai Gilgeous-Alexander",
        "Victor Wembanyama",
    }
    assert {r["market_id"] for r in earlier["rows"]} == {20}
    assert {r["market_id"] for r in later["rows"]} == {21}
    assert (
        next(r for r in earlier["rows"] if r["entity"] == "Shai Gilgeous-Alexander")[
            "probability"
        ]
        == 0.80
    )
    assert (
        next(r for r in later["rows"] if r["entity"] == "Shai Gilgeous-Alexander")[
            "probability"
        ]
        == 0.22
    )
    assert all(not r["settled"] for f in families for r in f["rows"])


def test_the_card_does_not_depend_on_the_order_rows_arrive_in():
    """One player priced by Kalshi and by two Polymarket events: one answer, every order."""
    from itertools import permutations

    answers = {
        tuple(_order_card(p))
        for p in permutations([ORDER_KALSHI, ORDER_POLY_A, ORDER_POLY_B])
    }
    assert len(answers) == 1, answers
    [sga] = [row for row in answers.pop() if row[0] == "Shai Gilgeous-Alexander"]
    assert "kalshi" in sga[3]


def test_a_tie_between_two_markets_of_one_venue_breaks_the_same_way_every_time():
    """Served Hawks shape: Jalen Johnson at 1% on two finished Kalshi awards."""
    from itertools import permutations

    finals = _market(
        413,
        "Finals MVP Winner",
        "kalshi",
        "kalshi:KXNBAFINMVP-26",
        "resolved",
        170,
        [("Jalen Johnson", 0.01, False), ("CJ McCollum", 0.01, False)],
    )
    east = _market(
        414,
        "Eastern Conference Finals MVP Winner",
        "kalshi",
        "kalshi:KXNBAEFINMVP-26",
        "resolved",
        170,
        [("Jalen Johnson", 0.01, False)],
    )

    def card(markets):
        families = group_prop_families(list(markets))
        return sorted(
            (
                r["entity"],
                r["probability"],
                tuple(sorted(r.get("merged_market_ids") or [r["market_id"]])),
            )
            for f in families
            for r in f["rows"]
        )

    assert len({tuple(card(p)) for p in permutations([finals, east])}) == 1

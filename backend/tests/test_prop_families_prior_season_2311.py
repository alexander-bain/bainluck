"""#2311 after-check — a team page's prop race never shows last season's result as this season's.

Once the Chiefs page searched Mahomes' name (#2311), Polymarket's 2024-season
"NFL MVP" (34617731, resolved 2025-02-09, every outcome stored at 1.0) joined
the MVP family beside the open 2026 markets, and the merge's "a settled ruling
wins" printed "Patrick Mahomes OUT 100%" where 8.5% had been. Last season's
Comeback Player market (34617278, resolved 2026-02-07) likewise put
"Rashee Rice OUT" into this season's race. Specimens below are those rows,
trimmed; dates are offsets from now (offset first, never branched on).
"""

from datetime import datetime, timedelta, timezone

from app.utils import prop_families as pf
from app.utils.prop_families import group_prop_families

NOW = datetime.now(timezone.utc)


def _at(days: float) -> str:
    return (NOW + timedelta(days=days)).isoformat()


def _market(market_id, name, source, status, resolves_in_days, outcomes, group_id=None):
    return {
        "market_id": market_id,
        "name": name,
        "source": source,
        "group_id": group_id or f"{source}:{market_id}",
        "status": status,
        "resolution_date": None if resolves_in_days is None else _at(resolves_in_days),
        "sport": "football",
        "outcomes": [
            {"outcome_id": market_id * 100 + i, "name": n, "probability": p, "is_winner": w}
            for i, (n, p, w) in enumerate(outcomes)
        ],
    }


def _mvp_markets():
    return [
        # Kalshi KXNFLMVP-27: open, stored resolution 2028-02-12 (#2644 padding).
        _market(40532, "MVP Winner?", "kalshi", "open", 506,
                [("Josh Allen", 0.25, False), ("Patrick Mahomes", 0.085, False)],
                group_id="kalshi:KXNFLMVP-27"),
        # Polymarket 315364: the SAME open question, stored resolution 2027-03-01.
        _market(7585490, "Pro Football: 2026 MVP Winner", "polymarket", "open", 158,
                [("Josh Allen", 0.25, False), ("Patrick Mahomes", 0.086, False)],
                group_id="polymarket:315364"),
        # Polymarket 12297: the 2024 season, resolved 592 days before the after-check.
        _market(34617731, "NFL MVP", "polymarket", "resolved", -592,
                [("Josh Allen", 1.0, True), ("Patrick Mahomes", 1.0, False)],
                group_id="polymarket:12297"),
    ]


def _family(families, key):
    [fam] = [f for f in families if f["family_key"] == key]
    return fam


def _row(fam, entity):
    rows = [r for r in fam["rows"] if r["entity"] == entity]
    assert len(rows) == 1, [r["entity"] for r in fam["rows"]]
    return rows[0]


def test_the_chiefs_mvp_card_shows_this_seasons_price_not_a_graded_2024_row():
    mahomes = _row(_family(group_prop_families(_mvp_markets()), "mvp"), "Patrick Mahomes")
    assert mahomes["settled"] is False
    assert mahomes["result"] is None
    assert mahomes["probability"] == 0.086
    assert 34617731 not in mahomes.get("merged_market_ids", [])


def test_last_seasons_comeback_loser_is_not_in_this_seasons_race():
    markets = [
        _market(15203993, "Comeback Player of the Year Winner?", "kalshi", "open", 180,
                [("Patrick Mahomes", 0.64, False), ("Joe Burrow", 0.085, False)],
                group_id="kalshi:KXNFLCPOTY-27"),
        _market(34617278, "NFL Comeback Player of the Year ", "polymarket", "resolved", -229,
                [("Christian McCaffrey", 1.0, True), ("Rashee Rice", 0.001, False)],
                group_id="polymarket:23938"),
    ]
    fam = _family(group_prop_families(markets), "comeback player of the year")
    assert {r["entity"] for r in fam["rows"]} == {"Patrick Mahomes", "Joe Burrow"}
    assert not any(r["settled"] for r in fam["rows"])


def test_a_recent_grading_still_wins_over_a_lagging_venue():
    # The merge's real case: one question, one venue graded it days ago, the
    # other still reads open with a padded future date. Settled means settled.
    markets = [
        _market(1, "MVP Winner?", "kalshi", "open", 300,
                [("Josh Allen", 0.97, False), ("Lamar Jackson", 0.02, False)]),
        _market(2, "NFL MVP", "polymarket", "resolved", -10,
                [("Josh Allen", 1.0, True), ("Lamar Jackson", 0.0, False)]),
    ]
    allen = _row(_family(group_prop_families(markets), "mvp"), "Josh Allen")
    assert allen["settled"] is True and allen["result"] == "won"
    assert allen["probability"] == 1.0


def test_an_all_settled_family_is_a_results_card_and_is_kept():
    markets = [m for m in _mvp_markets() if m["status"] == "resolved"]
    fam = _family(group_prop_families(markets), "mvp")
    assert _row(fam, "Josh Allen")["result"] == "won"
    assert _row(fam, "Patrick Mahomes")["settled"] is True


def test_a_settled_row_with_no_resolution_date_cannot_be_aged_and_is_kept():
    markets = [m for m in _mvp_markets() if m["status"] == "open"]
    markets.append(_market(3, "NFL MVP", "polymarket", "resolved", None,
                           [("Joe Burrow", 0.0, False), ("Josh Allen", 1.0, True)]))
    fam = _family(group_prop_families(markets), "mvp")
    assert _row(fam, "Joe Burrow")["settled"] is True


def test_the_boundary_is_the_named_constant():
    edge = pf.PRIOR_RESULT_MAX_AGE_DAYS
    live = _market(1, "MVP Winner?", "kalshi", "open", 300,
                   [("Josh Allen", 0.2, False), ("Lamar Jackson", 0.1, False)])

    def burrow_kept(age_days):
        old = _market(2, "NFL MVP", "polymarket", "resolved", -age_days,
                      [("Joe Burrow", 0.0, False)])
        fam = _family(group_prop_families([live, old]), "mvp")
        return any(r["entity"] == "Joe Burrow" for r in fam["rows"])

    assert burrow_kept(edge - 1)
    assert not burrow_kept(edge + 1)


def test_the_internal_resolution_stamp_never_reaches_the_payload():
    for fam in group_prop_families(_mvp_markets()):
        for row in fam["rows"]:
            assert "_resolves_at" not in row

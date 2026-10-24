"""#11568 — a team page's Prop Races never builds a race out of finished past-season boards.

Shopper, 2026-10-24 00:37Z, production v5902: the Seahawks page printed
"Comeback Player Of The Year · 3 IN THE MIX: Sam Darnold OUT 100% · Rashid
Shaheed OUT <1% · Cooper Kupp OUT <1%". No current-season board was in the card.
Two resolved Polymarket boards made it on their own:

* 34617286 "NFL Comeback Player of the Year" — the 2024-25 award, resolved
  2025-02-06, EVERY leg stored at 1.000 (losers included).
* 34617278 "NFL Comeback Player of the Year " — the 2025-26 award, resolved
  2026-02-07.

#2311's age cut only ran when the family still had a live row, so an all-settled
family of year-old boards was kept as a "results card". Dates below are offsets
from now (offset first, never branched on — gotcha #44).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.routes import prop_families as route
from app.utils import prop_families as pf
from app.utils.prop_families import group_prop_families

NOW = datetime.now(timezone.utc)
SEAHAWKS = 28


def _market(market_id, name, status, resolves_in_days, outcomes, group_id):
    return {
        "market_id": market_id,
        "name": name,
        "source": "polymarket",
        "group_id": group_id,
        "status": status,
        "resolution_date": (NOW + timedelta(days=resolves_in_days)).isoformat(),
        "sport": "football",
        "outcomes": [
            {"outcome_id": market_id * 100 + i, "name": n, "probability": p, "is_winner": w}
            for i, (n, p, w) in enumerate(outcomes)
        ],
    }


def _seahawks_cpoy_boards():
    return [
        # 2024-25, resolved 2025-02-06 (~624 days before the shopper's look).
        _market(34617286, "NFL Comeback Player of the Year", "resolved", -624,
                [("Sam Darnold", 1.0, False), ("Joe Burrow", 1.0, True)],
                "polymarket:15168"),
        # 2025-26, resolved 2026-02-07 (~258 days before).
        _market(34617278, "NFL Comeback Player of the Year ", "resolved", -258,
                [("Rashid Shaheed", 0.003, False), ("Cooper Kupp", 0.001, False),
                 ("Christian McCaffrey", 1.0, True)],
                "polymarket:23938"),
    ]


def _cpoy(families):
    return [f for f in families if f["family_key"] == "comeback player of the year"]


def test_two_finished_past_season_boards_do_not_form_a_race():
    assert _cpoy(group_prop_families(_seahawks_cpoy_boards())) == []


def test_the_avalanche_olympic_mvp_result_ages_off_the_page():
    # Shopper's NHL sibling on #11534 (19:17Z 10/23): Kalshi 110951 "Winter
    # Olympics Men's Hockey MVP", resolved 2026-02-23, every row OUT, headed the
    # Avalanche's Prop Races eight months after the tournament.
    board = _market(110951, "Winter Olympics Men's Hockey MVP", "resolved", -243,
                    [("Cale Makar", 0.02, False), ("Nathan MacKinnon", 0.01, False)],
                    "kalshi:KXWOMHOCKEYMVP-26")
    board["source"] = "kalshi"
    board["sport"] = "hockey"
    assert not [f for f in group_prop_families([board]) if "olympics" in f["family_key"]]


def test_a_results_card_lives_exactly_as_long_as_the_named_constant():
    edge = pf.PRIOR_RESULT_MAX_AGE_DAYS

    def card(age_days):
        board = _market(1, "NFL Comeback Player of the Year", "resolved", -age_days,
                        [("Sam Darnold", 0.0, False), ("Joe Burrow", 1.0, True)],
                        "polymarket:1")
        return _cpoy(group_prop_families([board]))

    assert card(edge - 1), "a recent results card must stay"
    assert card(edge + 1) == []


def test_a_settled_loser_never_prints_a_winning_price():
    # A RECENT board with the same 1.000-on-every-leg storage as 34617286.
    board = _market(2, "NFL Comeback Player of the Year", "resolved", -5,
                    [("Sam Darnold", 1.0, False), ("Joe Burrow", 1.0, True)],
                    "polymarket:2")
    [fam] = _cpoy(group_prop_families([board]))
    rows = {r["entity"]: r for r in fam["rows"]}
    darnold = rows["Sam Darnold"]
    assert darnold["result"] == "lost"
    assert darnold["probability"] is None
    assert darnold["cross_source"] == {"polymarket": None}
    assert rows["Joe Burrow"]["probability"] == 1.0


def test_a_settled_winner_never_prints_a_losing_price():
    board = _market(3, "NFL Comeback Player of the Year", "resolved", -5,
                    [("Sam Darnold", 0.0, False), ("Joe Burrow", 0.2, True)],
                    "polymarket:3")
    [fam] = _cpoy(group_prop_families([board]))
    rows = {r["entity"]: r for r in fam["rows"]}
    assert rows["Joe Burrow"]["result"] == "won"
    assert rows["Joe Burrow"]["probability"] is None
    assert rows["Sam Darnold"]["probability"] == 0.0


def test_a_live_row_keeps_its_price():
    board = _market(4, "Comeback Player of the Year Winner?", "open", 120,
                    [("Sam Darnold", 0.9, False), ("Joe Burrow", 0.05, False)],
                    "polymarket:4")
    [fam] = _cpoy(group_prop_families([board]))
    assert {r["entity"]: r["probability"] for r in fam["rows"]} == {
        "Sam Darnold": 0.9, "Joe Burrow": 0.05,
    }


def test_a_v2_mirror_written_before_this_rule_is_a_miss():
    """The 24h mirror outlives the 15-minute primary (#11534's lesson), so the
    narrowing ships with a new prefix and a v2 copy of the past-season race is
    never read again."""
    from app.utils.event_concept_cache import stamp_envelope, write_payload

    store: dict[str, bytes] = {}
    rc = MagicMock()
    rc.get.side_effect = lambda k: store.get(k)
    rc.setex.side_effect = lambda k, _ttl, v: store.__setitem__(k, v)
    rc.set.side_effect = lambda k, v, **_kw: store.__setitem__(k, v) or True

    old = route.cache_keys(f"{SEAHAWKS}:400", prefix="bainluck:prop_families:v2:")
    legacy = stamp_envelope(
        {"team": {"id": SEAHAWKS}, "families": [{"label": "Comeback Player Of The Year",
         "rows": [{"market_id": 34617286}]}], "total_families": 1},
        created_at=NOW, lifecycle_watermark=None, quality="full", quality_reasons=[],
    )
    write_payload(rc, old, legacy, primary_ttl=900)
    assert store.get(old.stale) is not None

    keys = route.prop_families_cache_keys(SEAHAWKS, 400)
    for key in (keys.primary, keys.stale, keys.negative, keys.refresh_lock):
        assert not key.startswith("bainluck:prop_families:v2:"), key
    assert route.read_slot(rc, keys.primary) is None
    assert route.read_slot(rc, keys.stale) is None

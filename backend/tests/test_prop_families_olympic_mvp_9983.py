"""#9983 — the Leafs page: an Olympic tournament MVP is not the NHL MVP race.

Leafs page, production 02:10Z 10/1 (390px, lane1b in passing):

* A prop-race card headed "MVP" listed Auston Matthews OUT 2% and William
  Nylander OUT 1% — Kalshi 110951 "Winter Olympics Men's Hockey MVP"
  (``kalshi:KXWOMHOCKEYMVP-26``), resolved 2026-02-23. The title fell through
  to the bare "mvp" keyword, so the card read as the current NHL award while
  Season Futures further down had Matthews alive at 8% for the Hart Trophy.

The grades are right for the Olympics; the defect is the family. Specimens are
the served rows, trimmed; the active NHL market is the same-player control.
"""

from app.utils.prop_families import _family_label, group_prop_families, resolve_family_key

OLYMPIC_ID = 110951
OLYMPIC_KEY = "2026 winter olympics men's mvp"


def _market(market_id, name, status, outcomes, group_id, resolution_date, **extra):
    return {
        "market_id": market_id,
        "name": name,
        "source": "kalshi",
        "group_id": group_id,
        "status": status,
        "resolution_date": resolution_date,
        "sport": "hockey",
        "outcomes": [
            {"outcome_id": market_id * 100 + i, "name": n, "probability": p, "is_winner": w}
            for i, (n, p, w) in enumerate(outcomes)
        ],
        **extra,
    }


def _olympic(**extra):
    return _market(
        OLYMPIC_ID, "Winter Olympics Men's Hockey MVP", "resolved",
        [("Auston Matthews", 0.02, False), ("William Nylander", 0.005, False)],
        "kalshi:KXWOMHOCKEYMVP-26", "2026-02-23T00:00:00+00:00", **extra,
    )


def _nhl_mvp():
    return _market(
        63300001, "Pro Hockey MVP", "open",
        [("Connor McDavid", 0.30, None), ("Auston Matthews", 0.08, None)],
        "kalshi:KXNHLMVP-27", "2027-06-20T00:00:00+00:00",
    )


def _families(markets):
    return {f["family_key"]: f for f in group_prop_families(markets)}


def test_the_olympic_result_is_not_captioned_as_the_mvp_race():
    # The production BEFORE: the Olympic market alone on the Leafs page.
    fams = _families([_olympic()])
    assert "mvp" not in fams, fams.keys()
    assert fams[OLYMPIC_KEY]["label"] == "2026 Winter Olympics Men's MVP"


def test_the_olympic_result_stays_readable_with_its_grades_and_source():
    fam = _families([_olympic(), _nhl_mvp()])[OLYMPIC_KEY]
    rows = {r["entity"]: r for r in fam["rows"]}
    assert set(rows) == {"Auston Matthews", "William Nylander"}
    for r in rows.values():
        assert r["market_id"] == OLYMPIC_ID
        assert r["group_id"] == "kalshi:KXWOMHOCKEYMVP-26"
        assert r["source"] == "kalshi" and r["sources"] == ["kalshi"]
        assert r["settled"] is True and r["result"] == "lost"
    assert rows["Auston Matthews"]["probability"] == 0.02
    assert rows["William Nylander"]["probability"] == 0.005


def test_the_live_nhl_race_keeps_matthews_alive_and_holds_no_olympic_row():
    fam = _families([_olympic(), _nhl_mvp()])["mvp"]
    assert fam["label"] == "MVP"
    assert all(r["market_id"] != OLYMPIC_ID for r in fam["rows"]), fam["rows"]
    matthews = next(r for r in fam["rows"] if r["entity"] == "Auston Matthews")
    assert matthews["probability"] == 0.08
    assert matthews["settled"] is False and matthews["result"] is None
    assert matthews["status"] == "open"


def test_a_cached_hint_cannot_file_the_olympic_result_into_the_season_award():
    for md in (
        {"market_metadata": {"prop_family": {"family_key": "mvp"}}},
        {"market_metadata": {"prop_family": {"family_key": "winter olympics mvp"}}},
        {"market_metadata": {"prop_family": {"family_key": "2026 Winter Olympics Men's MVP"}}},
        {"family_key_hint": "MVP"},
    ):
        assert resolve_family_key(_olympic(**md)) == OLYMPIC_KEY, md
        fams = _families([_olympic(**md), _nhl_mvp()])
        assert all(r["market_id"] != OLYMPIC_ID for r in fams["mvp"]["rows"]), md
        assert {r["market_id"] for r in fams[OLYMPIC_KEY]["rows"]} == {OLYMPIC_ID}, md


def test_a_hint_naming_the_olympics_qualifies_a_title_that_does_not():
    m = _market(1, "Hockey MVP", "resolved", [("A", 0.5, True)], "g", "2026-02-23T00:00:00Z",
                market_metadata={"prop_family": {"family_key": "winter olympics mvp"}})
    assert resolve_family_key(m) == "2026 winter olympics mvp"


def test_the_edition_is_named_by_the_title_first_then_the_resolution_year():
    m = _market(2, "2030 Winter Olympics Men's Hockey MVP", "open", [("A", 0.5, None)],
                "g", "2030-03-01T00:00:00Z")
    assert resolve_family_key(m) == "2030 winter olympics men's mvp"
    # No year anywhere ⇒ no edition, never a guessed one.
    m = _market(3, "Winter Olympics Men's Hockey MVP", "open", [("A", 0.5, None)], "g", None)
    assert resolve_family_key(m) == "winter olympics men's mvp"


def test_two_editions_and_two_draws_are_separate_cards():
    keys = {
        resolve_family_key(_market(4, t, "resolved", [("A", 0.5, True)], "g", d))
        for t, d in (
            ("Winter Olympics Men's Hockey MVP", "2026-02-23T00:00:00Z"),
            ("Winter Olympics Women's Hockey MVP", "2026-02-20T00:00:00Z"),
            ("Winter Olympics Men's Hockey MVP", "2022-02-20T00:00:00Z"),
        )
    }
    assert keys == {
        "2026 winter olympics men's mvp",
        "2026 winter olympics women's mvp",
        "2022 winter olympics men's mvp",
    }


def test_markets_naming_no_olympics_keep_their_keys_and_labels():
    # Controls: season award, one-night awards, series MVPs, a prior season,
    # and a hint on a non-Olympic market are byte-for-byte what they were.
    for title, key in (
        ("Pro Hockey MVP", "mvp"),
        ("AL MVP Winner", "mvp"),
        ("Will Patrick Mahomes win the 2024 NFL MVP?", "mvp"),
        ("All-Star Game MVP Winner", "all-star game mvp"),
        ("Pro Baseball Championship Series MVP Winner", "championship game mvp"),
        ("World Series MVP", "championship game mvp"),
        ("NBA Finals MVP", "finals mvp"),
        ("Rookie of the Year", "rookie of the year"),
    ):
        m = _market(5, title, "open", [("A", 0.5, None)], "g", "2024-02-11T00:00:00Z")
        assert resolve_family_key(m) == key, title
    hinted = _market(6, "Some Award", "open", [("A", 0.5, None)], "g", None,
                     market_metadata={"prop_family": {"family_key": "mvp"}})
    assert resolve_family_key(hinted) == "mvp"
    assert _family_label("mvp", "hockey") == "MVP"

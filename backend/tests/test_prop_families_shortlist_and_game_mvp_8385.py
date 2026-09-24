"""#8385 / #8386 / #7162 — a team page's award card is the WINNER race of the SEASON award, once.

Chiefs page, production 2026-09-24 (prod v5009):

* #8385 — "Offensive Player Of The Year: Patrick Mahomes 29%". The 29% was
  Kalshi's "Offensive Player of the Year Finalists" (59164987,
  KXNFLAWARDFIN-27OPOY); the winner market (53662, KXNFLOPOTY-27) says 1%. The
  finalist title keyed to the OPOY family and the merge took the higher price.
  The card above it, "Ap Offensive Player Of The Year" (Polymarket 56933331),
  was the same award again, split off by the "AP" in Polymarket's title.
* #8386 — the "MVP" card carried "Will Kenneth Walker III win the Pro ..." as a
  player: Kalshi's Super Bowl MVP ("Pro Football Championship MVP?", 479,
  KXNFLSBMVP-26) keyed to season "mvp" on the bare keyword, and its candidate
  is written as the whole question.

Specimens are those rows, trimmed.
"""

from app.utils.prop_families import _parse, extract_entity, group_prop_families


def _market(market_id, name, source, outcomes, group_id):
    return {
        "market_id": market_id,
        "name": name,
        "source": source,
        "group_id": group_id,
        "status": "open",
        "resolution_date": "2027-02-10T00:00:00+00:00",
        "sport": "football",
        "outcomes": [
            {"outcome_id": market_id * 100 + i, "name": n, "probability": p, "is_winner": False}
            for i, (n, p) in enumerate(outcomes)
        ],
    }


def _chiefs_opoy():
    return [
        _market(56933331, "Pro Football: 2026-27 AP Offensive Player of the Year Winner",
                "polymarket",
                [("Kenneth Walker III", 0.076), ("Patrick Mahomes", 0.003), ("Rashee Rice", 0.003)],
                "polymarket:741440"),
        _market(53662, "Offensive Player of the Year Winner?", "kalshi",
                [("Patrick Mahomes", 0.01), ("Rashee Rice", 0.015)], "kalshi:KXNFLOPOTY-27"),
        _market(59164987, "Offensive Player of the Year Finalists", "kalshi",
                [("Patrick Mahomes", 0.29), ("Rashee Rice", None)],
                "kalshi:KXNFLAWARDFIN-27OPOY"),
    ]


def _chiefs_mvp():
    return [
        _market(7585490, "Pro Football: 2026 MVP Winner", "polymarket",
                [("Josh Allen", 0.25), ("Patrick Mahomes", 0.0875)], "polymarket:315364"),
        _market(479, "Pro Football Championship MVP?", "kalshi",
                [("Will Kenneth Walker III win the Pro Football Championship Game MVP?", 0.085)],
                "kalshi:KXNFLSBMVP-26"),
    ]


def _families(markets):
    return {f["family_key"]: f for f in group_prop_families(markets)}


def _entities(fam):
    return {r["entity"]: r for r in fam["rows"]}


# --- #8385: finalists are not the winner race ----------------------------------------


def test_the_chiefs_opoy_card_prints_mahomes_at_the_winner_price_not_the_finalist_price():
    fams = _families(_chiefs_opoy())
    mahomes = _entities(fams["offensive player of the year"])["Patrick Mahomes"]
    assert mahomes["probability"] == 0.01
    assert 59164987 not in mahomes.get("merged_market_ids", [mahomes["market_id"]])


def test_the_finalist_market_is_not_family_shaped():
    assert _parse("Offensive Player of the Year Finalists") == (None, None)


def test_every_shortlist_title_in_production_stays_out_of_its_award_family():
    # Open production titles, 2026-09-24 census.
    for title in (
        "MVP Finalists",
        "American League MVP Finalists",
        "National League Cy Young Finalists",
        "Heisman Trophy Finalists",
        "Defensive Player to be a Heisman Trophy Finalist",
        "Defensive Rookie of the Year Finalists",
        "Coach of the Year Finalists",
        "Ballon d'Or 2026: Top 3 Finishers",
        "Top 5 Pro Basketball Draft Pick Wins Rookie of the Year?",
        "Grammy nominees: Album of the Year",
    ):
        assert _parse(title)[0] is None, title


def test_winner_titles_still_key_to_their_award():
    # Control: the guard must not strand the races it protects.
    assert _parse("Offensive Player of the Year Winner?")[0] == "offensive player of the year"
    assert _parse("MVP Winner?")[0] == "mvp"
    assert _parse("Heisman Trophy Winner")[0] == "heisman"
    assert _parse("Pro Football: 2026 MVP Winner")[0] == "mvp"


# --- #8385 / #7162: the AP award is the same award, one card ------------------------


def test_the_ap_and_venue_titles_of_one_award_are_one_card():
    fams = _families(_chiefs_opoy())
    assert "ap offensive player of the year" not in fams
    card = fams["offensive player of the year"]
    assert card["label"] == "Offensive Player Of The Year"
    assert set(_entities(card)) == {"Kenneth Walker III", "Patrick Mahomes", "Rashee Rice"}
    assert card["sources"] == ["kalshi", "polymarket"]


def test_every_polymarket_ap_nfl_award_keys_with_its_kalshi_twin():
    for award in ("Coach", "Comeback Player", "Defensive Player", "Defensive Rookie",
                  "Offensive Player", "Offensive Rookie"):
        poly = _parse(f"Pro Football: 2026-27 AP {award} of the Year Winner")[0]
        kalshi = _parse(f"{award} of the Year Winner?")[0]
        assert poly == kalshi == f"{award.lower()} of the year", award


# --- #8386: a single-game MVP is not the season MVP ---------------------------------


def test_the_super_bowl_mvp_question_is_not_a_row_on_the_season_mvp_card():
    fams = _families(_chiefs_mvp())
    rows = _entities(fams["mvp"]) if "mvp" in fams else {}
    assert not any("Walker" in e for e in rows), list(rows)
    assert all(r["market_id"] != 479 for r in rows.values())


def test_the_championship_mvp_keys_to_its_own_family():
    assert _parse("Pro Football Championship MVP?")[0] == "championship game mvp"
    assert _parse("Super Bowl MVP")[0] == "championship game mvp"
    assert _parse("World Series MVP")[0] == "championship game mvp"
    # Control: the season award and the Finals MVP keep their keys.
    assert _parse("MVP Winner?")[0] == "mvp"
    assert _parse("Finals MVP Winner")[0] == "finals mvp"


def test_a_candidate_written_as_the_whole_question_prints_as_the_candidate():
    assert extract_entity(
        "Pro Football Championship MVP?",
        "Will Kenneth Walker III win the Pro Football Championship Game MVP?",
    ) == "Kenneth Walker III"
    # Control: a plain candidate outcome is untouched.
    assert extract_entity("MVP Winner?", "Patrick Mahomes") == "Patrick Mahomes"

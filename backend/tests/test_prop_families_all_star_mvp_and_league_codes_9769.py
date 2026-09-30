"""#9769 — the Yankees page's prop races: an All-Star Game MVP is not the season MVP,
and a league code in a heading is printed as a league code.

Yankees page, production 2026-09-30 (390px, D48 walk):

* The "MVP" card listed Aaron Judge 34% (Kalshi AL MVP, live) and, below him,
  "Cody Bellinger ✓ WON 100%" — Kalshi 55686575 "All-Star Game MVP Winner",
  resolved 2026-07-15. The title fell through to the bare "mvp" keyword, the
  same way the Super Bowl MVP did before #8386.
* The reliever card was headed "Al Reliever Of The Year": the family key is
  lower-cased and ``capitalize`` turned the league code into the name "Al".

Specimens are those rows, trimmed.
"""

from app.utils.prop_families import _family_label, _parse, group_prop_families


def _market(market_id, name, source, status, outcomes, group_id):
    return {
        "market_id": market_id,
        "name": name,
        "source": source,
        "group_id": group_id,
        "status": status,
        "resolution_date": "2026-11-20T00:00:00+00:00",
        "sport": "baseball",
        "outcomes": [
            {"outcome_id": market_id * 100 + i, "name": n, "probability": p, "is_winner": w}
            for i, (n, p, w) in enumerate(outcomes)
        ],
    }


def _yankees_mvp():
    return [
        _market(62952889, "AL MVP Winner", "kalshi", "open",
                [("Aaron Judge", 0.34, None), ("Cam Schlittler", 0.035, None)],
                "kalshi:KXMLBALMVP-26"),
        _market(55686575, "All-Star Game MVP Winner", "kalshi", "resolved",
                [("Cody Bellinger", 1.0, True), ("Aaron Judge", 0.0, False)],
                "kalshi:KXMLBASGMVP-26"),
    ]


def _families(markets):
    return {f["family_key"]: f for f in group_prop_families(markets)}


def test_the_all_star_mvp_winner_is_not_a_row_on_the_season_mvp_card():
    fams = _families(_yankees_mvp())
    mvp_rows = fams["mvp"]["rows"]
    assert all(r["market_id"] != 55686575 for r in mvp_rows), mvp_rows
    assert not any(r.get("result") == "won" for r in mvp_rows), mvp_rows


def test_the_all_star_mvp_is_its_own_card_under_its_own_name():
    fams = _families(_yankees_mvp())
    assert fams["all-star game mvp"]["label"] == "All-Star Game MVP"
    assert {r["market_id"] for r in fams["all-star game mvp"]["rows"]} == {55686575}


def test_every_spelling_of_the_all_star_mvp_keys_to_its_own_family():
    for title in ("All-Star Game MVP Winner", "All Star Game MVP", "2026 All-Star MVP?", "All Star MVP"):
        assert _parse(title)[0] == "all-star game mvp", title
    # Control: the season award and the one-game championship MVP keep their keys.
    assert _parse("AL MVP Winner")[0] == "mvp"
    assert _parse("World Series MVP")[0] == "championship game mvp"


def test_a_league_code_in_a_heading_prints_in_capitals():
    assert _family_label(_parse("AL Reliever of the Year")[0]) == "AL Reliever Of The Year"
    assert _family_label(_parse("AL Rookie of the Year")[0]) == "AL Rookie Of The Year"
    assert _family_label(_parse("NL Reliever of the Year")[0]) == "NL Reliever Of The Year"


def test_ordinary_words_keep_the_house_casing():
    # Control: the "Of The Year" casing other guards pin is unchanged.
    assert _family_label("defensive player of the year") == "Defensive Player Of The Year"
    assert _family_label("sixth man of the year") == "Sixth Man Of The Year"
    assert _family_label("most improved player") == "Most Improved Player"


# ---------------------------------------------------------------------------
# After-check, production 2026-09-30 09:51Z: with Bellinger gone the card was
# still headed by "Aaron Judge 34%" — and 62952889 is NOT the AL MVP (the
# specimen above mislabelled it). It is Kalshi's "Pro Baseball Championship
# Series MVP Winner", the World Series MVP; Judge's AL MVP price is 1% (216).
# "championship mvp" missed it on the word "series". Census of series-MVP
# titles in futures_markets the same minute: that one, "ALCS MVP Winner",
# "NLCS MVP Winner", "MLB World Series MVP", "MLB Postseason: World Series MVP".
# ---------------------------------------------------------------------------


def _yankees_mvp_after_check():
    return [
        _market(216, "AL MVP Winner?", "kalshi", "open",
                [("Aaron Judge", 0.01, None), ("Cam Schlittler", 0.035, None)],
                "kalshi:KXMLBALMVP-26"),
        _market(62952889, "Pro Baseball Championship Series MVP Winner", "kalshi", "open",
                [("Aaron Judge", 0.34, None), ("Shohei Ohtani", 0.12, None)],
                "kalshi:KXMLBWSMVP-26"),
        _market(70000001, "ALCS MVP Winner", "kalshi", "open",
                [("Aaron Judge", 0.2, None), ("Junior Caminero", 0.1, None)],
                "kalshi:KXMLBALCSMVP-26"),
    ]


def test_the_world_series_mvp_price_does_not_head_the_season_mvp_card():
    fams = _families(_yankees_mvp_after_check())
    mvp = {r["entity"]: r for r in fams["mvp"]["rows"]}
    assert mvp["Aaron Judge"]["probability"] == 0.01, mvp["Aaron Judge"]
    assert {r["market_id"] for r in fams["mvp"]["rows"]} == {216}


def test_series_mvps_get_their_own_cards():
    fams = _families(_yankees_mvp_after_check())
    assert {r["market_id"] for r in fams["championship game mvp"]["rows"]} == {62952889}
    assert fams["alcs mvp"]["label"] == "ALCS MVP"
    assert {r["market_id"] for r in fams["alcs mvp"]["rows"]} == {70000001}
    assert _parse("NLCS MVP Winner")[0] == "nlcs mvp"
    assert _family_label("nlcs mvp") == "NLCS MVP"


def test_control_the_season_award_and_world_series_spellings_are_unchanged():
    assert _parse("AL MVP Winner?")[0] == "mvp"
    assert _parse("MLB: 2026 AL MVP")[0] == "mvp"
    assert _parse("MLB World Series MVP")[0] == "championship game mvp"
    assert _parse("MLB Postseason: World Series MVP")[0] == "championship game mvp"

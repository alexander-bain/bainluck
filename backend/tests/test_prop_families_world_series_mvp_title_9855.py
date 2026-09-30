"""#9855 — an MLB team page's World Series MVP card is titled "World Series MVP",
not football's "Championship Game MVP".

Dodgers page, production 2026-09-30 15:15Z (390px, web `df7f79ac`): the Prop Races
card read "Championship Game MVP" over Ohtani 13% / Freeman 9% / Tucker 5%, while
the same page's Season Futures list named the market "MLB Postseason: World Series
MVP". The Red Sox page showed the same title.

The family key stays "championship game mvp" for every sport — it is what keeps a
one-game MVP off the season-MVP card (#8386, #9769). Only the title reads the sport.
Specimens are the two open production markets behind that card, trimmed.
"""

from app.utils.prop_families import _family_label, _parse, group_prop_families


def _market(market_id, name, source, outcomes, group_id, sport):
    market = {
        "market_id": market_id,
        "name": name,
        "source": source,
        "group_id": group_id,
        "status": "open",
        "resolution_date": "2026-11-05T00:00:00+00:00",
        "outcomes": [
            {"outcome_id": market_id * 100 + i, "name": n, "probability": p, "is_winner": None}
            for i, (n, p) in enumerate(outcomes)
        ],
    }
    if sport is not None:
        market["sport"] = sport
    return market


def _dodgers_ws_mvp(sport="baseball"):
    return [
        _market(62952889, "Pro Baseball Championship Series MVP Winner", "kalshi",
                [("Shohei Ohtani", 0.13), ("Freddie Freeman", 0.09)],
                "kalshi:KXMLBWSMVP-26", sport),
        _market(71000001, "MLB Postseason: World Series MVP", "polymarket",
                [("Shohei Ohtani", 0.12), ("Kyle Tucker", 0.05)],
                "polymarket:71000001", sport),
    ]


def _nfl_sb_mvp(sport="football"):
    return [
        _market(479, "Pro Football Championship MVP?", "kalshi",
                [("Patrick Mahomes", 0.14), ("Josh Allen", 0.11)],
                "kalshi:KXNFLSBMVP-27", sport),
    ]


def _families(markets):
    return {f["family_key"]: f for f in group_prop_families(markets)}


def test_the_mlb_card_is_titled_world_series_mvp():
    fam = _families(_dodgers_ws_mvp())["championship game mvp"]
    assert fam["label"] == "World Series MVP"
    assert {r["entity"] for r in fam["rows"]} == {"Shohei Ohtani", "Freddie Freeman", "Kyle Tucker"}


def test_the_nfl_card_is_titled_super_bowl_mvp():
    fam = _families(_nfl_sb_mvp())["championship game mvp"]
    assert fam["label"] == "Super Bowl MVP"


def test_the_family_key_is_unchanged_so_the_season_mvp_card_stays_clean():
    for title in ("Pro Baseball Championship Series MVP Winner", "MLB Postseason: World Series MVP",
                  "Pro Football Championship MVP?", "Super Bowl MVP"):
        assert _parse(title)[0] == "championship game mvp", title


def test_a_card_whose_venue_named_no_sport_keeps_the_neutral_title():
    fam = _families(_dodgers_ws_mvp(sport=None))["championship game mvp"]
    assert fam["sport"] is None
    assert fam["label"] == "Championship Game MVP"
    assert _family_label("championship game mvp") == "Championship Game MVP"


def test_two_sports_on_one_key_each_get_their_own_title():
    fams = _families(_dodgers_ws_mvp() + _nfl_sb_mvp())
    assert fams["baseball:championship game mvp"]["label"] == "World Series MVP"
    assert fams["football:championship game mvp"]["label"] == "Super Bowl MVP"


def test_control_other_titles_ignore_the_sport():
    # A key with no per-sport entry reads exactly as before, whatever the sport.
    assert _family_label("mvp", "baseball") == "MVP"
    assert _family_label("alcs mvp", "baseball") == "ALCS MVP"
    assert _family_label("all-star game mvp", "baseball") == "All-Star Game MVP"
    assert _family_label("finals mvp", "basketball") == "Finals MVP"
    assert _family_label("defensive player of the year", "football") == "Defensive Player Of The Year"
    # And the per-sport entry does not leak to a sport it was not written for.
    assert _family_label("championship game mvp", "basketball") == "Championship Game MVP"

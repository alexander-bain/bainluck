"""#2311 — a player's season ladder reaches the team page as one row with its line.

After #8341 the Chiefs page searched Travis Kelce and Xavier Worthy, and still
showed none of their props: Polymarket writes a season total as one binary per
line — "Will Travis Kelce have 874.5+ receiving yards in the 2026-27 NFL
regular season?" — and ``_parse`` keyed that shape to no family, so all
sixteen open Kelce/Worthy rungs (production 2026-09-24) were discarded before
grouping.

The shape now keys to ``season <stat>``. Each player's rungs reduce to ONE row:
the priced line nearest an even call, with the line as the row's caption
("875+ receiving yards"), because a probability without its line says nothing
and four rungs per player is the ladder spam the page must not print.
"""

from app.utils.prop_families import _parse, extract_entity, group_prop_families

_SEASON = "in the 2026-27 NFL regular season?"


def _rung(mid, who, line, p, *, source="polymarket", status="open", winner=None):
    yes = {"name": "Yes", "probability": p}
    no = {"name": "No", "probability": None if p is None else round(1 - p, 3)}
    if winner is not None:
        # Production grades a rung on its Yes leg only: a missed line is
        # Yes=False, No=False (53 No legs graded, none True, 2026-09-24).
        yes["is_winner"] = winner
        no["is_winner"] = False
    return {
        "id": mid,
        "name": f"Will {who} have {line}+ receiving yards {_SEASON}",
        "source": source,
        "status": status,
        "resolution_date": "2027-01-12",
        "sport": "football",
        "outcomes": [yes, no],
    }


def _production_chiefs() -> list[dict]:
    """The open Kelce/Worthy yards rungs as production priced them (Yes)."""
    return [
        _rung(61495185, "Travis Kelce", "474.5", 0.79),
        _rung(61355882, "Travis Kelce", "674.5", None),
        _rung(61355883, "Travis Kelce", "874.5", 0.365),
        _rung(61355884, "Travis Kelce", "1,074.5", 0.195),
        _rung(61876821, "Xavier Worthy", "249.5", 0.895),
        _rung(61790369, "Xavier Worthy", "449.5", 0.57),
        _rung(61876823, "Xavier Worthy", "649.5", 0.22),
    ]


def _family(families, key="season receiving yards"):
    matches = [f for f in families if f["family_key"] == key]
    assert len(matches) == 1, [f["family_key"] for f in families]
    return matches[0]


def test_the_season_rung_shape_keys_to_a_family_with_the_player():
    name = "Will Travis Kelce have 1,074.5+ receiving yards in the 2026-27 NFL regular season?"
    assert _parse(name) == ("season receiving yards", "Travis Kelce")
    assert extract_entity(name) == "Travis Kelce"
    assert _parse(
        "Will Travis Kelce have 6.5+ receiving touchdowns in the 2026-27 NFL regular season?"
    ) == ("season receiving touchdowns", "Travis Kelce")


def test_a_single_game_line_does_not_join_a_season_ladder():
    assert _parse("Will Travis Kelce have 60+ receiving yards in Week 3 against the Bills?") == (None, None)


def test_each_player_gets_one_row_at_the_line_nearest_an_even_call():
    fam = _family(group_prop_families(_production_chiefs()))
    rows = {r["entity"]: r for r in fam["rows"]}
    assert set(rows) == {"Travis Kelce", "Xavier Worthy"}
    assert len(fam["rows"]) == 2
    assert (rows["Travis Kelce"]["market_id"], rows["Travis Kelce"]["probability"]) == (61355883, 0.365)
    assert rows["Travis Kelce"]["top_outcome"] == "875+ receiving yards"
    assert (rows["Xavier Worthy"]["market_id"], rows["Xavier Worthy"]["probability"]) == (61790369, 0.57)
    assert rows["Xavier Worthy"]["top_outcome"] == "450+ receiving yards"
    assert fam["label"] == "Season Receiving Yards"
    assert not [k for r in fam["rows"] for k in r if k.startswith("_")]


def test_an_unpriced_rung_never_speaks_for_the_ladder():
    # 0.0 and an unpriced rung are equally far from an even call; the priced
    # one must still win, whichever line is lower.
    fam = _family(group_prop_families([
        _rung(1, "Travis Kelce", "274.5", None),
        _rung(2, "Travis Kelce", "1,274.5", 0.0),
        _rung(3, "Xavier Worthy", "449.5", 0.57),
    ]))
    kelce = next(r for r in fam["rows"] if r["entity"] == "Travis Kelce")
    assert (kelce["market_id"], kelce["top_outcome"]) == (2, "1,275+ receiving yards")


def test_the_same_line_on_two_venues_merges_before_the_pick():
    fam = _family(group_prop_families([
        _rung(1, "Travis Kelce", "874.5", 0.36),
        _rung(2, "Travis Kelce", "874.5", 0.40, source="kalshi"),
        _rung(3, "Travis Kelce", "474.5", 0.79),
        _rung(4, "Xavier Worthy", "449.5", 0.57),
    ]))
    kelce = next(r for r in fam["rows"] if r["entity"] == "Travis Kelce")
    assert kelce["top_outcome"] == "875+ receiving yards"
    assert kelce["sources"] == ["kalshi", "polymarket"]
    assert sorted(kelce["merged_market_ids"]) == [1, 2]


def test_a_settled_ladder_names_the_highest_line_that_hit():
    fam = _family(group_prop_families([
        _rung(1, "Travis Kelce", "474.5", 0.99, status="resolved", winner=True),
        _rung(2, "Travis Kelce", "674.5", 0.99, status="resolved", winner=True),
        _rung(3, "Travis Kelce", "874.5", 0.01, status="resolved", winner=False),
        _rung(4, "Xavier Worthy", "449.5", 0.01, status="resolved", winner=False),
        _rung(5, "Xavier Worthy", "649.5", 0.01, status="resolved", winner=False),
    ]))
    rows = {r["entity"]: r for r in fam["rows"]}
    assert (rows["Travis Kelce"]["market_id"], rows["Travis Kelce"]["result"]) == (2, "won")
    assert (rows["Xavier Worthy"]["market_id"], rows["Xavier Worthy"]["result"]) == (4, "lost")


def test_one_players_ladder_alone_is_still_not_a_family():
    # The >= 2 distinct entities rule is unchanged (prop_families_warm derives
    # MIN_PROPS_TO_WARM from it): three rungs about one player emit nothing.
    assert group_prop_families([
        _rung(i, "Travis Kelce", line, 0.5) for i, line in enumerate(["474.5", "674.5", "874.5"])
    ]) == []

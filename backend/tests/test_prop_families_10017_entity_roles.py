"""#10017 — the Leafs page: "Teams" and "Players" are not people.

Leafs page, production 05:57Z 10/1 (390px, release v5367 ``10e786c1``):

* A prop-race card headed "To Record Points" had two rows, "Teams" 89%
  (top outcome Toronto Maple Leafs) and "Players" 61% (top outcome William
  Nylander). Both came from Polymarket FIELD markets — ``62861755`` "NHL: Teams
  to Record 80+ Points" (``polymarket:1093928``) and ``63068141`` "NHL: Players
  to Record 80+ Points" (``polymarket:1098841``) — whose title subject was read
  as the entity by the "<entity> to <verb> N <unit>" arm.
* Nylander's 61% was already the head row of Season Points (rung ``63123223``,
  same ``group_id``), so one question printed twice under two headers.

Specimens are the served rows (``artifacts/9983/propfam-leafs-after.json``),
trimmed: each field leg carries the one named outcome the served row showed as
``top_outcome``; the sibling legs' names are stand-ins (the payload carries
only their ids and the merged price). The controls are named subjects in the
same verb form, and the completed #9983 Olympic MVP family.
"""

from app.utils.prop_families import _parse, group_prop_families

SEASON = "in the 2026-27 NHL regular season?"
TEAMS_FIELD = "NHL: Teams to Record 80+ Points"
PLAYERS_FIELD = "NHL: Players to Record 80+ Points"
FIELD_IDS = {62861755, 62861731, 63068141, 63049664}


def _market(market_id, name, outcomes, group_id, source="polymarket", **extra):
    return {
        "market_id": market_id,
        "name": name,
        "source": source,
        "group_id": group_id,
        "status": extra.pop("status", "open"),
        "resolution_date": extra.pop("resolution_date", "2027-04-20T00:00:00+00:00"),
        "sport": "hockey",
        "outcomes": [
            {"outcome_id": market_id * 100 + i, "name": n, "probability": p, "is_winner": w}
            for i, (n, p, w) in enumerate(outcomes)
        ],
        **extra,
    }


def _field_legs():
    return [
        _market(62861755, TEAMS_FIELD, [("Toronto Maple Leafs", 0.89, None)], "polymarket:1093928"),
        _market(62861731, TEAMS_FIELD, [("Montreal Canadiens", 0.105, None)], "polymarket:1093928"),
        _market(63068141, PLAYERS_FIELD, [("William Nylander", 0.605, None)], "polymarket:1098841"),
        _market(63049664, PLAYERS_FIELD, [("Auston Matthews", 0.155, None)], "polymarket:1098841"),
    ]


def _rung(market_id, who, p):
    yes_no = [("Yes", p, None), ("No", None if p is None else round(1 - p, 3), None)]
    return _market(market_id, f"Will {who} have 80+ points {SEASON}", yes_no, "polymarket:1098841")


def _season_points():
    return [
        _rung(63123223, "William Nylander", 0.605),
        _rung(63119206, "Auston Matthews", 0.415),
        _rung(63123191, "Matthew Knies", 0.175),
        _rung(63119224, "John Tavares", None),
    ]


def _olympic():
    return _market(
        110951, "Winter Olympics Men's Hockey MVP",
        [("Auston Matthews", 0.02, False), ("William Nylander", 0.005, False)],
        "kalshi:KXWOMHOCKEYMVP-26", source="kalshi", status="resolved",
        resolution_date="2026-02-23T00:00:00+00:00",
    )


def _leafs_page():
    return group_prop_families(_field_legs() + _season_points() + [_olympic()])


def _families(fams):
    return {f["family_key"]: f for f in fams}


# --- the field titles are not family-shaped ---------------------------------


def test_a_generic_teams_or_players_subject_is_not_an_entity():
    assert _parse(TEAMS_FIELD) == (None, None)
    assert _parse(PLAYERS_FIELD) == (None, None)
    # Casing and the category prefix are not what the guard keys on.
    assert _parse("teams to record 80+ points") == (None, None)
    assert _parse("Players to score 40+ goals") == (None, None)


def test_the_field_markets_alone_make_no_family():
    # The production BEFORE: four field legs, two "entities" — Teams, Players.
    assert group_prop_families(_field_legs()) == []


def test_the_leafs_page_has_no_to_record_points_card_and_no_role_noun_rows():
    fams = _leafs_page()
    assert "to record points" not in _families(fams), [f["family_key"] for f in fams]
    rows = [r for f in fams for r in f["rows"]]
    assert not {r["entity"] for r in rows} & {"Teams", "Players"}
    held = {mid for r in rows for mid in [r["market_id"], *r.get("merged_market_ids", [])]}
    assert not held & FIELD_IDS


# --- Nylander's 61% shows exactly once, in Season Points --------------------


def test_nylanders_season_points_question_prints_once():
    # The BEFORE's duplicate was keyed "Players" and named Nylander only as its
    # top outcome — so match on either slot, or the duplicate is invisible here.
    fams = _leafs_page()
    hits = [
        (f["family_key"], r["market_id"])
        for f in fams
        for r in f["rows"]
        if "William Nylander" in (r["entity"], r.get("top_outcome")) and r["probability"] == 0.605
    ]
    assert hits == [("season points", 63123223)]


def test_season_points_keeps_every_rung_unchanged():
    fam = _families(_leafs_page())["season points"]
    assert fam["label"] == "Season Points"
    got = [(r["entity"], r["market_id"], r["probability"], r["top_outcome"]) for r in fam["rows"]]
    assert got == [
        ("William Nylander", 63123223, 0.605, "80+ points"),
        ("Auston Matthews", 63119206, 0.415, "80+ points"),
        ("Matthew Knies", 63123191, 0.175, "80+ points"),
        ("John Tavares", 63119224, None, "80+ points"),
    ]
    assert all(r["group_id"] == "polymarket:1098841" for r in fam["rows"])


# --- controls: named subjects in the same verb form are untouched -----------


def test_a_named_player_in_the_same_form_keeps_its_entity():
    assert _parse("William Nylander to Record 80+ Points") == ("to record points", "William Nylander")
    assert _parse("NHL: Auston Matthews to score 40+ goals") == ("to score goals", "Auston Matthews")


def test_named_teams_in_the_same_form_still_make_a_family():
    fams = _families(group_prop_families([
        _market(70000001, "Toronto Maple Leafs to Record 100+ Points", [("Yes", 0.62, None), ("No", 0.38, None)], "polymarket:7000"),
        _market(70000002, "Montreal Canadiens to Record 100+ Points", [("Yes", 0.21, None), ("No", 0.79, None)], "polymarket:7000"),
    ] + _field_legs()))
    fam = fams["to record points"]
    got = [(r["entity"], r["market_id"], r["probability"]) for r in fam["rows"]]
    assert got == [("Toronto Maple Leafs", 70000001, 0.62), ("Montreal Canadiens", 70000002, 0.21)]


def test_the_9983_olympic_mvp_family_is_unchanged_beside_the_field_markets():
    fam = _families(_leafs_page())["2026 winter olympics men's mvp"]
    assert fam["label"] == "2026 Winter Olympics Men's MVP"
    rows = {r["entity"]: r for r in fam["rows"]}
    assert set(rows) == {"Auston Matthews", "William Nylander"}
    assert rows["Auston Matthews"]["probability"] == 0.02
    assert rows["William Nylander"]["probability"] == 0.005
    assert {r["outcome_id"] for r in rows.values()} == {11095100, 11095101}
    assert all(r["settled"] is True and r["result"] == "lost" for r in rows.values())

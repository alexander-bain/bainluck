"""#6909, the Polymarket O/U arm — a football prop found by NAME had no words.

A Polymarket prop's id is numeric, so the Kalshi ticker table can never answer
for it and `_prop_stat_keys` falls to the market NAME. That path knew baseball,
basketball and soccer and not one football stat, so on the Saints 27 - Raiders
35 final (event 14782707, read 2026-09-28 ~11:05Z) Kalshi graded 402 of 402
player props and Polymarket **0 of 154**: WHAT HIT opened with five
`Tyler Shough: Passing Yards O/U …  Under · Resolved · grading unavailable` rows
directly above Kalshi's `Tyler Shough: 150+ … → 250.0 hit`.

The census below runs the REAL grader over every Polymarket row that page
served, joined to its stored settlement, against that game's real box score
(fixture provenance inside the JSON). Three things it pins that the diff alone
does not say:

1. **Every new verdict agrees with the row's own settlement** — 147 graded, 0
   disagreements. That is the check that matters, because the box score is the
   only thing typing these rows: `clean_resolution` is tier 1 and
   `_venue_typed_hit` refuses it by design (CERT-3025).
2. **One market disagrees, and it is WITHHELD, not published.** Juwan Johnson's
   stored box line says 48 receiving yards; Polymarket settled his O/U 49.5
   Over, and Kalshi's own `api_settlement` of his 50+ rung also says he cleared
   50. The name path withholds that verdict and keeps the 48.
3. **"Most Receiving Yards" is not a football prop to this path.** It names the
   stat but asks who led; the 510-row Kalshi census in
   `test_nfl_prop_stat_vocabulary_6909.py` moved 17 superlative rows before the
   guard existed, and moves 0 with it.
"""

import collections
import json
from pathlib import Path

import pytest

from app.routes.events import (
    _build_prop_grade_context,
    _grade_settled_prop,
    _prop_stat_keys,
)

FIXTURE = Path(__file__).parent / "fixtures" / "event_nfl_polymarket_ou_props_6909.json"


class _Obj:
    """Stand-in for the ORM rows the grader reads (attribute access only)."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture(scope="module")
def captured():
    return json.loads(FIXTURE.read_text())


@pytest.fixture(scope="module")
def ctx(captured):
    built = _build_prop_grade_context(
        _Obj(box_score_data={"players": captured["box_score_players"]})
    )
    assert built is not None
    return built


def _grade(captured, ctx, row):
    meta = captured["markets"][str(row["_market_id"])]
    stored = row["_stored"]
    return _grade_settled_prop(
        True,
        ctx,
        _Obj(external_id=meta["external_id"], name=meta["name"]),
        _Obj(
            name=row["outcome_name"],
            is_winner=stored["is_winner"],
            resolution_source=stored["resolution_source"],
            current_probability=stored["current_probability"],
        ),
        row["threshold"],
        row["_inverted"],
    )


def test_the_captured_payload_still_carries_the_defect(captured):
    """The fixture is the BEFORE and is never refreshed from a fixed tree."""
    rows = captured["player_props"]
    assert len(rows) == 154
    assert sum(r["hit"] is not None for r in rows) == 0
    assert sum(r["actual"] is not None for r in rows) == 0
    # Every row carries a settlement the reader was shown as "grading
    # unavailable" — the gap was the grader, not the data.
    assert {r["_stored"]["resolution_source"] for r in rows} == {"clean_resolution"}


def test_every_new_verdict_agrees_with_the_rows_own_settlement(captured, ctx):
    graded, disagree = 0, []
    for row in captured["player_props"]:
        g = _grade(captured, ctx, row)
        if g["hit"] is None:
            continue
        graded += 1
        if g["hit"] is not row["_stored"]["is_winner"]:
            disagree.append((row["market_name"], row["outcome_name"], g["actual"]))
    assert disagree == []
    assert graded == 147


def test_the_specimen_rows_grade_off_the_passers_line(captured, ctx):
    """The five rows the shopper photographed, and their Over twins."""
    seen = {}
    for row in captured["player_props"]:
        if not row["market_name"].startswith("Tyler Shough: Passing Yards O/U"):
            continue
        g = _grade(captured, ctx, row)
        seen[(row["threshold"], row["outcome_name"])] = (g["actual"], g["hit"])
    for line in (149.5, 174.5, 199.5, 224.5, 249.5):
        assert seen[(line, "Under")] == (250.0, False)
        assert seen[(line, "Over")] == (250.0, True)
    assert seen[(324.5, "Over")] == (250.0, False)


def test_every_row_still_ungraded_is_accounted_for(captured, ctx):
    buckets = collections.Counter()
    for row in captured["player_props"]:
        g = _grade(captured, ctx, row)
        if g["hit"] is not None:
            continue
        name = row["market_name"]
        if name.startswith("Juwan Johnson: Receiving Yards O/U 49.5"):
            # Point 2 of the module docstring: withheld, number kept.
            assert g["actual"] == 48.0
            buckets["box score contradicts the settlement"] += 1
        elif "Touchdowns" in name and "O/U" not in name:
            buckets["touchdown count, deliberately unmapped"] += 1
        elif name.startswith("Jack Bech:"):
            # No line in the box score at all; absence is not a zero (#1728).
            assert g["actual"] is None
            buckets["player absent from the box score"] += 1
        elif "Team First TD" in name:
            buckets["not a stat prop"] += 1
        else:
            buckets["UNCLASSIFIED"] += 1
    assert dict(buckets) == {
        "box score contradicts the settlement": 2,
        "touchdown count, deliberately unmapped": 2,
        "player absent from the box score": 2,
        "not a stat prop": 1,
    }


# --- the rules, one row each ------------------------------------------------

_LINE = {
    "passing yards": 250.0,
    "rushing yards": 36.0,
    "receiving yards": 12.0,
    "passing touchdowns": 4.0,
    "completions": 29.0,
    "long reception": 12.0,
    "receptions": 2.0,
}


def _one(market_name, outcome_name, threshold, is_under, *, is_winner=None,
         source=None, external_id="0xabc", players=None):
    ctx = _build_prop_grade_context(
        _Obj(box_score_data={"players": players or {"Pat Passer": _LINE}})
    )
    return _grade_settled_prop(
        True,
        ctx,
        _Obj(external_id=external_id, name=market_name),
        _Obj(name=outcome_name, is_winner=is_winner, resolution_source=source,
             current_probability=None),
        threshold,
        is_under,
    )


@pytest.mark.parametrize(
    "stat,key",
    [
        ("Passing Yards", "passing yards"),
        ("Rushing Yards", "rushing yards"),
        ("Receiving Yards", "receiving yards"),
        ("Passing Touchdowns", "passing touchdowns"),
        ("Passing Completions", "completions"),
        ("Longest Reception", "long reception"),
        ("Receptions", "receptions"),
    ],
)
def test_each_football_phrase_reads_the_box_score_key(stat, key):
    g = _one(f"Pat Passer: {stat} O/U 1.5", "Over", 1.5, False)
    assert g["actual"] == _LINE[key]


def test_the_composite_sums_both_legs_and_never_grades_off_one():
    g = _one("Pat Passer: Rushing + Receiving Yards O/U 40.5", "Over", 40.5, False)
    assert g["actual"] == 48.0
    assert g["hit"] is True


def test_passing_attempts_stays_unmapped():
    g = _one("Pat Passer: Passing Attempts O/U 30.5", "Over", 30.5, False)
    assert g["actual"] is None and g["hit"] is None


def test_a_superlative_is_not_read_as_one_players_line():
    market = _Obj(external_id="KXNFLMOSTRECYDS-26SEP27LVNO",
                  name="Las Vegas vs New Orleans: Most Receiving Yards")
    ctx = _build_prop_grade_context(
        _Obj(box_score_data={"players": {"Pat Passer": _LINE}})
    )
    assert _prop_stat_keys(market, ctx, _LINE) is None


def test_a_contradicting_settlement_withholds_the_verdict_and_keeps_the_number():
    g = _one("Pat Passer: Receiving Yards O/U 12.5", "Over", 12.5, False,
             is_winner=True, source="clean_resolution")
    assert g["actual"] == 12.0
    assert g["hit"] is None


def test_an_ungraded_rows_stored_false_is_not_a_contradiction():
    """Production stores False on ungraded rows. No source ⇒ not a verdict."""
    g = _one("Pat Passer: Passing Yards O/U 199.5", "Over", 199.5, False,
             is_winner=False, source=None)
    assert g["hit"] is True


def test_the_conflict_rule_does_not_touch_a_ticker_graded_row():
    """Kalshi rows keep the box-score-wins rule they had (#6751)."""
    g = _one("Las Vegas vs New Orleans: Receiving Yards", "Pat Passer: 15+", 15.0,
             False, is_winner=True, source="api_settlement",
             external_id="KXNFLRECYDS-26SEP27LVNO")
    assert g["actual"] == 12.0
    assert g["hit"] is False

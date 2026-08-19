"""#1986 — structural test over PRODUCTION relabel collisions (#1976 style).

Fixture: the real `/api/events/15194464/related-futures` payload (Orioles at
Rays), captured 2026-08-18 from master `72b7ed7a` / Heroku v3850.

The census this asserts is the whole point. The same payload carries TWO
collision classes wearing the same `merge_group`, and a fix that cannot tell
them apart is worse than the bug:

  world_series_champion :  2 rows, kalshi + polymarket, markets 275 + 114584
                           -> ONE question, two sources        -> MUST merge
  world_series_matchup  : 30 rows, kalshi only,  market 2417016
                           -> THIRTY questions, one per opponent -> MUST NOT

So every assertion below is two-directional: the duplicate collapses AND the
thirty distinct matchups survive untouched (gotcha #43 — a cap's guard tests
must assert both the flood is capped and the adjacent surface stays populated).
"""

import json
from pathlib import Path

import pytest

from app.utils.aggregation import SOURCE_WEIGHTS
from app.utils.futures_source_merge import (
    blend_probabilities,
    entities_compatible,
    merge_relabel_collisions,
)

FIXTURE = Path(__file__).parent / "fixtures" / "event_15194464_related_futures.json"


@pytest.fixture(scope="module")
def payload():
    return json.loads(FIXTURE.read_text())


def _champ(rows):
    return [r for r in rows if r.get("merge_group") == "world_series_champion"]


def _matchup(rows):
    return [r for r in rows if r.get("merge_group") == "world_series_matchup"]


def test_fixture_still_carries_both_collision_classes(payload):
    """If production drifts out of this shape the test below proves nothing."""
    home = payload["home_team_futures"]
    assert len(_champ(home)) == 2, "specimen needs the two-source champion pair"
    assert len({r["source"] for r in _champ(home)}) == 2
    assert len(_matchup(home)) == 15, "specimen needs the same-source matchup fan"
    assert len({r["source"] for r in _matchup(home)}) == 1


def test_the_duplicate_collapses_to_one_row(payload):
    for side in ("home_team_futures", "away_team_futures"):
        merged = merge_relabel_collisions(payload[side])
        champs = _champ(merged)
        assert len(champs) == 1, f"{side}: expected one blended row, got {len(champs)}"
        assert champs[0]["source_count"] == 2
        assert sorted(champs[0]["all_sources"]) == ["kalshi", "polymarket"]


def test_the_thirty_distinct_matchups_are_untouched(payload):
    """The adjacent surface must stay populated — and byte-identical."""
    for side in ("home_team_futures", "away_team_futures"):
        before = _matchup(payload[side])
        after = _matchup(merge_relabel_collisions(payload[side]))
        assert after == before, f"{side}: matchup rows must pass through unchanged"


def test_transition_census_is_exactly_one_class(payload):
    """Total accounting: 18 -> 17 per side, and the ONLY row that changed is
    the champion row. Zero changes of any other class."""
    for side in ("home_team_futures", "away_team_futures"):
        before, after = payload[side], merge_relabel_collisions(payload[side])
        assert len(before) == 18
        assert len(after) == 17

        changed = [r for r in after if r not in before]
        assert len(changed) == 1, changed
        assert changed[0]["merge_group"] == "world_series_champion"

        # everything that is not the champion pair survives identically
        survivors = [r for r in before if r.get("merge_group") != "world_series_champion"]
        assert all(r in after for r in survivors)


def test_an_equal_weight_pair_now_prints_the_midpoint(payload):
    """SUPERSEDED BY FABLE RULING (b), cycle 99. Rewritten, not deleted.

    This test used to pin the OPPOSITE assertion — that Kalshi 0.077 and
    Polymarket 0.0405, both weighing 0.8, blend to the LOWER value 0.0405 — and
    it defended that as "the standing algorithm's answer, not a local mean". The
    reasoning was sound and the ruling overturned it on evidence the test could
    not see: censused across the live merges, `median == min(values)` on 3 of 3
    and the bias was `-spread/2` EXACTLY, always downward. A tiebreak that
    always resolves down is a systematic discount, and which value sorts first
    carries no meaning.

    So the scope of the old objection survives — no second aggregator — but it
    now applies where there IS a judgement to express. On a genuine two-way tie
    there is none, and the midpoint is the only answer that does not silently
    prefer one side. The events hero keeps the weighted median untouched.
    """
    assert SOURCE_WEIGHTS["kalshi"] == SOURCE_WEIGHTS["polymarket"] == 0.8
    merged = merge_relabel_collisions(payload["home_team_futures"])
    row = _champ(merged)[0]
    assert row["probability"] == pytest.approx((0.077 + 0.0405) / 2)
    assert row["blend_rule"] == "equal_weight_midpoint"
    # The pair is 3.65 points apart, nowhere near the sanity threshold, so the
    # divergence gate must NOT claim it.
    assert "divergence" not in row


def test_a_merge_needs_all_three_conditions(payload):
    """Same source, or same market, or incompatible entities -> REFUSE.
    A refusal renders today's two rows; a wrong merge invents a number."""
    pair = _champ(payload["home_team_futures"])
    assert len(merge_relabel_collisions(pair)) == 1

    same_source = [dict(pair[0]), dict(pair[1])]
    same_source[1]["source"] = same_source[0]["source"]
    assert len(merge_relabel_collisions(same_source)) == 2

    same_market = [dict(pair[0]), dict(pair[1])]
    same_market[1]["market_id"] = same_market[0]["market_id"]
    assert len(merge_relabel_collisions(same_market)) == 2

    other_entity = [dict(pair[0]), dict(pair[1])]
    other_entity[1]["outcome_name"] = "Milwaukee Brewers"
    assert len(merge_relabel_collisions(other_entity)) == 2


def test_entity_aliasing_matches_teams_but_not_people():
    assert entities_compatible("Tampa Bay", "Tampa Bay Rays")
    assert entities_compatible("Baltimore Orioles", "Baltimore")
    assert not entities_compatible("Mason Miller", "Emmanuel Clase")
    assert not entities_compatible("Tampa Bay", "Milwaukee")
    assert not entities_compatible("", "Tampa Bay")


def test_blend_ignores_missing_probabilities():
    assert blend_probabilities([{"probability": None, "source": "kalshi"}]) is None
    got = blend_probabilities(
        [{"probability": None, "source": "kalshi"},
         {"probability": 0.25, "source": "polymarket"}]
    )
    assert got == pytest.approx(0.25)

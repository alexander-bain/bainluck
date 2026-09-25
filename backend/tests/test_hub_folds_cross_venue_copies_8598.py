"""#8598 — a hub section draws one card per question across venues.

ux/1491 · PILLAR: MATCHING / FORMATTING · SHIP: `/hub/esports` prints the
VALORANT Champions winner and MVP once each, not as a Kalshi card beside a
Polymarket card.

The specimen is production's own payload (`GET /api/hub/esports`, 2026-09-25),
banked verbatim in `fixtures/hub_esports_cross_venue_copies_8598.json` with the
neighbours that must NOT fold: the group-stage winner of the same tournament,
the unbeaten-champion and make-playoffs questions, another game's MVP, and the
two "Will a Western team win …" binaries. Measured over all five hubs the same
minute, the rule folded these two pairs and nothing else.
"""

import copy
import inspect
import json
from pathlib import Path

from app.routes import hub as hub_route
from app.utils.hub_cross_venue_fold import (
    fold_cross_venue_copies,
    is_cross_venue_copy,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "hub_esports_cross_venue_copies_8598.json"
)


def _sections() -> dict:
    return json.loads(FIXTURE.read_text())["sections"]


def _ids(rows) -> list:
    return [r["id"] for r in rows]


def _row(**over) -> dict:
    base = {
        "id": 1,
        "source": "kalshi",
        "name": "US Open Men's Singles Winner",
        "canonical_market_key": "tennis:US Open:championship:2026",
        "resolution_date": "2026-09-13T20:00:00+00:00",
        "top_outcomes": [
            {"name": n, "probability": p}
            for n, p in (("Sinner", 0.4), ("Alcaraz", 0.35), ("Djokovic", 0.1))
        ],
    }
    base.update(over)
    return base


# ── the specimen ────────────────────────────────────────────────────────────


def test_production_winner_pair_prints_once():
    assert {60775226, 61156894} <= set(_ids(_sections()["futures"]))  # both served
    futures = fold_cross_venue_copies(_sections())["futures"]
    names = [r["name"] for r in futures]
    assert "VALORANT Champions Shanghai Champion" in names
    assert "VALORANT Champions 2026: Winner" not in names
    # Both venues price all ten names, so the tie keeps the earlier card.
    assert 60775226 in _ids(futures) and 61156894 not in _ids(futures)


def test_production_mvp_pair_keeps_the_card_that_prices_more_of_the_field():
    assert {61484982, 61142921} <= set(_ids(_sections()["awards"]))  # both served
    awards = fold_cross_venue_copies(_sections())["awards"]
    # Kalshi prices two names (one off a zero bid, #8210); Polymarket prices
    # four. Keeping list order would have kept the worse card.
    assert _ids(awards) == [61142921, 60552214]


def test_the_survivor_takes_the_place_of_the_first_copy():
    before = _ids(_sections()["awards"])
    after = _ids(fold_cross_venue_copies(_sections())["awards"])
    assert before.index(61484982) == 0
    assert after.index(61142921) == 0


def test_production_neighbours_are_all_kept():
    sections = _sections()
    folded = fold_cross_venue_copies(sections)
    dropped = {
        name: sorted(set(_ids(sections[name])) - set(_ids(folded[name])))
        for name in sections
    }
    assert dropped == {"futures": [61156894], "awards": [61484982]}


def test_every_production_pair_the_rule_did_not_fold_is_refused_by_it():
    # Strawman: every other cross-venue pair in the banked sections really is
    # refused, not merely shadowed by an earlier fold.
    folded_pairs = {frozenset({60775226, 61156894}), frozenset({61484982, 61142921})}
    for rows in _sections().values():
        for i, a in enumerate(rows):
            for b in rows[i + 1 :]:
                expected = frozenset({a["id"], b["id"]}) in folded_pairs
                assert is_cross_venue_copy(a, b) is expected, (a["name"], b["name"])


def test_nothing_is_mutated():
    sections = _sections()
    snapshot = copy.deepcopy(sections)
    fold_cross_venue_copies(sections)
    assert sections == snapshot


# ── each gate refuses on its own ────────────────────────────────────────────


def test_the_twin_of_a_real_pair_folds():
    assert is_cross_venue_copy(
        _row(),
        _row(id=2, source="polymarket", name="2026 US Open Men's Singles Winner"),
    )


def test_one_venue_never_folds_its_own_listings():
    assert not is_cross_venue_copy(_row(), _row(id=2))


def test_a_different_canonical_key_refuses():
    assert not is_cross_venue_copy(
        _row(),
        _row(
            id=2,
            source="polymarket",
            canonical_market_key="tennis:US Open:championship:2027",
        ),
    )


def test_a_missing_canonical_key_refuses():
    assert not is_cross_venue_copy(
        _row(canonical_market_key=None),
        _row(id=2, source="polymarket", canonical_market_key=None),
    )


def test_the_group_stage_beside_the_final_refuses_on_dates():
    assert not is_cross_venue_copy(
        _row(),
        _row(id=2, source="polymarket", resolution_date="2026-09-01T20:00:00+00:00"),
    )


def test_two_stated_years_refuse():
    assert not is_cross_venue_copy(
        _row(name="2026 US Open Men's Singles Winner"),
        _row(id=2, source="polymarket", name="2027 US Open Men's Singles Winner"),
    )


def test_mens_beside_womens_refuses_even_with_a_shared_field():
    assert not is_cross_venue_copy(
        _row(),
        _row(id=2, source="polymarket", name="US Open Women's Singles Winner"),
    )


def test_a_superset_title_with_a_different_field_refuses():
    # "US Open Winner" is contained in the women's title; the field is not.
    assert not is_cross_venue_copy(
        _row(name="US Open Winner"),
        _row(
            id=2,
            source="polymarket",
            name="US Open Women's Singles Winner",
            top_outcomes=[
                {"name": n, "probability": 0.2}
                for n in ("Sabalenka", "Swiatek", "Gauff")
            ],
        ),
    )


def test_two_categories_of_one_ceremony_refuse():
    field = [{"name": n, "probability": 0.3} for n in ("Film A", "Film B", "Film C")]
    assert not is_cross_venue_copy(
        _row(name="Oscars 2027: Best Picture", top_outcomes=field),
        _row(
            id=2,
            source="polymarket",
            name="Oscars 2027: Best Cinematography",
            top_outcomes=field,
        ),
    )


def test_a_yes_no_pair_needs_the_same_two_sides():
    yes_no = [{"name": "Yes", "probability": 0.3}, {"name": "No", "probability": 0.7}]
    assert is_cross_venue_copy(
        _row(name="Will a Western team win Worlds?", top_outcomes=yes_no),
        _row(
            id=2,
            source="polymarket",
            name="Will a Western team win Worlds 2026?",
            top_outcomes=yes_no,
        ),
    )
    assert not is_cross_venue_copy(
        _row(name="Will a Western team win Worlds?", top_outcomes=yes_no),
        _row(
            id=2,
            source="polymarket",
            name="Will a Western team win Worlds 2026?",
            top_outcomes=[{"name": "Yes", "probability": 0.3}],
        ),
    )


def test_fail_open_on_missing_inputs():
    for field_name in ("source", "name", "resolution_date", "top_outcomes"):
        assert not is_cross_venue_copy(
            _row(**{field_name: None}), _row(id=2, source="polymarket")
        ), field_name
    assert not is_cross_venue_copy(
        _row(resolution_date="not a date"), _row(id=2, source="polymarket")
    )
    assert fold_cross_venue_copies({"futures": [None, "x", _row()]})["futures"] == [
        None,
        "x",
        _row(),
    ]
    assert fold_cross_venue_copies(None) == {}


def test_scoped_to_one_section():
    folded = fold_cross_venue_copies(
        {"futures": [_row()], "more_markets": [_row(id=2, source="polymarket")]}
    )
    assert _ids(folded["futures"]) == [1] and _ids(folded["more_markets"]) == [2]


# ── the route runs it, before the counts ────────────────────────────────────


def test_build_hub_folds_before_the_tier_and_the_counts():
    source = inspect.getsource(hub_route.build_hub)
    fold_at = source.index("fold_cross_venue_copies(sections)")
    assert source.index("drop_legs_of_a_rendered_field(sections)") < fold_at
    assert fold_at < source.index("resolve_entity_tier(")

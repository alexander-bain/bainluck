"""Population 4: the NFL Week 13 Monday-night game, and the sport that binds it.

lane1/115, #3070. The CREATE rail had three reviewed populations and all three were
MLB, so both of its shells hardcoded ``MLB_SPORT_ID`` at the four places the sport is
needed — resolving club anchors and stamping the created row. That was correct right
up until a population was not MLB, and then it becomes the quietest possible defect:
the plan builds, the gate passes, the apply succeeds, and one NFL game is created
under a baseball sport row with nothing downstream complaining.

So the sport moved onto the population. These tests hold the two halves of that:

* population 4 really does name NFL, and
* **populations 1-3 still name exactly what they named before** — the regression that
  would matter, because their approvals are content-addressed and a changed sport_id
  is a changed row digest, which is a changed ``plan_hash``, which is an approval
  Alex gave for an object that no longer exists.

The club-anchor half is measured, not assumed: within ``sport_id = 1`` each of the two
clubs this game needs resolves to exactly one ``teams`` row (Dallas Cowboys 552,
Seattle Seahawks 12), while both also carry a preseason row under sport 190411. The
anchor is 1:1 *because* the resolution is sport-scoped — which is precisely why the
sport cannot be a default parameter a shell forgets to pass.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.utils.event_create_derivation import (
    MLB_SPORT_ID,
    NFL_SPORT_ID,
    TRUTH_SET_REGISTRY,
    DerivationRefused,
    build_rows,
    load_games,
    parse_label,
    registry_entry_for,
    select_population,
    sport_for,
    truth_set_path_for,
)

DATA = Path(__file__).resolve().parents[1] / "app" / "data"
MNF_TRUTH_ID = "401873108"


def _truth() -> dict:
    return json.loads((DATA / "event_create_truth_set_nfl_week13_mnf.json").read_text())


# ── the reviewed object ────────────────────────────────────────────────────


def test_the_reviewed_file_is_committed_and_the_registry_points_at_it():
    """A rail that cannot read its own reviewed population cannot be attended."""
    assert truth_set_path_for("4") == (
        "app/data/event_create_truth_set_nfl_week13_mnf.json"
    )
    assert (DATA / "event_create_truth_set_nfl_week13_mnf.json").exists()


def test_population_4_is_its_own_object_and_not_a_slice_of_an_mlb_one():
    """Ruling 079's shape: a new population is a new file, not a widened constant."""
    truth = _truth()
    for other in ("1", "2", "3"):
        assert TRUTH_SET_REGISTRY["4"].path != TRUTH_SET_REGISTRY[other].path
    season = json.loads((DATA / "event_create_truth_set.json").read_text())
    aug19 = json.loads((DATA / "event_create_truth_set_aug19.json").read_text())
    assert set(truth["truth_ids"]).isdisjoint(set(season["truth_ids"]))
    assert set(truth["truth_ids"]).isdisjoint(set(aug19["truth_ids"]))


def test_the_reviewed_set_is_exactly_the_one_game_espn_attested():
    """ESPN summary?event=401873108, read 2026-09-04: DAL @ SEA, 2026-12-08T01:15Z."""
    truth = _truth()
    assert truth["truth_ids"] == [MNF_TRUTH_ID]
    assert truth["id_count"] == len(truth["truth_ids"])
    assert truth["row_one"] == MNF_TRUTH_ID
    (game,) = truth["games"]
    assert game["espn_id"] == MNF_TRUTH_ID
    assert game["commence"] == "2026-12-08T01:15:00+00:00"
    away, home = parse_label(game["label"])
    assert (away, home) == ("Dallas Cowboys", "Seattle Seahawks")


def test_the_truth_id_hash_matches_its_own_declared_formula():
    """The stamp is checkable, which the three older sets' stamps are not.

    Nothing in the rail verifies ``truth_id_hash`` — it is carried into plan context
    as provenance and never recomputed. That makes it a field which can rot to a
    number that means nothing, so this set declares the formulation it used and this
    test recomputes it. The older files are deliberately left alone: recomputing a
    stamp on a reviewed object is changing the object.
    """
    truth = _truth()
    assert truth["truth_id_hash_formula"] == "md5('\\n'.join(sorted(truth_ids)))"
    expected = hashlib.md5("\n".join(sorted(truth["truth_ids"])).encode()).hexdigest()
    assert truth["truth_id_hash"] == expected


# ── the sport is a property of the population ──────────────────────────────


def test_population_4_names_nfl():
    assert sport_for("4") == (NFL_SPORT_ID, "americanfootball_nfl")
    assert NFL_SPORT_ID == 1


@pytest.mark.parametrize("population", ["1", "2", "3"])
def test_the_mlb_populations_still_name_mlb(population):
    """The regression that would matter.

    ``sport_id`` is inside the create digest (queue 368), so moving one of these
    would re-address every row in an approval Alex already gave — he would present a
    ``plan_hash`` the rail no longer mints and be refused, with nothing saying why.
    """
    assert sport_for(population) == (MLB_SPORT_ID, "baseball_mlb")
    assert MLB_SPORT_ID == 53232


def test_an_unknown_population_is_refused_by_name_not_defaulted():
    """The failure mode this replaces is a silent default, so it must not default."""
    with pytest.raises(DerivationRefused) as excinfo:
        sport_for("99")
    assert excinfo.value.code == "UNKNOWN_POPULATION"
    assert "99" in excinfo.value.message

    with pytest.raises(DerivationRefused):
        registry_entry_for("nfl")


def test_every_registered_population_declares_a_sport():
    """A population added later cannot inherit MLB by omission — there is no default."""
    for token, entry in TRUTH_SET_REGISTRY.items():
        assert isinstance(entry.sport_id, int) and entry.sport_id > 0, token
        assert entry.sport_key, token
        assert sport_for(token) == (entry.sport_id, entry.sport_key)


def test_the_registry_is_still_readable_positionally():
    """Tests predating the sport fields index ``entry[0]`` / ``entry[1]``."""
    for token, entry in TRUTH_SET_REGISTRY.items():
        assert entry[0] == entry.path, token
        assert entry[1] == entry.subset, token


# ── the row the plan will actually build ───────────────────────────────────


def test_the_planned_row_carries_nfls_sport_id_not_mlbs():
    """The load-bearing assertion: the created game is bound to the NFL sport row.

    Anchors are handed in already-resolved (the shells resolve them against ``teams``
    scoped by this same sport_id and refuse anything not 1:1); the ids here are the
    ones measured on production 2026-09-04.
    """
    truth = _truth()
    games = load_games(truth)
    wanted = select_population(truth, "4")
    sport_id, _ = sport_for("4")
    rows = build_rows(
        wanted,
        games,
        {"Dallas Cowboys": 552, "Seattle Seahawks": 12},
        sport_id=sport_id,
    )

    (row,) = rows
    assert row.sport_id == NFL_SPORT_ID
    assert row.sport_id != MLB_SPORT_ID
    assert row.truth_id == MNF_TRUTH_ID
    assert row.provider == "espn"
    assert row.home_team_id == 12 and row.home_name == "Seattle Seahawks"
    assert row.away_team_id == 552 and row.away_name == "Dallas Cowboys"
    assert row.commence_time == "2026-12-08T01:15:00+00:00"


def test_a_club_with_no_anchor_is_refused_rather_than_looked_up_another_way():
    """The poisoned path stays closed for population 4 too."""
    truth = _truth()
    games = load_games(truth)
    wanted = select_population(truth, "4")
    with pytest.raises(DerivationRefused) as excinfo:
        build_rows(wanted, games, {"Dallas Cowboys": 552}, sport_id=NFL_SPORT_ID)
    assert excinfo.value.code == "CLUB_ANCHOR_NOT_UNIQUE"
    assert "Seattle Seahawks" in excinfo.value.detail["unanchored"]

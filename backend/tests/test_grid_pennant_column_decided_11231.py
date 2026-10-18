"""#11231: a two-winner column stops expecting a winner that is already decided.

Specimen: /playoffs/mlb, Sun 2026-10-18 17:22Z, ALCS tied going to Game 5.
Kalshi KXMLBAL-26 priced Tampa Bay .57/.58 and Cleveland .42/.43, and the
stored legs agreed. The NL pennant cell had gone ``state="won"`` (no
probability), so the pennant column summed to ~1.0 against
``EXPECTED_COLUMN_SUMS["pennant"] = 2.0`` and the live AL pair was scaled x2
and capped: TB 100%, CLE 88%. The same applies to NBA/NHL ``conference``.
"""

from types import SimpleNamespace

from app.utils.playoff_grid import normalize_column_sums

PENNANT = [SimpleNamespace(key="pennant")]


def _team(name: str, prob: float | None, state: str) -> dict:
    cell: dict = {"merged_probability": prob, "state": state, "sources": []}
    if prob is not None:
        cell["sources"] = [{"source": "kalshi", "probability": prob}]
    return {"name": name, "cells": {"pennant": cell}}


def _mlb_after_nl_decided() -> list[dict]:
    return [
        _team("Tampa Bay Rays", 0.575, "live"),
        _team("Cleveland Guardians", 0.425, "live"),
        _team("Los Angeles Dodgers", None, "won"),
        _team("Milwaukee Brewers", None, "eliminated"),
        _team("New York Yankees", None, "eliminated"),
    ]


def _p(teams: list[dict], name: str) -> float:
    return next(t for t in teams if t["name"] == name)["cells"]["pennant"]["merged_probability"]


def test_live_al_pair_is_left_at_its_venue_price_once_the_nl_is_won():
    teams = _mlb_after_nl_decided()
    applied = normalize_column_sums(teams, PENNANT, "mlb")

    assert _p(teams, "Tampa Bay Rays") == 0.575
    assert _p(teams, "Cleveland Guardians") == 0.425
    assert "pennant" not in applied, "the trend chart must not be told to scale it either"


def test_sources_stay_at_the_venue_price_too():
    teams = _mlb_after_nl_decided()
    normalize_column_sums(teams, PENNANT, "mlb")
    tb = next(t for t in teams if t["name"] == "Tampa Bay Rays")
    assert tb["cells"]["pennant"]["sources"][0]["probability"] == 0.575


def test_the_remaining_column_is_still_normalized_against_one_winner():
    # An undershooting AL pair (long tail floored away) scales to ONE, not two.
    teams = _mlb_after_nl_decided()
    teams[0]["cells"]["pennant"]["merged_probability"] = 0.40
    teams[1]["cells"]["pennant"]["merged_probability"] = 0.30
    applied = normalize_column_sums(teams, PENNANT, "mlb")

    assert abs(_p(teams, "Tampa Bay Rays") + _p(teams, "Cleveland Guardians") - 1.0) < 0.001
    assert abs(applied["pennant"] - 1.0 / 0.70) < 1e-9


def test_conference_column_reads_the_same_rule():
    cols = [SimpleNamespace(key="conference")]
    teams = [
        {"name": "Celtics", "cells": {"conference": {"merged_probability": 0.62, "state": "live", "sources": []}}},
        {"name": "Knicks", "cells": {"conference": {"merged_probability": 0.38, "state": "live", "sources": []}}},
        {"name": "Thunder", "cells": {"conference": {"merged_probability": None, "state": "won", "sources": []}}},
    ]
    normalize_column_sums(teams, cols, "nba")
    assert [t["cells"]["conference"]["merged_probability"] for t in teams[:2]] == [0.62, 0.38]


def test_a_won_cell_that_still_carries_its_price_is_not_counted_twice():
    # If a won cell keeps 1.0 it is already in the sum; the expectation stays 2.0.
    teams = _mlb_after_nl_decided()
    teams[2]["cells"]["pennant"]["merged_probability"] = 1.0
    normalize_column_sums(teams, PENNANT, "mlb")
    assert _p(teams, "Tampa Bay Rays") == 0.575


def test_both_pennants_decided_touches_nothing():
    teams = [_team("A", None, "won"), _team("B", None, "won"), _team("C", None, "eliminated")]
    assert normalize_column_sums(teams, PENNANT, "mlb") == {}


def test_before_either_pennant_is_decided_the_column_still_expects_two():
    teams = [
        _team("TB", 0.30, "live"), _team("CLE", 0.20, "live"),
        _team("LAD", 0.30, "live"), _team("MIL", 0.20, "live"),
    ]
    normalize_column_sums(teams, PENNANT, "mlb")
    total = sum(t["cells"]["pennant"]["merged_probability"] for t in teams)
    assert abs(total - 2.0) < 0.001

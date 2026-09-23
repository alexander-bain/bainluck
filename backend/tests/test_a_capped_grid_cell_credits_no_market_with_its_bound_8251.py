"""#8251 — a capped grid cell must not credit a market with a number it never quoted.

`enforce_monotonicity` caps a round at the round a team must already have come
through: the CFP `semifinal` column is capped at `make_playoffs`. The cap is
sound. What it used to do to `sources` was not: it clamped every source above
the bound down to it, so the row a reader taps printed

    College Football Playoff Semifinals Qualifiers  ·  kalshi  ·  12.75%

while that market quoted 18%. Measured 2026-09-23: 30 capped cells on four
grids, 15 of them CFP semifinal and 11 men's college basketball bracket rounds.

The contract now: the merged number is capped, every source keeps its market's
quote, and the cell says it was capped (`capped_by` = the bound column's key).

Specimens are production's own (served / stored, 21:25Z), on the real config.
"""
import copy

from app.config.league_configs import NCAA_FOOTBALL_CONFIG
from app.utils.playoff_grid import enforce_monotonicity

SEMI_MARKET = "College Football Playoff Semifinals Qualifiers"


def _team(name, make, semi):
    return {
        "name": name,
        "cells": {
            "make_playoffs": {
                "merged_probability": make,
                "state": "live",
                "sources": [{"source": "kalshi", "probability": make,
                             "market_name": "College Football Playoff Qualifiers"}],
            },
            "semifinal": {
                "merged_probability": semi,
                "state": "live",
                "sources": [{"source": "kalshi", "probability": semi,
                             "market_name": SEMI_MARKET}],
            },
        },
    }


def test_missouri_semifinal_is_capped_but_the_market_keeps_its_quote():
    missouri = _team("Missouri Tigers", make=0.1275, semi=0.18)
    fixes = enforce_monotonicity([missouri], NCAA_FOOTBALL_CONFIG.columns)

    semi = missouri["cells"]["semifinal"]
    assert fixes == 1
    assert semi["merged_probability"] == 0.1275        # the cap still holds
    assert semi["sources"][0]["probability"] == 0.18   # what KXNCAAFSF-27 says
    assert semi["sources"][0]["market_name"] == SEMI_MARKET
    assert semi["capped_by"] == "make_playoffs"


def test_an_uncapped_cell_is_byte_identical_and_carries_no_marker():
    """Control: Texas's semifinal (0.48) sits under its make-playoffs number and
    must come through untouched — the change reaches only capped cells."""
    texas = _team("Texas Longhorns", make=0.80, semi=0.48)
    before = copy.deepcopy(texas)
    fixes = enforce_monotonicity([texas], NCAA_FOOTBALL_CONFIG.columns)
    assert fixes == 0
    assert texas == before


def test_a_genuine_tie_is_not_a_cap():
    """Virginia served 0.09 in both columns on 9/23 because the market really
    quotes 0.09 — equality alone must not stamp the marker."""
    virginia = _team("Virginia Cavaliers", make=0.09, semi=0.09)
    enforce_monotonicity([virginia], NCAA_FOOTBALL_CONFIG.columns)
    assert "capped_by" not in virginia["cells"]["semifinal"]


def test_the_second_pass_after_normalization_leaves_the_same_answer():
    """The route runs the cap twice (cell build, then after normalization). The
    second pass must neither re-clamp the sources nor drop the marker."""
    missouri = _team("Missouri Tigers", make=0.1275, semi=0.18)
    enforce_monotonicity([missouri], NCAA_FOOTBALL_CONFIG.columns)
    once = copy.deepcopy(missouri)
    assert enforce_monotonicity([missouri], NCAA_FOOTBALL_CONFIG.columns) == 0
    assert missouri == once

"""#9713 — a box score with an infinite ERA is still a box Postgres will store.

ESPN prints a pitcher's ERA as ``INF`` when he has allowed an earned run
without recording an out. ``float("INF")`` accepts that, ``json.dumps`` writes
``Infinity``, and Postgres refuses the whole box as invalid JSON (22P02).
Production, 9/30: Red Sox at Yankees (15319563) lost every box write from 01:59Z
on (``Box score fetch error for event 15319563 … invalid input syntax for type
json``), so its line score stayed at NYY 2 through a 9–0 final.

* ship: the parsed box serialises as strict JSON, and the pitcher keeps his
  finite stats. RED on the parent (``'era': inf``);
* control: finite values, including a real 0.00 ERA and a negative number, still
  parse. A parser that refused every ERA would pass the ship alone.
"""

import copy
import json

import pytest

from app.services.espn_api import ESPNAPIService
from tests.test_espn_boxscore_group_aware import MLB_PITCHING, _mlb_summary


@pytest.fixture
def svc():
    return ESPNAPIService.__new__(ESPNAPIService)


def _summary_with_pitching_line(stats):
    summary = _mlb_summary()
    pitching = copy.deepcopy(MLB_PITCHING)
    pitching["athletes"][0]["stats"] = stats
    summary["boxscore"]["players"][0]["statistics"][1] = pitching
    return summary


# IP, H, R, ER, BB, K, HR, PC-ST, ERA, PC: two earned runs, no outs recorded.
_NO_OUT_LINE = ["0.0", "2", "2", "2", "1", "0", "0", "11-5", "INF", "11"]


def test_an_infinite_era_leaves_a_box_postgres_will_take(svc):
    box = svc._parse_boxscore(_summary_with_pitching_line(_NO_OUT_LINE))

    # `allow_nan=False` is JSON as Postgres reads it: Infinity/NaN raise.
    json.dumps(box, allow_nan=False)
    assert "era" not in box["Shane Baz"], box["Shane Baz"]
    assert box["Shane Baz"]["earned runs"] == 2.0
    assert box["Shane Baz"]["pitch count"] == 11.0


@pytest.mark.parametrize("raw", ["INF", "inf", "-INF", "Infinity", "NaN", "nan"])
def test_a_non_finite_stat_is_dropped_like_a_dash(svc, raw):
    assert svc._parse_stat_value(raw) is None


@pytest.mark.parametrize(
    "raw, expected",
    [("0.00", 0.0), ("4.02", 4.02), ("27.00", 27.0), ("-1", -1.0), ("104-69", 104.0)],
)
def test_finite_values_still_parse(svc, raw, expected):
    assert svc._parse_stat_value(raw) == expected


def test_a_finite_era_is_kept(svc):
    line = list(_NO_OUT_LINE)
    line[0], line[8] = "0.1", "54.00"
    box = svc._parse_boxscore(_summary_with_pitching_line(line))
    assert box["Shane Baz"]["era"] == 54.0

"""#6909, the bucket arm — four football stat words the classifier had never heard of.

Polymarket quotes an NFL player prop as "<Player>: <Stat> O/U <line>". The
structural test in `_is_player_prop_ou_market` is right, but its stat vocabulary
had no "receptions", "completions", "attempts" or "longest reception", so every
one of those names fell past the player branch into `game_total` — the game's
combined POINTS. Measured on production 2026-09-28 (NFL, last 21 days): 446 +
37 + 34 + 25 markets across 30 events; no other sport uses the words.

What a reader got, on the same pages:

* **A quarterback's line on the points ladder.** Lines inside football's 15-120
  band stayed there: `Bo Nix: Passing Attempts O/U 35.5` was a 35.5-point total
  rung on Broncos-Rams (`/api/events/14780548/game-markets`); Cowboys-Ravens
  carried five such rungs; the Saints-Raiders final below carried three.
* **A receiver's line nowhere, then as a bare Won/Lost.** Every receptions line
  sits below the band, so before kick-off the range guard deleted it — Monday
  night's 18 receptions lines reached no section — and after the final #6769
  rescued it to `other[]`, where it printed Won/Lost with no stat line even
  though the grader already maps "receptions", "passing completions" and
  "longest reception" to box-score keys (`test_nfl_polymarket_ou_prop_grading_6909`).

The census runs the REAL grader over the 83 Polymarket rows the Saints 27 -
Raiders 35 final (event 14782707) served in `other[]`/`totals[]` under those
four names, against that game's real box score: 73 now carry a verdict and 0 of
them disagree with the row's own stored settlement. The 10 that stay ungraded
are named below — passing attempts has no box-score key, and Jack Bech has no
box-score line.

THE CONTROL ARM. A matchup-subject O/U, NCAAF's team-subject "Utah State Total
Receptions: O/U 19.5" (stat in the subject, nothing between colon and line — a
different shape and a different fix), a team-subject yards total, and a bare
"Receptions" with no O/U line all keep their bucket.
"""

import collections
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.events import (
    _build_prop_grade_context,
    _classify_game_market,
    _extract_threshold,
    _game_markets_cache,
    _grade_settled_prop,
    _is_player_prop_ou_market,
    get_game_markets,
)

FIXTURES = Path(__file__).parent / "fixtures"
BUCKETS = FIXTURES / "event_nfl_polymarket_football_ou_buckets_6909.json"
BOX = FIXTURES / "event_nfl_polymarket_ou_props_6909.json"


# ------------------------------------------------------------ the classifier --

# Verbatim from production payloads, 2026-09-28.
PRODUCTION_NAMES = [
    "Ashton Jeanty: Receptions O/U 2.5",  # 14782707, other[]
    "Kirk Cousins: Passing Completions O/U 7.5",  # 14782707, other[]
    "Tyler Shough: Passing Completions O/U 21.5",  # 14782707, totals[] rung
    "Juwan Johnson: Longest Reception O/U 19.5",  # 14782707, totals[] rung
    "Bo Nix: Passing Attempts O/U 35.5",  # 14780548, totals[] rung
    "Jalen Hurts: Passing Attempts O/U 27.5",  # 14780549, absent pre-game
    "D'Andre Swift: Receptions O/U 3.5",  # 14780549, absent pre-game
    "Travis Etienne Jr.: Receptions O/U 1.5",  # suffix + period in the subject
]


@pytest.mark.parametrize("name", PRODUCTION_NAMES)
def test_the_production_names_are_player_props(name):
    assert _is_player_prop_ou_market(name) is True
    assert _classify_game_market(name) == "player_prop"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Raiders vs. Saints: O/U 24.5", "game_total"),
        ("Bears vs. Eagles: Receptions O/U 45.5", "game_total"),
        ("Utah State Total Receptions: O/U 19.5", "game_total"),
        ("Saints Total Offensive Yards: O/U 350.5", "game_total"),
        ("Tyler Shough: Passing Yards O/U 149.5", "player_prop"),
    ],
    ids=["matchup-ou", "matchup-subject-stat", "ncaaf-team-subject",
         "team-yards", "already-a-prop"],
)
def test_nothing_else_moves(name, expected):
    assert _classify_game_market(name) == expected


# ------------------------------------------------- the specimen, re-graded --


class _Obj:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture(scope="module")
def captured():
    return json.loads(BUCKETS.read_text())


@pytest.fixture(scope="module")
def ctx():
    players = json.loads(BOX.read_text())["box_score_players"]
    built = _build_prop_grade_context(_Obj(box_score_data={"players": players}))
    assert built is not None
    return built


def _grade(ctx, row):
    return _grade_settled_prop(
        True,
        ctx,
        _Obj(external_id="0x6909", name=row["market_name"]),
        _Obj(
            name=row["outcome_name"],
            is_winner=row["is_winner"],
            resolution_source=row["resolution_source"],
            current_probability=None,
        ),
        _extract_threshold(row["market_name"]),
        row["outcome_name"].lower().startswith("under"),
    )


def test_the_captured_payload_still_carries_the_defect(captured):
    """The fixture is the BEFORE: 80 rows in other[], 3 prop rungs on totals[]."""
    rows = captured["rows"]
    assert collections.Counter(r["served_in"] for r in rows) == {"other": 80, "totals": 3}
    rungs = sorted(r["market_name"] for r in rows if r["served_in"] == "totals")
    assert rungs == [
        "Juwan Johnson: Longest Reception O/U 19.5",
        "Tyler Shough: Passing Completions O/U 17.5",
        "Tyler Shough: Passing Completions O/U 21.5",
    ]


def test_every_captured_row_now_classifies_as_a_player_prop(captured):
    assert {_classify_game_market(r["market_name"]) for r in captured["rows"]} == {
        "player_prop"
    }


def test_every_new_verdict_agrees_with_the_rows_own_settlement(captured, ctx):
    graded, disagree = collections.Counter(), []
    for row in captured["rows"]:
        g = _grade(ctx, row)
        if g["hit"] is None:
            continue
        graded[row["market_name"].split(":")[1].split(" O/U")[0].strip()] += 1
        if g["hit"] is not row["is_winner"]:
            disagree.append((row["market_name"], row["outcome_name"], g["actual"]))
    assert disagree == []
    assert dict(graded) == {
        "Receptions": 64,
        "Passing Completions": 8,
        "Longest Reception": 1,
    }


def test_the_specimen_rows_read_the_players_line(captured, ctx):
    seen = {
        (r["market_name"], r["outcome_name"]): _grade(ctx, r)
        for r in captured["rows"]
    }
    jeanty_over = seen[("Ashton Jeanty: Receptions O/U 2.5", "Over")]
    assert (jeanty_over["actual"], jeanty_over["hit"]) == (3.0, True)
    jeanty_under = seen[("Ashton Jeanty: Receptions O/U 3.5", "Under")]
    assert (jeanty_under["actual"], jeanty_under["hit"]) == (3.0, True)
    cousins = seen[("Kirk Cousins: Passing Completions O/U 7.5", "Over")]
    assert (cousins["actual"], cousins["hit"]) == (22.0, True)


def test_every_row_still_ungraded_is_accounted_for(captured, ctx):
    buckets = collections.Counter()
    for row in captured["rows"]:
        g = _grade(ctx, row)
        if g["hit"] is not None:
            continue
        name = row["market_name"]
        if "Passing Attempts" in name:
            buckets["passing attempts, no box-score key"] += 1
        elif name.startswith("Jack Bech:"):
            assert g["actual"] is None
            buckets["player absent from the box score"] += 1
        else:
            buckets["UNCLASSIFIED"] += 1
    assert dict(buckets) == {
        "passing attempts, no box-score key": 6,
        "player absent from the box score": 4,
    }


# ------------------------------------------------ the endpoint, pre-game --


def _make_result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _make_event():
    event = MagicMock()
    event.id = 14780549
    event.home_team_name = "Chicago Bears"
    event.away_team_name = "Philadelphia Eagles"
    event.status = "scheduled"
    event.sport_id = None
    event.sport = MagicMock()
    event.sport.key = "americanfootball_nfl"
    event.commence_time = datetime(2026, 9, 29, 0, 15, tzinfo=timezone.utc)
    event.home_score = None
    event.away_score = None
    event.period = None
    event.game_clock = None
    event.box_score_data = None
    return event


def _make_market(*, id, name, event_id):
    market = MagicMock()
    market.id = id
    market.name = name
    market.external_id = f"0x{id:064x}"
    market.event_id = event_id
    market.category = "game_prop"
    market.status = "open"
    market.source = "polymarket"
    market.sport_id = None
    market.llm_sport_category = "football"
    market.commence_time = datetime(2026, 9, 29, 0, 15, tzinfo=timezone.utc)
    market.group_id = None
    market.group_type = None
    return market


def _make_outcome(*, id, market_id, name, probability):
    outcome = MagicMock()
    outcome.id = id
    outcome.market_id = market_id
    outcome.name = name
    outcome.current_probability = probability
    outcome.opening_probability = None
    outcome.resolution_source = None
    outcome.is_winner = None
    return outcome


def _payload_for(rows):
    event = _make_event()
    markets, outcomes = [], []
    for i, (name, outcome_name, prob) in enumerate(rows, start=1):
        markets.append(_make_market(id=1000 + i, name=name, event_id=event.id))
        outcomes.append(
            _make_outcome(id=2000 + i, market_id=1000 + i, name=outcome_name,
                          probability=prob)
        )
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar=event),
            _make_result(rows=[]),  # folded_event_ids (#2693)
            _make_result(rows=markets),
            _make_result(all_rows=[]),  # polymarket parent groups
            _make_result(rows=[]),  # unlinked fallback
            _make_result(rows=outcomes),
            _make_result(all_rows=[]),  # load_latest_observed_at (#4970)
        ]
    )
    return get_game_markets(event.id, db)


@pytest.fixture(autouse=True)
def clear_game_markets_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


GAME_RUNGS = [
    ("Eagles vs. Bears: O/U 41.5", "Over", 0.66),
    ("Eagles vs. Bears: O/U 45.5", "Over", 0.5),
    ("Eagles vs. Bears: O/U 49.5", "Over", 0.34),
]
PROPS = [
    ("Jalen Hurts: Passing Attempts O/U 27.5", "Over", 0.52),
    ("Jalen Hurts: Passing Completions O/U 19.5", "Over", 0.5),
    ("DeVonta Smith: Longest Reception O/U 19.5", "Over", 0.48),
    ("D'Andre Swift: Receptions O/U 3.5", "Over", 0.45),
]


@pytest.mark.asyncio
async def test_the_points_ladder_is_built_from_the_game_only():
    payload = await _payload_for(GAME_RUNGS + PROPS)
    assert sorted(t["threshold"] for t in payload["totals"]) == [41.5, 45.5, 49.5]


@pytest.mark.asyncio
async def test_every_prop_line_reaches_the_props_section():
    payload = await _payload_for(GAME_RUNGS + PROPS)
    served = {(p["market_name"], p["threshold"]) for p in payload["player_props"]}
    assert served == {
        ("Jalen Hurts: Passing Attempts O/U 27.5", 27.5),
        ("Jalen Hurts: Passing Completions O/U 19.5", 19.5),
        ("DeVonta Smith: Longest Reception O/U 19.5", 19.5),
        ("D'Andre Swift: Receptions O/U 3.5", 3.5),
    }
    assert not any("O/U" in o["market_name"] for o in payload["other"])

"""#10237 — a finished MLB box keeps each athlete's ESPN id and team, beside
the numbers.

SHIP (TRUTH / FORMATTING): After player props print an MLB batter's official
final count only once his name in the box resolves to ONE ESPN athlete on ONE
of this game's teams. The After reader (`prop_expectation_actual._box_identity`)
reads that from `box_score_data.player_identities`, which until now was
written for NFL only (#10103). This widens the stored side to MLB and nothing
else; the reader decides uniqueness and refuses anything shared or missing.

ORDER: the reader lands before, or atomically with, this file. Identities
stored with no reader change nothing a person sees; a reader with no
identities answers `unknown`. Never the other way round.

FIXTURE. `espn_summary_mlb_401907985_yankees_at_rays_10237.json` is ESPN's own
summary of a finished game (Yankees @ Rays, STATUS_FINAL, completed), raw
bytes sha256 d07bc129…, the same file authority's reader tests read. Every
"derived" case below edits a deep copy of it; nothing is hand-built.

The NFL half is pinned by `test_nfl_prop_subject_provider_bridge_9483.py`,
which this file reuses and does not edit.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_nfl_prop_subject_provider_bridge_9483 import (
    _backfill_write,
    _box_event,
    _live_write,
    _settled_write,
)

FIXTURES = Path(__file__).parent / "fixtures"
SUMMARY = json.loads(
    (FIXTURES / "espn_summary_mlb_401907985_yankees_at_rays_10237.json").read_text()
)
MLB = "baseball_mlb"
ESPN_EVENT_ID = "401907985"
RAYS, YANKEES = "30", "10"                     # ESPN team ids, header home / away
HEADSHOT = "https://a.espncdn.com/i/headshots/mlb/players/full/{}.png"

# Source-retained (name, athlete id, team id, side), read off the fixture.
RICE = ("Ben Rice", "5016968", YANKEES, "away")          # batter
COLE = ("Gerrit Cole", "32081", YANKEES, "away")         # pitcher
DIAZ = ("Yandy Diaz", "33481", RAYS, "home")             # batter
RASMUSSEN = ("Drew Rasmussen", "42584", RAYS, "home")    # pitcher
ATHLETES_IN_BOX = 27


def _summary():
    return copy.deepcopy(SUMMARY)


async def _context(sport_key=MLB, summary=None):
    """The real `get_event_context` over the fixture."""
    from app.services.espn_api import ESPNAPIService

    svc = ESPNAPIService()
    try:
        with patch.object(svc, "_get", AsyncMock(return_value=summary or _summary())):
            return await svc.get_event_context(sport_key, ESPN_EVENT_ID)
    finally:
        await svc.close()


def _athlete_entries(summary, athlete_id):
    """Every box entry ESPN wrote for one athlete, across all stat groups."""
    return [
        a
        for team_group in summary["boxscore"]["players"]
        for stat_group in team_group["statistics"]
        for a in stat_group["athletes"]
        if a["athlete"]["id"] == athlete_id
    ]


def _stat_group(summary, team_id, kind):
    for team_group in summary["boxscore"]["players"]:
        if team_group["team"]["id"] == team_id:
            for stat_group in team_group["statistics"]:
                if stat_group["type"] == kind:
                    return stat_group
    raise AssertionError(f"no {kind} group for team {team_id}")


def _stored(ctx):
    """The box exactly as the writers store it (see the writer test below)."""
    return {
        "source": "espn",
        "players": ctx["box_score"],
        "player_identities": ctx["box_score_player_identities"],
    }


def _after_reader_box_identity():
    """The After reader's own uniqueness rule. Skips only until #10416 lands —
    which by the ORDER above is before this file reaches master."""
    module = pytest.importorskip("app.utils.prop_expectation_actual")
    from app.utils.event_props_matrix import normalize_subject

    return lambda box, name: module._box_identity(box, normalize_subject(name))


# ═══════════════════════════════════════════════════════════════════════════
# 1. The finished MLB box keeps who played, for which team, by ESPN id
# ═══════════════════════════════════════════════════════════════════════════


def test_the_fixture_is_espns_finished_game_not_a_hand_built_one():
    comp = SUMMARY["header"]["competitions"][0]
    assert SUMMARY["header"]["id"] == comp["id"] == ESPN_EVENT_ID
    assert comp["status"]["type"]["name"] == "STATUS_FINAL"
    assert comp["status"]["type"]["completed"] is True
    sides = {c["team"]["id"]: c["homeAway"] for c in comp["competitors"]}
    assert sides == {RAYS: "home", YANKEES: "away"}


@pytest.mark.asyncio
async def test_the_mlb_context_keeps_each_batter_and_pitchers_game_identity():
    ctx = await _context()
    ids = ctx["box_score_player_identities"]
    by_name = {e["name"]: e for e in ids}
    for name, athlete_id, team_id, side in (RICE, COLE, DIAZ, RASMUSSEN):
        assert by_name[name] == {
            "name": name,
            "athlete_id": athlete_id,
            "team_id": team_id,
            "side": side,
            "headshot": HEADSHOT.format(athlete_id),
        }
    assert len(ids) == len({(e["athlete_id"], e["team_id"]) for e in ids}) == ATHLETES_IN_BOX
    # Every athlete in the numeric box has exactly one identity, and no more.
    assert {e["name"] for e in ids} == set(ctx["box_score"])


@pytest.mark.asyncio
async def test_STATS_SHAPE_CONTROL_the_numeric_box_and_every_other_key_are_unchanged():
    """The widening adds ONE sibling key. Everything else the context returns
    for this MLB game is byte-identical to what it returned before."""
    from app.services import espn_api

    ctx = await _context()
    with patch.object(espn_api, "BOX_SCORE_IDENTITY_SPORTS", frozenset({"americanfootball_nfl"})):
        before = await _context()
    assert before["box_score_player_identities"] == []
    assert ctx["box_score_player_identities"] != []
    for key in set(ctx) | set(before):
        if key in ("box_score_player_identities", "injuries", "news"):
            continue
        assert json.dumps(ctx[key], sort_keys=True, default=str) == json.dumps(
            before[key], sort_keys=True, default=str
        ), key
    assert ctx["box_score"] == espn_api.ESPNAPIService()._parse_boxscore(_summary())
    rice = ctx["box_score"][RICE[0]]
    assert not {"athlete_id", "team_id", "headshot", "side"} & set(rice)


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", [_settled_write, _live_write, _backfill_write])
async def test_every_box_writer_stores_mlb_identities_beside_identical_numbers(writer):
    ctx = await _context()
    if writer is _settled_write:
        stored = await writer(ctx, event=_box_event("completed", sport_key=MLB))
    else:
        stored = await writer(ctx)
    assert stored["player_identities"] == ctx["box_score_player_identities"]
    assert stored["players"] == ctx["box_score"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. Derived from the real box: repeats, shared names, missing ids
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_an_athlete_listed_in_batting_and_pitching_is_one_identity():
    """A two-way player, or a pitcher who also bats, appears in both groups —
    and twice in one group after a substitution. He is still one athlete."""
    s = _summary()
    (cole,) = _athlete_entries(s, COLE[1])
    batting = _stat_group(s, YANKEES, "batting")
    batting["athletes"].append(copy.deepcopy(cole))
    batting["athletes"].append(copy.deepcopy(cole))
    ctx = await _context(summary=s)
    ids = ctx["box_score_player_identities"]
    assert [e for e in ids if e["name"] == COLE[0]] == [{
        "name": COLE[0], "athlete_id": COLE[1], "team_id": YANKEES,
        "side": "away", "headshot": HEADSHOT.format(COLE[1]),
    }]
    assert len(ids) == ATHLETES_IN_BOX


@pytest.mark.asyncio
async def test_DUPLICATE_CONTROL_two_teams_sharing_a_name_stay_two_and_the_reader_refuses():
    """A Ray who shares a Yankee's display name is NOT merged into him: both
    identities are kept, so the reader sees two and refuses the name."""
    s = _summary()
    for entry in _athlete_entries(s, DIAZ[1]):
        entry["athlete"]["displayName"] = RICE[0]
    ctx = await _context(summary=s)
    shared = sorted(
        (e["athlete_id"], e["team_id"], e["side"])
        for e in ctx["box_score_player_identities"]
        if e["name"] == RICE[0]
    )
    assert shared == sorted([(RICE[1], YANKEES, "away"), (DIAZ[1], RAYS, "home")])

    from app.routes.events import _game_player_identity_index

    index = _game_player_identity_index(_stored(ctx), RAYS, YANKEES)
    assert RICE[0].casefold() not in index
    assert index[COLE[0].casefold()]["athlete_id"] == COLE[1]

    box_identity = _after_reader_box_identity()
    assert box_identity(_stored(ctx), RICE[0]) == {"reason": "ambiguous_player"}
    assert box_identity(_stored(ctx), COLE[0])["athlete_id"] == COLE[1]


@pytest.mark.asyncio
async def test_MISSING_CONTROL_an_athlete_without_an_id_is_never_given_one():
    """ESPN omits a batter's id: his numbers stay, his identity is absent, and
    no other athlete's id is borrowed for him."""
    s = _summary()
    for entry in _athlete_entries(s, RICE[1]):
        del entry["athlete"]["id"]
    ctx = await _context(summary=s)
    ids = ctx["box_score_player_identities"]
    assert RICE[0] in ctx["box_score"]
    assert [e for e in ids if e["name"] == RICE[0]] == []
    assert RICE[1] not in {e["athlete_id"] for e in ids}
    assert len(ids) == ATHLETES_IN_BOX - 1

    box_identity = _after_reader_box_identity()
    assert box_identity(_stored(ctx), RICE[0]) == {"reason": "player_not_in_box"}


@pytest.mark.asyncio
async def test_MISSING_CONTROL_a_team_group_without_a_team_id_is_never_guessed():
    s = _summary()
    for team_group in s["boxscore"]["players"]:
        if team_group["team"]["id"] == RAYS:
            del team_group["team"]["id"]
    ctx = await _context(summary=s)
    ids = ctx["box_score_player_identities"]
    assert ids and {e["team_id"] for e in ids} == {YANKEES}
    assert DIAZ[0] in ctx["box_score"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. Scope: NFL and MLB only, keyed on the sport, not on the box's content
# ═══════════════════════════════════════════════════════════════════════════


def test_the_stored_set_is_exactly_nfl_and_mlb_and_the_page_bridge_stays_nfl():
    from app.routes.events import _PROP_IDENTITY_SPORT
    from app.services.espn_api import BOX_SCORE_IDENTITY_SPORTS

    assert BOX_SCORE_IDENTITY_SPORTS == frozenset({"americanfootball_nfl", MLB})
    # The /game-markets roster bridge (#10103) is not widened by this change.
    assert _PROP_IDENTITY_SPORT == "americanfootball_nfl"


@pytest.mark.asyncio
@pytest.mark.parametrize("sport_key", ["basketball_nba", "icehockey_nhl"])
async def test_EXCLUDED_CONTROL_nba_and_nhl_store_no_identities_even_from_this_box(sport_key):
    ctx = await _context(sport_key=sport_key)
    assert ctx["box_score_player_identities"] == []
    assert ctx["box_score"]  # the numbers are still parsed; only identities are gated


# ═══════════════════════════════════════════════════════════════════════════
# 4. THE SHIP, composed with the After reader: identities unlock the actual
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_THE_SHIP_the_real_box_now_answers_the_official_final_count():
    """Through the real writer and the real After reader: Ben Rice went 0-for
    (below 1+ hits) and Jonathan Aranda homered (reached 1+ HR), each tied to
    the ESPN athlete and team that played in THIS game."""
    pytest.importorskip("app.utils.prop_expectation_actual")
    from tests import test_prop_expectation_actual_10237 as reader_tests

    ctx = await _context()
    box = await reader_tests._real_stored_box(ctx)
    rows = [
        reader_tests._row(71, 7, "Ben Rice: 1+", market_name="New York at Tampa Bay: Hits"),
        reader_tests._row(72, 8, "Jonathan Aranda: 1+", market_name="New York at Tampa Bay: Home Runs"),
    ]
    payload = reader_tests._real_build(box, rows)
    got = [
        (a["state"], a["reason"], a["value"], a["athlete_id"], a["team_id"], a["stat_key"])
        for a in payload["actuals"]
    ]
    assert got == [
        ("final", None, 0, RICE[1], YANKEES, "hits"),
        ("final", None, 1, "40810", RAYS, "home_runs"),
    ]
    assert [q["comparison"]["state"] for q in payload["questions"]] == ["below", "reached"]

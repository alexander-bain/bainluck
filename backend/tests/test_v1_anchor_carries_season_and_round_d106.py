"""A StatPal anchor records which season and round the fixture belongs to.

D106 rule from `docs/fixture-identity-contract-d106.md` §2. The identity half of
"real fixture identity": a provider id says *which fixture*, but not *which
competition, which season, which round* — and without those, two meetings of the
same pair in different seasons are the same claim.

## the gap this closes

`_parse_v1_season_schedule` already lifts `season` and `league` off the tournament
wrapper that `_extract_match_items` otherwise flattens away, and
`_parse_single_fixture` reads `round`/`week` per item. `_claim_context` then wrote
`league` and dropped the other two. Measured on production 2026-09-09: of 1,044
StatPal `game` anchors, **293 carry a round and 0 carry a season** — and all 293
are NFL, written by the other stamper. The v1 leagues carry neither.

## why the keys are conditional, and why that is not fussiness

Measured at the venue 2026-09-09, `season` is served on 1208/1208 NBA,
1405/1405 NHL and 182/182 MLB fixtures, and `round` on none of them; the NFL is
the mirror image (0/374 season, 374/374 round). A key written unconditionally
would put `"round": null` on every NBA anchor forever, and a column of nulls
reads as *"we looked and there is none"* rather than *"this endpoint does not
serve it"*. The file already applies that rule to `apply_run_id`; these follow it.

## what these tests fail on

* the keys being dropped again by an edit to `_claim_context`;
* them being written unconditionally, which is the failure that looks like success;
* the value being invented rather than taken from the fixture the parser built;
* `league`, `statpal_start`, `statpal_stats_id` or `apply_run_id` regressing —
  they are asserted here too, because a dict assembled in one place is only safe
  if the whole dict is pinned.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService, StatPalFixture
from app.tasks.stamp_v1_statpal_fixtures import LEAGUES, _claim_context

FIXTURES = Path(__file__).parent / "fixtures"


def _nba_spec():
    for spec in LEAGUES.values():
        if spec.sport_key == "basketball_nba":
            return spec
    raise AssertionError("no LeagueSpec for basketball_nba")


def _parsed_nba():
    payload = json.loads(
        (FIXTURES / "statpal_nba_season_schedule_20260904.json").read_text()
    )
    return StatPalAPIService()._parse_v1_season_schedule(payload, "nba")


# --- the corpus, before anything leans on it ------------------------------------


def test_the_pinned_nba_payload_still_carries_a_season():
    """If the wrapper stops being parsed, every test below goes vacuous."""
    fixtures = _parsed_nba()
    assert fixtures, "corpus empty"
    with_season = [f for f in fixtures if f.season]
    assert len(with_season) == len(fixtures), (
        f"only {len(with_season)}/{len(fixtures)} parsed fixtures carry a season"
    )
    assert fixtures[0].season == "2026/2027"


# --- the carry ------------------------------------------------------------------


def test_a_season_the_venue_serves_reaches_the_anchor():
    fixture = _parsed_nba()[0]
    context = _claim_context(_nba_spec(), fixture)
    assert context["season"] == fixture.season == "2026/2027"


def test_a_round_the_venue_serves_reaches_the_anchor():
    """NBA serves no round, so the value is supplied the way the NFL feed does."""
    fixture = _parsed_nba()[0]
    fixture.round_info = "Regular Season / Week 1"
    context = _claim_context(_nba_spec(), fixture)
    assert context["round"] == "Regular Season / Week 1"


@pytest.mark.parametrize("absent", [None, ""])
def test_a_season_the_venue_does_not_serve_writes_no_key_at_all(absent):
    """Not `null`. Absent. A null would claim we looked and there was none."""
    fixture = _parsed_nba()[0]
    fixture.season = absent
    context = _claim_context(_nba_spec(), fixture)
    assert "season" not in context


@pytest.mark.parametrize("absent", [None, ""])
def test_a_round_the_venue_does_not_serve_writes_no_key_at_all(absent):
    fixture = _parsed_nba()[0]
    fixture.round_info = absent
    context = _claim_context(_nba_spec(), fixture)
    assert "round" not in context


def test_the_nba_feed_as_it_actually_is_gets_a_season_and_no_round():
    """The measured shape, end to end: 100% season, 0% round on this sport."""
    spec = _nba_spec()
    contexts = [_claim_context(spec, f) for f in _parsed_nba()]
    assert all("season" in c for c in contexts)
    assert not any("round" in c for c in contexts)


# --- the rest of the dict, pinned so an edit here cannot quietly drop it ---------


def test_the_whole_claim_context_is_what_it_says_it_is():
    fixture = StatPalFixture(
        fixture_id="1043639",
        home_team="Toronto Raptors",
        away_team="Boston Celtics",
        start_time=None,
        season="2026/2027",
        round_info=None,
        stats_id="99887",
    )
    spec = _nba_spec()
    assert _claim_context(spec, fixture) == {
        "written_by": "stamp_v1_statpal_fixtures",
        "league": spec.label,
        "statpal_start": None,
        "statpal_stats_id": "99887",
        "season": "2026/2027",
    }


def test_an_operator_run_id_still_rides_along():
    """CERT-2207: the undo's only durable anchor. Adding keys must not evict it."""
    fixture = _parsed_nba()[0]
    context = _claim_context(_nba_spec(), fixture, apply_run_id="run-abc")
    assert context["apply_run_id"] == "run-abc"
    assert context["season"] == "2026/2027"


def test_a_beat_run_still_omits_the_run_id_entirely():
    context = _claim_context(_nba_spec(), _parsed_nba()[0])
    assert "apply_run_id" not in context

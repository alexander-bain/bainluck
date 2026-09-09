"""A StatPal postseason placeholder is not a contest, and must not be receipted as one.

D106 / `docs/fixture-identity-contract-d106.md` rule R3. Successor to #3840
(fabricated fixtures) and EVENT-GRAPH-DOCTRINE rule 1 (no phantom events).

## what the venue actually publishes

`tests/fixtures/statpal_nfl_post_season_placeholders_20260909.json` is the real
`Post Season` stage of `/v1/nfl/season-schedule`, captured 2026-09-09. It holds 53
match items across five "weeks" — Wild Card, Divisional Round, Conference
Championships, Pro Bowl, Super Bowl — and **not one of them is a game**:

  * both sides are the same club, `{"id": "6687", "name": "TBD"}` — home team id
    EQUALS away team id, which no real contest can do;
  * `venue` is empty;
  * `datetime_utc` is `00:00` with `time: "7:00 PM"` and `timezone: "EST"`, i.e.
    StatPal's own default evening slot for a game nobody has scheduled;
  * **`contestid` REPEATS.** `280795` appears 15 times, `280794` 10, `280797` 8 —
    one provider id claiming to be several different games.

That last one is the dangerous property. `event_provider_anchors` is unique on
`(source, source_id, id_kind)`, so a writer that keyed on these ids would bind one
row and report COLLISION for the rest — a duplicate detector firing on rows that
are not duplicates of anything.

## what protects us today, and why that is not enough

Nothing, explicitly. `classify_fixture` requires both team names to match a row in
our pool exactly, and no NFL team is called TBD, so every placeholder falls out as
`UNMATCHED`. That is the right OUTCOME reached for the wrong REASON, and it has
two costs that are live right now:

  1. `UNMATCHED` on the fixture side means *"StatPal has a contest we do not
     hold"* — an ingestion gap. 53 non-games are reported as gaps we should close.
  2. the candidate-pool window is `min(kickoff) - slack .. max(kickoff) + slack`
     over every parsed fixture, and the placeholders carry dates three weeks past
     the last real regular-season game, so they stretch the window they have no
     business being in.

And it is one relaxed name rule away from becoming a stamp. So the placeholder is
rejected BY NAME here, with its own verdict, before any matching is attempted.

## what these tests fail on

* a placeholder being classified as anything a caller could act on;
* the `home.id == away.id` tell being dropped in favour of matching the literal
  string "TBD" (StatPal is not obliged to keep that word);
* a real contest being caught by the guard — the negative control below drives the
  Week 1 corpus through the same predicate and requires every one of them to pass.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.services.statpal_api import StatPalAPIService
from app.tasks.stamp_nfl_statpal_fixtures import (
    VERDICT_PLACEHOLDER,
    VERDICT_STAMP,
    classify_fixture,
    is_placeholder_fixture,
)

FIXTURES = Path(__file__).parent / "fixtures"
PLACEHOLDERS = FIXTURES / "statpal_nfl_post_season_placeholders_20260909.json"
REAL_SCHEDULE = FIXTURES / "statpal_nfl_season_schedule_20260903.json"


def _parse(path: Path):
    service = StatPalAPIService()
    return service._parse_nfl_season_schedule(json.loads(path.read_text()))


def _placeholders():
    return _parse(PLACEHOLDERS)


def _real():
    return _parse(REAL_SCHEDULE)


# --- the corpus, checked before anything leans on it ----------------------------


def test_the_captured_placeholder_stage_still_parses():
    """A truncated corpus must fail here, not pass every test below on 0 rows."""
    fixtures = _placeholders()
    assert len(fixtures) == 53, f"expected 53 placeholder items, parsed {len(fixtures)}"
    assert all(f.round_info and f.round_info.startswith("Post Season") for f in fixtures)


def test_the_provider_id_repeats_which_is_the_whole_hazard():
    """One `contestid` naming several 'games' is why these may never be keyed on."""
    counts = Counter(f.fixture_id for f in _placeholders())
    repeated = {k: v for k, v in counts.items() if v > 1}
    assert len(repeated) == 6, f"expected 6 repeated contest ids, got {repeated}"
    assert max(repeated.values()) == 15
    assert sum(repeated.values()) == 52


# --- the predicate --------------------------------------------------------------


def test_every_captured_placeholder_is_recognised():
    fixtures = _placeholders()
    missed = [f for f in fixtures if not is_placeholder_fixture(f)]
    assert not missed, f"{len(missed)} placeholders not recognised: {missed[:3]}"


def test_no_real_contest_is_caught_by_the_guard():
    """The negative control. 0 of the real Week 1 / Hall of Fame games may match."""
    real = _real()
    assert real, "corpus empty — this control would pass on nothing"
    caught = [f for f in real if is_placeholder_fixture(f)]
    assert not caught, f"guard caught {len(caught)} REAL contests: {caught[:3]}"


def test_the_tell_is_the_team_id_not_the_word_tbd():
    """StatPal is not obliged to keep spelling it 'TBD'.

    Renaming both sides to something innocuous must still be refused, because the
    identity claim `home.id == away.id` is what makes it impossible as a contest.
    """
    fixture = _placeholders()[0]
    fixture.home_team = "American Conference Champion"
    fixture.away_team = "National Conference Champion"
    assert fixture.home_team_id == fixture.away_team_id == "6687"
    assert is_placeholder_fixture(fixture) is True


def test_the_name_arm_carries_the_case_where_the_ids_are_absent():
    """Both arms must be load-bearing, or one of them is decorative.

    Every item in the captured corpus carries ids, so the id arm alone would make
    `PLACEHOLDER_TEAM_NAMES` untested. StatPal serving a bracket slot with the
    team block empty is the case this arm is for.
    """
    fixture = _placeholders()[0]
    fixture.home_team_id = None
    fixture.away_team_id = None
    assert fixture.home_team == fixture.away_team == "TBD"
    assert is_placeholder_fixture(fixture) is True

    fixture.home_team = "Seattle Seahawks"
    assert is_placeholder_fixture(fixture) is False, (
        "one real club and one TBD is a half-known bracket slot, but it is not "
        "the both-sides-unknown shape this arm claims to catch"
    )


def test_a_real_pair_that_shares_no_id_is_not_a_placeholder():
    """And the converse: two clubs with distinct ids are a contest, TBD or not."""
    fixture = _placeholders()[0]
    fixture.home_team_id = "6687"
    fixture.away_team_id = "6688"
    fixture.home_team = "Seattle Seahawks"
    fixture.away_team = "New England Patriots"
    assert is_placeholder_fixture(fixture) is False


# --- the verdict ----------------------------------------------------------------


def test_a_placeholder_gets_its_own_verdict_not_an_ingestion_gap():
    """`UNMATCHED` means 'StatPal has a game we lack'. That is a false statement here."""
    for fixture in _placeholders():
        verdict, matches = classify_fixture(fixture, [])
        assert verdict == VERDICT_PLACEHOLDER, (
            f"{fixture.fixture_id} {fixture.round_info}: got {verdict}"
        )
        assert matches == []


def test_a_placeholder_is_refused_even_when_a_row_would_match_it():
    """The guard runs BEFORE matching, so a loosened name rule cannot reach it.

    A pool row named exactly as the placeholder is at the placeholder's own
    kickoff — the arrangement that would stamp if the rejection were incidental
    rather than deliberate.
    """
    fixture = _placeholders()[0]
    pool = [
        {
            "id": 999001,
            "home": fixture.home_team,
            "away": fixture.away_team,
            "commence_time": fixture.start_time,
            "statpal_fixture_id": None,
            "status": "scheduled",
        }
    ]
    verdict, matches = classify_fixture(fixture, pool)
    assert verdict == VERDICT_PLACEHOLDER
    assert matches == []


def test_a_placeholder_with_no_kickoff_is_still_a_placeholder():
    """The guard runs before the no-kickoff branch, and that ordering is the test.

    Every item in today's corpus carries StatPal's default 7:00 PM EST slot, so
    both orderings agree on all 53 and the placement looks free. It is not: a
    bracket slot served with no time at all would fall through to
    `VERDICT_UNMATCHED` — *"StatPal has a contest we do not hold"* — which is the
    exact false statement this guard exists to stop making.
    """
    fixture = _placeholders()[0]
    fixture.start_time = None
    verdict, matches = classify_fixture(fixture, [])
    assert verdict == VERDICT_PLACEHOLDER
    assert matches == []


def test_a_club_whose_name_merely_contains_a_token_is_still_a_club():
    """Names are matched whole. A substring test would swallow real clubs.

    The adversary is constructed — no NFL club is spelled this way — because the
    predicate is generic and the next sport to use it may have one. The claim in
    the docstring ("matched whole, never as a substring") is worth nothing unless
    something fails when it stops being true.
    """
    fixture = _placeholders()[0]
    fixture.home_team_id = None
    fixture.away_team_id = None
    fixture.home_team = "Tbd City FC"
    fixture.away_team = "TBD"
    assert is_placeholder_fixture(fixture) is False


def test_a_real_week_one_game_still_stamps():
    """The guard must not have cost us the thing the stamper is for."""
    fixture = next(f for f in _real() if f.round_info == "Regular Season / Week 1")
    pool = [
        {
            "id": 999002,
            "home": fixture.home_team,
            "away": fixture.away_team,
            "commence_time": fixture.start_time,
            "statpal_fixture_id": None,
            "status": "scheduled",
        }
    ]
    assert classify_fixture(fixture, pool)[0] == VERDICT_STAMP

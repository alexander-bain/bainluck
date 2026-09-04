"""MLB joins the shadow authority. #2867 / D50, step 5.

**SHIP: an MLB game page can eventually show StatPal's inning-by-inning truth
instead of a second-hand score, because the game on screen is now joined to the
StatPal contest that carries it. DARK — nothing reads the join — and this file is
what decides whether it may ever be read.** (Pillar: MATCHING.)

`test_statpal_mlb_id_spaces.py` answered *which field is the anchor*. This file
answers *what the stamper does with it*, and every number in it is driven by the
FULL CENSUS read from production on 2026-09-04 — all 16 `livescores` rows against
all 227 `season-schedule` rows — not by a reduced sample.

## that distinction is the point, and it is here because it already bit

CERT-926 granted its token with a non-blocking
`FOLLOW-UP -- AUTHORITY-016-FULL-CENSUS-FIXTURE-PROVENANCE`: the census numbers
were prose-backed while the committed guards ran on reduced 15/6 fixtures. The
follow-up then came true. `ARTIFACT-…-MLB-ID-SPACES.md` §5 said the blank-`oddsid`
residue "is the second half of the one real doubleheader" — a sentence whose
COUNT (3 of 16) came from the full census and whose STORY came from the reduced
6-row fixture, in which the doubleheader genuinely is the only blank. Two of the
three are ordinary single games.

**A reduced fixture may back a count or a characterisation, never both.** The
sample that preserves the rate is not automatically the sample that preserves the
shape. So the census fixtures are committed beside the reduced ones, every
count-bearing assertion below reads the census, and
:func:`test_the_reduced_fixtures_cannot_be_mistaken_for_the_census` fails if
anybody quotes a census number off a reduced sample again.

## what each test can fail on

* the anchor field silently reverting to `livescores.id`, which shares a width, a
  prefix and a numeric range with `stats_id` and not one value with either;
* the blank-anchor recovery widening its window, or falling back to a calendar
  day — which does not merely mis-flag the doubleheader, it fuses it;
* `FOREIGN_ID_SPACE` collapsing back into `CONTRADICTION`, which would file a
  namespace bug as a matching bug and send 92 values to the wrong owner;
* MLB's partial `stats_id` coverage being rounded to a boolean;
* the reduced fixtures being read as if they were the census.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from importlib import import_module
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService
from app.tasks.stamp_v1_statpal_fixtures import (
    CLOSEST_SAME_PAIR_SEPARATION,
    MATCH_WINDOW,
    MAX_SAFE_WINDOW,
    MLB,
    STATS_ID_ON_SOME_FIXTURES,
    VERDICT_ANCHOR_ONLY,
    VERDICT_FOREIGN_ID_SPACE,
    live_anchor_id,
    recover_live_anchor,
)
from app.utils.nfl_team_matching import normalize_team, pair_matches
from app.utils.statpal_league_rosters import MLB_TEAM_NAMES, is_known_league_team

task = import_module("app.tasks.stamp_v1_statpal_fixtures")

FIXTURES = Path(__file__).parent / "fixtures"

#: The full census, read from production 2026-09-04 at 14:28Z / 14:29Z.
CENSUS_LIVE = FIXTURES / "statpal_mlb_livescores_20260904_fullcensus.json"
CENSUS_SCHEDULE = FIXTURES / "statpal_mlb_season_schedule_20260904_fullcensus.json"

#: The reduced samples committed by step 5's predecessor. Named here ONLY so the
#: guard below can prove they are reduced; no count in this file comes off them.
REDUCED_LIVE = FIXTURES / "statpal_mlb_livescores_20260904.json"
REDUCED_SCHEDULE = FIXTURES / "statpal_mlb_season_schedule_20260904.json"

#: The census, as measured. Every one of these is asserted against the payloads
#: below rather than trusted, so a re-capture that changes the population fails
#: loudly instead of quietly rebasing the numbers underneath the tests.
CENSUS_LIVE_ROWS = 16
CENSUS_SCHEDULE_ROWS = 227
ODDSID_PRESENT = 13
ODDSID_BLANK = 3
STATS_ID_PRESENT = 198
STATS_ID_ABSENT = 29


def _matches(path: Path, top_key: str) -> list[dict]:
    payload = json.loads(path.read_text())
    tournaments = payload[top_key]["tournament"]
    if isinstance(tournaments, dict):
        tournaments = [tournaments]
    out: list[dict] = []
    for tournament in tournaments:
        found = tournament.get("match", [])
        out.extend(found if isinstance(found, list) else [found])
    return out


@pytest.fixture(scope="module")
def live_raw() -> list[dict]:
    return _matches(CENSUS_LIVE, "livescores")


@pytest.fixture(scope="module")
def schedule_raw() -> list[dict]:
    return _matches(CENSUS_SCHEDULE, "scores")


@pytest.fixture(scope="module")
def parsed(live_raw, schedule_raw):
    """Both endpoints through the REAL parser, not a hand-built shape.

    `_parse_v1_season_schedule` and `_parse_fixtures` are what production calls,
    so a change to either — the `datetime_utc` preference, the `oddsid` read, the
    `stats_id` carry — has to keep these tests passing or be seen.
    """
    service = StatPalAPIService(api_key="test")
    schedule = service._parse_v1_season_schedule(
        json.loads(CENSUS_SCHEDULE.read_text()), "mlb"
    )
    live = service._parse_fixtures(json.loads(CENSUS_LIVE.read_text()), "mlb")
    return live, schedule


def _by_teams(fixtures, away, home):
    found = [f for f in fixtures if f.away_team == away and f.home_team == home]
    assert found, f"{away} @ {home} is not in this census"
    return found


# ---------------------------------------------------------------------------
# the census is the census
# ---------------------------------------------------------------------------


def test_the_census_fixtures_are_the_whole_population_they_claim_to_be(
    live_raw, schedule_raw
):
    assert len(live_raw) == CENSUS_LIVE_ROWS
    assert len(schedule_raw) == CENSUS_SCHEDULE_ROWS
    # 227 distinct ids, no collisions and no blanks — the property that makes
    # `season-schedule.id` an anchor at all.
    ids = [m["id"] for m in schedule_raw]
    assert all(ids)
    assert len(set(ids)) == CENSUS_SCHEDULE_ROWS


def test_the_reduced_fixtures_cannot_be_mistaken_for_the_census():
    """CERT-926's FOLLOW-UP, as a test rather than a resolution.

    The defect was not that reduced fixtures exist — they are cheap and they pin
    shape well. It was that a census COUNT and a reduced-fixture STORY were
    published as one sentence. This asserts the two populations are different
    sizes, so `len(reduced) == CENSUS_*_ROWS` can never accidentally hold and let
    a census claim be "verified" against a sample.
    """
    reduced_live = _matches(REDUCED_LIVE, "livescores")
    reduced_schedule = _matches(REDUCED_SCHEDULE, "scores")
    assert 0 < len(reduced_live) < CENSUS_LIVE_ROWS
    assert 0 < len(reduced_schedule) < CENSUS_SCHEDULE_ROWS

    # And the specific way it misled: in the reduced live sample the doubleheader
    # IS the only blank `oddsid`, which is exactly why "the residue is the
    # doubleheader" survived review. In the census it is one of three.
    reduced_blanks = [m for m in reduced_live if not (m.get("oddsid") or "").strip()]
    assert len(reduced_blanks) == 1
    census_blanks = [
        m for m in _matches(CENSUS_LIVE, "livescores")
        if not (m.get("oddsid") or "").strip()
    ]
    assert len(census_blanks) == ODDSID_BLANK


# ---------------------------------------------------------------------------
# the anchor, and the number that looks exactly like it
# ---------------------------------------------------------------------------


def test_oddsid_is_the_anchor_and_every_one_of_them_dereferences(live_raw, schedule_raw):
    schedule_ids = {m["id"] for m in schedule_raw}
    filled = [(m.get("oddsid") or "").strip() for m in live_raw]
    present = [o for o in filled if o]
    assert len(present) == ODDSID_PRESENT
    assert len(filled) - len(present) == ODDSID_BLANK
    assert all(o in schedule_ids for o in present)


def test_the_live_id_is_a_third_space_and_it_is_a_trap(live_raw, schedule_raw):
    """`livescores.id` and `season-schedule.stats_id` are indistinguishable by
    shape and share NOTHING — which is why the anchor field is named per league
    and never inferred from the number (D55).
    """
    live_ids = {m["id"] for m in live_raw}
    schedule_ids = {m["id"] for m in schedule_raw}
    stats_ids = {
        (m.get("stats_id") or "").strip()
        for m in schedule_raw
        if (m.get("stats_id") or "").strip()
    }

    # Same width, same prefix, overlapping range — every reason to think they
    # are one space.
    assert {len(i) for i in live_ids} == {len(i) for i in stats_ids} == {10}
    assert all(i.startswith("1329") for i in live_ids | stats_ids)
    assert min(live_ids) < max(stats_ids) and min(stats_ids) < max(live_ids)

    # And not one value in common, with either schedule space.
    assert live_ids & stats_ids == set()
    assert live_ids & schedule_ids == set()


def test_the_parser_carries_oddsid_without_ever_preferring_it(parsed):
    """Additive. The live writers keep the id they have always had.

    `fixture_id` still comes from `id`, so nothing on the live path moves; the
    authority reader is the only caller that asks for `odds_id`, because it is
    the only one joining two endpoints together.
    """
    live, schedule = parsed
    assert [f.fixture_id for f in live] == [
        m["id"] for m in _matches(CENSUS_LIVE, "livescores")
    ]
    assert sum(1 for f in live if f.odds_id) == ODDSID_PRESENT
    # `season-schedule` does not serve the field at all.
    assert all(f.odds_id is None for f in schedule)


def test_the_named_anchor_field_is_what_the_spec_reads(parsed):
    live, _schedule = parsed
    resolved = [live_anchor_id(MLB, f) for f in live]
    assert sum(1 for r in resolved if r) == ODDSID_PRESENT
    assert [r for r in resolved if r] == [f.odds_id for f in live if f.odds_id]
    # The NBA/NHL spec reads the other field off the same payload — proof the
    # choice is the spec's and not the sport's shape.
    assert live_anchor_id(task.NBA, live[0]) == live[0].fixture_id


# ---------------------------------------------------------------------------
# recovering the three blanks, scored against ground truth
# ---------------------------------------------------------------------------


def test_the_recovery_rule_is_exact_on_every_row_the_anchor_can_check(parsed):
    """The 13 anchored rows ARE ground truth, so the rule is measured, not argued.

    This is the sub-population that already has an answer, used to score a
    fallback designed for the one that does not.
    """
    live, schedule = parsed
    checked = 0
    for fixture in live:
        if not fixture.odds_id:
            continue
        recovered, reason = recover_live_anchor(fixture, schedule)
        assert recovered == fixture.odds_id, (fixture.away_team, reason)
        checked += 1
    assert checked == ODDSID_PRESENT


@pytest.mark.parametrize(
    "tolerance_hours", [0.5, 1, 2, 3, 6]
)
def test_no_tolerance_in_the_swept_range_gets_a_single_row_wrong(
    parsed, tolerance_hours, monkeypatch
):
    """The sweep behind ±1h, as a test rather than a table in a report.

    Every tolerance tried is 13/13. The window is therefore NOT chosen to make
    the join work — it is chosen because it is the tightest one that does, and
    because MLB's doubleheader puts a hard ceiling overhead.
    """
    live, schedule = parsed
    monkeypatch.setattr(task, "MATCH_WINDOW", timedelta(hours=tolerance_hours))
    for fixture in live:
        if not fixture.odds_id:
            continue
        recovered, _reason = recover_live_anchor(fixture, schedule)
        assert recovered == fixture.odds_id


def test_the_calendar_day_key_is_ambiguous_where_the_anchor_is_certain(parsed):
    """The rule NOT adopted, measured on the same 13 rows: 9 correct, 4 ambiguous.

    Reported here so the comparison survives the report it came from. A future
    reader who reaches for a day key — and it is the obvious thing to reach for —
    finds the number rather than the intuition.
    """
    live, schedule = parsed
    correct = ambiguous = 0
    for fixture in live:
        if not fixture.odds_id:
            continue
        same_day = [
            s
            for s in schedule
            if s.start_time is not None
            and s.start_time.date() == fixture.start_time.date()
            and pair_matches(
                (fixture.home_team, fixture.away_team), (s.home_team, s.away_team)
            )
        ]
        if len(same_day) > 1:
            ambiguous += 1
        elif len(same_day) == 1 and same_day[0].fixture_id == fixture.odds_id:
            correct += 1
    assert (correct, ambiguous) == (9, 4)


def test_the_calendar_day_key_does_not_flag_the_doubleheader_it_fuses_it(parsed):
    """The reason the day key is refused outright rather than tuned.

    Detroit's nightcap has no `oddsid`. Keyed on the UTC day it resolves to
    schedule row `354453` — which the FIRST game already holds by its own
    explicit anchor. Two contests, one schedule row: gotcha #46's class, and D55's
    "a collision raises or tags, never silently no-ops".
    """
    live, schedule = parsed
    nightcap = next(
        f
        for f in _by_teams(live, "Detroit Tigers", "Cleveland Guardians")
        if not f.odds_id
    )
    opener = next(
        f
        for f in _by_teams(live, "Detroit Tigers", "Cleveland Guardians")
        if f.odds_id
    )

    same_day = [
        s
        for s in schedule
        if s.start_time is not None
        and s.start_time.date() == nightcap.start_time.date()
        and pair_matches(
            (nightcap.home_team, nightcap.away_team), (s.home_team, s.away_team)
        )
    ]
    assert [s.fixture_id for s in same_day] == [opener.odds_id]


def test_the_window_rule_recovers_two_blanks_and_declares_the_third(parsed):
    """15/16 with the 16th declared beats 16/16 with one silently fused."""
    live, schedule = parsed

    angels = next(f for f in _by_teams(live, "Los Angeles Angels", "Pittsburgh Pirates"))
    recovered, reason = recover_live_anchor(angels, schedule)
    assert (recovered, "recovered" in reason) == ("362149", True)

    athletics = next(f for f in _by_teams(live, "Athletics", "Seattle Mariners"))
    recovered, _reason = recover_live_anchor(athletics, schedule)
    assert recovered == "362161"

    nightcap = next(
        f
        for f in _by_teams(live, "Detroit Tigers", "Cleveland Guardians")
        if not f.odds_id
    )
    recovered, reason = recover_live_anchor(nightcap, schedule)
    assert recovered is None
    assert "no scheduled contest" in reason


def test_the_refused_row_is_refused_because_the_two_endpoints_disagree(parsed):
    """Not a gap in the schedule — a 3h05m disagreement about one first pitch.

    `livescores` says 04.09 23:10Z and `season-schedule` says 05.09 02:15Z for
    the same contest. Refusing is right: we do not know which is correct, and a
    wider window would write one of them into the graph.
    """
    live, schedule = parsed
    nightcap = next(
        f
        for f in _by_teams(live, "Detroit Tigers", "Cleveland Guardians")
        if not f.odds_id
    )
    scheduled = [
        s
        for s in schedule
        if pair_matches(
            (nightcap.home_team, nightcap.away_team), (s.home_team, s.away_team)
        )
    ]
    gap = min(abs(s.start_time - nightcap.start_time) for s in scheduled)
    assert gap == timedelta(hours=3, minutes=5)
    assert gap > MATCH_WINDOW
    # The contest is NOT lost: it is read from `season-schedule` under its own
    # id. Only the live view of it is dropped.
    assert "362151" in {s.fixture_id for s in scheduled}


def test_a_window_wide_enough_to_catch_the_nightcap_would_reach_the_doubleheader(
    parsed,
):
    """Why "just widen it" is not available here, in numbers.

    The refused row is 3h05m out. MLB's doubleheader is 8h05m apart, so anything
    over 4h02m30s can reach both games of it — and a window big enough for the
    nightcap is already three quarters of the way there. The two constraints are
    close enough that the tempting fix is nearly the breaking one.
    """
    assert MAX_SAFE_WINDOW == CLOSEST_SAME_PAIR_SEPARATION["baseball_mlb"] / 2
    assert timedelta(hours=3, minutes=5) < MAX_SAFE_WINDOW
    assert MATCH_WINDOW < MAX_SAFE_WINDOW

    live, schedule = parsed
    both_games = _by_teams(schedule, "Detroit Tigers", "Cleveland Guardians")
    starts = sorted(s.start_time for s in both_games)
    assert starts[1] - starts[0] == CLOSEST_SAME_PAIR_SEPARATION["baseball_mlb"]


# ---------------------------------------------------------------------------
# the column already holds two id spaces
# ---------------------------------------------------------------------------


def test_a_live_id_in_our_column_is_a_namespace_bug_not_a_matching_bug(parsed):
    """Measured on production 2026-09-04: of 222 distinct MLB column values, 130
    dereference to `season-schedule.id`, 0 to `stats_id`, and 92 to neither.

    `sync-statpal-livescores` runs every 30 seconds and writes `livescores.id`;
    `sync-statpal-schedules-mlb` runs hourly and writes `season-schedule.id`.
    Both go through `_parse_single_fixture`, which takes `fixture_id` from `id`,
    and `id` means different things on the two endpoints. Reporting that as a
    CONTRADICTION would claim the ingestion path picked a different GAME.
    """
    live, schedule = parsed
    opener = next(
        f
        for f in _by_teams(live, "Detroit Tigers", "Cleveland Guardians")
        if f.odds_id
    )
    contest = next(s for s in schedule if s.fixture_id == opener.odds_id)
    anchor_space = {s.fixture_id for s in schedule}

    ours = {
        "id": 1,
        "home": contest.home_team,
        "away": contest.away_team,
        "commence_time": contest.start_time,
        # The live id for this very contest — the right game, the wrong endpoint.
        "statpal_fixture_id": opener.fixture_id,
        "status": "scheduled",
    }
    verdict, matches = task.classify_fixture(contest, [ours], anchor_space)
    assert verdict == VERDICT_FOREIGN_ID_SPACE
    assert matches == [ours]

    # Same row, column corrected to the anchor: ordinary work, not a finding.
    ours["statpal_fixture_id"] = contest.fixture_id
    verdict, _matches = task.classify_fixture(contest, [ours], anchor_space)
    assert verdict == VERDICT_ANCHOR_ONLY


def test_without_the_anchor_space_the_verdict_degrades_to_contradiction(parsed):
    """Omitting the space is the honest degradation, not a silent one.

    With no evidence about which ids the endpoint publishes there is no way to
    tell a foreign space from a different game, so the caller that cannot supply
    it gets the older, weaker answer rather than a confident new one.
    """
    live, schedule = parsed
    opener = next(
        f
        for f in _by_teams(live, "Detroit Tigers", "Cleveland Guardians")
        if f.odds_id
    )
    contest = next(s for s in schedule if s.fixture_id == opener.odds_id)
    ours = {
        "id": 1,
        "home": contest.home_team,
        "away": contest.away_team,
        "commence_time": contest.start_time,
        "statpal_fixture_id": opener.fixture_id,
        "status": "scheduled",
    }
    verdict, _matches = task.classify_fixture(contest, [ours])
    assert verdict == task.VERDICT_CONTRADICTION


# ---------------------------------------------------------------------------
# stats_id: three-valued, and the blanks have no structure to exploit
# ---------------------------------------------------------------------------


def test_mlb_stats_id_coverage_is_partial_and_recorded_as_such(schedule_raw):
    filled = [m for m in schedule_raw if (m.get("stats_id") or "").strip()]
    assert len(filled) == STATS_ID_PRESENT
    assert len(schedule_raw) - len(filled) == STATS_ID_ABSENT
    assert MLB.stats_id_coverage == STATS_ID_ON_SOME_FIXTURES
    assert "198/227" in MLB.stats_id_measured


def test_the_stats_id_blanks_are_not_explained_by_the_game_having_been_played(
    schedule_raw,
):
    """A rule would have beaten a rate, so it was looked for and is not there.

    The obvious hypothesis is "filled once played". Measured, it is backwards:
    `Finished` games are filled 74.3% and `Not Started` 93.0%. There is nothing
    to key on, which is why the expectation is a three-valued adjective with the
    rate recorded beside it rather than a condition.
    """
    by_status: Counter = Counter()
    for match in schedule_raw:
        status = match.get("status", "")
        by_status[(status, bool((match.get("stats_id") or "").strip()))] += 1

    finished_filled = by_status[("Finished", True)]
    finished_blank = by_status[("Finished", False)]
    upcoming_filled = by_status[("Not Started", True)]
    upcoming_blank = by_status[("Not Started", False)]

    assert (finished_filled, finished_blank) == (52, 18)
    assert (upcoming_filled, upcoming_blank) == (146, 11)
    # Blanks are commoner on games already played — the opposite of the
    # hypothesis, so no ordering or status rule recovers them.
    assert finished_blank / (finished_filled + finished_blank) > upcoming_blank / (
        upcoming_filled + upcoming_blank
    )


def test_the_live_endpoint_serves_no_stats_id_for_any_sport(parsed):
    """Why the coverage count is scoped to `season-schedule`.

    `_parse_single_fixture` — the parser every `livescores` payload goes through
    — never populates `stats_id`. Counting both endpoints together would have
    reported NHL as broken the first time a live contest had no season-schedule
    twin to dedupe against. MLB is simply the first sport in season, so it is
    where that would have surfaced.
    """
    live, schedule = parsed
    assert all(f.stats_id is None for f in live)
    assert any(f.stats_id for f in schedule)


# ---------------------------------------------------------------------------
# the vocabulary
# ---------------------------------------------------------------------------


def test_both_sides_serve_thirty_one_strings_for_thirty_clubs(live_raw, schedule_raw):
    """And the extra string is the same on both sides: `St.Louis Cardinals`.

    Our table holds the split too — 12 rows against 7 on 2026-09-04 — so this is
    not a provider quirk to absorb at the boundary. `normalize_team` strips the
    period and collapses the space, which is what makes the comparison exact
    rather than lucky.
    """
    served = {m[side]["name"] for m in live_raw + schedule_raw for side in ("home", "away")}
    assert len(served) == 31
    assert {"St. Louis Cardinals", "St.Louis Cardinals"} <= served
    assert len({normalize_team(n) for n in served}) == 30
    assert {normalize_team(n) for n in served} == set(MLB_TEAM_NAMES)


def test_both_spellings_of_one_club_reduce_to_one_franchise():
    assert normalize_team("St.Louis Cardinals") == normalize_team("St. Louis Cardinals")
    assert is_known_league_team("baseball_mlb", "St.Louis Cardinals")
    assert is_known_league_team("baseball_mlb", "St. Louis Cardinals")
    # Reporting, never gating: a name nobody measured is named, not approximated.
    assert not is_known_league_team("baseball_mlb", "Oakland Athletics")


# ---------------------------------------------------------------------------
# one pass, end to end, over the real census
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_dark_pass_over_the_real_census_reads_both_endpoints(monkeypatch):
    """The whole read path on the real payloads, with no database write.

    `apply=False` plans and writes nothing, so this exercises the part MLB
    changed — the anchor resolution and the dedup — against the population it was
    designed on.
    """
    service = StatPalAPIService(api_key="test")
    schedule = service._parse_v1_season_schedule(
        json.loads(CENSUS_SCHEDULE.read_text()), "mlb"
    )
    live = service._parse_fixtures(json.loads(CENSUS_LIVE.read_text()), "mlb")

    run = task.StampRun(
        sport_key=MLB.sport_key,
        stats_id_coverage=MLB.stats_id_coverage,
        stats_id_measured=MLB.stats_id_measured,
    )

    class _Service:
        async def get_schedule_fixtures(self, sport):
            assert sport == "mlb"
            return list(schedule)

        async def get_live_fixtures(self, sport):
            return list(live)

        async def close(self):
            return None

    fixtures, anchor_space = await task._read_fixtures(_Service(), MLB, run)

    assert run.sources_read == ["season-schedule", "livescores"]
    assert run.read_failures == []
    assert len(anchor_space) == CENSUS_SCHEDULE_ROWS

    # Every live row that carries the anchor dedupes onto its schedule contest,
    # and the two recovered blanks do too — so the pass reads 227 contests, not
    # 227 plus a handful of live doubles.
    assert run.live_anchor_recovered == 2
    assert len(run.live_unkeyable) == 1
    assert len(fixtures) == CENSUS_SCHEDULE_ROWS

    (refused,) = run.live_unkeyable
    assert refused["teams"] == ["Detroit Tigers", "Cleveland Guardians"]
    assert "no scheduled contest" in refused["refused_because"]

    # Scoped to the endpoint that serves it, so the 16 live rows cannot dilute it.
    assert (run.stats_id_present, run.stats_id_absent) == (
        STATS_ID_PRESENT,
        STATS_ID_ABSENT,
    )
    assert run.stats_id_as_expected

    summary = run.summary()
    assert summary["stats_id"]["expected"] == STATS_ID_ON_SOME_FIXTURES
    assert summary["live_anchor_recovered"] == 2
    assert summary["live_unkeyable"] == 1


@pytest.mark.asyncio
async def test_a_live_contest_the_schedule_does_not_carry_is_kept_not_dropped(
    monkeypatch,
):
    """A blank anchor is refused; a PRESENT anchor is never second-guessed.

    The recovery rule only ever runs on rows with no anchor field, so a live
    contest StatPal has not put on the schedule still arrives — under its own
    `oddsid` — and is reported as the ingestion finding it is, rather than being
    quietly filtered for having no schedule twin.
    """
    service = StatPalAPIService(api_key="test")
    live = service._parse_fixtures(json.loads(CENSUS_LIVE.read_text()), "mlb")
    anchored = next(f for f in live if f.odds_id)

    run = task.StampRun(sport_key=MLB.sport_key)

    class _Service:
        async def get_schedule_fixtures(self, sport):
            return []

        async def get_live_fixtures(self, sport):
            return [anchored]

        async def close(self):
            return None

    fixtures, anchor_space = await task._read_fixtures(_Service(), MLB, run)

    assert anchor_space == set()
    assert [f.fixture_id for f in fixtures] == [anchored.odds_id]
    assert run.live_unkeyable == []
    assert run.live_anchor_recovered == 0

"""AUTHORITY step 5 (D50) — MLB's id question, answered. The anchor exists; it is
not called `id` on the endpoint that carries it.

MLB is excluded from `V1_SEASON_SCHEDULE_SPORTS` because it "has three id spaces
and none survives across endpoints", so the ledger spec falls back to joining on
`(away_team_name, home_team_name, calendar date)`. The three spaces are real.
The conclusion drawn from them was not: there is a FOURTH field, `oddsid`, and it
is the season-schedule `id` carried on livescores.

MEASURED AGAINST PRODUCTION, 2026-09-04 13:38Z and 13:52Z:

    GET /api/v1/mlb/season-schedule   227 games, 2026-08-29 -> 2026-09-15
    GET /api/v1/mlb/livescores         16 games, all of 2026-09-04

Five findings.

  1. `season-schedule.id` ANCHORS. 227/227 filled, 227 distinct, zero collisions,
     zero blanks. Same verdict NHL reached; it is the one MLB was missing.

  2. `stats_id` CANNOT ANCHOR — 22.5% of the window is unusable. 29 of 227 are
     blank and a further 22 rows share 11 values with another contest. Its
     collisions are not random: every colliding pair is the same two clubs about
     18h apart, so `stats_id` keys something series-shaped, not a contest. NHL
     failed the same test on 3 pairs; MLB fails it far harder.

  3. `livescores.id` IS GENUINELY A THIRD SPACE, AND IT IS A TRAP. 16/16 distinct
     and 0/16 appear in either schedule space. The trap is that it LOOKS like
     `stats_id`: livescores.id spans 1329192580..1329202652 and schedule.stats_id
     spans 1329190986..1329201329 — the same width, the same prefix, overlapping
     ranges, and not one value in common. Any rule that infers a space from digit
     count or numeric range joins these confidently and wrongly. This is the
     measured MLB case for D55: an anchor key is explicit (provider, sport, id),
     never inferred from the shape of the number.

  4. `livescores.oddsid` IS `season-schedule.id`. 13 of 16 rows carry it and all
     13 dereference to a schedule row. THAT is the cross-endpoint anchor, and it
     was sitting under a name that reads like an odds-provider key. The remaining
     3 rows carry `oddsid: ""` — so the anchor covers 81% of a live board and the
     residue needs a second signal, which is a bounded problem rather than the
     open one step 5 inherited.

  5. THE (teams, date) FALLBACK IS DEFECTIVE, AND NOT FOR THE REASON GIVEN. On
     the full window it flags 22 same-pair-same-day collisions. Not one is a
     doubleheader: the gaps run 17.4h to 23.1h (median 18.5h) and zero are under
     6h. They are consecutive-day games of one series, and StatPal's
     season-schedule `date`/`time` are UTC, so a 7:05pm ET first pitch is stamped
     00:05 the next day and lands on the same UTC date as the next afternoon's
     game.

     The window holds exactly ONE genuine doubleheader — Detroit at Cleveland on
     2026-09-04, 8.08h apart — and the UTC key CANNOT SEE IT, because its two
     games straddle midnight UTC and are filed under different dates. So the key
     as specified invents 22 doubleheaders that do not exist and misses the only
     one that does. Re-keyed on the local day it drops to 1 collision, the real
     one. Every MLB park is UTC-4..UTC-7, so a flat 5h separates a night game
     from the next afternoon's for every park in the league.

     Even re-keyed it stays worse than the anchor: joining today's 16 live rows
     to the schedule by (clubs, local day) hits 13, misses 1 and is ambiguous on
     2. The miss is `St. Louis Cardinals` against `St.Louis Cardinals` — one
     space, two endpoints, same club. `oddsid` joins that row without noticing.

TWO TIME BASES, ONE FIELD NAME. `time` is UTC on season-schedule and ET on
livescores (which also serves `datetime_utc` and `timezone`, neither of which
season-schedule has). Read `time` from the wrong endpoint and every MLB game
moves by four or five hours.

Nothing here reads MLB as an authority. `test_mlb_is_deliberately_not_routed_here_yet`
in test_statpal_authority_nba_nhl.py still holds the gate shut: an anchor is not a
stamper, and flipping the gate is step 5's ship, not this file's.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SCHEDULE_FIXTURE = FIXTURES / "statpal_mlb_season_schedule_20260904.json"
LIVESCORES_FIXTURE = FIXTURES / "statpal_mlb_livescores_20260904.json"

# Every MLB park sits between UTC-4 and UTC-7. Any offset in that range splits a
# night game from the next afternoon's game; 5h is the middle of it.
PARK_OFFSET = timedelta(hours=5)


@pytest.fixture
def matches():
    payload = json.loads(SCHEDULE_FIXTURE.read_text())
    return payload["scores"]["tournament"]["match"]


@pytest.fixture
def live_matches():
    """Note the envelope: livescores nests under `livescores`, not `scores`.

    Reading it as `scores` yields a KeyError if you are lucky and an empty list
    if you are not — and "no games are live" is an entirely plausible story for
    an empty MLB board at 06:38 PT, which is what makes it gotcha #53 rather
    than a typo. It cost this session one wrong finding before the 2026-09-03
    fixture contradicted it.
    """
    payload = json.loads(LIVESCORES_FIXTURE.read_text())
    return payload["livescores"]["tournament"]["match"]


def _kickoff(match):
    """StatPal serves `date` as DD.MM.YYYY and `time` as HH:MM, both UTC."""
    return datetime.strptime(f"{match['date']} {match['time']}", "%d.%m.%Y %H:%M")


def _clubs(match):
    return (match["away"]["name"].strip(), match["home"]["name"].strip())


def _group(matches, day_of):
    grouped = defaultdict(list)
    for match in matches:
        grouped[(_clubs(match), day_of(match))].append(match)
    return grouped


class TestWhichIdAnchors:
    """Finding 1 and 2 — `id` anchors a contest, `stats_id` does not."""

    def test_id_is_unique_and_always_present(self, matches):
        ids = [str(m["id"]) for m in matches]
        assert "" not in ids
        assert len(set(ids)) == len(ids) == 15

    def test_stats_id_is_blank_on_some_games_and_shared_by_others(self, matches):
        stats_ids = [str(m.get("stats_id") or "") for m in matches]
        filled = [s for s in stats_ids if s]

        assert len(stats_ids) - len(filled) == 2, "blank stats_id must stay visible"
        shared = {s: n for s, n in Counter(filled).items() if n > 1}
        assert len(shared) == 3

        # The collisions are series-shaped, not random: same clubs, ~18h apart.
        for value in shared:
            pair = [m for m in matches if str(m.get("stats_id") or "") == value]
            assert len({_clubs(m) for m in pair}) == 1
            times = sorted(_kickoff(m) for m in pair)
            gap = (times[-1] - times[0]).total_seconds() / 3600
            assert 12 <= gap < 24, f"stats_id {value} spans {gap:.1f}h"

    def test_stats_id_would_lose_games_that_id_keeps(self, matches):
        """The two ids are not interchangeable, so a reader may not substitute."""
        by_id = {str(m["id"]) for m in matches}
        by_stats_id = {str(m.get("stats_id") or "") for m in matches} - {""}

        assert len(by_id) == len(matches)
        assert len(by_stats_id) < len(matches)


class TestTheJoinKeyIsKeyedOnTheWrongDay:
    """Finding 5 — the UTC date invents doubleheaders and hides the real one."""

    def test_utc_date_flags_pairs_that_are_not_doubleheaders(self, matches):
        collisions = {
            key: group
            for key, group in _group(matches, lambda m: m["date"]).items()
            if len(group) > 1
        }
        assert len(collisions) == 3

        for key, group in collisions.items():
            times = sorted(_kickoff(m) for m in group)
            gap = (times[-1] - times[0]).total_seconds() / 3600
            assert gap >= 12, (
                f"{key[0]} are {gap:.1f}h apart — a doubleheader is a few hours, "
                "so this is a consecutive-day series collapsed onto one UTC date"
            )

    def test_utc_date_cannot_see_the_one_real_doubleheader(self, matches):
        """Its two games straddle midnight UTC, so they land on different dates."""
        real = [
            m for m in matches
            if _clubs(m) == ("Detroit Tigers", "Cleveland Guardians")
        ]
        assert len(real) == 2
        assert {m["date"] for m in real} == {"04.09.2026", "05.09.2026"}

        utc_keyed = _group(matches, lambda m: m["date"])
        for match in real:
            assert len(utc_keyed[(_clubs(match), match["date"])]) == 1, (
                "the genuine doubleheader is filed under two separate UTC dates, "
                "so a same-pair-same-day rule never flags it"
            )

    def test_the_local_day_finds_the_real_one_and_only_it(self, matches):
        collisions = {
            key: group
            for key, group in _group(
                matches, lambda m: (_kickoff(m) - PARK_OFFSET).date()
            ).items()
            if len(group) > 1
        }

        assert list(collisions) == [
            (("Detroit Tigers", "Cleveland Guardians"), datetime(2026, 9, 4).date())
        ]
        times = sorted(_kickoff(m) for m in collisions.popitem()[1])
        gap = (times[-1] - times[0]).total_seconds() / 3600
        assert gap == pytest.approx(8.08, abs=0.01)

    def test_re_keying_recovers_the_games_the_utc_key_merged(self, matches):
        """The count that matters to a denominator: 12 keys become 14."""
        utc_keys = _group(matches, lambda m: m["date"])
        local_keys = _group(matches, lambda m: (_kickoff(m) - PARK_OFFSET).date())

        assert len(utc_keys) == 12
        assert len(local_keys) == 14
        assert sum(len(v) for v in local_keys.values()) == len(matches)


class TestTheCrossEndpointAnchor:
    """Findings 3 and 4 — `livescores.id` is a decoy; `livescores.oddsid` is the
    season-schedule `id`. This is the pair that decides step 5."""

    def test_livescores_id_reaches_neither_schedule_space(
        self, matches, live_matches
    ):
        schedule_ids = {str(m["id"]) for m in matches}
        schedule_stats_ids = {str(m.get("stats_id") or "") for m in matches} - {""}
        live_ids = [str(m["id"]) for m in live_matches]

        assert len(set(live_ids)) == len(live_ids)
        assert not set(live_ids) & schedule_ids
        assert not set(live_ids) & schedule_stats_ids

    def test_livescores_id_is_shaped_exactly_like_the_stats_id_it_is_not(
        self, matches, live_matches
    ):
        """Why a digit-count or range heuristic would join these and be wrong."""
        live_ids = [str(m["id"]) for m in live_matches]
        stats_ids = [str(m.get("stats_id") or "") for m in matches if m.get("stats_id")]

        assert {len(v) for v in live_ids} == {len(v) for v in stats_ids} == {10}
        assert all(v.startswith("1329") for v in live_ids + stats_ids)
        # Overlapping ranges, and still not one value in common (arm above).
        assert min(live_ids) < max(stats_ids) and min(stats_ids) < max(live_ids)

    def test_oddsid_dereferences_to_the_schedule_row(self, matches, live_matches):
        by_schedule_id = {str(m["id"]): m for m in matches}
        carried = [str(m.get("oddsid") or "") for m in live_matches]
        filled = [o for o in carried if o]

        assert len(filled) == 5, "one live row in this slice carries no oddsid"
        for oddsid in filled:
            assert oddsid in by_schedule_id

    def test_oddsid_joins_the_club_whose_name_the_two_endpoints_spell_differently(
        self, matches, live_matches
    ):
        """`St. Louis Cardinals` on livescores, `St.Louis Cardinals` on the
        schedule. A name key drops this game; the anchor never sees the problem."""
        live = next(m for m in live_matches if "Louis" in m["away"]["name"])
        sched = next(m for m in matches if "Louis" in m["away"]["name"])

        assert live["away"]["name"] != sched["away"]["name"]
        assert str(live["oddsid"]) == str(sched["id"])

    def test_oddsid_is_blank_on_the_hardest_row_in_the_slate(self, live_matches):
        """The second half of the one real doubleheader. The anchor's residue is
        not random — it lands where a name-and-day key is also weakest, so the
        fallback cannot be assumed to cover it."""
        halves = [
            m for m in live_matches
            if m["away"]["name"] == "Detroit Tigers"
        ]
        assert len(halves) == 2
        assert sorted(str(m.get("oddsid") or "") for m in halves) == ["", "354453"]

    def test_time_means_utc_on_one_endpoint_and_et_on_the_other(self, live_matches):
        """Same field name, two bases. livescores alone carries the tiebreaker."""
        for match in live_matches:
            local = datetime.strptime(
                f"{match['date']} {match['time']}", "%d.%m.%Y %H:%M"
            )
            utc = datetime.strptime(match["datetime_utc"], "%d.%m.%Y %H:%M")
            assert match["timezone"] == "ET"
            assert (utc - local).total_seconds() / 3600 == 4

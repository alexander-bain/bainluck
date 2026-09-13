"""CAL-P002: a settled event's stored score MUST be the game's final score.

The forensic anchor (2026-08-05, identity-verified against ESPN finals):

    ev12080400  NHL   we stored BOS 3-1 MIN  · ESPN final BOS 6-3   (frozen mid-game)
    ev12080353  NBA   we stored MIN 45-56 DET · ESPN final 87-109   (a HALFTIME score)
    ev15182558  MLB   we stored SF 2-8 MIL   · ESPN final SF 16-3   (7/28's final on
                                                                     the 7/29 game)

Measured defect rates over identity-verified samples:
    closed  · NHL/NBA/MLB/WNBA   10/399 =  2.5%
    closed  · NCAA Baseball      43/388 = 11.1%
    completed · major 2-9d old   19/70  = 27.1%
    completed · major 30-60d     43/199 = 21.6%

This suite pins the two pure predicates and the sentinel detector. It is the
deliberate counterpart to ``test_espn_score_correction.py`` — see
``TestAuthorityBoundaryWithCorrectedFinalScore`` for why the two rules coexist.
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.tasks.flow_sentinel import frozen_final_score_events
from scripts.repair_event_final_scores import (
    _identity_matches,
    espn_date_matches,
    resolved_home_from_score,
    score_is_stale,
)


class TestScoreIsStale:
    def test_frozen_mid_game_score_is_a_defect(self):
        # The BOS 3-1 / 6-3 anchor: a REAL, plausible, non-zero stored score that
        # is simply not the final. This is the case no existing rail could see.
        assert score_is_stale(3, 1, 6, 3, True) is True

    def test_halftime_score_is_a_defect(self):
        assert score_is_stale(45, 56, 87, 109, True) is True

    def test_wrong_game_from_same_series_is_a_defect(self):
        # ev15182558 held the neighbouring 7/28 game's final.
        assert score_is_stale(2, 8, 16, 3, True) is True

    def test_zero_zero_placeholder_is_a_defect(self):
        assert score_is_stale(0, 0, 9, 6, True) is True

    def test_matching_final_is_not_a_defect(self):
        # The overwhelming majority. Repair must be a no-op here (idempotence).
        assert score_is_stale(5, 4, 5, 4, True) is False
        assert score_is_stale(0, 0, 0, 0, True) is False

    def test_non_final_espn_reading_is_never_a_defect(self):
        # #980/#981: writing a non-final ESPN score is the original corruption.
        # An in-progress ESPN game can NEVER justify a write, however different.
        assert score_is_stale(3, 1, 6, 3, False) is False
        assert score_is_stale(0, 0, 9, 6, False) is False

    def test_missing_scores_are_not_a_defect(self):
        assert score_is_stale(3, 1, None, None, True) is False
        assert score_is_stale(3, 1, 6, None, True) is False
        assert score_is_stale(None, None, 6, 3, True) is False


class TestAuthorityBoundaryWithCorrectedFinalScore:
    """Why this repair may overwrite a real score when ``_corrected_final_score``
    may not — the two rules are complementary, not contradictory.

    ``_corrected_final_score`` runs UNATTENDED inside the box-score backfill on
    events of any age and freshness, so it takes the conservative branch of gotcha
    #21: only a 0-0 placeholder is safe to overwrite without a human in the loop.
    That left the larger half of the defect structurally uncorrectable — CAL-P002
    measured 2.5-27% of settled events holding a wrong, NON-zero final.

    This repair earns the wider authority with three constraints the backfill does
    not have: it is ATTENDED (dry-run first, explicit ``apply=true``), it writes
    only on an ESPN FINAL, and it writes only after a team-identity check proves
    the ESPN row describes the same fixture."""

    def test_corrected_final_score_still_refuses_real_scores(self):
        from app.tasks.espn_sync import _corrected_final_score

        # Unchanged: the unattended rail stays conservative.
        assert _corrected_final_score(3, 2, 5, 4) is None

    def test_this_repair_flags_exactly_what_the_backfill_cannot(self):
        from app.tasks.espn_sync import _corrected_final_score

        assert _corrected_final_score(3, 1, 6, 3) is None  # invisible to the backfill
        assert score_is_stale(3, 1, 6, 3, True) is True    # visible here

    def test_both_agree_a_non_final_is_untouchable(self):
        from app.tasks.espn_sync import _corrected_final_score

        assert _corrected_final_score(0, 0, 6, 3, espn_is_final=False) is None
        assert score_is_stale(0, 0, 6, 3, False) is False


class TestIdentityGuard:
    """An ``espn_id`` pointing at a different game must BLOCK the write. The census
    found 3 such NCAA-Baseball rows; repairing off them would import a wrong score
    rather than remove one (that is an espn_id linkage defect, a different repair)."""

    def test_same_fixture_passes(self):
        assert _identity_matches(
            "Boston Bruins", "Minnesota Wild", "Boston Bruins", "Minnesota Wild"
        ) is True

    def test_partial_names_still_match(self):
        assert _identity_matches(
            "Boston Bruins", "Minnesota Wild", "Bruins", "Wild"
        ) is True

    def test_different_game_is_blocked(self):
        # ev12256979: ours California Baptist vs St. John's; espn_id pointed at
        # Dallas Baptist vs Oklahoma State.
        assert _identity_matches(
            "California Baptist", "St. John's",
            "Dallas Baptist Patriots", "Oklahoma State Cowboys",
        ) is False

    def test_swapped_home_away_is_blocked(self):
        # A swapped fixture is an orientation defect, not a score defect — writing
        # ESPN's home/away onto our reversed row would silently invert the game.
        assert _identity_matches(
            "West Virginia", "Penn State",
            "Penn State Nittany Lions", "West Virginia Mountaineers",
        ) is False

    def test_missing_espn_names_block(self):
        assert _identity_matches("Boston Bruins", "Minnesota Wild", "", "") is False


class TestEspnDateGuard:
    """The guard team-identity cannot provide. In a playoff series the same two
    teams meet repeatedly, so identity passes on EVERY game of the series.

    A simulated repair that trusted identity alone imported neighbouring games'
    finals and RAISED the KXNHLSPREAD disagreement count 8 -> 14. These are the
    exact production rows that regression came from."""

    def _et(self, s):
        from datetime import datetime, timezone

        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)

    def test_same_day_game_passes(self):
        from datetime import date

        # 2026-03-28 21:00Z == 17:00 ET on 03-28.
        assert espn_date_matches(date(2026, 3, 28), self._et("2026-03-28T21:00:00")) is True

    def test_late_night_utc_rolls_back_to_prior_et_day(self):
        from datetime import date

        # 2026-04-30 02:00Z == 22:00 ET on 04-29 — a 7pm PT start. Our game_date is
        # computed on the same ET basis, so this must MATCH, not block.
        assert espn_date_matches(date(2026, 4, 29), self._et("2026-04-30T02:00:00")) is True

    @pytest.mark.parametrize(
        "our,espn",
        [
            ("2026-06-09", "2026-06-07T00:00:00"),  # ev14861878 -> 06-06 ET game
            ("2026-06-11", "2026-06-05T00:00:00"),  # ev14881094 -> 06-04 ET game
            ("2026-05-27", "2026-05-26T00:00:00"),  # ev14792938 -> 05-25 ET game
            ("2026-05-29", "2026-05-23T23:00:00"),  # ev14798909 -> 05-23 ET game
            ("2026-05-16", "2026-05-12T23:00:00"),  # ev14639101 -> 05-12 ET game
        ],
    )
    def test_same_series_neighbour_is_blocked(self, our, espn):
        from datetime import date

        assert espn_date_matches(date.fromisoformat(our), self._et(espn)) is False

    def test_adjacent_day_is_blocked_not_tolerated(self):
        from datetime import date

        # No +/-1 day slack: back-to-backs are a real NHL/NBA pattern, so a one-day
        # tolerance would wave through exactly the defect we are guarding.
        assert espn_date_matches(date(2026, 5, 27), self._et("2026-05-26T18:00:00")) is False

    def test_missing_inputs_block(self):
        from datetime import date

        assert espn_date_matches(None, self._et("2026-03-28T21:00:00")) is False
        assert espn_date_matches(date(2026, 3, 28), None) is False

    def test_naive_datetime_treated_as_utc(self):
        from datetime import date, datetime

        assert espn_date_matches(date(2026, 3, 28), datetime(2026, 3, 28, 21, 0)) is True


class TestResolvedHomeFromScore:
    def test_home_win_away_win_tie(self):
        assert resolved_home_from_score(6, 3) == 1.0
        assert resolved_home_from_score(3, 6) == 0.0
        assert resolved_home_from_score(2, 2) == 0.5

    def test_winner_flip_is_detectable(self):
        # ev15182890: stored LAD 6-7 (away win) vs real LAD 6-2 (home win). The
        # staleness net had already graded the blend off the WRONG side.
        assert resolved_home_from_score(6, 7) != resolved_home_from_score(6, 2)


class TestFrozenFinalScoreDetector:
    """The sentinel detector is pure over the repair's dry-run ledger, so guard and
    repair share ONE definition of the defect."""

    def _ledger(self):
        return [
            {"action": "fix_score", "event_id": 12080400, "sport_key": "icehockey_nhl",
             "matchup": "Boston Bruins vs Minnesota Wild", "status": "closed",
             "stored_score": "3-1", "espn_final": "6-3", "winner_flip": False},
            {"action": "fix_completed_at_only", "event_id": 999, "sport_key": "baseball_mlb"},
            {"action": "skip_identity_mismatch", "event_id": 12256979,
             "sport_key": "baseball_ncaa"},
        ]

    def test_flags_only_score_defects(self):
        found = frozen_final_score_events(self._ledger())
        assert [f["event_id"] for f in found] == [12080400]
        assert found[0]["stored_score"] == "3-1"
        assert found[0]["espn_final"] == "6-3"

    def test_identity_blocked_rows_are_not_reported_as_frozen_scores(self):
        # They are an espn_id linkage defect; filing them here would mis-route the
        # issue and cry wolf on a class this repair deliberately refuses to touch.
        found = frozen_final_score_events(self._ledger())
        assert all(f["event_id"] != 12256979 for f in found)

    def test_clean_ledger_is_green(self):
        assert frozen_final_score_events([]) == []
        assert frozen_final_score_events(
            [{"action": "fix_completed_at_only", "event_id": 1}]
        ) == []

    def test_winner_flip_is_surfaced(self):
        found = frozen_final_score_events([
            {"action": "fix_score", "event_id": 15182890, "sport_key": "baseball_mlb",
             "matchup": "Los Angeles Dodgers vs Seattle Mariners", "status": "completed",
             "stored_score": "6-7", "espn_final": "6-2", "winner_flip": True},
        ])
        assert found[0]["winner_flip"] is True


class TestRepairIsRegisteredOnTheRail:
    def test_registered_and_signature_accepts_bounds(self):
        import inspect

        from app.routes.admin_repairs import _REPAIRS
        from scripts.repair_event_final_scores import repair

        assert _REPAIRS["event-final-scores"] == (
            "scripts.repair_event_final_scores", "repair",
        )
        params = inspect.signature(repair).parameters
        # The dispatcher passes these through only if declared; the repair is
        # unusable over 6k+ events without a bound and a resumable cursor.
        for p in ("limit", "sport", "newest_first", "offset"):
            assert p in params, f"{p} must stay in the signature (dispatcher passthrough)"

    def test_dispatcher_forwards_the_resume_cursor(self):
        import inspect

        from app.routes.admin_repairs import run_repair

        # CAL-P002B: `offset` is useless if the endpoint silently drops it. The
        # dispatcher only forwards params it declares AND the repair names.
        assert "offset" in inspect.signature(run_repair).parameters
        src = inspect.getsource(run_repair)
        assert '("offset", offset)' in src

    def test_dry_run_is_the_default(self):
        import inspect

        from scripts.repair_event_final_scores import repair

        assert inspect.signature(repair).parameters["apply"].default is inspect.Parameter.empty
        # apply is positional-required on the rail contract fn(session, apply);
        # the ENDPOINT defaults it to False. Pin that here so it can't regress.
        from app.routes.admin_repairs import run_repair

        assert inspect.signature(run_repair).parameters["apply"].default.default is False


@pytest.mark.parametrize(
    "ours,espn,expected",
    [
        ((3, 1), (6, 3), True),    # NHL frozen mid-game
        ((2, 8), (16, 3), True),   # MLB wrong-game-from-series
        ((45, 56), (87, 109), True),  # NBA halftime
        ((5, 4), (5, 4), False),   # healthy
        ((1, 0), (1, 0), False),   # healthy low-scoring
    ],
)
def test_anchor_table(ours, espn, expected):
    assert score_is_stale(ours[0], ours[1], espn[0], espn[1], True) is expected


# ---------------------------------------------------------------------------
# CAL-P002B — end-to-end tests of repair() itself.
#
# THE GAP THIS CLOSES. CAL-P002 shipped 38 tests, all of them on the pure
# predicates, and zero on repair(). The predicates were right; the repair was
# still unusable in production for two reasons nothing in the suite could see:
#
#   1. `limit` bounded the ESPN calls but not the SCAN. Candidate rows were
#      fetched for the WHOLE population, each carrying two correlated MAX()
#      subqueries, and the slice to `limit` groups happened in Python afterwards.
#      Every unscoped call H12'd at the 30s router wall (measured 2026-08-07:
#      limit=3 and limit=25 alike, 30.27s), so the two cohorts holding 179 of the
#      241 known defects — baseball_mlb and baseball_ncaa — were unreachable.
#   2. It was NOT resumable. The group predicate is unchanged by the repair, so
#      `ordered[:limit]` returned the same oldest groups on every invocation and
#      `groups_remaining` never fell. "Re-invoke until groups_remaining is 0"
#      could not terminate.
#
# Both are properties of the candidate scan and the cursor, not of any predicate,
# so they are tested here against a session that records the SQL it is asked to
# run and the parameters it is asked to run it with.
# ---------------------------------------------------------------------------
UTC = timezone.utc


def _espn_game(espn_id, home, away, home_score, away_score, when, status="post"):
    return SimpleNamespace(
        espn_id=espn_id, status=status, date=when,
        home_team=SimpleNamespace(display_name=home, name=home, short_name=home),
        away_team=SimpleNamespace(display_name=away, name=away, short_name=away),
        home_score=home_score, away_score=away_score,
    )


# Three (sport, date) groups, four events. The NBA row is the halftime anchor
# with the winner flipped; the rest are healthy.
_GROUPS = [
    SimpleNamespace(sport_key="basketball_nba", game_date=date(2026, 5, 1), n=1),
    SimpleNamespace(sport_key="baseball_mlb", game_date=date(2026, 5, 2), n=2),
    SimpleNamespace(sport_key="icehockey_nhl", game_date=date(2026, 5, 3), n=1),
]

_EVENTS = [
    SimpleNamespace(
        event_id=12080353, espn_id="401", sport_key="basketball_nba", ev_status="closed",
        home_team_name="Detroit Pistons", away_team_name="Minnesota Timberwolves",
        # A literal halftime score, frozen: away ahead 56-45. ESPN's final is
        # 109-87 the OTHER way, so the derived "away won" is also wrong.
        home_score=45, away_score=56,
        commence_time=datetime(2026, 5, 1, 23, 0, tzinfo=UTC),
        completed_at=datetime(2026, 5, 2, 2, 0, tzinfo=UTC), game_date=date(2026, 5, 1),
    ),
    SimpleNamespace(
        event_id=15182558, espn_id="402", sport_key="baseball_mlb", ev_status="completed",
        home_team_name="Milwaukee Brewers", away_team_name="San Francisco Giants",
        home_score=3, away_score=16,
        commence_time=datetime(2026, 5, 2, 23, 0, tzinfo=UTC),
        completed_at=datetime(2026, 5, 3, 2, 0, tzinfo=UTC), game_date=date(2026, 5, 2),
    ),
    SimpleNamespace(
        event_id=15182559, espn_id="403", sport_key="baseball_mlb", ev_status="completed",
        home_team_name="Chicago Cubs", away_team_name="St. Louis Cardinals",
        home_score=4, away_score=2,
        commence_time=datetime(2026, 5, 2, 23, 30, tzinfo=UTC),
        completed_at=None, game_date=date(2026, 5, 2),
    ),
    SimpleNamespace(
        event_id=12080400, espn_id="404", sport_key="icehockey_nhl", ev_status="closed",
        home_team_name="Boston Bruins", away_team_name="Minnesota Wild",
        home_score=6, away_score=3,
        commence_time=datetime(2026, 5, 3, 23, 0, tzinfo=UTC),
        completed_at=datetime(2026, 5, 4, 2, 0, tzinfo=UTC), game_date=date(2026, 5, 3),
    ),
]

_BOARDS = {
    ("basketball_nba", "20260501"): [
        # 56-45 stored, 109-87 final: a real defect AND a winner flip.
        _espn_game("401", "Detroit Pistons", "Minnesota Timberwolves", 109, 87,
                   datetime(2026, 5, 1, 23, 0, tzinfo=UTC)),
    ],
    ("baseball_mlb", "20260502"): [
        _espn_game("402", "Milwaukee Brewers", "San Francisco Giants", 3, 16,
                   datetime(2026, 5, 2, 23, 0, tzinfo=UTC)),
        _espn_game("403", "Chicago Cubs", "St. Louis Cardinals", 4, 2,
                   datetime(2026, 5, 2, 23, 30, tzinfo=UTC)),
    ],
    ("icehockey_nhl", "20260503"): [
        _espn_game("404", "Boston Bruins", "Minnesota Wild", 6, 3,
                   datetime(2026, 5, 3, 23, 0, tzinfo=UTC)),
    ],
}


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _RecordingSession:
    """A session that answers the repair's queries and records what it was asked.

    Deliberately dispatches on SQL text: the property under test is *which query
    runs with which bounds*, which is exactly what a mock returning blanket empty
    results cannot express.
    """

    def __init__(self, grades_per_event=None):
        self.calls = []          # (sql, params)
        self.score_writes = []
        self.completed_at_writes = []
        self.blend_writes = 0
        self.commits = 0
        # Queue 067: event_id -> how many EVENTS_DERIVED_SOURCES grades sit on
        # it. Defaults to none, so every pre-existing test keeps its old shape.
        self.grades_per_event = grades_per_event or {}
        self.grade_retractions = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.calls.append((sql, params or {}))

        # Queue 067 — BEFORE the population count, which also says
        # "COUNT(*) AS n". Dispatching on the table keeps them apart.
        if "futures_outcomes" in sql:
            if sql.startswith("SELECT") or "SELECT COUNT" in sql:
                n = self.grades_per_event.get(params["event_id"], 0)
                return _Result([SimpleNamespace(n=n)])
            self.grade_retractions.append(params)
            return SimpleNamespace(
                rowcount=self.grades_per_event.get(params["event_id"], 0)
            )

        if "GROUP BY 1, 2" in sql:
            return _Result(list(_GROUPS))
        if "unnest(" in sql:
            wanted = set(zip(params["g_sports"], params["g_dates"]))
            return _Result([e for e in _EVENTS if (e.sport_key, e.game_date) in wanted])
        if "MAX(x.captured_at)" in sql:
            # Only event 15182559 has a usable post-commence snapshot.
            return _Result([
                SimpleNamespace(event_id=i, last_snap=datetime(2026, 5, 3, 3, 0, tzinfo=UTC))
                for i in params["event_ids"] if i == 15182559
            ])
        if "COUNT(*) AS n" in sql:
            return _Result([SimpleNamespace(n=sum(g.n for g in _GROUPS))])
        if "UPDATE events SET home_score" in sql:
            self.score_writes.append(params)
            return _Result([])
        if "UPDATE events SET completed_at" in sql:
            self.completed_at_writes.append(params)
            return _Result([])
        if sql.startswith("SELECT events.win_probability_sources"):
            return _Result([{"final_result": {"probability": 0.0}}])
        if sql.startswith("UPDATE events SET win_probability_sources"):
            self.blend_writes += 1
            return _Result([])
        raise AssertionError(f"unexpected SQL: {sql[:160]}")

    async def commit(self):
        self.commits += 1


def _fake_espn():
    svc = SimpleNamespace()
    svc.get_scoreboard = AsyncMock(
        side_effect=lambda sport_key, d: list(_BOARDS.get((sport_key, d), []))
    )
    return svc


async def _run(**kw):
    from scripts import repair_event_final_scores as mod

    s = _RecordingSession(kw.pop("grades_per_event", None))
    with patch("app.services.espn_api.get_espn_service", return_value=_fake_espn()):
        res = await mod.repair(s, kw.pop("apply", False), **kw)
    return s, res


def _candidate_params(session):
    return [p for sql, p in session.calls if "unnest(" in sql]


class TestScanIsBoundedBeforeTheWork:
    """`limit` must bound the SCAN, not just the ESPN calls."""

    @pytest.mark.asyncio
    async def test_only_the_selected_groups_are_fetched(self):
        from app.utils.sport_keys import ESPN_SPORT_MAPPING

        s, res = await _run(limit=1)
        # THE regression: pre-fix this query ran over the whole population.
        assert _candidate_params(s) == [{
            "sport_keys": sorted(ESPN_SPORT_MAPPING),
            "g_sports": ["basketball_nba"],
            "g_dates": [date(2026, 5, 1)],
        }]
        assert res["groups_scanned"] == 1
        assert res["events_scanned"] == 1

    @pytest.mark.asyncio
    async def test_the_group_bound_runs_before_any_candidate_fetch(self):
        s, _ = await _run(limit=1)
        order = [i for i, (sql, _) in enumerate(s.calls)
                 if "GROUP BY 1, 2" in sql or "unnest(" in sql]
        first, second = s.calls[order[0]][0], s.calls[order[1]][0]
        assert "GROUP BY 1, 2" in first
        assert "unnest(" in second

    @pytest.mark.asyncio
    async def test_zero_selected_groups_fetches_no_candidates(self):
        s, res = await _run(limit=0)
        assert _candidate_params(s) == []
        assert res["groups_scanned"] == 0

    def test_no_correlated_subquery_rides_on_every_candidate_row(self):
        from scripts.repair_event_final_scores import _CANDIDATE_SQL, _GROUPS_SQL

        # The two correlated MAX() subqueries were the whole cost. They now live
        # in a separate batched query run only for rows with a NULL completed_at.
        assert "SELECT MAX(" not in _CANDIDATE_SQL
        assert "SELECT MAX(" not in _GROUPS_SQL

    def test_all_three_queries_share_one_predicate(self):
        from scripts.repair_event_final_scores import (
            _CANDIDATE_SQL,
            _GROUPS_SQL,
            _POPULATION_SQL,
            _SETTLED_PREDICATE,
        )

        # A bound computed over a different population than the work is not a bound.
        for sql in (_GROUPS_SQL, _CANDIDATE_SQL, _POPULATION_SQL):
            assert _SETTLED_PREDICATE in sql

    @pytest.mark.asyncio
    async def test_completed_at_derivation_is_lazy(self):
        # Only the group holding the NULL-completed_at row pays for the snapshot
        # query; a group of healthy rows must not trigger it at all.
        s_nba, _ = await _run(limit=1)
        assert not [1 for sql, _ in s_nba.calls if "MAX(x.captured_at)" in sql]

        s_mlb, _ = await _run(limit=1, offset=1)
        snaps = [p for sql, p in s_mlb.calls if "MAX(x.captured_at)" in sql]
        assert snaps == [{"event_ids": [15182559]}]


class TestResumability:
    """The shipped contract could never terminate; the cursor must."""

    @pytest.mark.asyncio
    async def test_offset_selects_a_different_group(self):
        _, first = await _run(limit=1, offset=0)
        _, second = await _run(limit=1, offset=1)
        assert first["next_offset"] == 1
        assert second["groups_offset"] == 1
        assert second["next_offset"] == 2

    @pytest.mark.asyncio
    async def test_a_driver_loop_covers_every_group_exactly_once(self):
        seen, offset, guard = [], 0, 0
        while True:
            guard += 1
            assert guard < 20, "driver loop did not terminate — the CAL-P002 bug"
            s, res = await _run(limit=1, offset=offset)
            seen += [p["g_sports"][0] for p in _candidate_params(s)]
            offset = res["next_offset"]
            if res["groups_remaining"] == 0:
                break
        assert seen == ["basketball_nba", "baseball_mlb", "icehockey_nhl"]
        assert len(seen) == len(set(seen))

    @pytest.mark.asyncio
    async def test_groups_remaining_is_measured_against_the_cursor(self):
        _, res = await _run(limit=2, offset=0)
        assert (res["groups_total"], res["groups_remaining"]) == (3, 1)
        _, res = await _run(limit=2, offset=2)
        assert res["groups_remaining"] == 0

    @pytest.mark.asyncio
    async def test_newest_first_walks_the_other_end(self):
        s, _ = await _run(limit=1, newest_first=True)
        assert _candidate_params(s)[0]["g_sports"] == ["icehockey_nhl"]


class TestDeadline:
    @pytest.mark.asyncio
    async def test_an_exhausted_budget_stops_before_the_router_does(self):
        _, res = await _run(limit=3, deadline_seconds=0.0)
        assert res["stopped_on_deadline"] is True
        assert res["groups_scanned"] == 0
        # A truthful cursor: a deadline stop must not advance past unscanned work.
        assert res["next_offset"] == 0
        assert res["groups_remaining"] == 3

    @pytest.mark.asyncio
    async def test_a_normal_run_does_not_report_a_deadline_stop(self):
        _, res = await _run(limit=3)
        assert res["stopped_on_deadline"] is False
        assert res["groups_scanned"] == 3


class TestApplyPath:
    @pytest.mark.asyncio
    async def test_dry_run_writes_nothing(self):
        s, res = await _run(limit=3, apply=False)
        assert (s.score_writes, s.commits, s.blend_writes) == ([], 0, 0)
        assert res["score_defects"] == 1 and res["scores_repaired"] == 0

    @pytest.mark.asyncio
    async def test_apply_writes_the_espn_final_and_restamps_the_blend(self):
        s, res = await _run(limit=3, apply=True)
        assert s.score_writes == [
            {"event_id": 12080353, "home_score": 109, "away_score": 87},
        ]
        # The staleness net graded the blend off the frozen 45-56 (an away win)
        # when the real final 109-87 is a HOME win, so the derived final that
        # calibration grades against is inverted and must be restamped.
        assert res["winner_flips"] == 1
        assert s.blend_writes == 1
        assert s.commits >= 1

    @pytest.mark.asyncio
    async def test_healthy_rows_are_left_alone(self):
        s, res = await _run(limit=1, offset=2, apply=True)
        assert s.score_writes == [] and res["score_defects"] == 0

    @pytest.mark.asyncio
    async def test_completed_at_gap_is_filled_from_the_last_real_snapshot(self):
        s, res = await _run(limit=1, offset=1, apply=True)
        assert res["completed_at_gaps"] == 1
        assert s.completed_at_writes == [{
            "event_id": 15182559,
            "completed_at": datetime(2026, 5, 3, 3, 0, tzinfo=UTC),
        }]


# ---------------------------------------------------------------------------
# QUEUE 067 — the grades that stood on the score this rail replaces.
#
# Correcting `events.home_score`/`away_score` invalidates every outcome graded
# FROM those columns, and this rail used to leave them untouched. That is not
# cosmetic: `game_score` and its EVENTS_DERIVED_SOURCES siblings are tier 2 but
# NOT in OVERWRITABLE_WINNER_SOURCES, so `backfill_winners`' re-resolution HAVING
# clause excludes any market carrying one — forever. Fixing the score under a
# `game_score` grade changed nothing anybody could see.
#
# Fixture 12080353 is the score defect (45-56 stored, 109-87 final); 15182559 is
# the control — its score already matches ESPN and only its completed_at is
# repaired, so nothing about its grades has been disproven.
# ---------------------------------------------------------------------------
_GRADES = {12080353: 7, 15182559: 5}


class TestStaleGradesAreRetracted:

    @pytest.mark.asyncio
    async def test_a_corrected_score_retracts_the_grades_derived_from_it(self):
        s, res = await _run(apply=True, limit=25, grades_per_event=_GRADES)
        assert [p["event_id"] for p in s.grade_retractions] == [12080353]
        assert res["grades_retracted"] == 7

    @pytest.mark.asyncio
    async def test_an_event_whose_score_was_never_wrong_keeps_its_grades(self):
        # 15182559 gets a completed_at repair and nothing else. A repair that
        # un-grades on the strength of an unrelated write is worse than the bug.
        s, _ = await _run(apply=True, limit=25, grades_per_event=_GRADES)
        assert 15182559 not in [p["event_id"] for p in s.grade_retractions]
        assert s.completed_at_writes, "the control must still get its own repair"

    @pytest.mark.asyncio
    async def test_only_events_derived_sources_are_retracted(self):
        # A venue's settlement said what it said; our score being wrong does not
        # disprove it, and it outranks these grades anyway. The source list is
        # imported from the ladder, never restated here — that is the point.
        from app.utils.resolution_authority import (
            AUTHORITATIVE_SOURCES,
            EVENTS_DERIVED_SOURCES,
        )

        s, _ = await _run(apply=True, limit=25, grades_per_event=_GRADES)
        sources = set(s.grade_retractions[0]["sources"])
        assert sources == set(EVENTS_DERIVED_SOURCES)
        assert not (sources & AUTHORITATIVE_SOURCES)
        assert "game_score" in sources and "box_score" in sources

    @pytest.mark.asyncio
    async def test_the_dry_run_names_the_grades_it_would_un_grade(self):
        # An operator approving a score fix must see that it also un-grades
        # rows. A plan that hides half its writes is not a plan.
        s, res = await _run(apply=False, limit=25, grades_per_event=_GRADES)
        assert s.grade_retractions == []
        assert res["grades_retracted"] == 0
        assert res["grades_to_retract"] == 7
        entry = [e for e in res["ledger"] if e["event_id"] == 12080353][0]
        assert entry["events_derived_grades"] == 7
        assert entry["grade_action"] == "retract_for_regrade"

    @pytest.mark.asyncio
    async def test_planned_and_applied_counts_agree(self):
        # Two counters, not one: "it returned" is not "it worked" (gotcha #53).
        _, res = await _run(apply=True, limit=25, grades_per_event=_GRADES)
        assert res["grades_to_retract"] == res["grades_retracted"] == 7

    @pytest.mark.asyncio
    async def test_an_event_with_no_derived_grades_is_not_churned(self):
        # The score is still repaired; there is simply nothing to retract, and
        # no UPDATE is issued against futures_outcomes.
        s, res = await _run(apply=True, limit=25, grades_per_event={})
        assert s.score_writes, "the score defect must still be repaired"
        assert s.grade_retractions == []
        assert res["grades_to_retract"] == res["grades_retracted"] == 0

    @pytest.mark.asyncio
    async def test_the_retraction_rides_the_same_commit_as_the_score(self):
        # If the score lands and the retraction does not, the grades outlive the
        # value they were computed from — the exact state this repairs.
        s, _ = await _run(apply=True, limit=25, grades_per_event=_GRADES)
        order = [
            "score" if "UPDATE events SET home_score" in sql
            else "retract" if "UPDATE futures_outcomes" in sql
            else "commit?"
            for sql, _p in s.calls
            if "UPDATE events SET home_score" in sql or "UPDATE futures_outcomes" in sql
        ]
        assert order == ["score", "retract"]
        assert s.commits >= 1

    def test_is_winner_goes_to_unknown_and_never_to_a_graded_loss(self):
        # NULL is UNKNOWN truth; False is an affirmative graded LOSS (see the
        # FuturesOutcome.is_winner column comment). Retracting to False would
        # publish a fabricated loss — the CAL-P056 class, one layer over.
        from scripts.repair_event_final_scores import (
            _RETRACT_EVENTS_DERIVED_GRADES_SQL as sql,
        )

        assert "is_winner = NULL" in sql
        assert "resolution_source = NULL" in sql
        assert "is_winner = false" not in sql.lower()

    def test_the_retraction_makes_the_market_regradeable_again(self):
        # The whole mechanism: `backfill_winners` re-resolves a market only when
        # no outcome carries `is_winner AND resolution_source NOT IN
        # <overwritable>`. game_score is not in that set, so clearing BOTH
        # columns is what puts the market back in front of the real grader.
        from app.utils.resolution_authority import (
            EVENTS_DERIVED_SOURCES,
            OVERWRITABLE_WINNER_SOURCES,
        )

        blocking = EVENTS_DERIVED_SOURCES - set(OVERWRITABLE_WINNER_SOURCES)
        assert "game_score" in blocking, (
            "if game_score ever becomes overwritable this retraction is "
            "unnecessary — and this test should be the thing that says so"
        )

"""#6590 repair — the gates in front of a write that un-says a crowned Draw.

THE DEFECT THIS REPAIRS. `/futures/60015154` badges BOTH `SK Beveren` and
`Draw (SK Beveren vs. Oud-Heverlee Leuven)` as `Won · 100% Settled` on a match
that finished 3-0. The producer fix in this same commit stops the next one; it
cannot reach this row, because `game_score` is not overwritable and both
resolvers skip a market that already holds a non-overwritable TRUE winner.

WHY THESE ARE PURE/SEEDED GUARDS AND NOT DATABASE GUARDS. Every real-Postgres
gate in this repo is env-gated and SKIPS in CI, which has no Postgres service,
and a skipped guard is not a guard. So the repair's statements live behind a
six-method store seam and `MemoryStore` drives the REAL sequence — plan, backup,
apply, restore — over seeded rows.

🔴 THE ONE THING A ONE-SIDED TEST CANNOT SEE. A screen that refuses everything
passes every "the segment market is refused" test ever written. So both
directions are asserted: `TestTheRowThisExistsFor` proves the draw IS demoted
and the write lands, and `TestTheRowsItMustNotTouch` proves the fourteen
production rows #5221 owns are refused BY NAME. The decisive acquittal is
`test_a_match_that_really_was_level_keeps_its_draw_6590` — a filter that judged
by "is a draw leg crowned" alone would destroy every correct draw we store.
"""

import argparse
import importlib
import os
import sys

import pytest


@pytest.fixture(scope="module")
def repair():
    """The repair module, imported by path the way `scripts/` modules are."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module("scripts.repair_6590_a_draw_crowned_as_a_team")


def _args(**kw):
    base = dict(backup=False, apply=False, restore=False, allow_new=False)
    base.update(kw)
    return argparse.Namespace(**base)


# ── the seeded world ─────────────────────────────────────────────────────────

#: The real market, in the shape production stores it: two legs, BOTH TRUE,
#: on an event that finished 3-0. Values read off production 2026-09-16 18:4xZ.
def _the_real_corrupt_market():
    common = dict(
        market_id=60015154,
        market_type="duel",
        market_name="SK Beveren vs. Oud-Heverlee Leuven",
        resolution_source="game_score",
        event_id=15298068,
        event_status="completed",
        home_score=3,
        away_score=0,
    )
    return [
        dict(common, outcome_id=223837848, outcome_name="SK Beveren", is_winner=True),
        dict(common, outcome_id=223837849,
             outcome_name="Draw (SK Beveren vs. Oud-Heverlee Leuven)", is_winner=True),
    ]


#: The fourteen rows this repair must refuse, taken from production rather than
#: invented — every one is a real `Tie` leg stored TRUE on a real half-winner
#: market whose GAME was not level. They belong to #5221.
FIFTEEN_MINUS_ONE = [
    (1623916, 112649, "Creighton vs UConn: First Half Winner", 84, 91),
    (3744237, 541912, "Portland vs Phoenix: First Half Winner", 77, 92),
    (3744541, 541949, "Boston vs Los Angeles L: First Half Winner", 89, 111),
    (5883920, 960183, "Charlotte vs Chicago: First Half Winner", 99, 131),
    (7500920, 1258740, "Cleveland vs Milwaukee: First Half Winner", 118, 116),
    (12190069, 2104873, "Memphis vs Indiana: First Half Winner", 106, 125),
    (14004038, 2418893, "Baylor vs Houston: First Half Winner", 77, 64),
    (14649358, 2521597, "Michigan vs Iowa: First Half Winner", 68, 71),
    (14898552, 2562761, "Detroit vs San Antonio: Second Half Winner", 121, 106),
    (18964119, 3218674, "Indiana vs Portland: First Half Winner", 131, 111),
    (21573355, 3650216, "Toronto vs Houston: First Half Winner", 113, 99),
    (21742468, 3676940, "Memphis vs Philadelphia: First Half Winner", 139, 129),
    (23625844, 3973832, "Phoenix vs Indiana: First Half Winner", 108, 123),
    (31626965, 6185550, "Oklahoma City vs Washington: First Half Winner", 111, 132),
]


def _half_winner_row(outcome_id, market_id, market_name, home, away):
    return dict(
        outcome_id=outcome_id, market_id=market_id, market_type="field",
        market_name=market_name, outcome_name="Tie", is_winner=True,
        resolution_source="game_score", event_id=market_id, event_status="completed",
        home_score=home, away_score=away,
    )


class MemoryStore:
    """The store seam, backed by seeded rows instead of Postgres.

    It implements the SEMANTICS the SQL has, not a convenience: `demote` is a
    compare-and-swap that skips a row already FALSE, `backup_missing` returns an
    empty mapping while no backup table exists (so `backup_is_exact` is False and
    `--apply` refuses), and `restore` writes back the value that was copied.
    """

    def __init__(self, rows):
        self.rows = [dict(r) for r in rows]
        self.backup = None          # None == the table does not exist yet
        self.writes = 0

    def _by_id(self, oid):
        return next(r for r in self.rows if r["outcome_id"] == oid)

    async def fetch_candidates(self):
        # Mirrors `_PLAN_SQL`'s WHERE clause.
        out = []
        for r in self.rows:
            if not r["is_winner"]:
                continue
            if r["resolution_source"] != "game_score":
                continue
            if not repair_module.is_draw_outcome(r["outcome_name"]):
                continue
            if r["event_status"] != "completed":
                continue
            if r["home_score"] is None or r["away_score"] is None:
                continue
            if r["home_score"] == r["away_score"]:
                continue
            out.append(dict(r))
        return out

    async def fetch_market_legs(self, market_ids):
        legs = {}
        for r in self.rows:
            if r["market_id"] in set(market_ids):
                legs.setdefault(r["market_id"], []).append(dict(r))
        return legs

    async def copy_to_backup(self, ids):
        if self.backup is None:
            self.backup = {}
        for oid in ids:
            self.backup.setdefault(oid, self._by_id(oid)["is_winner"])

    async def backup_missing(self, ids):
        if self.backup is None:
            return {}
        return {"missing": sum(1 for oid in ids if oid not in self.backup)}

    async def demote(self, ids):
        n = 0
        for oid in ids:
            row = self._by_id(oid)
            if row["is_winner"]:      # the CAS
                row["is_winner"] = False
                n += 1
        self.writes += n
        return n

    async def restore(self):
        if self.backup is None:
            return 0
        for oid, was in self.backup.items():
            self._by_id(oid)["is_winner"] = was
        return len(self.backup)

    # test helpers
    def winners(self, market_id=60015154):
        return [r["outcome_id"] for r in self.rows
                if r["market_id"] == market_id and r["is_winner"]]


repair_module = None


@pytest.fixture(autouse=True)
def _bind(repair):
    global repair_module
    repair_module = repair
    return repair


# ── direction 1: the row this repair exists for ──────────────────────────────

class TestTheRowThisExistsFor:

    @pytest.mark.asyncio
    async def test_the_draw_is_planned_and_the_team_leg_is_not_6590(self, repair):
        store = MemoryStore(_the_real_corrupt_market())
        report = await repair.execute_repair(store, _args())

        assert report.planned == [223837849]
        assert report.blocked is None

    @pytest.mark.asyncio
    async def test_a_dry_run_writes_nothing_6590(self, repair):
        store = MemoryStore(_the_real_corrupt_market())
        report = await repair.execute_repair(store, _args())

        assert report.wrote == 0
        assert store.writes == 0
        assert store.winners() == [223837848, 223837849], "still two winners"

    @pytest.mark.asyncio
    async def test_backup_then_apply_leaves_exactly_one_winner_6590(self, repair):
        store = MemoryStore(_the_real_corrupt_market())
        await repair.execute_repair(store, _args(backup=True))
        report = await repair.execute_repair(store, _args(apply=True))

        assert report.wrote == 1
        assert store.winners() == [223837848], "the team that won 3-0, and only it"
        assert report.blocked is None

    @pytest.mark.asyncio
    async def test_restore_puts_the_crowned_draw_back_6590(self, repair):
        """The undo is load-bearing: D51(b) is what makes this unattended-safe."""
        store = MemoryStore(_the_real_corrupt_market())
        await repair.execute_repair(store, _args(backup=True))
        await repair.execute_repair(store, _args(apply=True))
        assert store.winners() == [223837848]

        report = await repair.execute_repair(store, _args(restore=True))

        assert report.restored == 1
        assert store.winners() == [223837848, 223837849], "back as it was found"

    @pytest.mark.asyncio
    async def test_apply_refuses_without_a_backup_6590(self, repair):
        """gotcha #53 — an empty reconciliation must not read as a clean pass."""
        store = MemoryStore(_the_real_corrupt_market())
        report = await repair.execute_repair(store, _args(apply=True))

        assert report.blocked and "backup does not cover" in report.blocked
        assert store.writes == 0
        assert store.winners() == [223837848, 223837849]

    @pytest.mark.asyncio
    async def test_applying_twice_writes_once_6590(self, repair):
        """The CAS: a row already FALSE is not written again."""
        store = MemoryStore(_the_real_corrupt_market())
        await repair.execute_repair(store, _args(backup=True))
        await repair.execute_repair(store, _args(apply=True))
        second = await repair.execute_repair(store, _args(apply=True))

        assert second.planned == [], "the row no longer matches the predicate"
        assert store.winners() == [223837848]


# ── direction 2: the rows it must NOT touch ──────────────────────────────────

class TestTheRowsItMustNotTouch:

    @pytest.mark.parametrize("oid,mid,name,home,away", FIFTEEN_MINUS_ONE)
    def test_a_half_winner_tie_is_refused_by_name_6590(
        self, repair, oid, mid, name, home, away
    ):
        """#5221 owns these. A half CAN be tied on a game that was not."""
        screen = repair.screen_candidates([_half_winner_row(oid, mid, name, home, away)])

        assert screen.plan == []
        assert [r.outcome_id for r in screen.refuse] == [oid]
        assert "SEGMENT" in screen.refuse[0].reason

    def test_the_whole_production_cohort_splits_one_from_fourteen_6590(self, repair):
        """The measurement this repair was sized on, as a guard."""
        rows = _the_real_corrupt_market() + [
            _half_winner_row(*r) for r in FIFTEEN_MINUS_ONE
        ]
        screen = repair.screen_candidates(rows)

        assert screen.plan == [223837849]
        assert len(screen.refuse) == 15, "the team leg plus the fourteen"

    def test_a_match_that_really_was_level_keeps_its_draw_6590(self, repair):
        """The acquittal a naive 'a draw is crowned' filter would destroy."""
        rows = [dict(r, home_score=1, away_score=1) for r in _the_real_corrupt_market()]
        screen = repair.screen_candidates(rows)

        assert screen.plan == []
        assert any("WAS level" in r.reason for r in screen.refuse)

    def test_a_draw_on_an_unfinished_event_is_refused_6590(self, repair):
        rows = [dict(r, event_status="live") for r in _the_real_corrupt_market()]
        screen = repair.screen_candidates(rows)

        assert screen.plan == []
        assert any("not completed" in r.reason for r in screen.refuse)

    def test_a_leg_another_writer_graded_is_refused_6590(self, repair):
        """`game_score` is the only verdict this repair has any standing over."""
        rows = [dict(r, resolution_source="api_settlement")
                for r in _the_real_corrupt_market()]
        screen = repair.screen_candidates(rows)

        assert screen.plan == []
        assert any("api_settlement" in r.reason for r in screen.refuse)

    def test_a_non_whole_game_market_type_is_refused_6590(self, repair):
        """Second, independent guard against the segment cohort."""
        rows = [dict(r, market_type="field", market_name="Some Cup Winner")
                for r in _the_real_corrupt_market()]
        screen = repair.screen_candidates(rows)

        assert screen.plan == []
        assert any("whole-game" in r.reason for r in screen.refuse)


# ── the gates in front of the write ──────────────────────────────────────────

class TestTheGates:

    def test_an_unmeasured_row_stops_the_repair_6590(self, repair):
        blocked = repair.identity_refusal([223837849, 999999], allow_new=False)

        assert blocked and "never measured" in blocked

    def test_allow_new_is_the_only_way_past_it_6590(self, repair):
        assert repair.identity_refusal([223837849, 999999], allow_new=True) is None

    def test_the_measured_cohort_passes_6590(self, repair):
        assert repair.identity_refusal([223837849], allow_new=False) is None

    @pytest.mark.asyncio
    async def test_a_write_that_would_leave_no_winner_is_refused_6590(self, repair):
        """CERT-2631's lesson: no verdict is worse than the wrong verdict."""
        rows = _the_real_corrupt_market()
        rows[0]["is_winner"] = False          # the team leg is already not a winner
        store = MemoryStore(rows)

        report = await repair.execute_repair(store, _args(backup=True, apply=True))

        assert report.blocked and "exactly one winner" in report.blocked
        assert store.writes == 0

    def test_backup_is_exact_refuses_an_empty_reconciliation_6590(self, repair):
        assert repair.backup_is_exact({}) is False
        assert repair.backup_is_exact({"missing": 1}) is False
        assert repair.backup_is_exact({"missing": 0}) is True

    def test_a_write_off_the_named_app_is_refused_6590(self, repair, monkeypatch):
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        assert "REFUSING to write" in repair.wrong_app_refusal(_args(apply=True))
        assert "REFUSING to write" in repair.wrong_app_refusal(_args(backup=True))
        assert "REFUSING to write" in repair.wrong_app_refusal(_args(restore=True))

    def test_a_dry_run_is_allowed_anywhere_6590(self, repair, monkeypatch):
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        assert repair.wrong_app_refusal(_args()) is None

    def test_the_named_app_may_write_6590(self, repair, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)
        assert repair.wrong_app_refusal(_args(apply=True)) is None


# ── the recognisers ──────────────────────────────────────────────────────────

class TestRecognisers:

    @pytest.mark.parametrize("name", [
        "Draw (SK Beveren vs. Oud-Heverlee Leuven)", "Draw", "Tie", "draw",
    ])
    def test_a_draw_leg_is_recognised_6590(self, repair, name):
        assert repair.is_draw_outcome(name) is True

    @pytest.mark.parametrize("name", [
        "SK Beveren", "Oud-Heverlee Leuven", "Drawbridge United", None, "",
    ])
    def test_a_team_leg_is_not_a_draw_leg_6590(self, repair, name):
        assert repair.is_draw_outcome(name) is False

    @pytest.mark.parametrize("name", [
        "Creighton vs UConn: First Half Winner",
        "Detroit vs San Antonio: Second Half Winner",
        "Lakers vs Suns: 1H Winner",
        "Team A vs Team B: Q1 Winner",
    ])
    def test_a_segment_market_is_recognised_6590(self, repair, name):
        assert repair.names_a_segment(name) is True

    @pytest.mark.parametrize("name", [
        "SK Beveren vs. Oud-Heverlee Leuven",
        "Arsenal vs Chelsea",
        "Champions League Winner",
    ])
    def test_a_whole_game_market_is_not_a_segment_6590(self, repair, name):
        assert repair.names_a_segment(name) is False

"""#1798 — the team-binding repair must see what name checks cannot, and guess nothing.

The whole point of this repair is that it dereferences the foreign key. So the
central test is the one where **every name on the row is correct** and only the id
is wrong — the exact shape that made 153 miswired sides invisible to a codebase
full of name comparisons.
"""

from datetime import date, datetime

import pytest

from app.tasks.repair_event_team_binding import _as_date, _classify, _norm, repair

MLB = 53232
PRESEASON = 33178


class TestClassify:
    """The predicate, in isolation. One side, one verdict."""

    def test_sound_binding_is_not_a_defect(self):
        assert _classify("Boston Red Sox", "Boston Red Sox", MLB, MLB) is None

    def test_cross_club_is_caught(self):
        assert _classify("Boston Red Sox", "Minnesota Twins", PRESEASON, MLB) == "cross_club"

    def test_wrong_sport_twin_is_caught_and_named_separately(self):
        """Right club, wrong half of the duplicate pair — a different defect."""
        assert _classify("Boston Red Sox", "Boston Red Sox", PRESEASON, MLB) == "wrong_sport"

    def test_unbound_side_is_not_a_defect(self):
        """A NULL id is a coverage gap, not a miswiring. Do not conflate them."""
        assert _classify("Boston Red Sox", None, None, MLB) is None

    def test_punctuation_and_case_are_not_a_disagreement(self):
        assert _classify("St. Louis Cardinals", "St.Louis Cardinals", MLB, MLB) is None
        assert _classify("boston red sox", "Boston Red Sox", MLB, MLB) is None

    def test_norm_strips_to_alnum(self):
        assert _norm("St. Louis Cardinals") == "stlouiscardinals"
        assert _norm(None) == ""


# ── A session double that speaks the two SQL shapes this repair uses ──


class _Result:
    def __init__(self, rows, mappings=False):
        self._rows = rows
        self._mappings = mappings

    def mappings(self):
        return _Result(self._rows, mappings=True)

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, candidates, teams_by_sport):
        self.candidates = candidates
        self.teams_by_sport = teams_by_sport
        self.updates = []
        self.commits = 0
        self._after = None
        # Params of EVERY candidate scan, kept so a test can assert the TYPES
        # this double would otherwise erase. There are two such scans and only
        # the second runs under apply=True, so recording just the first would
        # have left the after-census unguarded. See TestSinceIsBoundAsADate.
        self.candidate_scans = []

    def set_after(self, rows):
        """Rows the SECOND candidate scan should return (the after-census)."""
        self._after = rows

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM events e" in sql:
            self.candidate_scans.append(dict(params or {}))
            rows = self.candidates
            if self._after is not None and self.updates:
                rows = self._after
            return _Result(rows)
        if "FROM teams" in sql:
            target = _norm(params["target"])
            return _Result([
                (tid, name)
                for tid, name, sid in self.teams_by_sport
                if sid == params["sport_id"] and _norm(name) == target
            ])
        if "UPDATE events" in sql:
            side = "home" if "home_team_id" in sql else "away"
            self.updates.append((params["eid"], side, params["tid"]))
            return _Result([])
        raise AssertionError(f"unexpected SQL: {sql}")

    async def commit(self):
        self.commits += 1


def _row(**kw):
    base = {
        "id": 1, "sport_id": MLB, "commence_time": "2026-08-16 17:35:00+00",
        "status": "scheduled",
        "home_team_name": "Pittsburgh Pirates", "home_team_id": 10736,
        "home_bound_name": "Pittsburgh Pirates", "home_bound_sport": MLB,
        "away_team_name": "Boston Red Sox", "away_team_id": 10709,
        "away_bound_name": "Boston Red Sox", "away_bound_sport": MLB,
    }
    base.update(kw)
    return base


TEAMS = [
    (10709, "Boston Red Sox", MLB),
    (855, "Minnesota Twins", PRESEASON),
    (10739, "Minnesota Twins", MLB),
    (10736, "Pittsburgh Pirates", MLB),
    (870, "Pittsburgh Pirates", PRESEASON),
    (10707, "Los Angeles Dodgers", MLB),
    (10710, "Arizona Diamondbacks", MLB),
]


class TestRepairPlansAndApplies:

    @pytest.mark.asyncio
    async def test_the_real_aug16_row_is_detected_and_planned(self):
        """Event 15191702 as measured in production 2026-08-12.

        'Boston Red Sox @ Pittsburgh Pirates' — both NAMES correct, away id
        pointing at the preseason Minnesota Twins and home id at the preseason
        Pirates twin. Two defects on one row, of two different classes.
        """
        row = _row(
            id=15191702,
            away_team_id=855, away_bound_name="Minnesota Twins", away_bound_sport=PRESEASON,
            home_team_id=870, home_bound_name="Pittsburgh Pirates", home_bound_sport=PRESEASON,
        )
        session = _FakeSession([row], TEAMS)

        result = await repair(session, apply=False)

        assert result["census"]["cross_club"] == 1
        assert result["census"]["wrong_sport"] == 1
        assert result["census"]["planned"] == 2
        assert result["census"]["applied"] == 0
        assert session.updates == [], "dry-run must not write"

        by_side = {e["side"]: e for e in result["ledger"]}
        assert by_side["away"]["before"]["name"] == "Minnesota Twins"
        assert by_side["away"]["after"] == {
            "id": 10709, "name": "Boston Red Sox", "sport_id": MLB,
        }
        assert by_side["home"]["after"]["id"] == 10736

    @pytest.mark.asyncio
    async def test_the_dry_run_emits_a_plan_whose_rows_are_the_ledger(self):
        """The apply half of this rail lives in the plan-bound suite (queue 362).

        What belongs HERE is the contract between the scan and the artifact: every
        planned side, and nothing else, becomes a plan row carrying the before-id
        the compare-and-set will assert.
        """
        row = _row(
            id=15194469, home_team_name="Boston Red Sox", away_team_name="Arizona Diamondbacks",
            home_team_id=855, home_bound_name="Minnesota Twins", home_bound_sport=PRESEASON,
            away_team_id=10707, away_bound_name="Los Angeles Dodgers", away_bound_sport=MLB,
        )
        session = _FakeSession([row], TEAMS)

        result = await repair(session, apply=False)

        assert result["census"]["planned"] == 2
        assert result["plan_rows"] == 2
        assert session.updates == [], "a dry-run writes nothing"
        assert session.commits == 0

    @pytest.mark.asyncio
    async def test_sound_rows_are_left_alone(self):
        session = _FakeSession([_row()], TEAMS)
        result = await repair(session, apply=False)
        assert result["census"]["planned"] == 0
        assert result["census"]["sound"] == 2
        assert session.updates == []
        assert session.commits == 0


class TestFailsClosed:
    """A guess here re-points a live foreign key. Ambiguity must go to review."""

    @pytest.mark.asyncio
    async def test_no_match_goes_to_review_not_a_guess(self):
        row = _row(
            away_team_name="Yokohama BayStars",
            away_team_id=855, away_bound_name="Minnesota Twins", away_bound_sport=PRESEASON,
        )
        session = _FakeSession([row], TEAMS)

        result = await repair(session, apply=False)

        assert result["census"]["review"] == 1
        assert result["census"]["planned"] == 0
        assert session.updates == []
        assert "0 exact name matches" in result["review"][0]["reason"]

    @pytest.mark.asyncio
    async def test_ambiguous_match_goes_to_review(self):
        teams = TEAMS + [(99999, "Boston Red Sox", MLB)]
        row = _row(
            away_team_id=855, away_bound_name="Minnesota Twins", away_bound_sport=PRESEASON,
        )
        session = _FakeSession([row], teams)

        result = await repair(session, apply=False)

        assert result["census"]["review"] == 1
        assert session.updates == []
        assert "2 exact name matches" in result["review"][0]["reason"]

    @pytest.mark.asyncio
    async def test_never_fuzzy_matches(self):
        """'Red Sox' must NOT resolve to 'Boston Red Sox'.

        Fuzzy resolution is the most likely producer of this defect; repairing
        with it would launder the error rather than fix it.
        """
        row = _row(
            away_team_name="Red Sox",
            away_team_id=855, away_bound_name="Minnesota Twins", away_bound_sport=PRESEASON,
        )
        session = _FakeSession([row], TEAMS)

        result = await repair(session, apply=False)

        assert result["census"]["planned"] == 0
        assert result["census"]["review"] == 1
        assert session.updates == []


class TestDryRunIsTheDefault:

    @pytest.mark.asyncio
    async def test_apply_defaults_to_false(self):
        row = _row(
            away_team_id=855, away_bound_name="Minnesota Twins", away_bound_sport=PRESEASON,
        )
        session = _FakeSession([row], TEAMS)
        result = await repair(session)
        assert result["apply"] is False
        assert session.updates == []
        assert session.commits == 0


class TestRegisteredOnTheRail:

    def test_repair_is_in_the_registry(self):
        """A repair that is not registered is an incantation, which is the thing
        the rail exists to abolish."""
        from app.routes.admin_repairs import _REPAIRS

        assert _REPAIRS["event-team-binding"] == (
            "app.tasks.repair_event_team_binding", "repair",
        )

    def test_signature_is_what_the_dispatcher_can_call(self):
        import inspect

        params = inspect.signature(repair).parameters
        assert list(params)[:2] == ["session", "apply"]
        # The dispatcher only forwards names the signature declares.
        assert "limit" in params and "sport" in params
        # Queue 362: without this the dispatcher silently drops ?plan_hash= and
        # every apply refuses with PLAN_HASH_MISMATCH for a reason that is true
        # but deeply misleading — the operator DID pass one.
        assert "plan_hash" in params


class TestSinceIsBoundAsADate:
    """Regression guard for the defect this rail shipped with (#1798 follow-up).

    The rail passed 19/19 and then returned HTTP 500 on its first production
    call: ``invalid input for query argument $2: '2026-03-01' (expected a
    datetime.date or datetime.datetime instance, got 'str')``.

    Why the whole existing suite was blind to it: every test here drives
    ``_FakeSession``, which accepts a params dict and never binds it to a
    driver. asyncpg binds by TYPE rather than rendering values into SQL text,
    and psycopg2 would have adapted the string silently -- so the bug lives
    exclusively in the gap between the double and the real driver. A test
    double cannot check a driver's type contract, but it CAN check the type of
    what we hand it, and that is enough to pin this class.
    """

    @pytest.mark.asyncio
    async def test_default_since_is_bound_as_a_date_not_a_string(self):
        session = _FakeSession([_row()], TEAMS)
        await repair(session)
        since = session.candidate_scans[0]["since"]
        assert isinstance(since, date), (
            f"since was bound as {type(since).__name__}={since!r}; asyncpg "
            "rejects a str for a timestamp column and the rail 500s"
        )
        assert not isinstance(since, str)

    @pytest.mark.asyncio
    async def test_explicit_string_since_is_coerced(self):
        session = _FakeSession([_row()], TEAMS)
        await repair(session, since="2026-07-04")
        assert session.candidate_scans[0]["since"] == date(2026, 7, 4)

    @pytest.mark.asyncio
    async def test_a_real_date_passes_through_unharmed(self):
        session = _FakeSession([_row()], TEAMS)
        await repair(session, since=date(2026, 5, 1))
        assert session.candidate_scans[0]["since"] == date(2026, 5, 1)

    @pytest.mark.asyncio
    async def test_a_datetime_is_narrowed_to_its_date(self):
        session = _FakeSession([_row()], TEAMS)
        await repair(session, since=datetime(2026, 5, 1, 18, 30))
        assert session.candidate_scans[0]["since"] == date(2026, 5, 1)

    @pytest.mark.asyncio
    async def test_only_one_candidate_scan_ever_runs(self):
        """The 'after-census' second scan is GONE as of queue 362, and its removal
        is asserted here rather than left as an absence somebody re-adds.

        It used to run post-commit under apply=True — which made it the more
        dangerous of the two date bindings, and this class was written for it. But
        C-APPLY-PRE showed the scan was worse than fragile: re-measuring the whole
        population after writing to it produced ``miswired_after=0``, a true number
        that says nothing about whether the writes were the APPROVED ones. The apply
        path now iterates the reviewed plan and verifies the plan's own events, so
        there is exactly one candidate scan in this rail and it is the dry-run's.
        """
        session = _FakeSession([_row()], TEAMS)

        await repair(session, apply=False)

        assert len(session.candidate_scans) == 1
        assert isinstance(session.candidate_scans[0]["since"], date)

    def test_the_helper_rejects_an_unparseable_string(self):
        with pytest.raises(ValueError):
            _as_date("not-a-date")

    @pytest.mark.asyncio
    async def test_scope_echoes_the_coerced_value(self):
        session = _FakeSession([_row()], TEAMS)
        result = await repair(session, since="2026-07-04")
        assert result["scope"]["since"] == "2026-07-04"

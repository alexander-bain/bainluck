"""#1798 — the team-binding repair must see what name checks cannot, and guess nothing.

The whole point of this repair is that it dereferences the foreign key. So the
central test is the one where **every name on the row is correct** and only the id
is wrong — the exact shape that made 153 miswired sides invisible to a codebase
full of name comparisons.
"""

import pytest

from app.tasks.repair_event_team_binding import _classify, _norm, repair

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

    def set_after(self, rows):
        """Rows the SECOND candidate scan should return (the after-census)."""
        self._after = rows

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM events e" in sql:
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
    async def test_apply_writes_both_sides_and_commits(self):
        row = _row(
            id=15194469, home_team_name="Boston Red Sox", away_team_name="Arizona Diamondbacks",
            home_team_id=855, home_bound_name="Minnesota Twins", home_bound_sport=PRESEASON,
            away_team_id=10707, away_bound_name="Los Angeles Dodgers", away_bound_sport=MLB,
        )
        session = _FakeSession([row], TEAMS)
        session.set_after([_row(
            id=15194469, home_team_name="Boston Red Sox",
            away_team_name="Arizona Diamondbacks",
            home_team_id=10709, home_bound_name="Boston Red Sox", home_bound_sport=MLB,
            away_team_id=10710, away_bound_name="Arizona Diamondbacks", away_bound_sport=MLB,
        )])

        result = await repair(session, apply=True)

        assert result["census"]["applied"] == 2
        assert session.commits == 1
        assert sorted(session.updates) == sorted([
            (15194469, "home", 10709), (15194469, "away", 10710),
        ])
        assert result["miswired_after"] == 0, "the after-census must prove the write landed"

    @pytest.mark.asyncio
    async def test_sound_rows_are_left_alone(self):
        session = _FakeSession([_row()], TEAMS)
        result = await repair(session, apply=True)
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

        result = await repair(session, apply=True)

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

        result = await repair(session, apply=True)

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

        result = await repair(session, apply=True)

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
        # The dispatcher only forwards these four names.
        assert "limit" in params and "sport" in params

"""#1204 / Queue #247 Item 1 — team-identity merge safety-gate guard tests.

The catastrophic failure mode this gate prevents: espn_id is NOT unique across
distinct NCAA schools, so a blind (sport_id, espn_id) merge would fuse Kent State
into Ohio State. Every test below asserts BOTH directions — the real bare-location
stub folds, AND the name-incompatible / real-team cases are refused.
"""
import pathlib
import re
from types import SimpleNamespace

from app.utils import team_merge as tm


def test_repair_scripts_never_set_events_updated_at():
    """The `events` table has NO `updated_at` column — an `UPDATE events SET ...
    updated_at` raises UndefinedColumnError and fails the whole repair (caught live
    on the inverted-events apply). Guard every repair that touches events."""
    root = pathlib.Path(tm.__file__).parent.parent.parent
    offenders = []
    for name in ("repair_inverted_completed_at.py", "repair_season_series_mislinks.py"):
        src = (root / "scripts" / name).read_text()
        # Any UPDATE ... events ... updated_at within a statement is the bug.
        for m in re.finditer(r"UPDATE\s+events\b[\s\S]{0,200}?updated_at", src, re.I):
            offenders.append(f"{name}: {m.group(0)[:60]!r}")
    # team_merge's FK re-points also target events.
    tm_src = pathlib.Path(tm.__file__).read_text()
    for m in re.finditer(r"UPDATE\s+events\b[\s\S]{0,200}?updated_at", tm_src, re.I):
        offenders.append(f"team_merge.py: {m.group(0)[:60]!r}")
    assert not offenders, f"events has no updated_at column: {offenders}"


def _member(id, name, slug="s", recent=0, total=0, mappings=0, espn="1", sport="x"):
    return SimpleNamespace(
        id=id, name=name, slug=slug, recent_events=recent, total_events=total,
        mapping_count=mappings, espn_id=espn, sport_id=1, sport_key=sport,
        alternate_names=[],
    )


class TestTokenPrefix:
    def test_bare_location_is_prefix(self):
        assert tm._is_token_prefix("Boston", "Boston Bruins")
        assert tm._is_token_prefix("Philadelphia", "Philadelphia Union")

    def test_different_school_is_not_prefix(self):
        # THE safety case: Kent State must NOT be a prefix of Ohio State Buckeyes.
        assert not tm._is_token_prefix("Kent State", "Ohio State Buckeyes")
        assert not tm._is_token_prefix("Fresno State", "Oklahoma State Cowboys")

    def test_partial_token_is_not_a_token_prefix(self):
        # "Bost" is not a whole-token prefix of "Boston Bruins".
        assert not tm._is_token_prefix("Bost", "Boston Bruins")

    def test_accent_folding(self):
        assert tm._normalize("Montréal Canadiens") == "montreal canadiens"
        assert tm._is_token_prefix("Montreal", "Montréal Canadiens")


class TestPlanCluster:
    def test_bare_location_stub_folds(self):
        # Boston (stub: 0 mappings, 0 recent, 1 event) → Boston Bruins (live).
        stub = _member(12682, "Boston", recent=0, total=1, mappings=0)
        canon = _member(574, "Boston Bruins", recent=3, total=37, mappings=6)
        plan = tm._plan_cluster([stub, canon])
        assert plan["status"] == "planned"
        assert plan["canonical"].id == 574
        assert [m.id for m in plan["folds"]] == [12682]

    def test_incoherent_cluster_is_skipped_entirely(self):
        # espn_id collision: Kent State poisons the whole Ohio-State cluster.
        ohio_state = _member(879, "Ohio State Buckeyes", recent=0, total=43, mappings=2)
        kent = _member(14650, "Kent State", recent=0, total=1, mappings=0)
        ohio = _member(14666, "Ohio", recent=0, total=1, mappings=0)
        plan = tm._plan_cluster([ohio_state, kent, ohio])
        assert plan["status"] == "skip_incoherent"
        assert plan["folds"] == []

    def test_real_team_is_not_folded(self):
        # A non-canonical member that is NOT a clean stub (has its own mappings /
        # recent events) must never be folded — it is a real team.
        canon = _member(1, "New York Yankees", recent=5, total=60, mappings=4)
        real = _member(2, "New York", recent=2, total=20, mappings=3)  # not a stub
        plan = tm._plan_cluster([canon, real])
        assert plan["status"] == "skip_no_stub"
        assert plan["folds"] == []

    def test_canonical_is_the_one_with_current_events(self):
        # r258 rule: canonical = carries the most CURRENT events, even if the other
        # twin has a longer name / more total history.
        stub = _member(10, "Fremantle", recent=0, total=5, mappings=0)
        live = _member(20, "Fremantle Dockers", recent=12, total=20, mappings=1)
        plan = tm._plan_cluster([stub, live])
        assert plan["status"] == "planned"
        assert plan["canonical"].id == 20

    def test_stub_with_too_many_events_is_not_folded(self):
        # A "prefix" member with a full schedule is a real team, not a stub.
        canon = _member(1, "Chicago Bulls", recent=4, total=40, mappings=3)
        busy = _member(2, "Chicago", recent=0, total=30, mappings=0)  # too many events
        plan = tm._plan_cluster([canon, busy])
        assert plan["status"] == "skip_no_stub"

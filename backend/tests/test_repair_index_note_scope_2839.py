"""#2839 — the plan note names a table-scoped blocker, never a slice's count.

`POST /api/admin/repairs/authority-id-collisions?apply=false` closes with one
sentence written to be acted on: whether the unique index on `events.espn_id`
can be created.  That sentence used to be built from `summary.groups_unresolved`,
which counts only the groups the call examined, so scoping to a quiet sport
printed on production, verbatim, over a payload carrying `contested_ids: 164`:

    "The unique index on events.espn_id cannot be created while 0 group(s)
     remain unresolved."

A blocker of zero — an all-clear — for a precondition that 164 groups block.

This is CERT-825's shape one file over (a bounded look reporting itself as a
whole-table verdict), which is why the guard below is structural rather than a
string compare: the word `group(s)` may be spoken ONLY of the census number, in
every arm, so a future edit cannot reintroduce the confusion under new wording.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from app.tasks import repair_authority_id_collisions as rail
from app.utils.authority_id_collisions import AuthorityRecord


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, script):
        self._script = list(script)
        self.executed = []
        self.commits = 0

    async def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        return _Result(self._script.pop(0) if self._script else [])

    async def commit(self):
        self.commits += 1


# The production census on the day #2839 was filed: 164 contested ids over 352
# rows.  The NHL slice of it was already drained, which is how the all-clear
# came to be printed.
CENSUS_CONTESTED = [(164, 352)]
CENSUS_DRAINED = [(0, 0)]

# Two baseball groups, so an `?sport=icehockey_nhl` filter selects none of them
# while the table stays contested.
OTHER_SPORT_ROWS = [
    ("401847094", 14683176, "baseball_ncaa", "Alabama Crimson Tide",
     "Ole Miss Rebels", None, "hash", "148", "92", 12),
    ("401847094", 14707075, "baseball_ncaa", "North Alabama",
     "Ole Miss", None, None, "148", "92", 0),
]

NHL_ROWS = [
    ("401688562", 15200817, "icehockey_nhl", "Boston Bruins",
     "Montreal Canadiens", None, "hash", "1", "10", 5),
    ("401688562", 15201232, "icehockey_nhl", "Boston Bruins",
     "Montreal Canadiens", None, None, "1", "10", 0),
]


def _numbers_called_groups(note: str) -> list[int]:
    """Every number the note attaches the word ``group(s)`` to."""
    return [int(n) for n in re.findall(r"(\d+)\s+group\(s\)", note)]


@pytest.fixture
def stub_rail(monkeypatch):
    """`_fetch_record` and `_save_plan` stubbed; ESPN answers for the NHL pair."""
    async def _record(service, sport_keys, authority_id):
        if authority_id != "401688562":
            return None
        return AuthorityRecord(
            authority_id=authority_id,
            home_names=frozenset({"boston bruins"}),
            away_names=frozenset({"montreal canadiens"}),
            label="Boston Bruins v Montreal Canadiens",
        )

    async def _save(payload):
        return True, "ok"

    monkeypatch.setattr(rail, "_fetch_record", _record)
    monkeypatch.setattr(rail, "_save_plan", _save)


# ---------------------------------------------------------------------------
# The arm that is RED on the parent: a bounded call over a contested table.
# ---------------------------------------------------------------------------


class TestABoundedCallNeverRendersAnIndexAllClear:
    def test_the_exact_production_shape_names_164_not_0(self, stub_rail):
        """`?sport=icehockey_nhl` with the NHL slice already drained.

        This is the verbatim payload from #2839: examined 0, unresolved 0,
        `before.contested_ids` 164.  On the parent the note said "cannot be
        created while 0 group(s) remain unresolved".
        """
        session = _FakeSession([CENSUS_CONTESTED, OTHER_SPORT_ROWS])
        out = asyncio.run(rail.repair(session, sport="icehockey_nhl"))

        assert out["before"]["contested_ids"] == 164
        assert out["groups_examined"] == 0
        assert out["summary"]["groups_unresolved"] == 0

        note = out["note"]
        assert _numbers_called_groups(note) == [164], note
        assert "cannot be created while 164 group(s)" in note
        assert "while 0 group(s)" not in note
        assert "no remaining blocker" not in note

    def test_a_slice_that_fully_resolves_still_reports_the_table(self, stub_rail):
        """Examined > 0 and every one of them resolved — still not an all-clear
        while the census is above zero."""
        session = _FakeSession([CENSUS_CONTESTED, NHL_ROWS + OTHER_SPORT_ROWS])
        out = asyncio.run(rail.repair(session, sport="icehockey_nhl"))

        assert out["groups_examined"] == 1
        assert out["summary"]["groups_unresolved"] == 0
        assert out["rows_planned"] == 1

        note = out["note"]
        assert _numbers_called_groups(note) == [164], note
        assert "cannot be created while 164 group(s)" in note
        assert "examined 1 of them" in note
        assert "0 of those unresolved" in note

    def test_a_truncated_call_says_it_was_truncated_in_the_same_sentence(
        self, stub_rail
    ):
        """`?limit=` is the other way to bound the look, and it bounded the
        counts the same way."""
        session = _FakeSession([CENSUS_CONTESTED, NHL_ROWS + OTHER_SPORT_ROWS])
        out = asyncio.run(rail.repair(session, limit=1))

        assert out["groups_truncated"] is True
        note = out["note"]
        assert _numbers_called_groups(note) == [164], note
        assert "truncated at limit" in note
        assert "do not speak for the table" in note

    def test_a_bounded_call_says_so_where_the_numbers_are(self, stub_rail):
        session = _FakeSession([CENSUS_CONTESTED, OTHER_SPORT_ROWS])
        out = asyncio.run(rail.repair(session, sport="icehockey_nhl"))
        assert "bounded (sport=icehockey_nhl)" in out["note"]


# ---------------------------------------------------------------------------
# The control: a genuinely drained table MAY read as an all-clear.
# ---------------------------------------------------------------------------


class TestTheDrainedControl:
    def test_an_unfiltered_drained_table_reports_no_blocker(self, stub_rail):
        """The guard above must not be satisfiable by never saying "clear" —
        when the census really is zero, the note says so."""
        session = _FakeSession([CENSUS_DRAINED, []])
        out = asyncio.run(rail.repair(session))

        assert out["before"]["contested_ids"] == 0
        note = out["note"]
        assert "no remaining blocker" in note
        assert "cannot be created" not in note
        assert _numbers_called_groups(note) == [0], note
        assert "do not speak for the table" not in note


# ---------------------------------------------------------------------------
# The sentence builder itself.
# ---------------------------------------------------------------------------


class TestIndexBlockerNote:
    def test_the_census_is_the_only_number_called_a_group(self):
        note = rail.index_blocker_note(
            contested_ids=164, examined=25, slice_unresolved=2,
            sport=None, truncated=False,
        )
        assert _numbers_called_groups(note) == [164], note

    def test_the_slice_count_survives_named_as_the_slices(self):
        """#2839's repair keeps the slice's number — it is useful — but stops
        it standing in for the table's."""
        note = rail.index_blocker_note(
            contested_ids=164, examined=25, slice_unresolved=2,
            sport=None, truncated=False,
        )
        assert "examined 25 of them" in note
        assert "2 of those unresolved" in note

    def test_both_bounds_at_once_are_both_named(self):
        note = rail.index_blocker_note(
            contested_ids=164, examined=1, slice_unresolved=0,
            sport="baseball_ncaa", truncated=True,
        )
        assert "sport=baseball_ncaa" in note
        assert "truncated at limit" in note

    @pytest.mark.parametrize("sport", [None, "icehockey_nhl"])
    @pytest.mark.parametrize("truncated", [False, True])
    def test_no_bounding_combination_can_zero_the_blocker(self, sport, truncated):
        """The failure was that the blocker moved with the scope. It must not,
        under any combination of the two things that narrow a call."""
        note = rail.index_blocker_note(
            contested_ids=164, examined=0, slice_unresolved=0,
            sport=sport, truncated=truncated,
        )
        assert "cannot be created while 164 group(s)" in note
        assert _numbers_called_groups(note) == [164], note

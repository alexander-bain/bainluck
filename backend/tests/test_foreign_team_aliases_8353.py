"""#8353 — a fuzzy ESPN hit never lends a team another school's names.

Production 2026-09-24: typing "wolverines" offered Akron Zips FIRST, above Michigan,
because team 3113 carried ``['Michigan Wolverines', 'Michigan', 'Wolverines',
'Eastern Michigan Eagles', 'Eagles', ...]``. ``_backfill_team_logos`` unioned the
names of whatever club a token-overlap score picked, while the ``espn_id`` write
beside it refused the same fuzzy hit. Two halves pinned here: the writer
(``espn_aliases_to_store``) and the repair of the 28 rows already borrowing.
"""

from __future__ import annotations

import ast
import inspect
import os
import sys
import textwrap
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import repair_8353_foreign_team_aliases as repair  # noqa: E402
from app.tasks import espn_sync  # noqa: E402
from app.tasks.espn_sync import espn_aliases_to_store  # noqa: E402

MICHIGAN = SimpleNamespace(
    espn_id="130",
    display_name="Michigan Wolverines",
    short_name="Michigan",
    nickname="Wolverines",
    name="Wolverines",
)
AKRON = SimpleNamespace(
    espn_id="2006",
    display_name="Akron Zips",
    short_name="Akron",
    nickname="Zips",
    name="Zips",
)


class TestAFuzzyHitLendsNoName:
    def test_the_specimen_a_fuzzy_michigan_hit_writes_nothing_onto_akron(self):
        assert (
            espn_aliases_to_store(
                "Akron Zips",
                ["Akron", "Zips"],
                MICHIGAN,
                match_was_exact=False,
                repointed_from=None,
            )
            is None
        )

    def test_an_exact_hit_still_unions_the_clubs_own_names(self):
        got = espn_aliases_to_store(
            "Akron Zips", ["Akron"], AKRON, match_was_exact=True, repointed_from=None
        )
        assert sorted(got) == ["Akron", "Zips"]

    def test_the_row_name_is_never_stored_as_its_own_alias(self):
        got = espn_aliases_to_store(
            "Akron Zips", [], AKRON, match_was_exact=True, repointed_from=None
        )
        assert "Akron Zips" not in got

    def test_a_repoint_is_an_id_match_and_still_writes(self):
        got = espn_aliases_to_store(
            "Akron Zips", None, AKRON, match_was_exact=False, repointed_from="9999"
        )
        assert sorted(got) == ["Akron", "Zips"]

    def test_no_match_writes_nothing(self):
        assert (
            espn_aliases_to_store(
                "Akron Zips", ["Akron"], None, match_was_exact=True, repointed_from=None
            )
            is None
        )


class TestTheBackfillWritesAliasesOnlyThroughTheGate:
    """A second, ungated ``team.alternate_names = ...`` in the backfill would undo
    the helper in silence — every assignment must carry the helper's result."""

    def _fn(self):
        src = textwrap.dedent(inspect.getsource(espn_sync._backfill_team_logos))
        return ast.parse(src)

    def test_every_alias_assignment_is_the_helpers_result(self):
        tree = self._fn()
        gated: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and getattr(node.value.func, "id", None) == "espn_aliases_to_store"
            ):
                gated |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        writes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Attribute) and t.attr == "alternate_names"
                for t in node.targets
            )
        ]
        assert writes, "the backfill no longer writes aliases — this guard is vacuous"
        for w in writes:
            assert isinstance(w.value, ast.Name) and w.value.id in gated, ast.unparse(w)

    def test_the_gate_is_handed_the_match_exactness(self):
        tree = self._fn()
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", None) == "espn_aliases_to_store"
        ]
        assert len(calls) == 1
        kws = {k.arg: ast.unparse(k.value) for k in calls[0].keywords}
        assert kws == {
            "match_was_exact": "match_was_exact",
            "repointed_from": "repointed_from",
        }


def _rows(state: str) -> dict:
    """Every pinned row as production held it BEFORE, or as the strip leaves it."""
    out = {}
    for team_id, (name, before, after) in repair.PINNED.items():
        names = before if state == "before" else after
        small = large = None
        if team_id in repair.LOGO_CLEAR and state == "before":
            small = large = repair.LOGO_CLEAR[team_id]
        out[team_id] = (name, list(names), small, large)
    return out


class TestTheRepairPlan:
    def test_apply_strips_every_pinned_row_and_clears_the_borrowed_crest(self):
        got = repair.plan(_rows("before"), restore=False)
        assert len(got["aliases"]) == 28
        assert dict(got["aliases"])[3113] == ["Akron", "Zips"]
        assert got["logos"] == [(724, None)]
        assert got["skip"] == []

    def test_restore_puts_back_exactly_what_was_there(self):
        got = repair.plan(_rows("after"), restore=True)
        back = dict(got["aliases"])
        assert back == {i: before for i, (_n, before, _a) in repair.PINNED.items()}
        assert got["logos"] == [(724, repair.LOGO_CLEAR[724])]

    def test_a_second_apply_writes_nothing(self):
        got = repair.plan(_rows("after"), restore=False)
        assert got["aliases"] == [] and got["logos"] == []
        assert all(reason.startswith("already") or "logo" in reason for _i, reason in got["skip"])

    def test_a_row_the_backfill_touched_since_is_skipped_not_overwritten(self):
        rows = _rows("before")
        name, names, s, lg = rows[2601]
        rows[2601] = (name, names + ["Missouri State"], s, lg)
        got = repair.plan(rows, restore=False)
        assert 2601 not in dict(got["aliases"])
        assert (2601, "aliases changed since the pin") in got["skip"]

    def test_a_refilled_crest_is_not_undone_by_restore(self):
        rows = _rows("after")
        name, names, _s, _l = rows[724]
        rows[724] = (name, names, "x/2110.png", "x/2110.png")
        got = repair.plan(rows, restore=True)
        assert got["logos"] == []
        assert (724, "logo refilled since the clear") in got["skip"]

    def test_an_id_that_no_longer_names_its_team_refuses_the_whole_run(self):
        rows = _rows("before")
        _n, names, s, lg = rows[3113]
        rows[3113] = ("Toledo Rockets", names, s, lg)
        with pytest.raises(repair.Refused):
            repair.plan(rows, restore=False)

    def test_it_refuses_off_production(self):
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck-staging"})
        repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})


class TestTheManifestIsAStripAndNothingElse:
    FOREIGN = {
        "Michigan Wolverines", "Wolverines", "Eastern Michigan Eagles", "E Michigan",
        "West Virginia Mountaineers", "Mountaineers", "West Virginia",
        "Iowa Hawkeyes", "Hawkeyes", "Iowa", "Florida Gators", "Gators",
        "Houston Cougars", "Cougars", "Texas Tech Red Raiders", "Red Raiders",
        "Arkansas Razorbacks", "Razorbacks", "Baylor Bears", "Baylor",
        "Oklahoma Sooners", "Colorado Buffaloes", "Buffaloes",
    }

    def test_after_is_a_subset_of_before_on_every_row(self):
        for team_id, (_n, before, after) in repair.PINNED.items():
            assert set(after) < set(before), team_id

    def test_no_row_keeps_a_borrowed_school(self):
        for team_id, (name, _b, after) in repair.PINNED.items():
            own = {w.lower() for w in name.split()}
            borrowed = {
                a for a in after
                if a in self.FOREIGN and not set(a.lower().split()) <= own
            }
            assert not borrowed, (team_id, name, borrowed)

    def test_every_row_keeps_at_least_one_name_of_its_own(self):
        for team_id, (name, _b, after) in repair.PINNED.items():
            assert after, (team_id, name)

    def test_the_specimen_rows_are_pinned(self):
        assert repair.PINNED[3113][2] == ["Akron", "Zips"]
        wv = [i for i, (_n, b, _a) in repair.PINNED.items() if "West Virginia Mountaineers" in b]
        assert len(wv) == 12

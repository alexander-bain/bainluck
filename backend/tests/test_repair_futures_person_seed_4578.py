"""#4578 — the purge deletes what the SHIPPED guard refuses, and nothing else.

The failure this file is written against is not "the repair deletes too much".
It is "the repair deletes a *different set* than `is_plausible_person_name`
refuses" — which looks identical in a census, passes any count-based review, and
only becomes visible when somebody tries to explain a restore.

#4578's own filing counts the cohort with a SQL proxy (digit / " beats " / " vs ")
and gets 4,913 of 7,471 — 65.8 %. Running the same rows through the shipped
predicate refuses 67.2 %. The gap is `normalize_alias` running first, the
`len < 3` floor, the closed field-word list, and the padded marker test. So the
membership rule here is the imported function, and
:class:`TestMembershipIsTheShippedRuleNotACopy` fails the build if this module
ever grows a rule of its own.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.entity_registry import is_plausible_person_name
from app.tasks import repair_futures_person_seed as rp

MODULE_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "app" / "tasks" / "repair_futures_person_seed.py"
)


def _row(entity_id: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=entity_id, canonical_name=name)


#: Quoted from #4578's measurement, not invented. Each is one of the three
#: shapes the filing names.
POLLUTION = [
    pytest.param("1+ strokes", id="margin-ladder"),
    pytest.param("R1: Justin Rose under 73.5 strokes", id="round-ladder"),
    pytest.param("Above 13500", id="threshold"),
    pytest.param("Jon Rahm beats McIlroy and Spieth", id="head-to-head"),
]

#: The control population — persons seeded from EVENTS, where a name is a real
#: competitor. The filing measures 0 refusals in a random 1,000.
REAL_PEOPLE = [
    pytest.param("Rory McIlroy", id="plain"),
    pytest.param("Jon Rahm", id="plain-2"),
    pytest.param("Ludvig Åberg", id="diacritic"),
    pytest.param("Michael Kim", id="colliding-surname-is-still-a-person"),
]


class TestMembershipIsTheShippedRuleNotACopy:
    """The one property that makes this repair safe to reverse."""

    def test_the_module_imports_the_guard(self):
        assert "from app.services.entity_registry import is_plausible_person_name" in (
            MODULE_SOURCE.read_text()
        )

    def test_it_states_no_membership_rule_of_its_own(self):
        """No digit test, no " beats ", no " vs " — in CODE.

        Prose may quote them (the docstring does, deliberately), so comments are
        stripped rather than the patterns weakened. A repair that restates the
        guard's rules is one refactor away from deleting rows the guard would
        have kept, and the receipt would faithfully record the wrong set.
        """
        code = []
        for line in MODULE_SOURCE.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            code.append(line.split("  #")[0])
        body = "\n".join(code)
        # The docstring is prose too, and it names all three shapes.
        body = re.sub(r'""".*?"""', "", body, flags=re.DOTALL)
        offenders = [
            pat
            for pat in ("isdigit", " beats ", " vs ", "MULTI_COMPETITOR")
            if pat in body
        ]
        assert offenders == [], (
            "this repair has grown its own membership rule; it must ask "
            "is_plausible_person_name() instead: " + repr(offenders)
        )

    @pytest.mark.parametrize("name", POLLUTION)
    def test_pollution_is_refused(self, name):
        assert rp.refused_rows([_row(1, name)]) != []

    @pytest.mark.parametrize("name", REAL_PEOPLE)
    def test_a_real_competitor_is_kept(self, name):
        assert rp.refused_rows([_row(1, name)]) == []

    @pytest.mark.parametrize("name", POLLUTION + REAL_PEOPLE)
    def test_it_agrees_with_the_guard_row_for_row(self, name):
        """Both directions (gotcha #43), and stated as agreement, not as a list.

        A refusal list can be right about every case someone thought to write
        down and still disagree with the guard on the population. This asserts
        the relationship instead.
        """
        refused = rp.refused_rows([_row(1, name)]) != []
        assert refused is not is_plausible_person_name(name)

    def test_a_null_name_is_refused_not_crashed(self):
        assert rp.refused_rows([_row(1, None)]) != []


class TestThePlanBindsTheApply:
    def test_the_hash_is_over_membership_only(self):
        """Same ids in any order is the same plan."""
        assert rp.plan_hash_for([3, 1, 2]) == rp.plan_hash_for([1, 2, 3])

    def test_a_different_set_is_a_different_plan(self):
        assert rp.plan_hash_for([1, 2]) != rp.plan_hash_for([1, 2, 3])

    def test_the_empty_plan_is_stable(self):
        assert rp.plan_hash_for([]) == rp.plan_hash_for([])


class TestTheRestoreCommandIsRunnable:
    """D51: a repair may be applied unattended because it is REVERSIBLE.

    The restore line is the whole permission, so it is asserted rather than
    trusted — a command that names the wrong repair or drops the identity is a
    backup nobody can use.
    """

    def test_it_names_this_repair_and_carries_the_identity(self):
        cmd = rp.restore_command("repair:futures_person_seed:undo:X:Y:Z")
        assert "futures-person-seed-purge" in cmd
        assert "undo_identity=repair:futures_person_seed:undo:X:Y:Z" in cmd
        assert "apply=true" in cmd

    def test_the_identity_is_unique_per_invocation(self):
        """Two applies deriving the same plan in the same second must not
        collide — the store refuses to replace an occupied identity, so a
        colliding salt makes the SECOND apply unrestorable (CERT-856)."""
        from datetime import datetime, timezone

        at = datetime(2026, 9, 9, 20, 0, 0, tzinfo=timezone.utc)
        a = rp.undo_identity_for("deadbeef", at=at, invocation=rp.new_invocation())
        b = rp.undo_identity_for("deadbeef", at=at, invocation=rp.new_invocation())
        assert a != b


class TestTheReceiptCarriesEveryColumnItMustPutBack:
    """A backup of `entities` alone is not a restore, it is half of one.

    `entity_aliases.entity_id` is `ON DELETE CASCADE`, so after the delete there
    is nothing left to reconstruct the aliases from. And both tables have NOT
    NULL columns (`entities.kind`, `entity_aliases.alias_type`) that an INSERT
    omitting them would fail on — on the one code path nobody exercises until
    they need it.
    """

    def test_the_entity_insert_names_every_selected_column(self):
        body = MODULE_SOURCE.read_text()
        insert = body.split("INSERT INTO entities")[1].split("ON CONFLICT")[0]
        for column in (
            "kind", "canonical_name", "slug", "sport_id", "sport_key",
            "external_ref", "entity_metadata", "created_at", "source_team_id",
            "date_window_start", "date_window_end", "confidence",
        ):
            assert column in insert, column

    def test_the_alias_insert_carries_the_not_null_columns(self):
        body = MODULE_SOURCE.read_text()
        insert = body.split("INSERT INTO entity_aliases")[1].split("ON CONFLICT")[0]
        for column in ("entity_id", "alias", "alias_norm", "alias_type"):
            assert column in insert, column

    def test_aliases_are_read_before_the_delete_not_after(self):
        """CASCADE means "after" reads nothing, and reads it silently."""
        body = MODULE_SOURCE.read_text()
        assert body.index("_aliases_for(db, ids)") < body.index(
            "DELETE FROM entities"
        )

    def test_the_receipt_is_staged_before_the_delete(self):
        body = MODULE_SOURCE.read_text()
        assert body.index("_save_undo_co_commit(db, identity, payload)") < body.index(
            "DELETE FROM entities"
        )


class TestTheSeedMarkerIsMatchedExactly:
    def test_it_is_equality_and_never_a_prefix(self):
        """`seed_persons_events` is the CONTROL population — 7,209 real
        competitors the guard refuses 0 of. A LIKE 'seed_persons%' would take
        it, and no alias count would reveal that it had."""
        assert rp.SEED_SOURCE == "seed_persons_futures"
        # The SQL itself, not the file text. The first version of this test
        # scanned the whole module for "LIKE" and failed on the docstring's own
        # phrase "SQL that looks LIKE it" — a substring read as a sentence,
        # which is the same mistake in miniature that the assertion is about.
        sql = str(rp._COHORT_SQL).upper()
        assert "ENTITY_METADATA->>'SEED_SOURCE' = :SEED_SOURCE" in sql
        assert "LIKE" not in sql


class TestItIsAttendedAndCapped:
    def test_it_is_not_wired_to_a_beat(self):
        from app.tasks import celery_app

        schedule = getattr(celery_app.conf, "beat_schedule", {}) or {}
        assert not any(
            "repair_futures_person_seed" in str(v) for v in schedule.values()
        )

    def test_a_caller_cannot_raise_the_cap(self):
        """`limit` bounds the page DOWN, never up — an unbounded call would
        build a receipt too large to publish and time the transaction out."""
        assert rp.APPLY_CAP == 1500
        body = MODULE_SOURCE.read_text()
        assert "min(int(limit or APPLY_CAP), APPLY_CAP)" in body

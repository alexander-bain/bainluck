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


# ── the paths that are only ever run once, by someone who needs them ──────────
#
# Everything above this line reads the module: its source text, its constants,
# its pure functions. None of it EXECUTES `repair()` or `_undo()`, and the module
# docstring's own boast is that the restore is "the one path nobody exercises
# until they need it". A source-scan cannot tell a staged receipt from a staged
# receipt that is never written, and an ordering assertion over file offsets
# holds just as well if the delete is unreachable. So the doubles below run both
# halves and read what came out of them.


class _Result:
    """What `AsyncSession.execute` hands back, as much of it as this uses."""

    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows


def _entity(entity_id: int, name: str, **over):
    base = dict(
        id=entity_id,
        canonical_name=name,
        slug=name.lower().replace(" ", "-"),
        kind="person",
        sport_id=7,
        sport_key="golf_pga",
        external_ref=None,
        entity_metadata={"seed_source": rp.SEED_SOURCE},
        created_at=None,
        source_team_id=None,
        date_window_start=None,
        date_window_end=None,
        confidence=0.5,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _alias(alias_id: int, entity_id: int, alias: str):
    return SimpleNamespace(
        id=alias_id,
        entity_id=entity_id,
        alias=alias,
        alias_norm=alias.lower(),
        alias_type="derived",
        source="seed",
        confidence=0.5,
        created_at=None,
    )


def _participant(row_id: int, entity_id: int):
    return SimpleNamespace(
        id=row_id, entity_id=entity_id, entity_type="person", entity_name="x"
    )


class _ApplySession:
    """Answers the four SQL shapes the apply issues, and records the order.

    The order is the point: a receipt staged after the delete, or a delete that
    runs when the receipt did not persist, are both invisible to a census and
    both cost the reversal. `calls` is the transcript the assertions read.
    """

    def __init__(self, cohort, aliases=(), participants=(), delete_rowcount=None):
        self.cohort = list(cohort)
        self.aliases = list(aliases)
        self.participants = list(participants)
        self.delete_rowcount = delete_rowcount
        self.calls: list[str] = []
        self.params: dict[str, dict] = {}
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        if "FROM entities e" in sql:
            self.calls.append("cohort")
            after = int(params.get("after_id") or 0)
            rows = [r for r in self.cohort if r.id > after][
                : int(params["scan_limit"])
            ]
            return _Result(rows)
        if "FROM entity_aliases" in sql:
            self.calls.append("read-aliases")
            ids = set(params["ids"])
            return _Result([a for a in self.aliases if a.entity_id in ids])
        if "FROM event_participants" in sql:
            self.calls.append("read-participants")
            ids = set(params["ids"])
            return _Result([p for p in self.participants if p.entity_id in ids])
        if sql.startswith("UPDATE event_participants"):
            self.calls.append("clear-participants")
            self.params["clear"] = params
            return _Result(rowcount=len(params.get("ids", [])))
        if sql.startswith("DELETE FROM entities"):
            self.calls.append("delete")
            self.params["delete"] = params
            n = params["ids"]
            return _Result(
                rowcount=(
                    len(n) if self.delete_rowcount is None else self.delete_rowcount
                )
            )
        raise AssertionError("unexpected statement: " + sql[:120])

    async def commit(self):
        self.calls.append("commit")
        self.commits += 1

    async def rollback(self):
        self.calls.append("rollback")
        self.rollbacks += 1


@pytest.fixture
def staged(monkeypatch):
    """Capture the receipt instead of writing it, and report `ok` by default."""
    seen: dict = {"status": "ok", "payloads": [], "sessions": []}

    async def _publish(session, envelope, *, owner_key, owner):
        seen["payloads"].append(envelope.payload)
        seen["sessions"].append(session)
        seen["owner_key"] = owner_key
        seen["owner"] = owner
        # Recorded on the transcript so ordering is asserted against the same
        # timeline as the SQL, not inferred from two separate lists.
        session.calls.append("stage-receipt")
        return {"status": seen["status"]}

    monkeypatch.setattr(
        "app.services.durable_snapshots.publish_owned_snapshot_in_txn", _publish
    )
    return seen


COHORT = [
    _entity(11, "Rory McIlroy"),
    _entity(12, "1+ strokes"),
    _entity(13, "Jon Rahm beats McIlroy and Spieth"),
    _entity(14, "Ludvig Åberg"),
]
REFUSED_IDS = [12, 13]


async def _plan(session):
    census = await rp.repair(session)
    return census["plan_hash"]


@pytest.mark.asyncio
class TestTheApplyActuallyRuns:
    async def test_the_dry_run_writes_nothing_and_names_both_sides(self, staged):
        session = _ApplySession(COHORT)
        census = await rp.repair(session)

        assert census["would_delete"] == 2
        assert census["kept_as_people"] == 2
        assert census["scan_exhausted"] is True
        assert session.calls == ["cohort"]
        assert session.commits == 0
        assert staged["payloads"] == []

    async def test_it_deletes_the_refused_ids_and_only_those(self, staged):
        session = _ApplySession(COHORT)
        plan = await _plan(session)
        out = await rp.repair(session, apply=True, plan_hash=plan)

        assert sorted(session.params["delete"]["ids"]) == REFUSED_IDS
        assert out["applied"] == 2
        assert session.commits == 1

    async def test_the_receipt_is_staged_before_the_delete_and_commits_once(
        self, staged
    ):
        session = _ApplySession(
            COHORT, aliases=[_alias(1, 12, "strokes")], participants=[]
        )
        plan = await _plan(session)
        await rp.repair(session, apply=True, plan_hash=plan)

        transcript = session.calls
        assert transcript.index("stage-receipt") < transcript.index("delete")
        # One transaction: no commit separates the receipt from the delete.
        assert transcript[transcript.index("stage-receipt"):] == [
            "stage-receipt",
            "delete",
            "commit",
        ]
        # And it was staged on the SAME session that runs the delete — a receipt
        # published on its own connection is the failure this shape exists to
        # prevent, and it looks identical from the outside.
        assert staged["sessions"] == [session]

    async def test_an_unpersisted_receipt_rolls_back_and_deletes_nothing(
        self, staged
    ):
        staged["status"] = "occupied"
        session = _ApplySession(COHORT)
        plan = await _plan(session)
        out = await rp.repair(session, apply=True, plan_hash=plan)

        assert out["refused"] == "UNDO_NOT_PERSISTED"
        assert out["undo_status"] == "occupied"
        assert "delete" not in session.calls
        assert session.rollbacks == 1
        assert session.commits == 0

    async def test_a_stale_plan_deletes_nothing(self, staged):
        session = _ApplySession(COHORT)
        out = await rp.repair(session, apply=True, plan_hash="0" * 16)

        assert out["refused"] == "PLAN_STALE"
        assert "delete" not in session.calls
        assert session.commits == 0

    async def test_no_plan_at_all_deletes_nothing(self, staged):
        session = _ApplySession(COHORT)
        out = await rp.repair(session, apply=True)

        assert out["refused"] == "PLAN_HASH_REQUIRED"
        assert "delete" not in session.calls

    async def test_a_page_of_only_real_people_is_a_no_op_not_an_empty_delete(
        self, staged
    ):
        session = _ApplySession([_entity(11, "Rory McIlroy")])
        plan = await _plan(session)
        out = await rp.repair(session, apply=True, plan_hash=plan)

        assert out["applied"] == 0
        assert "delete" not in session.calls
        assert staged["payloads"] == []

    async def test_applied_is_what_postgres_deleted_not_what_was_planned(
        self, staged
    ):
        """Same rule as the restore's counts, on the forward half.

        A concurrent delete between the plan and the DELETE takes rows out from
        under it. `applied` must be the rowcount, because it is the number that
        gets compared against the receipt when somebody reconciles a purge.
        """
        session = _ApplySession(COHORT, delete_rowcount=1)
        plan = await _plan(session)
        out = await rp.repair(session, apply=True, plan_hash=plan)

        assert sorted(session.params["delete"]["ids"]) == REFUSED_IDS
        assert out["applied"] == 1

    async def test_the_receipt_carries_the_cascade_and_the_dangling_pointers(
        self, staged
    ):
        session = _ApplySession(
            COHORT,
            aliases=[_alias(1, 12, "strokes"), _alias(2, 13, "spieth")],
            participants=[_participant(90, 13)],
        )
        plan = await _plan(session)
        out = await rp.repair(session, apply=True, plan_hash=plan)

        payload = staged["payloads"][0]
        assert [e["id"] for e in payload["entities"]] == REFUSED_IDS
        assert [a["id"] for a in payload["aliases"]] == [1, 2]
        assert payload["participants"] == [{"id": 90, "entity_id": 13}]
        # Every column of the row, not just the ones the delete reads.
        assert set(payload["entities"][0]) >= {
            "kind", "canonical_name", "slug", "sport_id", "sport_key",
            "external_ref", "entity_metadata", "created_at", "source_team_id",
            "date_window_start", "date_window_end", "confidence",
        }
        assert session.params["clear"]["ids"] == [90]
        assert out["participants_cleared"] == 1
        assert out["aliases_cascaded"] == 2
        assert out["restore_command"].endswith(out["undo_identity"] + '"')


class _UndoSession:
    """Postgres for the restore: `ON CONFLICT (id) DO NOTHING` is modelled.

    `occupied` is the set of ids already present, and an INSERT naming one of
    them reports rowcount 0 — exactly as Postgres would. Modelling that is the
    whole value of the double: a double that always says 1 makes the difference
    between "restored" and "reported restored" untestable.
    """

    def __init__(self, occupied_entities=(), occupied_aliases=(), repointed=()):
        self.occupied_entities = set(occupied_entities)
        self.occupied_aliases = set(occupied_aliases)
        self.repointed = set(repointed)
        self.inserted_entities: list[dict] = []
        self.inserted_aliases: list[dict] = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}
        if sql.startswith("INSERT INTO entities"):
            self.inserted_entities.append(params)
            return _Result(rowcount=0 if params["id"] in self.occupied_entities else 1)
        if sql.startswith("INSERT INTO entity_aliases"):
            self.inserted_aliases.append(params)
            return _Result(rowcount=0 if params["id"] in self.occupied_aliases else 1)
        if sql.startswith("UPDATE event_participants"):
            return _Result(rowcount=0 if params["id"] in self.repointed else 1)
        raise AssertionError("unexpected statement: " + sql[:120])

    async def commit(self):
        self.commits += 1


RECEIPT = {
    "invocation": "abcd",
    "issue": rp.ISSUE,
    "taken_at": "2026-09-10T04:00:00+00:00",
    "plan_hash": "deadbeefdeadbeef",
    "entities": [
        {
            "id": 12, "kind": "person", "canonical_name": "1+ strokes",
            "slug": "1-strokes", "sport_id": 7, "sport_key": "golf_pga",
            "external_ref": None, "entity_metadata": {"seed_source": "x"},
            "created_at": None, "source_team_id": None,
            "date_window_start": None, "date_window_end": None, "confidence": 0.5,
        },
        {
            "id": 13, "kind": "person", "canonical_name": "A beats B",
            "slug": "a-beats-b", "sport_id": 7, "sport_key": "golf_pga",
            "external_ref": None, "entity_metadata": None,
            "created_at": None, "source_team_id": None,
            "date_window_start": None, "date_window_end": None, "confidence": 0.5,
        },
    ],
    "aliases": [
        {
            "id": 1, "entity_id": 12, "alias": "strokes", "alias_norm": "strokes",
            "alias_type": "derived", "source": "seed", "confidence": 0.5,
            "created_at": None,
        }
    ],
    "participants": [{"id": 90, "entity_id": 13}],
}


@pytest.fixture
def receipt(monkeypatch):
    """Serve one stored receipt, with a settable read classification."""
    state = {"payload": RECEIPT, "status": "ok"}

    async def _read(identity, *, expected_version=None, max_age_s=None):
        from app.utils.durable_state import DurableEnvelope, EnvelopeRead

        if state["status"] != "ok":
            return EnvelopeRead(status=state["status"], tier="durable")
        envelope = DurableEnvelope.build(
            identity=identity,
            schema_version=rp.UNDO_SCHEMA,
            payload=state["payload"],
            complete=True,
            source="test",
        )
        return EnvelopeRead(status="ok", tier="durable", envelope=envelope)

    monkeypatch.setattr(
        "app.services.durable_snapshots.read_snapshot_standalone", _read
    )
    return state


@pytest.mark.asyncio
class TestTheRestoreActuallyRuns:
    async def test_the_dry_run_reports_the_receipt_and_writes_nothing(self, receipt):
        session = _UndoSession()
        out = await rp.repair(session, apply=False, undo_identity="id-1")

        assert out["would_restore_entities"] == 2
        assert out["would_restore_aliases"] == 1
        assert out["would_restore_participants"] == 1
        assert session.inserted_entities == []
        assert session.commits == 0

    async def test_it_puts_the_rows_back_under_their_original_ids(self, receipt):
        session = _UndoSession()
        out = await rp.repair(session, apply=True, undo_identity="id-1")

        assert [e["id"] for e in session.inserted_entities] == [12, 13]
        assert session.inserted_entities[0]["canonical_name"] == "1+ strokes"
        assert [a["id"] for a in session.inserted_aliases] == [1]
        assert out["restored_entities"] == 2
        assert out["restored_aliases"] == 1
        assert out["restored_participants"] == 1
        assert session.commits == 1

    async def test_the_metadata_is_handed_over_as_json_not_a_dict(self, receipt):
        """`CAST(:entity_metadata AS JSONB)` needs text; a dict binds as a
        parameter Postgres cannot cast, and it fails on the restore path only."""
        session = _UndoSession()
        await rp.repair(session, apply=True, undo_identity="id-1")

        assert session.inserted_entities[0]["entity_metadata"] == (
            '{"seed_source": "x"}'
        )

    async def test_it_reports_what_postgres_wrote_not_what_the_receipt_held(
        self, receipt
    ):
        """The number an operator reads after a reversal.

        `ON CONFLICT DO NOTHING` skips an occupied id, and the participant UPDATE
        skips a row something has re-pointed since. Reporting the receipt's
        length would print a full restore over a run that wrote one row.
        """
        session = _UndoSession(
            occupied_entities=[12], occupied_aliases=[1], repointed=[90]
        )
        out = await rp.repair(session, apply=True, undo_identity="id-1")

        assert out["restored_entities"] == 1
        assert out["restored_aliases"] == 0
        assert out["restored_participants"] == 0
        assert out["skipped_already_present"] == {
            "entities": 1, "aliases": 1, "participants": 1,
        }

    async def test_a_store_outage_is_not_reported_as_a_missing_receipt(
        self, receipt
    ):
        """`read_snapshot_standalone` NEVER RAISES — it returns `unavailable`.

        So the `not ok` branch is the one that fires when the database is down,
        and telling an operator mid-reversal that their receipt does not exist
        is how a recoverable purge becomes an unrecovered one.
        """
        receipt["status"] = "unavailable"
        session = _UndoSession()
        out = await rp.repair(session, apply=True, undo_identity="id-1")

        assert out["refused"] == rp.REASON_UNDO_UNREADABLE
        assert session.inserted_entities == []
        assert session.commits == 0

    async def test_a_genuinely_absent_receipt_still_says_missing(self, receipt):
        receipt["status"] = "missing"
        session = _UndoSession()
        out = await rp.repair(session, apply=True, undo_identity="id-1")

        assert out["refused"] == rp.REASON_UNDO_MISSING

    async def test_a_malformed_envelope_is_unreadable_not_missing(self, receipt):
        receipt["status"] = "malformed"
        session = _UndoSession()
        out = await rp.repair(session, apply=True, undo_identity="id-1")

        assert out["refused"] == rp.REASON_UNDO_UNREADABLE

    async def test_a_receipt_without_an_entities_list_is_corrupt(self, receipt):
        receipt["payload"] = {"invocation": "x", "aliases": []}
        session = _UndoSession()
        out = await rp.repair(session, apply=True, undo_identity="id-1")

        assert out["refused"] == rp.REASON_UNDO_CORRUPT
        assert session.commits == 0

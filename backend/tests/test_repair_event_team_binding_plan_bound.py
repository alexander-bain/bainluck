"""#1798 queue 362 — the apply must write the plan Alex read, and nothing else.

WHY THIS FILE EXISTS

Codex's C-APPLY-PRE certification BLOCKed the approved 180-side re-bind. Not on the
census, which was correct in every dimension it checked (arithmetic, plan/review
disjointness, before-and-after clubs, the ambiguity rail). Not on the approval, which
Alex had given. On this:

    ``repair()`` has no ``plan_hash`` parameter, so ``apply=true`` re-derives a fresh
    census and is NOT bound to the artifact Alex reviewed.

and it proved it with an executable specimen — reviewed set ``[(1001, away)]``, a
candidate ``2002:away`` that appeared after review, and the deployed function wrote
**both**, committed, and reported ``miswired_after=0``.

That last number is the part worth staring at. It was TRUE. The population really did
contain zero miswired sides afterwards. It simply is not an answer to the question
anybody was asking, which is *were these the writes that were approved* — and an
after-census structurally cannot answer that, because it measures the world the write
already changed.

So the central test here is ``test_a_candidate_that_appeared_after_review_is_never_written``:
same shape as the certification's specimen, run against the shipping function.

THE FOUR REFUSALS, EACH BY NAME

    no plan artifact          -> PLAN_ARTIFACT_MISSING
    an edited/truncated one   -> PLAN_ARTIFACT_CORRUPT
    no hash, or a stale hash  -> PLAN_HASH_MISMATCH
    a side that moved since   -> CONCURRENT_ROW_DRIFT   (per-row, not per-run)

The last is the compare-and-set, and it is per-row on purpose: one side drifting must
not cancel the other 179 approved writes, and it must not be silently written either.
"""

from types import SimpleNamespace

import pytest

from app.tasks import repair_event_team_binding as rail
from app.tasks.repair_event_team_binding import repair
from app.utils.repair_apply_plan import (
    BINDING_APPLY_PLAN_SCHEMA,
    REASON_CONCURRENT_DRIFT,
    REASON_PLAN_CORRUPT,
    REASON_PLAN_EMPTY,
    REASON_PLAN_HASH_MISMATCH,
    REASON_PLAN_MISSING,
    PlannedBinding,
    build_binding_plan,
    decode_binding_plan,
    mutations_outside_approved_keys,
)

MLB = 53232
PRESEASON = 33178


# ── doubles ────────────────────────────────────────────────────────────────


class _Result:
    def __init__(self, rows, rowcount=0, mappings=False):
        self._rows = rows
        self.rowcount = rowcount
        self._mappings = mappings

    def mappings(self):
        return _Result(self._rows, self.rowcount, mappings=True)

    def all(self):
        return self._rows


class _ApplySession:
    """A session that answers the apply path's two SQL shapes.

    ``events`` is the live table, keyed by id. The compare-and-set is modelled
    honestly: an UPDATE whose ``expected`` does not match the live value affects
    ZERO rows, exactly as Postgres would. Modelling that faithfully is the whole
    value of this double — a double that always reports rowcount 1 would make the
    drift refusal untestable and it would ship dead.
    """

    def __init__(self, events, teams):
        self.events = {e["id"]: dict(e) for e in events}
        self.teams = {t[0]: (t[1], t[2]) for t in teams}
        self.updates = []
        self.commits = 0
        self.rollbacks = 0
        self.scans = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}

        if "UPDATE events" in sql:
            side = "home" if "home_team_id" in sql else "away"
            row = self.events.get(params["eid"])
            assert "AND %s_team_id = :expected" % side in sql, (
                "the write must be a compare-and-set on the plan's before-id"
            )
            if row is None or row[f"{side}_team_id"] != params["expected"]:
                return _Result([], rowcount=0)
            row[f"{side}_team_id"] = params["tid"]
            self.updates.append((params["eid"], side, params["tid"]))
            return _Result([], rowcount=1)

        if "WHERE e.id = ANY(:ids)" in sql:
            out = []
            for eid in params["ids"]:
                row = self.events.get(eid)
                if row is None:
                    continue
                rec = {"id": row["id"], "sport_id": row["sport_id"]}
                for side in ("home", "away"):
                    tid = row[f"{side}_team_id"]
                    name, sport = self.teams.get(tid, (None, None))
                    rec[f"{side}_team_name"] = row[f"{side}_team_name"]
                    rec[f"{side}_team_id"] = tid
                    rec[f"{side}_bound_name"] = name
                    rec[f"{side}_bound_sport"] = sport
                out.append(rec)
            return _Result(out)

        if "FROM events e" in sql:
            self.scans += 1
            raise AssertionError(
                "the apply path ran the CANDIDATE SCAN. That is the defect: a work "
                "list recomputed at apply time is not the work list that was reviewed."
            )

        raise AssertionError(f"unexpected SQL: {sql}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


TEAMS = [
    (10709, "Boston Red Sox", MLB),
    (855, "Minnesota Twins", PRESEASON),
    (10739, "Minnesota Twins", MLB),
    (10736, "Pittsburgh Pirates", MLB),
    (10707, "Los Angeles Dodgers", MLB),
    (10710, "Arizona Diamondbacks", MLB),
]


def _event(eid, *, home_name, home_id, away_name, away_id, sport_id=MLB):
    return {
        "id": eid, "sport_id": sport_id,
        "home_team_name": home_name, "home_team_id": home_id,
        "away_team_name": away_name, "away_team_id": away_id,
    }


def _binding(eid, side, before, before_name, after, after_name, defect="cross_club"):
    return PlannedBinding(
        event_id=eid, side=side,
        expected_before_id=before, before_name=before_name,
        after_id=after, after_name=after_name,
        defect=defect, sport_id=MLB, matchup="X @ Y",
        commence_time="2026-08-16 17:35:00+00",
    )


def _install_plan(monkeypatch, plan):
    async def _load():
        return plan, "ok"

    monkeypatch.setattr(rail, "_load_plan", _load)


# ── the certification's own specimen ───────────────────────────────────────


class TestTheCertificationSpecimen:
    """C-APPLY-PRE's BLOCK, run against the shipping function."""

    @pytest.mark.asyncio
    async def test_a_candidate_that_appeared_after_review_is_never_written(
        self, monkeypatch
    ):
        """Reviewed [(1001, away)]. 2002:away appears afterwards. Only 1001 moves.

        Both events are defective and both are repairable, so a rail that
        re-derived would write both and every after-measurement would applaud.
        """
        reviewed = _binding(1001, "away", 855, "Minnesota Twins", 10709, "Boston Red Sox")
        plan = build_binding_plan([reviewed])
        _install_plan(monkeypatch, plan)

        session = _ApplySession(
            [
                _event(1001, home_name="Pittsburgh Pirates", home_id=10736,
                       away_name="Boston Red Sox", away_id=855),
                # Arrived after the plan was reviewed. Same defect class.
                _event(2002, home_name="Pittsburgh Pirates", home_id=10736,
                       away_name="Boston Red Sox", away_id=855),
            ],
            TEAMS,
        )

        out = await repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["applied"] is True
        assert session.updates == [(1001, "away", 10709)]
        assert session.events[2002]["away_team_id"] == 855, (
            "the out-of-plan candidate was written — this is the C-APPLY-PRE defect"
        )
        assert out["census"] == {"planned": 1, "applied": 1, "drifted": 0}

    @pytest.mark.asyncio
    async def test_the_apply_path_never_runs_the_candidate_scan(self, monkeypatch):
        """Not 'it rejects extra rows' — it never asks the question.

        The double raises on the candidate SQL, so this passes only if the scan is
        genuinely absent from the path rather than filtered afterwards.
        """
        plan = build_binding_plan(
            [_binding(1001, "away", 855, "Minnesota Twins", 10709, "Boston Red Sox")]
        )
        _install_plan(monkeypatch, plan)
        session = _ApplySession(
            [_event(1001, home_name="Pittsburgh Pirates", home_id=10736,
                    away_name="Boston Red Sox", away_id=855)],
            TEAMS,
        )

        await repair(session, apply=True, plan_hash=plan.plan_hash)

        assert session.scans == 0

    @pytest.mark.asyncio
    async def test_verification_reads_the_plans_events_not_the_population(
        self, monkeypatch
    ):
        """`miswired_after=0` over the whole population is the false comfort.

        What this reports instead is: of the sides I was approved to write, how many
        now dereference correctly — a statement about the approved set.
        """
        plan = build_binding_plan(
            [_binding(1001, "away", 855, "Minnesota Twins", 10709, "Boston Red Sox")]
        )
        _install_plan(monkeypatch, plan)
        session = _ApplySession(
            [
                _event(1001, home_name="Pittsburgh Pirates", home_id=10736,
                       away_name="Boston Red Sox", away_id=855),
                _event(9009, home_name="Boston Red Sox", home_id=855,
                       away_name="Pittsburgh Pirates", away_id=10736),
            ],
            TEAMS,
        )

        out = await repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["verified_plan_sides"]["sound"] == 1
        assert out["verified_plan_sides"]["still_defective"] == 0
        assert "miswired_after" not in out, (
            "a population-wide number here is the statistic that hid the defect"
        )


# ── the four refusals ──────────────────────────────────────────────────────


class TestRefusesByName:

    @pytest.mark.asyncio
    async def test_apply_without_a_hash_is_refused(self, monkeypatch):
        plan = build_binding_plan(
            [_binding(1001, "away", 855, "Minnesota Twins", 10709, "Boston Red Sox")]
        )
        _install_plan(monkeypatch, plan)
        session = _ApplySession([], TEAMS)

        out = await repair(session, apply=True)

        assert out["applied"] is False
        assert out["reason_codes"] == [REASON_PLAN_HASH_MISMATCH]
        assert session.updates == []
        assert session.commits == 0

    @pytest.mark.asyncio
    async def test_a_stale_hash_is_refused_and_both_hashes_are_reported(
        self, monkeypatch
    ):
        """The operator must be able to see WHICH plan they were holding."""
        plan = build_binding_plan(
            [_binding(1001, "away", 855, "Minnesota Twins", 10709, "Boston Red Sox")]
        )
        _install_plan(monkeypatch, plan)
        session = _ApplySession([], TEAMS)

        out = await repair(session, apply=True, plan_hash="a-hash-from-yesterday")

        assert out["reason_codes"] == [REASON_PLAN_HASH_MISMATCH]
        assert out["presented_plan_hash"] == "a-hash-from-yesterday"
        assert out["artifact_plan_hash"] == plan.plan_hash
        assert session.updates == []

    @pytest.mark.asyncio
    async def test_a_missing_artifact_is_refused(self, monkeypatch):
        async def _none():
            return None, REASON_PLAN_MISSING

        monkeypatch.setattr(rail, "_load_plan", _none)
        session = _ApplySession([], TEAMS)

        out = await repair(session, apply=True, plan_hash="anything")

        assert out["reason_codes"] == [REASON_PLAN_MISSING]
        assert session.updates == []

    @pytest.mark.asyncio
    async def test_a_corrupt_artifact_is_refused_as_corrupt_not_as_missing(self, monkeypatch):
        """Distinct readings. 'Absent' invites a fresh dry-run; 'edited in the
        store' is a security-shaped event and must not be papered over.

        CONVERTED, queue 365 — this test used to be the sharpest dead-oracle
        specimen in the repo, and it was on the apply-safety rail itself.

        It read::

            async def _corrupt():
                return None, REASON_PLAN_CORRUPT
            monkeypatch.setattr(rail, "_load_plan", _corrupt)

        which asserts the binder behaves correctly GIVEN the right reason. The
        actual defect was that nothing ever produced the right reason:
        ``_load_plan`` flattened ``decode_envelope``'s correct
        ``ChecksumMismatch`` classification into prose, ``bind_apply`` matched on
        the corrupt CONSTANT, and the whole path fell through to
        ``PLAN_ARTIFACT_MISSING`` — telling an attended operator the plan never
        existed and sending them to regenerate it, which is the one action that
        destroys the evidence of an edited store. **A test that patches past the
        boundary containing the bug is green by construction**, and this one was,
        inside a 60-test suite, for as long as the bug existed.

        Now only the TRANSPORT is faked. The envelope is real, the tamper is
        real, and the classification comes from production ``decode_envelope``;
        the reason code is produced by the shipping ``_load_plan`` rather than
        handed to the binder. Revert the corrupt-vs-missing fix and this goes red.
        """
        import app.services.durable_snapshots as snaps
        from app.utils import durable_state as ds
        from app.utils.durable_state import DurableEnvelope, decode_envelope

        # A REAL checksum failure: build a valid envelope, then alter the payload
        # without re-checksumming. Nothing here asserts the status into being.
        envelope = DurableEnvelope.build(
            identity="repair:event-team-binding:plan",
            schema_version="event-team-binding-apply-plan/v2",
            payload={
                "schema": "event-team-binding-apply-plan/v2",
                "rows": [],
                "plan_hash": "x",
            },
            complete=True,
            source="test",
        )
        read = decode_envelope(
            {
                "identity": envelope.identity,
                "schema_version": envelope.schema_version,
                "generation": envelope.generation,
                "generated_at": envelope.generated_at.isoformat(),
                "payload": {
                    "schema": "event-team-binding-apply-plan/v2",
                    "rows": [{"edited": True}],
                },
                "checksum": envelope.checksum,  # stale: belongs to the ORIGINAL payload
                "complete": True,
                "source": "test",
            },
            tier="durable",
            expected_version="event-team-binding-apply-plan/v2",
            max_age_s=14 * 86400,
        )
        # Premise check. If production stops calling this a checksum mismatch,
        # the specimen below proves nothing and must fail loudly rather than pass.
        assert read.status == ds.MALFORMED
        assert read.error_class == "ChecksumMismatch"

        async def _read(*_a, **_k):
            return read

        monkeypatch.setattr(snaps, "read_snapshot_standalone", _read)
        session = _ApplySession([], TEAMS)

        out = await repair(session, apply=True, plan_hash="anything")

        assert out["reason_codes"] == [REASON_PLAN_CORRUPT], (
            "the shipping loader did not classify a torn artifact as CORRUPT — "
            "if this says PLAN_ARTIFACT_MISSING, an attended operator is being "
            "told to regenerate the plan over an edited store"
        )
        assert session.updates == [], "a refused apply wrote to the database"

    @pytest.mark.asyncio
    async def test_an_empty_plan_cannot_be_applied(self, monkeypatch):
        plan = build_binding_plan([])
        _install_plan(monkeypatch, plan)
        session = _ApplySession([], TEAMS)

        out = await repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["reason_codes"] == [REASON_PLAN_EMPTY]


class TestCompareAndSet:

    @pytest.mark.asyncio
    async def test_a_side_that_moved_since_review_is_skipped_and_named(
        self, monkeypatch
    ):
        """The reviewer approved a decision about a state that no longer exists."""
        plan = build_binding_plan(
            [_binding(1001, "away", 855, "Minnesota Twins", 10709, "Boston Red Sox")]
        )
        _install_plan(monkeypatch, plan)
        session = _ApplySession(
            [_event(1001, home_name="Pittsburgh Pirates", home_id=10736,
                    # someone re-bound this side between review and apply
                    away_name="Boston Red Sox", away_id=10739)],
            TEAMS,
        )

        out = await repair(session, apply=True, plan_hash=plan.plan_hash)

        assert session.updates == []
        assert out["census"]["drifted"] == 1
        assert out["census"]["applied"] == 0
        assert out["drift"][0]["reason_code"] == REASON_CONCURRENT_DRIFT
        assert out["drift"][0]["event_id"] == 1001
        assert session.events[1001]["away_team_id"] == 10739, "untouched"

    @pytest.mark.asyncio
    async def test_one_drifted_side_does_not_cancel_the_others(self, monkeypatch):
        """179 approved writes must not be lost because one row moved."""
        plan = build_binding_plan([
            _binding(1001, "away", 855, "Minnesota Twins", 10709, "Boston Red Sox"),
            _binding(1002, "away", 855, "Minnesota Twins", 10709, "Boston Red Sox"),
        ])
        _install_plan(monkeypatch, plan)
        session = _ApplySession(
            [
                _event(1001, home_name="Pittsburgh Pirates", home_id=10736,
                       away_name="Boston Red Sox", away_id=10739),  # drifted
                _event(1002, home_name="Pittsburgh Pirates", home_id=10736,
                       away_name="Boston Red Sox", away_id=855),    # as reviewed
            ],
            TEAMS,
        )

        out = await repair(session, apply=True, plan_hash=plan.plan_hash)

        assert out["census"] == {"planned": 2, "applied": 1, "drifted": 1}
        assert session.updates == [(1002, "away", 10709)]
        assert session.commits == 1

    @pytest.mark.asyncio
    async def test_nothing_commits_when_every_row_drifted(self, monkeypatch):
        plan = build_binding_plan(
            [_binding(1001, "away", 855, "Minnesota Twins", 10709, "Boston Red Sox")]
        )
        _install_plan(monkeypatch, plan)
        session = _ApplySession(
            [_event(1001, home_name="Pittsburgh Pirates", home_id=10736,
                    away_name="Boston Red Sox", away_id=10739)],
            TEAMS,
        )

        await repair(session, apply=True, plan_hash=plan.plan_hash)

        assert session.commits == 0


# ── the artifact itself ────────────────────────────────────────────────────


class TestThePlanArtifact:

    def test_the_address_is_order_independent(self):
        a = _binding(1, "home", 855, "Minnesota Twins", 10739, "Minnesota Twins")
        b = _binding(2, "away", 10707, "Los Angeles Dodgers", 10710, "Arizona Diamondbacks")
        assert build_binding_plan([a, b]).plan_hash == build_binding_plan([b, a]).plan_hash

    def test_the_two_sides_of_one_event_are_two_different_work_items(self):
        home = _binding(1, "home", 855, "Minnesota Twins", 10739, "Minnesota Twins")
        away = _binding(1, "away", 855, "Minnesota Twins", 10739, "Minnesota Twins")
        assert home.row_key != away.row_key
        assert build_binding_plan([home]).plan_hash != build_binding_plan([away]).plan_hash

    def test_a_swapped_club_name_is_a_different_plan(self):
        """The approval is over CLUBS. Ids are how it is executed, not what it says."""
        honest = _binding(1, "home", 855, "Minnesota Twins", 10709, "Boston Red Sox")
        relabelled = _binding(1, "home", 855, "Minnesota Twins", 10709, "New York Yankees")
        assert (
            build_binding_plan([honest]).plan_hash
            != build_binding_plan([relabelled]).plan_hash
        )

    def test_a_moved_before_id_is_a_different_plan(self):
        a = _binding(1, "home", 855, "Minnesota Twins", 10709, "Boston Red Sox")
        b = _binding(1, "home", 870, "Minnesota Twins", 10709, "Boston Red Sox")
        assert build_binding_plan([a]).plan_hash != build_binding_plan([b]).plan_hash

    def test_provenance_is_outside_the_address(self):
        """A corrected kickoff time must not invalidate a reviewed plan — an
        address that moved for a cosmetic reason trains operators to wave
        mismatches through, and then the gate is decoration."""
        a = _binding(1, "home", 855, "Minnesota Twins", 10709, "Boston Red Sox")
        b = PlannedBinding(
            event_id=1, side="home", expected_before_id=855,
            before_name="Minnesota Twins", after_id=10709, after_name="Boston Red Sox",
            defect="cross_club", sport_id=MLB, matchup="COMPLETELY DIFFERENT",
            commence_time="1999-01-01 00:00:00+00",
        )
        assert build_binding_plan([a]).plan_hash == build_binding_plan([b]).plan_hash

    def test_a_round_trip_survives_and_a_tampered_one_does_not(self):
        plan = build_binding_plan(
            [_binding(1, "home", 855, "Minnesota Twins", 10709, "Boston Red Sox")],
            context={"issue": "#1798"},
        )
        back, reason = decode_binding_plan(plan.as_payload())
        assert reason == "ok" and back.plan_hash == plan.plan_hash

        tampered = plan.as_payload()
        tampered["rows"][0]["after_id"] = 99999
        none_plan, why = decode_binding_plan(tampered)
        assert none_plan is None and why == REASON_PLAN_CORRUPT

    def test_a_calibration_plan_is_not_a_binding_plan(self):
        """Two rails, two schemas. An apply must never consume the other's artifact."""
        from app.utils.repair_apply_plan import APPLY_PLAN_SCHEMA

        assert BINDING_APPLY_PLAN_SCHEMA != APPLY_PLAN_SCHEMA
        payload = build_binding_plan(
            [_binding(1, "home", 855, "Minnesota Twins", 10709, "Boston Red Sox")]
        ).as_payload()
        payload["schema"] = APPLY_PLAN_SCHEMA
        plan, why = decode_binding_plan(payload)
        assert plan is None and why == REASON_PLAN_CORRUPT

    def test_out_of_plan_keys_are_reported_by_key(self):
        plan = build_binding_plan(
            [_binding(1, "home", 855, "Minnesota Twins", 10709, "Boston Red Sox")]
        )
        assert mutations_outside_approved_keys(plan, ["1:home"]) == []
        assert mutations_outside_approved_keys(plan, ["1:home", "1:away", "2:home"]) == [
            "1:away", "2:home",
        ]


class TestTheDryRunEmitsAndPersistsThePlan:

    @pytest.mark.asyncio
    async def test_the_hash_the_dry_run_returns_is_the_one_the_apply_accepts(
        self, monkeypatch
    ):
        """End to end through the REAL persistence helpers, so the re-digest on
        read is exercised rather than mocked past."""
        from tests.test_kalshi_fabricated_loss_p062 import _DurableStore
        from tests.test_repair_event_team_binding import TEAMS as SCAN_TEAMS, _FakeSession, _row

        store = _DurableStore().install(monkeypatch)

        scan_row = _row(
            id=1001,
            away_team_id=855, away_bound_name="Minnesota Twins", away_bound_sport=PRESEASON,
        )
        dry = await repair(_FakeSession([scan_row], SCAN_TEAMS), apply=False)

        assert dry["plan_persisted"] is True
        assert dry["plan_hash"]
        assert dry["plan_rows"] == 1
        assert dry["plan_hash"] in dry["apply_command"]

        stored = store.payload(rail.PLAN_IDENTITY)
        assert stored["schema"] == BINDING_APPLY_PLAN_SCHEMA
        assert stored["rows"][0]["expected_before_id"] == 855

        session = _ApplySession(
            [_event(1001, home_name="Pittsburgh Pirates", home_id=10736,
                    away_name="Boston Red Sox", away_id=855)],
            TEAMS,
        )
        out = await repair(session, apply=True, plan_hash=dry["plan_hash"])

        assert out["applied"] is True
        assert session.updates == [(1001, "away", 10709)]

    @pytest.mark.asyncio
    async def test_a_plan_that_did_not_persist_yields_no_hash_and_says_so(
        self, monkeypatch
    ):
        """Handing back a hash for an artifact that is not there would produce a
        refusal the operator cannot diagnose (gotcha #53: an absence and a
        failure must not share a reading)."""
        from tests.test_kalshi_fabricated_loss_p062 import _DurableStore
        from tests.test_repair_event_team_binding import TEAMS as SCAN_TEAMS, _FakeSession, _row

        store = _DurableStore().install(monkeypatch)
        store.forced_status[rail.PLAN_IDENTITY] = "rejected"

        scan_row = _row(
            id=1001,
            away_team_id=855, away_bound_name="Minnesota Twins", away_bound_sport=PRESEASON,
        )
        dry = await repair(_FakeSession([scan_row], SCAN_TEAMS), apply=False)

        assert dry["plan_persisted"] is False
        assert dry["plan_hash"] is None
        assert "NO PLAN HASH" in dry["apply_command"]


class TestRegisteredOnTheRail:

    def test_the_dispatcher_forwards_plan_hash_to_this_repair(self):
        """The gate is only a gate if the parameter actually arrives."""
        import inspect

        from app.routes.admin_repairs import _REPAIRS, run_repair

        assert _REPAIRS["event-team-binding"] == (
            "app.tasks.repair_event_team_binding", "repair",
        )
        assert "plan_hash" in inspect.signature(run_repair).parameters
        assert "plan_hash" in inspect.signature(repair).parameters

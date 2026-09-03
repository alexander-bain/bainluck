"""A matcher pass that ran stays having run (#2803, repairing CERT-819).

WHAT CERT-819 BLOCKED, and what these guards pin. ``GET
/api/admin/match-receipts`` derived ``coverage.backlog_pass_has_run`` from a
``GROUP BY phase`` over ``market_match_receipts``. That table is ONE MUTABLE ROW
PER MARKET and the upsert sets ``phase = excluded.phase``, so Pass 1/2
re-attempting the same open unlinked markets erases every ``pass3_backlog``
label and the endpoint reports "the backlog pass has never run" about a pass
that ran minutes ago. An admin reading that false negative goes hunting a beat
that is working.

The whole point of the repair is that the run fact lives somewhere a later pass
cannot reach, so the tests that matter here are the ORDERING ones: record Pass
3, then let Pass 1 and Pass 2 write as much as they like, and Pass 3's answer
must not move.

WHY THE STORE IS FAKED AND THE CONTRACT IS NOT. There is no Postgres in the
sandbox, and ``publish_snapshot``'s upsert is Postgres-specific
(``CAST(... AS jsonb)``, ``SET LOCAL statement_timeout``). ``_FakeDurableStore``
reimplements the ONE property the repair leans on — the generation-guarded
replace, ``WHERE generation <= EXCLUDED.generation``, copied from
``durable_snapshots._UPSERT_SQL`` — and nothing else. Everything above the SQL
is the real code: the real ``DurableEnvelope.build`` (so checksum and generation
are really computed) and the real ``decode_envelope`` (so version, checksum,
completeness and age are really classified).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.utils import match_receipts as mr
from app.utils import matcher_pass_runs as pr
from app.utils.durable_state import decode_envelope

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


class _FakeDurableStore:
    """``durable_state_snapshots`` minus Postgres. One row per identity."""

    def __init__(self):
        self.rows: dict[str, object] = {}
        self.writes: list[str] = []
        self.fail = False

    def upsert(self, envelope) -> str:
        if self.fail:
            raise RuntimeError("durable store is down")
        self.writes.append(envelope.identity)
        existing = self.rows.get(envelope.identity)
        # The generation guard, verbatim in behaviour: an older writer matches
        # the conflict, fails the predicate, and writes NOTHING.
        if existing is not None and existing.generation > envelope.generation:
            return "superseded"
        self.rows[envelope.identity] = envelope
        return "ok"

    def install(self):
        """Patch only the two SQL-touching functions; the rest is real code."""
        store = self

        async def _publish(envelope):
            try:
                return {"status": store.upsert(envelope), "identity": envelope.identity}
            except Exception as exc:  # mirrors publish_snapshot: never raises
                return {"status": "error", "error_class": exc.__class__.__name__}

        async def _read(_db, identity, *, expected_version=None, max_age_s=None, now=None):
            from app.utils.durable_state import EnvelopeRead

            if store.fail:
                raise RuntimeError("durable store is down")
            env = store.rows.get(identity)
            if env is None:
                return EnvelopeRead(status="missing", tier="durable")
            return decode_envelope(
                {
                    "identity": env.identity,
                    "schema_version": env.schema_version,
                    "generation": env.generation,
                    "generated_at": env.generated_at,
                    "payload": env.payload,
                    "checksum": env.checksum,
                    "complete": env.complete,
                    "source": env.source,
                },
                tier="durable",
                expected_version=expected_version,
                max_age_s=max_age_s,
                now=now,
            )

        return patch.multiple(
            "app.services.durable_snapshots",
            publish_snapshot_standalone=_publish,
            read_snapshot=_read,
        )


def _record(store, phase, *, at=NOW, rows=100, eligible=None):
    with store.install():
        return asyncio.run(
            pr.record_pass_run(
                phase=phase, ran_at=at, rows_attempted=rows, eligible_total=eligible
            )
        )


def _read(store, phase, *, now=NOW, witness=None):
    with store.install():
        return asyncio.run(
            pr.read_pass_run(object(), phase, now=now, receipt_witness=witness)
        )


class TestARunThatHappenedStaysHavingHappened:
    """CERT-819's required repair: durable, monotone, and guarded across the
    Pass 3 -> later Pass 1/2 -> still true sequence."""

    def test_a_recorded_run_reads_back_with_what_it_did(self):
        store = _FakeDurableStore()
        assert _record(
            store, mr.PHASE_PASS3_BACKLOG, rows=3000, eligible=36966
        )["status"] == "ok"

        fact = _read(store, mr.PHASE_PASS3_BACKLOG)
        assert fact.has_run is True
        assert fact.status == "ok"
        assert fact.last_run_at == NOW
        assert fact.rows_attempted == 3000
        assert fact.eligible_total == 36966

    def test_pass_1_and_2_cannot_unmake_pass_3s_run(self):
        """THE GUARD CERT-819 ASKED FOR, in its own words: Pass 3, then later
        Pass 1/2, then still true.

        In the blocked version this is where the answer flipped back to false,
        because both later passes rewrote the same rows Pass 3 had labelled.
        """
        store = _FakeDurableStore()
        _record(store, mr.PHASE_PASS3_BACKLOG, at=NOW, rows=3000)
        assert _read(store, mr.PHASE_PASS3_BACKLOG).has_run is True

        # 96 cycles of both upstream passes — a full day of the real beat.
        for cycle in range(96):
            later = NOW + timedelta(minutes=15 * (cycle + 1))
            _record(store, mr.PHASE_PASS1_TICKER, at=later, rows=138676)
            _record(store, mr.PHASE_PASS2_GENERAL, at=later, rows=500)

        fact = _read(store, mr.PHASE_PASS3_BACKLOG, now=NOW + timedelta(days=1))
        assert fact.has_run is True, (
            "a day of Pass 1/2 writes unmade Pass 3's run — CERT-819's defect"
        )
        # Unchanged, not merely still true: the row is Pass 3's alone.
        assert fact.last_run_at == NOW
        assert fact.rows_attempted == 3000

    def test_each_pass_owns_a_separate_row(self):
        """The mechanism behind the test above, stated directly. If two passes
        ever share an identity, the last writer wins and the guard is theatre."""
        identities = {
            pr.pass_run_identity(p)
            for p in (
                mr.PHASE_PASS1_TICKER, mr.PHASE_PASS2_GENERAL, mr.PHASE_PASS3_BACKLOG,
            )
        }
        assert len(identities) == 3

        store = _FakeDurableStore()
        _record(store, mr.PHASE_PASS3_BACKLOG)
        _record(store, mr.PHASE_PASS1_TICKER)
        assert len(store.rows) == 2
        assert pr.pass_run_identity(mr.PHASE_PASS3_BACKLOG) in store.rows

    def test_a_run_does_not_expire(self):
        """A run in July is still a run in September. The shared durable reader
        defaults to a 7-day ``max_age_s``, which would have classified an old
        row ``stale`` — and a stale run read as "never ran" is the same false
        negative the repair exists to remove."""
        from app.utils.durable_state import DEFAULT_MAX_AGE_S

        store = _FakeDurableStore()
        _record(store, mr.PHASE_PASS3_BACKLOG, at=NOW)

        much_later = NOW + timedelta(seconds=DEFAULT_MAX_AGE_S * 60)
        fact = _read(store, mr.PHASE_PASS3_BACKLOG, now=much_later)
        assert fact.has_run is True
        assert fact.status == "ok"
        # …and the age is published, so a reader can still judge staleness.
        assert fact.age_s(much_later) > DEFAULT_MAX_AGE_S

    def test_a_delayed_older_writer_cannot_roll_the_run_back(self):
        """Monotone against clock skew and retries, not just against Pass 1/2."""
        store = _FakeDurableStore()
        _record(store, mr.PHASE_PASS3_BACKLOG, at=NOW, rows=3000)

        stale_write = _record(
            store, mr.PHASE_PASS3_BACKLOG, at=NOW - timedelta(hours=6), rows=7
        )
        assert stale_write["status"] == "superseded"

        fact = _read(store, mr.PHASE_PASS3_BACKLOG)
        assert fact.has_run is True
        assert fact.rows_attempted == 3000, "an older writer overwrote a newer run"


class TestItRefusesToTurnNotKnowingIntoNo:
    """``false`` is a claim about the matcher. Everything else is a claim about
    the store, and must not be published as the first."""

    def test_no_row_is_no_evidence_not_a_no(self):
        """CERT-824. This used to answer ``False`` and call it "genuinely never
        published". It is not: the failed-write path below lands in exactly this
        state, so the read cannot tell "never ran" from "ran, write errored"."""
        fact = _read(_FakeDurableStore(), mr.PHASE_PASS3_BACKLOG)
        assert fact.has_run is None
        assert fact.status == pr.STATUS_NO_RECORD

    def test_false_is_not_reachable_from_any_read_state(self):
        """The property stated directly, over every state the store can be in.

        A per-case assertion can be satisfied one case at a time while a new
        branch quietly adds a sixth that answers ``False``."""
        from app.utils.durable_state import DurableEnvelope

        identity = pr.pass_run_identity(mr.PHASE_PASS3_BACKLOG)
        states = {}

        empty = _FakeDurableStore()
        states["missing"] = _read(empty, mr.PHASE_PASS3_BACKLOG)
        states["missing+witness"] = _read(
            empty, mr.PHASE_PASS3_BACKLOG, witness=True
        )

        down = _FakeDurableStore()
        down.fail = True
        states["unavailable"] = _read(down, mr.PHASE_PASS3_BACKLOG)

        wrong = _FakeDurableStore()
        wrong.upsert(
            DurableEnvelope.build(
                identity=identity, schema_version="from-the-future",
                generated_at=NOW, payload={"phase": mr.PHASE_PASS3_BACKLOG},
            )
        )
        states["wrong_version"] = _read(wrong, mr.PHASE_PASS3_BACKLOG)

        recorded = _FakeDurableStore()
        _record(recorded, mr.PHASE_PASS3_BACKLOG)
        states["ok"] = _read(recorded, mr.PHASE_PASS3_BACKLOG)

        for name, fact in states.items():
            assert fact.has_run is not False, (
                f"the {name} read published 'the backlog pass never ran', a "
                "claim no read state can support (CERT-824)"
            )
        # …and not vacuous: the states really are distinct, and one is a true.
        assert {f.status for f in states.values()} >= {
            pr.STATUS_NO_RECORD, pr.STATUS_WITNESSED, "unavailable",
            "wrong_version", "ok",
        }
        assert states["ok"].has_run is True

    def test_a_store_that_does_not_answer_is_unknown(self):
        store = _FakeDurableStore()
        _record(store, mr.PHASE_PASS3_BACKLOG)
        store.fail = True

        fact = _read(store, mr.PHASE_PASS3_BACKLOG)
        assert fact.has_run is None, "a read failure was published as 'never ran'"
        assert fact.status == "unavailable"
        assert fact.error_class == "RuntimeError"

    def test_a_row_from_another_contract_is_unknown(self):
        """A version the reader does not understand is not evidence of absence."""
        from app.utils.durable_state import DurableEnvelope

        store = _FakeDurableStore()
        store.upsert(
            DurableEnvelope.build(
                identity=pr.pass_run_identity(mr.PHASE_PASS3_BACKLOG),
                schema_version="matcher-pass-run/v0-from-the-future",
                generated_at=NOW,
                payload={"phase": mr.PHASE_PASS3_BACKLOG},
            )
        )
        fact = _read(store, mr.PHASE_PASS3_BACKLOG)
        assert fact.has_run is None
        assert fact.status == "wrong_version"

    def test_the_published_block_carries_the_status_not_just_the_answer(self):
        store = _FakeDurableStore()
        store.fail = True
        published = _read(store, mr.PHASE_PASS3_BACKLOG).as_dict(NOW)
        assert published["has_run"] is None
        assert published["status"] == "unavailable"
        assert "not 'never ran'" in published["note"]

    def test_recording_never_costs_the_matcher(self):
        """A record is not a constraint. The backlog pass must survive a durable
        store that is entirely down."""
        store = _FakeDurableStore()
        store.fail = True
        stage = _record(store, mr.PHASE_PASS3_BACKLOG)
        assert stage["status"] == "error"

    def test_a_run_whose_write_failed_is_not_a_no_once_the_store_recovers(self):
        """CERT-824'S EXACT SEQUENCE: run -> write error -> recovery -> read.

        The test above is the reason this one has to exist. Because recording is
        non-fatal — and it must stay non-fatal, a telemetry row cannot be
        allowed to stop the backlog pass — an errored write is a SUPPORTED
        outcome that leaves no row. A later healthy read then finds the same
        empty store a pass that never ran would leave, and the blocked version
        published that as ``false``: CERT-824 reproduced ``ran=True,
        record_stage='error', has_run=False``. There is no read that can undo
        this, so the only repair is that ``false`` is never the answer.
        """
        store = _FakeDurableStore()

        store.fail = True                       # the durable store is down…
        stage = _record(store, mr.PHASE_PASS3_BACKLOG, rows=3000)
        assert stage["status"] == "error", "this arm must exercise a failed write"
        assert store.rows == {}, "the failed write must really have left no row"

        store.fail = False                      # …and comes back, healthy.
        fact = _read(store, mr.PHASE_PASS3_BACKLOG)

        assert fact.has_run is not False, (
            "a pass that ran was published as 'never ran' because its non-fatal "
            "record write failed — CERT-824"
        )
        assert fact.has_run is None
        assert fact.status == pr.STATUS_NO_RECORD
        assert "not 'never ran'" in fact.as_dict(NOW)["note"]

    def test_a_live_receipt_label_witnesses_the_run_the_lost_write_dropped(self):
        """The same sequence, with the recovery the endpoint actually has.

        Pass 3's flush is the only writer of ``phase=pass3_backlog``, so a live
        label is proof of a run even with no durable row. Absence of the label
        proves nothing (that is CERT-819), which is why the witness can only
        ever turn a null into a true."""
        store = _FakeDurableStore()
        store.fail = True
        assert _record(store, mr.PHASE_PASS3_BACKLOG)["status"] == "error"
        store.fail = False

        witnessed = _read(store, mr.PHASE_PASS3_BACKLOG, witness=True)
        assert witnessed.has_run is True
        assert witnessed.status == pr.STATUS_WITNESSED
        # It reports no run time, because it does not have one to report.
        assert witnessed.last_run_at is None

        # And it cannot invent one: no row, no label, still not a claim.
        assert _read(store, mr.PHASE_PASS3_BACKLOG, witness=False).has_run is None

    def test_the_witness_never_overrides_the_durable_row(self):
        """The census is the fallback, not the source. If it could outrank the
        durable row, CERT-819's mutable label would be back in the answer."""
        store = _FakeDurableStore()
        _record(store, mr.PHASE_PASS3_BACKLOG, rows=3000)

        for witness in (True, False, None):
            fact = _read(store, mr.PHASE_PASS3_BACKLOG, witness=witness)
            assert fact.has_run is True
            assert fact.status == "ok", "the witness displaced the durable read"
            assert fact.rows_attempted == 3000


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, eligible=0):
        self._eligible = eligible

    async def execute(self, _stmt):
        return _FakeResult([])

    async def scalar(self, _stmt):
        return self._eligible


class TestPass3RecordsItsOwnRun:
    """The write site, run rather than read. A source scan would pass on a call
    that is unreachable, or on one in a branch the budget never takes."""

    @staticmethod
    def _run_pass3(time_remaining):
        from app.tasks import prediction_market_matching as pmm

        stats = {"funnel": {}, "errors": []}
        recorded: list[dict] = []

        async def _fake_record(**kw):
            recorded.append(kw)
            return {"status": "ok"}

        with patch.object(pmm._pass_runs, "record_pass_run", _fake_record):
            asyncio.run(
                pmm._phase1_pass3_backlog_scan(
                    _FakeSession(eligible=36966), stats, NOW, set(), [],
                    lambda: time_remaining,
                )
            )
        return stats, recorded

    def test_a_completed_pass_records_that_it_ran(self):
        stats, recorded = self._run_pass3(time_remaining=700)

        assert len(recorded) == 1, "the backlog pass ran and recorded nothing"
        assert recorded[0]["phase"] == mr.PHASE_PASS3_BACKLOG
        assert recorded[0]["ran_at"] == NOW
        assert recorded[0]["eligible_total"] == 36966
        assert stats["funnel"]["backlog_run_recorded"] == "ok"

    def test_a_pass_skipped_for_budget_records_nothing(self):
        """It did not run, so it must not say it did.

        Since CERT-824 removed ``false``, ``true`` is the only falsifiable thing
        this flag says — which makes this guard the one holding the whole block
        up, not a symmetry check beside a stronger one."""
        from app.tasks.prediction_market_matching import (
            _BACKLOG_MIN_SECONDS_REMAINING,
        )

        stats, recorded = self._run_pass3(
            time_remaining=_BACKLOG_MIN_SECONDS_REMAINING - 1
        )
        assert stats["funnel"]["backlog_skipped_budget"] is True
        assert recorded == [], "a pass that never started claimed a run"

    def test_a_pass_that_dies_mid_loop_still_records_its_run(self):
        """Why the call sits in the ``finally``. A pass that got halfway through
        the backlog and then threw DID drive the coverage number down, and the
        reader needs that fact more than it needs a clean one — a crash that
        also erased the evidence of the crash is the worst of both."""
        from app.tasks import prediction_market_matching as pmm

        stats = {"funnel": {}, "errors": []}
        recorded: list[dict] = []

        async def _fake_record(**kw):
            recorded.append(kw)
            return {"status": "ok"}

        class _WithBacklog(_FakeSession):
            """Never-attempted query yields three markets; the stale top-up
            query (which returns (id, last_attempted_at) pairs) yields none."""

            def __init__(self):
                super().__init__(eligible=36966)
                self._calls = 0

            async def execute(self, _stmt):
                self._calls += 1
                return _FakeResult([101, 102, 103] if self._calls == 1 else [])

        async def _boom(_session, _market_id):
            raise RuntimeError("boom, mid-loop")

        with patch.object(pmm._pass_runs, "record_pass_run", _fake_record), \
                patch.object(pmm, "_load_market_row", _boom):
            with pytest.raises(RuntimeError):
                asyncio.run(
                    pmm._phase1_pass3_backlog_scan(
                        _WithBacklog(), stats, NOW, set(), [], lambda: 700,
                    )
                )

        assert len(recorded) == 1, (
            "the pass ran, threw, and left no record that it had run"
        )
        assert recorded[0]["phase"] == mr.PHASE_PASS3_BACKLOG

    def test_the_real_pass_survives_a_failed_write_and_is_still_not_a_no(self):
        """CERT-824 END TO END, through the real functions rather than a fake.

        The two arms above stub ``record_pass_run``, so they prove the call site
        and nothing about what the call does when the store is down. This one
        runs the real ``_phase1_pass3_backlog_scan`` against a real
        ``record_pass_run`` writing into a broken store, lets the store recover,
        and reads the real ``read_pass_run``. That is the whole path the cert
        walked to print ``ran=True, record_stage='error', has_run=False``.
        """
        from app.tasks import prediction_market_matching as pmm

        store = _FakeDurableStore()
        store.fail = True
        stats = {"funnel": {}, "errors": []}

        with store.install():
            asyncio.run(
                pmm._phase1_pass3_backlog_scan(
                    _FakeSession(eligible=36966), stats, NOW, set(), [],
                    lambda: 700,
                )
            )

        # The pass ran (it reported an eligibility count and was not skipped)
        # and its record write really did fail.
        assert stats["funnel"].get("backlog_skipped_budget") is not True
        assert stats["funnel"]["backlog_eligible_total"] == 36966
        assert stats["funnel"]["backlog_run_recorded"] == "error", (
            "this arm has to exercise the failed write, not a healthy one"
        )

        store.fail = False
        fact = _read(store, mr.PHASE_PASS3_BACKLOG)
        assert fact.has_run is not False, (
            "the backlog pass ran, its record write failed, the store came "
            "back, and the endpoint would have told an admin nothing is "
            "driving the coverage number down — CERT-824"
        )
        assert fact.status == pr.STATUS_NO_RECORD

        # THE CONTROL. Same path, healthy store: the run IS recorded and read
        # back as true, so the assertion above is not passing because Pass 3
        # never reaches its recorder.
        healthy = _FakeDurableStore()
        clean = {"funnel": {}, "errors": []}
        with healthy.install():
            asyncio.run(
                pmm._phase1_pass3_backlog_scan(
                    _FakeSession(eligible=36966), clean, NOW, set(), [],
                    lambda: 700,
                )
            )
        assert clean["funnel"]["backlog_run_recorded"] == "ok"
        assert _read(healthy, mr.PHASE_PASS3_BACKLOG).has_run is True

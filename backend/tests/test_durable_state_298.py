"""Queue 298 Item 1 — the durable-state boundary against C117's oracle (#1512).

The headline test is :class:`TestAgainstC117Corpus`: every one of C117's 34
fixture rows is replayed through the REAL implementation
(``app.utils.durable_state``) and must produce the same served source, health
verdict, task-success decision, and contract violations as the frozen oracle.
That is what stops the implementation and the contract from drifting apart —
a corpus row is a spec, not a sample.

The rest pin the pieces the corpus abstracts over: envelope decoding of real
stored bytes, the generation guard in the upsert, and the caller's handling of
ok / superseded / error publication stages.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils import durable_state as ds

FIXTURE = (
    Path(__file__).parent / "evals" / "fixtures" / "durable_state_survival_contract.json"
)

NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


# --- Corpus replay -----------------------------------------------------------


def _load_cases() -> list[dict]:
    from scripts.evals.durable_state_survival_contract import load_corpus

    return sorted(load_corpus(FIXTURE)["cases"], key=lambda row: row["id"])


def _read_from_spec(tier: str, spec: dict, artifact: dict) -> ds.EnvelopeRead:
    """Turn one fixture read-state into what the real tier reader would return.

    Every abstract state is realized as bytes/structure and pushed through the
    REAL :func:`decode_envelope` wherever the store would have answered, so the
    corpus exercises the shipped classifier rather than a restatement of it.
    """
    state = spec["state"]

    if state == "missing":
        return ds.EnvelopeRead(status=ds.MISSING, tier=tier)
    if state in ("unavailable", "tls_eof", "timeout"):
        # The store could not answer at all: construction, TLS EOF, or a command
        # deadline. All three are UNKNOWN, never "no data".
        return ds.EnvelopeRead(
            status=ds.UNAVAILABLE,
            tier=tier,
            error_class=spec.get("error_class") or "ConnectionError",
            error="store unavailable",
        )

    payload = {"body": f"{artifact['identity']}@{spec['generation']}"}
    generated_at = NOW - timedelta(seconds=spec["age_s"])
    raw = {
        "identity": artifact["identity"],
        "schema_version": spec["schema_version"],
        "generation": spec["generation"],
        "generated_at": generated_at.isoformat(),
        "payload": payload,
        "checksum": ds.checksum_payload(payload),
        "complete": spec["complete"],
        "source": "test",
    }

    if state == "wrong_type":
        # Decodes, but not to an envelope object (the shape that used to reach an
        # unguarded ``.get()``).
        raw = ["not", "an", "envelope"]
    elif state == "malformed":
        # Parses fine, but the body does not match its own checksum — a torn or
        # truncated write.
        raw["checksum"] = "0" * 64

    return ds.decode_envelope(
        raw,
        tier=tier,
        expected_version=artifact["schema_version"],
        max_age_s=artifact["max_age_s"],
        now=NOW,
    )


def _evaluate(row: dict) -> dict:
    artifact, reads, publication = row["artifact"], row["reads"], row["publication"]

    resolution = ds.resolve(
        volatile=_read_from_spec("volatile", reads["volatile"], artifact),
        durable=_read_from_spec("durable", reads["durable"], artifact),
        process=_read_from_spec("process", reads["process"], artifact),
        fresh_process=reads["fresh_process"],
    )
    errors = list(resolution.errors)

    task_success = None
    if publication["stage"] != "not_applicable":
        outcome = ds.evaluate_publication(
            compute_complete=publication["compute_complete"],
            durable_write=publication["durable_write"],
            volatile_write=publication["volatile_write"],
            cancelled=publication["cancelled"],
            prior_last_good_preserved=publication["prior_last_good_preserved"],
            torn=ds.ERR_VOLATILE_AHEAD in resolution.errors,
        )
        task_success = outcome.success
        errors.extend(outcome.errors)

    health = resolution.health(artifact["payload_verdict"], checked=artifact["checked"])

    # Surface-level guards the corpus also asserts.
    composite = row.get("composite") or {}
    if composite:
        if not composite.get("per_field_metadata"):
            errors.append(ds.ERR_COMPOSITE_ERASES)
        if composite.get("checked_zero_as_green"):
            errors.append(ds.ERR_CHECKED_ZERO_GREEN)
    poison = row.get("poison") or {}
    if poison and poison.get("healthy_siblings_survive") is not True:
        errors.append(ds.ERR_POISON_WIPES)

    errors = sorted(set(errors))
    if errors:
        health = ds.UNKNOWN

    return {
        "source": resolution.source,
        "health": health,
        "task_success": task_success,
        "errors": errors,
    }


class TestAgainstC117Corpus:
    """Every C117 case, replayed through the shipped implementation."""

    @pytest.mark.parametrize("row", _load_cases(), ids=lambda r: r["id"])
    def test_case_matches_oracle(self, row):
        assert _evaluate(row) == row["expected"]

    def test_corpus_is_not_silently_empty(self):
        """A corpus that stops loading must fail loudly, not vacuously pass."""
        cases = _load_cases()
        assert len(cases) >= 34
        # The failure classes that motivated the queue must all be represented.
        ids = {row["id"] for row in cases}
        assert {
            "redis-outage-fresh-process",
            "redis-evicted-durable-good",
            "fresh-process-rejects-process-only",
            "volatile-ahead-generation-conflict",
            "durable-write-fails",
            "checked-zero",
        } <= ids


# --- Envelope decoding -------------------------------------------------------


class TestDecodeEnvelope:
    def _raw(self, **over):
        payload = over.pop("payload", {"a": 1})
        raw = {
            "identity": "calibration:main",
            "schema_version": "v1",
            "generation": ds.generation_for(NOW),
            "generated_at": NOW.isoformat(),
            "payload": payload,
            "checksum": ds.checksum_payload(payload),
            "complete": True,
            "source": "precompute",
        }
        raw.update(over)
        return raw

    def _decode(self, raw, **kw):
        kw.setdefault("expected_version", "v1")
        kw.setdefault("max_age_s", 100)
        kw.setdefault("now", NOW)
        return ds.decode_envelope(raw, tier="durable", **kw)

    def test_healthy_envelope_is_ok(self):
        read = self._decode(self._raw())
        assert read.ok and read.envelope.identity == "calibration:main"

    def test_absent_row_is_missing_not_unavailable(self):
        assert self._decode(None).status == ds.MISSING

    def test_non_dict_is_wrong_type(self):
        assert self._decode(["nope"]).status == ds.WRONG_TYPE

    def test_checksum_mismatch_is_malformed(self):
        """A torn write can still be valid JSON — the checksum is what catches it."""
        raw = self._raw()
        raw["payload"] = {"a": 2}  # body changed, checksum did not
        read = self._decode(raw)
        assert read.status == ds.MALFORMED
        assert read.error_class == "ChecksumMismatch"

    def test_wrong_version_is_distinct_from_malformed(self):
        read = self._decode(self._raw(schema_version="v0"))
        assert read.status == ds.WRONG_VERSION

    def test_incomplete_artifact_is_not_servable(self):
        assert not self._decode(self._raw(complete=False)).ok

    def test_age_bound_is_inclusive_at_the_boundary(self):
        raw = self._raw(generated_at=(NOW - timedelta(seconds=100)).isoformat())
        assert self._decode(raw).ok
        raw = self._raw(generated_at=(NOW - timedelta(seconds=101)).isoformat())
        assert self._decode(raw).status == ds.STALE

    def test_future_stamp_is_rejected_not_clamped(self):
        """Clock skew must surface, not read as the freshest possible copy."""
        raw = self._raw(generated_at=(NOW + timedelta(seconds=30)).isoformat())
        assert self._decode(raw).status == ds.STALE

    def test_missing_generation_is_malformed(self):
        raw = self._raw()
        del raw["generation"]
        assert self._decode(raw).status == ds.MALFORMED

    def test_errors_never_leak_credentials(self):
        exc = ConnectionError("Error connecting to rediss://user:hunter2@host:10819")
        read = ds.failed_read("volatile", exc)
        assert "hunter2" not in (read.error or "")
        assert read.status == ds.UNAVAILABLE


class TestChecksumAndGeneration:
    def test_checksum_is_key_order_independent(self):
        assert ds.checksum_payload({"a": 1, "b": 2}) == ds.checksum_payload({"b": 2, "a": 1})

    def test_checksum_changes_with_content(self):
        assert ds.checksum_payload({"a": 1}) != ds.checksum_payload({"a": 2})

    def test_generation_is_monotonic_in_time(self):
        assert ds.generation_for(NOW) < ds.generation_for(NOW + timedelta(seconds=1))

    def test_naive_stamp_is_treated_as_utc(self):
        assert ds.generation_for(NOW.replace(tzinfo=None)) == ds.generation_for(NOW)


# --- Publication contract ----------------------------------------------------


class TestPublicationContract:
    def test_success_requires_the_durable_write(self):
        assert ds.evaluate_publication(
            compute_complete=True, durable_write="ok", volatile_write="ok"
        ).success
        assert not ds.evaluate_publication(
            compute_complete=True, durable_write="error", volatile_write="not_attempted"
        ).success

    def test_volatile_without_durable_is_a_violation(self):
        outcome = ds.evaluate_publication(
            compute_complete=True, durable_write="error", volatile_write="ok"
        )
        assert ds.ERR_VOLATILE_WITHOUT_DURABLE in outcome.errors
        assert not outcome.success

    def test_incomplete_compute_must_not_reach_the_durable_store(self):
        outcome = ds.evaluate_publication(
            compute_complete=False, durable_write="ok", volatile_write="not_attempted"
        )
        assert ds.ERR_INCOMPLETE_WRITES_DURABLE in outcome.errors
        assert not outcome.success

    def test_cancelled_run_cannot_publish_volatile(self):
        outcome = ds.evaluate_publication(
            compute_complete=False, durable_write="not_attempted",
            volatile_write="ok", cancelled=True,
        )
        assert ds.ERR_CANCELLED_PUBLISHED in outcome.errors

    def test_destroying_prior_last_good_is_a_violation(self):
        outcome = ds.evaluate_publication(
            compute_complete=True, durable_write="ok", volatile_write="ok",
            prior_last_good_preserved=False,
        )
        assert ds.ERR_PRIOR_DESTROYED in outcome.errors

    def test_volatile_write_failure_after_durable_still_succeeds(self):
        """The survivor landed; losing the accelerator is not a failed run."""
        assert ds.evaluate_publication(
            compute_complete=True, durable_write="ok", volatile_write="error"
        ).success

    def test_raise_if_failed_names_the_reason_and_the_preserved_state(self):
        outcome = ds.evaluate_publication(
            compute_complete=True, durable_write="error", volatile_write="ok"
        )
        with pytest.raises(RuntimeError, match="prior last-good preserved"):
            outcome.raise_if_failed("calibration")


# --- Resolution precedence ---------------------------------------------------


def _ok(tier, generation, age_s=10):
    payload = {"g": generation}
    return ds.decode_envelope(
        {
            "identity": "x", "schema_version": "v1", "generation": generation,
            "generated_at": (NOW - timedelta(seconds=age_s)).isoformat(),
            "payload": payload, "checksum": ds.checksum_payload(payload),
            "complete": True, "source": "t",
        },
        tier=tier, expected_version="v1", max_age_s=1000, now=NOW,
    )


def _gone(tier, status=ds.UNAVAILABLE):
    return ds.EnvelopeRead(status=status, tier=tier)


class TestResolutionPrecedence:
    def test_durable_survives_total_volatile_loss_on_a_fresh_process(self):
        """The exact #1512 shape: fresh dyno, Redis gone, durable answers."""
        res = ds.resolve(
            volatile=_gone("volatile"), durable=_ok("durable", 10),
            process=_gone("process", ds.MISSING), fresh_process=True,
        )
        assert res.source == ds.SOURCE_DURABLE and res.servable and not res.errors

    def test_fresh_process_may_not_serve_from_process_memory(self):
        res = ds.resolve(
            volatile=_gone("volatile"), durable=_gone("durable"),
            process=_ok("process", 9), fresh_process=True,
        )
        assert res.source == ds.SOURCE_UNAVAILABLE
        assert res.health("GREEN") == ds.UNKNOWN

    def test_warm_process_may_serve_when_both_stores_are_down(self):
        res = ds.resolve(
            volatile=_gone("volatile"), durable=_gone("durable"),
            process=_ok("process", 9), fresh_process=False,
        )
        assert res.source == ds.SOURCE_PROCESS

    def test_volatile_ahead_of_durable_is_torn_not_fresher(self):
        res = ds.resolve(
            volatile=_ok("volatile", 11), durable=_ok("durable", 10),
            process=_gone("process", ds.MISSING), fresh_process=False,
        )
        assert res.source == ds.SOURCE_DURABLE
        assert ds.ERR_VOLATILE_AHEAD in res.errors
        assert res.health("GREEN") == ds.UNKNOWN

    def test_equal_generations_serve_the_fast_tier(self):
        res = ds.resolve(
            volatile=_ok("volatile", 12), durable=_ok("durable", 12),
            process=_gone("process", ds.MISSING), fresh_process=False,
        )
        assert res.source == ds.SOURCE_VOLATILE and not res.errors

    def test_newer_durable_wins_over_older_volatile(self):
        res = ds.resolve(
            volatile=_ok("volatile", 10), durable=_ok("durable", 11),
            process=_gone("process", ds.MISSING), fresh_process=False,
        )
        assert res.source == ds.SOURCE_DURABLE and not res.errors

    def test_nothing_trustworthy_is_unknown_never_a_verdict(self):
        res = ds.resolve(
            volatile=_gone("volatile", ds.MISSING), durable=_gone("durable", ds.MISSING),
            process=_gone("process", ds.MISSING), fresh_process=True,
        )
        assert res.source == ds.SOURCE_UNAVAILABLE
        assert res.health("RED") == ds.UNKNOWN
        assert res.health("GREEN") == ds.UNKNOWN

    def test_checked_zero_can_never_be_green(self):
        res = ds.resolve(
            volatile=_ok("volatile", 10), durable=_ok("durable", 10),
            process=_gone("process", ds.MISSING), fresh_process=False,
        )
        assert res.health("GREEN", checked=0) == ds.UNKNOWN
        assert res.health("GREEN", checked=1) == "GREEN"

    def test_a_real_red_verdict_is_retained_not_softened(self):
        res = ds.resolve(
            volatile=_gone("volatile", ds.MISSING), durable=_ok("durable", 10),
            process=_gone("process", ds.MISSING), fresh_process=True,
        )
        assert res.health("RED") == "RED"


class TestProvenance:
    def test_provenance_dates_a_durable_serve(self):
        env = ds.DurableEnvelope.build(
            identity="calibration:main", schema_version="v1",
            payload={"a": 1}, generated_at=NOW - timedelta(hours=3), source="precompute",
        )
        prov = env.provenance(served_from=ds.SOURCE_DURABLE, now=NOW)
        assert prov["dated"] is True
        assert prov["age_s"] == pytest.approx(10800, abs=1)
        assert prov["generation"] == ds.generation_for(NOW - timedelta(hours=3))
        assert prov["source"] == "durable"

    def test_unavailable_status_is_typed_and_says_why(self):
        body = ds.unavailable_status(
            "sentinel:flow",
            reads={
                "volatile": ds.EnvelopeRead(ds.UNAVAILABLE, "volatile", error_class="ConnectionError"),
                "durable": ds.EnvelopeRead(ds.MISSING, "durable"),
            },
        )
        assert body["health"] == ds.UNKNOWN
        assert body["status"] == "unavailable"
        assert body["tiers"]["volatile"]["error_class"] == "ConnectionError"
        assert body["tiers"]["durable"]["status"] == ds.MISSING


# --- Store behavior ----------------------------------------------------------


class TestPublishSnapshot:
    """The caller's half of atomicity. The guard itself is one SQL predicate;
    these prove it is present and that every stage is handled honestly."""

    def _envelope(self, generation_at=NOW):
        return ds.DurableEnvelope.build(
            identity="calibration:main", schema_version="v1",
            payload={"buckets": [1]}, generated_at=generation_at, source="precompute",
        )

    def test_upsert_keeps_the_generation_guard_and_never_deletes(self):
        """A refactor that drops the WHERE would silently allow a stale writer to
        overwrite a newer good copy — the failure this table exists to prevent."""
        from app.services.durable_snapshots import _UPSERT_SQL

        sql = " ".join(str(_UPSERT_SQL).split())
        assert "ON CONFLICT (identity) DO UPDATE" in sql
        assert "WHERE durable_state_snapshots.generation <= EXCLUDED.generation" in sql
        assert "RETURNING generation" in sql
        assert "DELETE" not in sql.upper()
        # asyncpg drops a bind param followed by ``::`` — the cast must be CAST().
        assert "CAST(:payload AS jsonb)" in sql
        assert ":payload::jsonb" not in sql

    @pytest.mark.asyncio
    async def test_write_reports_ok_when_the_row_lands(self):
        from app.services.durable_snapshots import publish_snapshot

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = ds.generation_for(NOW)
        db.execute.return_value = result

        stage = await publish_snapshot(db, self._envelope())
        assert stage["status"] == "ok"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "written", [ds.generation_for(NOW), None], ids=["ok", "superseded"]
    )
    async def test_the_in_txn_write_NEVER_ends_the_callers_transaction(self, written):
        """CERT-851. This is the whole contract of the in-txn variant.

        A caller uses it to put a data write and the record of that write in ONE
        transaction, then commits once. A commit or rollback added here — the
        obvious "tidy-up" a later refactor reaches for — would split them again
        and silently restore the gap in which a durable change has an empty undo
        record. Swept over BOTH terminal statuses, because a commit hidden on
        the superseded path is just as fatal and is the one a single-status test
        would miss.
        """
        from app.services.durable_snapshots import publish_snapshot_in_txn

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = written
        db.execute.return_value = result

        stage = await publish_snapshot_in_txn(db, self._envelope())

        assert stage["status"] == ("ok" if written is not None else "superseded")
        db.commit.assert_not_awaited()
        db.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_in_txn_write_leaves_a_RAISE_for_the_caller_to_roll_back(self):
        """It still must not raise — the caller reads the status — but it must
        also not roll back, because only the caller knows what else is in the
        transaction it would be discarding."""
        from app.services.durable_snapshots import publish_snapshot_in_txn

        db = AsyncMock()
        db.execute.side_effect = RuntimeError("durable store is down")

        stage = await publish_snapshot_in_txn(db, self._envelope())

        assert stage["status"] == "error"
        assert stage["error_class"] == "RuntimeError"
        db.commit.assert_not_awaited()
        db.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_losing_the_generation_race_is_superseded_not_an_error(self):
        """A newer copy already sits there: durability IS satisfied."""
        from app.services.durable_snapshots import publish_snapshot

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None  # guard rejected our row
        db.execute.return_value = result

        stage = await publish_snapshot(db, self._envelope())
        assert stage["status"] == "superseded"

    @pytest.mark.asyncio
    async def test_database_failure_is_classified_not_raised(self):
        from app.services.durable_snapshots import publish_snapshot

        db = AsyncMock()
        db.execute.side_effect = RuntimeError("connection refused")

        stage = await publish_snapshot(db, self._envelope())
        assert stage["status"] == "error"
        assert stage["error_class"] == "RuntimeError"
        db.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_payload_is_serialized_canonically(self):
        """The stored body must hash to the stored checksum on the way back in."""
        from app.services.durable_snapshots import publish_snapshot

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = 1
        db.execute.return_value = result

        env = self._envelope()
        await publish_snapshot(db, env)
        params = db.execute.await_args_list[-1].args[1]
        assert ds.checksum_payload(json.loads(params["payload"])) == env.checksum

    @pytest.mark.asyncio
    async def test_a_concurrent_older_writer_cannot_win(self):
        """Emulate the guard: two writers, the older one must not replace."""
        from app.services.durable_snapshots import publish_snapshot

        store: dict = {}

        def _fake_execute(stmt, params=None):
            result = MagicMock()
            if params is None:  # the SET LOCAL statement_timeout
                result.scalar_one_or_none.return_value = None
                return result
            existing = store.get(params["identity"])
            if existing is None or existing <= params["generation"]:
                store[params["identity"]] = params["generation"]
                result.scalar_one_or_none.return_value = params["generation"]
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db = AsyncMock()
        db.execute.side_effect = _fake_execute

        newer = self._envelope(NOW)
        older = self._envelope(NOW - timedelta(hours=6))

        assert (await publish_snapshot(db, newer))["status"] == "ok"
        assert (await publish_snapshot(db, older))["status"] == "superseded"
        assert store["calibration:main"] == newer.generation


class TestPublishOwnedSnapshot:
    """CERT-856 — the store's half of "a receipt is not a version".

    The generation guard answers "is my copy newer", which is the right question
    for an identity naming a THING: one calibration bank, one sentinel
    scorecard, every writer producing the same thing, freshest wins. It is the
    wrong question for an identity naming an EVENT. Two applies that land on one
    identity are not two versions of one receipt — they are two receipts, and
    the second one winning destroys the first one's only proof of what it did.

    Measured, on the sibling rails: an apply unstamped row 11 and stored receipt
    ``[11]``; a same-instant run that cleared nothing reused the identity and
    replaced it with ``rows: []``, ``receipt_complete: true``. The row was
    durably cleared and no longer restorable.
    """

    OWNER_KEY = "invocation"

    def _envelope(self, owner="inv-a", generation_at=NOW, rows=()):
        return ds.DurableEnvelope.build(
            identity="repair:x:undo:1",
            schema_version="v1",
            payload={"rows": list(rows), self.OWNER_KEY: owner},
            generated_at=generation_at,
            source="repair:x:undo",
        )

    def test_the_upsert_carries_the_owner_predicate_beside_the_generation_one(self):
        """Both, not either. Dropping the owner predicate restores CERT-856;
        dropping the generation predicate restores the stale-writer defect the
        table was built for."""
        from app.services.durable_snapshots import _OWNED_UPSERT_SQL

        sql = " ".join(str(_OWNED_UPSERT_SQL).split())
        assert "ON CONFLICT (identity) DO UPDATE" in sql
        assert "WHERE durable_state_snapshots.generation <= EXCLUDED.generation" in sql
        assert "durable_state_snapshots.payload ->> :owner_key = :owner" in sql
        assert "RETURNING generation" in sql
        assert "DELETE" not in sql.upper()
        assert "CAST(:payload AS jsonb)" in sql
        assert ":payload::jsonb" not in sql

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "written", [ds.generation_for(NOW), None], ids=["ok", "refused"]
    )
    async def test_it_NEVER_ends_the_callers_transaction(self, written):
        """Same contract as the unowned in-txn write, swept over both terminal
        arms — a commit hidden on the refusal path would split the data write
        from its receipt again, which is CERT-851 restored."""
        from app.services.durable_snapshots import publish_owned_snapshot_in_txn

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = written
        result.mappings.return_value.first.return_value = None
        db.execute.return_value = result

        await publish_owned_snapshot_in_txn(
            db, self._envelope(), owner_key=self.OWNER_KEY, owner="inv-a"
        )

        db.commit.assert_not_awaited()
        db.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_empty_owner_never_reaches_the_database(self):
        """An unowned write to an owned identity is indistinguishable from a
        legacy row on the way back in, so it is refused rather than stored."""
        from app.services.durable_snapshots import publish_owned_snapshot_in_txn

        db = AsyncMock()
        stage = await publish_owned_snapshot_in_txn(
            db, self._envelope(), owner_key=self.OWNER_KEY, owner=""
        )

        assert stage["status"] == "error"
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_classify_read_resolves_to_occupied_not_superseded(self):
        """"I could not establish that this record is mine" must never read as
        "it is mine". Both are refusals, but only `superseded` tells an operator
        a good copy of THEIR run is on file."""
        from app.services.durable_snapshots import publish_owned_snapshot_in_txn

        calls = {"n": 0}

        async def _execute(stmt, params=None):
            calls["n"] += 1
            if calls["n"] <= 2:  # SET LOCAL, then the upsert
                result = MagicMock()
                result.scalar_one_or_none.return_value = None
                return result
            raise RuntimeError("the classify read fell over")

        db = AsyncMock()
        db.execute.side_effect = _execute

        stage = await publish_owned_snapshot_in_txn(
            db, self._envelope(), owner_key=self.OWNER_KEY, owner="inv-a"
        )
        assert stage["status"] == "occupied"

    # --- The predicate, emulated end to end ---------------------------------

    def _store_backed_db(self, store):
        """A database whose upsert obeys BOTH predicates, as the SQL does."""

        def _execute(stmt, params=None):
            result = MagicMock()
            if params is None:  # SET LOCAL statement_timeout
                result.scalar_one_or_none.return_value = None
                return result
            sql = " ".join(str(stmt).split())
            existing = store.get(params["identity"])
            if sql.startswith("SELECT"):
                result.mappings.return_value.first.return_value = (
                    None
                    if existing is None
                    else {
                        "generation": existing["generation"],
                        "owner": json.loads(existing["payload"]).get(
                            params["owner_key"]
                        ),
                    }
                )
                return result
            owned = existing is None or json.loads(existing["payload"]).get(
                params["owner_key"]
            ) == params["owner"]
            fresh = existing is None or existing["generation"] <= params["generation"]
            if owned and fresh:
                store[params["identity"]] = dict(params)
                result.scalar_one_or_none.return_value = params["generation"]
            else:
                result.scalar_one_or_none.return_value = None
            return result

        db = AsyncMock()
        db.execute.side_effect = _execute
        return db

    @pytest.mark.asyncio
    async def test_THE_REGRESSION_a_second_invocation_cannot_replace_the_first(self):
        """The measured CERT-856 sequence, at the store.

        A wins the identity with a real receipt; B arrives LATER (so the
        generation guard alone would wave it through) with an empty one. B is
        refused and A's receipt is still on disk, unaltered.
        """
        from app.services.durable_snapshots import publish_owned_snapshot_in_txn

        store: dict = {}
        db = self._store_backed_db(store)

        a = await publish_owned_snapshot_in_txn(
            db, self._envelope(owner="inv-a", rows=[11]),
            owner_key=self.OWNER_KEY, owner="inv-a",
        )
        b = await publish_owned_snapshot_in_txn(
            db, self._envelope(owner="inv-b", generation_at=NOW + timedelta(seconds=1)),
            owner_key=self.OWNER_KEY, owner="inv-b",
        )

        assert a["status"] == "ok"
        assert b["status"] == "occupied", "a second invocation overwrote the receipt"
        assert b["owner"] == "inv-a"
        assert json.loads(store["repair:x:undo:1"]["payload"])["rows"] == [11]

    @pytest.mark.asyncio
    async def test_CONTROL_the_SAME_invocation_may_advance_its_own_record(self):
        """Without this arm the refusal above passes for a store that refuses
        every update — which would break the rails outright, since each one
        writes an empty claim first and fills it in row by row."""
        from app.services.durable_snapshots import publish_owned_snapshot_in_txn

        store: dict = {}
        db = self._store_backed_db(store)

        await publish_owned_snapshot_in_txn(
            db, self._envelope(owner="inv-a"),
            owner_key=self.OWNER_KEY, owner="inv-a",
        )
        second = await publish_owned_snapshot_in_txn(
            db,
            self._envelope(
                owner="inv-a", generation_at=NOW + timedelta(seconds=1), rows=[11, 22]
            ),
            owner_key=self.OWNER_KEY, owner="inv-a",
        )

        assert second["status"] == "ok"
        assert json.loads(store["repair:x:undo:1"]["payload"])["rows"] == [11, 22]

    @pytest.mark.asyncio
    async def test_its_own_older_generation_is_superseded_not_occupied(self):
        """The generation guard still applies WITHIN one owner — a retry
        carrying an older copy must not walk back a newer one — and losing that
        race is reported as `superseded`, since a good copy of this run's record
        genuinely is on file."""
        from app.services.durable_snapshots import publish_owned_snapshot_in_txn

        store: dict = {}
        db = self._store_backed_db(store)

        await publish_owned_snapshot_in_txn(
            db, self._envelope(owner="inv-a", rows=[11, 22]),
            owner_key=self.OWNER_KEY, owner="inv-a",
        )
        stale = await publish_owned_snapshot_in_txn(
            db,
            self._envelope(owner="inv-a", generation_at=NOW - timedelta(hours=6)),
            owner_key=self.OWNER_KEY, owner="inv-a",
        )

        assert stale["status"] == "superseded"
        assert json.loads(store["repair:x:undo:1"]["payload"])["rows"] == [11, 22]

    @pytest.mark.asyncio
    async def test_a_row_that_predates_owners_is_left_alone(self):
        """Fail-closed. A legacy record carries no owner key, so `->> = :owner`
        is NULL and never true: it is never silently adopted and overwritten."""
        from app.services.durable_snapshots import publish_owned_snapshot_in_txn

        store = {
            "repair:x:undo:1": {
                "generation": ds.generation_for(NOW - timedelta(days=1)),
                "payload": json.dumps({"rows": [99]}),
            }
        }
        db = self._store_backed_db(store)

        stage = await publish_owned_snapshot_in_txn(
            db, self._envelope(owner="inv-a"),
            owner_key=self.OWNER_KEY, owner="inv-a",
        )

        assert stage["status"] == "occupied"
        assert json.loads(store["repair:x:undo:1"]["payload"])["rows"] == [99]

    @pytest.mark.asyncio
    async def test_the_standalone_variant_commits_a_win_and_rolls_back_a_refusal(self):
        from app.services.durable_snapshots import publish_owned_snapshot_standalone

        for status, commits, rollbacks in (("ok", 1, 0), ("occupied", 0, 1)):
            db = AsyncMock()
            sessions = _one_shot_session(db)

            with pytest.MonkeyPatch.context() as mp:
                async def _stage(_db, _env, *, owner_key, owner, _s=status):
                    return {"status": _s, "identity": _env.identity}

                mp.setattr(
                    "app.services.durable_snapshots.publish_owned_snapshot_in_txn",
                    _stage,
                )
                mp.setattr("app.tasks.base.get_task_session", sessions)
                stage = await publish_owned_snapshot_standalone(
                    self._envelope(), owner_key=self.OWNER_KEY, owner="inv-a"
                )

            assert stage["status"] == status
            assert db.commit.await_count == commits
            assert db.rollback.await_count == rollbacks


def _one_shot_session(db):
    """`get_task_session()` as an async context manager yielding ``db``."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _sessions():
        yield db

    return _sessions


class TestReadSnapshot:
    @pytest.mark.asyncio
    async def test_absent_row_is_missing(self):
        from app.services.durable_snapshots import read_snapshot

        db = AsyncMock()
        result = MagicMock()
        result.mappings.return_value.first.return_value = None
        db.execute.return_value = result

        read = await read_snapshot(db, "sentinel:flow")
        assert read.status == ds.MISSING

    @pytest.mark.asyncio
    async def test_database_failure_is_unavailable_not_missing(self):
        """A dead database must never read as 'this sentinel never ran'."""
        from app.services.durable_snapshots import read_snapshot

        db = AsyncMock()
        db.execute.side_effect = RuntimeError("could not connect")

        read = await read_snapshot(db, "sentinel:flow")
        assert read.status == ds.UNAVAILABLE
        assert not read.missing

    @pytest.mark.asyncio
    async def test_round_trip_of_a_published_row(self):
        from app.services.durable_snapshots import read_snapshot

        env = ds.DurableEnvelope.build(
            identity="sentinel:flow", schema_version="v1",
            payload={"verdict": "GREEN"}, generated_at=NOW - timedelta(minutes=5),
        )
        db = AsyncMock()
        result = MagicMock()
        result.mappings.return_value.first.return_value = {
            "identity": env.identity, "schema_version": env.schema_version,
            "generation": env.generation, "generated_at": env.generated_at,
            "payload": env.payload, "checksum": env.checksum,
            "complete": True, "source": "flow_sentinel",
        }
        db.execute.return_value = result

        read = await read_snapshot(db, "sentinel:flow", expected_version="v1", now=NOW)
        assert read.ok
        assert read.envelope.payload == {"verdict": "GREEN"}

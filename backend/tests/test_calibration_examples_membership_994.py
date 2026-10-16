"""#994 — a DataGolf bucket opens the exact members of the PUBLISHED curve.

THE READER SHIP. A reader taps a DataGolf Accuracy bucket and opens the exact
eligible examples behind that published curve on the first click, without
per-click full-cohort work.

WHAT THIS FILE PINS (no database, no Redis — both faked at their boundary):

* the producer half — :func:`verify_cells_against_fold` and
  :func:`build_published_membership` refuse every disagreement between the
  members and the fold / the payload (counts, winners, summed price, bucket
  rule, duplicates, extra or missing cells, size), and bind a membership to the
  exact bytes it was verified against; ``_publish_examples_membership`` never
  raises and never stops the payload publishing;
* the reader half — a stored artifact is re-validated in full on load; it is
  served ONLY when it provably belongs to the curve being served (byte digest,
  or the durable copy's fields and counts) and to the curve on the reader's
  screen when the page says which one that is; every other state falls back to
  the bounded live path, which says why;
* the first click with a valid membership runs no population SQL — one
  primary-key lookup of the sampled rows only — and concurrent first clicks
  read the stored membership once;
* the sample is drawn uniformly from the ENTIRE known membership of the
  (bucket, cohort), across every category and bundle cell;
* a published grade is labelled as published, and a grade corrected since is
  shown as corrected — a stale record is never presented as the current grade.

What rows Stage B emits, and that they ARE the canonical chain's rows, is
``tests/integration/test_calibration_staged_members_994_pg.py``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routes import calibration as cal
from app.utils import calibration_examples_membership as cem
from app.utils.durable_state import DurableEnvelope, EnvelopeRead

GEN = "2026-10-20T14:35:40.360309+00:00"


def _key(bucket, moved, category="golf", bundle=False):
    return json.dumps([bucket, category, moved, bundle], separators=(",", ":"))


def _records(*items):
    return ";".join(items)


# A small published DataGolf population: two moved/unmoved arms in bucket 6, a
# second category in bucket 6, and a bucket-2 cell.
CELLS = {
    _key(6, True): ["11,1101,0.64,1;11,1102,0.61,0", "12,1201,0.65,1"],
    _key(6, False): ["11,1103,0.62,0"],
    _key(6, True, category="golf_major"): ["13,1301,0.6000000000000000001,0"],
    _key(2, True): ["12,1202,0.21,0;12,1203,0.24,0"],
}


def _fold_rows(cells=CELLS):
    rows = []
    for key, values in cells.items():
        bucket, category, moved, bundle = json.loads(key)
        recs = [r for v in values for r in v.split(";")]
        rows.append(SimpleNamespace(
            bucket_idx=bucket, source="datagolf", category=category,
            price_moved=moved, is_nonexclusive_bundle=bundle,
            n=len(recs), winners=sum(r.endswith(",1") for r in recs),
            sum_prob=sum(float(r.split(",")[2]) for r in recs),
        ))
    rows.append(SimpleNamespace(
        bucket_idx=6, source="kalshi", category="golf", price_moved=True,
        is_nonexclusive_bundle=False, n=9, winners=4, sum_prob=5.0,
    ))
    return rows


def _payload_buckets(rows):
    out = {}
    for r in rows:
        k = (r.bucket_idx, r.source, r.category, r.price_moved)
        n, w = out.get(k, (0, 0))
        out[k] = (n + r.n, w + r.winners)
    return [
        {"bucket_idx": b, "source": s, "category": c, "price_moved": m, "n": n, "winners": w}
        for (b, s, c, m), (n, w) in out.items()
    ]


def _response(rows=None):
    rows = rows if rows is not None else _fold_rows()
    return {
        "generated_at": GEN,
        "population_version": "q271",
        "population_predicate_fingerprint": "ea3ef49d2a15568e11d7d8e54240bfdb",
        "buckets": _payload_buckets(rows),
    }


def _published():
    response = _response()
    payload_json = json.dumps(response)
    verified, reason = cem.verify_cells_against_fold(CELLS, _fold_rows())
    assert reason == cem.COMPLETE
    artifact, reason = cem.build_published_membership(
        verified,
        response=response,
        payload_sha256=hashlib.sha256(payload_json.encode()).hexdigest(),
        staged_unit_fingerprint="7435677428a14a4ecebfe02c9310e101",
        bank={"units": 3, "served_at": 1.0},
    )
    assert reason == cem.COMPLETE, reason
    return artifact, payload_json, response


# ---------------------------------------------------------------------------
# Producer: the fold check
# ---------------------------------------------------------------------------
class TestVerifyAgainstTheFold:
    def test_a_faithful_membership_verifies(self):
        verified, reason = cem.verify_cells_against_fold(CELLS, _fold_rows())
        assert reason == cem.COMPLETE
        assert {k: v["n"] for k, v in verified.items()} == {
            _key(6, True): 3, _key(6, False): 1, _key(6, True, "golf_major"): 1, _key(2, True): 2,
        }
        assert verified[_key(6, True)]["winners"] == 2

    def test_no_eligible_rows_is_a_complete_empty_membership(self):
        rows = [r for r in _fold_rows() if r.source != "datagolf"]
        assert cem.verify_cells_against_fold({}, rows) == ({}, cem.COMPLETE)

    def _broken(self, key, values):
        cells = dict(CELLS)
        cells[key] = values
        return cells

    @pytest.mark.parametrize(
        "cells, reason",
        [
            # A member missing from a cell: n disagrees.
            ({**CELLS, _key(6, True): ["11,1101,0.64,1;11,1102,0.61,0"]}, cem.REASON_FOLD_MISMATCH),
            # A grade flipped: winners disagree.
            ({**CELLS, _key(6, False): ["11,1103,0.62,1"]}, cem.REASON_FOLD_MISMATCH),
            # Same count and grades, different price: the summed price disagrees.
            ({**CELLS, _key(6, False): ["11,1103,0.69,0"]}, cem.REASON_FOLD_MISMATCH),
            # A price outside its own cell's bucket.
            ({**CELLS, _key(2, True): ["12,1202,0.31,0;12,1203,0.24,0"]}, cem.REASON_MALFORMED_RECORD),
            # One outcome counted in two cells.
            ({**CELLS, _key(6, False): ["11,1101,0.62,0"]}, cem.REASON_DUPLICATE_MEMBER),
            # A cell the fold does not have.
            ({**CELLS, _key(3, True): ["14,1401,0.33,0"]}, cem.REASON_FOLD_MISMATCH),
            # A cell the fold has and the members do not.
            ({k: v for k, v in CELLS.items() if k != _key(2, True)}, cem.REASON_FOLD_MISMATCH),
            # A malformed record.
            ({**CELLS, _key(6, False): ["11,1103,0.62"]}, cem.REASON_MALFORMED_RECORD),
        ],
    )
    def test_every_disagreement_refuses(self, cells, reason):
        assert cem.verify_cells_against_fold(cells, _fold_rows()) == (None, reason)

    def test_an_over_large_membership_is_refused_whole(self, monkeypatch):
        monkeypatch.setattr(cem, "MAX_MEMBERS", 3)
        assert cem.verify_cells_against_fold(CELLS, _fold_rows()) == (None, cem.REASON_TOO_LARGE)


# ---------------------------------------------------------------------------
# Producer: binding to the payload
# ---------------------------------------------------------------------------
class TestBindToThePayload:
    def test_the_artifact_carries_the_payload_identity(self):
        artifact, payload_json, response = _published()
        assert artifact["generated_at"] == GEN
        assert artifact["payload_sha256"] == hashlib.sha256(payload_json.encode()).hexdigest()
        assert artifact["population_predicate_fingerprint"] == response["population_predicate_fingerprint"]
        assert artifact["members_total"] == 7
        assert artifact["methodology"]["bucket_rule"] == cem.BUCKET_RULE

    def test_a_payload_whose_datagolf_buckets_disagree_publishes_nothing(self):
        verified, _ = cem.verify_cells_against_fold(CELLS, _fold_rows())
        response = _response()
        for b in response["buckets"]:
            if b["source"] == "datagolf" and b["bucket_idx"] == 2:
                b["n"] += 1
        assert cem.build_published_membership(
            verified, response=response, payload_sha256="a" * 64, staged_unit_fingerprint=None,
        ) == (None, cem.REASON_PAYLOAD_MISMATCH)

    def test_a_payload_without_identity_publishes_nothing(self):
        verified, _ = cem.verify_cells_against_fold(CELLS, _fold_rows())
        response = {**_response(), "generated_at": None}
        assert cem.build_published_membership(
            verified, response=response, payload_sha256="a" * 64, staged_unit_fingerprint=None,
        ) == (None, cem.REASON_IDENTITY_MISSING)

    def test_over_the_byte_bound_publishes_nothing(self, monkeypatch):
        verified, _ = cem.verify_cells_against_fold(CELLS, _fold_rows())
        monkeypatch.setattr(cem, "MAX_MEMBER_BYTES", 10)
        assert cem.build_published_membership(
            verified, response=_response(), payload_sha256="a" * 64, staged_unit_fingerprint=None,
        ) == (None, cem.REASON_TOO_LARGE)


class TestThePublisher:
    def _runner(self, verified):
        return SimpleNamespace(
            examples_membership=verified,
            examples_membership_reason="complete" if verified is not None else "membership_absent",
            examples_membership_bank={"units": 3},
        )

    async def test_nothing_staged_publishes_nothing(self, monkeypatch):
        from app.tasks import precompute_calibration as pc

        out = await pc._publish_examples_membership(self._runner(None), _response(), "{}")
        assert out == {"status": "not_published", "reason": "membership_absent"}

    async def test_a_verified_membership_publishes_under_the_payloads_generation(self, monkeypatch):
        import app.services.durable_snapshots as ds
        from app.tasks import precompute_calibration as pc

        seen = []

        async def fake_publish(envelope):
            seen.append(envelope)
            return {"status": "ok"}

        monkeypatch.setattr(ds, "publish_snapshot_standalone", fake_publish)
        verified, _ = cem.verify_cells_against_fold(CELLS, _fold_rows())
        response = _response()
        payload_json = json.dumps(response)
        out = await pc._publish_examples_membership(self._runner(verified), response, payload_json)
        assert out["status"] == "published" and out["members"] == 7
        (env,) = seen
        main = DurableEnvelope.build(identity="calibration:main", schema_version="q271", payload=response,
                                     generated_at=datetime.fromisoformat(GEN), source="x")
        assert env.identity == cem.DURABLE_IDENTITY
        assert env.generation == main.generation, "membership and payload must share a generation"
        assert env.payload["payload_sha256"] == hashlib.sha256(payload_json.encode()).hexdigest()

    async def test_a_failed_write_is_reported_and_never_raised(self, monkeypatch):
        import app.services.durable_snapshots as ds
        from app.tasks import precompute_calibration as pc

        async def boom(envelope):
            raise OSError("db down")

        monkeypatch.setattr(ds, "publish_snapshot_standalone", boom)
        verified, _ = cem.verify_cells_against_fold(CELLS, _fold_rows())
        out = await pc._publish_examples_membership(self._runner(verified), _response(), "{}")
        assert out == {"status": "error", "reason": "OSError"}

    async def test_a_payload_mismatch_is_not_published(self, monkeypatch):
        from app.tasks import precompute_calibration as pc

        verified, _ = cem.verify_cells_against_fold(CELLS, _fold_rows())
        response = _response([r for r in _fold_rows() if r.bucket_idx != 2])
        out = await pc._publish_examples_membership(self._runner(verified), response, "{}")
        assert out == {"status": "not_published", "reason": cem.REASON_PAYLOAD_MISMATCH}


# ---------------------------------------------------------------------------
# Reader: parsing and matching
# ---------------------------------------------------------------------------
class TestParseAndMatch:
    def test_a_published_artifact_parses(self):
        artifact, _, _ = _published()
        m, reason = cem.parse_published_membership(json.loads(json.dumps(artifact)))
        assert reason == cem.COMPLETE and m.members_total == 7 and m.generated_at == GEN

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda a: a["cells"][0].update(n=a["cells"][0]["n"] + 1),
            lambda a: a["cells"][0].update(winners=a["cells"][0]["winners"] + 1),
            lambda a: a["cells"][0].update(members=a["cells"][0]["members"] + ";99,9901,0.25,0"),
            lambda a: a.update(members_total=a["members_total"] + 1),
            lambda a: a.update(schema="calibration-examples-membership/v0"),
            lambda a: a.update(source="kalshi"),
            lambda a: a.update(payload_sha256="short"),
            lambda a: a["cells"].append(dict(a["cells"][0])),
        ],
    )
    def test_a_tampered_or_foreign_artifact_is_refused(self, mutate):
        artifact, _, _ = _published()
        artifact = json.loads(json.dumps(artifact))
        mutate(artifact)
        m, reason = cem.parse_published_membership(artifact)
        assert m is None and reason != cem.COMPLETE

    def test_byte_identity_is_the_strong_proof(self):
        artifact, payload_json, _ = _published()
        m, _ = cem.parse_published_membership(artifact)
        sha = hashlib.sha256(payload_json.encode()).hexdigest()
        assert cem.membership_matches_served(m, served_sha256=sha) == (True, cem.COMPLETE)
        assert cem.membership_matches_served(m, served_sha256="b" * 64) == (
            False, cem.REASON_GENERATION_MISMATCH,
        )

    def test_the_durable_copy_matches_on_fields_and_counts(self):
        artifact, _, response = _published()
        m, _ = cem.parse_published_membership(artifact)
        assert cem.membership_matches_served(m, served_payload=response) == (True, cem.COMPLETE)
        older = {**response, "generated_at": "2026-10-19T00:00:00+00:00"}
        assert cem.membership_matches_served(m, served_payload=older)[1] == cem.REASON_GENERATION_MISMATCH
        changed = json.loads(json.dumps(response))
        changed["buckets"][0]["n"] += 1
        assert cem.membership_matches_served(m, served_payload=changed)[1] == cem.REASON_PAYLOAD_MISMATCH

    def test_the_readers_own_curve_must_match_too(self):
        artifact, payload_json, _ = _published()
        m, _ = cem.parse_published_membership(artifact)
        sha = hashlib.sha256(payload_json.encode()).hexdigest()
        assert cem.membership_matches_served(m, served_sha256=sha, reader_generation=GEN)[0]
        assert cem.membership_matches_served(
            m, served_sha256=sha, reader_generation="2026-10-19T00:00:00+00:00"
        ) == (False, cem.REASON_READER_GENERATION_MISMATCH)

    def test_unreadable_served_state_never_matches(self):
        artifact, _, _ = _published()
        m, _ = cem.parse_published_membership(artifact)
        assert cem.membership_matches_served(m) == (False, cem.REASON_SERVED_UNREADABLE)


class TestSelectMembers:
    def test_the_whole_bucket_across_categories(self):
        artifact, _, _ = _published()
        m, _ = cem.parse_published_membership(artifact)
        moved = cem.select_members(m, bucket=6, moved_only=True)
        assert sorted(r.split(",")[1] for r in moved) == ["1101", "1102", "1201", "1301"]
        every = cem.select_members(m, bucket=6, moved_only=False)
        assert sorted(r.split(",")[1] for r in every) == ["1101", "1102", "1103", "1201", "1301"]

    def test_a_bucket_with_no_eligible_rows_is_empty(self):
        artifact, _, _ = _published()
        m, _ = cem.parse_published_membership(artifact)
        for bucket in (0, 1, 3, 4, 5, 7, 8, 9):
            for moved in (True, False):
                assert cem.select_members(m, bucket=bucket, moved_only=moved) == []

    def test_every_bucket_and_arm_partitions_the_membership(self):
        artifact, _, _ = _published()
        m, _ = cem.parse_published_membership(artifact)
        allrows = [r for b in range(10) for r in cem.select_members(m, bucket=b, moved_only=False)]
        assert len(allrows) == len(set(allrows)) == m.members_total

    def test_a_record_keeps_its_exact_price(self):
        member = cem.parse_record("13,1301,0.6000000000000000001,0")
        assert member.price == Decimal("0.6000000000000000001") and member.winner is False


# ---------------------------------------------------------------------------
# Reader: the route
# ---------------------------------------------------------------------------
class _Redis:
    def __init__(self, values):
        self.values = values
        self.gets = []

    async def get(self, key):
        self.gets.append(key)
        return self.values.get(key)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _DB:
    """The request session: records SQL, answers the hydrate lookup."""

    def __init__(self, current=None):
        self.current = current or {}
        self.statements = []
        self.rolled_back = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append((sql, params))
        if "FROM futures_outcomes fo" in sql:
            return _Rows([self.current[oid] for oid in params["outcome_ids"] if oid in self.current])
        return _Rows([])

    async def rollback(self):
        self.rolled_back += 1


def _current(oid, mid, *, won, name=None):
    return SimpleNamespace(
        outcome_id=oid, market_id=mid, outcome_name=name or f"Player {oid}",
        market_name=f"Open {mid}", current_winner=won,
        settle_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


CURRENT = {
    1101: _current(1101, 11, won=True), 1102: _current(1102, 11, won=False),
    1103: _current(1103, 11, won=False), 1201: _current(1201, 12, won=True),
    1301: _current(1301, 13, won=False), 1202: _current(1202, 12, won=False),
    1203: _current(1203, 12, won=False),
}


@pytest.fixture
def world(monkeypatch):
    """Redis holds the published payload's bytes; durable holds the membership."""
    import app.services.durable_snapshots as ds
    import app.utils.request_cache as rcache

    artifact, payload_json, response = _published()
    state = {
        "redis": _Redis({"bainluck:calibration:main": payload_json.encode()}),
        "membership": artifact,
        "main_durable": response,
        "reads": [],
        "live_calls": 0,
    }

    async def fake_redis():
        return state["redis"]

    async def fake_read_snapshot(db, identity, **kw):
        state["reads"].append(identity)
        payload = state["membership"] if identity == cem.DURABLE_IDENTITY else state["main_durable"]
        if payload is None:
            return EnvelopeRead(status="missing", tier="durable")
        env = DurableEnvelope.build(identity=identity, schema_version="x", payload=payload,
                                    generated_at=datetime.fromisoformat(GEN), source="t")
        return EnvelopeRead(status="ok", tier="durable", envelope=env)

    monkeypatch.setattr(rcache, "get_shared_async_redis", fake_redis)
    monkeypatch.setattr(ds, "read_snapshot", fake_read_snapshot)
    cal._membership_cache.update(key=None, membership=None, reason=None, at=0.0)
    cal._examples_cache.clear()

    class _NoLive:
        """The live scoped path: counted, never run for real here."""

    def fake_owned(db):
        state["live_calls"] += 1
        raise AssertionError("the live path ran")

    monkeypatch.setattr(cal, "_owned_examples_session", fake_owned)
    yield state
    cal._membership_cache.update(key=None, membership=None, reason=None, at=0.0)
    cal._examples_cache.clear()


async def _click(db, *, bucket=6, wt=1, limit=10, generation=None):
    return await cal.calibration_examples(
        db=db, source="datagolf", bucket=bucket, well_traded=wt, limit=limit,
        generation=generation,
    )


def _no_population_sql(db):
    for sql, _ in db.statements:
        assert "virtual_market" not in sql and "deduped" not in sql, sql[:200]


class TestTheFirstClick:
    async def test_a_valid_membership_answers_without_any_population_sql(self, world):
        db = _DB(CURRENT)
        res = await _click(db)
        assert res["sampling"]["published_generation_membership"] == "verified"
        assert res["sampling"]["basis"] == "published_generation"
        assert res["sampling"]["generation"] == GEN
        assert res["sampling"]["members_in_bucket"] == 4
        _no_population_sql(db)
        hydrates = [s for s, _ in db.statements if "FROM futures_outcomes fo" in s]
        assert len(hydrates) == 1
        assert world["live_calls"] == 0
        assert {e["outcome_id"] for e in res["examples"]} == {1101, 1102, 1201, 1301}

    async def test_examples_carry_the_published_price_and_grade(self, world):
        res = await _click(_DB(CURRENT))
        by = {e["outcome_id"]: e for e in res["examples"]}
        assert by[1101]["price"] == 0.64 and by[1101]["result"] == "Yes"
        assert by[1101]["result_basis"] == "published"
        assert by[1101]["grade_changed_since_publish"] is False
        assert by[1101]["market_name"] == "Open 11"
        assert by[1301]["price"] == 0.6

    async def test_the_membership_is_read_once_per_dyno_per_publish(self, world):
        await _click(_DB(CURRENT))
        await _click(_DB(CURRENT), bucket=2)
        await _click(_DB(CURRENT), wt=0)
        assert world["reads"].count(cem.DURABLE_IDENTITY) == 1

    async def test_concurrent_first_clicks_read_it_once(self, world):
        await asyncio.gather(*[_click(_DB(CURRENT)) for _ in range(8)])
        assert world["reads"].count(cem.DURABLE_IDENTITY) == 1

    async def test_a_bucket_with_no_eligible_rows_is_verified_and_empty(self, world):
        db = _DB(CURRENT)
        res = await _click(db, bucket=8)
        assert res["examples"] == []
        assert res["sampling"]["published_generation_membership"] == "verified"
        assert res["sampling"]["members_in_bucket"] == 0
        assert db.statements == [], "nothing to hydrate, nothing read"

    async def test_the_cohort_is_respected(self, world):
        res = await _click(_DB(CURRENT), wt=0)
        assert {e["outcome_id"] for e in res["examples"]} == {1101, 1102, 1103, 1201, 1301}


class TestUniformOverTheWholeBucket:
    async def test_the_sample_is_drawn_from_every_known_member(self, world, monkeypatch):
        seen = {}
        real = cal.random.sample

        def spy(population, k):
            seen["population"] = list(population)
            seen["k"] = k
            return real(population, k)

        monkeypatch.setattr(cal.random, "sample", spy)
        await _click(_DB(CURRENT), wt=0, limit=2)
        assert sorted(r.split(",")[1] for r in seen["population"]) == [
            "1101", "1102", "1103", "1201", "1301",
        ]
        assert seen["k"] == 2

    async def test_every_member_is_reachable(self, world):
        hits = set()
        for _ in range(200):
            res = await _click(_DB(CURRENT), wt=0, limit=1)
            hits |= {e["outcome_id"] for e in res["examples"]}
            if len(hits) == 5:
                break
        assert hits == {1101, 1102, 1103, 1201, 1301}


class TestStaleAndCorrectedRecords:
    async def test_a_grade_corrected_since_publish_is_flagged_not_asserted(self, world):
        current = dict(CURRENT)
        current[1102] = _current(1102, 11, won=True)  # corrected Loss -> Win since
        res = await _click(_DB(current))
        e = {x["outcome_id"]: x for x in res["examples"]}[1102]
        assert e["result"] == "No" and e["result_basis"] == "published"
        assert e["current_result"] == "Yes"
        assert e["grade_changed_since_publish"] is True

    async def test_a_withdrawn_grade_is_flagged(self, world):
        current = dict(CURRENT)
        current[1101] = _current(1101, 11, won=None)
        e = {x["outcome_id"]: x for x in (await _click(_DB(current)))["examples"]}[1101]
        assert e["current_result"] is None and e["grade_changed_since_publish"] is True

    async def test_a_row_that_left_its_market_is_not_attributed(self, world):
        current = dict(CURRENT)
        current[1201] = _current(1201, 99, won=True, name="Someone else")
        e = {x["outcome_id"]: x for x in (await _click(_DB(current)))["examples"]}[1201]
        assert e["outcome_name"] == "—" and e["current_result"] is None


class TestEverythingElseFallsBackHonestly:
    @pytest.fixture
    def live(self, monkeypatch):
        calls = []

        async def fake_within(work, started):
            calls.append(1)
            return []

        monkeypatch.setattr(cal, "_within_examples_deadline", fake_within)
        return calls

    async def test_no_membership_published(self, world, live):
        world["membership"] = None
        res = await _click(_DB(CURRENT))
        assert live and res["sampling"]["published_generation_membership"] == "unverified"
        assert res["sampling"]["membership_status"] == cem.REASON_ABSENT

    async def test_an_absent_membership_is_not_re_read_every_click(self, world, live):
        world["membership"] = None
        for _ in range(3):
            cal._examples_cache.clear()
            await _click(_DB(CURRENT))
        assert world["reads"].count(cem.DURABLE_IDENTITY) == 1

    async def test_a_newer_payload_than_the_membership(self, world, live):
        """Publication generation mismatch: the curve moved on (or the payload
        write that followed the membership failed) — the old membership is not
        the served curve's."""
        world["redis"].values["bainluck:calibration:main"] = b'{"generated_at": "later"}'
        res = await _click(_DB(CURRENT))
        assert res["sampling"]["membership_status"] == cem.REASON_GENERATION_MISMATCH

    async def test_a_page_showing_an_older_curve(self, world, live):
        res = await _click(_DB(CURRENT), generation="2026-10-19T00:00:00+00:00")
        assert res["sampling"]["membership_status"] == cem.REASON_READER_GENERATION_MISMATCH

    async def test_a_corrupted_membership(self, world, live):
        world["membership"] = {**world["membership"], "members_total": 999}
        res = await _click(_DB(CURRENT))
        assert res["sampling"]["membership_status"] == cem.REASON_MALFORMED

    async def test_a_record_that_does_not_parse_refuses_at_use(self, world, live):
        artifact = json.loads(json.dumps(world["membership"]))
        cell = next(c for c in artifact["cells"] if c["bucket_idx"] == 2)
        cell["members"] = cell["members"].replace("0.21", "x.21")
        world["membership"] = artifact
        res = await _click(_DB(CURRENT), bucket=2)
        assert res["sampling"]["membership_status"] == "malformed_record"

    async def test_nothing_readable_is_served_unreadable(self, world, live):
        world["redis"].values.clear()
        world["main_durable"] = None
        res = await _click(_DB(CURRENT))
        assert res["sampling"]["membership_status"] == cem.REASON_SERVED_UNREADABLE

    async def test_an_unexpected_failure_falls_back_and_ends_the_transaction(self, world, live, monkeypatch):
        async def boom(*a, **k):
            raise RuntimeError("x")

        monkeypatch.setattr(cal, "_load_published_membership", boom)
        db = _DB(CURRENT)
        res = await _click(db)
        assert res["sampling"]["membership_status"] == "membership_error"
        assert db.rolled_back >= 1


class TestTheDurableTier:
    async def test_with_redis_empty_the_durable_copy_is_compared(self, world):
        world["redis"].values.clear()
        res = await _click(_DB(CURRENT))
        assert res["sampling"]["published_generation_membership"] == "verified"

    async def test_a_durable_copy_from_another_generation_falls_back(self, world, monkeypatch):
        async def fake_within(work, started):
            return []

        monkeypatch.setattr(cal, "_within_examples_deadline", fake_within)
        world["redis"].values.clear()
        world["main_durable"] = {**world["main_durable"], "generated_at": "older"}
        res = await _click(_DB(CURRENT))
        assert res["sampling"]["membership_status"] == cem.REASON_GENERATION_MISMATCH


class TestTheBudget:
    async def test_a_hydrate_over_budget_is_a_503(self, world):
        class QueryCanceled(Exception):
            sqlstate = "57014"

        class _SlowDB(_DB):
            async def execute(self, stmt, params=None):
                if "FROM futures_outcomes fo" in str(stmt):
                    raise QueryCanceled("canceling statement due to statement timeout")
                return await super().execute(stmt, params)

        res = await _click(_SlowDB(CURRENT))
        assert res.status_code == 503
        assert json.loads(res.body)["reason"] == "examples_query_timeout"

    async def test_the_hydrate_is_armed_from_the_one_request_budget(self, world):
        db = _DB(CURRENT)
        await _click(db)
        armed = [s for s, _ in db.statements if s.startswith("SET LOCAL statement_timeout")]
        assert len(armed) == 1
        assert 0 < int(armed[0].split("=")[1]) <= int(cal._EXAMPLES_SCOPED_STATEMENT_WALL_S * 1000)


# ---------------------------------------------------------------------------
# The beat: membership first, and never in the payload's way
# ---------------------------------------------------------------------------
from tests.test_calibration_publish_first_994 import (  # noqa: E402
    _FakeRunner,
    _Recorder,
    orchestrator,  # noqa: F401 — the real _run_calibration_main_build over stubbed I/O
)


@pytest.fixture
def beat(orchestrator, monkeypatch):  # noqa: F811
    import app.services.durable_snapshots as ds
    import app.utils.durable_state as dstate

    pc, _sessions = orchestrator
    published: list[str] = []
    state = {"fail_membership": False}

    class _Env(SimpleNamespace):
        pass

    def build(**kw):
        return _Env(identity=kw["identity"], payload=kw["payload"], generation=7)

    async def publish(envelope):
        if envelope.identity == cem.DURABLE_IDENTITY and state["fail_membership"]:
            raise OSError("membership write refused")
        published.append(envelope.identity)
        return {"status": "ok"}

    monkeypatch.setattr(dstate, "DurableEnvelope", SimpleNamespace(build=build))
    monkeypatch.setattr(ds, "publish_snapshot_standalone", publish)
    verified, _ = cem.verify_cells_against_fold(CELLS, _fold_rows())

    async def compute(db, runner=None):
        runner.examples_membership = verified
        runner.examples_membership_reason = "complete"
        runner.examples_membership_bank = {"units": 3}
        return {**_response(), "total_outcomes": 16}

    monkeypatch.setattr(pc, "compute_calibration_payload", compute)
    monkeypatch.setattr(pc, "_run_staged_futures", _Recorder())

    def runner():
        r = _FakeRunner(window_ms=10_000_000)
        r.begin = lambda phase: None
        r.complete = lambda phase, committed=True: 0
        return r

    return pc, published, state, runner


class TestTheBeat:
    async def test_the_membership_lands_before_the_payload_it_belongs_to(self, beat):
        pc, published, _state, runner = beat
        r = runner()
        summary = await pc._run_calibration_main_build(r)
        assert summary["status"] == "ok"
        assert published == [cem.DURABLE_IDENTITY, "calibration:main"]
        assert r.outcome["examples_membership"]["status"] == "published"
        assert r.outcome["published"] is True

    async def test_a_failed_membership_write_never_stops_the_curve(self, beat):
        pc, published, state, runner = beat
        state["fail_membership"] = True
        r = runner()
        summary = await pc._run_calibration_main_build(r)
        assert summary["status"] == "ok"
        assert published == ["calibration:main"]
        assert r.outcome["published"] is True
        assert r.outcome["examples_membership"] == {"status": "error", "reason": "OSError"}

    async def test_a_beat_with_no_staged_membership_publishes_only_the_curve(self, beat, monkeypatch):
        pc, published, _state, runner = beat

        async def compute(db, runner=None):
            return {**_response(), "total_outcomes": 16}

        monkeypatch.setattr(pc, "compute_calibration_payload", compute)
        r = runner()
        await pc._run_calibration_main_build(r)
        assert published == ["calibration:main"]
        assert r.outcome["examples_membership"]["status"] == "not_published"

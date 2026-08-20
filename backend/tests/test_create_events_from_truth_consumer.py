"""#1796/#1902 queue 369 — the attended CREATE consumer, driven through the LIVE rail.

WHY THIS FILE EXISTS

Three windows built the CREATE plan object — queue 363 the shape, 364 the address
scheme, 368 the ``sport_id`` binding — and two populations sat GREEN and approved
against an apply path that **did not exist on any branch**. Every
``decode_create_plan`` call site in the tree was the definition module, the deriver
script, or a test. So the certification could not certify an apply; there was
nothing to point it at, and every prior "shipped" claim about a create consumer was
the claim-not-execution class.

Every test below therefore calls ``repair()`` — the function the dispatcher
actually invokes — and never a local re-statement of what it is supposed to do. A
test that models the rail proves the model. The certification's own specimen on the
sibling rail (#1798) is the precedent: reviewed set ``[(1001, away)]``, a candidate
that appeared after review, and the deployed function wrote BOTH while reporting a
perfectly true after-census of zero defects.

THE FIVE REFUSALS, EACH BY NAME

    no plan artifact            -> PLAN_ARTIFACT_MISSING
    an edited/truncated one     -> PLAN_ARTIFACT_CORRUPT
    the store could not be read -> PLAN_ARTIFACT_UNREADABLE
    no hash, or a stale hash    -> PLAN_HASH_MISMATCH
    an id created since review  -> TRUTH_ID_ALREADY_PRESENT   (per-row, not per-run)

MISSING vs UNREADABLE vs CORRUPT are three tests and not one on purpose (gotcha
#53, C-APPLY-PRE-R2 finding 1): MISSING tells an operator to go generate a plan,
which during a store outage is the one action that destroys the evidence.
"""

import json
from datetime import datetime, timezone

import pytest

from app.tasks import create_events_from_truth as rail
from app.tasks.create_events_from_truth import repair
from app.utils import durable_state as ds
from app.utils.repair_apply_plan import (
    CREATE_PLAN_SCHEMA,
    REASON_OUTSIDE_APPROVED,
    REASON_PLAN_CORRUPT,
    REASON_PLAN_HASH_MISMATCH,
    REASON_PLAN_MISSING,
    REASON_PLAN_UNREADABLE,
    REASON_TRUTH_ID_PRESENT,
    PlannedCreate,
    build_create_plan,
)

MLB = 53232
PRESEASON = 33178


# ── doubles ────────────────────────────────────────────────────────────────


class _Result:
    def __init__(self, rows=(), rowcount=0, as_mappings=False):
        self._rows = list(rows)
        self.rowcount = rowcount
        self._as_mappings = as_mappings

    def mappings(self):
        return _Result(self._rows, self.rowcount, as_mappings=True)

    def all(self):
        return self._rows


class _Session:
    """Answers the rail's five SQL shapes over an in-memory ``events`` table.

    The INSERT is modelled HONESTLY: its ``WHERE NOT EXISTS`` is evaluated here,
    so a row whose provider id is already present affects ZERO rows exactly as
    Postgres would. A double that always returned rowcount 1 would make the
    TRUTH_ID_ALREADY_PRESENT refusal untestable and it would ship dead — which is
    precisely how the sibling rail's drift refusal could have shipped dead.
    """

    def __init__(self, events=(), teams=(), *, appears_before_insert=()):
        # events: list of dicts with espn_id / id / …
        self.events = [dict(e) for e in events]
        self.teams = list(teams)  # (name, id) rows already scoped to a sport
        self.inserted = []
        self.locks = []
        self.commits = 0
        self.rollbacks = 0
        self._next_id = 90000
        # Provider ids that the ORDINARY PIPELINE creates in the instant between the
        # gate's read and this row's INSERT. This is the race the in-statement
        # existence check exists for, and it cannot be exercised any other way.
        self._appears = set(appears_before_insert)

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        params = params or {}
        if "FROM teams" in sql:
            wanted = set(params["names"])
            return _Result([(n, i) for (n, i) in self.teams if n in wanted])
        if "SELECT DISTINCT espn_id" in sql:
            ids = set(params["ids"])
            return _Result([(e["espn_id"],) for e in self.events if e["espn_id"] in ids])
        if "pg_advisory_xact_lock" in sql:
            self.locks.append((params["ns"], params["key"]))
            return _Result()
        if "INSERT INTO events" in sql:
            tid = params["truth_id"]
            # HONOUR THE STATEMENT, do not model the fix. The guard below only
            # applies if the SQL actually asks for it — a double that enforced
            # uniqueness unconditionally would keep passing after someone deleted
            # the `WHERE NOT EXISTS`, which is the whole property under test.
            guarded = "WHERE NOT EXISTS" in sql
            if tid in self._appears:
                # The pipeline got there first, after the gate read.
                self.events.append({"espn_id": tid, "id": self._new_id(), "pipeline": True,
                                    "sport_id": MLB, "home_team_id": 1, "away_team_id": 2,
                                    "home_team_name": "?", "away_team_name": "?",
                                    "commence_time": "?", "status": "scheduled"})
                self._appears.discard(tid)
            if guarded and any(e["espn_id"] == tid for e in self.events):
                return _Result(rowcount=0)
            row = {
                "espn_id": tid,
                "id": self._new_id(),
                "sport_id": params["sport_id"],
                "home_team_id": params["home_team_id"],
                "away_team_id": params["away_team_id"],
                "home_team_name": params["home_name"],
                "away_team_name": params["away_name"],
                "commence_time": params["commence_time"],
                "status": "scheduled",
            }
            self.events.append(row)
            self.inserted.append(dict(row))
            return _Result(rowcount=1)
        if "FROM events" in sql and "ORDER BY espn_id" in sql:
            ids = set(params["ids"])
            return _Result([e for e in self.events if e["espn_id"] in ids], as_mappings=True)
        raise AssertionError(f"unexpected SQL in double: {sql[:120]}")

    def _new_id(self):
        self._next_id += 1
        return self._next_id

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _planned(truth_id, home_id=101, away_id=202, *, sport_id=MLB, commence="2026-08-19T23:05:00+00:00"):
    return PlannedCreate(
        truth_id=truth_id,
        provider="espn",
        home_team_id=home_id,
        away_team_id=away_id,
        home_name="Pittsburgh Pirates",
        away_name="Boston Red Sox",
        commence_time=commence,
        sport_id=sport_id,
        label=f"Boston Red Sox @ Pittsburgh Pirates {commence[:10]} 23:05Z",
    )


class _Read:
    def __init__(self, payload=None, *, ok=True, status="ok", error_class=None):
        self.ok = ok
        self.status = status
        self.error_class = error_class
        self.envelope = None if payload is None else type("E", (), {"payload": payload})()


def _stage(monkeypatch, read):
    """Make the durable store answer with ``read`` for the apply's plan load."""
    import app.services.durable_snapshots as snaps

    async def _fake_read(identity, expected_version=None, max_age_s=None):
        return read

    monkeypatch.setattr(snaps, "read_snapshot_standalone", _fake_read, raising=False)


def _no_feed_cache(monkeypatch, status="ok"):
    import app.utils.feed_cache as fc

    async def _fake(reason):
        return {"status": status, "deleted": 3, "reason": reason}

    monkeypatch.setattr(fc, "invalidate_feed_response_cache", _fake, raising=False)


# ── the specimen: a row created between review and apply ───────────────────


@pytest.mark.asyncio
async def test_an_id_created_after_review_retires_that_row_and_no_other(monkeypatch):
    """The create-direction twin of C-APPLY-PRE's specimen.

    A reviewed id that the ordinary pipeline created between the review and the
    apply is NOT an error in the world — it is the system working. It must:
      * not be created a second time,
      * be named with its own reason code rather than counted as a success,
      * and NOT cancel its approved siblings.

    One upstream create cancelling 327 approved ones is the failure this asserts
    against; so is silently treating it as applied.
    """
    plan = build_create_plan([_planned("A1"), _planned("A2"), _planned("A3")])
    _stage(monkeypatch, _Read(plan.as_payload()))
    _no_feed_cache(monkeypatch)

    session = _Session(events=[{"espn_id": "A2", "id": 5, "sport_id": MLB,
                                "home_team_id": 1, "away_team_id": 2,
                                "home_team_name": "x", "away_team_name": "y",
                                "commence_time": "t", "status": "scheduled"}])

    out = await repair(session, apply=True, plan_hash=plan.plan_hash, population="2")

    assert out["applied"] is True
    assert out["census"]["created"] == 2
    assert sorted(e["truth_id"] for e in out["ledger"]) == ["A1", "A3"]
    # Named by the gate, not silently dropped.
    assert out["gate"]["no_longer_missing"] == ["A2"]
    assert out["gate"]["retired_by_gate"] == 1
    assert out["gate"]["passes"] is False
    # And the row that already existed was never written again.
    assert [r["espn_id"] for r in session.inserted] == ["A1", "A3"]

    # A2 must be retired BY THE GATE, not discovered by the insert's collision
    # guard. Both stop the write, so a rail that skipped the gate would still be
    # safe — and would report a routine pipeline create as a concurrency race. Two
    # different facts about the world must not arrive as one number: "the plan
    # shrank between review and apply, as expected" is not "something raced us".
    assert out["census"]["already_present"] == 0
    assert out["skipped"] == []
    assert out["census"]["actionable_this_call"] == 2


@pytest.mark.asyncio
async def test_a_row_that_appears_between_the_gate_and_the_insert_is_caught_by_the_insert(monkeypatch):
    """The reason the existence check is INSIDE the statement, not in front of it.

    Here the gate reads a world where ``B2`` is missing, and the pipeline creates
    it before this rail's own INSERT lands. A check performed before the statement
    would have licensed a duplicate. The ``WHERE NOT EXISTS`` catches it, rowcount
    is 0, and the row is reported as TRUTH_ID_ALREADY_PRESENT rather than created.
    """
    plan = build_create_plan([_planned("B1"), _planned("B2")])
    _stage(monkeypatch, _Read(plan.as_payload()))
    _no_feed_cache(monkeypatch)

    session = _Session(appears_before_insert={"B2"})
    out = await repair(session, apply=True, plan_hash=plan.plan_hash, population="2")

    assert out["census"]["created"] == 1
    assert out["census"]["already_present"] == 1
    skipped = out["skipped"]
    assert [s["truth_id"] for s in skipped] == ["B2"]
    assert skipped[0]["reason_code"] == REASON_TRUTH_ID_PRESENT
    # The gate could not have known: it saw B2 as missing.
    assert out["gate"]["no_longer_missing"] == []


def test_the_existence_check_lives_inside_the_insert_statement():
    """Structural: the compare half must be part of the write, not a prior read.

    Asserted on the SQL text because this is the one property the whole rail is
    built around, and a future edit that splits the check back out would still
    pass every behavioural test above on a quiet database.
    """
    sql = " ".join(str(rail._INSERT_SQL).split())
    assert "INSERT INTO events" in sql
    assert "WHERE NOT EXISTS" in sql
    assert "FROM events" in sql and "espn_id = CAST(:truth_id AS varchar)" in sql
    # `:param::cast` silently drops the bind under asyncpg's text() parser.
    assert "::" not in sql


def test_every_repeated_bind_param_is_cast_at_every_occurrence():
    """A bind param used in TWO positions must be pinned in BOTH.

    THE FAILURE THIS EXISTS FOR, measured in production on 2026-08-19 (queue 376):
    ``:truth_id`` appeared bare in the SELECT list and again compared against
    ``events.espn_id``. asyncpg deduces ``text`` from the first and
    ``character varying`` from the second and refuses the whole statement with
    ``AmbiguousParameterError: inconsistent types deduced for parameter $2``.

    Every gate upstream was GREEN — the plan re-derived to an identical
    ``plan_hash``, ``still_missing`` was 328, ``already_present`` 0, the set gate
    passed — and ``apply=true`` then died without writing a row. So no behavioural
    test on a mocked session could have caught it: the mock never type-checks a
    bind. It is asserted on the SQL TEXT for the same reason the compare-half
    assertion above is.

    This is deliberately a rule about SHAPE, not a spelling check for
    ``:truth_id``. A param used ONCE is inferred from its single context and needs
    no help; casting one side of a two-context param only relocates the
    disagreement.
    """
    import re

    sql = " ".join(str(rail._INSERT_SQL).split())
    params = set(re.findall(r"(?<!:):([a-zA-Z_]\w*)", sql))
    repeated = {p for p in params if len(re.findall(r"(?<!:):%s\b" % p, sql)) > 1}
    assert repeated, "expected at least one repeated bind param — the compare half reuses one"
    for prm in sorted(repeated):
        occurrences = len(re.findall(r"(?<!:):%s\b" % prm, sql))
        casts = len(re.findall(r"CAST\(\s*:%s\b" % prm, sql, re.I))
        assert casts == occurrences, (
            f":{prm} appears {occurrences}x but is CAST {casts}x. asyncpg deduces a "
            f"type per position and refuses the statement when they disagree "
            f"(AmbiguousParameterError). Wrap EVERY occurrence in CAST(... AS <type>)."
        )


# ── the four read/bind refusals, each distinct ─────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "read,expected",
    [
        (_Read(None, ok=False, status=ds.MISSING), REASON_PLAN_MISSING),
        (_Read(None, ok=False, status=ds.MALFORMED, error_class="ChecksumMismatch"), REASON_PLAN_CORRUPT),
        (_Read(None, ok=False, status=ds.WRONG_VERSION), REASON_PLAN_CORRUPT),
        (_Read(None, ok=False, status=ds.UNAVAILABLE), REASON_PLAN_UNREADABLE),
        (_Read(None, ok=False, status=ds.STALE), REASON_PLAN_UNREADABLE),
    ],
)
async def test_each_unreadable_state_refuses_by_its_own_name(monkeypatch, read, expected):
    """CORRUPT is not MISSING and UNREADABLE is not either.

    Telling an operator MISSING during a store outage sends them to regenerate the
    plan — the one action that destroys the evidence. All three refuse the apply;
    only the sentence differs, and the sentence is the whole value.
    """
    _stage(monkeypatch, read)
    session = _Session()
    out = await repair(session, apply=True, plan_hash="whatever", population="2")

    assert out["applied"] is False and out["refused"] is True
    assert out["reason_codes"] == [expected]
    assert session.inserted == []


@pytest.mark.asyncio
async def test_a_tampered_artifact_refuses_as_corrupt_not_as_missing(monkeypatch):
    """An artifact whose content no longer digests to its stored address."""
    plan = build_create_plan([_planned("C1")])
    payload = plan.as_payload()
    payload["rows"][0]["sport_id"] = PRESEASON  # the queue-368 hole, now inside the address
    _stage(monkeypatch, _Read(payload))

    out = await repair(_Session(), apply=True, plan_hash=plan.plan_hash, population="2")
    assert out["reason_codes"] == [REASON_PLAN_CORRUPT]


@pytest.mark.asyncio
@pytest.mark.parametrize("presented", [None, "", "0" * 32])
async def test_apply_without_the_reviewed_hash_is_refused(monkeypatch, presented):
    """An apply that cannot name the plan it read is not an attended apply."""
    plan = build_create_plan([_planned("D1")])
    _stage(monkeypatch, _Read(plan.as_payload()))

    session = _Session()
    out = await repair(session, apply=True, plan_hash=presented, population="2")
    assert out["reason_codes"] == [REASON_PLAN_HASH_MISMATCH]
    assert session.inserted == []


# ── plan-boundedness, keying, and the registry binding ─────────────────────


@pytest.mark.asyncio
async def test_the_apply_writes_the_plans_sport_id_and_club_ids_verbatim(monkeypatch):
    """The reviewed row is the written row — including WHICH registry it binds to.

    MLB carries two team registries with all 30 clubs duplicated (#1798), so
    ``sport_id`` decides which copy of the club a created game hangs off. It is
    inside the address (queue 368) and it must also be inside the WRITE.
    """
    plan = build_create_plan([_planned("E1", home_id=777, away_id=888, sport_id=MLB)])
    _stage(monkeypatch, _Read(plan.as_payload()))
    _no_feed_cache(monkeypatch)

    session = _Session()
    out = await repair(session, apply=True, plan_hash=plan.plan_hash, population="2")

    assert out["census"]["created"] == 1
    written = session.inserted[0]
    assert written["sport_id"] == MLB and written["sport_id"] != PRESEASON
    assert (written["home_team_id"], written["away_team_id"]) == (777, 888)
    assert written["status"] == "scheduled"
    # Correction, never invention: no scores, no lines, no derived fields.
    assert "home_score" not in written and "away_score" not in written


@pytest.mark.asyncio
async def test_a_doubleheader_is_two_rows_because_the_key_is_the_provider_id(monkeypatch):
    """Same clubs, same date, two real games. Keying on the matchup loses one.

    The 328-row population contains twin bills, and R5 hit this blind spot once
    already on the merge primitive. The row key here is ``espn:<id>`` throughout,
    so both halves are created.
    """
    a = _planned("F1", commence="2026-07-19T00:08:00+00:00")
    b = _planned("F2", commence="2026-07-19T23:20:00+00:00")
    plan = build_create_plan([a, b])
    _stage(monkeypatch, _Read(plan.as_payload()))
    _no_feed_cache(monkeypatch)

    session = _Session()
    out = await repair(session, apply=True, plan_hash=plan.plan_hash, population="2")

    assert out["census"]["created"] == 2
    assert sorted(r["espn_id"] for r in session.inserted) == ["F1", "F2"]
    # Reported to the reviewer, never treated as a defect.
    assert set(plan.doubleheaders()) == {"F1", "F2"}


@pytest.mark.asyncio
async def test_an_event_outside_the_plan_is_never_touched(monkeypatch):
    """The apply iterates the plan and nothing else."""
    plan = build_create_plan([_planned("G1")])
    _stage(monkeypatch, _Read(plan.as_payload()))
    _no_feed_cache(monkeypatch)

    session = _Session(events=[{"espn_id": "STRANGER", "id": 1, "sport_id": MLB,
                                "home_team_id": 1, "away_team_id": 2,
                                "home_team_name": "a", "away_team_name": "b",
                                "commence_time": "t", "status": "scheduled"}])
    out = await repair(session, apply=True, plan_hash=plan.plan_hash, population="2")

    assert [r["espn_id"] for r in session.inserted] == ["G1"]
    assert "STRANGER" not in json.dumps(out)
    # The verification reads the plan's own ids, not the population.
    assert out["verified_plan_truth_ids"]["present"] == 1


def test_the_apply_path_does_not_call_the_derivation():
    """A work list recomputable at apply time is a work list that can differ.

    Structural, because it is the property the whole pattern rests on and it is
    invisible to any behavioural test that happens to run on a quiet database.
    """
    import inspect

    src = inspect.getsource(rail._apply_reviewed_plan)
    for forbidden in ("build_rows(", "select_population(", "required_club_names(", "_RESOLVE_CLUBS_SQL"):
        assert forbidden not in src, f"the apply path re-derives via {forbidden}"


def test_the_dry_run_cannot_create_a_row():
    """`apply=false` must have no path to a write."""
    import inspect

    src = inspect.getsource(rail.repair)
    assert "_INSERT_SQL" not in src


# ── cap, resumability, and the invalidation obligation ─────────────────────


@pytest.mark.asyncio
async def test_the_cap_stops_the_run_and_says_so_rather_than_claiming_exhaustion(monkeypatch):
    """A partial page is a normal outcome; it must not read as 'nothing left'.

    Gotcha #53's shape: a run that did less than it could must be distinguishable
    from a run with nothing to do. Resumption needs no cursor — the gate drops the
    ids now present, so the SAME plan_hash continues.
    """
    monkeypatch.setattr(rail, "APPLY_CREATE_CAP", 2)
    rows = [_planned(f"H{i}") for i in range(5)]
    plan = build_create_plan(rows)
    _stage(monkeypatch, _Read(plan.as_payload()))
    _no_feed_cache(monkeypatch)

    session = _Session()
    first = await repair(session, apply=True, plan_hash=plan.plan_hash, population="2")
    assert first["census"]["created"] == 2
    assert first["stopped_on_cap"] is True
    assert first["exhausted"] is False
    assert first["census"]["remaining"] == 3

    second = await repair(session, apply=True, plan_hash=plan.plan_hash, population="2")
    assert second["census"]["created"] == 2
    assert second["census"]["remaining"] == 1

    third = await repair(session, apply=True, plan_hash=plan.plan_hash, population="2")
    assert third["census"]["created"] == 1
    assert third["exhausted"] is True
    assert third["stopped_on_cap"] is False
    assert sorted(r["espn_id"] for r in session.inserted) == [f"H{i}" for i in range(5)]


@pytest.mark.asyncio
async def test_a_failed_feed_invalidation_is_reported_not_swallowed(monkeypatch):
    """The rows are committed; the obligation is surfaced with success=false.

    Deliberately reported rather than persisted as a debt: this cache carries a TTL
    and self-heals inside it. The point of the assertion is that a failure cannot
    arrive dressed as a clean run.
    """
    plan = build_create_plan([_planned("I1")])
    _stage(monkeypatch, _Read(plan.as_payload()))
    _no_feed_cache(monkeypatch, status="error")

    out = await repair(_Session(), apply=True, plan_hash=plan.plan_hash, population="2")
    assert out["census"]["created"] == 1
    assert out["invalidation"]["status"] == "error"
    assert out["invalidation_discharged"] is False
    assert out["success"] is False


@pytest.mark.asyncio
async def test_each_write_takes_its_own_advisory_lock(monkeypatch):
    """The non-unique index leaves a millisecond window; the lock closes it against
    this rail racing ITSELF. Keyed per provider id so one row cannot block another."""
    plan = build_create_plan([_planned("J1"), _planned("J2")])
    _stage(monkeypatch, _Read(plan.as_payload()))
    _no_feed_cache(monkeypatch)

    session = _Session()
    await repair(session, apply=True, plan_hash=plan.plan_hash, population="2")
    assert len(session.locks) == 2
    assert len({k for _, k in session.locks}) == 2
    assert {ns for ns, _ in session.locks} == {rail._ADVISORY_LOCK_NS}


# ── the dry run ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_dry_run_derives_persists_and_hands_back_an_apply_command(monkeypatch):
    """The deliverable of a dry run is a hash an operator can present back."""
    saved = {}

    async def _fake_save(plan, population):
        saved["hash"] = plan.plan_hash
        saved["population"] = population
        return True, "ok"

    monkeypatch.setattr(rail, "_save_plan", _fake_save)
    monkeypatch.setattr(
        rail, "_load_truth_set",
        lambda population="2": (
            {
                "truth_id_hash": "deadbeef",
                "gate": "every reviewed id must still be missing",
                "truth_ids": ["401816534", "401816407"],
                "games": [
                    {"espn_id": "401816534", "label": "Boston Red Sox @ Pittsburgh Pirates 2026-08-15 22:40Z",
                     "commence": "2026-08-15T22:40:00+00:00"},
                    {"espn_id": "401816407", "label": "Minnesota Twins @ Kansas City Royals 2026-08-05 00:10Z",
                     "commence": "2026-08-05T00:10:00+00:00"},
                ],
            },
            "ok",
        ),
    )

    session = _Session(teams=[
        ("Boston Red Sox", 11), ("Pittsburgh Pirates", 12),
        ("Minnesota Twins", 13), ("Kansas City Royals", 14),
    ])
    out = await repair(session, apply=False, population="2")

    assert out["apply"] is False
    assert out["plan_persisted"] is True
    assert out["plan_rows"] == 2
    assert out["schema"] == CREATE_PLAN_SCHEMA
    assert out["gate"]["passes"] is True
    assert out["plan_hash"] == saved["hash"]
    assert f"plan_hash={out['plan_hash']}" in out["apply_command"]
    assert session.inserted == []  # a dry run creates nothing


@pytest.mark.asyncio
async def test_population_1_is_a_subset_of_the_reviewed_set_and_row_one_is_asserted(monkeypatch):
    """A derivation that loses Alex's own reported-missing game must fail loudly."""
    monkeypatch.setattr(rail, "_save_plan", lambda plan, population: _ok_save(plan))
    monkeypatch.setattr(
        rail, "_load_truth_set",
        lambda population="2": (
            {
                "truth_id_hash": "x",
                "truth_ids": ["401816407"],
                "games": [
                    {"espn_id": "401816407", "label": "Minnesota Twins @ Kansas City Royals 2026-08-05 00:10Z",
                     "commence": "2026-08-05T00:10:00+00:00"},
                ],
            },
            "ok",
        ),
    )
    out = await repair(_Session(), apply=False, population="1")
    assert out["refused"] is True
    assert out["reason_codes"] == ["TRUTH_SET_ROW_ONE_ABSENT"]


async def _ok_save(plan):  # pragma: no cover — helper for the monkeypatch above
    return True, "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason", ["TRUTH_SET_MISSING", "TRUTH_SET_UNREADABLE", "TRUTH_SET_CORRUPT"],
)
async def test_the_reviewed_set_gets_the_same_three_readings_as_the_plan(monkeypatch, reason):
    """MISSING/UNREADABLE/CORRUPT again, one level up. Same argument, same split."""
    monkeypatch.setattr(rail, "_load_truth_set", lambda population="2": (None, reason))
    out = await repair(_Session(), apply=False, population="2")
    assert out["refused"] is True and out["reason_codes"] == [reason]


@pytest.mark.asyncio
async def test_a_club_without_a_unique_anchor_refuses_rather_than_guessing(monkeypatch):
    """The #1918 poisoned path is not consulted, and a 0-or-2 match is a refusal."""
    monkeypatch.setattr(
        rail, "_load_truth_set",
        lambda population="2": (
            {
                "truth_id_hash": "x",
                "truth_ids": ["401816534"],
                "games": [
                    {"espn_id": "401816534", "label": "Boston Red Sox @ Pittsburgh Pirates 2026-08-15 22:40Z",
                     "commence": "2026-08-15T22:40:00+00:00"},
                ],
            },
            "ok",
        ),
    )
    # Pirates resolves twice — the registry split, seen from inside one sport.
    session = _Session(teams=[("Boston Red Sox", 11), ("Pittsburgh Pirates", 12),
                              ("Pittsburgh Pirates", 99)])
    out = await repair(session, apply=False, population="2")
    assert out["refused"] is True
    assert out["reason_codes"] == ["CLUB_ANCHOR_NOT_UNIQUE"]
    assert "Pittsburgh Pirates" in out["ambiguous"]


@pytest.mark.asyncio
async def test_an_unknown_population_is_refused_by_name():
    out = await repair(_Session(), apply=False, population="9")
    assert out["reason_codes"] == ["UNKNOWN_POPULATION"]


def test_the_aug19_games_are_their_own_reviewed_set_not_an_extension_of_the_season_one():
    """Ruling 079's shape: a new population is a new object, not a widened constant.

    The four Aug-19 games (#1947's population 2) have no row at all and play within
    ~24h, so the temptation to append them to the 328-row set is real and is exactly
    wrong. That set's declared scope ends 2026-08-17 and its latest reviewed game
    starts 2026-08-16T01:38Z: folding them in would change an object Alex already
    reviewed, and the plan_hash he approved would silently cover four games he never
    saw. So they get their own file, their own address, and their own approval.
    """
    import json
    from pathlib import Path

    from app.utils.event_create_derivation import TRUTH_SET_REGISTRY

    data = Path(__file__).resolve().parents[1] / "app" / "data"
    season = json.loads((data / "event_create_truth_set.json").read_text())
    aug19 = json.loads((data / "event_create_truth_set_aug19.json").read_text())

    # Distinct files, and 3 is not a slice of 2.
    assert TRUTH_SET_REGISTRY["3"][0] != TRUTH_SET_REGISTRY["2"][0]
    assert set(aug19["truth_ids"]).isdisjoint(set(season["truth_ids"]))
    assert set(aug19["truth_ids"]) == {"401816586", "401816587", "401816588", "401816590"}

    # And the season set really does stop before them, so this is a measured
    # boundary rather than a stylistic preference.
    assert max(g["commence"] for g in season["games"]) < "2026-08-19"
    assert min(g["commence"] for g in aug19["games"]).startswith("2026-08-19")

    # Each reviewed set names its own sentinel row.
    assert aug19["row_one"] in set(aug19["truth_ids"])


# ── the two producers cannot drift ─────────────────────────────────────────


def test_the_deriver_script_and_the_rail_share_one_row_builder():
    """One builder, two readers.

    The plan is a content address. A second implementation that trims a label
    differently, or picks the other MLB registry, mints a DIFFERENT address from
    the SAME approval — and the operator is then holding a hash nothing accepts.
    """
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "derive_event_create_plan.py"
    src = script.read_text()
    assert "from app.utils.event_create_derivation import" in src
    assert "build_rows" in src
    # And it must not have grown a private copy back.
    assert "PlannedCreate(" not in src


def test_the_rail_is_registered_on_the_dispatcher_and_declares_population():
    """A repair nobody can invoke is a repair that does not exist."""
    import inspect

    from app.routes import admin_repairs

    assert admin_repairs._REPAIRS["event-create-from-truth"] == (
        "app.tasks.create_events_from_truth",
        "repair",
    )
    # The dispatcher passes through only what it names, so an unnamed param is
    # silently dropped and the apply would bind to the wrong population's artifact.
    dispatcher = inspect.getsource(admin_repairs.run_repair)
    assert '("population", population)' in dispatcher
    assert "population" in inspect.signature(admin_repairs.run_repair).parameters
    assert "population" in inspect.signature(rail.repair).parameters


# ── queue 379: the bind must hand asyncpg a datetime, not its ISO string ──────


def test_commence_time_is_bound_as_a_datetime_not_an_iso_string():
    """asyncpg type-checks the PYTHON argument before the server sees the CAST.

    THE FAILURE THIS EXISTS FOR, measured in production 2026-08-20T03:12Z (queue
    379). The wave fired with every gate green — #2023 deployed and ancestry
    proved, plan re-derived to an identical ``plan_hash``, ``still_missing`` 328,
    ``already_present`` 0, set gate passing — and died inside the write, nine calls
    in a row, writing ZERO rows::

        asyncpg.exceptions.DataError: invalid input for query argument $7:
        '2026-06-21T02:10:00+00:00' (expected a datetime.date or datetime.datetime
        instance, got 'str')

    ``CAST(:commence_time AS timestamptz)`` is already in the statement and does not
    help: the driver rejects the argument client-side, so a server-side cast is
    applied to a value the server never receives. This is #2013's
    ``AmbiguousParameterError`` one parameter over, and it has the SAME tell —
    ``test_the_dry_run_cannot_create_a_row`` passes precisely because the dry run
    never executes the INSERT, so no amount of dry-run greenness can reach it.

    Asserted on the BOUND VALUE rather than on the SQL text, because the SQL text
    was already correct. The type of the argument is the whole defect.
    """
    assert isinstance(
        rail._as_datetime("2026-06-21T02:10:00+00:00"), datetime
    ), "the ISO string from the plan artifact must be coerced before binding"


@pytest.mark.asyncio
async def test_the_insert_receives_a_datetime_for_commence_time(monkeypatch):
    """End-to-end at the bind: what reaches the driver is a datetime.

    The unit test above can be satisfied by a helper nobody calls. This one fails
    if the helper is not wired into the actual INSERT bind — which is the state
    production was in.
    """
    plan = build_create_plan([_planned("E1", commence="2026-06-21T02:10:00+00:00")])
    _stage(monkeypatch, _Read(plan.as_payload()))
    _no_feed_cache(monkeypatch)

    session = _Session()
    out = await repair(session, apply=True, plan_hash=plan.plan_hash, population="2")

    assert out["census"]["created"] == 1
    bound = session.inserted[0]["commence_time"]
    assert isinstance(bound, datetime), (
        f"commence_time reached the driver as {type(bound).__name__}; asyncpg "
        f"rejects a str for a timestamptz argument before the CAST is ever applied"
    )
    assert bound.tzinfo is not None, "a naive stamp would be read as the server's zone"
    assert bound == datetime(2026, 6, 21, 2, 10, tzinfo=timezone.utc)


def test_the_plan_row_keeps_commence_time_as_a_string_so_the_address_is_stable():
    """The coercion must NOT migrate onto ``PlannedCreate``.

    ``commence_time`` is a string on the plan row because it is inside the plan's
    CONTENT ADDRESS — it is how a reviewer knows which game a row is. Retyping the
    field would change every ``plan_hash`` and invalidate the artifact Alex
    approved, converting a one-line bind fix into a re-review. The string is the
    reviewed object; the datetime is an implementation detail of the driver.
    """
    row = _planned("E1", commence="2026-06-21T02:10:00+00:00")
    assert isinstance(row.commence_time, str)
    # And the address is unchanged by this queue's fix.
    assert build_create_plan([row]).plan_hash == build_create_plan([row]).plan_hash


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-06-21T02:10:00+00:00", datetime(2026, 6, 21, 2, 10, tzinfo=timezone.utc)),
        # JSON artifacts carry "Z", which `fromisoformat` refuses on older Pythons.
        ("2026-06-21T02:10:00Z", datetime(2026, 6, 21, 2, 10, tzinfo=timezone.utc)),
        # A naive stamp is UTC — the truth set is UTC, and defaulting to the
        # server's local zone would silently shift every created game.
        ("2026-06-21T02:10:00", datetime(2026, 6, 21, 2, 10, tzinfo=timezone.utc)),
    ],
)
def test_as_datetime_accepts_the_shapes_the_truth_set_actually_carries(raw, expected):
    assert rail._as_datetime(raw) == expected


def test_as_datetime_passes_through_none_and_datetimes_unchanged():
    """Idempotent: a value already correct must not be re-parsed or re-zoned."""
    already = datetime(2026, 6, 21, 2, 10, tzinfo=timezone.utc)
    assert rail._as_datetime(already) is already
    assert rail._as_datetime(None) is None

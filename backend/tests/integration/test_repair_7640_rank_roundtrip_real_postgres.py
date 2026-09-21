"""#7640's apply/restore round trip, executed against a REAL PostgreSQL.

## what this grades that nothing cheaper can

`scripts/repair_7640_stale_futures_ranks.py` rewrites `futures_outcomes.rank` on
~13,000 open markets under D51(b), which permits an unattended-by-Alex data
repair only because it "writes a backup first and ships a one-command restore".
Four of the five things that claim rests on are decided by a planner:

1. **`rank()` over the real column types.** The ordering is
   `current_probability DESC NULLS LAST` on a `Numeric(7,6)` with a genuine
   NULL in the field. Ties must SHARE a number and the next rank must skip the
   gap (1, 2, 2, 4) — `row_number()` would produce 1, 2, 3, 4 and every
   assertion built on a mock would pass either way.
2. **`IS DISTINCT FROM` making a healthy board a no-op.** The claim "a re-run is
   free and the script is resumable" is entirely this predicate. Only a server
   reports how many rows an UPDATE actually touched.
3. **RETURNING giving the POST-update rank and the UNTOUCHED `last_updated`.**
   The manifest is banked from the forward write's own RETURNING, so if
   PostgreSQL returned pre-update values the undo would bind to the wrong
   witness and spare nothing.
4. **The undo sparing a row a poller rewrote after the repair — the clause the
   whole D51(b) grant turns on.** A poller that re-derives a board arrives at
   the SAME rank this pass wrote, so `rank` alone cannot separate "nobody
   touched it" from "somebody did". `last_updated` can, and whether it can is a
   property of how PostgreSQL applies the UPDATE, not of the Python around it.

The fifth, `#6325`'s settled exemption, is here too because it is one line in
the plan's WHERE and one re-read at write time, and a repair that renumbers a
finished field is unrecoverable in the way that matters — the record of how the
board finished is gone.

There is no local PostgreSQL in the agent sandbox, so CI is where this runs. The
`search-recall` job provides the container and its skip-detection step is what
stops a silently-skipped gate reading as a passing one.

## the corpus, and what each row can fail on

* **`fragmented`** (open) — the defect shape #6598's docstring opens with: five
  legs, ranks written by three different batches, two drivers badged `1` and a
  0.10 leg ranked above a 0.30 one, plus one unpriced leg. It carries the tie
  (two legs at 0.300), the gap after it, and the NULL that must sort last.
* **`healthy`** (open) — already correct. It must produce no plan row, no write
  and no manifest row; without it "the repair wrote 3 rows" could equally mean
  "the repair rewrote everything it saw".
* **`settled`** (resolved) — the same fragmented shape on a finished board.
  #6325 says its ranks are the record of how it finished. It must be invisible
  to the plan AND dropped by the write-time re-read.

`test_the_seeded_corpus_can_distinguish_the_wrong_answers` asserts those shapes
are present before anything is measured, so a future edit to the seed cannot
quietly make the rest vacuous.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #7640 rank "
        "round trip (CI job `search-recall` provides one)"
    ),
)

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "scripts"
    / "repair_7640_stale_futures_ranks.py"
)


def _load_repair():
    spec = importlib.util.spec_from_file_location("repair_7640", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load_repair()

_T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)

#: `key -> (probability, stored rank, last_updated offset in hours)`.
#:
#: The offsets are the fragmentation: three different write moments, which is
#: how a market ends up holding ranks from three different orderings at once.
#: Expected field ranks after the repair are in the comments and are asserted
#: from a literal, never re-derived by the test (a test that computes the answer
#: with the same rule it is grading proves nothing).
_FRAGMENTED = {
    "leader":   (0.50, 1, 0),    # -> 1   (already right; must NOT be rewritten)
    "tie_a":    (0.30, 1, 8),    # -> 2   (a second row badged 1: the defect)
    "tie_b":    (0.30, 2, 0),    # -> 2   (already right; ties SHARE a number)
    "trailer":  (0.10, 1, 22),   # -> 4   (ranked above a 0.30 leg; gap skipped)
    "unpriced": (None, 1, 22),   # -> 5   (NULLS LAST, below every priced leg)
}
_EXPECTED_AFTER = {"leader": 1, "tie_a": 2, "tie_b": 2, "trailer": 4, "unpriced": 5}
#: The three the write must change. The other two are the no-op control.
_EXPECTED_WRITTEN = {"tie_a", "trailer", "unpriced"}

_HEALTHY = {"front": (0.60, 1, 0), "back": (0.40, 2, 0)}


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped for the reason `test_tag_counts_real_postgres.py` records:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that made its engine.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def session(pg_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with maker() as s:
        await _seed(s)
        yield s


async def _make_market(s, key: str, status: str, legs: dict) -> tuple[int, dict]:
    """One market plus its legs, by raw INSERT.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `futures_markets.category` / `.mutually_exclusive` / `.status` and
    `futures_outcomes.external_id` / `.name` / `.last_updated` are NOT NULL; the
    first three carry a **client-side `default=`** applied by the ORM and
    invisible to a raw INSERT, so omitting one raises `NotNullViolation` rather
    than silently taking the default. This file is registered in
    `tests/test_pg_gate_seed_completeness.py`'s `COVERED` tuple.

    `last_updated` is written explicitly on every leg because it is the undo's
    witness: a leg seeded from `server_default=now()` would carry the moment of
    the INSERT, and the "a poller touched this row" assertion would be
    comparing two values a few milliseconds apart.
    """
    market_id = (
        await s.execute(
            text(
                "INSERT INTO futures_markets "
                "(source, external_id, name, category, mutually_exclusive, "
                " status, market_tier, volume) "
                "VALUES ('kalshi', :x, :n, 'championship', true, :st, 5, 3242) "
                "RETURNING id"
            ),
            {"x": f"7640-{key}", "n": f"#7640 {key} board", "st": status},
        )
    ).scalar_one()

    ids = {}
    for name, (prob, rank, hours) in legs.items():
        ids[name] = (
            await s.execute(
                text(
                    "INSERT INTO futures_outcomes "
                    "(market_id, external_id, name, current_probability, rank, "
                    " last_updated) "
                    "VALUES (:m, :x, :n, :p, :r, :u) RETURNING id"
                ),
                {
                    "m": market_id,
                    "x": f"{key}-{name}",
                    "n": name,
                    "p": prob,
                    "r": rank,
                    "u": _T0 + timedelta(hours=hours),
                },
            )
        ).scalar_one()
    return market_id, ids


async def _seed(s) -> None:
    s.info["fragmented"] = await _make_market(s, "fragmented", "open", _FRAGMENTED)
    s.info["healthy"] = await _make_market(s, "healthy", "open", _HEALTHY)
    s.info["settled"] = await _make_market(s, "settled", "resolved", _FRAGMENTED)
    await s.commit()


async def _ranks(s, ids: dict) -> dict:
    rows = (
        await s.execute(
            text("SELECT id, rank FROM futures_outcomes WHERE id = ANY(CAST(:ids AS int[]))"),
            {"ids": list(ids.values())},
        )
    ).all()
    by_id = {int(i): (None if r is None else int(r)) for i, r in rows}
    return {name: by_id[oid] for name, oid in ids.items()}


async def _last_updated(s, outcome_id: int):
    return (
        await s.execute(
            text("SELECT last_updated FROM futures_outcomes WHERE id = :i"),
            {"i": outcome_id},
        )
    ).scalar_one()


# ── the corpus is capable of failing ────────────────────────────────────────


@needs_postgres
async def test_the_seeded_corpus_can_distinguish_the_wrong_answers(session):
    _, frag = session.info["fragmented"]
    stored = await _ranks(session, frag)

    # The BEFORE is wrong, so a green AFTER is a real test and not a tautology.
    assert stored != _EXPECTED_AFTER
    # Two legs badged 1 whose prices differ — the shape no tie rule explains.
    assert stored["leader"] == stored["tie_a"] == 1
    # A 0.10 leg outranking a 0.30 one.
    assert stored["trailer"] < stored["tie_b"]
    # A real tie is present, so `rank()` vs `row_number()` is decidable here.
    assert _FRAGMENTED["tie_a"][0] == _FRAGMENTED["tie_b"][0]
    # A real NULL is present, so NULLS LAST is decidable here.
    assert _FRAGMENTED["unpriced"][0] is None
    # The healthy board really is healthy, so a no-op there means something.
    _, healthy = session.info["healthy"]
    assert await _ranks(session, healthy) == {"front": 1, "back": 2}


# ── the plan ────────────────────────────────────────────────────────────────


@needs_postgres
async def test_the_plan_finds_the_broken_open_board_and_nothing_else(session):
    frag_id, _ = session.info["fragmented"]
    healthy_id, _ = session.info["healthy"]
    settled_id, _ = session.info["settled"]

    rows = await repair.plan(session, limit=0)
    planned = {int(r["market_id"]): r for r in rows}

    assert frag_id in planned
    assert planned[frag_id]["bad_legs"] == len(_EXPECTED_WRITTEN)
    assert planned[frag_id]["legs"] == len(_FRAGMENTED)
    assert healthy_id not in planned, "a correct board must not be planned"
    assert settled_id not in planned, "#6325: a finished field keeps its ranks"


@needs_postgres
async def test_the_write_time_reread_drops_a_market_that_settled(session):
    frag_id, _ = session.info["fragmented"]
    settled_id, _ = session.info["settled"]

    assert await repair.still_open(session, [frag_id, settled_id]) == [frag_id]


# ── the round trip ──────────────────────────────────────────────────────────


async def _apply(session):
    """plan -> backup -> reconcile -> write, the documented order."""
    rows = await repair.plan(session, limit=0)
    mids = [int(r["market_id"]) for r in rows]

    await repair.backup(session, mids)
    recon = await repair.reconcile_backup(session, mids)
    assert repair.backup_is_exact(recon), recon

    await session.execute(text(repair.SQL["man_create"]))
    applied_at = datetime(2026, 9, 21, 3, 0, tzinfo=timezone.utc)
    written = await repair.apply_chunk(
        session, await repair.still_open(session, mids), applied_at
    )
    await session.commit()
    return mids, written


@needs_postgres
async def test_the_repair_writes_the_field_rank_and_leaves_the_rest_alone(session):
    _, frag = session.info["fragmented"]
    _, healthy = session.info["healthy"]
    _, settled = session.info["settled"]

    _, written = await _apply(session)

    assert await _ranks(session, frag) == _EXPECTED_AFTER
    # Ties share a number and the next rank skips the gap — `row_number()` would
    # have produced 1, 2, 3, 4, 5 here.
    assert _EXPECTED_AFTER["tie_a"] == _EXPECTED_AFTER["tie_b"]
    assert _EXPECTED_AFTER["trailer"] == _EXPECTED_AFTER["tie_b"] + 2

    # `IS DISTINCT FROM` made the two already-correct legs zero row writes.
    assert written == len(_EXPECTED_WRITTEN)

    # The settled board is untouched in the database, not merely unplanned.
    assert await _ranks(session, settled) == {
        k: v[1] for k, v in _FRAGMENTED.items()
    }
    assert await _ranks(session, healthy) == {"front": 1, "back": 2}


@needs_postgres
async def test_the_backup_covers_every_leg_of_a_written_market(session):
    """Including the two the plan considered fine — the write's unit is the field."""
    _, frag = session.info["fragmented"]
    await _apply(session)

    staged = (
        await session.execute(
            text(
                f"SELECT count(*) FROM {repair.BAK_TABLE} "
                "WHERE outcome_id = ANY(CAST(:ids AS int[]))"
            ),
            {"ids": list(frag.values())},
        )
    ).scalar_one()
    assert int(staged) == len(_FRAGMENTED)


@needs_postgres
async def test_the_manifest_records_only_what_was_written(session):
    _, frag = session.info["fragmented"]
    await _apply(session)

    rows = (
        await session.execute(
            text(
                f"SELECT outcome_id, wrote_rank, seen_last_updated "
                f"FROM {repair.MANIFEST_TABLE}"
            )
        )
    ).all()
    by_id = {int(r[0]): (int(r[1]), r[2]) for r in rows}
    assert set(by_id) == {frag[name] for name in _EXPECTED_WRITTEN}

    # RETURNING gave the POST-update rank...
    for name in _EXPECTED_WRITTEN:
        assert by_id[frag[name]][0] == _EXPECTED_AFTER[name]
    # ...and the UNTOUCHED last_updated. #6598's statement names `rank` and the
    # column has no onupdate, so a re-rank cannot move it — which is the entire
    # reason it can serve as the undo's witness.
    for name in _EXPECTED_WRITTEN:
        assert by_id[frag[name]][1] == _T0 + timedelta(hours=_FRAGMENTED[name][2])


@needs_postgres
async def test_a_rerun_after_a_completed_pass_is_a_no_op(session):
    """The resumability claim, which is entirely `IS DISTINCT FROM`."""
    await _apply(session)
    rows = await repair.plan(session, limit=0)
    assert [int(r["market_id"]) for r in rows] == []


# ── the undo, and the row it must refuse to undo ────────────────────────────


@needs_postgres
async def test_the_restore_reverts_what_it_wrote_and_spares_what_a_poller_rewrote(
    session,
):
    """The clause the D51(b) grant turns on.

    After the repair a poller reprices the board and re-derives the field — the
    ordinary #6598 path. It arrives at the SAME rank this pass wrote, so a
    restore keyed on `rank` alone would put the broken fossil back over a live,
    correct number. `last_updated` is what separates them.
    """
    _, frag = session.info["fragmented"]
    await _apply(session)

    # A poller writes `tie_a`: same rank as the repair wrote, new touch-stamp.
    poller_at = datetime(2026, 9, 21, 4, 0, tzinfo=timezone.utc)
    await session.execute(
        text(
            "UPDATE futures_outcomes SET current_probability = 0.31, "
            "rank = :r, last_updated = :u WHERE id = :i"
        ),
        {"r": _EXPECTED_AFTER["tie_a"], "u": poller_at, "i": frag["tie_a"]},
    )
    await session.commit()

    # The premise of the test: `rank` alone cannot tell this row from an
    # untouched one. If this ever stops holding, the test below is proving
    # something easier than it claims.
    manifest_rank = (
        await session.execute(
            text(
                f"SELECT wrote_rank FROM {repair.MANIFEST_TABLE} WHERE outcome_id = :i"
            ),
            {"i": frag["tie_a"]},
        )
    ).scalar_one()
    current_rank = (await _ranks(session, {"x": frag["tie_a"]}))["x"]
    assert int(manifest_rank) == current_rank

    reverted = await repair.restore(session)

    after = await _ranks(session, frag)
    # SPARED: the poller's row keeps the live number.
    assert after["tie_a"] == _EXPECTED_AFTER["tie_a"]
    assert await _last_updated(session, frag["tie_a"]) == poller_at
    # REVERTED: the rows nothing touched go back to their pre-repair values.
    assert after["trailer"] == _FRAGMENTED["trailer"][1]
    assert after["unpriced"] == _FRAGMENTED["unpriced"][1]
    # NEVER WRITTEN, so never in the manifest, so never reverted.
    assert after["leader"] == _FRAGMENTED["leader"][1]
    assert after["tie_b"] == _FRAGMENTED["tie_b"][1]

    assert reverted == len(_EXPECTED_WRITTEN) - 1

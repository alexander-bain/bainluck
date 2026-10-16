"""#1912 — the per-market census returns exactly what the grouped census did.

PILLAR: TRUTH. SHIP: Resolved Polymarket questions with venue-backed results
stop displaying an ungraded all-Lost field.

The reviewed recovery wave is gated on a FULL census of the never-graded
cohort, and on production that census died at its 20 s budget (2026-10-16
03:54Z, ``measured: false``). Its plan scanned every outcome, joined, sorted
the joined rows by market id and grouped them before it could count a single
market. ``_CENSUS_SQL`` now states the same cohort per market — EXISTS one
outcome, NOT EXISTS an outcome with a winner or a grade — so each market can be
answered from the existing ``futures_outcomes.market_id`` index.

A census that is faster and counts a different population is worse than one
that times out, so this gate is about EQUALITY, on a real server, where the
three-valued logic actually runs:

1. Every outcome multiset up to three legs over the nine leg shapes
   (``is_winner`` NULL/false/true × ``resolution_source`` NULL/a source/``''``),
   plus a market with no legs, crossed with every market-filter shape the
   census keys on (source, status, ``0x`` prefix and its near-misses, NULL and
   literal ``'unknown'`` category). Old SQL, new SQL and a Python oracle of the
   cohort's DEFINITION must return byte-identical rows.
2. The rail's ``census()`` wrapper on the real server: ``measured: true``, the
   oracle's total and split, and its 20 s ``statement_timeout`` in force.
3. The work selection — ``clob_resolve._load_cohort`` with the never-graded
   cohort, paged exactly as the dry-run pages it — walks precisely the market
   ids the census counts.
4. A representative mass: graded, closed, crowned and partially graded markets
   with never-graded siblings in the same categories.

Nothing here claims production latency; the plan and the timing on production
are owed by a separate read after review.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os

import pytest
from sqlalchemy import text

from app.tasks import repair_pm_never_graded as rail

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #1912 census equivalence "
            "gate (CI job: database-integration)"
        ),
    ),
]


#: The nine leg shapes: (is_winner, resolution_source).
_LEGS = [
    (w, src)
    for w in (None, False, True)
    for src in (None, "api_settlement", "")
]

#: (source, status, external_id template, eligible) — the census's three WHERE
#: clauses and their near-misses. ``LIKE '0x%'`` is case-sensitive, so ``0X`` is
#: a near-miss, not an alias.
_FILTERS = [
    ("polymarket", "resolved", "0x{n:06x}", True),
    ("kalshi", "resolved", "0x{n:06x}", False),
    ("polymarket", "open", "0x{n:06x}", False),
    ("polymarket", "closed", "0x{n:06x}", False),
    ("polymarket", "resolved", "{n}", False),
    ("polymarket", "resolved", "0X{n:06x}", False),
    ("polymarket", "resolved", "x0{n:06x}", False),
]

#: NULL and the literal 'unknown' both land in the 'unknown' bucket.
_CATEGORIES = ["tennis", "soccer", None, "unknown", "politics"]


@pytest.fixture
async def db():
    """A real Postgres carrying the schema ``create_all`` builds from the model."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401  — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


class _Seed:
    """Seeds markets and legs, and keeps the oracle's view of what it wrote."""

    def __init__(self, session):
        self.session = session
        self.markets: dict[int, dict] = {}
        self.legs: dict[int, list[tuple]] = {}
        self._next_leg = 1

    async def market(self, mid, source, status, external_id, category, legs):
        await self.session.execute(
            text(
                "INSERT INTO futures_markets (id, source, external_id, name, "
                "category, status, mutually_exclusive, llm_sport_category) "
                "VALUES (:id, :src, :ext, :name, 'futures', :st, true, :cat)"
            ),
            {
                "id": mid,
                "src": source,
                "ext": external_id,
                "name": f"Market {mid}",
                "st": status,
                "cat": category,
            },
        )
        self.markets[mid] = {
            "source": source,
            "status": status,
            "external_id": external_id,
            "category": category,
        }
        self.legs[mid] = []
        for is_winner, src in legs:
            oid = self._next_leg
            self._next_leg += 1
            # `is_winner` is named on every insert, NULL included: an omitted
            # column stores the server default `false`, which is a different
            # leg shape from the one this gate claims to have seeded.
            await self.session.execute(
                text(
                    "INSERT INTO futures_outcomes (id, market_id, external_id, "
                    "name, is_winner, resolution_source) VALUES "
                    "(:id, :mid, :ext, :name, :w, :src)"
                ),
                {
                    "id": oid,
                    "mid": mid,
                    "ext": f"leg-{oid}",
                    "name": f"Leg {oid}",
                    "w": is_winner,
                    "src": src,
                },
            )
            self.legs[mid].append((is_winner, src))

    def oracle_ids(self) -> set[int]:
        """The cohort's DEFINITION in Python, independent of either SQL form:
        an eligible market with at least one leg, no leg crowned, no leg
        carrying any ``resolution_source`` (``''`` is a value, not an absence).
        """
        out = set()
        for mid, m in self.markets.items():
            legs = self.legs[mid]
            if not (
                m["source"] == "polymarket"
                and m["status"] == "resolved"
                and m["external_id"].startswith("0x")
            ):
                continue
            if not legs:
                continue
            if any(w is True for w, _ in legs):
                continue
            if any(src is not None for _, src in legs):
                continue
            out.add(mid)
        return out

    def oracle_rows(self) -> dict[str, int]:
        by_cat: dict[str, int] = {}
        for mid in self.oracle_ids():
            cat = self.markets[mid]["category"] or "unknown"
            by_cat[cat] = by_cat.get(cat, 0) + 1
        return by_cat


async def _rows(session, sql) -> list[tuple[str, int]]:
    return [(r.category, int(r.markets)) for r in (await session.execute(text(sql))).all()]


def _digest(rows) -> str:
    """Order-free digest. ``ORDER BY 2 DESC`` leaves ties unordered in BOTH
    forms, and the census folds rows into a dict, so the multiset is the
    contract."""
    return hashlib.sha256(json.dumps(sorted(rows)).encode()).hexdigest()


async def _census_ids(session) -> set[int]:
    """The market ids the per-market census counts — same FROM/WHERE, no GROUP."""
    sql = f"""
        SELECT fm.id FROM futures_markets fm
        WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
          AND fm.external_id LIKE '0x%'
          AND {rail.POPULATION_EXISTS_SQL}
    """
    assert rail.POPULATION_EXISTS_SQL in rail._CENSUS_SQL
    return {r.id for r in (await session.execute(text(sql))).all()}


async def _walk_work_selection(session, page: int) -> list[int]:
    """Page the never-graded work selection exactly as ``_dry_run`` does:
    ``ORDER BY fm.id DESC`` with the last id as the next ``before``."""
    from app.tasks.clob_resolve import _COHORT_NEVER_GRADED, _load_cohort

    seen: list[int] = []
    before = None
    for _ in range(10_000):
        rows = await _load_cohort(session, page, before, cohort=_COHORT_NEVER_GRADED)
        if not rows:
            return seen
        seen.extend(r.id for r in rows)
        before = rows[-1].id
    raise AssertionError("work selection did not terminate")


async def _seed_exhaustive(seed: _Seed) -> None:
    shapes = [()]
    for size in (1, 2, 3):
        shapes.extend(itertools.combinations_with_replacement(_LEGS, size))
    assert len(shapes) == 1 + 9 + 45 + 165
    mid = 1
    for f_index, (source, status, ext, _eligible) in enumerate(_FILTERS):
        for s_index, legs in enumerate(shapes):
            cat = _CATEGORIES[(s_index + f_index) % len(_CATEGORIES)]
            await seed.market(mid, source, status, ext.format(n=mid), cat, legs)
            mid += 1
    await seed.session.commit()


async def test_old_new_and_the_definition_agree_over_every_leg_and_filter_shape(db):
    seed = _Seed(db)
    await _seed_exhaustive(seed)

    expected = seed.oracle_rows()
    old = await _rows(db, rail._CENSUS_GROUPED_SQL)
    new = await _rows(db, rail._CENSUS_SQL)

    # Not vacuous: the cohort is non-empty, spans the 'unknown' fold, and is a
    # strict subset of the eligible markets (graded/crowned shapes are OUT).
    eligible = sum(1 for m in seed.markets.values()
                   if m["source"] == "polymarket" and m["status"] == "resolved"
                   and m["external_id"].startswith("0x"))
    total = sum(expected.values())
    assert 0 < total < eligible
    assert "unknown" in expected and len(expected) >= 4

    assert dict(old) == expected, "the grouped census drifted from the definition"
    assert dict(new) == expected, "the per-market census drifted from the definition"
    assert _digest(new) == _digest(old)
    assert sorted(new) == sorted(old)
    assert len(new) == len(old) == len(expected), "one row per category, no duplicates"

    # The NULL-leg cases are the ones a human reasons about wrongly. Pin them
    # by id, not by total, so two compensating errors cannot cancel out.
    ids = await _census_ids(db)
    assert ids == seed.oracle_ids()
    shapes_in = {tuple(seed.legs[m]) for m in ids}
    assert ((None, None),) in shapes_in, "an all-NULL winner field is IN"
    assert ((False, None), (None, None)) in {tuple(sorted(s, key=repr)) for s in shapes_in}, (
        "a mixed NULL/false winner field is IN"
    )
    for m in ids:
        assert seed.legs[m], "a market with no legs is never counted"
        assert all(w is not True and src is None for w, src in seed.legs[m])


async def test_the_rail_census_on_a_real_server_is_measured_bounded_and_exact(db):
    seed = _Seed(db)
    await _seed_exhaustive(seed)

    out = await rail.census(db)
    assert out["measured"] is True
    assert out["by_category"] == seed.oracle_rows()
    assert out["total_markets"] == len(seed.oracle_ids())
    # The bound is the server's, in this transaction, not a string we sent.
    timeout = (await db.execute(text("SHOW statement_timeout"))).scalar()
    assert timeout == "20s"
    assert rail._CENSUS_TIMEOUT_MS == 20_000
    await db.rollback()


@pytest.mark.parametrize("page", [1, 7, 40])
async def test_the_work_selection_pages_exactly_the_markets_the_census_counts(db, page):
    seed = _Seed(db)
    await _seed_exhaustive(seed)

    walked = await _walk_work_selection(db, page)
    assert len(walked) == len(set(walked)), "a page repeated a market"
    census_ids = await _census_ids(db)
    assert set(walked) == census_ids == seed.oracle_ids()
    out = await rail.census(db)
    assert out["total_markets"] == len(walked)
    await db.rollback()


async def test_a_representative_graded_mass_with_never_graded_siblings(db):
    """The shape production carries: most resolved markets are graded (a
    winner and a source on every leg), some are graded all-losers, a few are
    partially graded or crowned without a source, and the never-graded tail
    sits beside them in the same categories — plus other sources' markets
    carrying ungraded legs that must never be counted."""
    seed = _Seed(db)
    mid = 1
    cats = ["tennis", "soccer", "basketball", None]
    for i in range(1200):
        n = 2 + i % 5
        kind = i % 20
        if kind < 11:      # graded, winner crowned
            legs = [(k == 0, "api_settlement") for k in range(n)]
        elif kind < 14:    # graded all-losers
            legs = [(False, "pass2_loser")] * n
        elif kind == 14:   # partially graded
            legs = [(False, "api_settlement")] + [(False, None)] * (n - 1)
        elif kind == 15:   # crowned, never sourced
            legs = [(True, None)] + [(False, None)] * (n - 1)
        elif kind == 16:   # never graded, all-NULL winner field
            legs = [(None, None)] * n
        else:              # never graded, default `false` winner field
            legs = [(False, None)] * n
        await seed.market(mid, "polymarket", "resolved", f"0x{mid:06x}",
                          cats[i % len(cats)], legs)
        mid += 1
    for i in range(300):   # ungraded legs on markets the census never keys on
        source, status, ext = [
            ("kalshi", "resolved", f"0x{mid:06x}"),
            ("polymarket", "closed", f"0x{mid:06x}"),
            ("polymarket", "resolved", f"{mid}"),
        ][i % 3]
        await seed.market(mid, source, status, ext, cats[i % len(cats)],
                          [(False, None)] * (2 + i % 3))
        mid += 1
    await db.commit()

    expected = seed.oracle_rows()
    assert sum(expected.values()) == 1200 * 4 // 20, "never-graded tail = kinds 16..19"
    old = await _rows(db, rail._CENSUS_GROUPED_SQL)
    new = await _rows(db, rail._CENSUS_SQL)
    assert dict(old) == dict(new) == expected
    assert _digest(old) == _digest(new)
    assert set(await _walk_work_selection(db, rail.APPLY_MARKET_CAP)) == seed.oracle_ids()

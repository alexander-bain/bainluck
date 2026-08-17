"""LAT-P058 / #1866 — the golf identity prefilter, the database's former #1 evictor.

`_build_completed_tournament` prefilters `futures_markets` down to golf before running
`_is_golf_market` in Python. Measured on production v3817 that one statement was
**533.7 GB/day of physical reads, 19% of every read the database performs** — 1,110
calls/day, 492.2 MB each, mean 2,742 ms, on a user-facing route.

It selects 7,169 rows out of 779,617 (0.92%). Before the two partial indexes named in
`GOLF_IDENTITY_INDEXES` it paid a full sequential scan of a 977 MB heap to find them.
With them it is a `BitmapOr`: planner cost 128,191.5 -> 12,243.92, per-call physical
reads 516.7 -> 2.395 MB, warm runtime ~2,900 ms -> ~18 ms.

**There is exactly one shape, and this file no longer tests a second one (#1917).** A
`UNION` rewrite was built, indexed and measured, and it is **4.79x SLOWER** than the
`OR` while costing 2.8x less on paper — 94 of its 98 ms is a `HashAggregate` the `OR`
never pays. It was refused (ruling 076, `lat-p061-split-scan-refused.md`) and deleted
along with its `GOLF_IDENTITY_SPLIT_SCAN` flag, because measured-worse code behind a
permanently-off switch is a trap rather than a rollback path. The tests that kept that
branch green went with it: a maintained, passing test suite is exactly what made the
dead branch read as an unfinished migration.

What these tests lock down, all of it about the shape that actually runs:

1. **The predicate selects what it claims to**, against a seeded corpus that includes
   the adversarial cases (a row matching ONLY the `external_id` branch, a row matching
   ONLY the category branch, a row matching BOTH, and rows matching neither).
2. **`golf_identity_select()` emits ONE statement and takes no shape argument** — the
   regression guard for #1917, so the split scan cannot quietly return.
3. **The four selected columns never drift** from what `_is_golf_market` and the slug
   test actually read.
4. **The index names stay in sync** with the DDL spec that created them.
"""

import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base

from app.routes.golf import (
    GOLF_IDENTITY_INDEXES,
    golf_identity_select,
)


# --------------------------------------------------------------------------
# A standalone mirror of the four columns the prefilter touches. Using a local
# Base keeps this test independent of the production metadata (and of every
# other table's SQLite-hostile column types), while the predicates under test
# are imported from the real module.
# --------------------------------------------------------------------------
Base = declarative_base()


class _FM(Base):
    __tablename__ = "futures_markets"
    id = Column(Integer, primary_key=True)
    source = Column(String)
    external_id = Column(String)
    name = Column(String)
    llm_sport_category = Column(String)


#: (id, source, external_id, llm_sport_category) — the discriminating corpus.
#: `expected` names which rows the prefilter must return, and why.
_CORPUS = [
    # matches BOTH branches — must appear exactly once
    (1, "odds_api", "golf_pga_championship_winner", "golf"),
    # matches the external_id branch ONLY (category is wrong/absent)
    (2, "odds_api", "golf_the_open_winner", "other"),
    (3, "odds_api", "golf_masters_winner", None),
    # matches the category branch ONLY
    (4, "kalshi", "KXPGATOUR-THOC26", "golf"),
    (5, "datagolf", "datagolf:masters:win", "golf"),
    # matches NEITHER — the 99% of the table that must stay out
    (6, "kalshi", "KXNBA-CHAMP", "basketball"),
    (7, "polymarket", "0xdeadbeef", None),
    (8, "odds_api", "soccer_epl_winner", "soccer"),
    # `golf_%`'s `_` is a LIKE single-char wildcard, not a literal: 'golfXwinner'
    # matches today and must keep matching.
    (9, "odds_api", "golfXwinner", None),
    # ILIKE is case-insensitive; a plain `LIKE` would silently drop this.
    (10, "odds_api", "GOLF_US_OPEN_WINNER", None),
]

_EXPECTED_IDS = {1, 2, 3, 4, 5, 9, 10}


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        for mid, source, external_id, category in _CORPUS:
            s.add(
                _FM(
                    id=mid,
                    source=source,
                    external_id=external_id,
                    name=f"market {mid}",
                    llm_sport_category=category,
                )
            )
        s.commit()
        yield s


def _ids(session, stmt):
    return {row.id for row in session.execute(stmt).all()}


# --------------------------------------------------------------------------
# 1 — what the predicate selects
# --------------------------------------------------------------------------


def test_selects_the_expected_rows(session):
    assert _ids(session, golf_identity_select()) == _EXPECTED_IDS


def test_a_row_matching_both_branches_appears_exactly_once(session):
    """Row 1 satisfies both branches of the `OR`.

    A duplicate is not cosmetic here: `_build_completed_tournament` appends to
    `matched_ids` in scan order and phase 2 re-orders by that list, so a doubled
    id would double a market in the winner field. The `OR` cannot duplicate — this
    asserts the property directly rather than trusting the shape, because it is the
    property the caller depends on.
    """
    ids = [row.id for row in session.execute(golf_identity_select()).all()]
    assert len(ids) == len(set(ids))
    assert ids.count(1) == 1


def test_rows_matching_neither_branch_are_excluded(session):
    assert _ids(session, golf_identity_select()).isdisjoint({6, 7, 8})


def test_underscore_stays_a_like_wildcard_and_ilike_stays_case_insensitive(session):
    """Two ways a 'tidy-up' of the pattern would silently change the result set."""
    ids = _ids(session, golf_identity_select())
    assert 9 in ids, "golf_% must keep matching 'golfXwinner' (_ is a wildcard)"
    assert 10 in ids, "ILIKE must keep matching 'GOLF_US_OPEN_WINNER'"


# --------------------------------------------------------------------------
# 2 — one shape, no switch (#1917 / ruling 076 regression guard)
# --------------------------------------------------------------------------


def test_the_shape_is_the_indexed_or_and_there_is_only_one_statement():
    """The deletion guard.

    The `UNION` rewrite measured **4.79x slower** than this `OR` (≈88.2 ms vs
    ≈18.4 ms warm median, 2.45x shared buffers) while the planner ranked it 2.8x
    CHEAPER. It was refused and removed with its flag. If a `UNION` ever reappears
    in this statement, the numbers that refused it are in ruling 076 — read them
    before making this test pass.
    """
    sql = str(golf_identity_select().compile(compile_kwargs={"literal_binds": True}))
    upper = sql.upper()
    assert "UNION" not in upper
    assert " OR " in upper
    assert upper.count("FROM FUTURES_MARKETS") == 1


def test_golf_identity_select_takes_no_shape_argument():
    """No `split=`, and no config var behind it.

    A default-off keyword is how the trap came back last time: unreachable in
    production, green in CI, one `heroku config:set` from live.
    """
    import inspect

    params = inspect.signature(golf_identity_select).parameters
    assert params == {}, f"golf_identity_select must take no arguments, got {list(params)}"

    src = inspect.getsource(golf_identity_select)
    assert "split" not in src
    assert "GOLF_IDENTITY_SPLIT_SCAN" not in src


def test_no_split_scan_flag_survives_in_the_module():
    """Belt and braces: the env var name must not exist anywhere in the module.

    `_golf_split_scan_enabled` and `_GOLF_SPLIT_SCAN_ENV` are deleted; this asserts
    the deletion rather than the absence of a call site.
    """
    import app.routes.golf as golf_module

    assert not hasattr(golf_module, "_golf_split_scan_enabled")
    assert not hasattr(golf_module, "_GOLF_SPLIT_SCAN_ENV")
    assert not hasattr(golf_module, "_GOLF_SPLIT_SCAN_TRUE")


# --------------------------------------------------------------------------
# 3 — the contract with the caller and with the DDL spec
# --------------------------------------------------------------------------


def test_exposes_exactly_the_four_columns_the_caller_reads(session):
    """`_is_golf_market` reads source/external_id/name; the slug test reads name."""
    row = session.execute(golf_identity_select()).first()
    assert set(row._mapping.keys()) == {"id", "source", "external_id", "name"}
    assert row.name.startswith("market ")
    assert row.source
    assert row.external_id


def test_index_names_are_declared_for_the_ddl_spec():
    """The spec, the DDL and the code must name the same two indexes.

    These two indexes are LIVE and load-bearing: they are what turns this `OR` into
    a `BitmapOr` instead of a seq scan of a 977 MB heap. The `UNION` was deleted;
    the indexes were not, and must not be.
    """
    assert GOLF_IDENTITY_INDEXES == (
        "ix_fm_golf_identity_category",
        "ix_fm_golf_identity_extid",
    )

"""LAT-P058 / #1866 — the golf identity prefilter, the database's #1 evictor.

`_build_completed_tournament` prefilters `futures_markets` down to golf before running
`_is_golf_market` in Python. Measured on production v3817 that one statement was
**533.7 GB/day of physical reads, 19% of every read the database performs** — 1,110
calls/day, 492.2 MB each, mean 2,742 ms, on a user-facing route.

It selects 7,169 rows out of 779,617 (0.92%) and pays a full sequential scan of a
977 MB heap to find them, because `OR` defeats every index on the table.

What these tests lock down:

1. **Set-equality of the two shapes.** The `UNION` shape is the one the covering
   partial indexes can serve; it must select exactly what the `OR` selects. Proven
   here against a seeded corpus that includes the adversarial cases (a row matching
   ONLY the `external_id` branch, a row matching ONLY the category branch, a row
   matching BOTH — which is where a `UNION ALL` would duplicate — and rows matching
   neither).
2. **The default is unchanged.** With no config var set, the shape is the `OR` that
   shipped. This is load-bearing: `EXPLAIN` on production says the `UNION` costs
   255,180 against the `OR`'s 128,191 *until the indexes exist*, so shipping it bare
   would have DOUBLED the reads of the largest query in the database.
3. **The flag parses the way the spec says it does**, so the Integrator's
   `heroku config:set` and the code agree on what "on" means.
4. **The four selected columns never drift** from what `_is_golf_market` and the slug
   test actually read.
"""

import os
from unittest import mock

import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base

from app.routes.golf import (
    GOLF_IDENTITY_INDEXES,
    _golf_split_scan_enabled,
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
    # matches BOTH branches — the row a `UNION ALL` would return twice
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
    # matches today and must keep matching, or the rewrite is not equivalent.
    (9, "odds_api", "golfXwinner", None),
    # ILIKE is case-insensitive; a plain `LIKE` rewrite would silently drop this.
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
# 1 — set-equality
# --------------------------------------------------------------------------


def test_or_shape_selects_the_expected_rows(session):
    assert _ids(session, golf_identity_select(split=False)) == _EXPECTED_IDS


def test_union_shape_selects_the_expected_rows(session):
    assert _ids(session, golf_identity_select(split=True)) == _EXPECTED_IDS


def test_the_two_shapes_are_set_identical(session):
    """The whole licence for the rewrite. Proven, not asserted by construction.

    Production capture on v3817 agrees: 7,169 = 7,169 rows, symmetric difference
    0/0, md5 of the ordered id list `0e7625c986754f8315b451c1003dd206` for both.
    """
    or_ids = _ids(session, golf_identity_select(split=False))
    union_ids = _ids(session, golf_identity_select(split=True))
    assert or_ids == union_ids
    assert or_ids - union_ids == set()
    assert union_ids - or_ids == set()


def test_union_does_not_duplicate_a_row_matching_both_branches(session):
    """Row 1 satisfies both branches. `UNION ALL` would emit it twice.

    A duplicate is not cosmetic here: `_build_completed_tournament` appends to
    `matched_ids` in scan order and phase 2 re-orders by that list, so a doubled
    id would double a market in the winner field.
    """
    rows = session.execute(golf_identity_select(split=True)).all()
    ids = [row.id for row in rows]
    assert len(ids) == len(set(ids))
    assert ids.count(1) == 1


def test_rows_matching_neither_branch_are_excluded(session):
    both = _ids(session, golf_identity_select(split=False)) | _ids(
        session, golf_identity_select(split=True)
    )
    assert both.isdisjoint({6, 7, 8})


def test_underscore_stays_a_like_wildcard_and_ilike_stays_case_insensitive(session):
    """Two ways a 'tidy-up' of the pattern would silently change the result set."""
    for shape in (False, True):
        ids = _ids(session, golf_identity_select(split=shape))
        assert 9 in ids, "golf_% must keep matching 'golfXwinner' (_ is a wildcard)"
        assert 10 in ids, "ILIKE must keep matching 'GOLF_US_OPEN_WINNER'"


# --------------------------------------------------------------------------
# 2 — the default shape, and the flag
# --------------------------------------------------------------------------


def test_default_shape_is_the_or_that_shipped():
    """Bare-merge safety.

    Production `EXPLAIN`: `OR` = one Seq Scan, total cost 128,191.5; `UNION` = two
    Seq Scans + Sort + Unique, 255,180.0. Until the covering partial indexes exist
    the `UNION` is a 1.99x regression on the single largest query in the database,
    so the default must be the `OR`.
    """
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GOLF_IDENTITY_SPLIT_SCAN", None)
        assert _golf_split_scan_enabled() is False
        sql = str(golf_identity_select().compile(compile_kwargs={"literal_binds": True}))
    assert "UNION" not in sql.upper()
    assert " OR " in sql.upper()


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on", " on "])
def test_flag_on_values(raw):
    with mock.patch.dict(os.environ, {"GOLF_IDENTITY_SPLIT_SCAN": raw}):
        assert _golf_split_scan_enabled() is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", "", "maybe"])
def test_flag_off_values(raw):
    with mock.patch.dict(os.environ, {"GOLF_IDENTITY_SPLIT_SCAN": raw}):
        assert _golf_split_scan_enabled() is False


def test_flag_selects_the_union_shape():
    with mock.patch.dict(os.environ, {"GOLF_IDENTITY_SPLIT_SCAN": "1"}):
        sql = str(golf_identity_select().compile(compile_kwargs={"literal_binds": True}))
    assert "UNION" in sql.upper()
    # Two independently indexable branches — one per index in the spec.
    assert sql.upper().count("FROM FUTURES_MARKETS") == 2


# --------------------------------------------------------------------------
# 3 — the contract with the caller and with the DDL spec
# --------------------------------------------------------------------------


def test_both_shapes_expose_exactly_the_four_columns_the_caller_reads(session):
    """`_is_golf_market` reads source/external_id/name; the slug test reads name.

    Attribute access must survive the subquery wrapper the UNION shape adds — if it
    does not, the caller fails at runtime rather than at import.
    """
    for shape in (False, True):
        row = session.execute(golf_identity_select(split=shape)).first()
        assert set(row._mapping.keys()) == {"id", "source", "external_id", "name"}
        assert row.name.startswith("market ")
        assert row.source
        assert row.external_id


def test_index_names_are_declared_for_the_ddl_spec():
    """The spec, the DDL and the code must name the same two indexes.

    `docs/audits/latency/lat-p058-golf-index-spec.md` is the Integrator's runbook;
    this constant is what stops it drifting from the query it exists to serve.
    """
    assert GOLF_IDENTITY_INDEXES == (
        "ix_fm_golf_identity_category",
        "ix_fm_golf_identity_extid",
    )

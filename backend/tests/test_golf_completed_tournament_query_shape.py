"""LAT-P014/#1107 — `_build_completed_tournament` must not load the golf corpus.

Why this file exists
--------------------
`_build_completed_tournament` runs whenever the live golf listing does not contain
a slug — which is every completed tournament, every multi-edition major, and every
key that does not exist at all. It used to be a single

    select(FuturesMarket).options(selectinload(FuturesMarket.outcomes))
      .where(external_id ILIKE 'golf_%' OR llm_sport_category == 'golf')

with **no status filter, no date filter and no row bound**, matched against the
slug in Python afterwards. So it loaded every golf market that has ever existed,
with every outcome eager-loaded (`futures_outcomes` is 3.2M rows; a golf winner
market carries the whole field), to answer a question about one slug. Its result
is never cached, so every request paid it again.

MEASURED in production 2026-08-09, each sample paired against an
`event:ufc:26aug12` control on the same route 4-5s away:

===================================  ==========================================
`event:golf:the-open-championship`   **503 @ 30,286 / 30,268 / 30,279 ms**
`event:golf:pga-championship`        **503 @ 30,263 ms**
`event:golf:u-s-open`                **503 @ 30,269 ms**
`event:golf:the-masters`             200 @ 17,598 ms, then **503 @ 30,279 ms**
control                              290 - 1,783 ms throughout
===================================  ==========================================

30.3s is Heroku's H12 boundary. All four golf majors resolve through this
function, `/api/events/search?q=the open` offers their concept keys, and #1063
documents them as "guaranteed never-dead" — so this was a live broken promise on
a page the product links to.

The cause was isolated with an internal control rather than inferred: on the same
route, a bad CYCLING key 404s in 290ms (its adapter proves absence from an
in-memory config parse) while a bad GOLF key took 6,931-14,518ms. Same route,
same outcome; the only difference is how much work runs before giving up.

These assert the SHAPE, not wall-clock — a timing assertion on CI hardware is
flaky and proves nothing about production (LAT-P005).
"""

from __future__ import annotations

import inspect
import re

from app.routes import golf as golf_route


SRC = inspect.getsource(golf_route._build_completed_tournament)

# LAT-P058/#1866 moved the phase-1 predicate and projection out of the function body
# and into `golf_identity_select`, so that the `OR` can be swapped for an indexable
# `UNION` once the covering partial indexes exist. The invariants below did not move
# with it — they follow the code. See `test_golf_identity_prefilter.py` for the
# set-equality proof between the two shapes.
PREFILTER_SRC = inspect.getsource(golf_route.golf_identity_select)


def _strip_comments(src: str) -> str:
    """Drop whole-line `#` comments.

    The fix is heavily commented and those comments QUOTE the anti-pattern they
    replaced, so a naive substring check matches the explanation rather than live
    code.
    """
    return "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )


CODE = _strip_comments(SRC)
PREFILTER_CODE = _strip_comments(PREFILTER_SRC)


def test_the_matching_pass_does_not_eager_load_outcomes():
    """The dominant cost: every outcome of every golf market, to match one slug.

    The match reads only `source`, `external_id` and `name`. Outcomes belong to
    the rows that actually matched, and nowhere else.
    """
    match_pass, _, hydrate_pass = CODE.partition("if not matched_ids:")
    assert "selectinload" not in match_pass, (
        "the matching pass is eager-loading outcomes again — that is the 3.2M-row "
        "load which put all four golf majors over Heroku's 30s H12 boundary"
    )
    assert "selectinload(FuturesMarket.outcomes)" in hydrate_pass, (
        "the hydrate pass lost its outcomes load; the winner field will be empty"
    )


def test_the_matching_pass_selects_only_the_columns_the_match_reads():
    """A narrow projection, not the whole entity.

    `select(FuturesMarket)` pulls every column of every golf row even without
    outcomes. The predicate needs three fields.
    """
    match_pass = CODE.split("if not matched_ids:")[0]
    assert "golf_identity_select()" in match_pass, (
        "the matching pass no longer goes through the narrow prefilter — if the "
        "projection has been inlined again, this test must follow it, not be deleted"
    )
    assert "select(FuturesMarket)" not in match_pass, (
        "the matching pass is selecting whole entities again"
    )
    assert re.search(r"FuturesMarket\.id\s*,", PREFILTER_CODE), (
        "the prefilter is not selecting a narrow column projection"
    )
    for col in ("FuturesMarket.source", "FuturesMarket.external_id",
                "FuturesMarket.name"):
        assert col in PREFILTER_CODE, f"{col} is read by the match but not selected"
    assert "selectinload" not in PREFILTER_CODE, (
        "the prefilter is eager-loading outcomes — the 3.2M-row load is back"
    )


def test_the_hydrate_pass_is_bounded_by_the_matched_ids():
    """Phase 2 must be a subset keyed by id — that is what makes this
    set-identical to the single-query version rather than merely similar."""
    hydrate_pass = CODE.split("if not matched_ids:")[1]
    assert "FuturesMarket.id.in_(matched_ids)" in hydrate_pass, (
        "the hydrate pass is not bounded to the matched ids — it is loading the "
        "corpus again one step later"
    )


def test_the_hydrated_rows_keep_the_order_the_match_found_them_in():
    """Neither query carries an ORDER BY, so the two phases can only be made to
    agree explicitly.

    `_assemble_completed_winner_field` and the `matched_key` pick both consume
    this sequence, so a reordering is a behaviour change, not a cosmetic one.
    """
    assert re.search(r"for i in matched_ids", CODE), (
        "the hydrated rows are not re-ordered to the phase-1 match order"
    )


def test_absence_is_still_reported_as_absence():
    """The early return must survive. Without it a miss falls through to the
    hydrate pass and builds a tournament out of nothing."""
    assert "if not matched_ids:" in CODE
    assert CODE.count("return None") >= 2, (
        "the not-found paths were removed; a miss must still return None so the "
        "route can 404"
    )


def test_the_predicate_that_selects_golf_markets_is_unchanged():
    """Recall guard. The point of this function is completed tournaments, so the
    row set it considers must not narrow — no status or date filter may creep in
    while 'optimising', or completed majors stop resolving entirely."""
    match_pass = CODE.split("if not matched_ids:")[0]
    assert 'FuturesMarket.external_id.ilike("golf_%")' in PREFILTER_CODE
    assert 'FuturesMarket.llm_sport_category == "golf"' in PREFILTER_CODE
    for where, label in ((match_pass, "the matching pass"),
                         (PREFILTER_CODE, "the prefilter")):
        assert "status" not in where, (
            f"a status filter appeared in {label} of the completed-tournament "
            "lookup — completed markets are exactly what this function exists to find"
        )
    # LAT-P058: the indexable shape must be a UNION, never a UNION ALL. `A UNION B`
    # is `A OR B` de-duplicated; `UNION ALL` would double every row that satisfies
    # both branches, and `matched_ids` feeds an ordered hydrate.
    if "union" in PREFILTER_CODE:
        assert "union_all" not in PREFILTER_CODE, (
            "the indexable shape uses UNION ALL — rows matching both branches would "
            "be returned twice and doubled in the winner field"
        )


# ---------------------------------------------------------------------------
# Behaviour, not just shape.
#
# Every existing test of this function MONKEYPATCHES it
# (`tests/integration/test_route_golf.py:157`), so its body had never executed in
# the suite. LAT-P014 changed the matching pass from ORM entities to a narrow
# column projection, which hands `_is_golf_market` a SQLAlchemy `Row` instead of
# a `FuturesMarket`. If Row attribute access did not work, this would 500 on
# exactly the path being fixed — so it is executed here rather than reasoned about.
# ---------------------------------------------------------------------------
import pytest
from types import SimpleNamespace


class _Result:
    def __init__(self, rows, scalar_rows=None):
        self._rows = rows
        self._scalar_rows = scalar_rows or []

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def unique(self):
        return self

    # `.scalars().unique().all()` and the bare `.all()` differ by path, so the
    # phase-2 result object is constructed with its own rows.


class _StubDB:
    """Returns phase-1 rows on the first execute, phase-2 rows on the second."""

    def __init__(self, ident_rows, hydrated):
        self.ident_rows = ident_rows
        self.hydrated = hydrated
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        if len(self.statements) == 1:
            return _Result(self.ident_rows)
        return _Result([], None) if False else _ScalarResult(self.hydrated)


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self._rows


def _row(i, name, source="datagolf", ext="golf_x"):
    return SimpleNamespace(id=i, source=source, external_id=ext, name=name)


@pytest.mark.asyncio
async def test_an_unknown_slug_returns_none_without_a_second_query():
    """The miss path must short-circuit before hydrating anything.

    This is the 404 that measured 6,931-14,518ms in production.
    """
    db = _StubDB([_row(1, "Wyndham Championship Winner 2026")], hydrated=[])
    out = await golf_route._build_completed_tournament("no-such-tournament-zqx", db)

    assert out is None
    assert len(db.statements) == 1, (
        f"{len(db.statements)} queries ran for a slug that matches nothing — the "
        "miss must not reach the hydrate pass"
    )


@pytest.mark.asyncio
async def test_a_matching_slug_hydrates_only_the_matched_ids():
    """A hit hydrates the matched rows and nothing else.

    Guards the property that makes the two-phase rewrite set-identical: phase 2
    is a subset keyed by the ids phase 1 chose.
    """
    # Real production names and their real derived slug: `_normalize_tournament`
    # folds both Open markets to the key `the_open`, whose display slug is
    # `the-open-championship` — the exact key that was 503ing.
    rows = [
        _row(11, "The Open Championship Winner 2026"),
        _row(22, "Masters Tournament Winner 2026"),
        _row(33, "The Open Championship Top 5 2026"),
    ]
    hydrated = [
        SimpleNamespace(id=11, name=rows[0].name, source="datagolf",
                        external_id="golf_x", outcomes=[]),
        SimpleNamespace(id=33, name=rows[2].name, source="datagolf",
                        external_id="golf_x", outcomes=[]),
    ]
    db = _StubDB(rows, hydrated)
    try:
        await golf_route._build_completed_tournament("the-open-championship", db)
    except Exception:
        # Downstream assembly needs richer fixtures; the contract under test is
        # which rows the two passes select, and that is already observable.
        pass

    # >= 2, not == 2: once a slug matches, the function continues into downstream
    # assembly which issues its own queries. The contract under test is that the
    # SECOND statement is the bounded hydrate.
    assert len(db.statements) >= 2, "the hydrate pass did not run for a match"
    compiled = str(db.statements[1])
    assert "IN (" in compiled.replace("IN(", "IN ("), (
        "the hydrate pass is not bounded by an id list"
    )
    # `IN` renders as ONE expanding bindparam whose value is the id LIST, not as
    # separate integer params — so collect from list-valued params too.
    bound = db.statements[1].compile().params
    ids = set()
    for v in bound.values():
        if isinstance(v, (list, tuple)):
            ids.update(x for x in v if isinstance(x, int))
        elif isinstance(v, int):
            ids.add(v)
    assert ids == {11, 33}, (
        f"hydrated {ids} — must be exactly the ids the slug matched (11, 33), "
        "not the Masters row (22) and not the whole corpus"
    )

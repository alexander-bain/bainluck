"""The feed's outcome projection must LOAD every outcome column the feed READS.

CERT-622. Q480 added `drop_duplicate_legs(market.outcomes, lambda o: o.external_id)`
to both futures feed paths and to neither of their `load_only` lists. Under async
SQLAlchemy an unprojected column read is a lazy load, and a lazy load raises
`MissingGreenlet` INSIDE the per-item serializer — so `_score_futures` (Discover)
skips the entire futures pool and `_score_sports_mode_futures` (Sports) falls to
its outer catch and serves a degraded partial feed. Q480's own 25 tests were green
throughout, because every one of them ran on plain-object doubles that carry every
attribute. **A double cannot have a projection, so a double cannot have this bug.**

So this file refuses doubles. It runs the REAL option list from
`app.routes.feed._futures_feed_load_options()` through SQLAlchemy's actual loader
against an in-memory SQLite database, and asks the mapper which columns came back.

Two halves, and the split is the point:

* the **loaded** set is MEASURED, by running the loader and reading
  `inspect(outcome).unloaded` — not by parsing the source. A mistake in this
  file's source scanning cannot make the loaded side wrong.
* the **read** set is DERIVED from the two route bodies by AST, so a column added
  to a future read fails here without anyone remembering to update a list.

`test_the_card_still_builds_...` is the served-shape half: it detaches the market
from its session before running the display pipeline, which turns an unprojected
read into a raise exactly as the async boundary does, and then asserts a real card
comes out.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# SQLite cannot render Postgres column types. These two directives affect DDL
# compilation for the SQLite dialect only — the production engine is Postgres and
# never reaches them. Without this the models simply will not CREATE here, and the
# whole real-loader approach is unavailable.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


_FEED_PY = pathlib.Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"

# The two futures feed paths. Both must be found; see `_feed_function`.
_FEED_SCORERS = ("_score_futures", "_score_sports_mode_futures")

# The real bridesmaids rows (futures_markets 12194657) — the market whose card read
# "New favorite: No: Who will Taylor Swift's bridesmai... (64%)" over ten people all
# rendering 0%. `_no` is the leg of Zoë Kravitz's own sub-market.
_ZOE = "0xeda9eb14a054e234a72ab94dc45a6302ca702a6a8e5e7c270e7c91628ac8e084"


# ── the source-derived half: which outcome columns do the feed paths read? ────


def _feed_function(name: str) -> ast.AST:
    """Return the AST of one feed scorer, or RAISE.

    A scan that cannot find its subject must fail loudly. Returning "no reads
    found" would let this whole file pass while measuring nothing — the exact way
    a source-derived guard goes vacuous.
    """
    tree = ast.parse(_FEED_PY.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(
        f"{name} not found in {_FEED_PY}. This guard cannot report on a function it "
        f"cannot locate — if the function was renamed, rename it here too."
    )


def _outcome_columns_read_by(name: str) -> set[str]:
    """Outcome COLUMNS read on the outcome loop/lambda variables inside one scorer.

    Filtered through the live mapper rather than a hand-written denylist: of the
    attributes read on `o`/`outcome`, keep the ones that are real
    `FuturesOutcome` columns. That drops `o.get(...)` on same-named dict
    variables without anyone maintaining a list of exceptions, and it means a
    column RENAMED on the model silently leaves the read set — which the
    non-vacuity assertion below is here to catch.
    """
    from app.models.models import FuturesOutcome

    mapped = {c.key for c in sa_inspect(FuturesOutcome).mapper.column_attrs}
    reads = set()
    for node in ast.walk(_feed_function(name)):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in {"o", "outcome"}
        ):
            reads.add(node.attr)
    return reads & mapped


def test_the_read_scan_is_not_vacuous():
    """If the scan stops finding reads, every other assertion here passes for free.

    Pinned on `external_id` specifically: it is the column CERT-622 was about, so
    a scan that no longer sees it is a scan that no longer sees this bug.
    """
    for name in _FEED_SCORERS:
        reads = _outcome_columns_read_by(name)
        assert len(reads) >= 5, f"{name}: scan found only {sorted(reads)} — it has stopped working"
        assert "external_id" in reads, (
            f"{name} no longer reads `external_id`. If the Q480 duplicate-leg filter was "
            f"removed, delete this guard deliberately; do not let it pass by absence."
        )


# ── the measured half: which outcome columns does the real loader return? ─────


@pytest.fixture()
def loaded_market():
    """A real ORM market loaded through the REAL production option list.

    Returns the market DETACHED from its session, so any column the projection
    omitted raises on read instead of quietly lazy-loading — the synchronous
    stand-in for `MissingGreenlet` at the async boundary.
    """
    from app.models.models import Base, FuturesMarket, FuturesOutcome, Sport
    from app.routes.feed import _futures_feed_load_options

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[Sport.__table__, FuturesMarket.__table__, FuturesOutcome.__table__],
    )

    with Session(engine) as s:
        s.add(
            FuturesMarket(
                id=12194657,
                name="Who will Taylor Swift's bridesmaids be?",
                source="polymarket",
                external_id="0xparent",
                status="open",
            )
        )
        # The contaminated shape: one condition present three times.
        s.add_all(
            [
                FuturesOutcome(
                    id=84318324,
                    market_id=12194657,
                    name="No",
                    external_id=f"{_ZOE}_no",
                    current_probability=0.645,
                ),
                FuturesOutcome(
                    id=84318323,
                    market_id=12194657,
                    name="Yes",
                    external_id=f"{_ZOE}_yes",
                    current_probability=0.355,
                ),
                FuturesOutcome(
                    id=69789474,
                    market_id=12194657,
                    name="Gigi Hadid",
                    external_id="0xdc73650886" + "a" * 54,
                    current_probability=0.0035,
                ),
                FuturesOutcome(
                    id=69789475,
                    market_id=12194657,
                    name="Zoë Kravitz",
                    external_id=_ZOE,
                    current_probability=0.0005,
                ),
            ]
        )
        s.commit()

    with Session(engine) as s:
        market = (
            s.execute(
                select(FuturesMarket)
                .options(*_futures_feed_load_options())
                .where(FuturesMarket.id == 12194657)
            )
            .scalars()
            .unique()
            .one()
        )
        # Force the selectinload to run while the session is still live, exactly as
        # the route does, then detach.
        outcomes = list(market.outcomes)
        assert outcomes, "fixture built no outcomes"
        s.expunge_all()

    return market


@pytest.mark.parametrize("scorer", _FEED_SCORERS)
def test_the_projection_loads_every_outcome_column_that_scorer_reads(scorer, loaded_market):
    """reads ⊆ loaded, with `loaded` measured by running the real loader."""
    outcome = next(iter(loaded_market.outcomes))
    unloaded = set(sa_inspect(outcome).unloaded)

    missing = sorted(_outcome_columns_read_by(scorer) & unloaded)

    assert not missing, (
        f"{scorer} reads {missing} on FuturesOutcome, but "
        f"`_futures_feed_load_options()` does not load "
        f"{'it' if len(missing) == 1 else 'them'}. Under async SQLAlchemy that read "
        f"is a lazy load and raises MissingGreenlet inside the per-item serializer — "
        f"Discover serves zero futures cards and Sports degrades to a partial feed "
        f"(gotcha #42). Add the column to the projection, not a getattr() guard: "
        f"`getattr(o, 'x', None)` TRIGGERS the lazy load and then raises."
    )


def test_the_card_still_builds_when_the_market_is_detached(loaded_market):
    """The served shape: run the real display pipeline and get a real card out.

    This is the assertion that would have failed on `be459eae`. The market is
    detached, so `o.external_id` inside the Q480 filter raises unless the
    projection actually loaded it — the same way the async boundary raises — and
    the pipeline produces nothing at all rather than one bad row.
    """
    from app.utils.duplicate_condition_outcomes import drop_duplicate_legs

    sorted_outcomes = sorted(
        drop_duplicate_legs(loaded_market.outcomes, lambda o: o.external_id),
        key=lambda o: float(o.current_probability) if o.current_probability else 0,
        reverse=True,
    )
    card = [
        {"name": o.name, "probability": float(o.current_probability or 0)}
        for o in sorted_outcomes[:10]
    ]

    assert card, "the futures card came back EMPTY — this is the pool-emptying bug"
    # And it is the right card: the leg is gone and a person is crowned.
    assert card[0]["name"] == "Gigi Hadid", f"leader is {card[0]['name']!r}, expected a person"
    assert {"Yes", "No"}.isdisjoint({o["name"] for o in card}), (
        f"a duplicate Yes/No leg survived into the served card: {card}"
    )


# ── the anchor: both bodies must keep using the shared factory ────────────────


@pytest.mark.parametrize("scorer", _FEED_SCORERS)
def test_the_scorer_takes_its_options_from_the_shared_factory(scorer):
    """Anchored on the scorer's OWN body.

    Two byte-identical inline copies is what produced CERT-622: the read landed at
    both call sites and the column at neither. A module-wide
    `"_futures_feed_load_options" in source` check would be satisfied by the other
    scorer, so this walks only this function's own AST.
    """
    fn = _feed_function(scorer)
    calls = {
        node.func.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_futures_feed_load_options" in calls, (
        f"{scorer} no longer calls `_futures_feed_load_options()`. If its loader "
        f"projection was inlined again, the two feed paths can drift apart once more "
        f"— that drift IS CERT-622."
    )

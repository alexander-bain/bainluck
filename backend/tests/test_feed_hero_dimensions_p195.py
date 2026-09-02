"""The feed must SERVE the hero's true pixel dimensions, on BOTH futures paths.

LAT-P195 (#2614). `image_width`/`image_height` are stored at ingest and
backfilled, but a column nobody serves is a column nobody can use: CERT-709
blocked the storage half for exactly that, because at that SHA no route exposed
the fact and no client consumed it. This file guards the wire.

Three separate ways to get it wrong, and each gets its own guard because each
fails differently:

1. **The projection.** A column read by the serializer but absent from
   `_futures_feed_load_options()` is a lazy load, and a lazy load under async
   SQLAlchemy raises `MissingGreenlet` INSIDE the per-item serializer — which
   empties the WHOLE futures pool rather than dropping one card (gotcha #42,
   #1698, CERT-622). Note that the defensive `getattr(market, ..., None)` in
   the serializer does NOT save you here: getattr TRIGGERS the load and then
   raises. Only the projection prevents it, so only the projection is the fix.
   This is MEASURED — the real option list is run through SQLAlchemy's real
   loader and the mapper is asked what came back — never parsed out of source.

2. **One path only.** There are two futures serializers, Discover's and
   Sports'. #1698 and CERT-622 were both "landed on one, missed the other", so
   the key assertion is made against EACH serializer's own AST body. A
   module-wide substring check would be satisfied by either one alone, which is
   the sibling-call-site trap that makes a containment guard vacuous.

3. **Serving a key that is always absent.** A payload that omits the key when
   it is null is indistinguishable to the client from an old build. The
   contract is "always present, sometimes null", so the client can tell "not
   measured yet" from "this deploy predates the field".
"""

from __future__ import annotations

import ast
import inspect

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.models import FuturesMarket

HERO_DIMENSION_COLUMNS = ("image_width", "image_height")

# The two futures feed paths. Both carry a serializer; both must serve the keys.
FEED_SCORERS = ("_score_futures", "_score_sports_mode_futures")


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@pytest.mark.parametrize("column", HERO_DIMENSION_COLUMNS)
def test_the_column_is_real_and_nullable(column):
    """The premise. Nullable is not incidental — it is the ship's safety margin.

    The backfill drains over days, so most rows are NULL for most of that time.
    Every consumer is required to read NULL as "carry on exactly as before", and
    a NOT NULL column with a default would destroy that signal by making
    "unmeasured" indistinguishable from "measured as the default".
    """
    mapper = sa_inspect(FuturesMarket)
    assert column in mapper.columns, f"{column} is not a mapped column"
    assert mapper.columns[column].nullable, (
        f"{column} must stay nullable — NULL is how a consumer knows the photo "
        f"has not been measured yet and must fall back to its old behaviour"
    )


@pytest.fixture
def detached_market():
    """A real ORM market loaded through the REAL production option list.

    Detached, so a column the projection omitted raises on read instead of
    quietly lazy-loading — the synchronous stand-in for `MissingGreenlet`.
    A duck-typed double cannot have a projection, so a double cannot have this
    bug; that is why this fixture refuses to use one.
    """
    from app.models.models import Base, FuturesOutcome, Sport
    from app.routes.feed import _futures_feed_load_options

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[Sport.__table__, FuturesMarket.__table__, FuturesOutcome.__table__],
    )
    with Session(engine) as s:
        s.add(
            FuturesMarket(
                id=555001,
                name="Who wins the US Open?",
                source="kalshi",
                external_id="hero-dims",
                status="open",
                image_url="https://images.pexels.com/photos/1/x.jpg?h=350",
                image_width=525,
                image_height=350,
            )
        )
        s.commit()

    with Session(engine) as s:
        market = (
            s.execute(
                select(FuturesMarket)
                .options(*_futures_feed_load_options())
                .where(FuturesMarket.id == 555001)
            )
            .scalars()
            .unique()
            .one()
        )
        s.expunge_all()
    return market


@pytest.mark.parametrize("column", HERO_DIMENSION_COLUMNS)
def test_the_shared_projection_actually_loads_the_column(column, detached_market):
    """MEASURED, by asking the mapper what the real loader returned."""
    unloaded = set(sa_inspect(detached_market).unloaded)
    assert column not in unloaded, (
        f"`_futures_feed_load_options()` does not load {column}, which the "
        f"serializer reads. Under async that read is a lazy load and raises "
        f"MissingGreenlet inside the per-item serializer — Discover serves ZERO "
        f"futures cards and Sports degrades to a partial feed (gotcha #42). Add "
        f"the column to the projection; a getattr() guard does NOT help, because "
        f"getattr triggers the load before it can return its default."
    )


@pytest.mark.parametrize("column", HERO_DIMENSION_COLUMNS)
def test_the_detached_market_can_be_read_without_raising(column, detached_market):
    """The behaviour behind the projection assertion, not a restatement of it.

    If the column were unprojected this read is the exact operation that raises
    in production. Asserting the VALUE also proves the loader returned the real
    stored number rather than a default.
    """
    assert getattr(detached_market, column) == {"image_width": 525, "image_height": 350}[column]


def _serializer_dict_keys(scorer: str) -> set[str]:
    """Every string key in every dict literal inside one scorer's own body.

    Anchored on the function, not the module: the two serializers are near-
    copies, and a module-wide search is satisfied by whichever one already has
    the key — the precise way #1698 shipped fixed on one path and broken on the
    other.
    """
    from app.routes import feed

    tree = ast.parse(inspect.getsource(feed))
    fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == scorer
        ),
        None,
    )
    assert fn is not None, (
        f"{scorer} not found in app/routes/feed.py — this guard cannot report on "
        f"a function it cannot locate, so it fails rather than passing vacuously"
    )
    return {
        key.value
        for node in ast.walk(fn)
        if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


@pytest.mark.parametrize("scorer", FEED_SCORERS)
@pytest.mark.parametrize("column", HERO_DIMENSION_COLUMNS)
def test_each_serializer_serves_the_hero_dimensions(scorer, column):
    keys = _serializer_dict_keys(scorer)
    assert "image_url" in keys, (
        f"{scorer} no longer serves image_url — re-point this guard, it is "
        f"anchored on the serializer that carries the hero photo"
    )
    assert column in keys, (
        f"{scorer} serves image_url but not {column}. The hero ladder can only "
        f"use the pixels the photo really has if this path serves them, and a "
        f"column served on Discover but not Sports is the #1698/CERT-622 shape: "
        f"fixed on one surface, silently missing on the other."
    )


@pytest.mark.parametrize("scorer", FEED_SCORERS)
def test_the_dimensions_are_served_unconditionally_not_only_when_known(scorer):
    """"Always present, sometimes null" — absence must not be the null signal.

    A key omitted when the value is null reads to the client exactly like a
    build from before the field existed, and the client's fallback keys on
    absence. Serving the key with a null value is what keeps those two facts
    distinguishable while the backfill drains.
    """
    from app.routes import feed

    tree = ast.parse(inspect.getsource(feed))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == scorer
    )
    for node in ast.walk(fn):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and key.value in HERO_DIMENSION_COLUMNS):
                continue
            assert not isinstance(value, ast.IfExp), (
                f"{scorer} serves {key.value} conditionally. Null means 'not "
                f"measured yet'; an ABSENT key means 'this build predates the "
                f"field'. Collapsing the two takes the fallback signal away."
            )

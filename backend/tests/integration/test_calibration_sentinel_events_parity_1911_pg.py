"""#1911 parity — the sentinel's events PUBLISHED aggregate is the curve's own admission.

PILLAR: TRUTH. SHIP: Accuracy alerts describe what the published chart actually
includes, with unproved comparisons explicitly UNKNOWN.

CERT-4150 and Root (2026-10-16) executed the curve's ``events_sql`` beside the
sentinel's ``_EVENTS_MINING_SQL`` over typed rows: a tied non-soccer game and a
terminal 1.0/0.0 price were counted by the sentinel as PUBLISHED (200) while the
curve admits none of them (0), and the alert then claimed "users see it". The
sentinel's published aggregate now carries the curve's two-way admission rule.

This runs BOTH real SQL strings — the curve's extracted from
``precompute_calibration.py`` by AST, never re-typed — over the same rows, in a
read-only transaction, and requires the published n, winners and probability
sum to agree case by case. A future edit to either side that breaks parity is
red here, not discovered from a mis-labelled alert.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``.
"""

from __future__ import annotations

import ast
import os
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #1911 events parity gate",
    ),
]

ROOT = Path(__file__).resolve().parents[2]


def _curve_events_sql() -> str:
    """The curve's ``events_sql`` text, taken from the source by AST."""
    src = (ROOT / "app" / "tasks" / "precompute_calibration.py").read_text()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "events_sql" for t in node.targets
        ):
            for inner in ast.walk(node.value):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str) and "SELECT" in inner.value:
                    return inner.value
    raise AssertionError("events_sql not found in precompute_calibration.py")


def _rows_prefix() -> str:
    return """WITH sports(id, key) AS (
        VALUES (1, 'icehockey_nhl'::text), (2, 'soccer_epl'::text)
    ), events AS (
        SELECT v.* FROM (VALUES (
            CAST(:sport_id AS int), 'completed'::text,
            CAST(:hs AS int), CAST(:aws AS int),
            CAST(:hp AS float), CAST(:ap AS float),
            NULL::float, NULL::float,
            CAST(:commence AS timestamptz), CAST(:period AS text), NULL::jsonb
        )) AS v(sport_id, status, home_score, away_score,
                opening_home_probability, opening_away_probability,
                closing_home_probability, closing_away_probability,
                commence_time, period, box_score_data)
        CROSS JOIN generate_series(1, 100)
    ) """


async def _both(session, **case):
    import importlib

    from app.utils.soccer_three_way import SOCCER_THREE_WAY_PARAMS

    # The MODULE, not `from app.tasks import calibration_sentinel`: the package
    # re-exports a Celery task under that name.
    cs = importlib.import_module("app.tasks.calibration_sentinel")

    params = dict(SOCCER_THREE_WAY_PARAMS, **case)
    await session.execute(text("SET TRANSACTION READ ONLY"))
    scan = (await session.execute(
        text(_rows_prefix() + cs._EVENTS_MINING_SQL.replace("WITH ev AS (", ", ev AS (", 1)),
        params,
    )).mappings().all()
    curve = (await session.execute(text(_rows_prefix() + _curve_events_sql()), params)).mappings().all()
    await session.rollback()
    return scan, curve


def _sum(rows, key):
    return sum(float(r[key] or 0) for r in rows)


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    async with async_sessionmaker(engine)() as s:
        yield s
    await engine.dispose()


def _cases():
    from app.utils.soccer_three_way import SOCCER_THREE_WAY_PARAMS as P

    since = P["soccer_three_way_since"]
    after, before = since + timedelta(days=1), since - timedelta(days=1)
    reg = P["soccer_regulation_period"]
    return [
        # name, sport, home, away, p_home, p_away, commence, period, raw_n, published_n
        ("valid_control", 1, 2, 1, 0.6, 0.4, after, None, 200, 200),
        ("tied_non_soccer", 1, 1, 1, 0.6, 0.4, after, None, 200, 0),
        ("terminal_prices", 1, 2, 1, 1.0, 0.0, after, None, 200, 0),
        ("one_side_terminal", 1, 2, 1, 0.99, 0.0, after, None, 200, 100),
        ("soccer_two_way", 2, 2, 1, 0.6, 0.3, before, None, 200, 0),
        ("soccer_three_way", 2, 1, 1, 0.45, 0.30, after, reg, 300, 300),
    ]


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c[0])
async def test_published_events_are_what_the_curve_admits(session, case):
    name, sport, hs, aws, hp, ap, commence, period, raw_n, published_n = case
    scan, curve = await _both(
        session, sport_id=sport, hs=hs, aws=aws, hp=hp, ap=ap,
        commence=commence, period=period,
    )
    assert int(_sum(scan, "n")) == raw_n, (name, "raw accounting is unchanged")
    assert int(_sum(curve, "n")) == published_n, (name, "the curve's own count")
    assert int(_sum(scan, "pub_n")) == published_n, (name, scan)
    assert int(_sum(scan, "pub_winners")) == int(_sum(curve, "winners")), name
    assert _sum(scan, "pub_sum_prob") == pytest.approx(_sum(curve, "sum_prob")), name


async def test_the_union_coverage_is_unchanged_by_the_parity_rule(session):
    """Raw mining and the union coverage stay as they were: a tie is not a new
    known exclusion class, only a row the published aggregate does not hold."""
    scan, _ = await _both(
        session, sport_id=1, hs=1, aws=1, hp=0.6, ap=0.4,
        commence=_cases()[0][6], period=None,
    )
    assert int(_sum(scan, "any_known_n")) == 0 and int(_sum(scan, "soccer_2way_n")) == 0

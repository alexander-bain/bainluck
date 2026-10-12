"""#1011 — soccer accuracy graded three-way, proved on ROWS in real Postgres.

WHAT IS UNDER TEST
------------------
Since release v4636 (2026-09-16T17:43:41Z) a soccer sportsbook pair keeps the
draw as ``1 - home - away``. Three statements now read that contract, and each
one is executed here against seeded rows rather than asserted as a string:

* the events curve (``events_sql`` inside ``compute_calibration_payload``):
  soccer reaches it only through a three-way branch reading the last
  pre-kickoff consensus pair, drawn matches included;
* the soccer exclusion count (``soccer_2way_sql``): a match the three-way
  branch grades is no longer counted as excluded;
* the per-sportsbook soccer slice (``_BOOKMAKER_SOCCER_THREE_WAY_CHUNK_SQL``):
  the LAST pre-kickoff reading per (match, book), proven three-way, cutoff on
  both kickoff and capture;
* and the drill-down sample (``/api/calibration/examples``), which must draw a
  soccer bucket's examples from the same rows — Draw included.

THE ORACLE IS AN INVARIANT, NOT A COPY
--------------------------------------
A three-way reading's three probabilities sum to 1 and exactly one of its three
outcomes wins. So for any set of admitted readings: ``n = 3k``, ``winners = k``
and ``sum_prob = k``. A statement that read the CLOSING pair (whose away leg is
``1 - home``), dropped drawn matches, admitted a two-way pair, or graded a
draw as two losses breaks at least one of those three equalities — which is why
the seed carries each of those shapes beside the admitted ones.

Pair values for the admitted matches come from the REAL writer
(``odds_polling._parse_snapshot_values``) on provider-shaped boards, so the
contract is tested against what the writer stores.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` and NAMED IN ``ci.yml``: a PG-gated file
no workflow step invokes skips silently while pytest still exits 0.
"""

from __future__ import annotations

import inspect
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #1011 contract",
    ),
]

SINCE = datetime(2026, 9, 16, 17, 43, 41, tzinfo=timezone.utc)
AFTER = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
BEFORE = datetime(2026, 9, 10, 15, 0, tzinfo=timezone.utc)
SOCCER_SPORT, NBA_SPORT = 910111, 910112


def _writer_pair(home_price, away_price, draw_price):
    """What the sportsbook writer stores for one book's three-way board."""
    from app.tasks.odds_polling import _parse_snapshot_values

    values = _parse_snapshot_values(
        {"key": "draftkings", "markets": [{"key": "h2h", "outcomes": [
            {"name": "Home FC", "price": home_price},
            {"name": "Away FC", "price": away_price},
            {"name": "Draw", "price": draw_price}]}]},
        {"home_team": "Home FC", "away_team": "Away FC", "sport_key": "soccer_epl"},
    )
    return values["home_win_probability"], values["away_win_probability"]


H1 = _writer_pair(120, 230, 250)     # St Gallen v Sion's board
H2 = _writer_pair(175, 160, 210)     # an even match: the draw is large
H3 = _writer_pair(300, -110, 270)

#: (id, sport, kickoff, status, home, away, opening pair, closing pair).
#: The closing pair is written the way ``_backfill_closing_lines`` writes it —
#: one book's last home leg, away = 1 - home — and its home leg differs from the
#: consensus median, so a statement that read EITHER closing leg would break the
#: sum invariant.
EVENTS = [
    # admitted: home win, draw, away win
    (9101101, SOCCER_SPORT, AFTER, "completed", 2, 1, H1, (0.45, 0.55)),
    (9101102, SOCCER_SPORT, AFTER + timedelta(days=1), "completed", 1, 1, H2, None),
    (9101103, SOCCER_SPORT, AFTER + timedelta(days=2), "closed", 0, 2, H3,
     (0.24, 0.76)),
    # excluded: kicked off before v4636 (a renormalized two-way pair)
    (9101104, SOCCER_SPORT, BEFORE, "completed", 2, 0, (0.6, 0.4), (0.6, 0.4)),
    # excluded by the CUTOFF alone: its pair keeps the draw, but the match
    # kicked off before v4636 (synthetic — it proves the date clause bites on
    # its own, not only through the shape test)
    (9101109, SOCCER_SPORT, BEFORE, "completed", 1, 0, H1, None),
    # excluded: after the cutoff but two-way-shaped — the draw is not in it
    (9101105, SOCCER_SPORT, AFTER + timedelta(days=3), "completed", 3, 1,
     (0.65, 0.35), None),
    # excluded: not finished
    (9101106, SOCCER_SPORT, AFTER, "scheduled", 1, 1, H2, None),
    # control: a two-way sport keeps its existing arm
    (9101107, NBA_SPORT, AFTER, "completed", 110, 100, (0.69, 0.31), (0.7, 0.3)),
    # excluded from the per-book slice: kicked off just after the cutoff, but
    # its only reading was captured before the release
    (9101108, SOCCER_SPORT, SINCE + timedelta(hours=1), "completed", 2, 0, None, None),
]

#: (event id, bookmaker, captured_at, home, away).
SNAPSHOTS = [
    (9101101, "draftkings", AFTER - timedelta(hours=2), *H1),
    # fanduel: an earlier three-way reading, then a LATER two-way-shaped one.
    # The last reading decides, so this book is skipped — never replaced by
    # the earlier reading.
    (9101101, "fanduel", AFTER - timedelta(hours=5), *H1),
    (9101101, "fanduel", AFTER - timedelta(hours=1), 0.6, 0.4),
    # betmgm: its last PRE-kickoff reading counts; the in-play one does not.
    (9101101, "betmgm", AFTER - timedelta(hours=3), *H1),
    (9101101, "betmgm", AFTER + timedelta(minutes=10), 0.9, 0.04),
    (9101102, "draftkings", AFTER + timedelta(days=1) - timedelta(hours=2), *H2),
    (9101104, "draftkings", BEFORE - timedelta(hours=2), *H1),
    (9101105, "draftkings", AFTER + timedelta(days=3) - timedelta(hours=2), 0.65, 0.35),
    (9101108, "draftkings", SINCE - timedelta(hours=1), *H1),
]


@pytest.fixture
async def pg_engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await _seed(conn)
    yield engine
    await engine.dispose()


async def _seed(conn):
    """Raw INSERTs, every NOT NULL column named (``sports.active`` and
    ``odds_snapshots.reading_count`` carry only client-side defaults)."""
    for sid, key in ((SOCCER_SPORT, "soccer_epl"), (NBA_SPORT, "basketball_nba")):
        await conn.execute(
            text("INSERT INTO sports (id, key, name, active) "
                 "VALUES (:id, :key, :key, true)"),
            {"id": sid, "key": key},
        )
    for eid, sid, kickoff, status, hs, as_, opening, closing in EVENTS:
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
                "commence_time, status, home_score, away_score, "
                "opening_home_probability, opening_away_probability, "
                "closing_home_probability, closing_away_probability) "
                "VALUES (:id, :sid, 'Home FC', 'Away FC', :ko, :st, :hs, :as_, "
                ":oh, :oa, :ch, :ca)"
            ),
            {"id": eid, "sid": sid, "ko": kickoff, "st": status, "hs": hs, "as_": as_,
             "oh": opening[0] if opening else None,
             "oa": opening[1] if opening else None,
             "ch": closing[0] if closing else None,
             "ca": closing[1] if closing else None},
        )
    for eid, book, captured, home, away in SNAPSHOTS:
        await conn.execute(
            text(
                "INSERT INTO odds_snapshots (event_id, bookmaker, captured_at, "
                "home_win_probability, away_win_probability, reading_count) "
                "VALUES (:e, :b, :c, :h, :a, 1)"
            ),
            {"e": eid, "b": book, "c": captured, "h": home, "a": away},
        )


def _build_sql(name: str):
    """The statement exactly as ``compute_calibration_payload`` builds it."""
    import app.tasks.precompute_calibration as pc

    src = inspect.getsource(pc.compute_calibration_payload)
    marker = f'{name} = text("""'
    assert src.count(marker) == 1, name
    body = src.split(marker, 1)[1].split('""")', 1)[0]
    return text(body).bindparams(**pc.SOCCER_THREE_WAY_PARAMS)


def _three_way_invariant(rows, category):
    mine = [r for r in rows if r.category == category]
    n = sum(int(r.n) for r in mine)
    winners = sum(int(r.winners) for r in mine)
    sum_prob = sum(float(r.sum_prob) for r in mine)
    return n, winners, sum_prob


async def test_the_events_curve_grades_admitted_soccer_three_way(pg_engine):
    async with pg_engine.connect() as conn:
        rows = (await conn.execute(_build_sql("events_sql"))).all()

    n, winners, sum_prob = _three_way_invariant(rows, "soccer_epl")
    # Exactly the three admitted matches: 3 outcomes each, one winner each, and
    # each reading's probabilities sum to 1.
    assert (n, winners) == (9, 3)
    assert sum_prob == pytest.approx(3.0, abs=1e-6)

    # The drawn match's draw is a graded WIN in its bucket.
    draw = 1 - H2[0] - H2[1]
    draw_bucket = [r for r in rows
                   if r.category == "soccer_epl" and r.bucket_idx == int(draw * 10)]
    assert draw_bucket and sum(int(r.winners) for r in draw_bucket) >= 1

    # Control: the two-way arm is unchanged for other sports (closing preferred).
    nba = [r for r in rows if r.category == "basketball_nba"]
    assert sum(int(r.n) for r in nba) == 2
    assert sum(int(r.winners) for r in nba) == 1
    assert sum(float(r.sum_prob) for r in nba) == pytest.approx(1.0)


async def test_the_exclusion_count_no_longer_counts_admitted_matches(pg_engine):
    async with pg_engine.connect() as conn:
        excluded = (await conn.execute(_build_sql("soccer_2way_sql"))).scalar()
    # Legacy two-way eligibility (non-drawn, a price present): 9101101, 9101103,
    # 9101104, 9101105, 9101109 -> 10 outcomes. The two graded three-way leave
    # the count; the pre-cutoff 9101109 stays in it.
    assert excluded == 6


async def test_the_per_book_slice_reads_the_last_proven_three_way_reading(pg_engine):
    import app.tasks.backfill_winners as bw
    from app.utils.soccer_three_way import SOCCER_THREE_WAY_PARAMS

    async with pg_engine.connect() as conn:
        rows = (await conn.execute(
            text(bw._BOOKMAKER_SOCCER_THREE_WAY_CHUNK_SQL),
            {**SOCCER_THREE_WAY_PARAMS, "category": "soccer_epl",
             "lo": datetime(2026, 9, 1, tzinfo=timezone.utc),
             "hi": datetime(2026, 11, 1, tzinfo=timezone.utc)},
        )).all()
        grid = (await conn.execute(
            text(bw._BOOKMAKER_SOCCER_THREE_WAY_GRID_SQL), SOCCER_THREE_WAY_PARAMS,
        )).all()

    n, winners, sum_prob = _three_way_invariant(rows, "soccer_epl")
    # draftkings + betmgm on 9101101, draftkings on the drawn 9101102. Not
    # fanduel (last reading two-way-shaped), not betmgm's in-play reading, not
    # the pre-cutoff match, not 9101108's pre-release reading.
    assert (n, winners) == (9, 3)
    assert sum_prob == pytest.approx(3.0, abs=1e-6)
    assert {r.category for r in rows} == {"soccer_epl"}
    # The grid keeps a month whose match was drawn and only names soccer.
    assert {(c.category, c.bucket_start.month) for c in grid} == {
        ("soccer_epl", 9)}


async def test_the_drill_down_samples_the_same_rows_draw_included(pg_engine):
    from sqlalchemy.ext.asyncio import AsyncSession

    import app.routes.calibration as rc

    rc._examples_cache.clear()
    draw = 1 - H2[0] - H2[1]
    async with AsyncSession(pg_engine) as session:
        result = await rc.calibration_examples(
            db=session, source="odds_api", bucket=int(draw * 10),
            well_traded=1, limit=10,
        )
    names = {(e["outcome_name"], e["result"]) for e in result["examples"]}
    assert ("Draw", "Yes") in names
    # Nothing from the two-way-shaped or pre-cutoff matches is sampled.
    prices = {e["price"] for e in result["examples"]}
    assert round(1 - 0.6 - 0.4, 4) not in prices

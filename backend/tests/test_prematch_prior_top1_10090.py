"""#10090 — the pre-match miss read is a per-source top-1, behind an off switch.

`PREMATCH_PRIOR_TOP1_SQL` asks for each (game, source) the newest row at or
before the cutoff with `ORDER BY captured_at DESC, id DESC LIMIT 1`, so the read
is one backward seek of `ix_winprob_event_source_captured` instead of a walk of
every snapshot the game has. These are the unit guards: what the switch selects,
that both execute paths use it, that the rollback is the old statement byte for
byte, and that flipping it leaves the cache keys alone. The row-for-row truth
gate is real Postgres: `tests/integration/test_prematch_prior_lateral_equivalence_pg.py`.
"""

import hashlib
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.utils.prematch_reading as pr
from app.utils.prematch_reading import (
    PREMATCH_PRIOR_SQL,
    PREMATCH_PRIOR_TOP1_SQL,
    fetch_prematch_prior_rows,
    prematch_prior_share_key,
    prematch_prior_sql,
)

_KICK = datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)

#: Today's statement, copied as it ran before this change. The rollback must
#: be these bytes, not a tidied equivalent.
_WALK_AS_SHIPPED = """
    SELECT x.event_id, x.source,
           x.home_win_probability, x.away_win_probability, x.draw_probability
    FROM unnest(cast(:ids as integer[]), cast(:cutoffs as timestamptz[]))
         AS t(event_id, cutoff)
    CROSS JOIN LATERAL (
        SELECT DISTINCT ON (s.source)
               s.event_id, s.source,
               s.home_win_probability, s.away_win_probability,
               s.draw_probability
        FROM win_prob_snapshots s
        WHERE s.event_id = t.event_id
          AND s.source = ANY(:sources)
          AND s.home_win_probability IS NOT NULL
          AND s.captured_at <= t.cutoff
        ORDER BY s.source, s.captured_at DESC
    ) x
"""


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("PREMATCH_PRIOR_TOP1", raising=False)
    monkeypatch.delenv("PREMATCH_READING_CACHE", raising=False)
    monkeypatch.setenv("PREMATCH_READING_CACHE_SHARED", "0")
    monkeypatch.setattr(pr, "_utcnow", lambda: _KICK + timedelta(days=1))
    pr._reset_prematch_cache_for_tests()
    yield
    pr._reset_prematch_cache_for_tests()


def test_the_rollback_is_todays_statement_byte_for_byte():
    assert PREMATCH_PRIOR_SQL == _WALK_AS_SHIPPED


def test_the_switch_defaults_on_and_every_off_spelling_restores_the_walk(monkeypatch):
    assert prematch_prior_sql() == PREMATCH_PRIOR_TOP1_SQL
    for on in ("1", "true", "yes", "on", ""):
        monkeypatch.setenv("PREMATCH_PRIOR_TOP1", on)
        assert prematch_prior_sql() == PREMATCH_PRIOR_TOP1_SQL, on
    for off in ("0", "false", "no", "off", " OFF "):
        monkeypatch.setenv("PREMATCH_PRIOR_TOP1", off)
        assert prematch_prior_sql() == PREMATCH_PRIOR_SQL, off


def test_the_top1_takes_the_same_binds_and_keeps_the_semantics_inside_the_limit():
    placeholders = lambda sql: set(re.findall(r"(?<!:):(\w+)", sql))  # noqa: E731
    assert placeholders(PREMATCH_PRIOR_TOP1_SQL) == placeholders(PREMATCH_PRIOR_SQL)
    assert placeholders(PREMATCH_PRIOR_TOP1_SQL) == {"ids", "cutoffs", "sources"}

    inner = PREMATCH_PRIOR_TOP1_SQL.split("CROSS JOIN LATERAL", 1)[1]
    inner = inner.split("LIMIT 1", 1)[0]
    assert "s.home_win_probability IS NOT NULL" in inner
    assert "s.captured_at <= t.cutoff" in inner
    assert "ORDER BY s.captured_at DESC, s.id DESC" in inner
    assert "SELECT DISTINCT u.src" in PREMATCH_PRIOR_TOP1_SQL
    assert "WHERE u.src IS NOT NULL" in PREMATCH_PRIOR_TOP1_SQL
    assert PREMATCH_PRIOR_TOP1_SQL.rstrip().endswith("ORDER BY t.ord, x.source")
    # #6277: the draw rides the one row, and is not in the NOT NULL guard.
    assert PREMATCH_PRIOR_TOP1_SQL.count("draw_probability") == 2
    assert "draw_probability IS NOT NULL" not in PREMATCH_PRIOR_TOP1_SQL


class _RecordingDb:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, stmt, params):
        self.statements.append(str(stmt))
        rows = [
            SimpleNamespace(
                event_id=event_id,
                source="kalshi",
                home_win_probability=0.6,
                away_win_probability=0.4,
                draw_probability=None,
            )
            for event_id in params["ids"]
        ]
        return SimpleNamespace(all=lambda: rows)


def _binds(*pairs):
    return {
        "ids": [p[0] for p in pairs],
        "cutoffs": [p[1] for p in pairs],
        "sources": ["kalshi", "polymarket"],
    }


@pytest.mark.parametrize("flag, expected", [("1", "top1"), ("0", "walk")])
@pytest.mark.asyncio
async def test_both_execute_paths_run_the_switched_statement(
    monkeypatch, flag, expected
):
    """The miss read AND the read-as-before bypasses (cache off, misaligned,
    conflicting cutoff) execute whatever the switch selects."""
    want = PREMATCH_PRIOR_TOP1_SQL if expected == "top1" else PREMATCH_PRIOR_SQL
    monkeypatch.setenv("PREMATCH_PRIOR_TOP1", flag)

    db = _RecordingDb()
    await fetch_prematch_prior_rows(db, _binds((1, _KICK)))  # miss path
    await fetch_prematch_prior_rows(  # conflicting cutoff bypass
        db, _binds((2, _KICK), (2, _KICK - timedelta(hours=1)))
    )
    await fetch_prematch_prior_rows(  # misaligned bypass
        db, {"ids": [3, 4], "cutoffs": [_KICK], "sources": ["kalshi"]}
    )
    monkeypatch.setenv("PREMATCH_READING_CACHE", "0")
    await fetch_prematch_prior_rows(db, _binds((5, _KICK)))  # cache off

    assert db.statements == [want] * 4


@pytest.mark.asyncio
async def test_flipping_the_switch_does_not_rotate_the_cache_keys(monkeypatch):
    """The keys name the answer, which both forms give; a flip must not empty
    the shared cache. L1 held under one arm still serves under the other."""
    binds = _binds((1, _KICK))
    on_share = prematch_prior_share_key(binds)
    on_l2 = pr._l2_key((1, _KICK, ("kalshi", "polymarket")))

    db = _RecordingDb()
    await fetch_prematch_prior_rows(db, binds)
    monkeypatch.setenv("PREMATCH_PRIOR_TOP1", "0")
    await fetch_prematch_prior_rows(db, binds)

    assert len(db.statements) == 1
    assert prematch_prior_share_key(binds) == on_share
    assert pr._l2_key((1, _KICK, ("kalshi", "polymarket"))) == on_l2
    assert (
        pr._SQL_DIGEST == hashlib.sha256(PREMATCH_PRIOR_SQL.encode()).hexdigest()[:12]
    )

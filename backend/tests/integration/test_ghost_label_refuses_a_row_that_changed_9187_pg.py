"""#9187 follow-up (CERT-3662 ``9187-CAS-ANCHOR-SCORE-AT-WRITE``), against a real PostgreSQL.

The reschedule/adjacent-day sweep reads a ghost row, reads ESPN's boards, then
labels the ghost ``provenance:duplicate-of:<canonical>``. If ESPN's pass anchors
the row, or a score or status lands on it, between that read and the write, the
label must not land. The guard is SQL (``IS NOT DISTINCT FROM``, ``NULLIF``,
JSONB ``@>``), so a recording session cannot run it — this file does.

A narrow ``events`` table in a private schema, so this runs on the lane VM's
Postgres 14 as well as in CI.
"""
import json
import os

import pytest
from sqlalchemy import text

from app.tasks import mlb_reschedule_ghost_sweep as sweep
from app.utils.mlb_reschedule_ghosts import GhostTag

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9187 "
            "write-guard gate (CI job: search-recall)"
        ),
    ),
]

_SCHEMA = "ghost_label_cas_gate_9187"
GHOST, CANON = 15320181, 15168035
LABEL = f"provenance:duplicate-of:{CANON}"


@pytest.fixture
async def pg():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # search_path is pinned on EVERY pooled connection: the write commits per row,
    # and a commit may hand the session a different connection.
    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": _SCHEMA}}
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
        await s.execute(text(f"CREATE SCHEMA {_SCHEMA}"))
        await s.execute(
            text(
                f"CREATE TABLE {_SCHEMA}.events (id bigint PRIMARY KEY, sport_id int NOT NULL, "
                "home_team_name varchar(200) NOT NULL, away_team_name varchar(200) NOT NULL, "
                "commence_time timestamptz NOT NULL, status varchar(20) NOT NULL, "
                "espn_id varchar(50), home_score int, away_score int, event_tags jsonb)"
            )
        )
        await s.commit()
        yield s
        await s.rollback()
        await s.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
        await s.commit()
    await engine.dispose()


async def _seed(s, *, espn_id=None, home=None, away=None, status="scheduled", tags=None):
    await s.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, espn_id, home_score, away_score, event_tags) "
            "VALUES (:id, 1, 'Vegas Golden Knights', 'Chicago Blackhawks', "
            "'2026-09-30T21:30:10Z', :st, :espn, :h, :a, CAST(:t AS jsonb))"
        ),
        {
            "id": GHOST,
            "espn": espn_id,
            "h": home,
            "a": away,
            "st": status,
            "t": json.dumps(tags if tags is not None else ["provenance:source:odds_api"]),
        },
    )
    await s.commit()


async def _read(s):
    row = (
        await s.execute(
            text("SELECT id, espn_id, home_score, away_score, status, event_tags FROM events")
        )
    ).one()
    return row


async def _move(s, sql):
    """Something else writes the row after the plan read it."""
    await s.execute(text(sql), {"id": GHOST})
    await s.commit()


def _tag():
    return [GhostTag(ghost_id=GHOST, canonical_id=CANON, reason="adjacent_day")]


async def _plan_then_write(s, between=None):
    observed = sweep.observed_state([await _read(s)])
    if between:
        await _move(s, between)
    out = await sweep.write_tags_if_unchanged(s, _tag(), observed)
    return out, (await _read(s)).event_tags


class TestTheLabelLandsOnlyOnTheRowThePlanJudged:
    async def test_the_specimen_unchanged_is_labelled(self, pg):
        await _seed(pg)
        (written, failed, zero), tags = await _plan_then_write(pg)
        assert (written, failed, zero) == (1, [], [])
        assert tags == ["provenance:source:odds_api", LABEL]

    async def test_espn_anchoring_the_row_in_between_refuses(self, pg):
        await _seed(pg)
        (written, failed, zero), tags = await _plan_then_write(
            pg, "UPDATE events SET espn_id = '401891775' WHERE id = :id"
        )
        assert (written, zero) == (0, [GHOST])
        assert LABEL not in tags

    async def test_a_score_landing_in_between_refuses(self, pg):
        await _seed(pg)
        (written, _f, zero), tags = await _plan_then_write(
            pg, "UPDATE events SET home_score = 3, away_score = 2 WHERE id = :id"
        )
        assert (written, zero) == (0, [GHOST])
        assert LABEL not in tags

    async def test_one_side_of_the_score_landing_refuses(self, pg):
        await _seed(pg)
        (written, _f, zero), tags = await _plan_then_write(
            pg, "UPDATE events SET away_score = 1 WHERE id = :id"
        )
        assert (written, zero) == (0, [GHOST])
        assert LABEL not in tags

    async def test_a_status_change_in_between_refuses(self, pg):
        await _seed(pg)
        (written, _f, zero), tags = await _plan_then_write(
            pg, "UPDATE events SET status = 'live' WHERE id = :id"
        )
        assert (written, zero) == (0, [GHOST])
        assert LABEL not in tags

    async def test_an_empty_string_espn_id_reads_as_unanchored_like_the_planner(self, pg):
        # build_rows treats '' as no id; the guard must agree or it refuses a
        # ghost the plan rightly chose.
        await _seed(pg, espn_id="")
        (written, _f, zero), tags = await _plan_then_write(pg)
        assert (written, zero) == (1, [])
        assert LABEL in tags

    async def test_the_postponed_arms_placeholder_zero_zero_is_still_written(self, pg):
        # The postponed arm labels a ghost holding a placeholder 0-0. A guard that
        # demanded NULL scores would refuse it; comparing what was READ does not.
        await _seed(pg, home=0, away=0, status="postponed")
        (written, _f, zero), tags = await _plan_then_write(pg)
        assert (written, zero) == (1, [])
        assert LABEL in tags

    async def test_a_placeholder_turning_into_a_real_score_refuses(self, pg):
        await _seed(pg, home=0, away=0, status="postponed")
        (written, _f, zero), tags = await _plan_then_write(
            pg, "UPDATE events SET home_score = 4 WHERE id = :id"
        )
        assert (written, zero) == (0, [GHOST])
        assert LABEL not in tags

    async def test_a_rerun_does_not_append_twice(self, pg):
        await _seed(pg)
        await _plan_then_write(pg)
        (written, _f, zero), tags = await _plan_then_write(pg)
        assert (written, zero) == (0, [GHOST])
        assert tags.count(LABEL) == 1

    async def test_an_unrelated_tag_write_in_between_does_not_refuse(self, pg):
        # The guard compares identity and result columns only; another rail
        # adding a tag is not a change of evidence.
        await _seed(pg)
        (written, _f, zero), tags = await _plan_then_write(
            pg,
            "UPDATE events SET event_tags = event_tags || '[\"league:nhl\"]'::jsonb "
            "WHERE id = :id",
        )
        assert (written, zero) == (1, [])
        assert tags == ["provenance:source:odds_api", "league:nhl", LABEL]


class TestTheReReadSeparatesARefusalFromAMissedWrite:
    async def test_a_row_anchored_in_between_reads_as_changed(self, pg):
        await _seed(pg)
        observed = sweep.observed_state([await _read(pg)])
        await _move(pg, "UPDATE events SET espn_id = '401891775' WHERE id = :id")
        assert await sweep.changed_since(pg, [GHOST], observed) == [GHOST]

    async def test_an_untouched_row_does_not_read_as_changed(self, pg):
        await _seed(pg)
        observed = sweep.observed_state([await _read(pg)])
        assert await sweep.changed_since(pg, [GHOST], observed) == []

    async def test_a_row_that_is_gone_reads_as_changed(self, pg):
        await _seed(pg)
        observed = sweep.observed_state([await _read(pg)])
        await _move(pg, "DELETE FROM events WHERE id = :id")
        assert await sweep.changed_since(pg, [GHOST], observed) == [GHOST]

    async def test_an_empty_string_id_is_the_same_as_none(self, pg):
        await _seed(pg, espn_id="")
        observed = sweep.observed_state([await _read(pg)])
        await _move(pg, "UPDATE events SET espn_id = NULL WHERE id = :id")
        assert await sweep.changed_since(pg, [GHOST], observed) == []

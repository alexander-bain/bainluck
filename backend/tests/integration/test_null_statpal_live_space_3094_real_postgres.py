"""The #3094 clear's apply/rollback round trip, executed against a REAL PostgreSQL.

## what this gate is for

`scripts/null_statpal_live_space_ids_3094.py` runs unattended under D51, which
grants that only because the repair "writes a backup first and ships a
one-command restore". D51's grant is worth exactly as much as the restore is,
and CERT-847 is the precedent for a restore that reported success while
restoring nothing.

This repair writes to **two places on one row** — the `statpal_fixture_id`
column and the `win_probability_sources->>'statpal_fixture_id'` JSONB key — and
those two halves fail in opposite directions:

* Clear only the column and `_get_statpal_id` (`statpal_sync.py` L1530) still
  returns the stale id through its JSONB fallback. The write-once guard keeps
  firing, the row never re-anchors, and the column reads NULL so the row LOOKS
  repaired. 21 of the 364 production rows are in this shape.
* Restore the JSONB unconditionally and 343 rows get a key they never had — a
  mutation wearing a restore's clothes, which `COUNT_UNRESTORED` is the only
  thing that can see.

## why this gate needs a real server

The claim is a round trip through a JSONB subtraction and a conditional JSONB
reinsert. What has to be observed:

1. **`jsonb - 'key'` removes one key and leaves its siblings.** A mock cannot
   have an opinion about that; only the server's JSONB implementation can.
2. **`jsonb_set` puts back a JSON *string*, not a bare token.** `to_jsonb(text)`
   is the difference between `"1329192623"` and a type error, and it is decided
   by the server's cast.
3. **`IS NOT DISTINCT FROM` over NULLs on both sides.** The post-condition leans
   on three-valued logic in four places; `=` would silently pass every NULL row
   and report a clean undo of nothing.
4. **psycopg2's paramstyle on the real statements.** This drives `apply_clear`
   and `rollback_clear` themselves — not a copy of their SQL — over psycopg2,
   the driver the Heroku one-off dyno uses.

There is no local PostgreSQL in the agent sandbox, so CI is where this runs. The
`search-recall` job provides the container and its "Verify the gate is actually
armed" step is what stops a skipped gate reading as a passing one.

## the corpus, and what each row can fail on

* **`col_only`** — MLB, ten-digit column, and `win_probability_sources` left
  **NULL outright**, not merely keyless. The 343-row majority. Apply must clear
  it; rollback must NOT invent a JSONB key for it. The NULL is load-bearing:
  `jsonb ? key` yields NULL rather than false on a NULL column, so a
  `jsonb_had_key` stored without a COALESCE is NULL, and the post-condition's
  `= b.jsonb_had_key` then goes three-valued and reports this row as
  permanently unrestored straight after a perfect restore. A corpus whose rows
  all carried a JSONB object would miss that entirely.
* **`col_and_jsonb`** — MLB, ten-digit column AND the JSONB key, *alongside two
  sibling keys*. The 21-row case that hides. Apply must clear both halves and
  leave the siblings untouched; a `win_probability_sources = NULL` shortcut
  would destroy the siblings and only this row would notice.
* **`six_digit`** — MLB, six-digit column. The correct shape. No statement may
  read, write, back up or restore it — this is the row that fails if the
  population test is ever loosened to "longer than six" or "not NULL".
* **`nba_seven`** — a seven-digit NBA row. NBA is not in
  `STATPAL_LIVE_ANCHOR_FIELD`; its ids are a different question. A repair whose
  blast radius grew by sport would show up here and nowhere else.
* **`already_null`** — MLB, no id at all. Must stay out of the backup, so that
  rollback cannot hand it someone else's id.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #3094 clear "
        "round trip (CI job `search-recall` provides one)"
    ),
)

BACKUP_TABLE = "events_statpal_live_space_backup_3094"

#: The ten-digit live-space value, and the six-digit schedule-space value it is
#: NOT. Distinct lengths on purpose: the population test is a shape test.
LIVE_ID = "1329192623"
SCHEDULE_ID = "362147"


def _psycopg2_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres://", "postgresql://", 1
    )


@pytest.fixture
def pg_schema():
    """Real Postgres with the real schema, dropped and rebuilt.

    Deliberately SYNCHRONOUS: the subject is a psycopg2 script, so the tests are
    sync functions, and a sync test cannot depend on an async fixture —
    pytest-asyncio hands it an unawaited generator and the schema is silently
    never built.
    """
    from sqlalchemy import create_engine, text

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_engine(_psycopg2_url(DB_URL))
    with engine.begin() as c:
        # Not in the ORM metadata, so `drop_all` leaves it behind and the next
        # run's `CREATE TABLE IF NOT EXISTS` would keep a stale snapshot —
        # exactly the failure the script's docstring warns about.
        c.execute(text(f"DROP TABLE IF EXISTS {BACKUP_TABLE}"))
        Base.metadata.drop_all(c)
        Base.metadata.create_all(c)
    engine.dispose()
    yield


@pytest.fixture
def conn(pg_schema):
    """A psycopg2 connection — the driver the Heroku one-off dyno uses."""
    import psycopg2

    c = psycopg2.connect(_psycopg2_url(DB_URL))
    c.autocommit = False
    yield c
    c.close()


def _seed(cur) -> dict[str, int]:
    """Insert the corpus. Returns `{label: event id}`.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT. `events.home_team_name`,
    `.away_team_name`, `.commence_time` and `.status` are NOT NULL, and
    `.status` carries a **client-side** default the ORM applies and a raw INSERT
    does not — omitting it raises `NotNullViolation` rather than taking the
    default. `tests/test_pg_gate_seed_completeness.py` parses these statements
    against the live ORM metadata; this file is registered there.
    """
    cur.execute(
        "INSERT INTO sports (id, key, name, active) VALUES "
        "(1, 'baseball_mlb', 'MLB', true), "
        "(2, 'basketball_nba', 'NBA', true)"
    )
    commence = datetime(2026, 9, 1, 23, 0, tzinfo=timezone.utc)

    #: `(label, event id, sport id, statpal_fixture_id, win_probability_sources)`
    corpus = (
        ("col_only", 201, 1, LIVE_ID, None),
        (
            "col_and_jsonb",
            202,
            1,
            LIVE_ID[:-1] + "4",
            # The siblings are the point: a `SET win_probability_sources = NULL`
            # shortcut passes every other assertion in this file and destroys
            # these two.
            {
                "statpal_fixture_id": LIVE_ID[:-1] + "4",
                "espn": {"prob": 0.61},
                "statpal_end_time": "2026-09-01T02:10:00+00:00",
            },
        ),
        ("six_digit", 203, 1, SCHEDULE_ID, None),
        ("nba_seven", 204, 2, "4018731", None),
        ("already_null", 205, 1, None, None),
    )

    ids: dict[str, int] = {}
    for label, event_id, sport_id, fixture_id, sources in corpus:
        cur.execute(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, statpal_fixture_id, win_probability_sources) "
            "VALUES (%s, %s, %s, %s, %s, 'completed', %s, %s)",
            (
                event_id,
                sport_id,
                f"Home {label}",
                f"Away {label}",
                commence,
                fixture_id,
                json.dumps(sources) if sources is not None else None,
            ),
        )
        ids[label] = event_id
    return ids


def _rows(cur) -> dict[int, tuple]:
    """`{event id: (statpal_fixture_id, win_probability_sources)}`."""
    cur.execute(
        "SELECT id, statpal_fixture_id, win_probability_sources "
        "FROM events ORDER BY id"
    )
    return {r[0]: (r[1], r[2]) for r in cur.fetchall()}


@needs_postgres
class TestApplyRollbackRoundTrip:
    def test_apply_clears_both_halves_and_rollback_restores_verbatim(self, conn):
        from scripts.null_statpal_live_space_ids_3094 import (
            apply_clear,
            rollback_clear,
        )

        cur = conn.cursor()
        ids = _seed(cur)
        before = _rows(cur)

        done = apply_clear(cur, dry_run=False)
        conn.commit()

        # Exactly the two live-space MLB rows, and the JSONB half was seen.
        assert done["planned"] == 2, done
        assert done["planned_jsonb"] == 1, done
        assert done["cleared"] == 2, done
        assert done["backed_up"] == 2, done

        after = _rows(cur)

        # --- the two rows that must move -------------------------------------
        assert after[ids["col_only"]][0] is None
        assert after[ids["col_only"]][1] is None

        cleared_col, cleared_sources = after[ids["col_and_jsonb"]]
        assert cleared_col is None
        # The key is gone...
        assert "statpal_fixture_id" not in cleared_sources
        # ...and ONLY that key. This is the assertion a `SET ... = NULL`
        # shortcut fails and nothing else in this file would notice.
        assert cleared_sources["espn"] == {"prob": 0.61}
        assert cleared_sources["statpal_end_time"] == "2026-09-01T02:10:00+00:00"

        # --- the three bystanders, byte for byte ------------------------------
        for label in ("six_digit", "nba_seven", "already_null"):
            assert after[ids[label]] == before[ids[label]], label

        # The backup holds the two touched rows and NOT the bystanders.
        cur.execute(f"SELECT event_id FROM {BACKUP_TABLE} ORDER BY event_id")
        assert [r[0] for r in cur.fetchall()] == [
            ids["col_only"],
            ids["col_and_jsonb"],
        ]

        # --- the undo ---------------------------------------------------------
        undone = rollback_clear(cur)
        conn.commit()

        assert undone["restored"] == 2, undone
        # The post-condition, which is the only claim worth making.
        assert undone["unrestored"] == 0, undone

        restored = _rows(cur)
        assert restored[ids["col_only"]] == before[ids["col_only"]]
        assert restored[ids["col_and_jsonb"]] == before[ids["col_and_jsonb"]]
        for label in ("six_digit", "nba_seven", "already_null"):
            assert restored[ids[label]] == before[ids[label]], label

    def test_rollback_does_not_invent_a_jsonb_key_the_row_never_had(self, conn):
        """The 343-row shape: column only, and it must come back column only.

        `jsonb_set` on a row whose backup says `jsonb_had_key = false` would
        hand it a key it never carried. `_get_statpal_id` prefers the column, so
        the row would still dereference correctly and every column assertion
        would pass — the damage is a stale duplicate in the JSONB that outlives
        the next correct re-anchor. Only asking the JSONB directly catches it.
        """
        from scripts.null_statpal_live_space_ids_3094 import (
            apply_clear,
            rollback_clear,
        )

        cur = conn.cursor()
        ids = _seed(cur)

        apply_clear(cur, dry_run=False)
        conn.commit()
        rollback_clear(cur)
        conn.commit()

        cur.execute(
            "SELECT statpal_fixture_id, win_probability_sources FROM events "
            "WHERE id = %s",
            (ids["col_only"],),
        )
        fixture_id, sources = cur.fetchone()
        assert fixture_id == LIVE_ID
        assert sources is None, (
            f"rollback invented win_probability_sources={sources!r} for a row "
            f"that never had one"
        )

    def test_dry_run_writes_nothing_and_creates_no_backup(self, conn):
        """The default path. A dry run that leaves a backup table behind is
        worse than one that writes rows: the next `--apply` finds
        `IF NOT EXISTS` satisfied and keeps a snapshot of the wrong moment.
        """
        from scripts.null_statpal_live_space_ids_3094 import apply_clear

        cur = conn.cursor()
        _seed(cur)
        before = _rows(cur)

        done = apply_clear(cur, dry_run=True)
        conn.commit()

        assert done["planned"] == 2, done
        assert done["cleared"] == 0, done
        assert _rows(cur) == before

        cur.execute("SELECT to_regclass(%s) IS NOT NULL", (BACKUP_TABLE,))
        assert cur.fetchone()[0] is False

    def test_rollback_without_an_apply_refuses(self, conn):
        """A restore with no backup must not read as "nothing needed restoring"."""
        from scripts.null_statpal_live_space_ids_3094 import rollback_clear

        cur = conn.cursor()
        _seed(cur)

        with pytest.raises(SystemExit, match="nothing to roll back to"):
            rollback_clear(cur)

    def test_rollback_finishes_a_partial_restore_rather_than_declining_it(self, conn):
        """A half-restored row must be completable by re-running the undo.

        The restore's guard used to read only `statpal_fixture_id IS DISTINCT
        FROM b.statpal_fixture_id`. A row whose column had been put back by hand
        while its JSONB key was still missing then matched the guard's "already
        correct" branch: the UPDATE declined, no error was raised, and the row
        surfaced in `COUNT_UNRESTORED` as a shortfall the operator had no way to
        clear. An operator holding a partial restore needs re-running the undo
        to converge, not to report the same number forever.
        """
        from scripts.null_statpal_live_space_ids_3094 import (
            apply_clear,
            rollback_clear,
        )

        cur = conn.cursor()
        ids = _seed(cur)
        before = _rows(cur)

        apply_clear(cur, dry_run=False)
        conn.commit()

        # Hand-repair the column half only — the shape the old guard skipped.
        cur.execute(
            "UPDATE events SET statpal_fixture_id = %s WHERE id = %s",
            (before[ids["col_and_jsonb"]][0], ids["col_and_jsonb"]),
        )
        conn.commit()

        undone = rollback_clear(cur)
        conn.commit()

        assert undone["unrestored"] == 0, undone
        assert _rows(cur)[ids["col_and_jsonb"]] == before[ids["col_and_jsonb"]]

    def test_apply_is_idempotent_and_keeps_the_first_snapshot(self, conn):
        """A second `--apply` must find nothing to do and must NOT refresh the
        backup — the first run's snapshot is the one that predates every change.
        """
        from scripts.null_statpal_live_space_ids_3094 import (
            apply_clear,
            rollback_clear,
        )

        cur = conn.cursor()
        ids = _seed(cur)
        before = _rows(cur)

        apply_clear(cur, dry_run=False)
        conn.commit()

        second = apply_clear(cur, dry_run=False)
        conn.commit()
        assert second["planned"] == 0, second
        assert second["cleared"] == 0, second
        # Still the ORIGINAL two rows, not a half-repaired re-snapshot.
        assert second["backed_up"] == 2, second

        # And the undo still works after the no-op second run.
        undone = rollback_clear(cur)
        conn.commit()
        assert undone["unrestored"] == 0, undone
        assert _rows(cur)[ids["col_and_jsonb"]] == before[ids["col_and_jsonb"]]

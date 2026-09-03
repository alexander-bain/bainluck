"""The #2879 re-key's apply/rollback round trip, executed against a REAL PostgreSQL.

## what this replaces, and why nothing cheaper would have caught it

`scripts/rekey_statpal_anchors_2879.py` is a data repair that runs unattended
under D51, which grants that only because it "writes a backup first and ships a
one-command restore". CERT-847 found the restore did not restore.

`--apply` writes in **two** shapes:

    REKEY_ONE          UPDATE ... SET source_id = 'baseball_mlb:354453'
    DELETE_SUPERSEDED  DELETE the legacy row, when the writer already made the
                       D55 one for the same event

and the script's own docstring calls the second one **the usual case** once
lane1's step 2 is live. `--rollback` ran a single statement:

    UPDATE event_provider_anchors a SET source_id = b.source_id
      FROM backup b WHERE a.id = b.id AND a.source_id <> b.source_id

There is no `a` for a deleted row. The reproduction deleted `s6:354453` and
rollback restored **0**, reporting success. The undo D51 was granted against
did not exist for the branch the script expects to take most often.

## why this gate needs a real server

The claim is a **round trip through two write shapes, one of which is a DELETE
that must reappear verbatim**. What has to be observed:

1. **`DELETE_SUPERSEDED` actually fires.** It is guarded by a correlated
   EXISTS on `(source, source_id, id_kind, event_id)`. A mock cursor returns
   whatever rowcount it is told to; only a server decides whether the row went.
2. **The reinsert survives `uq_anchor_source_id`** — unique on
   `(source, source_id, id_kind)`. Putting a legacy row back while the D55 row
   it was superseded by is still standing either works or raises, and only the
   index can say which.
3. **`id` and `first_seen_at` come back unchanged.** `id` is `BigInteger`
   autoincrement and `first_seen_at` carries a `server_default`; a reinsert
   that omits either gets a *new* value silently. Nothing but a real INSERT
   against the real DDL exercises that.
4. **psycopg2's `%s` paramstyle, on the real statements.** This drives
   `apply_rekey`/`rollback_rekey` themselves — not a copy of their SQL — over a
   psycopg2 connection, the same driver the Heroku one-off dyno uses.

There is no local PostgreSQL in the agent sandbox, so CI is where this runs.
The `search-recall` job provides the container and its "Verify the gate is
actually armed" step is what stops a skipped gate reading as a passing one.

## the corpus, and what each row can fail on

Four anchors across three events, each paired with the defect it catches:

* **the dual-row case** (`dual`) — a legacy row *and* its D55 twin on the same
  event. This is the row CERT-847 lost. Apply must delete the legacy one;
  rollback must bring it back with the twin still there.
* **the plain re-key** (`solo`) — legacy row, no twin. Apply rewrites it in
  place; rollback must move it back. This is the arm that already worked, and
  it is here so a repair that fixes the delete by breaking the update cannot
  pass.
* **the collision** (`collide`) — the D55 key is taken by a *different* event.
  The script must touch neither row and say so. Without this, a reinsert that
  is too eager looks correct.
* **a non-StatPal anchor** (`bystander`) — an ESPN row that no statement may
  read, write, back up or restore. A repair whose blast radius grew would show
  up here and nowhere else.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #2879 rekey "
        "round trip (CI job `search-recall` provides one)"
    ),
)

BACKUP_TABLE = "event_provider_anchors_backup_2879"

#: A fixed, distinctive timestamp. `first_seen_at` has a `server_default`, so a
#: reinsert that forgets the column comes back as "now" — which is only
#: distinguishable from the original if the original is not now.
SEEN_AT = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _psycopg2_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres://", "postgresql://", 1
    )


@pytest.fixture
def pg_schema():
    """Real Postgres with the real schema, dropped and rebuilt.

    Deliberately SYNCHRONOUS, unlike its siblings in this directory. The
    subject is a psycopg2 script, so the tests are sync functions, and a sync
    test cannot depend on an async fixture — pytest-asyncio hands it an
    unawaited generator and the schema is silently never built.
    """
    from sqlalchemy import create_engine, text

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_engine(_psycopg2_url(DB_URL))
    with engine.begin() as c:
        # The backup table is not in the ORM metadata, so `drop_all` leaves it
        # behind and the next run's `CREATE TABLE IF NOT EXISTS` would keep a
        # stale snapshot — exactly the failure the script warns about.
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
    """Insert the corpus. Returns `{label: anchor id}`.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT. `events.home_team_name`,
    `.away_team_name`, `.commence_time` and `.status` are NOT NULL, and
    `.status` carries a **client-side** default the ORM applies and a raw
    INSERT does not — omitting it raises `NotNullViolation` rather than taking
    the default. `tests/test_pg_gate_seed_completeness.py` parses these
    statements against the live ORM metadata; this file is registered there.
    """
    cur.execute(
        "INSERT INTO sports (id, key, name, active) VALUES "
        "(1, 'baseball_mlb', 'MLB', true), "
        "(2, 'americanfootball_nfl', 'NFL', true)"
    )
    commence = datetime(2026, 9, 1, 23, 0, tzinfo=timezone.utc)
    for eid, sid, home, away in (
        (101, 1, "Yankees", "Red Sox"),
        (102, 1, "Dodgers", "Giants"),
        (103, 1, "Cubs", "Cardinals"),
        (104, 2, "49ers", "Rams"),
    ):
        cur.execute(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status) VALUES (%s, %s, %s, %s, %s, 'scheduled')",
            (eid, sid, home, away, commence),
        )

    anchors = {
        # the dual-row case: legacy AND its D55 twin, same event. CERT-847's row.
        "dual": (101, "statpal", "s6:354453", "game"),
        "dual_twin": (101, "statpal", "baseball_mlb:354453", "game"),
        # the plain re-key: legacy, no twin.
        "solo": (102, "statpal", "s6:354454", "game"),
        # the collision: the D55 key is taken by a DIFFERENT event.
        "collide": (103, "statpal", "s6:354455", "game"),
        "collide_other": (104, "statpal", "baseball_mlb:354455", "game"),
        # the bystander: not StatPal, must never be touched.
        "bystander": (101, "espn", "401873124", "game"),
    }
    ids: dict[str, int] = {}
    for n, (label, (event_id, source, source_id, kind)) in enumerate(
        anchors.items(), start=1
    ):
        cur.execute(
            "INSERT INTO event_provider_anchors "
            "(id, event_id, source, source_id, id_kind, first_seen_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (n, event_id, source, source_id, kind, SEEN_AT + timedelta(minutes=n)),
        )
        ids[label] = n
    return ids


def _rows(cur) -> dict[int, tuple]:
    cur.execute(
        "SELECT id, event_id, source, source_id, id_kind, first_seen_at "
        "FROM event_provider_anchors ORDER BY id"
    )
    return {r[0]: r for r in cur.fetchall()}


@needs_postgres
class TestApplyRollbackRoundTrip:

    def test_the_seed_contains_all_four_shapes(self, conn):
        """Without this the assertions below could go vacuously green if a
        later edit dropped a row from the corpus."""
        cur = conn.cursor()
        ids = _seed(cur)
        rows = _rows(cur)
        assert len(rows) == 6
        # a legacy row whose D55 key is already taken by the SAME event
        assert rows[ids["dual"]][3] == "s6:354453"
        assert rows[ids["dual_twin"]][3] == "baseball_mlb:354453"
        assert rows[ids["dual"]][1] == rows[ids["dual_twin"]][1]
        # a legacy row whose D55 key is taken by a DIFFERENT event
        assert rows[ids["collide"]][1] != rows[ids["collide_other"]][1]
        # and a row that is not StatPal at all
        assert rows[ids["bystander"]][2] == "espn"
        conn.rollback()

    def test_apply_deletes_the_superseded_legacy_row(self, conn):
        """The write CERT-847 found unrecoverable. Pinned so the repair below
        is provably undoing something that really happened."""
        from scripts.rekey_statpal_anchors_2879 import apply_rekey

        cur = conn.cursor()
        ids = _seed(cur)
        done = apply_rekey(cur)

        assert done["superseded"] == 1, "the dual-row case must take the DELETE arm"
        assert done["rekeyed"] == 1, "the solo row must take the UPDATE arm"
        assert done["skipped"] == 1, "the collision must be left alone"

        rows = _rows(cur)
        assert ids["dual"] not in rows, "the legacy row is gone"
        assert rows[ids["dual_twin"]][3] == "baseball_mlb:354453"
        assert rows[ids["solo"]][3] == "baseball_mlb:354454"
        assert rows[ids["collide"]][3] == "s6:354455", "collision untouched"
        assert rows[ids["collide_other"]][3] == "baseball_mlb:354455"
        conn.rollback()

    def test_rollback_recreates_the_legacy_row_and_keeps_the_qualified_one(self, conn):
        """CERT-847's required repair, executed.

        The whole round trip: the deleted row comes back **verbatim** — same
        id, same event, same source_id, same first_seen_at — while the D55 twin
        that superseded it is still standing."""
        from scripts.rekey_statpal_anchors_2879 import apply_rekey, rollback_rekey

        cur = conn.cursor()
        ids = _seed(cur)
        before = _rows(cur)

        apply_rekey(cur)
        assert ids["dual"] not in _rows(cur)

        done = rollback_rekey(cur)
        after = _rows(cur)

        assert done["reinserted"] == 1, "the deleted legacy row was put back"
        assert done["restored"] == 1, "the re-keyed row was moved back too"
        assert done["unrestored"] == 0, "and nothing is left owing"

        assert after[ids["dual"]] == before[ids["dual"]], "verbatim, id and timestamp"
        assert after[ids["dual_twin"]] == before[ids["dual_twin"]], "twin preserved"
        conn.rollback()

    def test_the_whole_table_is_byte_identical_after_the_round_trip(self, conn):
        """The strongest form of the claim, and the one a partial repair fails:
        every row, not just the interesting ones."""
        from scripts.rekey_statpal_anchors_2879 import apply_rekey, rollback_rekey

        cur = conn.cursor()
        _seed(cur)
        before = _rows(cur)

        apply_rekey(cur)
        rollback_rekey(cur)

        assert _rows(cur) == before
        conn.rollback()

    def test_the_update_arm_alone_cannot_pass_this(self, conn):
        """The red arm. Runs the ORIGINAL one-statement restore — the exact SQL
        CERT-847 blocked — and shows it leaves the deleted row gone. Without
        this, a rollback that quietly stopped reinserting would still be green
        on the assertions above only until someone changed them."""
        from scripts.rekey_statpal_anchors_2879 import RESTORE, apply_rekey

        cur = conn.cursor()
        ids = _seed(cur)
        apply_rekey(cur)

        cur.execute(RESTORE)  # the old rollback, in full
        rows = _rows(cur)

        assert ids["dual"] not in rows, (
            "the update-only restore cannot resurrect a deleted row — if this "
            "ever fails, RESTORE has grown a second job and the reinsert arm "
            "may no longer be load-bearing"
        )
        assert rows[ids["solo"]][3] == "s6:354454", "it does still fix the re-key"
        conn.rollback()

    def test_rollback_refuses_when_no_backup_exists(self, conn):
        """A rollback with no backup used to report a successful restore of
        zero rows. 'Nothing to restore' and 'nothing was restored' are
        different answers (gotcha #53)."""
        from scripts.rekey_statpal_anchors_2879 import rollback_rekey

        cur = conn.cursor()
        _seed(cur)
        cur.execute(f"DROP TABLE IF EXISTS {BACKUP_TABLE}")

        with pytest.raises(SystemExit):
            rollback_rekey(cur)
        conn.rollback()

    def test_a_reused_primary_key_never_gets_a_strangers_source_id(self, conn):
        """`id` is a reusable BIGSERIAL, and `DELETE_SUPERSEDED` frees one.

        This is the case that makes `a.id = b.id` on its own dangerous: restore
        it that way and a Kalshi market anchor that happened to be handed the
        freed key gets stamped `s6:354453` — a row the script was never asked
        to touch, corrupted in the name of an undo. The restore must recognise
        its own rows (same provider, kind and event), not just their number."""
        from scripts.rekey_statpal_anchors_2879 import apply_rekey, rollback_rekey

        cur = conn.cursor()
        ids = _seed(cur)
        apply_rekey(cur)

        # Something else claims the freed primary key.
        cur.execute(
            "INSERT INTO event_provider_anchors "
            "(id, event_id, source, source_id, id_kind, first_seen_at) "
            "VALUES (%s, 101, 'kalshi', 'KXMLB-26SEP01', 'market', %s)",
            (ids["dual"], SEEN_AT),
        )

        done = rollback_rekey(cur)

        stranger = _rows(cur)[ids["dual"]]
        assert stranger[2] == "kalshi", "the occupant is not replaced"
        assert stranger[3] == "KXMLB-26SEP01", (
            "and its source_id is NOT overwritten with the backed-up StatPal id"
        )
        assert stranger[4] == "market"

        # The undo is partial, and — the point of the post-condition count —
        # it is REPORTED as partial. Both write arms return 0 for this row and
        # neither raises, so a rowcount-based report would have called this a
        # clean undo while a row was gone for good.
        assert done["reinserted"] == 0
        assert done["restored"] == 1, "the solo re-key is still put back"
        assert done["unrestored"] == 1, (
            "the lost row is counted, so the operator is told this is a "
            "PARTIAL restore rather than an undo"
        )
        conn.rollback()

    def test_the_bystander_is_never_read_or_written(self, conn):
        """Blast radius. An ESPN anchor on one of the same events must not
        appear in the backup, must survive apply, and must survive rollback."""
        from scripts.rekey_statpal_anchors_2879 import apply_rekey, rollback_rekey

        cur = conn.cursor()
        ids = _seed(cur)
        before = _rows(cur)[ids["bystander"]]

        apply_rekey(cur)
        cur.execute(f"SELECT count(*) FROM {BACKUP_TABLE} WHERE source <> 'statpal'")
        assert cur.fetchone()[0] == 0, "the backup holds StatPal rows only"
        assert _rows(cur)[ids["bystander"]] == before

        rollback_rekey(cur)
        assert _rows(cur)[ids["bystander"]] == before
        conn.rollback()

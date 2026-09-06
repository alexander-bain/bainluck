"""The containers migration upgrades, enforces, and UNDOES — on real Postgres.

#2927 Phase 1, migration ``containers_phase1``. Authorised by Alex's verbatim
"go 2927" (``.claude/handoff/ALEX-GO-2927.md``), which authorises the four
additive tables **and requires that dropping them is the undo**. This file is
the proof of that sentence rather than the assertion of it.

WHY THIS CANNOT BE A UNIT TEST, AND WHY A SQLITE RIG WOULD BE WORSE THAN
NOTHING HERE. Every claim below is a claim about PostgreSQL specifically:

* the **FK reference loop** — ``event_edges.receipt_id`` -> ``market_match_receipts``
  and ``market_match_receipts.container_id`` -> ``containers`` — is only
  survivable because the column is added last. Nothing but a real
  ``CREATE TABLE`` in that order can fail if the order is wrong, and if it is
  wrong it fails in the Heroku release phase, on production.
* ``CHECK`` constraints are enforced by the **server**. SQLAlchemy will hand
  Postgres any row; the constraint is what says no. The provenance-enum
  incident (C-ADHOC-PROV-CORE) is the precedent: a recording double stored and
  committed a value the real type would have rejected, and every unit test was
  green while the defect was live.
* a ``UNIQUE`` index refusing a second claim is server behaviour, and "one
  provider id names one container" (D55) is the single most load-bearing
  sentence in the spec.
* the **downgrade restoring the exact prior schema** can only be shown by
  reading ``information_schema`` before and after.

THE SHAPE OF THE STRONGEST TEST HERE is a round trip, not a snapshot: migrate
to the revision *before* this one, photograph the schema, migrate up, prove the
new objects both exist and bite, migrate back down, photograph again, and
require the two photographs to be identical. A test that only checked "the
tables exist after upgrade" would pass just as happily with a downgrade that
silently left three indexes and a foreign key behind — which is precisely the
state that makes a rollback fail the second time it is attempted.

The scratch database is created and dropped by this module and is NOT the
database its sibling gates in the ``search-recall`` job share: this test
migrates from empty and drops everything, so pointing it at ``bl_searchtest``
would destroy the schema those gates build.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import psycopg2
import pytest
from psycopg2 import errors as pg_errors
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from app.utils.migration_lock_budget import psycopg2_url

#: The revision immediately before ours — the state a rollback returns to, and
#: the argument in the undo line the go was given:
#:     alembic downgrade uq_event_espn_id
PARENT_REVISION = "uq_event_espn_id"
THIS_REVISION = "containers_phase1"

BACKEND_DIR = Path(__file__).resolve().parents[2]

_RAW_URL = os.getenv("SEARCH_TEST_DATABASE_URL") or os.getenv(
    "MIGRATION_TEST_DATABASE_URL"
)

pytestmark = pytest.mark.skipif(
    not _RAW_URL,
    reason=(
        "needs a real PostgreSQL: set SEARCH_TEST_DATABASE_URL (the "
        "search-recall job's service container) or MIGRATION_TEST_DATABASE_URL"
    ),
)


def _admin_url_and_scratch_name() -> tuple[str, str]:
    """A maintenance URL plus a unique scratch database name.

    Unique per run: two concurrent CI jobs against one server must not fight
    over a fixed name, and a leaked database from a killed run must not make
    the next run fail with "already exists" — which would read as a migration
    failure and send someone hunting the wrong bug.
    """
    sync_url = psycopg2_url(_RAW_URL)
    base, _, _ = sync_url.rpartition("/")
    scratch = f"bl_mig_{uuid.uuid4().hex[:12]}"
    return f"{base}/postgres", scratch


@pytest.fixture(scope="module")
def scratch_db() -> str:
    """Create an empty database for the round trip; drop it afterwards."""
    admin_url, scratch = _admin_url_and_scratch_name()

    conn = psycopg2.connect(admin_url)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{scratch}"')
    finally:
        conn.close()

    base, _, _ = admin_url.rpartition("/")
    scratch_url = f"{base}/{scratch}"
    try:
        yield scratch_url
    finally:
        conn = psycopg2.connect(admin_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        try:
            with conn.cursor() as cur:
                # Terminate stragglers first: a leaked connection makes DROP
                # DATABASE hang, and a hanging teardown reads as a hung test.
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (scratch,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{scratch}"')
        finally:
            conn.close()


def _alembic(scratch_url: str, *args: str) -> subprocess.CompletedProcess:
    """Run Alembic exactly the way the Heroku release phase does.

    A subprocess, not ``alembic.command`` in-process: the release phase runs
    ``alembic upgrade head`` as its own process against ``DATABASE_URL``, and
    an in-process call with a hand-built Config would be testing a code path
    production never takes.
    """
    env = dict(os.environ)
    env["DATABASE_URL"] = scratch_url
    return subprocess.run(
        ["python", "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )


def _require_alembic(scratch_url: str, *args: str) -> None:
    result = _alembic(scratch_url, *args)
    assert result.returncode == 0, (
        f"alembic {' '.join(args)} exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# schema photographs
# ---------------------------------------------------------------------------


def _photograph(conn) -> dict:
    """Everything the downgrade is responsible for putting back.

    Deliberately broader than "did the four tables go": the failure this
    catches is a downgrade that drops the tables but leaves
    ``market_match_receipts.container_id``, its foreign key, or its index
    behind. Those three survive their tables and must be removed by hand, so
    they are exactly the ones a hand-written ``downgrade`` forgets.
    """
    photo: dict = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
        photo["tables"] = [r[0] for r in cur.fetchall()]

        cur.execute(
            "SELECT table_name, column_name, data_type, is_nullable, "
            "       column_default "
            "FROM information_schema.columns WHERE table_schema = 'public' "
            "ORDER BY table_name, column_name"
        )
        photo["columns"] = [tuple(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT tablename, indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' ORDER BY tablename, indexname"
        )
        photo["indexes"] = [tuple(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) "
            "FROM pg_constraint "
            "WHERE connamespace = 'public'::regnamespace "
            "ORDER BY 1, 2"
        )
        photo["constraints"] = [tuple(r) for r in cur.fetchall()]
    return photo


@pytest.fixture(scope="module")
def round_trip(scratch_db: str) -> dict:
    """Migrate to the parent, photograph, migrate up. Yields both photographs.

    Module-scoped because the full chain is ~112 migrations and running it once
    per assertion would turn a fast gate into a slow one nobody keeps.
    """
    _require_alembic(scratch_db, "upgrade", PARENT_REVISION)

    conn = psycopg2.connect(scratch_db)
    try:
        before = _photograph(conn)
    finally:
        conn.close()

    _require_alembic(scratch_db, "upgrade", THIS_REVISION)
    return {"url": scratch_db, "before": before}


@pytest.fixture()
def pg(round_trip: dict):
    """A connection to the migrated scratch database, rolled back per test.

    Rollback rather than commit: every behaviour test below deliberately
    violates a constraint, and a committed half-row would leak into the next
    test's assertions.
    """
    conn = psycopg2.connect(round_trip["url"])
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


# ---------------------------------------------------------------------------
# 1. the upgrade runs at all — the FK loop and the ordering
# ---------------------------------------------------------------------------


def test_upgrade_creates_all_four_tables_and_the_receipt_column(round_trip, pg):
    """The whole chain reaches our head, in order, on a real server.

    This is the assertion that catches a reordered ``upgrade()``: the two
    cross-references between ``event_edges`` and ``market_match_receipts`` mean
    a wrong order raises ``UndefinedTable`` here rather than in the release
    phase.
    """
    with pg.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY(%s) "
            "ORDER BY table_name",
            (
                [
                    "container_provider_anchors",
                    "containers",
                    "event_edges",
                    "event_participants",
                ],
            ),
        )
        assert [r[0] for r in cur.fetchall()] == [
            "container_provider_anchors",
            "containers",
            "event_edges",
            "event_participants",
        ]

        cur.execute(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "  AND table_name = 'market_match_receipts' "
            "  AND column_name = 'container_id'"
        )
        row = cur.fetchone()
        assert row is not None, "market_match_receipts.container_id was not added"
        # NULLABLE is the deploy-safety claim: a nullable column with no default
        # is catalogue-only on PG 11+, so the ACCESS EXCLUSIVE lock is not held
        # for a rewrite of ~450k rows.
        assert row[1] == "YES", "container_id must be nullable — see the migration"

        cur.execute(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'market_match_receipts' "
            "  AND column_name = 'container_id'"
        )
        assert cur.fetchone()[0] is None, (
            "container_id must have NO default; a default is what turns the "
            "ADD COLUMN into a table rewrite on older servers"
        )


def test_head_is_single_after_this_migration(round_trip):
    """Two heads fail the Heroku release phase outright — the site does not
    deploy at all. Read from the migrated database, not from the files."""
    result = _alembic(round_trip["url"], "current")
    assert result.returncode == 0, result.stderr
    assert THIS_REVISION in result.stdout, result.stdout
    # `current` prints one line per head; more than one head means a branch.
    head_lines = [
        line
        for line in result.stdout.splitlines()
        if line.strip() and "(head)" in line
    ]
    assert len(head_lines) == 1, f"expected a single head, got: {head_lines}"


# ---------------------------------------------------------------------------
# 2. the constraints BITE — server-side, not in Python
# ---------------------------------------------------------------------------


def _insert_container(cur, slug="us-open-2026", kind="tournament", **kw) -> int:
    cur.execute(
        "INSERT INTO containers (kind, name, slug, status) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (kind, kw.get("name", "US Open 2026"), slug, kw.get("status", "scheduled")),
    )
    return cur.fetchone()[0]


def test_one_provider_id_names_one_container(pg):
    """D55, and the single most load-bearing sentence in the spec.

    A second claim on the same ``(provider, id_kind, provider_id)`` must RAISE.
    A silent no-op here is how two draws quietly become one hub.
    """
    with pg.cursor() as cur:
        first = _insert_container(cur, slug="us-open-2026-mens-doubles")
        second = _insert_container(cur, slug="us-open-2026-womens-doubles")
        cur.execute(
            "INSERT INTO container_provider_anchors "
            "(container_id, provider, provider_id, id_kind) "
            "VALUES (%s, 'espn', '1234', 'tournament')",
            (first,),
        )
        with pytest.raises(pg_errors.UniqueViolation):
            cur.execute(
                "INSERT INTO container_provider_anchors "
                "(container_id, provider, provider_id, id_kind) "
                "VALUES (%s, 'espn', '1234', 'tournament')",
                (second,),
            )


def test_the_same_string_may_be_two_different_id_kinds(pg):
    """``id_kind`` is IN the unique key on purpose.

    One Polymarket string can legitimately be both an ``event_slug`` and a
    ``tag``. If this raised, the key would be over-tight and assembly would
    have to drop a real anchor to record another.
    """
    with pg.cursor() as cur:
        cid = _insert_container(cur, slug="us-open-2026-tags")
        cur.execute(
            "INSERT INTO container_provider_anchors "
            "(container_id, provider, provider_id, id_kind) "
            "VALUES (%s, 'polymarket', 'us-open', 'event_slug')",
            (cid,),
        )
        cur.execute(
            "INSERT INTO container_provider_anchors "
            "(container_id, provider, provider_id, id_kind) "
            "VALUES (%s, 'polymarket', 'us-open', 'tag')",
            (cid,),
        )
        cur.execute(
            "SELECT count(*) FROM container_provider_anchors WHERE container_id = %s",
            (cid,),
        )
        assert cur.fetchone()[0] == 2


def test_a_contains_edge_without_a_class_is_refused(pg):
    """A member with no section is a member the hub cannot render.

    The answer for "we could not classify it" is ``'unclassified'`` — a real
    class that gets a section last — and never NULL, because a NULL class is
    how a member silently disappears from every section the hub draws. That is
    the exact failure this program exists to end, so the database refuses it.
    """
    with pg.cursor() as cur:
        cid = _insert_container(cur, slug="us-open-2026-noclass")
        with pytest.raises(pg_errors.CheckViolation):
            cur.execute(
                "INSERT INTO event_edges "
                "(parent_id, parent_type, child_id, child_type, kind, "
                " class, source, confidence) "
                "VALUES (%s, 'container', 99, 'event', 'contains', "
                " NULL, 'register', 1.0)",
                (cid,),
            )


def test_unclassified_is_accepted_as_a_class(pg):
    """The other half of the rule above, and it must be tested as a pair.

    A CHECK written as ``class IN (<the six named classes>)`` would also make
    the previous test pass, while making the honest answer unstorable — so
    assembly would have to invent a class or drop the member. Both are the
    silent loss. Only ``'unclassified'`` being *accepted* proves the constraint
    is the one the spec asked for.
    """
    with pg.cursor() as cur:
        cid = _insert_container(cur, slug="us-open-2026-unclassified")
        cur.execute(
            "INSERT INTO event_edges "
            "(parent_id, parent_type, child_id, child_type, kind, "
            " class, source, confidence) "
            "VALUES (%s, 'container', 99, 'event', 'contains', "
            " 'unclassified', 'register', 0.5) RETURNING id",
            (cid,),
        )
        assert cur.fetchone()[0] is not None


def test_a_non_contains_edge_needs_no_class(pg):
    """``same_as`` / ``derived_from`` / ``advances_to`` carry no section."""
    with pg.cursor() as cur:
        cur.execute(
            "INSERT INTO event_edges "
            "(parent_id, parent_type, child_id, child_type, kind, "
            " class, source, confidence) "
            "VALUES (1, 'event', 2, 'event', 'same_as', NULL, 'matcher', 0.9) "
            "RETURNING id"
        )
        assert cur.fetchone()[0] is not None


def test_a_node_cannot_contain_itself(pg):
    with pg.cursor() as cur:
        with pytest.raises(pg_errors.CheckViolation):
            cur.execute(
                "INSERT INTO event_edges "
                "(parent_id, parent_type, child_id, child_type, kind, "
                " class, source, confidence) "
                "VALUES (7, 'event', 7, 'event', 'contains', "
                " 'match_winner', 'matcher', 1.0)"
            )


def test_two_ids_that_match_across_different_types_are_fine(pg):
    """The self-edge CHECK is on the ``(type, id)`` PAIR, not on the id.

    Container 7 containing event 7 is an ordinary row — the id spaces are
    unrelated. A CHECK written as ``parent_id <> child_id`` would pass the test
    above and silently refuse this, which at production id densities would
    reject roughly one real membership in every container.
    """
    with pg.cursor() as cur:
        cur.execute(
            "INSERT INTO event_edges "
            "(parent_id, parent_type, child_id, child_type, kind, "
            " class, source, confidence) "
            "VALUES (7, 'container', 7, 'event', 'contains', "
            " 'match_winner', 'matcher', 1.0) RETURNING id"
        )
        assert cur.fetchone()[0] is not None


def test_confidence_outside_zero_to_one_is_refused(pg):
    # The out-of-range value is BOUND, not interpolated. An f-string here would
    # be unreadable to `tests/test_pg_gate_seed_completeness.py`'s parser, and a
    # seed that check cannot read is a seed it is not guarding — which is the
    # whole reason that file exists.
    with pg.cursor() as cur:
        for bad in ("1.5", "-0.1"):
            pg.rollback()
            with pytest.raises(pg_errors.CheckViolation):
                cur.execute(
                    "INSERT INTO event_edges "
                    "(parent_id, parent_type, child_id, child_type, kind, "
                    " class, source, confidence) "
                    "VALUES (1, 'container', 2, 'event', 'contains', "
                    " 'title', 'human', %s)",
                    (bad,),
                )


def test_an_edge_of_a_given_kind_is_unique_so_reassembly_is_idempotent(pg):
    """Assembly re-runs. Without this key a nightly job doubles every member."""
    with pg.cursor() as cur:
        sql = (
            "INSERT INTO event_edges "
            "(parent_id, parent_type, child_id, child_type, kind, "
            " class, source, confidence) "
            "VALUES (11, 'container', 22, 'event', 'contains', "
            " 'match_winner', 'register', 1.0)"
        )
        cur.execute(sql)
        with pytest.raises(pg_errors.UniqueViolation):
            cur.execute(sql)


def test_the_same_pair_may_hold_two_different_kinds(pg):
    """``kind`` is in the key: ``contains`` and ``derived_from`` can coexist."""
    with pg.cursor() as cur:
        cur.execute(
            "INSERT INTO event_edges "
            "(parent_id, parent_type, child_id, child_type, kind, "
            " class, source, confidence) "
            "VALUES (11, 'container', 22, 'market', 'contains', "
            " 'prop', 'venue_grouping', 1.0)"
        )
        cur.execute(
            "INSERT INTO event_edges "
            "(parent_id, parent_type, child_id, child_type, kind, "
            " class, source, confidence) "
            "VALUES (11, 'container', 22, 'market', 'derived_from', "
            " NULL, 'matcher', 0.8)"
        )
        cur.execute(
            "SELECT count(*) FROM event_edges WHERE parent_id = 11 AND child_id = 22"
        )
        assert cur.fetchone()[0] == 2


def test_a_container_cannot_be_its_own_parent(pg):
    with pg.cursor() as cur:
        cid = _insert_container(cur, slug="us-open-2026-selfparent")
        with pytest.raises(pg_errors.CheckViolation):
            cur.execute(
                "UPDATE containers SET parent_container_id = %s WHERE id = %s",
                (cid, cid),
            )


def test_two_containers_cannot_claim_one_slug(pg):
    """The slug IS the public URL ``/api/containers/{slug}``."""
    with pg.cursor() as cur:
        _insert_container(cur, slug="us-open-2026-dup")
        with pytest.raises(pg_errors.UniqueViolation):
            _insert_container(cur, slug="us-open-2026-dup")


def test_a_doubles_pair_occupies_two_positions_on_one_side(pg):
    """The shape the whole participants table exists for.

    Two rows, one side, positions 0 and 1 — and a third row at position 0
    refused, so a re-run cannot turn a doubles pair into four.
    """
    with pg.cursor() as cur:
        # The scratch database is migrated, not seeded, so there are no sports
        # rows to borrow — make one.
        #
        # `active` IS SPELLED OUT ON PURPOSE. `Sport.active` carries a
        # CLIENT-SIDE ORM default (`default=True`) and no `server_default`, so
        # the column is NOT NULL with nothing to fill it: the default exists
        # only inside SQLAlchemy's flush and is invisible to raw SQL. Omitting
        # it here is a NotNullViolation, and this fixture found that the hard
        # way. It is the same trap as `futures_outcomes.is_winner` in #2199,
        # pointing the other direction.
        cur.execute(
            "INSERT INTO sports (key, name, active) VALUES "
            "('tennis_atp_us_open', 'US Open', true) RETURNING id"
        )
        sport_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO events (sport_id, external_id, home_team_name, "
            "away_team_name, commence_time, status) "
            "VALUES (%s, 'containers-test-1', 'A/B', 'C/D', now(), "
            "'scheduled') RETURNING id",
            (sport_id,),
        )
        event_id = cur.fetchone()[0]

        for position, name in ((0, "Player A"), (1, "Player B")):
            cur.execute(
                "INSERT INTO event_participants "
                "(event_id, side, entity_type, entity_name, role, position) "
                "VALUES (%s, 'home', 'player', %s, 'partner', %s)",
                (event_id, name, position),
            )

        with pytest.raises(pg_errors.UniqueViolation):
            cur.execute(
                "INSERT INTO event_participants "
                "(event_id, side, entity_type, entity_name, position) "
                "VALUES (%s, 'home', 'player', 'Player C', 0)",
                (event_id,),
            )


def test_a_participant_survives_an_unresolved_entity(pg):
    """``entity_id`` NULL with ``entity_name`` set is the normal day-one row.

    Ten name shapes in ARTIFACT-M-20260903-I will not resolve on day one
    ("Y. Bu" is Bu Yunchaokete). A side we cannot name is a side we do not
    store, so ``entity_name`` is NOT NULL and ``entity_id`` is not.
    """
    with pg.cursor() as cur:
        cur.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'event_participants' AND column_name = %s",
            ("entity_id",),
        )
        assert cur.fetchone()[0] == "YES"
        cur.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'event_participants' AND column_name = %s",
            ("entity_name",),
        )
        assert cur.fetchone()[0] == "NO"


def test_deleting_a_container_keeps_the_receipts_of_what_it_refused(pg):
    """SET NULL, not CASCADE.

    A container rebuilt from scratch after a bad assembly run is exactly when
    the record of what it refused is worth most. CASCADE here would delete the
    evidence at the only moment anyone wants to read it.
    """
    with pg.cursor() as cur:
        cur.execute(
            "SELECT confdeltype FROM pg_constraint "
            "WHERE conname = 'fk_match_receipt_container'"
        )
        row = cur.fetchone()
        assert row is not None, "fk_match_receipt_container is missing"
        # 'n' = SET NULL, 'c' = CASCADE, 'a' = NO ACTION.
        assert row[0] == "n", f"expected ON DELETE SET NULL, got confdeltype={row[0]!r}"

    with pg.cursor() as cur:
        cur.execute(
            "SELECT confdeltype FROM pg_constraint "
            "WHERE conrelid = 'container_provider_anchors'::regclass "
            "  AND contype = 'f'"
        )
        # The anchor's cascade IS correct: an anchor to a container that no
        # longer exists is a dangling assertion the next run would act on.
        assert [r[0] for r in cur.fetchall()] == ["c"]


# ---------------------------------------------------------------------------
# 3. the undo line — the sentence Alex's go was given
# ---------------------------------------------------------------------------


def test_downgrade_restores_the_exact_prior_schema(round_trip):
    """``alembic downgrade uq_event_espn_id`` puts the schema back, exactly.

    Runs LAST in the module (pytest executes in file order) because it leaves
    the scratch database at the parent revision.

    The comparison is the whole point. "The four tables are gone" would also
    be true of a downgrade that left ``market_match_receipts.container_id``,
    its foreign key and its index standing — and that residue is what makes the
    SECOND rollback attempt fail, in the release phase, with the site down. The
    three objects on ``market_match_receipts`` are the ones a hand-written
    ``downgrade`` forgets, because they are the only ones that do not disappear
    with their own table.
    """
    _require_alembic(round_trip["url"], "downgrade", PARENT_REVISION)

    conn = psycopg2.connect(round_trip["url"])
    try:
        after = _photograph(conn)
    finally:
        conn.close()

    before = round_trip["before"]

    # Named separately so a failure says WHICH kind of object leaked, rather
    # than dumping four lists and leaving the reader to diff them.
    assert after["tables"] == before["tables"], (
        "tables differ after downgrade; leaked: "
        f"{sorted(set(after['tables']) - set(before['tables']))}"
    )
    assert after["columns"] == before["columns"], (
        "columns differ after downgrade; leaked: "
        f"{sorted(set(after['columns']) - set(before['columns']))}"
    )
    assert after["indexes"] == before["indexes"], (
        "indexes differ after downgrade; leaked: "
        f"{sorted(set(after['indexes']) - set(before['indexes']))}"
    )
    assert after["constraints"] == before["constraints"], (
        "constraints differ after downgrade; leaked: "
        f"{sorted(set(after['constraints']) - set(before['constraints']))}"
    )

    # LEADING NEWLINE, and it is load-bearing rather than cosmetic. Under
    # `-v -s` pytest writes the test id and the captured output on the SAME
    # line, so a summary printed without it lands mid-line as
    # `test_downgrade_… CONTAINERS MIGRATION ROUND TRIP: …` — and the CI step's
    # `grep -E "^CONTAINERS MIGRATION ROUND TRIP"` then fails on a run where all
    # 18 tests passed. That happened: 18 passed, step red, "the undo line is
    # unproved". A gate that goes red on success is worse than no gate, because
    # the next person's fix is to delete the check.
    print(
        f"\nCONTAINERS MIGRATION ROUND TRIP: {THIS_REVISION} up and back to "
        f"{PARENT_REVISION}; {len(before['tables'])} tables, "
        f"{len(before['columns'])} columns, {len(before['indexes'])} indexes, "
        f"{len(before['constraints'])} constraints identical before and after"
    )

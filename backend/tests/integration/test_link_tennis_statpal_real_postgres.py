"""The #2867 tennis link's apply/rollback round trip, against a REAL PostgreSQL.

## why this gate needs a real server

`scripts/link_tennis_statpal_anchors_2867.py` runs unattended under D51, which
grants that only because it "writes a backup first and ships a one-command
restore". CERT-847 is the precedent for what a mocked restore proves: the #2879
re-key's rollback reported success while restoring nothing, because the arm that
had to resurrect a deleted row did not exist and a mock cursor returns whatever
rowcount it is told to.

This script writes in **two** shapes per link and they undo differently:

    UPDATE events SET statpal_fixture_id = '2631673'      -> restore the old value
    INSERT event_provider_anchors ('tennis:2631673')      -> delete, but only ours

Four things only a server can decide:

1. **`ON CONFLICT DO NOTHING` against `uq_anchor_source_id`.** The unique index
   is `(source, source_id, id_kind)`. Whether a second claim on a live key is a
   silent no-op or a raise is the index's answer, not a mock's.
2. **Whether the delete arm is correctly scoped.** `anchor_existed_before` is
   the whole of the undo's precision: an anchor that predated the apply must
   still be standing afterwards. Deleting it would be a change, not an undo, and
   only a real DELETE ... USING can be observed getting that wrong.
3. **`IS DISTINCT FROM` / `IS NOT DISTINCT FROM` over NULL.** The normal
   `statpal_fixture_id_before` is NULL, so every restore and every
   post-condition read runs through three-valued logic. sqlite spells this
   differently and would pass a statement Postgres refuses.
4. **psycopg2's `%s` paramstyle on the real statements.** This drives `plan`,
   `apply_links` and `rollback_links` themselves — not a copy of their SQL —
   over the driver the Heroku one-off dyno uses.

There is no local PostgreSQL in the agent sandbox, so CI is where this runs. The
`search-recall` job provides the container and its "Verify the gate is actually
armed" step is what stops a skipped gate reading as a passing one.

## the corpus, and what each row can fail on

Seven events, each paired with the defect it catches:

* **`clean`** — the ordinary link. Both writes fire; both come back.
* **`prior_anchor_same_event`** — the anchor is already there and already names
  this event. The column is still written, and rollback must LEAVE THE ANCHOR
  ALONE. This is the row that catches an undo which deletes by key.
* **`espn_disagrees`** — the map's corroborating witness does not match the row.
  Refused: the row moved under the sweep.
* **`holds_other_fixture`** — already linked to a different StatPal match.
* **`fixture_taken`** — a *different* event of ours already holds this fixture id.
* **`anchor_taken`** — an anchor on this key already names a different event.
* **`not_tennis`** — a baseball row. Refused before a key is even built.

Plus a **bystander** ESPN anchor that must never be read or written.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #2867 tennis link "
        "round trip (CI job `search-recall` provides one)"
    ),
)

LEDGER_TABLE = "statpal_tennis_link_backup_2867"

#: A fixed, distinctive timestamp — `first_seen_at` carries a `server_default`,
#: so "unchanged" is only observable if the original is not now.
SEEN_AT = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _load_script():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "link_tennis_statpal_anchors_2867.py"
    )
    spec = importlib.util.spec_from_file_location("link_tennis_statpal_2867_pg", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


def _psycopg2_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres://", "postgresql://", 1
    )


@pytest.fixture
def pg_schema():
    """Real Postgres with the real schema, dropped and rebuilt.

    Synchronous on purpose: the subject is a psycopg2 script, so the tests are
    sync functions, and a sync test given an async fixture silently receives an
    unawaited generator and never gets a schema.
    """
    from sqlalchemy import create_engine, text

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_engine(_psycopg2_url(DB_URL))
    with engine.begin() as c:
        # Not in the ORM metadata, so `drop_all` leaves it behind and the next
        # run's `CREATE TABLE IF NOT EXISTS` keeps a stale ledger — which is the
        # exact state that makes a rollback undo somebody else's apply.
        c.execute(text(f"DROP TABLE IF EXISTS {LEDGER_TABLE}"))
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


#: `label -> (event_id, sport_id, espn_id, statpal_fixture_id)`.
EVENTS = {
    "clean": (201, 1, "182745", None),
    "prior_anchor_same_event": (202, 1, "182691", None),
    "espn_disagrees": (203, 1, "999999", None),
    "holds_other_fixture": (204, 1, "182747", "2600000"),
    "fixture_taken": (205, 2, "182689", None),
    "squatter": (206, 2, "182600", "2631512"),  # holds `fixture_taken`'s id
    "anchor_taken": (207, 1, "182570", None),
    "anchor_squatter": (208, 2, "182601", None),  # holds `anchor_taken`'s anchor
    "not_tennis": (209, 3, "401873124", None),
}

#: `our_event_id -> statpal_id`, the map rows the corpus is driven by.
MAP_ROWS = [
    # event_id, statpal_id, espn_id (as the map believes it)
    (201, "2631673", "182745"),
    (202, "2631734", "182691"),
    (203, "2631690", "182745"),  # espn_id disagrees with event 203
    (204, "2631691", "182747"),
    (205, "2631512", "182689"),  # `squatter` already holds 2631512
    (207, "2631627", "182570"),  # `anchor_squatter` already holds tennis:2631627
    (209, "2631999", "401873124"),  # baseball
]


def _seed(cur) -> None:
    """Insert the corpus.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT. `events.home_team_name`,
    `.away_team_name`, `.commence_time` and `.status` are NOT NULL, and
    `.status` carries a **client-side** default the ORM applies and a raw INSERT
    does not — omitting it raises `NotNullViolation` rather than taking the
    default. `tests/test_pg_gate_seed_completeness.py` parses these statements
    against the live ORM metadata; this file is registered there.
    """
    cur.execute(
        "INSERT INTO sports (id, key, name, active) VALUES "
        "(1, 'tennis_atp_us_open', 'US Open (ATP)', true), "
        "(2, 'tennis_atp', 'ATP', true), "
        "(3, 'baseball_mlb', 'MLB', true)"
    )
    commence = datetime(2026, 9, 4, 23, 0, tzinfo=timezone.utc)
    for label, (eid, sid, espn_id, fixture_id) in EVENTS.items():
        cur.execute(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
            "commence_time, status, espn_id, statpal_fixture_id) "
            "VALUES (%s, %s, %s, %s, %s, 'scheduled', %s, %s)",
            (eid, sid, f"{label} home", f"{label} away", commence, espn_id, fixture_id),
        )

    anchors = (
        # already names event 202 — the apply must not double it and the
        # rollback must not delete it.
        (1, 202, "statpal", "tennis:2631734", "game"),
        # already names event 208, so event 207's claim is refused.
        (2, 208, "statpal", "tennis:2631627", "game"),
        # the bystander: never read, never written.
        (3, 201, "espn", "182745", "game"),
    )
    for n, event_id, source, source_id, kind in anchors:
        cur.execute(
            "INSERT INTO event_provider_anchors "
            "(id, event_id, source, source_id, id_kind, first_seen_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (n, event_id, source, source_id, kind, SEEN_AT + timedelta(minutes=n)),
        )
    # Explicit ids do not advance the sequence, so the first INSERT the script
    # makes would be handed id 1 and raise on the primary key — a failure of the
    # seed masquerading as a failure of the subject.
    cur.execute(
        "SELECT setval('event_provider_anchors_id_seq', "
        "(SELECT max(id) FROM event_provider_anchors))"
    )


def _map_rows() -> list[dict]:
    return [
        {
            "our_event_id": str(eid),
            "statpal_id": fid,
            "espn_id": espn,
            "confidence": "high",
            "method": "pair+date",
        }
        for eid, fid, espn in MAP_ROWS
    ]


def _fixture_ids(cur) -> dict[int, str | None]:
    cur.execute("SELECT id, statpal_fixture_id FROM events ORDER BY id")
    return dict(cur.fetchall())


def _anchors(cur) -> dict[int, tuple]:
    cur.execute(
        "SELECT id, event_id, source, source_id, id_kind, first_seen_at "
        "FROM event_provider_anchors ORDER BY id"
    )
    return {r[0]: r for r in cur.fetchall()}


def _refusals(refused) -> dict[str, str]:
    return {r["our_event_id"]: reason for r, reason in refused}


@needs_postgres
class TestPlanRefusesEveryUnsafeRow:
    def test_the_seed_is_the_corpus_the_docstring_describes(self, conn):
        cur = conn.cursor()
        _seed(cur)
        assert _fixture_ids(cur)[206] == "2631512"
        assert _anchors(cur)[2][3] == "tennis:2631627"
        conn.rollback()

    def test_only_the_two_safe_rows_are_writable(self, conn):
        cur = conn.cursor()
        _seed(cur)
        writable, refused = script.plan(cur, _map_rows())
        assert sorted(w["event_id"] for w in writable) == [201, 202]
        assert set(_refusals(refused)) == {"203", "204", "205", "207", "209"}
        conn.rollback()

    def test_each_refusal_names_the_value_that_caused_it(self, conn):
        cur = conn.cursor()
        _seed(cur)
        _, refused = script.plan(cur, _map_rows())
        reasons = _refusals(refused)
        assert "espn_id disagrees" in reasons["203"]
        assert "999999" in reasons["203"]
        assert "already holds statpal_fixture_id" in reasons["204"]
        assert "2600000" in reasons["204"]
        assert "206 already holds this fixture id" in reasons["205"]
        assert "already names event 208" in reasons["207"]
        assert "not a tennis event" in reasons["209"]
        assert "baseball_mlb" in reasons["209"]
        conn.rollback()

    def test_a_refusal_writes_nothing(self, conn):
        """`plan` is read-only. A dry run that mutates is not a dry run."""
        cur = conn.cursor()
        _seed(cur)
        before_events, before_anchors = _fixture_ids(cur), _anchors(cur)
        script.plan(cur, _map_rows())
        assert _fixture_ids(cur) == before_events
        assert _anchors(cur) == before_anchors
        conn.rollback()

    def test_the_qualifier_written_is_the_id_space_not_the_sport_key(self, conn):
        """Both writable events are tennis under DIFFERENT `sports.key` values
        in the wider corpus; the key they claim is qualified by `tennis:`."""
        cur = conn.cursor()
        _seed(cur)
        writable, _ = script.plan(cur, _map_rows())
        assert {w["source_id"] for w in writable} == {
            "tennis:2631673",
            "tennis:2631734",
        }
        conn.rollback()


@needs_postgres
class TestApplyWritesBothShapes:
    def test_the_column_and_the_anchor_are_both_written(self, conn):
        cur = conn.cursor()
        _seed(cur)
        writable, _ = script.plan(cur, _map_rows())
        result = script.apply_links(cur, writable)

        assert _fixture_ids(cur)[201] == "2631673"
        anchors = _anchors(cur)
        new = [a for a in anchors.values() if a[3] == "tennis:2631673"]
        assert len(new) == 1 and new[0][1] == 201
        assert result["events_updated"] == 2
        assert result["anchors_written"] == 1, (
            "event 202's anchor already existed — ON CONFLICT DO NOTHING must "
            "make that a no-op rather than a second row"
        )
        conn.rollback()

    def test_an_anchor_without_its_column_would_be_stale_so_both_are_written(
        self, conn
    ):
        """The reason there are two writes at all (CERT-410 [P1]).

        `anchor_channel.anchor_is_current` re-derives the key from
        `events.statpal_fixture_id` and refuses any anchor that disagrees. An
        anchor over a NULL column is stale on arrival, so every event that got
        an anchor must also carry the bare id.

        Scoped to the ledger — the rows THIS RUN is responsible for. The seed
        deliberately contains a counter-example (`anchor_squatter`, event 208,
        `tennis:2631627` over a NULL column) because that is how event 207's
        claim gets refused, and it is a live demonstration that the table can
        hold a stale anchor. Asserting over the whole table would fail on that
        row and say nothing about the subject.
        """
        cur = conn.cursor()
        _seed(cur)
        writable, _ = script.plan(cur, _map_rows())
        script.apply_links(cur, writable)

        cur.execute(
            f"SELECT a.source_id, e.statpal_fixture_id "
            f"FROM {LEDGER_TABLE} b "
            f"JOIN event_provider_anchors a "
            f"  ON a.event_id = b.event_id AND a.source_id = b.anchor_source_id "
            f" AND a.source = 'statpal' AND a.id_kind = 'game' "
            f"JOIN events e ON e.id = a.event_id"
        )
        rows = cur.fetchall()
        assert len(rows) == len(writable), (
            "every ledger row must have its anchor — a zero-row scan would pass "
            "this test vacuously"
        )
        for source_id, column in rows:
            assert column is not None, f"{source_id} anchors a NULL column"
            assert source_id == f"tennis:{column}"
        conn.rollback()

    def test_the_ledger_is_written_before_the_first_mutation(self, conn):
        """A backup taken after the first write is a backup of the wrong state.

        Observed by its content, not by ordering the statements: the ledger's
        `statpal_fixture_id_before` must be the PRE-apply value (NULL), which it
        can only be if it was read before the UPDATE.
        """
        cur = conn.cursor()
        _seed(cur)
        writable, _ = script.plan(cur, _map_rows())
        script.apply_links(cur, writable)
        cur.execute(
            f"SELECT event_id, statpal_fixture_id_before, statpal_fixture_id_after, "
            f"anchor_source_id, anchor_existed_before FROM {LEDGER_TABLE} ORDER BY 1"
        )
        assert cur.fetchall() == [
            (201, None, "2631673", "tennis:2631673", False),
            (202, None, "2631734", "tennis:2631734", True),
        ]
        conn.rollback()

    def test_the_bystander_is_never_read_or_written(self, conn):
        cur = conn.cursor()
        _seed(cur)
        before = _anchors(cur)[3]
        writable, _ = script.plan(cur, _map_rows())
        script.apply_links(cur, writable)
        assert _anchors(cur)[3] == before
        conn.rollback()

    def test_applying_twice_is_idempotent(self, conn):
        cur = conn.cursor()
        _seed(cur)
        writable, _ = script.plan(cur, _map_rows())
        script.apply_links(cur, writable)
        after_first = (_fixture_ids(cur), _anchors(cur))

        writable2, refused2 = script.plan(cur, _map_rows())
        script.apply_links(cur, writable2)
        assert (_fixture_ids(cur), _anchors(cur)) == after_first
        assert sorted(w["event_id"] for w in writable2) == [201, 202], (
            "a re-plan after an apply must still see the same rows as writable — "
            "the preconditions accept the value they themselves wrote"
        )
        conn.rollback()


@needs_postgres
class TestRollbackUndoesExactlyWhatWasDone:
    def test_the_round_trip_leaves_the_table_byte_identical(self, conn):
        cur = conn.cursor()
        _seed(cur)
        before_events, before_anchors = _fixture_ids(cur), _anchors(cur)

        writable, _ = script.plan(cur, _map_rows())
        script.apply_links(cur, writable)
        result = script.rollback_links(cur)

        assert _fixture_ids(cur) == before_events
        assert _anchors(cur) == before_anchors
        assert result["still_applied"] == 0
        assert result["moved_on"] == 0
        conn.rollback()

    def test_an_anchor_that_predated_the_apply_survives_the_rollback(self, conn):
        """The precision `anchor_existed_before` buys.

        An undo that deletes by key would take event 202's pre-existing anchor
        with it — a change, not an undo, and one that would darken a channel the
        apply never touched.
        """
        cur = conn.cursor()
        _seed(cur)
        before = _anchors(cur)[1]
        writable, _ = script.plan(cur, _map_rows())
        script.apply_links(cur, writable)
        script.rollback_links(cur)

        assert _anchors(cur)[1] == before
        cur.execute(
            "SELECT count(*) FROM event_provider_anchors "
            "WHERE source_id = 'tennis:2631673'"
        )
        assert cur.fetchone()[0] == 0, "the anchor this run created must be gone"
        conn.rollback()

    def test_the_column_goes_back_to_null_not_to_empty_string(self, conn):
        cur = conn.cursor()
        _seed(cur)
        writable, _ = script.plan(cur, _map_rows())
        script.apply_links(cur, writable)
        script.rollback_links(cur)
        assert _fixture_ids(cur)[201] is None
        assert _fixture_ids(cur)[202] is None
        conn.rollback()

    def test_a_later_writer_is_never_overwritten_by_the_undo(self, conn):
        """If something else re-linked the row after the apply, that is not ours.

        The restore is scoped to rows that still hold the value this run wrote.
        A row that has moved on is reported as still-applied rather than being
        silently stamped back to NULL.
        """
        cur = conn.cursor()
        _seed(cur)
        writable, _ = script.plan(cur, _map_rows())
        script.apply_links(cur, writable)
        cur.execute(
            "UPDATE events SET statpal_fixture_id = '2999999' WHERE id = 201"
        )
        result = script.rollback_links(cur)
        assert _fixture_ids(cur)[201] == "2999999"
        assert result["moved_on"] == 1, (
            "a row the restore declined to touch is neither restored nor still "
            "applied — counting only those two states would report a clean undo "
            "over a row that never went back"
        )
        conn.rollback()

    def test_rollback_refuses_when_there_was_no_apply(self, conn):
        """"No ledger" must not read as "nothing needed restoring"."""
        cur = conn.cursor()
        _seed(cur)
        with pytest.raises(RuntimeError) as exc:
            script.rollback_links(cur)
        assert "no apply to roll back" in str(exc.value)
        conn.rollback()

    def test_a_partial_undo_is_reported_rather_than_called_clean(self, conn):
        """The post-condition is read from the data, not inferred from rowcounts.

        The delete arm is scoped to `a.event_id = b.event_id`, so an anchor that
        has been repointed at another event survives it — correctly, because it
        is no longer the row this run wrote. Both write statements then return a
        clean rowcount and nothing raises. That is precisely the shape CERT-847
        wore, so `still_applied` must come from a query over the data.
        """
        cur = conn.cursor()
        _seed(cur)
        writable, _ = script.plan(cur, _map_rows())
        script.apply_links(cur, writable)

        cur.execute(
            "UPDATE event_provider_anchors SET event_id = 209 "
            "WHERE source_id = 'tennis:2631673'"
        )
        result = script.rollback_links(cur)
        assert result["anchors_deleted"] == 0
        assert result["still_applied"] == 1, (
            "the anchor this run created is still in the table under a key the "
            "ledger claims — a clean rowcount must not report that as an undo"
        )
        conn.rollback()

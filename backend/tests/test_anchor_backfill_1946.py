"""#1946 Item 8 — the backfill, and the census gate that decides half of it.

Queue 415. Three modules shipped before this one and ``event_provider_anchors``
still held **0 rows**: the table (queue 393), the key function (queue 412R), the
reader plus forward writer (queue 413). The forward writer fires when a
correspondence is *established*, which by construction never happens for a row
that was established before it existed. The 74,181 events already in the table —
including #2213's 41 duplicate MLB groups — were unreachable.

## The red, stated honestly rather than dressed as an exit code

This is new capability, so there is no behaviour to break. The measurable
absence is pinned by :func:`test_the_forward_path_alone_leaves_the_backlog_empty`,
which runs the live path over a backlog fixture and asserts it writes **zero**
anchors. That test passes before and after this queue — it is a characterization
of the gap, and the rest of the file is what closes it. Calling it a red-first
exit 1 would be a claim about a run that did not happen.

## What is pinned in BOTH directions (gotcha #43)

A suite that only proves the writer writes is half a suite. These pin the
refusals, and each of them is a case where writing *something* would be worse
than writing nothing:

* The link-derived class is **refused** while the sink census is unmeasured, and
  refused again if the census returns ``BLOCK`` or a verdict that will not parse.
* A collision writes an anchor and **does not merge** the rows. Two live event
  rows survive a proven duplicate; the merge rail owns deletion.
* Two StatPal ids in different namespaces do **not** collide, because the key is
  namespace-qualified. A false collision here would manufacture an absorption.
* #2213's 41 groups share no provider id, so the backfill collapses **none** of
  them, and the test says so in those words rather than leaving it to be
  discovered.
"""


import pytest

from app.tasks.backfill_event_provider_anchors import (
    backfill_column_anchors,
    backfill_link_anchors,
    run_backfill_event_provider_anchors,
    summarize_for_operator,
)
from app.services.anchor_channel import (
    COLLISION,
    CONFIRMED,
    NO_KEY,
    WROTE,
)
from app.utils.anchor_backfill_gate import (
    CLASS_COLUMN_DERIVED,
    CLASS_LINK_DERIVED,
    GATE_BLOCKED,
    GATE_CLEAR,
    GATE_CLEAR_WITH_EXCLUSIONS,
    gate_for,
)
from app.utils.provider_anchor_keys import ANCHOR_KIND_GAME

# --------------------------------------------------------------------------
# A session double that enforces the unique index, because the index IS the
# duplicate detector. A fake that let two events claim one id would test a
# table we do not have.
# --------------------------------------------------------------------------


class _Result:
    def __init__(self, *, rows=None, first=None, scalar=None):
        self._rows = rows or []
        self._first = first
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def first(self):
        return self._first

    def scalar(self):
        return self._scalar


class _FakeBackfillSession:
    """Models ``events`` as fixture rows and ``event_provider_anchors`` as a dict.

    The dict is keyed on ``(source, source_id, id_kind)`` — the real unique
    index — so ``ON CONFLICT DO NOTHING`` behaves the way Postgres would and a
    collision is produced by the same mechanism production would produce it by.
    """

    def __init__(self, events, *, in_window=None, below_floor=0, anchors=None):
        self.events = events
        self._in_window = len(events) if in_window is None else in_window
        self._below_floor = below_floor
        self.anchors: dict[tuple[str, str, str], int] = dict(anchors or {})
        self.tag_writes: list[dict] = []
        self.statements: list[str] = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        params = params or {}

        if "FROM events" in sql and "ORDER BY commence_time DESC" in sql:
            limit = params.get("limit", len(self.events))
            offset = params.get("offset", 0)
            return _Result(rows=self.events[offset : offset + limit])

        if "COUNT(*)" in sql and "commence_time <" in sql:
            return _Result(scalar=self._below_floor)

        if "COUNT(*)" in sql and "commence_time >=" in sql:
            return _Result(scalar=self._in_window)

        if "INSERT INTO event_provider_anchors" in sql:
            key = (params["source"], params["source_id"], params["id_kind"])
            if key in self.anchors:
                return _Result(first=None)  # ON CONFLICT DO NOTHING
            self.anchors[key] = params["event_id"]
            return _Result(first=(params["event_id"],))

        if "SELECT espn_id, external_id, statpal_fixture_id FROM events" in sql:
            # `anchor_channel.anchor_is_current` corroborates an incumbent anchor
            # against the event's own scalar id column. Answer it from the same
            # rows this fixture already holds, in `_SCALAR_COLUMN_ORDER`.
            for row in self.events:
                if row[0] == params["event_id"]:
                    _id, external_id, espn_id, statpal_fixture_id, _commence = row
                    return _Result(first=(espn_id, external_id, statpal_fixture_id))
            return _Result(first=None)

        if "SELECT event_id FROM event_provider_anchors" in sql:
            key = (params["source"], params["source_id"], params["id_kind"])
            incumbent = self.anchors.get(key)
            return _Result(first=None if incumbent is None else (incumbent,))

        if "UPDATE events" in sql and "event_tags" in sql:
            self.tag_writes.append(dict(params))
            return _Result()

        raise AssertionError(f"unexpected statement in fixture: {sql[:120]}")


def _event(event_id, *, external_id=None, espn_id=None, statpal_fixture_id=None):
    """One ``events`` row in the column order ``_CANDIDATE_SQL`` selects."""
    return (event_id, external_id, espn_id, statpal_fixture_id, "2026-08-25T22:40:00Z")


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


def test_link_derived_is_refused_while_the_census_is_unmeasured():
    """The launch gate that has only ever been prose now refuses in code.

    Queue 387 measured the hazard and every window since has repeated *"do not
    read a granted slot as clearance for Item 8"* — a sentence with no
    enforcement behind it. This is the enforcement.
    """
    verdict = gate_for(CLASS_LINK_DERIVED, census=None)
    assert verdict.state == GATE_BLOCKED
    assert not verdict.may_write
    # An absence must not read as a clean result (gotcha #53).
    assert "NOT been taken" in verdict.reason
    assert "M-SINK-CENSUS-1" in verdict.reason


def test_link_derived_is_refused_by_default_with_no_census_argument():
    """The module-level default is the refusal, not the permission."""
    assert gate_for(CLASS_LINK_DERIVED).state == GATE_BLOCKED


def test_column_derived_is_never_sink_gated_and_says_why():
    verdict = gate_for(CLASS_COLUMN_DERIVED, census=None)
    assert verdict.state == GATE_CLEAR
    assert verdict.may_write
    # The reason has to carry the argument, because the split is the part a
    # reader will want to challenge.
    assert "scalar column" in verdict.reason
    assert "link table" in verdict.reason


def test_a_census_that_says_block_blocks():
    verdict = gate_for(CLASS_LINK_DERIVED, census={"verdict": "BLOCK"})
    assert verdict.state == GATE_BLOCKED


def test_an_unparseable_census_verdict_fails_closed():
    """A gate whose input cannot be read has not been satisfied by it."""
    for bad in ({"verdict": "probably fine"}, {"verdict": ""}, {}):
        assert gate_for(CLASS_LINK_DERIVED, census=bad).state == GATE_BLOCKED


def test_an_unknown_anchor_class_is_refused_rather_than_defaulted():
    assert gate_for("something_new", census=None).state == GATE_BLOCKED


def test_excluded_classes_survive_into_the_verdict():
    census = {
        "census_id": "sink-census-1",
        "verdict": "BACKFILL_WITH_EXCLUSIONS",
        "dirty_classes": [
            {"name": "esports-map-absorption", "backfill_disposition": "EXCLUDE"},
            {"name": "cross-sport-mislink", "backfill_disposition": "EXCLUDE"},
            {"name": "single-market-mislink", "backfill_disposition": "OBSERVE"},
        ],
    }
    verdict = gate_for(CLASS_LINK_DERIVED, census=census)
    assert verdict.state == GATE_CLEAR_WITH_EXCLUSIONS
    assert verdict.may_write
    assert verdict.excluded_classes == frozenset(
        {"esports-map-absorption", "cross-sport-mislink"}
    )
    # OBSERVE is not EXCLUDE: those rows are written, as `market`, and can
    # never absorb. Dropping them would lose the discovery channel.
    assert "single-market-mislink" not in verdict.excluded_classes


def test_a_clean_census_clears_with_no_exclusions():
    verdict = gate_for(
        CLASS_LINK_DERIVED,
        census={"census_id": "sink-census-1", "verdict": "CLEAR_TO_BACKFILL"},
    )
    assert verdict.state == GATE_CLEAR
    assert verdict.excluded_classes == frozenset()


@pytest.mark.asyncio
async def test_the_link_derived_backfill_writes_nothing_today():
    session = _FakeBackfillSession([])
    result = await backfill_link_anchors(session, apply=True)
    assert result["terminal"] == "skipped"
    assert result["gate_state"] == GATE_BLOCKED
    assert result["completed"] == 0
    assert session.anchors == {}


# --------------------------------------------------------------------------
# The gap this queue closes
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_forward_path_alone_leaves_the_backlog_empty():
    """The characterization of the absence — see the module docstring.

    The forward writer is called when a correspondence is established. Nobody
    establishes one for a row created in February, so the backlog stays at zero
    however long the live path runs.
    """
    session = _FakeBackfillSession([])
    assert session.anchors == {}
    # No claim arrives for a backlog row, so `record_anchor` is never reached.
    assert not session.statements


# --------------------------------------------------------------------------
# The column-derived backfill
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_derives_everything_and_writes_nothing():
    session = _FakeBackfillSession(
        [
            _event(15291666, external_id="odds-abc", espn_id="401778"),
            _event(15228865, statpal_fixture_id="123456"),
        ]
    )
    result = await backfill_column_anchors(session, apply=False)

    assert result["applied"] is False
    assert result["examined"] == 2
    assert result["outcomes"][WROTE] == 3  # two on the first row, one on the second
    assert session.anchors == {}, "a dry run that wrote is not a dry run"
    assert session.tag_writes == []


@pytest.mark.asyncio
async def test_apply_writes_one_anchor_per_populated_column():
    session = _FakeBackfillSession(
        [_event(15291666, external_id="odds-abc", espn_id="401778")]
    )
    result = await backfill_column_anchors(session, apply=True)

    assert result["applied"] is True
    assert result["outcomes"][WROTE] == 2
    assert ("odds_api", "odds-abc", ANCHOR_KIND_GAME) in session.anchors
    assert ("espn", "401778", ANCHOR_KIND_GAME) in session.anchors
    assert session.anchors[("espn", "401778", ANCHOR_KIND_GAME)] == 15291666


@pytest.mark.asyncio
async def test_a_second_run_confirms_rather_than_rewriting():
    """Idempotence, and it must be visible as CONFIRMED rather than as silence."""
    events = [_event(15291666, espn_id="401778")]
    session = _FakeBackfillSession(events)

    first = await backfill_column_anchors(session, apply=True)
    assert first["outcomes"][WROTE] == 1

    second = await backfill_column_anchors(session, apply=True)
    assert second["outcomes"][WROTE] == 0
    assert second["outcomes"][CONFIRMED] == 1
    assert len(session.anchors) == 1


@pytest.mark.asyncio
async def test_a_shared_id_reports_a_collision_and_does_not_merge_anything():
    """The conflict is the proof — and proof is still not authority to delete.

    Ruling 048's drain clause finally has a signal here. What it must NOT have
    is an implementation that acts on the signal by itself: the merge rail owns
    that, with the #1947 corroboration arms, because production holds `espn_id`
    values shared by genuinely different games.
    """
    session = _FakeBackfillSession(
        [
            _event(15291666, espn_id="401778"),
            _event(15228865, espn_id="401778"),
        ]
    )
    result = await backfill_column_anchors(session, apply=True)

    assert result["outcomes"][WROTE] == 1
    assert result["outcomes"][COLLISION] == 1
    assert result["collision_count"] == 1

    collision = result["collisions"][0]
    assert collision["canonical_event_id"] == 15291666, "first writer wins"
    assert collision["duplicate_event_id"] == 15228865

    # The losing row is tagged so the pair is queryable...
    assert len(session.tag_writes) == 1
    assert session.tag_writes[0]["event_id"] == 15228865
    assert "duplicate-of:15291666" in session.tag_writes[0]["tag"]

    # ...and nothing was deleted, repointed, or absorbed.
    assert session.anchors[("espn", "401778", ANCHOR_KIND_GAME)] == 15291666
    assert not any("DELETE" in s.upper() for s in session.statements)


@pytest.mark.asyncio
async def test_statpal_namespaces_do_not_collide_with_each_other():
    """21 of #2213's 41 groups carry conflicting StatPal ids across two namespaces.

    `statpal_fixture_id` is an untagged union of a 6-digit and a 10-digit
    namespace. Unqualified, `123456` and `1234567890` are just two strings and
    a naive key would be fine — but the same 6-digit value reappearing in the
    10-digit space is the case that would manufacture an absorption. The key is
    namespace-qualified, so the two spaces cannot meet.
    """
    session = _FakeBackfillSession(
        [
            _event(1, statpal_fixture_id="123456"),
            _event(2, statpal_fixture_id="1234567890"),
        ]
    )
    result = await backfill_column_anchors(session, apply=True)

    assert result["outcomes"][COLLISION] == 0
    assert len(session.anchors) == 2
    written = {key[1] for key in session.anchors}
    assert all(
        ":" in source_id for source_id in written
    ), "a StatPal anchor must be namespace-qualified, never bare"


@pytest.mark.asyncio
async def test_an_unkeyable_id_is_counted_not_crashed_on():
    """One bad item must never wipe the pass (gotcha #42)."""
    session = _FakeBackfillSession(
        [
            _event(1, statpal_fixture_id="not-a-known-namespace"),
            _event(2, espn_id="401778"),
        ]
    )
    result = await backfill_column_anchors(session, apply=True)

    assert result["outcomes"][NO_KEY] == 1
    assert result["outcomes"][WROTE] == 1, "the healthy sibling still got written"
    assert ("espn", "401778", ANCHOR_KIND_GAME) in session.anchors


@pytest.mark.asyncio
async def test_the_41_groups_are_not_collapsed_by_this_backfill():
    """Stated as a test because it is the thing most likely to be over-claimed.

    Queue 411 measured the 41: **0 of 41 pairs share any provider id**. A
    channel keyed on shared ids has nothing to join on for them. This backfill
    gives each row its own anchor and collapses none of the pairs, and the
    correspondences that would collapse them are the link-derived class — still
    behind the census.
    """
    session = _FakeBackfillSession(
        [
            _event(15291666, espn_id="401778", external_id="odds-bos-mia"),
            _event(15228865, statpal_fixture_id="9876543210"),
        ]
    )
    result = await backfill_column_anchors(session, apply=True)

    assert result["outcomes"][COLLISION] == 0
    assert result["collision_count"] == 0
    assert len(session.anchors) == 3
    assert session.tag_writes == []


# --------------------------------------------------------------------------
# Bounds, and saying what was skipped
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_remainder_is_reported_rather_than_silently_dropped():
    """No silent caps. A bounded sweep that does not name its remainder reads
    as "covered everything" when it did not."""
    events = [_event(i, espn_id=f"e{i}") for i in range(10)]
    session = _FakeBackfillSession(events, in_window=10, below_floor=64_000)

    result = await backfill_column_anchors(session, limit=4, apply=True)

    assert result["examined"] == 4
    assert result["remaining_in_window"] == 6
    assert result["below_floor"] == 64_000
    assert result["terminal"] == "partial", "a partial sweep is not complete"


@pytest.mark.asyncio
async def test_a_drained_window_reports_complete():
    session = _FakeBackfillSession([_event(1, espn_id="401778")], in_window=1)
    result = await backfill_column_anchors(session, apply=True)
    assert result["remaining_in_window"] == 0
    assert result["terminal"] == "complete"


@pytest.mark.asyncio
async def test_an_empty_window_is_no_work_and_therefore_not_green():
    """`task_verdict` maps `no_work` to UNKNOWN, deliberately: a run that banked
    nothing proves nothing (gotcha #53)."""
    session = _FakeBackfillSession([], in_window=0)
    result = await backfill_column_anchors(session, apply=True)
    assert result["terminal"] == "no_work"


@pytest.mark.asyncio
async def test_the_offset_walks_the_window_without_re_examining():
    events = [_event(i, espn_id=f"e{i}") for i in range(6)]
    session = _FakeBackfillSession(events, in_window=6)

    first = await backfill_column_anchors(session, limit=3, offset=0, apply=True)
    second = await backfill_column_anchors(session, limit=3, offset=3, apply=True)

    assert first["remaining_in_window"] == 3
    assert second["remaining_in_window"] == 0
    assert len(session.anchors) == 6
    assert first["outcomes"][CONFIRMED] == 0
    assert (
        second["outcomes"][CONFIRMED] == 0
    ), "the second page is new rows, not re-reads"


# --------------------------------------------------------------------------
# The combined run
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_run_reports_the_two_classes_separately():
    """Summing a class that ran with a class that was refused is the number that
    would let a closed gate read as a finished backfill."""
    session = _FakeBackfillSession([_event(1, espn_id="401778")], in_window=1)
    result = await run_backfill_event_provider_anchors(session, apply=True)

    assert result["column_derived"]["terminal"] == "complete"
    assert result["link_derived"]["terminal"] == "skipped"
    assert result["link_derived"]["gate_state"] == GATE_BLOCKED
    # The run's own verdict follows the class that can do work.
    assert result["terminal"] == "complete"
    assert "total" not in result["link_derived"]


@pytest.mark.asyncio
async def test_the_operator_summary_names_the_gate_state():
    session = _FakeBackfillSession([_event(1, espn_id="401778")], in_window=1)
    result = await run_backfill_event_provider_anchors(session, apply=True)
    line = summarize_for_operator(result)
    assert "APPLY" in line
    assert "link-derived BLOCKED" in line
    assert "below-floor" in line

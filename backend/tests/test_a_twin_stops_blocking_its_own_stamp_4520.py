"""#4520: the duplicate that prevented the stamp that would have drained it.

## the deadlock, as production held it

`stamp_mlb_statpal_fixtures` runs hourly and, on the 2026-09-12 09:21Z pass,
stamped **0** rows and called **24** MLB fixtures `AMBIGUOUS`. Every one of those
24 was a game we hold twice: a StatPal-created row carrying
`statpal_fixture_id`, beside an ESPN-created row carrying `espn_id`, an odds id
and the snapshots, and holding no StatPal id at all.

`merge_duplicate_events` is what drains duplicates, and under ruling 048 it will
only destroy a row when the pair SHARES a provider id
(`event_merge_invariant.PROVIDER_ID_COLUMNS`). Pre-merge the two halves share
nothing, so it refuses — correctly — 48 times a day. And the stamper, which is
the one pass that could give them a shared id, refused too, because two rows
matched and two rows looked like a duplicate it must not resolve (D35).

So each half blocked the other and the twin was permanent. A reader searching
`yankees` got four rows for two games; the Red Sox slate of 2026-09-12 was in
the population, which is ship 3's own bar.

## what changed, and what deliberately did not

`classify_fixture` now separates "two rows and no way to tell them apart" from
"two rows, one of which ALREADY holds this contest's id". The second is not the
ambiguity `AMBIGUOUS` names: the column answers the question the verdict exists
to ask. The write goes to the other row, and nothing here merges or deletes
anything — `merge_duplicate_events` decides that, under its own guards.

Measured before the rule was written, over the 24 production `AMBIGUOUS`
receipts of that pass:

    shape (candidates, holding THIS id, holding none)      count
    (2, 1, 1)  -- the resolvable twin                        20
    (2, 2, 0)  -- both already hold it; nothing to write       4
    (2, 0, 2)  -- the genuine coin flip                        0

The predicate admits the first and refuses the rest, and the shapes it refuses
are asserted below one at a time. 19 of those 20 become merge candidates the
moment the id is shared; the 20th is held back by `St.Louis` vs `St. Louis` in
the MERGE's name arms, which is not this lane's file.

## what these tests fail on

* the twin rule widening to any shape it was not measured against — three rows,
  a row holding a different id, two rows holding nothing;
* the write going to the row that already holds the id instead of the one that
  does not, which would write nothing and hide it as success;
* an anchor being written on the twin path. It must not be: the anchor already
  names the other half, so `record_anchor` would return `COLLISION`, the column
  write would roll back and the stamp would be inert — and the collision path
  tags the LOSING row, which here is the row the merge keeps;
* the D35 refusal being lost for the shapes it still governs.
"""

from __future__ import annotations

import json
from datetime import timedelta
from importlib import import_module
from pathlib import Path

import pytest

from app.services.statpal_api import StatPalAPIService
from app.tasks.stamp_v1_statpal_fixtures import (
    VERDICT_AMBIGUOUS,
    VERDICT_STAMP,
    VERDICT_STAMP_TWIN,
    classify_fixture,
)

task = import_module("app.tasks.stamp_v1_statpal_fixtures")

FIXTURES = Path(__file__).parent / "fixtures"
CENSUS_SCHEDULE = FIXTURES / "statpal_mlb_season_schedule_20260904_fullcensus.json"

#: A real MLB contest out of the pinned season-schedule payload, so the fixture
#: under test is one StatPal actually served rather than one shaped to pass.
def _contest():
    service = StatPalAPIService(api_key="test")
    fixtures = service._parse_v1_season_schedule(
        json.loads(CENSUS_SCHEDULE.read_text()), "mlb"
    )
    return next(f for f in fixtures if f.start_time is not None)


def _row(event_id, fixture, *, statpal_fixture_id=None, offset=timedelta(0)):
    """One of our event rows, in the shape the candidate pool holds."""
    return {
        "id": event_id,
        "home": fixture.home_team,
        "away": fixture.away_team,
        "commence_time": fixture.start_time + offset,
        "statpal_fixture_id": statpal_fixture_id,
        "status": "scheduled",
    }


# ---------------------------------------------------------------------------
# the decision
# ---------------------------------------------------------------------------


def test_the_twin_of_an_already_identified_row_is_stamped_not_filed():
    """The production shape: one row holds the id, the other holds nothing.

    Both halves of the assertion matter. "Not AMBIGUOUS" is satisfied by any
    other verdict, and "the id-holder is not the target" is satisfied by writing
    nowhere at all — so the target is named positively.
    """
    fixture = _contest()
    identified = _row(15305549, fixture, statpal_fixture_id=fixture.fixture_id)
    unlinked = _row(15310368, fixture)

    verdict, matches = classify_fixture(fixture, [identified, unlinked])

    assert verdict == VERDICT_STAMP_TWIN
    # matches[0] is what the caller writes to.
    assert matches[0]["id"] == 15310368
    assert matches[0]["statpal_fixture_id"] is None
    assert matches[1]["id"] == 15305549


def test_the_write_target_does_not_depend_on_which_row_the_pool_lists_first():
    """Pool order is a query artefact, not evidence. Both orders, same answer."""
    fixture = _contest()
    identified = _row(15305549, fixture, statpal_fixture_id=fixture.fixture_id)
    unlinked = _row(15310368, fixture)

    for pool in ([identified, unlinked], [unlinked, identified]):
        verdict, matches = classify_fixture(fixture, pool)
        assert verdict == VERDICT_STAMP_TWIN
        assert matches[0]["id"] == 15310368


def test_a_twin_five_minutes_apart_is_still_the_same_contest():
    """One of the 20 sits at a 300-second gap, not 0. The window decides that,
    and the id decides which row is the contest."""
    fixture = _contest()
    identified = _row(15304890, fixture, statpal_fixture_id=fixture.fixture_id)
    unlinked = _row(15309655, fixture, offset=timedelta(minutes=5))

    verdict, matches = classify_fixture(fixture, [identified, unlinked])

    assert verdict == VERDICT_STAMP_TWIN
    assert matches[0]["id"] == 15309655


def test_two_rows_holding_nothing_are_still_refused():
    """D35's rule, unchanged, on the shape it was written for.

    Nothing distinguishes these two rows, so choosing one is a coin flip. The
    production census found ZERO of this shape among the 24; it is refused on
    principle rather than because it is rare.
    """
    fixture = _contest()
    verdict, matches = classify_fixture(
        fixture, [_row(101, fixture), _row(102, fixture)]
    )

    assert verdict == VERDICT_AMBIGUOUS
    assert {m["id"] for m in matches} == {101, 102}


def test_a_row_holding_a_different_contests_id_is_refused():
    """Two rows disagreeing about which contest they are is a bigger finding
    than a missing stamp, and stamping the other one would bury it."""
    fixture = _contest()
    other = str(int(fixture.fixture_id) + 1)
    verdict, matches = classify_fixture(
        fixture,
        [_row(101, fixture, statpal_fixture_id=other), _row(102, fixture)],
    )

    assert verdict == VERDICT_AMBIGUOUS
    assert {m["id"] for m in matches} == {101, 102}


def test_two_rows_that_both_already_hold_this_id_are_refused():
    """The four `St.Louis` pairs. They already share the id, so there is nothing
    for this task to write; they are the MERGE's to drain and it is refusing
    them for an unrelated reason (its name arms), which is not repaired here."""
    fixture = _contest()
    verdict, matches = classify_fixture(
        fixture,
        [
            _row(101, fixture, statpal_fixture_id=fixture.fixture_id),
            _row(102, fixture, statpal_fixture_id=fixture.fixture_id),
        ],
    )

    assert verdict == VERDICT_AMBIGUOUS
    assert {m["id"] for m in matches} == {101, 102}


def test_three_rows_are_refused_even_when_one_holds_the_id():
    """A shape the census never produced. A rule written before the shape
    existed does not get to absorb it silently."""
    fixture = _contest()
    verdict, matches = classify_fixture(
        fixture,
        [
            _row(101, fixture, statpal_fixture_id=fixture.fixture_id),
            _row(102, fixture),
            _row(103, fixture, offset=timedelta(minutes=2)),
        ],
    )

    assert verdict == VERDICT_AMBIGUOUS
    assert len(matches) == 3


def test_a_third_row_holding_a_different_id_still_refuses_the_pair():
    """Three rows, of which exactly one holds this id and exactly one holds
    nothing — so every per-row count the rule checks is satisfied and only the
    SIZE of the candidate set refuses it.

    Written because without this input the size check and the per-row checks
    cover for each other: on a plain three-row set both refuse, so either could
    be deleted and every other test here would still pass.
    """
    fixture = _contest()
    other = str(int(fixture.fixture_id) + 1)
    verdict, matches = classify_fixture(
        fixture,
        [
            _row(101, fixture, statpal_fixture_id=fixture.fixture_id),
            _row(102, fixture),
            _row(103, fixture, statpal_fixture_id=other, offset=timedelta(minutes=2)),
        ],
    )

    assert verdict == VERDICT_AMBIGUOUS
    assert len(matches) == 3


def test_the_id_holders_partner_must_hold_nothing_not_merely_something_else():
    """Two rows, one holding this contest, one holding a DIFFERENT contest.

    There is no row to write to — the second is already claimed by another
    contest — and that is a contradiction between two rows, not a twin. The
    counterpart to the three-row case above: here the set is the right size and
    only the per-row count refuses it.
    """
    fixture = _contest()
    other = str(int(fixture.fixture_id) + 1)
    verdict, matches = classify_fixture(
        fixture,
        [
            _row(101, fixture, statpal_fixture_id=fixture.fixture_id),
            _row(102, fixture, statpal_fixture_id=other),
        ],
    )

    assert verdict == VERDICT_AMBIGUOUS
    assert {m["id"] for m in matches} == {101, 102}


def test_a_blank_contest_id_cannot_make_a_row_its_own_twin():
    """With no id to match on, a row holding `""` satisfies BOTH sides of the
    rule — it reads as the identified row and as the unstamped one — and the
    pair would be that single row twice. Refused before the question is asked,
    which is what keeps the two sides disjoint."""
    fixture = _contest()
    fixture.fixture_id = ""
    verdict, _ = classify_fixture(
        fixture,
        [
            _row(101, fixture, statpal_fixture_id=""),
            _row(102, fixture, statpal_fixture_id="999"),
        ],
    )
    assert verdict == VERDICT_AMBIGUOUS


def test_one_row_is_still_an_ordinary_stamp():
    """The twin rule must not capture the single-candidate path it sits above."""
    fixture = _contest()
    assert classify_fixture(fixture, [_row(101, fixture)]) == (
        VERDICT_STAMP,
        [_row(101, fixture)],
    )


def test_a_blank_contest_id_never_matches_a_row_holding_blank():
    """`None == None` would make every unstamped pair a twin of every other."""
    fixture = _contest()
    fixture.fixture_id = ""
    verdict, _ = classify_fixture(
        fixture, [_row(101, fixture), _row(102, fixture)]
    )
    assert verdict == VERDICT_AMBIGUOUS


# ---------------------------------------------------------------------------
# the write
# ---------------------------------------------------------------------------


class _RecordingSession:
    """Answers only `SET_FIXTURE_ID`. Anything else is a change worth failing on.

    A fake that quietly returns "no rows" to a statement it does not recognise
    turns a real change in the task into a green test (gotcha #53).
    """

    def __init__(self, rowcount=1):
        self._rowcount = rowcount
        self.updates: list[dict] = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        if sql == task.SET_FIXTURE_ID:
            self.updates.append(dict(params or {}))

            class _Result:
                rowcount = self._rowcount

            return _Result()
        raise AssertionError(
            "the twin write executed a statement this guard does not know:\n"
            f"{sql}\nAdd it here deliberately — do not let it return nothing."
        )


@pytest.mark.asyncio
async def test_the_twin_write_sets_the_column_on_the_row_that_holds_nothing():
    fixture = _contest()
    session = _RecordingSession()

    won = await task._write_twin_column(
        session, fixture, _row(15310368, fixture)
    )

    assert won is True
    assert session.updates == [
        {"event_id": 15310368, "fixture_id": fixture.fixture_id}
    ]


@pytest.mark.asyncio
async def test_the_twin_write_never_writes_an_anchor(monkeypatch):
    """The anchor already names the other half of the pair.

    Writing one here returns `COLLISION`, which is not committable, so the
    column write would roll back and the whole stamp would be inert — and the
    collision path tags the losing row, which is the row the merge KEEPS. This
    is asserted by making any anchor write fail loudly rather than by reading
    the current implementation, so a later edit that adds one is caught.
    """

    async def _explode(*args, **kwargs):
        raise AssertionError("the twin path wrote an anchor")

    monkeypatch.setattr(task, "record_anchor", _explode)

    session = _RecordingSession()
    assert await task._write_twin_column(session, _contest(), _row(1, _contest()))


@pytest.mark.asyncio
async def test_a_column_claimed_by_another_pass_is_not_reported_as_written():
    """The UPDATE is guarded by `statpal_fixture_id IS NULL`, so a racing pass
    makes it touch no row. That is a lost race, not a write."""
    session = _RecordingSession(rowcount=0)
    assert (
        await task._write_twin_column(session, _contest(), _row(1, _contest()))
        is False
    )


# ---------------------------------------------------------------------------
# the receipt
# ---------------------------------------------------------------------------


def test_the_summary_counts_twin_stamps_separately():
    """`stamped_twins` is a subset of `stamped`, not a sibling: these are
    ordinary column writes and every consumer of `stamped` should keep seeing
    them. It is listed apart because the CONSEQUENCE is not ordinary — the pair
    now shares an id, so the merge can delete one of the two rows."""
    run = task.StampRun(sport_key="baseball_mlb")
    run.stamped = 3
    run.stamped_twins.append({"statpal_id": "364963", "event_id": 15310368})

    summary = run.summary()

    assert summary["stamped"] == 3
    assert summary["stamped_twins"] == 1
    assert run.summary()["ambiguous"] == 0

"""The synthesized settlement point stops being stamped with the clock (#6360).

`_apply_settled_winner_freeze` draws a graded champion's line up to 1.0 by
synthesizing a terminal chart point (#1177). Its timestamp was
`min(resolution_date, now)`, and `resolution_date` is a SCHEDULE that Kalshi
routinely leaves in the FUTURE for a settled market (gotcha #14) — so the clamp
returned `now` and the champion's dot sat at the moment of the request, moving
on every read. Measured on production 2026-09-15 on `/api/futures/58675941`
(Vuelta a España 2026, settled 14 September): the point came back at
`11:32:56Z`, then at `11:33:24Z` 28 seconds later.

The ladder that replaces it lives in `app/utils/settlement_stamp.py`; these
tests pin each of its four arms, the two refusals that keep a future or
non-datetime witness out, and — the controls — that the 593,549 markets sitting
on a past `resolution_date` and every existing freeze behaviour are untouched.
"""

import ast
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from app.routes.futures import _apply_settled_winner_freeze
from app.utils.settlement_stamp import (
    BASIS_CLOCK,
    BASIS_LAST_OBSERVATION,
    BASIS_RESOLUTION_DATE,
    BASIS_SETTLED_AT,
    as_past_utc,
    last_charted_timestamp,
    settled_point_timestamp,
)

# ── THE ANCHOR, AND WHY IT IS NOT A LITERAL (#7611) ──────────────────────────
#
# This used to be `datetime(2026, 9, 15, 11, 33, 24, tzinfo=timezone.utc)`, with
# the comment "a fixed clock … nothing branches on the real time (gotcha #44)".
# The comment was half true and the half it missed turned master red.
#
# Nothing here branches. But `TestTheFreezeOnTheSpecimenShape` and
# `TestControlsThatMustHoldBothSidesOfThisChange` do not call the pure ladder —
# they call `_apply_settled_winner_freeze`, which reads the REAL clock
# (`routes/futures.py:172`) and hands it to `settled_point_timestamp`. So those
# cases ran against TWO clocks: their specimens were built against the frozen
# one and graded against the moving one. Their whole subject is a
# `resolution_date` that is still in the FUTURE — the Kalshi schedule of gotcha
# #14 — and a future built by adding to a fixed past instant has an expiry date.
#
# `NOW + timedelta(days=5, hours=10)` was 2026-09-20T21:33:24Z. Real time
# reached it, arm 1 of the ladder started matching, and
# `test_the_champions_dot_lands_on_the_data_not_on_the_clock` failed for every
# lane on master from that second onward — a literal in the past stays in the
# past. `NOW + timedelta(days=6)` (four more cases) was due to detonate at
# 2026-09-21T11:33:24Z, which is why this is fixed at the anchor and not at the
# one assertion that happened to go first.
#
# Offset from the clock, no branch, no truncation — the shape gotcha #44
# prescribes. `TestTheAnchorCannotAgeOut` below holds both halves of the rule so
# the next edit cannot quietly re-pin it.

#: The shortest FORWARD offset any specimen in this file uses — the Vuelta's
#: `resolution_date`. Every "future schedule" case depends on the clock not
#: having reached it, so this is the ceiling on how far back the anchor may sit.
SHORTEST_FUTURE_OFFSET = timedelta(days=5, hours=10)

#: How far behind the real clock the anchor sits. One day: comfortably under the
#: ceiling above (so a future schedule is still ≥4d10h out whenever the suite
#: runs) and comfortably over zero (so `NOW` reads as a past instant, which is
#: what every backward offset and every `as_past_utc` case assumes). Change it
#: freely — the guard is written against THIS name, not against "one day".
ANCHOR_LAG = timedelta(days=1)

#: The instant this module was imported, kept so the guard below can assert the
#: RELATIONSHIP between it and `NOW` instead of comparing `NOW` to a clock that
#: has moved on since.
#:
#: 🔴 THE FIRST DRAFT OF THAT GUARD FAILED CI ON THIS VERY BRANCH, and the
#: failure is worth more than the guard. It read
#: `abs((datetime.now(utc) - NOW) - ANCHOR_LAG) < 5 minutes`. Alone, that passes
#: — the file runs in a second. Inside the real shard it ran **11 minutes after
#: this module was imported**, because a 14,000-test shard imports its modules
#: at collection and gets to any one test much later. So the assertion was not
#: measuring the anchor at all; it was measuring HOW LONG THE SUITE HAD BEEN
#: RUNNING, and the failure message accused a correct anchor of being a literal.
#: Stamping the import instant removes the clock from the comparison entirely,
#: so no suite duration can move it.
_IMPORTED_AT = datetime.now(timezone.utc)

NOW = _IMPORTED_AT - ANCHOR_LAG


def _outcome(oid, name, prob=0.5, is_winner=False):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.current_probability = prob
    o.is_winner = is_winner
    return o


def _market(outcomes, resolution_date=None, settled_at=None, mutually_exclusive=True):
    m = MagicMock()
    m.id = 58675941
    m.name = "Vuelta a Espana 2026: Winner"
    m.market_metadata = None
    m.resolution_date = resolution_date
    m.settled_at = settled_at
    m.outcomes = outcomes
    # #7921 — SET EXPLICITLY, because a bare MagicMock auto-creates this
    # attribute as a truthy Mock. The co-winner gate reads it, and an unset
    # attribute would make these tests pass down the "we do not know" arm while
    # reading as if they had exercised the mutually-exclusive one.
    m.mutually_exclusive = mutually_exclusive
    return m


def _series(oid, name, points):
    return {
        "outcome_id": oid,
        "name": name,
        "history": [
            {"timestamp": ts.isoformat(), "probability": p,
             "american_odds": None, "bookmaker": "consensus"}
            for ts, p in points
        ],
        "eliminated": False,
        "eliminated_at": None,
    }


def _stamp_of(entry):
    return datetime.fromisoformat(entry["history"][-1]["timestamp"])


def _source_line(prefix: str) -> str:
    for line in Path(__file__).read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line
    raise AssertionError(f"no `{prefix}` assignment found in this module")


def _anchor_source_line() -> str:
    return _source_line("NOW = ")


def _future_offsets_graded_against_the_real_clock() -> list[timedelta]:
    """Every `NOW + timedelta(...)` inside a class that calls the real-clock freeze.

    The distinction matters and cannot be made by eye. `TestTheLadder` passes
    `now=NOW` into the pure ladder, so a `NOW + timedelta(minutes=5)` there is
    five minutes after a value it also supplies — it can never expire. The
    classes that call `_apply_settled_winner_freeze` get the REAL clock instead
    (`routes/futures.py:172`), so every forward offset in them is a promise
    about wall time. Only those are collected, and they are found by looking for
    that call rather than by naming the classes, so a third such class inherits
    the guard without anyone remembering to add it.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    offsets: list[timedelta] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        called = {
            n.func.id
            for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        if "_apply_settled_winner_freeze" not in called:
            continue
        for n in ast.walk(node):
            if (
                isinstance(n, ast.BinOp)
                and isinstance(n.op, ast.Add)
                and isinstance(n.left, ast.Name)
                and n.left.id == "NOW"
                and isinstance(n.right, ast.Call)
                and isinstance(n.right.func, ast.Name)
                and n.right.func.id == "timedelta"
            ):
                offsets.append(
                    timedelta(**{k.arg: ast.literal_eval(k.value) for k in n.right.keywords})
                )
    return offsets


class TestTheAnchorCannotAgeOut:
    """#7611 — the guard on this file's own anchor, not on the code under test.

    The defect was never in an assertion; it was in `NOW`. So the guard is
    aimed there. A test that only re-pinned the one expectation that went red
    would have passed all day on 2026-09-20 and gone red again at 11:33Z the
    next morning, when the four `NOW + timedelta(days=6)` cases came due.

    These two assertions fail on ANY re-pinned literal within hours of it being
    written, and they name the reason in the failure rather than leaving the
    next reader to derive it from a datetime subtraction, which is how the
    original cost a day of every lane's merges.
    """

    def test_the_anchor_is_derived_in_the_source_rather_than_typed_out(self):
        """The decisive one: a literal fails this the second it is written.

        The drift check below only notices a re-pinned literal once the clock
        has moved away from it, so a datetime typed a minute ago satisfies it.
        Reading the assignment itself closes that window.
        """
        stamp = _source_line("_IMPORTED_AT = ")
        anchor = _anchor_source_line()
        assert "datetime.now(" in stamp, (
            f"the import instant must come from the clock; it reads `{stamp}`. "
            "See #7611 — this file's previous anchor was a literal and master "
            "went red for every lane the second real time reached it."
        )
        for line in (stamp, anchor):
            assert not re.search(r"datetime\(\s*\d{4}", line), (
                f"this line names an instant: `{line}`. A datetime literal in "
                "the anchor is a dated bomb, not a fixed clock (gotcha #44). "
                "See #7611."
            )

    def test_the_declared_ceiling_is_the_real_shortest_future_offset(self):
        """And it is read off the specimens, so a new short one cannot slip in."""
        offsets = _future_offsets_graded_against_the_real_clock()
        assert offsets, (
            "found no `NOW + timedelta(...)` specimens in the classes that call "
            "`_apply_settled_winner_freeze` — either they were renamed or this "
            "guard has stopped measuring anything. See #7611."
        )
        assert SHORTEST_FUTURE_OFFSET <= min(offsets), (
            f"SHORTEST_FUTURE_OFFSET is {SHORTEST_FUTURE_OFFSET} but the "
            f"shortest specimen actually used is {min(offsets)}. The ceiling "
            "ANCHOR_LAG is checked against would then be too generous and the "
            "shortest specimen could expire under it. See #7611."
        )

    def test_the_anchor_is_exactly_its_declared_lag_behind_the_import_instant(self):
        """Exact, and with no clock in it — so no suite duration can move it.

        The version of this that read `datetime.now(utc) - NOW` against a
        five-minute tolerance was measuring how long the shard had been running,
        not the anchor, and it reddened CI on a correct anchor eleven minutes
        into the run. See the note beside `_IMPORTED_AT`.
        """
        assert NOW == _IMPORTED_AT - ANCHOR_LAG, (
            f"NOW ({NOW}) must be exactly ANCHOR_LAG ({ANCHOR_LAG}) behind the "
            f"import instant ({_IMPORTED_AT}). Any value written down by hand "
            "misses this by the width of a datetime. See #7611."
        )

    def test_the_anchor_leaves_room_for_this_files_future_schedules(self):
        """Pure arithmetic on the two constants — no clock, so it cannot flake."""
        assert timedelta(0) < ANCHOR_LAG < SHORTEST_FUTURE_OFFSET, (
            f"ANCHOR_LAG ({ANCHOR_LAG}) must sit strictly between zero and the "
            f"shortest forward offset in this file ({SHORTEST_FUTURE_OFFSET}). "
            "Below zero the anchor is not a past instant; above the ceiling the "
            "`resolution_date` specimens stop being future schedules and arm 1 "
            "of the ladder starts matching. See #7611."
        )

    def test_every_future_schedule_specimen_is_still_in_the_future(self):
        real = datetime.now(timezone.utc)
        assert NOW < real, "the anchor must be a past instant"
        assert NOW + SHORTEST_FUTURE_OFFSET > real, (
            "the `resolution_date` specimens in this file are Kalshi schedules "
            "that have NOT yet arrived (gotcha #14) — that is the arm under "
            "test. Once the clock passes them, arm 1 of the ladder starts "
            "matching and the specimens stop testing what they name. See #7611."
        )


class TestTheLadder:
    """`settled_point_timestamp` — one test per arm, asserting the BASIS too."""

    def test_a_past_resolution_date_still_wins_and_that_is_the_unchanged_arm(self):
        rd = NOW - timedelta(days=3)
        ts, basis = settled_point_timestamp(
            resolution_date=rd,
            last_observed=NOW - timedelta(hours=1),
            settled_at=NOW - timedelta(hours=2),
            now=NOW,
        )
        assert (ts, basis) == (rd, BASIS_RESOLUTION_DATE)

    def test_a_future_resolution_date_is_skipped_for_the_last_real_observation(self):
        """The Vuelta shape: rd is six days out, so the schedule is no witness."""
        observed = NOW - timedelta(days=1, hours=6)
        ts, basis = settled_point_timestamp(
            resolution_date=NOW + timedelta(days=6),
            last_observed=observed,
            settled_at=NOW - timedelta(hours=22),
            now=NOW,
        )
        assert (ts, basis) == (observed, BASIS_LAST_OBSERVATION)

    def test_settled_at_answers_only_when_there_is_no_schedule_and_no_chart(self):
        settled = NOW - timedelta(days=30)
        ts, basis = settled_point_timestamp(
            resolution_date=None, last_observed=None, settled_at=settled, now=NOW
        )
        assert (ts, basis) == (settled, BASIS_SETTLED_AT)

    def test_the_clock_is_reached_only_when_the_row_holds_no_evidence_at_all(self):
        ts, basis = settled_point_timestamp(
            resolution_date=None, last_observed=None, settled_at=None, now=NOW
        )
        assert (ts, basis) == (NOW, BASIS_CLOCK)

    def test_a_future_settled_at_is_refused_rather_than_clamped(self):
        """Clamping a future witness into the present is the whole defect."""
        ts, basis = settled_point_timestamp(
            resolution_date=NOW + timedelta(days=6),
            last_observed=None,
            settled_at=NOW + timedelta(minutes=5),
            now=NOW,
        )
        assert (ts, basis) == (NOW, BASIS_CLOCK)


class TestWitnessCoercion:
    def test_a_naive_datetime_is_read_as_utc_rather_than_dropped(self):
        naive = (NOW - timedelta(hours=4)).replace(tzinfo=None)
        assert as_past_utc(naive, NOW) == NOW - timedelta(hours=4)

    def test_a_non_datetime_witness_is_refused(self):
        """ORM rows and test doubles both reach here; a MagicMock is not a time."""
        assert as_past_utc(MagicMock(), NOW) is None
        assert as_past_utc("2026-09-14T11:31:56Z", NOW) is None
        assert as_past_utc(None, NOW) is None

    def test_a_witness_exactly_at_now_is_accepted(self):
        assert as_past_utc(NOW, NOW) == NOW


class TestLastChartedTimestamp:
    def test_it_is_the_max_across_every_series(self):
        oh = {
            1: _series(1, "A", [(NOW - timedelta(days=5), 0.2), (NOW - timedelta(days=2), 0.3)]),
            2: _series(2, "B", [(NOW - timedelta(days=4), 0.1), (NOW - timedelta(days=1), 0.4)]),
        }
        assert last_charted_timestamp(oh) == NOW - timedelta(days=1)

    def test_empty_and_malformed_series_are_skipped_not_raised_on(self):
        oh = {
            1: _series(1, "A", []),
            2: {"outcome_id": 2, "name": "B",
                "history": [{"timestamp": "not-a-time", "probability": 0.5}]},
            3: _series(3, "C", [(NOW - timedelta(days=9), 0.7)]),
        }
        assert last_charted_timestamp(oh) == NOW - timedelta(days=9)

    def test_no_chart_at_all_is_none(self):
        assert last_charted_timestamp({}) is None
        assert last_charted_timestamp(None) is None


class TestTheFreezeOnTheSpecimenShape:
    """End-to-end on the Vuelta's shape: settled market, future `resolution_date`."""

    def _vuelta(self):
        champ = _outcome(229691385, "Other", prob=1.0, is_winner=True)
        rider = _outcome(229691386, "Tadej Pogacar", prob=0.0)
        market = _market(
            [champ, rider],
            resolution_date=NOW + timedelta(days=5, hours=10),   # 2026-09-20
            settled_at=NOW - timedelta(hours=24),                # 2026-09-14
        )
        # The champion carries NO charted snapshots — the synthesize branch.
        oh = {
            rider.id: _series(rider.id, "Tadej Pogacar", [
                (NOW - timedelta(days=38), 0.25),
                (NOW - timedelta(days=1, hours=6, minutes=42), 0.0),
            ]),
        }
        return market, oh, champ, rider

    def test_the_champions_dot_lands_on_the_data_not_on_the_clock(self):
        market, oh, champ, _rider = self._vuelta()
        _apply_settled_winner_freeze(market, oh, {champ.id: "Other"})
        assert _stamp_of(oh[champ.id]) == NOW - timedelta(days=1, hours=6, minutes=42)
        assert oh[champ.id]["history"][-1]["probability"] == 1.0
        assert oh[champ.id]["history"][-1]["bookmaker"] == "settlement"

    def test_two_reads_a_second_apart_produce_the_same_timestamp(self):
        """The reader-visible property: the dot does not move between requests."""
        first_market, first_oh, champ, _ = self._vuelta()
        _apply_settled_winner_freeze(first_market, first_oh, {champ.id: "Other"})
        second_market, second_oh, champ2, _ = self._vuelta()
        _apply_settled_winner_freeze(second_market, second_oh, {champ2.id: "Other"})
        assert _stamp_of(first_oh[champ.id]) == _stamp_of(second_oh[champ2.id])

    def test_the_dot_never_precedes_the_field_it_resolves(self):
        market, oh, champ, rider = self._vuelta()
        _apply_settled_winner_freeze(market, oh, {champ.id: "Other"})
        assert _stamp_of(oh[champ.id]) >= _stamp_of(oh[rider.id])

    def test_a_charted_champion_on_a_future_schedule_lands_beside_its_own_last_point(self):
        """The other branch of the same defect: the champion HAS snapshots.

        `min(resolution_date, now)` sent this one to the clock too, appending a
        1.0 point hours or days right of the line it was supposed to finish.
        """
        champ = _outcome(1, "Spain", prob=0.587, is_winner=True)
        last_real = NOW - timedelta(days=2, hours=5)
        market = _market([champ], resolution_date=NOW + timedelta(days=6))
        oh = {1: _series(1, "Spain", [(NOW - timedelta(days=9), 0.55), (last_real, 0.587)])}
        _apply_settled_winner_freeze(market, oh, {1: "Spain"})
        assert _stamp_of(oh[1]) == last_real + timedelta(seconds=1)

    def test_an_empty_chart_falls_all_the_way_to_settled_at(self):
        """The 1,275-market arm: no schedule, no snapshots anywhere, one witness.

        A mutation that stops the route passing `settled_at` survives every other
        test in this file, because this is the only shape where that argument is
        the one that answers.
        """
        champ = _outcome(1, "Other", prob=1.0, is_winner=True)
        settled = NOW - timedelta(days=11)
        market = _market([champ], resolution_date=None, settled_at=settled)
        oh: dict = {}
        _apply_settled_winner_freeze(market, oh, {1: "Other"})
        assert _stamp_of(oh[1]) == settled

    def test_a_second_pass_over_the_same_chart_is_idempotent(self):
        """A synthesized point must never become the witness for the next one."""
        market, oh, champ, _ = self._vuelta()
        _apply_settled_winner_freeze(market, oh, {champ.id: "Other"})
        first = _stamp_of(oh[champ.id])
        _apply_settled_winner_freeze(market, oh, {champ.id: "Other"})
        assert _stamp_of(oh[champ.id]) == first
        assert len(oh[champ.id]["history"]) == 1


class TestControlsThatMustHoldBothSidesOfThisChange:
    def test_a_past_resolution_date_market_is_stamped_exactly_where_it_was(self):
        """The 593,549-market arm. If this moves, the ship widened."""
        champ = _outcome(1, "Spain", prob=0.587, is_winner=True)
        rd = NOW - timedelta(days=2)
        market = _market([champ], resolution_date=rd, settled_at=NOW - timedelta(days=1))
        oh = {1: _series(1, "Spain", [(NOW - timedelta(days=4), 0.55)])}
        _apply_settled_winner_freeze(market, oh, {1: "Spain"})
        assert _stamp_of(oh[1]) == rd

    def test_a_terminal_point_still_never_precedes_the_champions_own_last_point(self):
        champ = _outcome(1, "Spain", prob=0.587, is_winner=True)
        last_real = NOW - timedelta(hours=3)
        market = _market([champ], resolution_date=NOW - timedelta(days=9))
        oh = {1: _series(1, "Spain", [(last_real, 0.587)])}
        _apply_settled_winner_freeze(market, oh, {1: "Spain"})
        assert _stamp_of(oh[1]) == last_real + timedelta(seconds=1)

    def test_a_line_that_already_converged_gets_no_second_point(self):
        champ = _outcome(1, "Spain", prob=1.0, is_winner=True)
        market = _market([champ], resolution_date=NOW + timedelta(days=6))
        oh = {1: _series(1, "Spain", [(NOW - timedelta(days=2), 0.9995)])}
        _apply_settled_winner_freeze(market, oh, {1: "Spain"})
        assert len(oh[1]["history"]) == 1

    def test_non_champion_lines_terminate_at_their_own_last_value(self):
        champ = _outcome(1, "Spain", prob=0.587, is_winner=True)
        other = _outcome(2, "France", prob=0.30)
        market = _market([champ, other], resolution_date=NOW + timedelta(days=6))
        oh = {
            1: _series(1, "Spain", [(NOW - timedelta(days=2), 0.55)]),
            2: _series(2, "France", [(NOW - timedelta(days=2), 0.30)]),
        }
        _apply_settled_winner_freeze(market, oh, {1: "Spain", 2: "France"})
        assert oh[2]["history"][-1]["probability"] == 0.30
        assert len(oh[2]["history"]) == 1

    def test_co_winners_on_a_mutex_field_are_still_a_no_op(self):
        """Two winners where only one is possible is a CONTRADICTION (#7921).

        A stamped terminal 1.0 on both legs would publish that contradiction as a
        settled result. This market is a single-winner cycling race, so the
        no-op is the whole point.
        """
        a = _outcome(1, "A", is_winner=True)
        b = _outcome(2, "B", is_winner=True)
        market = _market(
            [a, b], resolution_date=NOW + timedelta(days=6), mutually_exclusive=True
        )
        oh = {1: _series(1, "A", [(NOW - timedelta(days=2), 0.5)])}
        _apply_settled_winner_freeze(market, oh, {1: "A", 2: "B"})
        assert len(oh[1]["history"]) == 1

    def test_a_single_non_champion_view_is_still_not_injected_into(self):
        champ = _outcome(1, "Spain", is_winner=True)
        other = _outcome(2, "France", prob=0.30)
        market = _market([champ, other], resolution_date=NOW + timedelta(days=6))
        oh = {2: _series(2, "France", [(NOW - timedelta(days=2), 0.30)])}
        _apply_settled_winner_freeze(market, oh, {1: "Spain", 2: "France"}, outcome_id_filter=2)
        assert 1 not in oh

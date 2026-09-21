"""#7784 — a price taken BEFORE a deadline is not a verdict about it.

WHAT A READER SAW, measured on production 2026-09-21 (ux filed it from a D48
pass at 390px; `market_staleness.py` and the futures route are this lane's files
under notice 41). `/futures/109403` — *When will DHS be funded again?*, an OPEN
board — drew five rungs and four of them were dates already gone, the earliest
by 129 days, each a live green bar with a live percentage:

    Before May 15, 2026   66%          Before Jul 1, 2026    96%
    Before May 22, 2026   78%          Before Jan 1, 2027    99%
    Before Jun 1, 2026    86%

The chart card one inch above already knew — *"No prices in the last 7 days."*

WHY THE EXPIRY RULE SPARED THEM. `expired_ladder_rungs` DID fire on that board
(`expired_rungs_dropped: 19`). These four survived its one exemption: a
past-dated rung priced at or above `EXPIRED_RUNG_MAX_PROBABILITY` "is the
ladder's answer, not a dead option, and is never stripped". That reasoning needs
the price to have been observed AFTER the deadline. Every rung on this board
carries the identical stamp `2026-04-30T04:46:55` — 15 to 62 days BEFORE its own
deadline, and 144 days before the reader saw it. The exemption read the market's
last forecast as its verdict.

THE FIX IS THE EXEMPTION'S OWN REASONING, SPELLED OUT: a confident price on a
past-dated rung is the ladder's answer only if it was observed once that rung's
deadline had arrived. Measured to the DAY rather than the second, because the
parser dates a rung to 23:59:59 of its named day — the five rungs in the whole
population that turn on that choice are tabulated in
`_price_is_the_ladders_answer`, and four of them are real verdicts.

NO STAMP CHANGES NOTHING, in every arm. This gate ends in a row being removed
from a reader's screen and the innocent case leaves no trace on the page it was
deleted from, so absence of evidence keeps today's behaviour.

Fixture values are the two specimens' served rows, copied from
`GET /api/futures/{id}` on 2026-09-21, not invented, so a later reader can
re-fetch the ids and check them. The clock is frozen at the minute of the
measurement for those two: their rung names carry absolute dates, so a
wall-clock test would change its own subject matter every day (gotcha #44). The
rule itself is ALSO proven on twelve clocks below, against boards whose names are
generated from the anchor, so nothing here rests on today's date.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import app.routes.futures as futures_routes
from app.routes import feed as feed_module
from app.routes import politics as politics_module
from app.utils.futures_market_snapshot import outcome_observed_at
from app.utils.market_staleness import (
    EXPIRED_RUNG_MAX_PROBABILITY,
    expired_ladder_rungs,
)

#: The minute ux photographed `/futures/109403`.
MEASURED_AT = datetime(2026, 9, 21, 11, 0, tzinfo=timezone.utc)

#: Every rung of board 109403 carries this one stamp — the board stopped being
#: repriced 144 days before the screenshot.
DHS_STAMP = datetime(2026, 4, 30, 4, 46, 55, 862136, tzinfo=timezone.utc)

# (name, probability) exactly as `GET /api/futures/109403` served them.
DHS_ROWS = [
    ("Before Jan 1, 2027", 0.9850),
    ("Before Jul 1, 2026", 0.9635),
    ("Before Jun 1, 2026", 0.8550),
    ("Before May 22, 2026", 0.7750),
    ("Before May 15, 2026", 0.6600),
]

#: The one rung on that board that can still happen.
DHS_LIVE = "Before Jan 1, 2027"
DHS_DEAD = [name for name, _ in DHS_ROWS if name != DHS_LIVE]

#: The second specimen: `/futures/1154493`, *When will Tony Gonzales depart as
#: House member?* — OPEN, `expired_rungs_dropped: 0`, 159 days stale.
GONZALES_STAMP = datetime(2026, 4, 15, 8, 45, 15, 761077, tzinfo=timezone.utc)
GONZALES_ROWS = [
    ("Before Nov 3, 2026", 0.9995),
    ("Before Apr 17, 2026", 0.9950),
    ("Before May 1, 2026", 0.9950),
    ("Before Apr 15, 2026", 0.9900),
]

#: ux's own reading of that board: "three past-dated rungs at 99-100%, TWO of
#: them priced before their own deadline". The third is stamped on its deadline's
#: own date and is left alone — see the table in `_price_is_the_ladders_answer`.
GONZALES_DEAD = ["Before Apr 17, 2026", "Before May 1, 2026"]
GONZALES_SAME_DAY = "Before Apr 15, 2026"


def _frozen(at=MEASURED_AT):
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return at if tz is None else at.astimezone(tz)

    return patch.object(futures_routes, "datetime", _Frozen)


def _outcome(outcome_id, name, prob, stamp, is_winner=None, resolution_source=None):
    """One `futures_outcomes` row as the detail serializer meets it.

    CERT-3236 made the grade a PARAMETER. It was hard-coded `None` here, and
    that is precisely why 376 green tests could not see that the ship deleted 25
    production rows the venue had already graded `is_winner=true`: every fixture
    described an ungraded board, so the one state that matters was unreachable.
    """
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        external_id=f"0x{outcome_id:064x}",
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=is_winner,
        resolution_source=resolution_source,
        last_updated=stamp,
        price_changed_at=stamp,
        team_id=None,
    )


def _board(market_id, name, rows, stamp, status="open"):
    return SimpleNamespace(
        id=market_id,
        name=name,
        description=None,
        category="politics",
        source="kalshi",
        external_id=str(market_id),
        status=status,
        sport=None,
        sport_id=None,
        event_id=None,
        market_type="quantity",
        market_tier=2,
        llm_sport_category="politics",
        # FALSE on both specimens' rows, read from `futures_markets` the same
        # day: a cumulative "Before X" ladder's rungs are nested, not exclusive.
        # It is load-bearing here — `drop_incoherent_near_certain` deletes the
        # two rungs above 0.95 on an EXCLUSIVE board, so a fixture that got this
        # flag wrong would be a different board than the one ux photographed.
        mutually_exclusive=False,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=[
            # A row may carry its grade as a third element (CERT-3236); the two
            # specimens are ungraded and read exactly as they did before.
            _outcome(i, row[0], row[1], stamp, *row[2:])
            for i, row in enumerate(rows, start=1)
        ],
    )


def dhs(stamp=DHS_STAMP, rows=None, status="open"):
    return _board(
        109403, "When will DHS be funded again?", rows or DHS_ROWS, stamp, status
    )


def gonzales(stamp=GONZALES_STAMP):
    return _board(
        1154493,
        "When will Tony Gonzales depart as House member?",
        GONZALES_ROWS,
        stamp,
    )


def _detail(market, at=MEASURED_AT):
    with _frozen(at):
        return futures_routes._format_market_detail(market, None, set())


def _names(payload):
    return [o["name"] for o in payload["outcomes"]]


def _pairs(rows):
    """The board as the surfaces passed it BEFORE this ship — no stamp."""
    return [(name, prob) for name, prob in rows]


def _triples(rows, stamp):
    return [(name, prob, stamp) for name, prob in rows]


# ───────────────────────── the specimen, on the page ──────────────────────────


class TestTheSpecimenBoard:
    """`/futures/109403` stops pricing four dates that have already passed."""

    def test_the_four_passed_dates_leave_the_table(self):
        assert _names(_detail(dhs())) == [DHS_LIVE]

    def test_the_rung_that_can_still_happen_stays(self):
        assert DHS_LIVE in _names(_detail(dhs()))

    def test_the_page_counts_what_it_dropped(self):
        assert _detail(dhs())["expired_rungs_dropped"] == len(DHS_DEAD)

    def test_the_reader_is_no_longer_offered_a_price_on_a_passed_date(self):
        priced = {
            o["name"]
            for o in _detail(dhs())["outcomes"]
            if o.get("probability") is not None
        }
        assert priced.isdisjoint(DHS_DEAD)

    def test_the_old_rule_kept_every_one_of_them(self):
        """The BEFORE, driven through the helper in the shape the page used to
        pass — without this the assertions above could be passing on a board
        that was never broken."""
        assert expired_ladder_rungs(_pairs(DHS_ROWS), MEASURED_AT) == set()

    def test_the_new_rule_names_exactly_the_four(self):
        assert expired_ladder_rungs(
            _triples(DHS_ROWS, DHS_STAMP), MEASURED_AT
        ) == set(DHS_DEAD)


class TestTheSecondSpecimen:
    """`/futures/1154493` — 159 days stale, and ux's own count is two."""

    def test_the_two_proven_forecasts_go(self):
        assert set(GONZALES_DEAD).isdisjoint(_names(_detail(gonzales())))

    def test_the_live_rung_and_the_same_day_rung_stay(self):
        assert _names(_detail(gonzales())) == ["Before Nov 3, 2026", GONZALES_SAME_DAY]

    def test_the_old_rule_kept_all_four(self):
        assert expired_ladder_rungs(_pairs(GONZALES_ROWS), MEASURED_AT) == set()


# ───────────────────── the exemption still does its own job ───────────────────


class TestAPriceObservedAfterTheDeadlineIsStillTheAnswer:
    """The rule this ship narrows must keep working where it was right."""

    def test_a_board_repriced_after_the_deadline_keeps_every_rung(self):
        fresh = MEASURED_AT - timedelta(hours=2)
        assert expired_ladder_rungs(_triples(DHS_ROWS, fresh), MEASURED_AT) == set()

    def test_the_constants_own_specimen_survives(self):
        """`In which month will SpaceX IPO?` -> `June` at 99.95%, observed after
        June ended. The census behind `EXPIRED_RUNG_MAX_PROBABILITY` is what
        this ship must not undo."""
        board = [("June 2026", 0.9995, datetime(2026, 7, 2, tzinfo=timezone.utc))]
        assert expired_ladder_rungs(board, MEASURED_AT) == set()

    def test_the_same_specimen_is_stripped_when_it_was_only_ever_a_forecast(self):
        board = [("June 2026", 0.9995, datetime(2026, 5, 2, tzinfo=timezone.utc))]
        assert expired_ladder_rungs(board, MEASURED_AT) == {"June 2026"}

    def test_a_rung_below_the_threshold_is_dropped_exactly_as_before(self):
        ghost = [("Before Jun 1, 2026", 0.02)]
        stamped = [("Before Jun 1, 2026", 0.02, MEASURED_AT)]
        assert expired_ladder_rungs(ghost, MEASURED_AT) == {"Before Jun 1, 2026"}
        assert expired_ladder_rungs(stamped, MEASURED_AT) == {"Before Jun 1, 2026"}

    def test_a_live_rung_is_untouched_however_old_its_stamp(self):
        ancient = datetime(2020, 1, 1, tzinfo=timezone.utc)
        assert expired_ladder_rungs([(DHS_LIVE, 0.985, ancient)], MEASURED_AT) == set()


class TestTheTwinArmMeasuresAgainstTheDeadlineItImplies:
    """#7383's arm dates a year-less rung off its board; the stamp follows it.

    `December 31` beside a live `December 31, 2026` is a strictly EARLIER
    occurrence, so the latest instant it can name is 2025-12-31. A confident
    price on it is the ladder's answer only if somebody observed that price once
    THAT date had arrived — the same question, asked of the same rung, against
    the deadline this arm derives rather than one the name states.
    """

    TWIN = "December 31, 2026"
    BARE = "December 31"
    IMPLIED_DEADLINE = datetime(2025, 12, 31, tzinfo=timezone.utc)

    def _board(self, stamp):
        return [
            (self.TWIN, 0.31, MEASURED_AT - timedelta(days=1)),
            (self.BARE, 1.0, stamp),
        ]

    def test_the_old_rule_kept_the_bare_rung(self):
        assert expired_ladder_rungs(
            [(self.TWIN, 0.31), (self.BARE, 1.0)], MEASURED_AT
        ) == set()

    def test_a_price_taken_before_the_implied_deadline_is_a_forecast(self):
        board = self._board(self.IMPLIED_DEADLINE - timedelta(days=90))
        assert expired_ladder_rungs(board, MEASURED_AT) == {self.BARE}

    def test_a_price_taken_after_it_still_answers_the_ladder(self):
        board = self._board(self.IMPLIED_DEADLINE + timedelta(days=14))
        assert expired_ladder_rungs(board, MEASURED_AT) == set()

    def test_the_live_twin_is_never_touched(self):
        board = self._board(self.IMPLIED_DEADLINE - timedelta(days=90))
        assert self.TWIN not in expired_ladder_rungs(board, MEASURED_AT)


class TestNoStampChangesNothing:
    """Absence of evidence is not evidence of a forecast."""

    def test_a_pair_behaves_exactly_as_it_did_before_this_ship(self):
        assert expired_ladder_rungs(_pairs(DHS_ROWS), MEASURED_AT) == set()

    def test_a_triple_with_no_stamp_behaves_the_same(self):
        assert expired_ladder_rungs(_triples(DHS_ROWS, None), MEASURED_AT) == set()

    def test_an_unreadable_stamp_is_no_stamp(self):
        assert expired_ladder_rungs(
            _triples(DHS_ROWS, "not a date at all"), MEASURED_AT
        ) == set()

    def test_a_bare_name_list_still_works(self):
        assert expired_ladder_rungs([n for n, _ in DHS_ROWS], MEASURED_AT) == set(
            DHS_DEAD
        )

    def test_the_page_keeps_the_board_whole_when_nothing_is_stamped(self):
        assert _names(_detail(dhs(stamp=None))) == [n for n, _ in DHS_ROWS]


# ─────────────────── the stamp is read to the DAY, not the second ─────────────


class TestTheDayBoundary:
    """The five rungs in the population that turn on this are in the docstring."""

    DEADLINE_DAY = datetime(2026, 9, 10, tzinfo=timezone.utc)

    def _rung(self, stamp):
        return expired_ladder_rungs(
            [("September 10, 2026", 1.0, stamp)], MEASURED_AT
        )

    def test_an_afternoon_stamp_on_the_deadlines_own_day_is_a_verdict(self):
        assert self._rung(self.DEADLINE_DAY + timedelta(hours=15)) == set()

    def test_the_first_second_of_the_deadlines_day_is_a_verdict(self):
        assert self._rung(self.DEADLINE_DAY) == set()

    def test_one_second_earlier_is_a_forecast(self):
        assert self._rung(self.DEADLINE_DAY - timedelta(seconds=1)) == {
            "September 10, 2026"
        }

    def test_the_day_before_is_a_forecast(self):
        assert self._rung(self.DEADLINE_DAY - timedelta(days=1)) == {
            "September 10, 2026"
        }


# ──────────────────────── the rule at twelve clocks ───────────────────────────

#: Twelve anchors spread across a year and over both a leap day and a New Year,
#: so nothing here can pass because of the month we happen to be in
#: (gotcha #44 — offset from the anchor, never branch on it).
CLOCKS = [
    datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc) + timedelta(days=31 * i)
    for i in range(12)
]


@pytest.mark.parametrize("anchor", CLOCKS, ids=lambda d: d.strftime("%Y-%m-%d"))
class TestTheRuleHoldsOnAnyClock:
    """The board is GENERATED from the anchor, so the subject matter travels."""

    @staticmethod
    def _board(anchor, offset_days):
        deadline = anchor - timedelta(days=30)
        name = f"Before {deadline.strftime('%b')} {deadline.day}, {deadline.year}"
        return name, deadline + timedelta(days=offset_days)

    def test_a_price_taken_before_the_deadline_stops_speaking_for_it(self, anchor):
        name, stamp = self._board(anchor, -10)
        assert expired_ladder_rungs([(name, 0.9, stamp)], anchor) == {name}

    def test_a_price_taken_after_the_deadline_still_answers_the_ladder(self, anchor):
        name, stamp = self._board(anchor, +1)
        assert expired_ladder_rungs([(name, 0.9, stamp)], anchor) == set()

    def test_no_stamp_keeps_the_old_answer(self, anchor):
        name, _ = self._board(anchor, 0)
        assert expired_ladder_rungs([(name, 0.9, None)], anchor) == set()

    def test_a_rung_still_in_the_future_is_never_touched(self, anchor):
        later = anchor + timedelta(days=60)
        name = f"Before {later.strftime('%b')} {later.day}, {later.year}"
        stamp = anchor - timedelta(days=200)
        assert expired_ladder_rungs([(name, 0.9, stamp)], anchor) == set()


# ───────────────────────── the harmful direction ──────────────────────────────


class TestTheHarmfulDirectionIsGuarded:
    def test_a_board_this_rule_would_empty_is_left_whole(self):
        """The page cannot drop itself, and an empty All Outcomes table is a
        worse answer than a stale one — the route's own rule, unchanged."""
        all_dead = [(name, prob) for name, prob in DHS_ROWS if name != DHS_LIVE]
        payload = _detail(dhs(rows=all_dead))
        assert _names(payload) == [name for name, _ in all_dead]
        assert payload["expired_rungs_dropped"] == 0

    def test_a_settled_board_is_untouched(self):
        """A settled board is a RESULT, and a result shows what ran, including
        the windows that elapsed without the event happening (#7274)."""
        assert _names(_detail(dhs(status="settled"))) == [n for n, _ in DHS_ROWS]

    def test_no_rung_becomes_live_that_was_dead_before(self):
        """The new rule may only ADD to the expired set. A specimen whose every
        rung the old rule already stripped must lose exactly the same ones."""
        ghosts = [(name, 0.01) for name, _ in DHS_ROWS if name != DHS_LIVE]
        before = expired_ladder_rungs(ghosts, MEASURED_AT)
        after = expired_ladder_rungs(
            [(n, p, DHS_STAMP) for n, p in ghosts], MEASURED_AT
        )
        assert before == after


# ───────────────────── the three call sites actually send it ──────────────────


class TestTheSurfacesPassTheStamp:
    """A helper that is never handed the stamp is a fix nobody can see."""

    def test_the_detail_page_sends_last_updated(self):
        calls = [
            node
            for node in ast.walk(ast.parse(inspect.getsource(futures_routes)))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "expired_ladder_rungs"
        ]
        assert len(calls) == 1, f"expected one detail call, found {len(calls)}"
        (listcomp,) = calls[0].args[:1]
        assert isinstance(listcomp, ast.ListComp)
        assert isinstance(listcomp.elt, ast.Tuple)
        assert len(listcomp.elt.elts) == 4, "the detail page dropped the stamp or the grade"
        assert "last_updated" in ast.unparse(listcomp.elt.elts[2])
        assert "is_winner" in ast.unparse(listcomp.elt.elts[3])

    def test_the_feed_reads_the_dual_carrier_reader_not_the_raw_column(self):
        """The mechanism, not the outcome. The CACHED path — nearly every card —
        rehydrates legs with `price_observed_epoch` and no `last_updated`, so a
        wiring that reads the column is silently inert exactly where the reader
        is, and no test built on ORM rows can see it."""
        calls = [
            node
            for node in ast.walk(ast.parse(inspect.getsource(feed_module)))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_expired_ladder_rungs"
        ]
        assert len(calls) == 1, f"expected one feed call, found {len(calls)}"
        (listcomp,) = calls[0].args[:1]
        assert isinstance(listcomp, ast.ListComp)
        assert isinstance(listcomp.elt, ast.Tuple)
        assert len(listcomp.elt.elts) == 4, "the card dropped the stamp or the grade"
        assert "_outcome_observed_at" in ast.unparse(listcomp.elt.elts[2])
        # CERT-3236: and the grade, read defensively — a rehydrated snapshot leg
        # carries no `is_winner` attribute at all, so a bare `o.is_winner` would
        # raise inside the scorer and take the whole card out (gotcha #42).
        assert ast.unparse(listcomp.elt.elts[3]) == "getattr(o, 'is_winner', None)"

    def test_a_rehydrated_leg_still_resolves_to_a_stamp(self):
        """The other half of the same claim, driven rather than parsed."""
        rehydrated = SimpleNamespace(
            id=1,
            name=DHS_DEAD[0],
            current_probability=0.66,
            price_observed_epoch=int(DHS_STAMP.timestamp()),
        )
        stamp = outcome_observed_at(rehydrated)
        assert stamp is not None
        assert expired_ladder_rungs(
            [(rehydrated.name, rehydrated.current_probability, stamp)], MEASURED_AT
        ) == {DHS_DEAD[0]}

    def test_politics_sends_the_stamp_too(self):
        calls = [
            node
            for node in ast.walk(ast.parse(inspect.getsource(politics_module)))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "expired_ladder_rungs"
        ]
        assert len(calls) == 1, f"expected one politics call, found {len(calls)}"
        (listcomp,) = calls[0].args[:1]
        assert isinstance(listcomp, ast.ListComp)
        assert isinstance(listcomp.elt, ast.Tuple)
        assert len(listcomp.elt.elts) == 4, "the dashboard dropped the stamp or the grade"
        assert "is_winner" in ast.unparse(listcomp.elt.elts[3])

    def test_a_carrier_without_the_column_does_not_raise(self):
        """Gotcha #42: a leg missing the column degrades to NO EVIDENCE, never to
        an exception inside a per-item loop."""
        bare = SimpleNamespace(name=DHS_LIVE, current_probability=0.985)
        assert outcome_observed_at(bare) is None
        assert expired_ladder_rungs(
            [(bare.name, bare.current_probability, None)], MEASURED_AT
        ) == set()


class TestTheThresholdIsUnmoved:
    """This ship narrows WHEN the exemption applies; it does not retune it."""

    def test_the_constant_is_where_the_census_put_it(self):
        assert EXPIRED_RUNG_MAX_PROBABILITY == 0.5


# ──────────── CERT-3236: a rung the venue already graded is never hidden ───────
#
# The BLOCK that made this section exist: the observation rule alone deleted 25
# production rungs carrying `is_winner=true, resolution_source='api_settlement'`,
# because a cumulative "Before Sep 1, 2026" contract settles YES on the day the
# thing HAPPENS — often weeks before its own deadline — and that settlement write
# is the last time the leg is ever touched. Its stamp is therefore permanently
# before its deadline and the stamp test reads the venue's verdict as a forecast.
#
# Reproduced independently before repairing (`artifacts/d383-7784r/`): 63 open
# boards carry a dated graded leg; the shipped rule newly hid 27 rungs on them
# and 25 were graded winners. After the repair: 0.

#: `/futures/5979169` — *When will Anthropic release Claude 5?*, OPEN. The rung
#: settled YES on 2026-08-01 and its deadline is 2026-09-01, so its only stamp is
#: a month EARLY. Values read from production 2026-09-21.
CLAUDE5_STAMP = datetime(2026, 8, 1, 4, 51, 33, 505511, tzinfo=timezone.utc)
CLAUDE5_ROWS = [
    ("Before Sep 1, 2026", 0.9900, True, "api_settlement"),
    ("Before Dec 1, 2026", 0.9950),
]


class TestAGradedWinnerIsNeverHidden:
    """The venue's verdict outranks every clock in this module."""

    def test_the_settled_rung_survives_a_stamp_taken_before_its_deadline(self):
        assert (
            expired_ladder_rungs(
                [("Before Sep 1, 2026", 0.99, CLAUDE5_STAMP, True)], MEASURED_AT
            )
            == set()
        )

    def test_the_same_rung_ungraded_is_still_removed(self):
        """The control that makes the test above mean something.

        Identical name, price and stamp; only the grade differs. Without this
        pair, a rule that simply stopped expiring `Before Sep 1, 2026` would pass.
        """
        assert expired_ladder_rungs(
            [("Before Sep 1, 2026", 0.99, CLAUDE5_STAMP, None)], MEASURED_AT
        ) == {"Before Sep 1, 2026"}

    def test_is_winner_false_is_not_a_grade(self):
        """`futures_outcomes.is_winner` is `default=False`, so FALSE is what a row
        is BORN with. Reading it as "graded a loser" here would be harmless, but
        reading it as a grade AT ALL is the class of bug #4788 documents — so the
        test is that only TRUE spares a rung."""
        assert expired_ladder_rungs(
            [("Before Sep 1, 2026", 0.99, CLAUDE5_STAMP, False)], MEASURED_AT
        ) == {"Before Sep 1, 2026"}

    def test_a_graded_winner_is_spared_by_the_twin_arm_too(self):
        """#7383's arm expires a rung a LIVE dated twin proves dead. A verdict is
        not made untrue by a sibling rung, so the grade is read before either arm
        rather than inside one of them."""
        rows = [
            ("September 14", 1.0, CLAUDE5_STAMP, True),
            ("September 30", 0.42, CLAUDE5_STAMP, None),
        ]
        assert "September 14" not in expired_ladder_rungs(rows, MEASURED_AT)

    def test_a_low_priced_graded_winner_is_also_spared(self):
        """The clause is unconditional, and measured to take nothing from master:
        0 graded winners are expired by the pre-#7784 rule on today's population,
        so nothing master hides stops being hidden."""
        assert (
            expired_ladder_rungs(
                [("Before Sep 1, 2026", 0.12, CLAUDE5_STAMP, True)], MEASURED_AT
            )
            == set()
        )

    def test_the_detail_page_keeps_the_settled_rung_and_drops_the_dead_ones(self):
        """Both halves on one board, through the serializer the reader gets."""
        board = _board(
            5979169,
            "When will Anthropic release Claude 5?",
            CLAUDE5_ROWS,
            CLAUDE5_STAMP,
        )
        names = _names(_detail(board))
        assert "Before Sep 1, 2026" in names
        assert "Before Dec 1, 2026" in names

    def test_the_dhs_specimen_is_unmoved_by_the_repair(self):
        """The ship still ships: not one of the four stale forecasts is graded, so
        the repair cannot resurrect them."""
        names = _names(_detail(dhs()))
        for dead in DHS_DEAD:
            assert dead not in names
        assert DHS_LIVE in names

    def test_a_grade_that_is_absent_changes_nothing(self):
        """A pair, a triple, and a four-tuple whose grade is `None` agree — which
        is what lets the politics/feed `getattr` defaults be safe."""
        rows3 = _triples(DHS_ROWS, DHS_STAMP)
        rows4 = [(n, p, s, None) for n, p, s in rows3]
        assert expired_ladder_rungs(rows4, MEASURED_AT) == expired_ladder_rungs(
            rows3, MEASURED_AT
        )
